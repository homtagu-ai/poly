"""
PolyHunter Background Task -- Take Profit / Stop Loss Monitor
Checks all open positions against TP/SL thresholds every 30 seconds
and executes sell orders when triggers are hit.
"""
import asyncio
import logging

from bot.config import TP_SL_CHECK_INTERVAL
from bot.engine.circuit_breaker import circuit_breaker
from shared.supabase import _supabase_rest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_positions_with_tp_sl() -> list[dict]:
    """Fetch all copy-trade configs that have TP or SL configured and are
    active.  Each row is enriched with position data from the DB.

    We query ``copy_trade_configs`` where ``tp_value`` or ``sl_value``
    is set and the config is active.  The ``tp_mode`` / ``sl_mode``
    columns indicate whether the value is a percentage or an absolute price.
    """
    rows = _supabase_rest(
        'copy_trade_configs',
        method='GET',
        match={'is_active': 'true'},
    )
    if not isinstance(rows, list):
        return []

    # Filter to configs that have any TP/SL setting
    results = []
    for row in rows:
        has_tp = row.get('tp_value') is not None
        has_sl = row.get('sl_value') is not None
        if has_tp or has_sl:
            results.append(row)
    return results


def _log_trade(telegram_user_id: int, action: str, **kwargs) -> None:
    """Insert a row into the ``trade_log`` audit table."""
    data = {'telegram_user_id': telegram_user_id, 'action': action}
    data.update(kwargs)
    _supabase_rest('trade_log', method='POST', data=data)


# ---------------------------------------------------------------------------
# TpSlMonitorTask
# ---------------------------------------------------------------------------

