"""
PolyHunter Engine -- Trade Size Calculator
Determines the correct dollar amount (buy) or share count (sell) for copy
trades based on the user's configuration and the original signal.
"""
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(config, key: str, default=None):
    """Read a field from *config* which may be a dict or an object."""
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _float_or(config, key: str, default: float = 0.0) -> float:
    """Read a numeric field from *config*, coercing to float safely."""
    val = _cfg(config, key)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Buy Size Calculation
# ---------------------------------------------------------------------------

def calculate_buy_size(config, signal) -> float:
    """Compute the USD amount for a copy-buy order.

    Modes
    -----
    * **percentage** (default): ``signal.value_usd * config.copy_percentage / 100``
    * **fixed**: ``config.copy_fixed_amount``

    Additional constraints applied in order:

    1. ``min_per_trade_usd`` / ``max_per_trade_usd`` -- clamp to per-trade
       bounds.
    2. ``below_min_buy_at_min`` -- if the calculated amount is below the
       minimum per-trade threshold, bump it up to the minimum instead of
       rejecting.
    3. ``total_spend_limit_usd`` -- ensure adding this trade does not
       exceed the lifetime spend cap.

    Returns:
        The trade amount in USD.  Returns ``0.0`` if the trade should be
        skipped entirely.
    """
    copy_mode = _cfg(config, 'copy_mode', 'percentage')

    if copy_mode == 'fixed':
        amount = _float_or(config, 'copy_fixed_amount', 0.0)
    else:
        # Percentage mode
        copy_pct = _float_or(config, 'copy_percentage', 100.0)
        signal_value = signal.value_usd if hasattr(signal, 'value_usd') else 0.0
        amount = signal_value * copy_pct / 100.0

    if amount <= 0:
        logger.debug('[CALC] Calculated buy amount is zero or negative')
        return 0.0

    # Per-trade bounds
    min_per_trade = _float_or(config, 'min_per_trade_usd', 0.0)
    max_per_trade = _float_or(config, 'max_per_trade_usd', 0.0)

    below_min_buy_at_min = _cfg(config, 'below_min_buy_at_min', True)

    if min_per_trade > 0 and amount < min_per_trade:
        if below_min_buy_at_min:
            logger.debug(
                '[CALC] Amount $%.2f below min $%.2f — bumping to min',
                amount, min_per_trade,
            )
            amount = min_per_trade
        else:
            logger.debug(
                '[CALC] Amount $%.2f below min $%.2f — skipping trade',
                amount, min_per_trade,
            )
            return 0.0

    if max_per_trade > 0 and amount > max_per_trade:
        logger.debug(
            '[CALC] Amount $%.2f exceeds max $%.2f — clamping',
            amount, max_per_trade,
        )
        amount = max_per_trade

    # Total spend limit
    total_limit = _float_or(config, 'total_spend_limit_usd', 0.0)
    total_spent = _float_or(config, 'total_spent_usd', 0.0)
    if total_limit > 0:
        remaining = total_limit - total_spent
        if remaining <= 0:
            logger.debug('[CALC] Total spend limit reached ($%.2f / $%.2f)',
                         total_spent, total_limit)
            return 0.0
        if amount > remaining:
            logger.debug(
                '[CALC] Clamping buy to remaining budget $%.2f (limit $%.2f, spent $%.2f)',
                remaining, total_limit, total_spent,
            )
            amount = remaining

    return round(amount, 2)


# ---------------------------------------------------------------------------
# Sell Size Calculation
# ---------------------------------------------------------------------------

def calculate_sell_size(
    config,
    signal,
    user_position_shares: float,
    target_position_shares: float,
) -> float:
    """Compute the number of shares to sell for a copy-sell order.

    Uses proportional sizing so the user exits at the same rate as the
    target wallet::

        sell_shares = signal.value_usd * (user_position / target_position)

    Here ``signal.value_usd`` is interpreted as the *share count* that the
    target sold (the monitor reports the USDC value but for sells the
    relevant metric is the proportional exit).

    If the target position is unknown (``<= 0``), the user sells their
    entire position.

    Returns:
        Number of shares to sell.  ``0.0`` if there is nothing to sell.
    """
    if user_position_shares <= 0:
        logger.debug('[CALC] User has no position — nothing to sell')
        return 0.0

    if target_position_shares <= 0:
        # Cannot compute proportion — sell the full user position
        logger.debug('[CALC] Target position unknown — selling full user position')
        return round(user_position_shares, 2)

    # signal.value_usd for a sell represents the USD value of the shares
    # the target sold.  We use the ratio of positions.
    signal_value = signal.value_usd if hasattr(signal, 'value_usd') else 0.0
    if signal_value <= 0:
        return 0.0

    ratio = user_position_shares / target_position_shares
    sell_shares = signal_value * ratio

    # Never sell more than the user owns
    sell_shares = min(sell_shares, user_position_shares)

    return round(sell_shares, 2)
