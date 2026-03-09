"""
PolyHunter Telegram Bot — Notification formatting utilities.

Every function returns a ready-to-send HTML-formatted string for Telegram.
These are used by the trade engine, TP/SL monitor, and command handlers
to build consistent user-facing messages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bot.i18n import t


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wallet_short(address: Optional[str]) -> str:
    if not address:
        return "-"
    return f"{address[:6]}...{address[-4:]}"


def _ts_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def _progress_bar(used: float, limit: float, width: int = 10) -> str:
    """Render a Unicode progress bar: ▰▰▰▰▰▱▱▱▱▱"""
    if limit <= 0:
        return ""
    ratio = min(used / limit, 1.0)
    filled = round(ratio * width)
    return "▰" * filled + "▱" * (width - filled)


# ---------------------------------------------------------------------------
# Trade Executed
# ---------------------------------------------------------------------------

def format_trade_executed(
    signal: dict,
    result: dict,
    config: dict,
    lang: str = "en",
) -> str:
    """
    Build the "TRADE EXECUTED" notification.

    Parameters
    ----------
    signal : dict
        Keys: market_name, side, outcome, signal_price, signal_source, value
    result : dict
        Keys: execution_price, slippage_pct, order_id, filled_amount_usd
    config : dict
        Keys: tag, target_wallet, daily_spent_usd, max_daily_exposure_usd
              (or equivalent fields from copy_trade_configs)
    """
    market = signal.get("market_name") or signal.get("market_slug") or "Unknown Market"
    side = signal.get("side", "BUY").upper()
    outcome = signal.get("outcome", "YES").upper()
    signal_price = _safe_float(signal.get("signal_price"))
    signal_source = signal.get("signal_source") or config.get("target_wallet")
    signal_value = _safe_float(signal.get("value"))

    exec_price = _safe_float(result.get("execution_price"))
    slippage = _safe_float(result.get("slippage_pct"))
    filled_usd = _safe_float(result.get("filled_amount_usd"))
    order_id = result.get("order_id") or "-"

    tag = config.get("tag") or _wallet_short(config.get("target_wallet"))
    daily_spent = _safe_float(config.get("daily_spent_usd") or config.get("total_spent_usd"))
    daily_limit = _safe_float(
        config.get("max_daily_exposure_usd") or config.get("total_spend_limit_usd")
    )

    daily_line = ""
    if daily_limit > 0:
        bar = _progress_bar(daily_spent, daily_limit)
        daily_line = (
            f"\n{DIVIDER}\n"
            f"💰 Spend: ${daily_spent:.2f} / ${daily_limit:.2f}  {bar}"
        )

    source_display = _wallet_short(signal_source) if signal_source else "-"

    return t(
        "notif.trade_executed", lang,
        market=market,
        side=side,
        outcome=outcome,
        amount=f"{filled_usd:.2f}",
        price=f"{exec_price:.4f}",
        source=source_display,
        signal_side=side.lower(),
        signal_value=f"{signal_value:,.2f}",
        signal_outcome=outcome,
        slippage=f"{slippage:.2f}",
        order_id=order_id,
        daily_line=daily_line,
        tag=tag,
    )


# ---------------------------------------------------------------------------
# Trade Skipped
# ---------------------------------------------------------------------------

def format_trade_skipped(
    signal: dict,
    reason: str,
    config: dict,
    lang: str = "en",
) -> str:
    """
    Build the "TRADE SKIPPED" notification.

    Parameters
    ----------
    signal : dict
        Keys: market_name, side, outcome
    reason : str
        Human-readable explanation of why the trade was skipped.
    config : dict
        Keys: tag, target_wallet
    """
    market = signal.get("market_name") or signal.get("market_slug") or "Unknown Market"
    tag = config.get("tag") or _wallet_short(config.get("target_wallet"))

    return t(
        "notif.trade_skipped", lang,
        market=market,
        reason=reason,
        tag=tag,
    )


# ---------------------------------------------------------------------------
# TP / SL Triggered
# ---------------------------------------------------------------------------

def format_tp_sl_triggered(
    position: dict,
    trigger_type: str,
    price: float,
    result: dict,
    lang: str = "en",
) -> str:
    """
    Build the "TAKE PROFIT / STOP LOSS TRIGGERED" notification.

    Parameters
    ----------
    position : dict
        Keys: market_name, side, size, avg_price
    trigger_type : str
        "TP" or "SL"
    price : float
        The price at which the trigger fired.
    result : dict
        Keys: execution_price, filled_amount_usd, order_id, pnl, pnl_pct
    """
    market = position.get("market_name") or "Unknown Market"
    side = position.get("side", "?").upper()
    shares = _safe_float(position.get("size") or position.get("shares"))
    avg_price = _safe_float(position.get("avg_price"))

    exec_price = _safe_float(result.get("execution_price"))
    filled_usd = _safe_float(result.get("filled_amount_usd"))
    order_id = result.get("order_id") or "-"
    pnl = _safe_float(result.get("pnl"))
    pnl_pct = _safe_float(result.get("pnl_pct"))

    pnl_sign = "+" if pnl >= 0 else ""
    key = "notif.tp_triggered" if trigger_type == "TP" else "notif.sl_triggered"

    return t(
        key, lang,
        market=market,
        side=side,
        shares=f"{shares:,.0f}",
        entry_price=f"{avg_price:.4f}",
        trigger_price=f"{price:.4f}",
        exec_price=f"{exec_price:.4f}",
        closed_amount=f"{filled_usd:.2f}",
        pnl_sign=pnl_sign,
        pnl=f"{abs(pnl):.2f}",
        pnl_pct=f"{abs(pnl_pct):.1f}",
        order_id=order_id,
    )


# ---------------------------------------------------------------------------
# Position Summary
# ---------------------------------------------------------------------------

def format_position_summary(positions: list[dict], lang: str = "en") -> str:
    """
    Build a compact summary of all open positions.

    Parameters
    ----------
    positions : list[dict]
        Each dict has keys: market_name, side, size, avg_price, cur_price,
        pnl, pnl_pct
    """
    if not positions:
        return t("notif.no_positions", lang)

    total_pnl = 0.0
    lines = []

    for idx, pos in enumerate(positions, start=1):
        market = pos.get("market_name") or "Unknown"
        side = pos.get("side", "?").upper()
        shares = _safe_float(pos.get("size") or pos.get("shares"))
        avg_price = _safe_float(pos.get("avg_price"))
        cur_price = _safe_float(pos.get("cur_price") or pos.get("current_price"))
        pnl = _safe_float(pos.get("pnl"))
        pnl_pct = _safe_float(pos.get("pnl_pct"))

        total_pnl += pnl
        pnl_sign = "+" if pnl >= 0 else ""
        indicator = "🟢" if pnl >= 0 else "🔴"

        lines.append(
            f"{indicator} <b>{market}</b>\n"
            f"   {side} | {shares:,.0f} shares | "
            f"Avg ${avg_price:.2f} | Cur ${cur_price:.2f}\n"
            f"   P&L: {pnl_sign}${abs(pnl):.2f} "
            f"({pnl_sign}{abs(pnl_pct):.1f}%)"
        )

    total_sign = "+" if total_pnl >= 0 else ""
    total_indicator = "🟢" if total_pnl >= 0 else "🔴"

    header = t("notif.positions_summary", lang, count=len(positions)) + "\n" + DIVIDER
    footer = (
        f"\n{DIVIDER}\n"
        f"{total_indicator} <b>Total P&L: {total_sign}${abs(total_pnl):.2f}</b>"
    )

    return header + "\n\n" + "\n\n".join(lines) + footer


# ---------------------------------------------------------------------------
# Welcome Message
# ---------------------------------------------------------------------------

def format_welcome_message(
    user,
    balance: Optional[float] = None,
    lang: str = "en",
) -> str:
    """
    Build the welcome message shown on /start.

    Parameters
    ----------
    user : telegram.User
        The Telegram user object.
    balance : float or None
        USDC balance from the CLOB API, or None if not connected.
    lang : str
        Language code for translation lookup.
    """
    name = user.first_name or user.username or "Trader"

    if balance is not None:
        balance_line = t("welcome.balance_connected", lang, balance=f"{balance:.2f}")
    else:
        balance_line = t("welcome.balance_not_connected", lang)

    return (
        t("welcome.title", lang, name=name) + "\n"
        + DIVIDER + "\n\n"
        + t("welcome.description", lang) + "\n\n"
        + balance_line + "\n\n"
        + DIVIDER + "\n"
        + t("welcome.commands_header", lang)
    )
