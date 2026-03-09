"""
PolyHunter Telegram Bot — /history handler.

Fetches the user's trade log from the database and formats the most
recent 20 entries for display in Telegram.
"""

import logging
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes

from bot.i18n import t, get_user_lang

logger = logging.getLogger(__name__)

MAX_ENTRIES = 20


def _get_db():
    from bot import db
    return db


def _format_timestamp(ts) -> str:
    """Format a timestamp for display.  Accepts str, datetime, or None."""
    if ts is None:
        return "?"
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return ts[:19]  # best-effort truncation
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(ts)


def _action_emoji(action: str) -> str:
    """Return a visual emoji indicator for the log action type."""
    mapping = {
        "order_filled": "✅",
        "order_placed": "📤",
        "order_rejected": "❌",
        "order_cancelled": "🚫",
        "validation_failed": "⏭️",
        "validation_passed": "✔️",
        "signal_received": "📡",
        "tp_executed": "🎯",
        "sl_executed": "🛑",
        "tp_failed": "🎯❌",
        "sl_failed": "🛑❌",
        "circuit_breaker_tripped": "⚡",
    }
    return mapping.get(action, f"[{action.upper()}]")


def _format_entry(idx: int, entry: dict) -> str:
    """Format a single trade-log entry."""
    action = entry.get("action", "unknown")
    market = entry.get("market_slug") or "Unknown"
    signal_source = entry.get("signal_source") or "-"
    outcome = entry.get("outcome") or "-"
    order_size = entry.get("order_size_usd")
    signal_price = entry.get("signal_price")
    exec_price = entry.get("execution_price")
    slippage = entry.get("slippage_pct")
    failure = entry.get("failure_reason")
    ts = _format_timestamp(entry.get("created_at"))

    lines = [f"<b>{idx}. {_action_emoji(action)}</b> {market}"]
    lines.append(f"   Time: {ts}")

    if outcome and outcome != "-":
        lines.append(f"   Side: {outcome}")

    if order_size is not None:
        try:
            lines.append(f"   Amount: ${float(order_size):.2f}")
        except (ValueError, TypeError):
            lines.append(f"   Amount: {order_size}")

    if signal_price is not None:
        try:
            lines.append(f"   Signal Price: ${float(signal_price):.4f}")
        except (ValueError, TypeError):
            pass

    if exec_price is not None:
        try:
            lines.append(f"   Exec Price: ${float(exec_price):.4f}")
        except (ValueError, TypeError):
            pass

    if slippage is not None:
        try:
            lines.append(f"   Slippage: {float(slippage):.2f}%")
        except (ValueError, TypeError):
            pass

    if signal_source and signal_source != "-":
        # Truncate wallet address for display
        if len(signal_source) > 12:
            signal_source = f"{signal_source[:6]}...{signal_source[-4:]}"
        lines.append(f"   Source: {signal_source}")

    if failure:
        lines.append(f"   Reason: {failure}")

    return "\n".join(lines)


async def history_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    /history — Show the last 20 trade-log entries.
    """
    lang = await get_user_lang(update, context)
    db = _get_db()
    telegram_id = update.effective_user.id

    try:
        entries = await db.get_trade_history(
            telegram_id=telegram_id,
            limit=MAX_ENTRIES,
        )
    except Exception:
        logger.exception("Failed to fetch trade history for user %s", telegram_id)
        await update.message.reply_text(t("history.error", lang))
        return

    if not entries:
        await update.message.reply_text(t("history.empty", lang))
        return

    header = t("history.header", lang, count=len(entries)) + "\n"

    lines = []
    for idx, entry in enumerate(entries, start=1):
        lines.append(_format_entry(idx, entry))

    text = header + "\n" + "\n\n".join(lines)

    # Handle Telegram 4096-char message limit
    if len(text) <= 4096:
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        chunks = _split_message(text, 4096)
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="HTML")


def _split_message(text: str, max_len: int) -> list[str]:
    """Split long text at double-newline boundaries."""
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
