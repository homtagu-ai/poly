"""
PolyHunter Copy Trading Telegram Bot — Application Entry Point

Starts the bot in polling mode (development) or webhook mode (production).
Registers all command handlers, callback routers, and background tasks.

Usage:
    python -m bot.main              # polling mode (default, for local dev)
    python -m bot.main --webhook    # webhook mode (production)
"""

import asyncio
import logging
import signal
import sys
from argparse import ArgumentParser

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.config import TELEGRAM_BOT_TOKEN

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s  %(name)-28s  %(levelname)-7s  %(message)s",
    level=logging.INFO,
)
# Quieten noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)

logger = logging.getLogger("bot.main")


# ---------------------------------------------------------------------------
# Handler imports (lazy-ish, but at module level for clarity)
# ---------------------------------------------------------------------------

from bot.handlers.start import start_handler, help_handler
from bot.handlers.connect import build_connect_conversation, disconnect_handler
from bot.handlers.copytrade import copytrade_handler
from bot.handlers.callbacks import callback_router, input_handler
from bot.handlers.positions import positions_handler
from bot.handlers.history import history_handler
from bot.handlers.controls import stop_handler, resume_handler
from bot.handlers.language import language_handler
from bot.handlers.app import app_handler


# ---------------------------------------------------------------------------
# Background task launcher
# ---------------------------------------------------------------------------

async def _start_background_tasks(app: Application) -> None:
    """Create and start background tasks after the bot is fully initialized.

    Runs as a ``post_init`` callback so that ``app.bot`` is available for
    sending notifications.
    """
    try:
        from bot.clob_client import PolymarketClient
        from bot.engine.executor import TradeExecutor
        from bot.tasks.wallet_poller import WalletPollerTask
        from bot.tasks.tp_sl import TpSlMonitorTask
    except ImportError as exc:
        logger.warning(
            "Could not import trading engine (py-clob-client missing?): %s\n"
            "Bot will run in UI-ONLY mode — commands and settings work, "
            "but live trading is disabled.",
            exc,
        )
        return

    # Shared PolymarketClient singleton (caches authenticated ClobClients)
    poly_client = PolymarketClient()
    app.bot_data["poly_client"] = poly_client

    # Trade executor
    executor = TradeExecutor(poly_client)
    app.bot_data["executor"] = executor

    # Background task: wallet poller
    poller = WalletPollerTask(executor=executor, telegram_app=app)
    poller_task = asyncio.create_task(poller.run(), name="wallet_poller")
    app.bot_data["_poller_task"] = poller_task

    # Background task: TP/SL monitor
    tp_sl = TpSlMonitorTask(executor=executor, telegram_app=app)
    tp_sl_task = asyncio.create_task(tp_sl.run(), name="tp_sl_monitor")
    app.bot_data["_tp_sl_task"] = tp_sl_task

    logger.info("Background tasks started: wallet_poller, tp_sl_monitor")


async def _stop_background_tasks(app: Application) -> None:
    """Cancel background tasks on shutdown.

    Runs as a ``post_shutdown`` callback.
    """
    for key in ("_poller_task", "_tp_sl_task"):
        task = app.bot_data.get(key)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # Clear cached CLOB clients
    poly_client = app.bot_data.get("poly_client")
    if poly_client:
        poly_client.clear_all()

    logger.info("Background tasks stopped and cleanup complete")


# ---------------------------------------------------------------------------
# Application builder
# ---------------------------------------------------------------------------

def build_application() -> Application:
    """Build and configure the Telegram Application."""

    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set.  "
            "Please add it to your .env file."
        )
        sys.exit(1)

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(_start_background_tasks)
        .post_shutdown(_stop_background_tasks)
        .build()
    )

    # ----- Command handlers ------------------------------------------------
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))

    # /connect is a multi-step ConversationHandler
    app.add_handler(build_connect_conversation())

    app.add_handler(CommandHandler("disconnect", disconnect_handler))
    app.add_handler(CommandHandler("copytrade", copytrade_handler))
    app.add_handler(CommandHandler("positions", positions_handler))
    app.add_handler(CommandHandler("history", history_handler))
    app.add_handler(CommandHandler("stop", stop_handler))
    app.add_handler(CommandHandler("resume", resume_handler))
    app.add_handler(CommandHandler("language", language_handler))
    app.add_handler(CommandHandler("app", app_handler))

    # ----- Callback query handler (inline keyboard) -----------------------
    app.add_handler(CallbackQueryHandler(callback_router))

    # ----- Message handler for typed input (e.g. after pressing a button) --
    # Must come AFTER the ConversationHandler so it doesn't intercept
    # credential input during the /connect flow.
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, input_handler)
    )

    logger.info("Application configured with all handlers")
    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = ArgumentParser(description="PolyHunter Telegram Bot")
    parser.add_argument(
        "--webhook",
        action="store_true",
        help="Run in webhook mode (default: polling mode for local dev)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8443,
        help="Port for webhook server (default: 8443)",
    )
    args = parser.parse_args()

    app = build_application()

    if args.webhook:
        logger.info("Starting bot in WEBHOOK mode on port %d", args.port)
        # For production: requires HTTPS reverse proxy (nginx, caddy, etc.)
        app.run_webhook(
            listen="0.0.0.0",
            port=args.port,
            url_path="telegram-webhook",
            # Set your domain here via env var or arg
            # webhook_url=f"https://yourdomain.com/telegram-webhook",
        )
    else:
        logger.info("Starting bot in POLLING mode (local development)")
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=[
                "message",
                "callback_query",
            ],
        )


if __name__ == "__main__":
    main()
