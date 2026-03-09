"""
PolyHunter Telegram Bot — /copytrade handler.

Implements the full 19-setting inline keyboard for copy-trade configuration,
matching PolyCop's layout.  Each config row is an InlineKeyboardButton with
callback_data formatted as ``ct:{config_id[:8]}:{field_code}``.

Field codes
-----------
wallet  — Target Wallet address
tag     — User label / tag
cpct    — Copy Percentage/$
btype   — Buy order type toggle (Market / Limit)
bslip   — Buy market-order slippage %
tp      — Take Profit %/Price
sl      — Stop Loss %/Price
bmin    — Below-Min toggle
ign     — Ignore trades under $X
minp    — Min Price filter
maxp    — Max Price filter
tlim    — Total Spend Limit
tmin    — Min per trade
tmax    — Max per trade
myn     — Max per Yes/No
mmkt    — Max per Market
mmkts   — Max Holder Market Number
cbuy    — Copy Buy toggle
csel    — Copy Sell toggle
stype   — Sell order type toggle (Market / Limit)
sslip   — Sell market-order slippage %
save    — Create / Save button
back    — Back button
"""

import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.i18n import t, get_user_lang

logger = logging.getLogger(__name__)


def _get_db():
    from bot import db
    return db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short_id(config_id: str) -> str:
    """Return first 8 characters of a config UUID for callback_data."""
    return str(config_id)[:8]


def _wallet_display(wallet: Optional[str]) -> str:
    if not wallet:
        return "-"
    return f"{wallet[:6]}...{wallet[-4:]}"


def _val(value, prefix: str = "$", suffix: str = "") -> str:
    """Format a numeric value for display; show '-' when None / 0."""
    if value is None:
        return "-"
    if isinstance(value, (int, float)) and value == 0:
        return "-"
    return f"{prefix}{value}{suffix}"


def _pct(value, default: str = "5") -> str:
    if value is None:
        return f"{default}%"
    return f"{value}%"


def _toggle(value: bool) -> str:
    return "✅" if value else "❌"


def _order_type_label(order_type: Optional[str]) -> str:
    if order_type == "limit":
        return "Limit"
    return "Market"


# ---------------------------------------------------------------------------
# Default config dict (used when creating a brand-new config)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "id": None,
    "target_wallet": None,
    "tag": None,
    "copy_percentage": 100,
    "copy_mode": "percentage",           # 'percentage' or 'fixed_amount'
    "buy_order_type": "market",
    "buy_slippage_pct": 5,
    "tp_value": None,
    "sl_value": None,
    "below_min_buy_at_min": True,
    "ignore_trades_under_usd": None,
    "min_price": None,
    "max_price": None,
    "total_spend_limit_usd": None,
    "min_per_trade_usd": None,
    "max_per_trade_usd": None,
    "max_per_yes_no_usd": None,
    "max_per_market_usd": None,
    "max_markets": None,
    "copy_buy": True,
    "copy_sell": True,
    "sell_order_type": "market",
    "sell_slippage_pct": 5,
    "limit_price_offset": 0.0,
    "limit_order_duration": 90,
    "is_active": False,
}


# ---------------------------------------------------------------------------
# Keyboard builder
# ---------------------------------------------------------------------------

