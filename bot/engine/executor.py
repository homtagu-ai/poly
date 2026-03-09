"""
PolyHunter Engine -- Trade Executor
Places orders on Polymarket via the CLOB API using py_clob_client.
"""
import logging
from dataclasses import dataclass
from enum import Enum

from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data classes
# ---------------------------------------------------------------------------

class OrderStyle(str, Enum):
    MARKET = 'market'
    LIMIT = 'limit'


@dataclass
class ExecutionResult:
    """Outcome of a trade execution attempt."""
    success: bool
    order_id: str = ''
    fill_price: float = 0.0
    shares: float = 0.0
    error: str = ''


# ---------------------------------------------------------------------------
# TradeExecutor
# ---------------------------------------------------------------------------

class TradeExecutor:
    """Executes trades on Polymarket via the CLOB API.

    Requires a :class:`bot.clob_client.PolymarketClient` instance to
    obtain authenticated ``ClobClient`` objects per user.
    """

    def __init__(self, poly_client) -> None:
        """
        Args:
            poly_client: A ``PolymarketClient`` instance (from
                ``bot.clob_client``) that provides ``get_client()``.
        """
        self._poly_client = poly_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def place_order(
        self,
        telegram_user_id: int,
        signal,
        trade_size_usd: float,
        config,
    ) -> ExecutionResult:
        """Place a copy-trade order for *telegram_user_id*.

        Args:
            telegram_user_id: Telegram user ID (maps to stored credentials).
            signal:           A :class:`TradeSignal` with ``side``,
                              ``token_id``, and ``price``.
            trade_size_usd:   Dollar amount to trade.
            config:           The user's ``copy_trade_configs`` row (dict or
                              object) with order-type and slippage fields.

        Returns:
            An :class:`ExecutionResult` describing the outcome.
        """
        try:
            client = await self._poly_client.get_client(telegram_user_id)
            if client is None:
                return ExecutionResult(
                    success=False,
                    error='No CLOB client — credentials may be missing or revoked',
                )

            token_id = signal.token_id
            if not token_id:
                return ExecutionResult(
                    success=False,
                    error='Signal has no token_id — cannot place order',
                )

            side_str = signal.side.upper()
            is_buy = side_str == 'BUY'

            # Determine order style from config
            order_style_field = 'buy_order_type' if is_buy else 'sell_order_type'
            order_style = _cfg(config, order_style_field, 'market')

            slippage_field = 'buy_slippage_pct' if is_buy else 'sell_slippage_pct'
            slippage_pct = float(_cfg(config, slippage_field, 5.0))

            # Fetch current mid price from orderbook
            current_price = await self.get_current_price(telegram_user_id, token_id)
            if current_price is None or current_price <= 0:
                return ExecutionResult(
                    success=False,
                    error='Could not fetch current price from orderbook',
                )

            # Calculate limit price and order type
            if order_style == OrderStyle.LIMIT or order_style == 'limit':
                # Limit order: use the signal price (or current price)
                limit_price = signal.price if signal.price > 0 else current_price

                # Apply limit price offset from config
                offset = float(_cfg(config, 'limit_price_offset', 0.0))
                if offset != 0.0:
                    limit_price = limit_price + offset
                    logger.info(
                        '[EXECUTOR] Applied limit_price_offset=%.4f -> adjusted price=%.4f user=%d',
                        offset, limit_price, telegram_user_id,
                    )

                # Determine order type: GTD with expiration if duration is set, otherwise GTC
                duration = int(_cfg(config, 'limit_order_duration', 0) or 0)
                if duration >= 90:
                    import time
                    order_type = OrderType.GTD
                    expiration = int(time.time()) + duration
                    logger.info(
                        '[EXECUTOR] Using GTD order with expiration=%d (duration=%ds) user=%d',
                        expiration, duration, telegram_user_id,
                    )
                else:
                    order_type = OrderType.GTC
                    expiration = None
            else:
                # Market order: FOK with slippage-adjusted limit price
                if is_buy:
                    limit_price = current_price * (1 + slippage_pct / 100)
                else:
                    limit_price = current_price * (1 - slippage_pct / 100)
                order_type = OrderType.FOK
                expiration = None

            # Clamp limit price to valid range [0.01, 0.99]
            limit_price = max(0.01, min(0.99, round(limit_price, 2)))

            # Calculate share count: size_usd / price
            if limit_price <= 0:
                return ExecutionResult(success=False, error='Invalid limit price')
            shares = trade_size_usd / limit_price

            side = BUY if is_buy else SELL

            logger.info(
                '[EXECUTOR] Placing %s %s order: token=%s price=%.2f '
                'size=$%.2f shares=%.2f slippage=%.1f%% user=%d',
                order_style, side_str, token_id[:16], limit_price,
                trade_size_usd, shares, slippage_pct, telegram_user_id,
            )

            # Build and sign the order via py_clob_client
            order_args = OrderArgs(
                price=limit_price,
                size=round(shares, 2),
                side=side,
                token_id=token_id,
            )
            signed_order = client.create_order(order_args)
            resp = client.post_order(signed_order, order_type)

            # Parse response
            if resp and resp.get('success'):
                order_id = resp.get('orderID', resp.get('order_id', ''))
                fill_price = float(resp.get('averagePrice', limit_price))
                filled_size = float(resp.get('filledSize', shares))

                logger.info(
                    '[EXECUTOR] Order placed: id=%s fill=%.2f shares=%.2f user=%d',
                    order_id, fill_price, filled_size, telegram_user_id,
                )
                return ExecutionResult(
                    success=True,
                    order_id=order_id,
                    fill_price=fill_price,
                    shares=filled_size,
                )
            else:
                error_msg = ''
                if isinstance(resp, dict):
                    error_msg = resp.get('errorMsg', resp.get('error', str(resp)))
                else:
                    error_msg = str(resp)
                logger.warning('[EXECUTOR] Order rejected: %s user=%d',
                               error_msg, telegram_user_id)
                return ExecutionResult(success=False, error=error_msg)

        except Exception as exc:
            logger.exception('[EXECUTOR] Error placing order for user %d',
                             telegram_user_id)
            return ExecutionResult(success=False, error=str(exc))

    async def get_current_price(
        self,
        telegram_user_id: int,
        token_id: str,
    ) -> float | None:
        """Fetch the mid price for *token_id* from the CLOB orderbook.

        Returns:
            The mid price as a float, or ``None`` on failure.
        """
        try:
            client = await self._poly_client.get_client(telegram_user_id)
            if client is None:
                return None

            book = client.get_order_book(token_id)
            if book is None:
                return None

            bids = book.bids or []
            asks = book.asks or []

            best_bid = float(bids[0].price) if bids else 0.0
            best_ask = float(asks[0].price) if asks else 0.0

            if best_bid > 0 and best_ask > 0:
                return (best_bid + best_ask) / 2.0
            elif best_bid > 0:
                return best_bid
            elif best_ask > 0:
                return best_ask
            return None

        except Exception:
            logger.exception('[EXECUTOR] Error fetching price for token %s',
                             token_id[:16] if token_id else '?')
            return None

    async def get_balance(self, telegram_user_id: int) -> float | None:
        """Fetch the USDC balance for *telegram_user_id* via the CLOB API.

        Returns:
            Balance in USD as a float, or ``None`` on failure.
        """
        try:
            client = await self._poly_client.get_client(telegram_user_id)
            if client is None:
                return None
            balance_resp = client.get_balance_allowance()
            if balance_resp and hasattr(balance_resp, 'balance'):
                return float(balance_resp.balance) / 1e6  # USDC has 6 decimals
            if isinstance(balance_resp, dict):
                raw = balance_resp.get('balance', 0)
                return float(raw) / 1e6
            return None
        except Exception:
            logger.exception('[EXECUTOR] Error fetching balance for user %d',
                             telegram_user_id)
            return None

    async def get_positions(self, telegram_user_id: int) -> list[dict]:
        """Fetch open positions for *telegram_user_id* via the CLOB API.

        Returns:
            List of position dicts, or an empty list on failure.
        """
        try:
            client = await self._poly_client.get_client(telegram_user_id)
            if client is None:
                return []
            positions = client.get_positions()
            if positions is None:
                return []
            # Normalise into plain dicts if needed
            result = []
            for pos in positions:
                if isinstance(pos, dict):
                    result.append(pos)
                else:
                    result.append({
                        'token_id': getattr(pos, 'token_id', ''),
                        'size': float(getattr(pos, 'size', 0)),
                        'avg_price': float(getattr(pos, 'avgPrice', 0)),
                        'cur_price': float(getattr(pos, 'curPrice', 0)),
                        'side': getattr(pos, 'side', ''),
                        'pnl': float(getattr(pos, 'pnl', 0)),
                    })
            return result
        except Exception:
            logger.exception('[EXECUTOR] Error fetching positions for user %d',
                             telegram_user_id)
            return []

    async def get_orderbook_liquidity(
        self,
        telegram_user_id: int,
        token_id: str,
        depth_pct: float = 5.0,
    ) -> float:
        """Estimate total liquidity within *depth_pct*% of mid price.

        Used by the validator to check minimum liquidity requirements.

        Returns:
            Total USD liquidity within the depth band, or ``0.0`` on error.
        """
        try:
            client = await self._poly_client.get_client(telegram_user_id)
            if client is None:
                return 0.0

            book = client.get_order_book(token_id)
            if book is None:
                return 0.0

            bids = book.bids or []
            asks = book.asks or []

            best_bid = float(bids[0].price) if bids else 0.0
            best_ask = float(asks[0].price) if asks else 0.0
            mid = (best_bid + best_ask) / 2.0 if (best_bid and best_ask) else 0.0
            if mid <= 0:
                return 0.0

            lower = mid * (1 - depth_pct / 100)
            upper = mid * (1 + depth_pct / 100)
            total = 0.0

            for level in bids:
                price = float(level.price)
                size = float(level.size)
                if price >= lower:
                    total += price * size

            for level in asks:
                price = float(level.price)
                size = float(level.size)
                if price <= upper:
                    total += price * size

            return total

        except Exception:
            logger.exception('[EXECUTOR] Error fetching liquidity for token %s',
                             token_id[:16] if token_id else '?')
            return 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(config, key: str, default=None):
    """Read a field from *config* which may be a dict or an object."""
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)
