"""
PolyHunter Engine -- Pre-Trade Validator
Runs 13 safety checks before every copy-trade execution.
"""
import logging
from datetime import datetime, timezone, timedelta

from bot.engine.calculator import calculate_buy_size
from bot.engine.circuit_breaker import circuit_breaker
from bot.config import MIN_MARKET_LIQUIDITY, SIGNAL_MAX_AGE_SECONDS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(config, key: str, default=None):
    """Read a field from *config* (dict or object)."""
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _float_or(config, key: str, default: float = 0.0) -> float:
    val = _cfg(config, key)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# In-memory per-config spend tracking (supplements the DB field)
# ---------------------------------------------------------------------------
# Maps config_id -> { market_slug -> spent_usd }
_per_market_spend: dict[str, dict[str, float]] = {}
# Maps config_id -> { outcome_key -> spent_usd }  outcome_key = f"{market_slug}:{side}"
_per_outcome_spend: dict[str, dict[str, float]] = {}
# Maps config_id -> set of market slugs currently held
_active_markets: dict[str, set[str]] = {}


def record_spend(config_id: str, market_slug: str, side: str, amount_usd: float):
    """Called after a successful trade to update in-memory spend trackers."""
    if config_id not in _per_market_spend:
        _per_market_spend[config_id] = {}
    _per_market_spend[config_id].setdefault(market_slug, 0.0)
    _per_market_spend[config_id][market_slug] += amount_usd

    outcome_key = f"{market_slug}:{side}"
    if config_id not in _per_outcome_spend:
        _per_outcome_spend[config_id] = {}
    _per_outcome_spend[config_id].setdefault(outcome_key, 0.0)
    _per_outcome_spend[config_id][outcome_key] += amount_usd

    if config_id not in _active_markets:
        _active_markets[config_id] = set()
    _active_markets[config_id].add(market_slug)


# ---------------------------------------------------------------------------
# PreTradeValidator
# ---------------------------------------------------------------------------

