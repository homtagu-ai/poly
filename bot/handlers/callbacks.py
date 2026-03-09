"""
PolyHunter Telegram Bot — Callback query router and typed-input handler.

All InlineKeyboardButton presses arrive here via ``callback_router``.

Routing scheme
--------------
``ct:{config_id_prefix}:{field}``
    Copy-trade configuration actions.  ``field`` is one of the short codes
    defined in ``copytrade.py``.

Toggle fields (flip a boolean, then refresh keyboard):
    btype, bmin, cbuy, csel, stype

Input fields (prompt user to type a value):
    wallet, tag, cpct, bslip, tp, sl, ign, minp, maxp,
    tlim, tmin, tmax, myn, mmkt, mmkts, sslip

Special:
    save  — validate & persist the config
    back  — return to the config list
    open  — open an existing config's keyboard
    new   — start a fresh config
"""

import logging
import re
from typing import Optional

from telegram import CallbackQuery, Update
from telegram.ext import ContextTypes

from bot.i18n import t, get_user_lang

from bot.handlers.copytrade import (
    DEFAULT_CONFIG,
    build_config_keyboard,
    show_config_keyboard,
    _short_id,
    _wallet_display,
)

logger = logging.getLogger(__name__)


def _get_db():
    from bot import db
    return db


# ---------------------------------------------------------------------------
# Mapping of field codes to human-readable names and DB column names
# ---------------------------------------------------------------------------

FIELD_META = {
    "wallet":  {"label": "Target Wallet",                "column": "target_wallet",            "type": "address"},
    "tag":     {"label": "Tag",                          "column": "tag",                      "type": "text"},
    "cpct":    {"label": "Copy Percentage/$",            "column": "copy_percentage",          "type": "number"},
    "bslip":   {"label": "Market Order Slippage %",      "column": "buy_slippage_pct",         "type": "number"},
    "tp":      {"label": "Take Profit %/Price",          "column": "tp_value",                 "type": "number_or_none"},
    "sl":      {"label": "Stop Loss %/Price",            "column": "sl_value",                 "type": "number_or_none"},
    "ign":     {"label": "Ignore Trades Under $",        "column": "ignore_trades_under_usd",  "type": "number_or_none"},
    "minp":    {"label": "Min Price $",                  "column": "min_price",                "type": "number_or_none"},
    "maxp":    {"label": "Max Price $",                  "column": "max_price",                "type": "number_or_none"},
    "tlim":    {"label": "Total Spend Limit $",          "column": "total_spend_limit_usd",    "type": "number_or_none"},
    "tmin":    {"label": "Min Per Trade $",              "column": "min_per_trade_usd",        "type": "number_or_none"},
    "tmax":    {"label": "Max Per Trade $",              "column": "max_per_trade_usd",        "type": "number_or_none"},
    "myn":     {"label": "Max Per Yes/No $",             "column": "max_per_yes_no_usd",       "type": "number_or_none"},
    "mmkt":    {"label": "Max Per Market $",             "column": "max_per_market_usd",       "type": "number_or_none"},
    "mmkts":   {"label": "Max Holder Market Number",     "column": "max_markets",              "type": "int_or_none"},
    "sslip":   {"label": "Sell Market Order Slippage %", "column": "sell_slippage_pct",        "type": "number"},
    "loff":    {"label": "Limit Price Offset",          "column": "limit_price_offset",    "type": "offset"},
    "ldur":    {"label": "Limit Order Duration (s)",     "column": "limit_order_duration",  "type": "duration"},
}

# Fields that are boolean toggles
TOGGLE_FIELDS = {
    "btype":  "buy_order_type",
    "bmin":   "below_min_buy_at_min",
    "cbuy":   "copy_buy",
    "csel":   "copy_sell",
    "stype":  "sell_order_type",
}

ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


# ---------------------------------------------------------------------------
# Config cache in context.user_data
# ---------------------------------------------------------------------------

def _cache_key(config_id_prefix: str) -> str:
    return f"_ct_cfg_{config_id_prefix}"


