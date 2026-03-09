"""
PolyHunter Telegram Bot — /app handler.

Opens the Telegram Mini App (TMA) via a WebAppInfo inline keyboard button.
"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from bot.config import TMA_URL
from bot.i18n import t, get_user_lang

logger = logging.getLogger(__name__)


async def app_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /app — Open the PolyHunter Mini App.

    Sends an inline keyboard button that launches the Telegram Mini App
    (WebApp) inside Telegram's native viewer.
    """
    lang = await get_user_lang(update, context)

    if not TMA_URL:
        await update.message.reply_text(
            t("app.not_configured", lang),
            parse_mode="HTML",
        )
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text=t("app.open_button", lang),
                web_app=WebAppInfo(url=TMA_URL),
            )
        ]
    ])

    await update.message.reply_text(
        t("app.message", lang),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