def build_config_keyboard(config: dict, lang: str = "en") -> InlineKeyboardMarkup:
    """
    Build the 19-row inline keyboard that matches PolyCop's layout.

    ``config`` is a dict (from DB or DEFAULT_CONFIG).
    """
    cid = _short_id(config.get("id") or "new00000")
    p = f"ct:{cid}"

    # Helper to shorten copy-percentage display
    cp = config.get("copy_percentage", 100)
    cp_display = f"{cp}%" if config.get("copy_mode") == "percentage" else f"${cp}"

    keyboard = [
        # Row 1 — Target Wallet
        [InlineKeyboardButton(
            t("copytrade.btn_target_wallet", lang, value=_wallet_display(config.get('target_wallet'))),
            callback_data=f"{p}:wallet",
        )],
        # Row 2 — Tag
        [InlineKeyboardButton(
            t("copytrade.btn_tag", lang, value=config.get('tag') or '-'),
            callback_data=f"{p}:tag",
        )],
        # Row 3 — Copy Percentage/$
        [InlineKeyboardButton(
            t("copytrade.btn_copy_pct", lang, value=cp_display),
            callback_data=f"{p}:cpct",
        )],
        # Row 4 — Order type toggle (Buy)
        [InlineKeyboardButton(
            t("copytrade.btn_buy_order_type", lang, value=_order_type_label(config.get('buy_order_type'))),
            callback_data=f"{p}:btype",
        )],
        # Row 5 — Buy market-order slippage
        [InlineKeyboardButton(
            t("copytrade.btn_buy_slippage", lang, value=_pct(config.get('buy_slippage_pct'))),
            callback_data=f"{p}:bslip",
        )],
        # Row 6 — TP / SL (two buttons)
        [
            InlineKeyboardButton(
                t("copytrade.btn_tp", lang, value=_val(config.get('tp_value'), prefix='', suffix='%') if config.get('tp_value') else '-'),
                callback_data=f"{p}:tp",
            ),
            InlineKeyboardButton(
                t("copytrade.btn_sl", lang, value=_val(config.get('sl_value'), prefix='', suffix='%') if config.get('sl_value') else '-'),
                callback_data=f"{p}:sl",
            ),
        ],
        # Row 7 — Below Min toggle
        [InlineKeyboardButton(
            t("copytrade.btn_below_min", lang, toggle=_toggle(config.get('below_min_buy_at_min', True))),
            callback_data=f"{p}:bmin",
        )],
        # Row 8 — Ignore trades under
        [InlineKeyboardButton(
            t("copytrade.btn_ignore_under", lang, value=_val(config.get('ignore_trades_under_usd'))),
            callback_data=f"{p}:ign",
        )],
        # Row 9 — Min Price / Max Price
        [
            InlineKeyboardButton(
                t("copytrade.btn_min_price", lang, value=_val(config.get('min_price'))),
                callback_data=f"{p}:minp",
            ),
            InlineKeyboardButton(
                t("copytrade.btn_max_price", lang, value=_val(config.get('max_price'))),
                callback_data=f"{p}:maxp",
            ),
        ],
        # Row 10 — Total Spend Limit
        [InlineKeyboardButton(
            t("copytrade.btn_total_limit", lang, value=_val(config.get('total_spend_limit_usd'))),
            callback_data=f"{p}:tlim",
        )],
        # Row 11 — Min/Trade / Max/Trade
        [
            InlineKeyboardButton(
                t("copytrade.btn_min_trade", lang, value=_val(config.get('min_per_trade_usd'))),
                callback_data=f"{p}:tmin",
            ),
            InlineKeyboardButton(
                t("copytrade.btn_max_trade", lang, value=_val(config.get('max_per_trade_usd'))),
                callback_data=f"{p}:tmax",
            ),
        ],
        # Row 12 — Max Per Yes/No / Max Per Market
        [
            InlineKeyboardButton(
                t("copytrade.btn_max_yes_no", lang, value=_val(config.get('max_per_yes_no_usd'))),
                callback_data=f"{p}:myn",
            ),
            InlineKeyboardButton(
                t("copytrade.btn_max_market", lang, value=_val(config.get('max_per_market_usd'))),
                callback_data=f"{p}:mmkt",
            ),
        ],
        # Row 13 — Max Holder Market Number
        [InlineKeyboardButton(
            t("copytrade.btn_max_markets", lang, value=_val(config.get('max_markets'), prefix='')),
            callback_data=f"{p}:mmkts",
        )],
        # Row 14 — Copy Buy / Copy Sell toggles
        [
            InlineKeyboardButton(
                t("copytrade.btn_copy_buy", lang, toggle=_toggle(config.get('copy_buy', True))),
                callback_data=f"{p}:cbuy",
            ),
            InlineKeyboardButton(
                t("copytrade.btn_copy_sell", lang, toggle=_toggle(config.get('copy_sell', True))),
                callback_data=f"{p}:csel",
            ),
        ],
        # Row 15 — Sell order type toggle
        [InlineKeyboardButton(
            t("copytrade.btn_sell_order_type", lang, value=_order_type_label(config.get('sell_order_type'))),
            callback_data=f"{p}:stype",
        )],
        # Row 16 — Sell market-order slippage
        [InlineKeyboardButton(
            t("copytrade.btn_sell_slippage", lang, value=_pct(config.get('sell_slippage_pct'))),
            callback_data=f"{p}:sslip",
        )],
        # Row 17 — Limit Price Offset
        [InlineKeyboardButton(
            t("copytrade.btn_limit_offset", lang, value=config.get('limit_price_offset', 0.0)),
            callback_data=f"{p}:loff",
        )],
        # Row 18 — Limit Order Duration
        [InlineKeyboardButton(
            t("copytrade.btn_limit_duration", lang, value=config.get('limit_order_duration', 90)),
            callback_data=f"{p}:ldur",
        )],
        # Row 19 — Back / Save
        [
            InlineKeyboardButton(t("copytrade.btn_back", lang), callback_data=f"{p}:back"),
            InlineKeyboardButton(
                t("copytrade.btn_save", lang) if config.get("id") else t("copytrade.btn_create", lang),
                callback_data=f"{p}:save",
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# /copytrade — list configs or create new
# ---------------------------------------------------------------------------

async def copytrade_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    /copytrade — Show list of existing copy-trade configs with status,
    and a "Create New Copy Trade" button.
    """
    db = _get_db()
    telegram_id = update.effective_user.id
    lang = await get_user_lang(update, context)

    try:
        configs = await db.get_copy_trade_configs(telegram_id=telegram_id)
    except Exception:
        logger.exception("Failed to fetch copy trade configs for %s", telegram_id)
        await update.message.reply_text(
            t("copytrade.error_loading", lang)
        )
        return

    buttons = []
    if configs:
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

    # "Create New" button always at the bottom
    buttons.append([
        InlineKeyboardButton(
            t("copytrade.create_new", lang),
            callback_data="ct:new00000:new",
        )
    ])

    text = t("copytrade.title", lang) + "\n\n" + t("copytrade.select_or_create", lang)
    if not configs:
        text = t("copytrade.title", lang) + "\n\n" + t("copytrade.no_configs", lang)

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Show / edit a single config's keyboard
# ---------------------------------------------------------------------------

async def show_config_keyboard(
    update_or_query,
    config: dict,
    *,
    edit: bool = False,
    lang: str = "en",
) -> None:
    """
    Send (or edit) the 19-row inline keyboard for a given config.

    Parameters
    ----------
    update_or_query :
        Either a ``telegram.Update`` or a ``telegram.CallbackQuery``.
    config : dict
        The config dict (from DB or DEFAULT_CONFIG).
    edit : bool
        If True, edit the existing message instead of sending a new one.
    lang : str
        Language code for translations.
    """
    keyboard = build_config_keyboard(config, lang=lang)

    tag = config.get("tag") or _wallet_display(config.get("target_wallet")) or "New Config"
    status = t("copytrade.status_active", lang) if config.get("is_active") else t("copytrade.status_paused", lang)
    header = t("copytrade.header", lang, tag=tag, status=status) + "\n"

    # Determine whether we have a CallbackQuery or a plain Update
    from telegram import CallbackQuery

    if isinstance(update_or_query, CallbackQuery):
        query = update_or_query
        if edit:
            await query.edit_message_text(
                header, reply_markup=keyboard, parse_mode="HTML"
            )
        else:
            await query.message.reply_text(
                header, reply_markup=keyboard, parse_mode="HTML"
            )
    else:
        # It's an Update
        msg = update_or_query.effective_message or update_or_query.message
        if msg is None:
            return
        if edit and hasattr(msg, "edit_text"):
            await msg.edit_text(
                header, reply_markup=keyboard, parse_mode="HTML"
            )
        else:
            await msg.reply_text(
                header, reply_markup=keyboard, parse_mode="HTML"
            )
