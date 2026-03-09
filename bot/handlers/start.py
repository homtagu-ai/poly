"""
PolyHunter Telegram Bot — /start and /help handlers.

Handles first-time user registration and welcome messaging.
"""

import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.notifications import format_welcome_message
from bot.i18n import t, get_user_lang

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports for DB / CLOB helpers to avoid circular-import issues at
# module level.  These are resolved at call time.
# ---------------------------------------------------------------------------

def _get_db():
    from bot import db
    return db


def _get_clob_client(context: ContextTypes.DEFAULT_TYPE):
    """Return a cached ClobClient from context.user_data, or None."""
    return context.user_data.get("clob_client")


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start — Welcome message.

    * If the user is not yet in the database, create a record.
    * Show bot name, description, balance placeholder, and command list.
    """
    user = update.effective_user
    if user is None:
        return

    db = _get_db()
    telegram_id = user.id
    chat_id = update.effective_chat.id if update.effective_chat else None

    # Ensure the user exists in our DB (synchronous call, run in thread)
    try:
        db_user = await asyncio.to_thread(
            db.get_or_create_telegram_user,
            telegram_user_id=telegram_id,
            username=user.username,
            chat_id=chat_id,
        )
    except Exception:
        logger.exception("Failed to get_or_create_telegram_user for %s", telegram_id)
        db_user = None

    # Attempt to fetch balance if credentials are connected
    balance = None
    clob = _get_clob_client(context)
    if clob is not None:
        try:
            bal = await clob.get_balance()
            balance = float(bal) if bal is not None else None
        except Exception:
            logger.debug("Could not fetch CLOB balance for user %s", telegram_id)

    lang = await get_user_lang(update, context)
    text = format_welcome_message(user, balance, lang=lang)

    # Try to send with a welcome banner image
    try:
        from bot.assets.generate import generate_welcome_banner
        import io
        name = user.first_name or user.username or "Trader"
        banner_bytes = generate_welcome_banner(name)
        # Photo captions limited to 1024 chars; fall back to text if too long
        if len(text) <= 1024:
            await update.message.reply_photo(
                photo=io.BytesIO(banner_bytes),
                caption=text,
                parse_mode="HTML",
            )
        else:
            await update.message.reply_photo(photo=io.BytesIO(banner_bytes))
            await update.message.reply_text(text, parse_mode="HTML")
    except Exception:
        logger.debug("Could not send welcome banner, falling back to text")
        await update.message.reply_text(text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------

HELP_TEXT = (
    "<b>PolyHunter Bot -- Command Reference</b>\n"
    "\n"
    "/start -- Show welcome message and balance\n"
    "/help -- This command reference\n"
    "\n"
    "<b>Credentials</b>\n"
    "/connect -- Link your Polymarket CLOB API keys (private DM only)\n"
    "/disconnect -- Remove stored credentials and stop trading\n"
    "\n"
    "<b>Copy Trading</b>\n"
    "/copytrade -- Manage copy-trade configurations\n"
    "/stop -- Pause ALL active copy-trade configs\n"
    "/resume -- Resume all paused configs (private DM only)\n"
    "\n"
    "<b>Portfolio</b>\n"
    "/positions -- View your open positions and P&L\n"
    "/history -- View recent trade log (last 20 entries)\n"
)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help -- Send the command reference."""
    lang = await get_user_lang(update, context)
    text = (
        t("help.title", lang) + "\n\n"
        + t("help.start", lang) + "\n"
        + t("help.help", lang) + "\n"
        + t("help.language", lang) + "\n\n"
        + t("help.credentials_header", lang) + "\n"
        + t("help.connect", lang) + "\n"
        + t("help.disconnect", lang) + "\n\n"
        + t("help.copytrade_header", lang) + "\n"
        + t("help.copytrade", lang) + "\n"
        + t("help.stop", lang) + "\n"
        + t("help.resume", lang) + "\n\n"
        + t("help.portfolio_header", lang) + "\n"
        + t("help.positions", lang) + "\n"
        + t("help.history", lang) + "\n\n"
        + t("help.app", lang)
    )
    await update.message.reply_text(text, parse_mode="HTML")