class TpSlMonitorTask:
    """Checks all open positions against TP/SL thresholds periodically.

    For each user config that has TP or SL values set:

    1. Fetch the current price from the CLOB orderbook.
    2. Compare against TP/SL thresholds (percentage or price mode).
    3. If triggered, execute a sell order and notify the user.
    """

    def __init__(self, executor, telegram_app=None) -> None:
        """
        Args:
            executor:     A :class:`TradeExecutor` for price lookups and
                          order placement.
            telegram_app: The ``telegram.ext.Application`` for sending
                          notifications to users.
        """
        self._executor = executor
        self._app = telegram_app

    async def run(self) -> None:
        """Main loop -- runs forever until cancelled."""
        logger.info('[TP/SL] Monitor task started (interval=%ds)',
                    TP_SL_CHECK_INTERVAL)
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                logger.info('[TP/SL] Monitor task cancelled')
                raise
            except Exception:
                logger.exception('[TP/SL] Unexpected error in monitor tick')
            await asyncio.sleep(TP_SL_CHECK_INTERVAL)

    async def _tick(self) -> None:
        """Single check iteration."""
        configs = _get_positions_with_tp_sl()
        if not configs:
            return

        for config in configs:
            try:
                await self._check_config(config)
            except Exception:
                logger.exception(
                    '[TP/SL] Error checking config %s',
                    config.get('id', '?')[:8],
                )

    async def _check_config(self, config: dict) -> None:
        """Check one config's positions against its TP/SL thresholds."""
        telegram_user_id = int(config.get('telegram_user_id', 0))
        config_id = config.get('id', '')

        if telegram_user_id <= 0:
            return

        # Skip if circuit breaker is active
        if circuit_breaker.is_tripped(telegram_user_id):
            return

        # Get positions for this user
        positions = await self._executor.get_positions(telegram_user_id)
        if not positions:
            return

        for pos in positions:
            token_id = pos.get('token_id', '')
            if not token_id:
                continue

            # Get current price from orderbook
            current_price = await self._executor.get_current_price(
                telegram_user_id, token_id,
            )
            if current_price is None or current_price <= 0:
                continue

            avg_price = float(pos.get('avg_price', 0))
            size = float(pos.get('size', 0))
            if avg_price <= 0 or size <= 0:
                continue

            # Calculate current P&L percentage
            pnl_pct = ((current_price - avg_price) / avg_price) * 100

            trigger_type = None
            trigger_reason = ''

            # --- Check Take Profit ---
            tp_val = _safe_float(config.get('tp_value'))
            tp_mode = config.get('tp_mode', 'percentage')

            if tp_val is not None and tp_val > 0:
                if tp_mode == 'price':
                    if current_price >= tp_val:
                        trigger_type = 'TP'
                        trigger_reason = (
                            f'Take Profit triggered: price ${current_price:.4f} '
                            f'>= target ${tp_val:.4f}'
                        )
                else:
                    # percentage mode
                    if pnl_pct >= tp_val:
                        trigger_type = 'TP'
                        trigger_reason = (
                            f'Take Profit triggered: P&L {pnl_pct:.1f}% '
                            f'>= threshold {tp_val:.1f}%'
                        )

            # --- Check Stop Loss ---
            sl_val = _safe_float(config.get('sl_value'))
            sl_mode = config.get('sl_mode', 'percentage')

            if trigger_type is None and sl_val is not None and sl_val > 0:
                if sl_mode == 'price':
                    if current_price <= sl_val:
                        trigger_type = 'SL'
                        trigger_reason = (
                            f'Stop Loss triggered: price ${current_price:.4f} '
                            f'<= threshold ${sl_val:.4f}'
                        )
                else:
                    # percentage mode — SL is a positive number but
                    # triggers on negative P&L
                    if pnl_pct <= -sl_val:
                        trigger_type = 'SL'
                        trigger_reason = (
                            f'Stop Loss triggered: P&L {pnl_pct:.1f}% '
                            f'<= threshold -{sl_val:.1f}%'
                        )

            if trigger_type is None:
                continue

            # --- Execute the TP/SL sell ---
            logger.info(
                '[TP/SL] %s for user %d token %s: %s',
                trigger_type, telegram_user_id, token_id[:16], trigger_reason,
            )

            await self._execute_tp_sl_sell(
                config=config,
                telegram_user_id=telegram_user_id,
                token_id=token_id,
                size=size,
                current_price=current_price,
                avg_price=avg_price,
                pnl_pct=pnl_pct,
                trigger_type=trigger_type,
                trigger_reason=trigger_reason,
            )

    async def _execute_tp_sl_sell(
        self,
        config: dict,
        telegram_user_id: int,
        token_id: str,
        size: float,
        current_price: float,
        avg_price: float,
        pnl_pct: float,
        trigger_type: str,
        trigger_reason: str,
    ) -> None:
        """Execute a sell order to close (or reduce) a position."""
        from bot.engine.monitor import TradeSignal
        from datetime import datetime, timezone

        # Build a synthetic signal for the executor
        sell_signal = TradeSignal(
            target_wallet='tp_sl_monitor',
            tx_hash=f'{trigger_type}_{token_id[:16]}_{int(datetime.now(timezone.utc).timestamp())}',
            side='SELL',
            value_usd=size * current_price,
            token_id=token_id,
            market_slug=config.get('market_slug', ''),
            price=current_price,
            detected_at=datetime.now(timezone.utc),
        )

        trade_size_usd = size * current_price

        result = await self._executor.place_order(
            telegram_user_id=telegram_user_id,
            signal=sell_signal,
            trade_size_usd=trade_size_usd,
            config=config,
        )

        if result.success:
            realised_pnl = (result.fill_price - avg_price) * size

            _log_trade(
                telegram_user_id=telegram_user_id,
                action=f'{trigger_type.lower()}_executed',
                market_slug=config.get('market_slug', ''),
                signal_source='tp_sl_monitor',
                signal_price=current_price,
                execution_price=result.fill_price,
                order_size_usd=trade_size_usd,
                outcome='SELL',
                polymarket_order_id=result.order_id,
            )

            # Record as a loss/win in circuit breaker
            was_loss = realised_pnl < 0
            circuit_breaker.record_trade_result(
                telegram_user_id,
                was_loss=was_loss,
                loss_pct=abs(pnl_pct) if was_loss else 0.0,
            )

            await self._notify_user(
                telegram_user_id,
                f"{trigger_type} EXECUTED\n"
                f"Market: {config.get('market_slug', 'Unknown')}\n"
                f"{trigger_reason}\n"
                f"Sold: {size:.2f} shares @ ${result.fill_price:.4f}\n"
                f"P&L: {'+'if realised_pnl >= 0 else ''}"
                f"${realised_pnl:.2f} ({pnl_pct:+.1f}%)\n"
                f"Order ID: {result.order_id}",
            )
        else:
            _log_trade(
                telegram_user_id=telegram_user_id,
                action=f'{trigger_type.lower()}_failed',
                market_slug=config.get('market_slug', ''),
                signal_source='tp_sl_monitor',
                signal_price=current_price,
                order_size_usd=trade_size_usd,
                outcome='SELL',
                failure_reason=result.error,
            )
            circuit_breaker.record_api_error()

            await self._notify_user(
                telegram_user_id,
                f"{trigger_type} FAILED\n"
                f"Market: {config.get('market_slug', 'Unknown')}\n"
                f"{trigger_reason}\n"
                f"Error: {result.error}\n"
                f"Manual action may be required.",
            )

    async def _notify_user(self, telegram_user_id: int, text: str) -> None:
        """Send a Telegram notification to the user."""
        if not self._app or telegram_user_id <= 0:
            return
        try:
            await self._app.bot.send_message(
                chat_id=telegram_user_id,
                text=text,
                parse_mode=None,
            )
        except Exception:
            logger.exception('[TP/SL] Failed to notify user %d',
                             telegram_user_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value) -> float | None:
    """Convert *value* to float, returning ``None`` if not possible."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
