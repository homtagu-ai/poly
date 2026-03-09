"""
PolyHunter Telegram Bot -- Internationalization (i18n) module.

Provides translation lookup, language detection, and a language-selection
inline keyboard.  Locale strings are stored as flat-key JSON files in
``bot/locales/``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported languages
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES = {
    "en": "English",
    "ja": "\u65e5\u672c\u8a9e",
    "ru": "\u0420\u0443\u0441\u0441\u043a\u0438\u0439",
    "ko": "\ud55c\uad6d\uc5b4",
    "fr": "Fran\u00e7ais",
    "ar": "\u0639\u0631\u0628\u064a",
    "zh-TW": "\u7e41\u9ad4\u4e2d\u6587",
    "pt": "Portugu\u00eas",
    "es": "Espa\u00f1ol",
}

DEFAULT_LANGUAGE = "en"

# ---------------------------------------------------------------------------
# Locale data (loaded once)
# ---------------------------------------------------------------------------

_locales: dict[str, dict[str, str]] = {}

LOCALES_DIR = Path(__file__).resolve().parent / "locales"


def _load_locales() -> None:
    """Load all JSON locale files from ``bot/locales/`` into ``_locales``."""
    global _locales
    _locales = {}

    if not LOCALES_DIR.is_dir():
        logger.warning("Locales directory not found: %s", LOCALES_DIR)
        return

    for filepath in LOCALES_DIR.glob("*.json"):
        lang_code = filepath.stem  # e.g. "en", "ja", "zh-TW"
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _locales[lang_code] = data
                logger.info("Loaded locale '%s' with %d keys", lang_code, len(data))
            else:
                logger.warning("Locale file %s is not a JSON object", filepath)
        except Exception:
            logger.exception("Failed to load locale file %s", filepath)


# Load on module import
_load_locales()


# ---------------------------------------------------------------------------
# Translation function
# ---------------------------------------------------------------------------

def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """Look up a translation string by *key* and *lang*.

    Fallback chain:
        1. ``_locales[lang][key]``
        2. ``_locales["en"][key]``  (English fallback)
        3. The *key* itself

    Any ``{placeholder}`` values are filled from *kwargs* via
    ``str.format(**kwargs)``.  Formatting errors are silently ignored.
    """
    # Try requested language
    text = _locales.get(lang, {}).get(key)

    # Fallback to English
    if text is None and lang != DEFAULT_LANGUAGE:
        text = _locales.get(DEFAULT_LANGUAGE, {}).get(key)

    # Fallback to key itself
    if text is None:
        text = key

    # Apply format substitutions
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # Silently ignore formatting errors -- better to show the raw
            # template than crash.
            pass

    return text


# ---------------------------------------------------------------------------
# Telegram language code mapping
# ---------------------------------------------------------------------------

def _map_telegram_lang(tg_lang: Optional[str]) -> str:
    """Map a Telegram ``language_code`` to one of our supported codes.

    Telegram sends BCP-47 codes like ``"en"``, ``"ja"``, ``"zh-hans"``,
    ``"pt-br"``, etc.  We map them to the closest supported language.

    Returns :data:`DEFAULT_LANGUAGE` if no match is found.
    """
    if not tg_lang:
        return DEFAULT_LANGUAGE

    code = tg_lang.lower().strip()

    # Exact match
    if code in SUPPORTED_LANGUAGES:
        return code

    # Special cases
    if code.startswith("zh"):
        return "zh-TW"

    # Prefix match (e.g. "pt-br" -> "pt", "es-mx" -> "es", "fr-ca" -> "fr")
    prefix = code.split("-")[0]
    if prefix in SUPPORTED_LANGUAGES:
        return prefix

    return DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# Get user language (async)
# ---------------------------------------------------------------------------

async def get_user_lang(update, context) -> str:
    """Resolve the user's preferred language.

    Resolution order:
        1. ``context.user_data["lang"]`` cache
        2. Database lookup via ``db.get_user_language()``
        3. ``update.effective_user.language_code`` mapped to supported codes
        4. Fallback ``"en"``

    The resolved language is cached in ``context.user_data["lang"]`` so
    subsequent calls within the same handler are free.
    """
    # 1. Cache hit
    cached = context.user_data.get("lang")
    if cached and cached in SUPPORTED_LANGUAGES:
        return cached

    # 2. Database lookup (lazy import to avoid circular imports)
    from bot import db

    telegram_id = update.effective_user.id if update.effective_user else None
    if telegram_id:
        try:
            db_lang = await asyncio.to_thread(db.get_user_language, telegram_id)
            if db_lang and db_lang in SUPPORTED_LANGUAGES:
                context.user_data["lang"] = db_lang
                return db_lang
        except Exception:
            logger.debug("Could not fetch language from DB for user %s", telegram_id)

    # 3. Telegram language_code
    if update.effective_user and update.effective_user.language_code:
        mapped = _map_telegram_lang(update.effective_user.language_code)
        context.user_data["lang"] = mapped
        return mapped

    # 4. Default
    context.user_data["lang"] = DEFAULT_LANGUAGE
    return DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# Language selection keyboard
# ---------------------------------------------------------------------------

def get_language_keyboard() -> InlineKeyboardMarkup:
    """Build an inline keyboard for language selection.

    Layout: 2 columns, with rows of 2 buttons each.  The last row may
    contain a single language button plus a back button, or just a back
    button on its own row.

    Each button's ``callback_data`` is ``lang:{code}``.
    """
    codes = list(SUPPORTED_LANGUAGES.keys())
    buttons: list[list[InlineKeyboardButton]] = []

    # Build rows of 2
    for i in range(0, len(codes), 2):
        row = []
        for code in codes[i : i + 2]:
            label = SUPPORTED_LANGUAGES[code]
            row.append(
                InlineKeyboardButton(label, callback_data=f"lang:{code}")
            )
        buttons.append(row)

    # Back button on its own row
    buttons.append([
        InlineKeyboardButton("\u2190 Back", callback_data="lang:back"),
    ])

    return InlineKeyboardMarkup(buttons)
