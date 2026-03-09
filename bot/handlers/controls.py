"""
PolyHunter Telegram Bot — /stop and /resume handlers.

/stop  — Works in ANY context (group or private). Immediately pauses ALL
         of the user's active copy-trade configs.
/resume — Private DM only. Resumes all paused configs and resets the
          circuit breaker state.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.i18n import t, get_user_lang

logger = logging.getLogger(__name__)


def _get_db():
    from bot import db
    return db


# ---------------------------------------------------------------------------
# /stop
# ---------------------------------------------------------------------------

async def stop_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    /stop — Pause ALL active copy-trade configs for this user.

    This command works in any chat context (groups included) so that the
    user can emergency-stop trading even from a group conversation.
    """
    lang = await get_user_lang(update, context)
    db = _get_db()
    telegram_id = update.effective_user.id

    try:
        configs = await db.get_copy_trade_configs(telegram_id=telegram_id)
    except Exception:
        logger.exception("Failed to load configs for user %s", telegram_id)
        await update.message.reply_text(t("stop.error", lang))
        return

    if not configs:
        await update.message.reply_text(t("stop.no_configs", lang))
        return

    paused_count = 0
    for cfg in configs:
        if cfg.get("is_active"):
            try:
                await db.update_copy_trade_config(
                    config_id=cfg["id"],
                    updates={"is_active": False},
                )
                paused_count += 1
            except Exception:
                logger.exception(
                    "Failed to pause config %s for user %s",
                    cfg["id"],
                    telegram_id,
                )

    if paused_count == 0:
        await update.message.reply_text(t("stop.already_paused", lang))
    else:
        await update.message.reply_text(
            t("stop.success", lang, count=paused_count)
        )


# ---------------------------------------------------------------------------
# /resume
# ---------------------------------------------------------------------------

async def resume_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    /resume — Resume all paused copy-trade configs (private DM only).

    Also resets any circuit-breaker flags so that trading can continue
    after a safety pause.
    """
    lang = await get_user_lang(update, context)

    # Enforce private-DM only
    if update.effective_chat.type != "private":
        await update.message.reply_text(t("resume.dm_only", lang))
        return

    db = _get_db()
    telegram_id = update.effective_user.id

    try:
        configs = await db.get_copy_trade_configs(telegram_id=telegram_id)
    except Exception:
        logger.exception("Failed to load configs for user %s", telegram_id)
        await update.message.reply_text(t("resume.error", lang))
        return

    if not configs:
        await update.message.reply_text(t("resume.no_configs", lang))
        return

    resumed_count = 0
    for cfg in configs:
        if not cfg.get("is_active"):
            try:
                await db.update_copy_trade_config(
                    config_id=cfg["id"],
                    updates={"is_active": True},
                )
                resumed_count += 1
            except Exception:
                logger.exception(
                    "Failed to resume config %s for user %s",
                    cfg["id"],
                    telegram_id,
                )

    # Reset circuit breaker for this user
    try:
        await db.reset_circuit_breaker(telegram_id=telegram_id)
    except Exception:
        logger.warning(
            "Could not reset circuit breaker for user %s (may not be implemented yet)",
            telegram_id,
        )

    if resumed_count == 0:
        await update.message.reply_text(t("resume.already_active", lang))
    else:
        await update.message.reply_text(
            t("resume.success", lang, count=resumed_count)
        )
