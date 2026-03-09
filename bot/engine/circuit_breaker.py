"""
PolyHunter Engine -- Circuit Breaker
Automatic kill switches that halt trading when anomalous conditions are
detected, as defined in the DEFENSIVE_SECURITY_SPEC.

Triggers
--------
1. Single trade loses > 20% of daily budget -> pause **user**.
2. 3 consecutive losses for a user            -> pause **user**.
3. > 50% of trades in last hour are losses    -> pause **all**.
4. API error rate > 30% in 5 minutes          -> pause **all**.

Resets
------
* Per-user:  ``/resume`` command calls ``reset_user(telegram_user_id)``.
* System:    Admin calls ``reset_system()``.
* API errors auto-reset when the 5-minute error rate drops below 5%.
"""
import logging
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal state containers
# ---------------------------------------------------------------------------

@dataclass
class _UserState:
    """Mutable per-user circuit breaker state."""
    tripped: bool = False
    trip_reason: str = ''
    consecutive_losses: int = 0
    # Ring buffer of (timestamp, was_loss) for hourly loss-rate calculation
    recent_trades: deque = field(default_factory=lambda: deque(maxlen=200))


@dataclass
class _ApiErrorWindow:
    """Rolling window of API call outcomes over 5 minutes."""
    # (timestamp, is_error)
    calls: deque = field(default_factory=lambda: deque(maxlen=1000))


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """In-memory circuit breaker for the PolyHunter copy-trade engine.

    All state is class-instance-level (not per-process persistent).
    A server restart resets all breakers.
    """

    def __init__(self) -> None:
        # Per-user state keyed by telegram_user_id
        self._users: dict[int, _UserState] = {}
        # System-wide trip flag
        self._system_tripped: bool = False
        self._system_trip_reason: str = ''
        # API error tracking
        self._api_errors = _ApiErrorWindow()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_user(self, telegram_user_id: int) -> _UserState:
        if telegram_user_id not in self._users:
            self._users[telegram_user_id] = _UserState()
        return self._users[telegram_user_id]

    def _prune_api_window(self) -> None:
        """Remove entries older than 5 minutes from the API error window."""
        cutoff = time.monotonic() - 300  # 5 minutes
        while self._api_errors.calls and self._api_errors.calls[0][0] < cutoff:
            self._api_errors.calls.popleft()

    # ------------------------------------------------------------------
    # Recording outcomes
    # ------------------------------------------------------------------

    def record_trade_result(
        self,
        telegram_user_id: int,
        was_loss: bool,
        loss_pct: float = 0.0,
        daily_budget: float = 0.0,
    ) -> None:
        """Record the result of a trade and check for trip conditions.

        Args:
            telegram_user_id: Telegram user whose trade completed.
            was_loss:         Whether the trade was a loss.
            loss_pct:         Magnitude of loss as a percentage of position
                              value (e.g. ``25.0`` means 25%).
            daily_budget:     The user's configured daily spend budget in USD.
        """
        user = self._get_user(telegram_user_id)
        now = time.monotonic()
        user.recent_trades.append((now, was_loss))

        if was_loss:
            user.consecutive_losses += 1
        else:
            user.consecutive_losses = 0

        # --- Trigger 1: Single trade loses > 20% of daily budget -----------
        if was_loss and daily_budget > 0 and loss_pct > 20.0:
            user.tripped = True
            user.trip_reason = (
                f'Single trade lost {loss_pct:.1f}% of daily budget '
                f'(threshold 20%)'
            )
            logger.warning(
                '[CIRCUIT] User %d tripped: %s',
                telegram_user_id, user.trip_reason,
            )

        # --- Trigger 2: 3 consecutive losses --------------------------------
        if user.consecutive_losses >= 3:
            user.tripped = True
            user.trip_reason = (
                f'{user.consecutive_losses} consecutive losses'
            )
            logger.warning(
                '[CIRCUIT] User %d tripped: %s',
                telegram_user_id, user.trip_reason,
            )

        # --- Trigger 3: > 50% of trades in last hour are losses -------------
        self._check_hourly_loss_rate()

    def record_api_error(self) -> None:
        """Record a failed API call and check error-rate trigger."""
        now = time.monotonic()
        self._api_errors.calls.append((now, True))
        self._check_api_error_rate()

    def record_api_success(self) -> None:
        """Record a successful API call (for error-rate denominator)."""
        now = time.monotonic()
        self._api_errors.calls.append((now, False))
        # Auto-reset: if error rate dropped below 5%, un-trip system
        self._check_api_auto_reset()

    # ------------------------------------------------------------------
    # Trip-condition evaluators
    # ------------------------------------------------------------------

    def _check_hourly_loss_rate(self) -> None:
        """Trigger 3: if > 50% of all trades across all users in the last
        hour were losses, trip the system."""
        cutoff = time.monotonic() - 3600
        total = 0
        losses = 0
        for user_state in self._users.values():
            for ts, was_loss in user_state.recent_trades:
                if ts >= cutoff:
                    total += 1
                    if was_loss:
                        losses += 1

        if total >= 4 and (losses / total) > 0.5:
            self._system_tripped = True
            self._system_trip_reason = (
                f'{losses}/{total} trades in last hour were losses '
                f'({losses / total * 100:.0f}%)'
            )
            logger.critical(
                '[CIRCUIT] SYSTEM tripped: %s', self._system_trip_reason,
            )

    def _check_api_error_rate(self) -> None:
        """Trigger 4: if API error rate > 30% in 5-minute window, trip system."""
        self._prune_api_window()
        calls = self._api_errors.calls
        if len(calls) < 5:
            return  # Not enough data

        errors = sum(1 for _, is_err in calls if is_err)
        rate = errors / len(calls)

        if rate > 0.30:
            self._system_tripped = True
            self._system_trip_reason = (
                f'API error rate {rate * 100:.0f}% '
                f'({errors}/{len(calls)} in 5 min window)'
            )
            logger.critical(
                '[CIRCUIT] SYSTEM tripped: %s', self._system_trip_reason,
            )

    def _check_api_auto_reset(self) -> None:
        """Auto-reset system breaker when API error rate drops below 5%."""
        if not self._system_tripped:
            return
        if 'API error rate' not in self._system_trip_reason:
            return  # System was tripped for a different reason

        self._prune_api_window()
        calls = self._api_errors.calls
        if len(calls) < 5:
            return

        errors = sum(1 for _, is_err in calls if is_err)
        rate = errors / len(calls)

        if rate < 0.05:
            logger.info(
                '[CIRCUIT] API error rate recovered to %.0f%% — auto-resetting system',
                rate * 100,
            )
            self._system_tripped = False
            self._system_trip_reason = ''

    # ------------------------------------------------------------------
    # Query state
    # ------------------------------------------------------------------

    def is_tripped(self, telegram_user_id: int) -> bool:
        """Check whether trading is paused for *telegram_user_id*.

        Returns ``True`` if either the user-level or system-level breaker
        is tripped.
        """
        if self._system_tripped:
            return True
        user = self._users.get(telegram_user_id)
        if user and user.tripped:
            return True
        return False

    def get_trip_reason(self, telegram_user_id: int) -> str:
        """Return a human-readable reason for the trip, or empty string."""
        if self._system_tripped:
            return f'System: {self._system_trip_reason}'
        user = self._users.get(telegram_user_id)
        if user and user.tripped:
            return user.trip_reason
        return ''

    # ------------------------------------------------------------------
    # Reset methods
    # ------------------------------------------------------------------

    def reset_user(self, telegram_user_id: int) -> None:
        """Reset the circuit breaker for a single user (called by /resume)."""
        user = self._users.get(telegram_user_id)
        if user:
            user.tripped = False
            user.trip_reason = ''
            user.consecutive_losses = 0
            logger.info('[CIRCUIT] User %d breaker reset', telegram_user_id)

    def reset_system(self) -> None:
        """Reset the system-wide circuit breaker (called by admin)."""
        self._system_tripped = False
        self._system_trip_reason = ''
        # Also clear all user breakers
        for uid, user in self._users.items():
            user.tripped = False
            user.trip_reason = ''
            user.consecutive_losses = 0
        logger.info('[CIRCUIT] System-wide breaker reset (all users cleared)')


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
circuit_breaker = CircuitBreaker()
