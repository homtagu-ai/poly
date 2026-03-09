"""
PolyHunter Telegram Bot — /positions handler.

Fetches the user's open positions from the database (which mirrors CLOB API
data) and formats them as a readable Telegram message with market name,
side, entry price, and current P&L.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.i18n import t, get_user_lang

logger = logging.getLogger(__name__)


def _get_db():
    from bot import db
    return db


def _pnl_emoji(pnl: float) -> str:
    if pnl > 0:
        return "+"
    elif pnl < 0:
        return ""  # minus sign already in the number
    return ""


def _format_position(idx: int, pos: dict) -> str:
    """Format a single position for display."""
    market = pos.get("market_name") or pos.get("market_slug") or "Unknown Market"
    side = pos.get("side", "?").upper()
    shares = pos.get("size") or pos.get("shares", 0)
    avg_price = pos.get("avg_price", 0)
    cur_price = pos.get("cur_price") or pos.get("current_price", 0)
    pnl = pos.get("pnl", 0)
    pnl_pct = pos.get("pnl_pct", 0)

    try:
        shares = float(shares)
        avg_price = float(avg_price)
        cur_price = float(cur_price)
        pnl = float(pnl)
        pnl_pct = float(pnl_pct)
    except (ValueError, TypeError):
        shares = avg_price = cur_price = pnl = pnl_pct = 0

    pnl_sign = _pnl_emoji(pnl)
    pnl_indicator = "🟢" if pnl >= 0 else "🔴"

    return (
        f"{pnl_indicator} <b>{idx}. {market}</b>\n"
        f"   Side: {side} | Shares: {shares:,.0f} | Avg: ${avg_price:.2f}\n"
        f"   Current: ${cur_price:.2f} | "
        f"P&L: {pnl_sign}${abs(pnl):.2f} ({pnl_sign}{abs(pnl_pct):.1f}%)"
    )


async def positions_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    /positions — Show the user's open positions and P&L.
    """
    lang = await get_user_lang(update, context)
    db = _get_db()
    telegram_id = update.effective_user.id

    try:
        positions = await db.get_open_positions(telegram_id=telegram_id)
    except Exception:
        logger.exception("Failed to fetch positions for user %s", telegram_id)
        await update.message.reply_text(t("positions.error", lang))
        return

    if not positions:
        await update.message.reply_text(t("positions.empty", lang))
        return

    # Calculate totals
    total_pnl = 0.0
    lines = []
    for idx, pos in enumerate(positions, start=1):
        lines.append(_format_position(idx, pos))
        try:
            total_pnl += float(pos.get("pnl", 0))
        except (ValueError, TypeError):
            pass

    total_sign = _pnl_emoji(total_pnl)
    total_indicator = "🟢" if total_pnl >= 0 else "🔴"

    header = t("positions.header", lang, count=len(positions)) + "\n"
    footer = (
        "\n" + t("positions.total_pnl", lang, sign=total_sign, value=f"{abs(total_pnl):.2f}", indicator=total_indicator)
    )

    text = header + "\n" + "\n\n".join(lines) + footer

    # Telegram messages have a 4096-char limit; split if necessary
    if len(text) <= 4096:
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        # Send in chunks
        chunks = _split_message(text, 4096)
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="HTML")


def _split_message(text: str, max_len: int) -> list[str]:
    """Split a long message at double-newline boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = (current + "\n\n" + paragraph) if current else paragraph
        if len(candidate) > max_len:
            if current:
                chunks.append(current)
            current = paragraph
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks
