"""
PolyHunter Background Task -- Wallet Poller
Continuously polls all target wallets for new trades and dispatches
copy-trade signals through the validation -> calculation -> execution
pipeline.
"""
import asyncio
import logging
from collections import defaultdict

from bot.config import WALLET_POLL_INTERVAL
from bot.engine.monitor import WalletMonitor
from bot.engine.validator import PreTradeValidator, record_spend
from bot.engine.calculator import calculate_buy_size, calculate_sell_size
from bot.engine.circuit_breaker import circuit_breaker
from shared.supabase import _supabase_rest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database helpers (thin wrappers around Supabase REST)
# ---------------------------------------------------------------------------

def _get_all_active_configs() -> list[dict]:
    """Fetch all active copy-trade configurations from Supabase."""
    rows = _supabase_rest(
        'copy_trade_configs',
        method='GET',
        match={'is_active': 'true'},
    )
    return rows if isinstance(rows, list) else []


def _get_user_credentials_status(telegram_user_id: int) -> bool:
    """Check whether the user's trading credentials are active."""
    rows = _supabase_rest(
        'user_trading_credentials',
        method='GET',
        match={'telegram_user_id': str(telegram_user_id), 'is_active': 'true'},
        select='id',
    )
    return bool(rows)


def _update_total_spent(config_id: str, additional: float) -> None:
    """Increment the ``total_spent_usd`` field on a config row."""
    # Read current value first
    rows = _supabase_rest(
        'copy_trade_configs',
        method='GET',
        match={'id': config_id},
        select='total_spent_usd',
    )
    current = 0.0
    if rows and isinstance(rows, list) and rows[0]:
        current = float(rows[0].get('total_spent_usd', 0))

    _supabase_rest(
        'copy_trade_configs',
        method='PATCH',
        data={'total_spent_usd': current + additional},
        match={'id': config_id},
    )


def _log_trade(
    telegram_user_id: int,
    action: str,
    market_slug: str = '',
    signal_source: str = '',
    signal_price: float = 0.0,
    execution_price: float = 0.0,
    slippage_pct: float = 0.0,
    order_size_usd: float = 0.0,
    outcome: str = '',
    polymarket_order_id: str = '',
    failure_reason: str = '',
    config_id: str = '',
) -> None:
    """Insert a row into the ``trade_log`` audit table."""
    data = {
        'telegram_user_id': telegram_user_id,
        'action': action,
        'market_slug': market_slug,
        'signal_source': signal_source,
        'signal_price': signal_price,
        'execution_price': execution_price,
        'slippage_pct': slippage_pct,
        'order_size_usd': order_size_usd,
        'outcome': outcome,
        'polymarket_order_id': polymarket_order_id,
        'failure_reason': failure_reason,
    }
    if config_id:
        data['config_id'] = config_id
    _supabase_rest('trade_log', method='POST', data=data)


def _get_user_language(telegram_user_id: int) -> str:
    """Fetch the user's preferred language from DB, default to 'en'."""
    rows = _supabase_rest(
        'telegram_users',
        method='GET',
        match={'telegram_user_id': str(telegram_user_id)},
        select='language',
    )
    if rows and isinstance(rows, list) and rows[0]:
        return rows[0].get('language') or 'en'
    return 'en'


# ---------------------------------------------------------------------------
# WalletPollerTask
# ---------------------------------------------------------------------------