class PreTradeValidator:
    """Runs all 13 pre-trade checks.

    Each check method returns ``(passed: bool, reason: str)``.
    The public :meth:`validate` method runs them in sequence and returns
    as soon as one fails, or proceeds to compute the trade amount.

    Args (to ``validate``):
        config:   The user's ``copy_trade_configs`` row (dict).
        signal:   A :class:`TradeSignal` instance.
        executor: A :class:`TradeExecutor` for orderbook queries.
        telegram_user_id: The Telegram user ID (for circuit breaker lookups
                          and CLOB API calls).

    Returns:
        ``(should_execute, amount_usd, rejection_reason)``
    """

    def __init__(self, executor=None):
        self._executor = executor

    async def validate(
        self,
        config,
        signal,
        executor=None,
        telegram_user_id: int = 0,
    ) -> tuple[bool, float, str]:
        """Run all 13 checks.

        Returns:
            ``(should_execute, trade_amount_usd, rejection_reason)``
            If ``should_execute`` is ``True``, ``rejection_reason`` is empty.
        """
        exe = executor or self._executor
        checks = [
            self._check_credentials_active(config),
            self._check_config_active(config),
            self._check_direction_allowed(config, signal),
            self._check_above_ignore_threshold(config, signal),
            self._check_price_range(config, signal),
            self._check_total_spend_limit(config, signal),
            self._check_per_outcome_limit(config, signal),
            self._check_per_market_limit(config, signal),
            self._check_max_markets(config, signal),
            await self._check_market_liquidity(config, signal, exe, telegram_user_id),
            self._check_market_not_expiring(signal),
            self._check_signal_freshness(signal),
            self._check_circuit_breaker(config, telegram_user_id),
        ]

        for passed, reason in checks:
            if not passed:
                logger.info('[VALIDATOR] Rejected: %s (config=%s signal_tx=%s)',
                            reason,
                            _cfg(config, 'id', '?')[:8],
                            signal.tx_hash[:12] if signal.tx_hash else '?')
                return False, 0.0, reason

        # All checks passed — compute trade amount
        amount = calculate_buy_size(config, signal)
        if amount <= 0:
            return False, 0.0, 'Calculated trade amount is zero after constraints'

        return True, amount, ''

    # ------------------------------------------------------------------
    # Individual checks — each returns (passed: bool, reason: str)
    # ------------------------------------------------------------------

    def _check_credentials_active(self, config) -> tuple[bool, str]:
        """1. Credentials are active and not revoked."""
        cred_active = _cfg(config, 'credentials_active', True)
        if not cred_active:
            return False, 'User credentials are not active or have been revoked'
        return True, ''

    def _check_config_active(self, config) -> tuple[bool, str]:
        """2. Copy-trade configuration is active (not paused)."""
        is_active = _cfg(config, 'is_active', True)
        if not is_active:
            return False, 'Copy-trade configuration is paused'
        return True, ''

    def _check_direction_allowed(self, config, signal) -> tuple[bool, str]:
        """3. The signal direction (BUY/SELL) is allowed by config."""
        side = signal.side.upper()
        if side == 'BUY' and not _cfg(config, 'copy_buy', True):
            return False, 'Copy-buy is disabled in configuration'
        if side == 'SELL' and not _cfg(config, 'copy_sell', True):
            return False, 'Copy-sell is disabled in configuration'
        return True, ''

    def _check_above_ignore_threshold(self, config, signal) -> tuple[bool, str]:
        """4. Target trade value is above the ignore threshold."""
        threshold = _float_or(config, 'ignore_trades_under_usd', 0.0)
        if threshold > 0 and signal.value_usd < threshold:
            return (
                False,
                f'Target trade ${signal.value_usd:.2f} is below '
                f'ignore threshold ${threshold:.2f}',
            )
        return True, ''

    def _check_price_range(self, config, signal) -> tuple[bool, str]:
        """5. Signal price is within the user's min/max price range."""
        price = signal.price
        if price <= 0:
            # If price is unknown, pass the check (will be validated at execution)
            return True, ''

        min_price = _float_or(config, 'min_price', 0.0)
        max_price = _float_or(config, 'max_price', 0.0)

        if min_price > 0 and price < min_price:
            return (
                False,
                f'Price ${price:.2f} is below min_price ${min_price:.2f}',
            )
        if max_price > 0 and price > max_price:
            return (
                False,
                f'Price ${price:.2f} is above max_price ${max_price:.2f}',
            )
        return True, ''

    def _check_total_spend_limit(self, config, signal) -> tuple[bool, str]:
        """6. Adding this trade does not exceed the total spend limit."""
        total_limit = _float_or(config, 'total_spend_limit_usd', 0.0)
        if total_limit <= 0:
            return True, ''  # No limit configured

        total_spent = _float_or(config, 'total_spent_usd', 0.0)
        if total_spent >= total_limit:
            return (
                False,
                f'Total spend limit reached (${total_spent:.2f} / ${total_limit:.2f})',
            )
        return True, ''

    def _check_per_outcome_limit(self, config, signal) -> tuple[bool, str]:
        """7. Per-outcome (YES/NO) spend limit not exceeded."""
        limit = _float_or(config, 'max_per_yes_no_usd', 0.0)
        if limit <= 0:
            return True, ''

        config_id = str(_cfg(config, 'id', ''))
        slug = signal.market_slug or ''
        side = signal.side.upper()
        outcome_key = f"{slug}:{side}"

        spent = _per_outcome_spend.get(config_id, {}).get(outcome_key, 0.0)
        if spent >= limit:
            return (
                False,
                f'Per-outcome limit reached for {outcome_key} '
                f'(${spent:.2f} / ${limit:.2f})',
            )
        return True, ''

    def _check_per_market_limit(self, config, signal) -> tuple[bool, str]:
        """8. Per-market spend limit not exceeded."""
        limit = _float_or(config, 'max_per_market_usd', 0.0)
        if limit <= 0:
            return True, ''

        config_id = str(_cfg(config, 'id', ''))
        slug = signal.market_slug or ''

        spent = _per_market_spend.get(config_id, {}).get(slug, 0.0)
        if spent >= limit:
            return (
                False,
                f'Per-market limit reached for {slug} '
                f'(${spent:.2f} / ${limit:.2f})',
            )
        return True, ''

    def _check_max_markets(self, config, signal) -> tuple[bool, str]:
        """9. Maximum number of distinct markets not exceeded."""
        max_markets = _float_or(config, 'max_markets', 0.0)
        if max_markets <= 0:
            return True, ''

        config_id = str(_cfg(config, 'id', ''))
        current_markets = _active_markets.get(config_id, set())
        slug = signal.market_slug or ''

        if slug in current_markets:
            return True, ''  # Already trading this market

        if len(current_markets) >= int(max_markets):
            return (
                False,
                f'Max markets limit reached ({len(current_markets)}'
                f' / {int(max_markets)})',
            )
        return True, ''

    async def _check_market_liquidity(
        self,
        config,
        signal,
        executor,
        telegram_user_id: int,
    ) -> tuple[bool, str]:
        """10. Market has at least $10,000 liquidity in the orderbook."""
        min_liquidity = MIN_MARKET_LIQUIDITY  # $10,000 default

        if not signal.token_id or executor is None:
            # Cannot check without token_id or executor — pass cautiously
            return True, ''

        try:
            liquidity = await executor.get_orderbook_liquidity(
                telegram_user_id, signal.token_id,
            )
        except Exception:
            logger.exception('[VALIDATOR] Error checking liquidity')
            liquidity = 0.0

        if liquidity < min_liquidity:
            return (
                False,
                f'Market liquidity ${liquidity:,.0f} is below '
                f'minimum ${min_liquidity:,.0f}',
            )
        return True, ''

    def _check_market_not_expiring(self, signal) -> tuple[bool, str]:
        """11. Market is not expiring within 1 hour."""
        if signal.market_end_time is None:
            return True, ''  # Unknown end time — pass

        now = datetime.now(timezone.utc)
        time_left = signal.market_end_time - now

        if time_left < timedelta(hours=1):
            minutes = max(0, time_left.total_seconds() / 60)
            return (
                False,
                f'Market expires in {minutes:.0f} minutes '
                f'(minimum 60 minutes required)',
            )
        return True, ''

    def _check_signal_freshness(self, signal) -> tuple[bool, str]:
        """12. Signal is not older than SIGNAL_MAX_AGE_SECONDS (30s default)."""
        now = datetime.now(timezone.utc)
        age = (now - signal.detected_at).total_seconds()

        if age > SIGNAL_MAX_AGE_SECONDS:
            return (
                False,
                f'Signal is {age:.1f}s old (max {SIGNAL_MAX_AGE_SECONDS}s)',
            )
        return True, ''

    def _check_circuit_breaker(self, config, telegram_user_id: int) -> tuple[bool, str]:
        """13. Circuit breaker is not tripped for the user or system-wide."""
        if circuit_breaker.is_tripped(telegram_user_id):
            return False, 'Circuit breaker tripped — trading paused'
        return True, ''
