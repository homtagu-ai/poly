"""
PolyHunter Engine -- Wallet Monitor
Detects trades from target wallets by polling Etherscan v2.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from shared.constants import USDC_E_ADDRESS, EXCHANGE_PROXY
from shared.etherscan import fetch_wallet_transfers, detect_trade_direction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data class for trade signals detected from on-chain activity
# ---------------------------------------------------------------------------

@dataclass
class TradeSignal:
    """Represents a detected trade from a target wallet."""
    target_wallet: str
    tx_hash: str
    side: str                         # 'BUY' or 'SELL'
    value_usd: float
    token_id: str = ''                # empty until resolved via CLOB/Gamma
    market_slug: str = ''             # empty until resolved via CLOB/Gamma
    price: float = 0.0
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    market_end_time: datetime | None = None


# ---------------------------------------------------------------------------
# In-memory state to track already-seen transactions per wallet
# ---------------------------------------------------------------------------

# Maps wallet_address (lowercase) -> set of tx_hashes we have already processed
_wallet_monitor_state: dict[str, set[str]] = {}


def _get_seen_hashes(wallet: str) -> set[str]:
    """Return the set of tx hashes already seen for *wallet*."""
    key = wallet.lower()
    if key not in _wallet_monitor_state:
        _wallet_monitor_state[key] = set()
    return _wallet_monitor_state[key]


def _mark_seen(wallet: str, tx_hash: str) -> None:
    """Record *tx_hash* as processed for *wallet*."""
    _get_seen_hashes(wallet).add(tx_hash)


def _prune_state(wallet: str, max_entries: int = 500) -> None:
    """Prevent unbounded growth of the seen-hashes set.

    When the set exceeds *max_entries* we keep only the most-recently-added
    half.  Because Python 3.7+ ``set`` does not guarantee insertion order we
    convert to a list-based approach (dict preserves insertion order).
    """
    key = wallet.lower()
    seen = _wallet_monitor_state.get(key)
    if seen is None or len(seen) <= max_entries:
        return
    # Keep the last max_entries // 2 items — they are the newest
    as_list = list(seen)
    keep = as_list[-(max_entries // 2):]
    _wallet_monitor_state[key] = set(keep)
    logger.debug('[MONITOR] Pruned state for %s from %d to %d entries',
                 wallet, len(as_list), len(keep))


# ---------------------------------------------------------------------------
# WalletMonitor
# ---------------------------------------------------------------------------

class WalletMonitor:
    """Detects trades from target wallets by polling Etherscan v2."""

    def __init__(self) -> None:
        self._exchange_proxy = EXCHANGE_PROXY.lower()

    async def check_wallet(self, target_wallet: str) -> list[TradeSignal]:
        """Poll Etherscan for new USDC.e transfers for *target_wallet*.

        Uses ``shared.etherscan.fetch_wallet_transfers()`` to query the
        Etherscan v2 API for recent ERC-20 transfers of the USDC.e token.
        Compares each transaction hash against the in-memory state to
        detect new transactions.

        Returns:
            A list of :class:`TradeSignal` instances for any *new*
            transfers that involve the Polymarket Exchange Proxy.
        """
        wallet_lower = target_wallet.lower()
        signals: list[TradeSignal] = []

        try:
            transfers = fetch_wallet_transfers(
                address=target_wallet,
                contract_address=USDC_E_ADDRESS,
                limit=25,
            )
        except Exception:
            logger.exception('[MONITOR] Error fetching transfers for %s',
                             target_wallet)
            return signals

        if not transfers:
            return signals

        seen = _get_seen_hashes(wallet_lower)

        # On first run we seed state without emitting signals so we don't
        # replay the entire history.
        is_first_run = len(seen) == 0
        if is_first_run:
            for tx in transfers:
                _mark_seen(wallet_lower, tx['tx_hash'])
            logger.info('[MONITOR] Seeded %d tx hashes for %s (first run)',
                        len(transfers), target_wallet)
            return signals

        for tx in transfers:
            tx_hash = tx.get('tx_hash', '')
            if not tx_hash or tx_hash in seen:
                continue

            # Determine trade direction relative to Exchange Proxy
            direction = detect_trade_direction(tx, self._exchange_proxy)
            if direction is None:
                # Not a Polymarket trade — skip but still mark as seen
                _mark_seen(wallet_lower, tx_hash)
                continue

            side = direction.upper()  # 'BUY' or 'SELL'
            value_usd = tx.get('value_usd', 0.0)

            signal = TradeSignal(
                target_wallet=wallet_lower,
                tx_hash=tx_hash,
                side=side,
                value_usd=value_usd,
                detected_at=datetime.now(timezone.utc),
            )
            signals.append(signal)
            _mark_seen(wallet_lower, tx_hash)

            logger.info(
                '[MONITOR] New %s signal: wallet=%s tx=%s value=$%.2f',
                side, target_wallet[:10], tx_hash[:16], value_usd,
            )

        _prune_state(wallet_lower)
        return signals


# ---------------------------------------------------------------------------
# Module-level convenience instance
# ---------------------------------------------------------------------------
wallet_monitor = WalletMonitor()