class WalletPollerTask:
    """Runs continuously, polling all target wallets for new trades.

    Lifecycle
    ---------
    1. Fetch all active ``copy_trade_configs`` from Supabase.
    2. Group configs by ``target_wallet`` (to avoid redundant Etherscan
       calls when multiple users track the same wallet).
    3. For each wallet, call ``WalletMonitor.check_wallet()`` to detect
       new transactions.
    4. For each signal, iterate over all configs tracking that wallet
       and run the validate -> calculate -> execute pipeline.
    5. Sleep for ``WALLET_POLL_INTERVAL`` seconds and repeat.
    """

    def __init__(self, executor, telegram_app=None) -> None:
        """
        Args:
            executor:     A :class:`TradeExecutor` for order placement.
            telegram_app: The ``telegram.ext.Application`` for sending
                          notifications to users.
        """
        self._monitor = WalletMonitor()
        self._validator = PreTradeValidator(executor=executor)
        self._executor = executor
        self._app = telegram_app

    async def run(self) -> None:
        """Main loop -- runs forever until cancelled."""
        logger.info('[POLLER] Wallet poller task started (interval=%ds)',
                    WALLET_POLL_INTERVAL)
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                logger.info('[POLLER] Wallet poller task cancelled')
                raise
            except Exception:
                logger.exception('[POLLER] Unexpected error in poller tick')
                circuit_breaker.record_api_error()
            await asyncio.sleep(WALLET_POLL_INTERVAL)

    async def _tick(self) -> None:
        """Single poll iteration."""
        active_configs = _get_all_active_configs()
        if not active_configs:
            return

        wallets = self._group_by_wallet(active_configs)

        for target_wallet, configs in wallets.items():
            try:
                signals = await self._monitor.check_wallet(target_wallet)
            except Exception:
                logger.exception('[POLLER] Error polling wallet %s',
                                 target_wallet[:12])
                circuit_breaker.record_api_error()
                continue

            circuit_breaker.record_api_success()

            for signal in signals:
                for config in configs:
                    try:
                        await self._process_signal(config, signal)
                    except Exception:
                        logger.exception(
                            '[POLLER] Error processing signal tx=%s '
                            'config=%s',
                            signal.tx_hash[:12],
                            config.get('id', '?')[:8],
                        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_wallet(configs: list[dict]) -> dict[str, list[dict]]:
        """Group configs by lowercase ``target_wallet``."""
        groups: dict[str, list[dict]] = defaultdict(list)
        for cfg in configs:
            wallet = (cfg.get('target_wallet') or '').lower()
            if wallet:
                groups[wallet].append(cfg)
        return dict(groups)

    async def _process_signal(self, config: dict, signal) -> None:
        """Validate -> Calculate -> Execute -> Notify for one config+signal pair."""
        from bot.notifications import format_trade_executed, format_trade_skipped

        telegram_user_id = int(config.get('telegram_user_id', 0))
        config_id = config.get('id', '')
        lang = _get_user_language(telegram_user_id)

        # Enrich config with credentials-active flag
        config['credentials_active'] = _get_user_credentials_status(telegram_user_id)

        # Log signal received
        _log_trade(
            telegram_user_id=telegram_user_id,
            action='signal_received',
            market_slug=signal.market_slug,
            signal_source=signal.target_wallet,
            signal_price=signal.price,
            order_size_usd=signal.value_usd,
            outcome=signal.side,
            config_id=config_id,
        )

        # --- Validation ---
        should_execute, amount, reason = await self._validator.validate(
            config=config,
            signal=signal,
            executor=self._executor,
            telegram_user_id=telegram_user_id,
        )

        if not should_execute:
            _log_trade(
                telegram_user_id=telegram_user_id,
                action='validation_failed',
                market_slug=signal.market_slug,
                signal_source=signal.target_wallet,
                signal_price=signal.price,
                failure_reason=reason,
                config_id=config_id,
            )
            text = format_trade_skipped(
                signal={'market_name': signal.market_slug, 'side': signal.side, 'outcome': signal.side},
                reason=reason,
                config=config,
                lang=lang,
            )
            await self._notify_user(telegram_user_id, text)
            return

        # --- Execution ---
        result = await self._executor.place_order(
            telegram_user_id=telegram_user_id,
            signal=signal,
            trade_size_usd=amount,
            config=config,
        )

        if result.success:
            # Compute slippage
            slippage = 0.0
            if signal.price > 0 and result.fill_price > 0:
                slippage = abs(result.fill_price - signal.price) / signal.price * 100

            _log_trade(
                telegram_user_id=telegram_user_id,
                action='order_filled',
                market_slug=signal.market_slug,
                signal_source=signal.target_wallet,
                signal_price=signal.price,
                execution_price=result.fill_price,
                slippage_pct=round(slippage, 2),
                order_size_usd=amount,
                outcome=signal.side,
                polymarket_order_id=result.order_id,
                config_id=config_id,
            )

            # Update spend tracking
            _update_total_spent(config_id, amount)
            record_spend(config_id, signal.market_slug, signal.side, amount)

            circuit_breaker.record_api_success()

            text = format_trade_executed(
                signal={
                    'market_name': signal.market_slug,
                    'side': signal.side,
                    'outcome': signal.side,
                    'signal_price': signal.price,
                    'signal_source': signal.target_wallet,
                    'value': signal.value_usd,
                },
                result={
                    'execution_price': result.fill_price,
                    'slippage_pct': round(slippage, 2),
                    'order_id': result.order_id,
                    'filled_amount_usd': amount,
                },
                config=config,
                lang=lang,
            )
            await self._notify_user(telegram_user_id, text)
        else:
            _log_trade(
                telegram_user_id=telegram_user_id,
                action='order_rejected',
                market_slug=signal.market_slug,
                signal_source=signal.target_wallet,
                signal_price=signal.price,
                order_size_usd=amount,
                outcome=signal.side,
                failure_reason=result.error,
                config_id=config_id,
            )
            circuit_breaker.record_api_error()

            text = format_trade_skipped(
                signal={'market_name': signal.market_slug, 'side': signal.side, 'outcome': signal.side},
                reason=f"Order rejected: {result.error}",
                config=config,
                lang=lang,
            )
            await self._notify_user(telegram_user_id, text)

    async def _notify_user(self, telegram_user_id: int, text: str) -> None:
        """Send a Telegram notification to the user (HTML formatted)."""
        if not self._app or telegram_user_id <= 0:
            return
        try:
            await self._app.bot.send_message(
                chat_id=telegram_user_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception:
            logger.exception('[POLLER] Failed to notify user %d',
                             telegram_user_id)