async def _resolve_config(
    context: ContextTypes.DEFAULT_TYPE,
    telegram_id: int,
    config_id_prefix: str,
) -> Optional[dict]:
    """
    Resolve a config dict by its 8-char prefix.
    Uses context.user_data as a short-lived cache.
    """
    ck = _cache_key(config_id_prefix)
    cached = context.user_data.get(ck)
    if cached is not None:
        return cached

    db = _get_db()
    try:
        configs = await db.get_copy_trade_configs(telegram_id=telegram_id)
    except Exception:
        logger.exception("Failed to load configs for %s", telegram_id)
        return None

    for cfg in configs:
        if str(cfg["id"]).startswith(config_id_prefix):
            context.user_data[ck] = cfg
            return cfg
    return None


def _save_to_cache(context: ContextTypes.DEFAULT_TYPE, config: dict) -> None:
    cid = _short_id(config.get("id") or "new00000")
    context.user_data[_cache_key(cid)] = config


# ---------------------------------------------------------------------------
# Main callback router
# ---------------------------------------------------------------------------

async def callback_router(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Route every ``CallbackQuery`` by parsing the prefix.

    Expected format:  ``ct:{config_id[:8]}:{field}``
    """
    query: CallbackQuery = update.callback_query
    await query.answer()  # acknowledge immediately

    data = query.data or ""

    # --- Language selection callbacks ---
    if data.startswith("lang:"):
        lang_code = data.split(":", 1)[1]
        if lang_code == "back":
            # Just delete the language keyboard message
            try:
                await query.delete_message()
            except Exception:
                pass
            return
        # Save language preference
        from bot.i18n import SUPPORTED_LANGUAGES
        if lang_code in SUPPORTED_LANGUAGES:
            from bot import db as _db
            telegram_id = update.effective_user.id
            try:
                await _db.update_language(telegram_id, lang_code)
            except Exception:
                logger.warning("Could not save language for user %s", telegram_id)
            context.user_data["lang"] = lang_code
            await query.edit_message_text(
                t("language.changed", lang_code, language=SUPPORTED_LANGUAGES[lang_code]),
                parse_mode="HTML",
            )
        return

    parts = data.split(":")
    if len(parts) < 3 or parts[0] != "ct":
        logger.warning("Unknown callback_data: %s", data)
        return

    prefix = parts[0]          # "ct"
    config_id_prefix = parts[1]  # first 8 chars of UUID or "new00000"
    field = parts[2]

    telegram_id = update.effective_user.id
    lang = context.user_data.get("lang", "en")

    # ------------------------------------------------------------------
    # "new" — start a fresh config
    # ------------------------------------------------------------------
    if field == "new":
        new_cfg = dict(DEFAULT_CONFIG)
        _save_to_cache(context, new_cfg)
        await show_config_keyboard(query, new_cfg, edit=True, lang=lang)
        return

    # ------------------------------------------------------------------
    # "open" — open an existing config
    # ------------------------------------------------------------------
    if field == "open":
        cfg = await _resolve_config(context, telegram_id, config_id_prefix)
        if cfg is None:
            await query.edit_message_text(t("callbacks.config_not_found", lang))
            return
        await show_config_keyboard(query, cfg, edit=True, lang=lang)
        return

    # ------------------------------------------------------------------
    # "back" — return to the config list
    # ------------------------------------------------------------------
    if field == "back":
        db = _get_db()
        try:
            configs = await db.get_copy_trade_configs(telegram_id=telegram_id)
        except Exception:
            configs = []

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        buttons = []
        for cfg in configs:
            status_icon = "✅" if cfg.get("is_active") else "❌"
            tag = cfg.get("tag") or _wallet_display(cfg.get("target_wallet"))
            cid = _short_id(cfg["id"])
            buttons.append([
                InlineKeyboardButton(
                    f"{status_icon} {tag}",
                    callback_data=f"ct:{cid}:open",
                )
            ])
        buttons.append([
            InlineKeyboardButton(
                t("copytrade.create_new", lang),
                callback_data="ct:new00000:new",
            )
        ])

        text = t("callbacks.list_header", lang)
        if not configs:
            text = t("callbacks.list_empty", lang)

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )
        return

    # ------------------------------------------------------------------
    # "save" — validate and persist
    # ------------------------------------------------------------------
    if field == "save":
        await _handle_save(query, context, telegram_id, config_id_prefix, lang=lang)
        return

    # ------------------------------------------------------------------
    # Toggle fields
    # ------------------------------------------------------------------
    if field in TOGGLE_FIELDS:
        await _handle_toggle(query, context, telegram_id, config_id_prefix, field, lang=lang)
        return

    # ------------------------------------------------------------------
    # Input fields — prompt user for typed input
    # ------------------------------------------------------------------
    if field in FIELD_META:
        meta = FIELD_META[field]
        context.user_data["awaiting_input"] = {
            "config_id_prefix": config_id_prefix,
            "field": field,
            "column": meta["column"],
            "type": meta["type"],
            "message_id": query.message.message_id,
            "chat_id": query.message.chat_id,
        }
        hint = ""
        if meta["type"] == "address":
            hint = t("callbacks.hint_address", lang)
        elif meta["type"] in ("number_or_none", "int_or_none"):
            hint = t("callbacks.hint_number_or_none", lang)
        elif meta["type"] == "number":
            hint = t("callbacks.hint_number", lang)
        elif meta["type"] == "offset":
            hint = t("callbacks.hint_offset", lang)
        elif meta["type"] == "duration":
            hint = t("callbacks.hint_duration", lang)

        await query.message.reply_text(
            t("callbacks.enter_value", lang, label=meta['label'], hint=hint),
            parse_mode="HTML",
        )
        return

    logger.warning("Unhandled callback field: %s (full data: %s)", field, data)


# ---------------------------------------------------------------------------
# Toggle handler
# ---------------------------------------------------------------------------

async def _handle_toggle(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_id: int,
    config_id_prefix: str,
    field: str,
    *,
    lang: str = "en",
) -> None:
    """Flip a boolean/enum value in the config and refresh the keyboard."""
    cfg = await _resolve_config(context, telegram_id, config_id_prefix)
    if cfg is None:
        # Might be a new (unsaved) config
        ck = _cache_key(config_id_prefix)
        cfg = context.user_data.get(ck)
    if cfg is None:
        cfg = dict(DEFAULT_CONFIG)
        _save_to_cache(context, cfg)

    column = TOGGLE_FIELDS[field]

    # Order-type fields toggle between "market" and "limit"
    if column in ("buy_order_type", "sell_order_type"):
        current = cfg.get(column, "market")
        cfg[column] = "limit" if current == "market" else "market"
    else:
        # Boolean toggle
        cfg[column] = not cfg.get(column, False)

    _save_to_cache(context, cfg)

    # Persist to DB if config has an id (already saved)
    if cfg.get("id"):
        db = _get_db()
        try:
            await db.update_copy_trade_config(
                config_id=cfg["id"],
                updates={column: cfg[column]},
            )
        except Exception:
            logger.exception("Failed to persist toggle for config %s", cfg["id"])

    # Refresh the keyboard inline
    keyboard = build_config_keyboard(cfg, lang=lang)
    try:
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except Exception:
        logger.debug("edit_message_reply_markup failed, trying full edit")
        await show_config_keyboard(query, cfg, edit=True, lang=lang)


# ---------------------------------------------------------------------------
# Save handler
# ---------------------------------------------------------------------------

async def _handle_save(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_id: int,
    config_id_prefix: str,
    *,
    lang: str = "en",
) -> None:
    """Validate the config has a target wallet, then create or update."""
    cfg = await _resolve_config(context, telegram_id, config_id_prefix)
    if cfg is None:
        ck = _cache_key(config_id_prefix)
        cfg = context.user_data.get(ck)
    if cfg is None:
        await query.edit_message_text(t("callbacks.no_config_data", lang))
        return

    # Validation: must have a target wallet
    wallet = cfg.get("target_wallet")
    if not wallet or not ETH_ADDRESS_RE.match(wallet):
        await query.answer(
            t("callbacks.wallet_required", lang),
            show_alert=True,
        )
        return

    db = _get_db()

    try:
        if cfg.get("id"):
            # Update existing
            updates = {k: v for k, v in cfg.items() if k != "id"}
            await db.update_copy_trade_config(
                config_id=cfg["id"],
                updates=updates,
            )
            # Activate on save
            await db.update_copy_trade_config(
                config_id=cfg["id"],
                updates={"is_active": True},
            )
            cfg["is_active"] = True
            _save_to_cache(context, cfg)
            await query.answer(t("callbacks.config_saved", lang), show_alert=True)
        else:
            # Create new
            cfg["is_active"] = True
            new_id = await db.create_copy_trade_config(
                telegram_id=telegram_id,
                config=cfg,
            )
            cfg["id"] = new_id
            _save_to_cache(context, cfg)
            await query.answer(t("callbacks.config_created", lang), show_alert=True)
    except Exception:
        logger.exception("Failed to save config for user %s", telegram_id)
        await query.answer(
            t("callbacks.save_failed", lang), show_alert=True
        )
        return

    # Refresh the keyboard to show updated state
    keyboard = build_config_keyboard(cfg, lang=lang)
    await show_config_keyboard(query, cfg, edit=True, lang=lang)


# ---------------------------------------------------------------------------
# Typed-input handler (called from a MessageHandler)
# ---------------------------------------------------------------------------

async def input_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Capture typed input after the user was prompted by a callback button.

    Reads ``context.user_data['awaiting_input']`` to know which field to
    update, validates the value, persists it, and refreshes the keyboard.
    """
    awaiting = context.user_data.pop("awaiting_input", None)
    if awaiting is None:
        # Not expecting input — ignore silently
        return

    lang = context.user_data.get("lang", "en")

    raw = update.message.text.strip()
    field = awaiting["field"]
    column = awaiting["column"]
    value_type = awaiting["type"]
    config_id_prefix = awaiting["config_id_prefix"]
    chat_id = awaiting["chat_id"]
    message_id = awaiting["message_id"]
    telegram_id = update.effective_user.id

    # --- Parse and validate ----------------------------------------------------
    parsed_value = None
    error = None

    if value_type == "address":
        # Clean common copy-paste artefacts
        cleaned = raw.strip()
        if not ETH_ADDRESS_RE.match(cleaned):
            error = t("callbacks.invalid_address", lang)
        else:
            parsed_value = cleaned

    elif value_type == "text":
        if len(raw) > 64:
            error = t("callbacks.tag_too_long", lang)
        else:
            parsed_value = raw

    elif value_type == "number":
        try:
            val = float(raw.replace("$", "").replace("%", "").replace(",", ""))
            if val < 0:
                error = t("callbacks.value_non_negative", lang)
            else:
                parsed_value = val
        except ValueError:
            error = t("callbacks.enter_valid_number", lang)

    elif value_type in ("number_or_none", "int_or_none"):
        cleaned = raw.replace("$", "").replace("%", "").replace(",", "").strip()
        if cleaned in ("0", "-", "none", "clear", ""):
            parsed_value = None  # clear the field
        else:
            try:
                val = int(cleaned) if value_type == "int_or_none" else float(cleaned)
                if val < 0:
                    error = t("callbacks.value_non_negative", lang)
                else:
                    parsed_value = val
            except ValueError:
                error = t("callbacks.enter_number_or_clear", lang)

    elif value_type == "offset":
        try:
            val = float(raw.replace(",", "").strip())
            if val < -0.99 or val > 0.99:
                error = t("callbacks.offset_range", lang)
            else:
                parsed_value = val
        except ValueError:
            error = t("callbacks.enter_valid_number", lang)

    elif value_type == "duration":
        try:
            val = int(raw.replace(",", "").replace("s", "").strip())
            if val < 90:
                error = t("callbacks.duration_min", lang)
            else:
                parsed_value = val
        except ValueError:
            error = t("callbacks.enter_valid_number", lang)

    if error:
        await update.message.reply_text(t("callbacks.invalid_input", lang, error=error))
        # Re-set awaiting so user can try again
        context.user_data["awaiting_input"] = awaiting
        return

    # --- Apply to config -------------------------------------------------------
    cfg = await _resolve_config(context, telegram_id, config_id_prefix)
    if cfg is None:
        ck = _cache_key(config_id_prefix)
        cfg = context.user_data.get(ck)
    if cfg is None:
        cfg = dict(DEFAULT_CONFIG)

    cfg[column] = parsed_value
    _save_to_cache(context, cfg)

    # Persist if already in DB
    if cfg.get("id"):
        db = _get_db()
        try:
            await db.update_copy_trade_config(
                config_id=cfg["id"],
                updates={column: parsed_value},
            )
        except Exception:
            logger.exception("Failed to update config field %s", column)

    # Confirm to user
    display = parsed_value if parsed_value is not None else "cleared"
    await update.message.reply_text(
        t("callbacks.field_set", lang, label=FIELD_META[field]['label'], value=display),
        parse_mode="HTML",
    )

    # Refresh the inline keyboard on the original settings message
    keyboard = build_config_keyboard(cfg, lang=lang)
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=keyboard,
        )
    except Exception:
        logger.debug(
            "Could not refresh keyboard (message_id=%s). User may need to "
            "re-open with /copytrade.",
            message_id,
        )
