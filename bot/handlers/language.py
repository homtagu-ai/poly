"""
PolyHunter Telegram Bot — /language handler.
Allows the user to select their preferred language via an inline keyboard.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.i18n import SUPPORTED_LANGUAGES, t, get_user_lang

logger = logging.getLogger(__name__)

# Native display names with layout matching PolyCop screenshot:
# 2 columns, 4 rows + 1 centered Español row + Back
LANG_DISPLAY = [
    ("en", "English"),    ("ja", "日本語"),
    ("ru", "Русский"),    ("ko", "한국어"),
    ("fr", "Français"),   ("ar", "عربي"),
    ("zh-TW", "繁體中文"), ("pt", "Português"),
    ("es", "Español"),
]

async def language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/language — Show language selection keyboard."""
    lang = await get_user_lang(update, context)

    buttons = []
    row = []
    for code, name in LANG_DISPLAY:
        row.append(InlineKeyboardButton(name, callback_data=f"lang:{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:  # Español alone
        buttons.append(row)
    # Back button
    buttons.append([InlineKeyboardButton(t("copytrade.btn_back", lang), callback_data="lang:back")])

    await update.message.reply_text(
        t("language.select", lang),
        reply_markup=InlineKeyboardMarkup(buttons),
    )
