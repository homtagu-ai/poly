"""
PolyHunter Telegram Bot — /connect and /disconnect handlers.

Implements a ConversationHandler that walks the user through providing
their Polymarket CLOB API credentials (API Key, Secret, Passphrase).

Security rules (from DEFENSIVE_SECURITY_SPEC section 7):
  * Only works in private DMs -- rejects group chats.
  * Each credential message from the user is deleted immediately.
  * Credentials are never echoed back.
  * Validated via a read-only CLOB balance call before storage.
  * Encrypted at rest via crypto.encrypt_credentials().
"""

import asyncio
import logging
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.i18n import t, get_user_lang

logger = logging.getLogger(__name__)

# Conversation states
ASK_KEY, ASK_SECRET, ASK_PASSPHRASE = range(3)

# ---------------------------------------------------------------------------
# Lazy helper imports
# ---------------------------------------------------------------------------

def _get_db():
    from bot import db
    return db


def _get_crypto():
    from bot import crypto
    return crypto


async def _build_clob_client(api_key: str, api_secret: str, passphrase: str):
    """
    Build a ClobClient from raw credentials and attempt a balance check.
    Returns (client, balance) on success, raises on failure.
    """
    def _create_and_validate():
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
        from shared.constants import CLOB_API, POLYGON_CHAIN_ID

        client = ClobClient(
            host=CLOB_API,
            chain_id=POLYGON_CHAIN_ID,
            creds=ApiCreds(
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=passphrase,
            ),
        )
        # Validate credentials with a lightweight read-only call
        resp = client.get_balance_allowance()
        balance = None
        if resp and hasattr(resp, 'balance'):
            balance = float(resp.balance) / 1e6
        elif isinstance(resp, dict):
            balance = float(resp.get('balance', 0)) / 1e6
        return client, balance

    return await asyncio.to_thread(_create_and_validate)


# ---------------------------------------------------------------------------
# Disclaimer text (DEFENSIVE_SECURITY_SPEC 7.1)
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "<b>BEFORE YOU CONNECT:</b>\n"
    "\n"
    "1. We store your Polymarket CLOB API credentials "
    "(API Key, Secret, Passphrase)\n"
    "2. These credentials allow us to place trades on your behalf <b>ONLY</b>\n"
    "3. We <b>CANNOT</b> withdraw your funds or access your wallet\n"
    "4. Your credentials are encrypted at rest with AES-256\n"
    "5. You can revoke access instantly with /disconnect -- "
    "credentials are permanently deleted\n"
    "6. We log every trade action -- view anytime with /history\n"
    "7. You set your own limits (max bet size, daily budget, slippage "
    "tolerance)\n"
    "8. <b>Never share your wallet private key or seed phrase with anyone, "
    "including us</b>\n"
    "\n"
    "To proceed, please send your <b>API Key</b> now.\n"
    "Type /cancel at any time to abort."
)


# ---------------------------------------------------------------------------
# Conversation entry point
# ---------------------------------------------------------------------------

async def connect_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /connect -- Begin the credential-linking flow.

    Only allowed in private DMs.
    """
    lang = await get_user_lang(update, context)
    context.user_data["lang"] = lang

    if update.effective_chat.type != "private":
        await update.message.reply_text(t("connect.dm_only", lang))
        return ConversationHandler.END

    await update.message.reply_text(t("connect.disclaimer", lang), parse_mode="HTML")
    return ASK_KEY


# ---------------------------------------------------------------------------
# Step 1 -- Receive API Key
# ---------------------------------------------------------------------------

async def receive_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the API key in user_data and delete the user's message."""
    api_key = update.message.text.strip()

    # Delete the message containing the credential immediately
    try:
        await update.message.delete()
    except Exception:
        logger.warning(
            "Could not delete credential message for user %s",
            update.effective_user.id,
        )

    lang = context.user_data.get("lang", "en")

    if not api_key:
        await update.effective_chat.send_message(t("connect.invalid_key", lang))
        return ASK_KEY

    context.user_data["_connect_key"] = api_key
    await update.effective_chat.send_message(
        t("connect.key_received", lang),
        parse_mode="HTML",
    )
    return ASK_SECRET


# ---------------------------------------------------------------------------
# Step 2 -- Receive API Secret
# ---------------------------------------------------------------------------

async def receive_secret(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the API secret in user_data and delete the user's message."""
    api_secret = update.message.text.strip()

    try:
        await update.message.delete()
    except Exception:
        logger.warning(
            "Could not delete credential message for user %s",
            update.effective_user.id,
        )

    lang = context.user_data.get("lang", "en")

    if not api_secret:
        await update.effective_chat.send_message(t("connect.invalid_secret", lang))
        return ASK_SECRET

    context.user_data["_connect_secret"] = api_secret
    await update.effective_chat.send_message(
        t("connect.secret_received", lang),
        parse_mode="HTML",
    )
    return ASK_PASSPHRASE


# ---------------------------------------------------------------------------
# Step 3 -- Receive Passphrase, validate, encrypt, store
# ---------------------------------------------------------------------------

async def receive_passphrase(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    Validate credentials via CLOB balance check, then encrypt and store.
    """
    passphrase = update.message.text.strip()

    try:
        await update.message.delete()
    except Exception:
        logger.warning(
            "Could not delete credential message for user %s",
            update.effective_user.id,
        )

    lang = context.user_data.get("lang", "en")

    api_key = context.user_data.pop("_connect_key", None)
    api_secret = context.user_data.pop("_connect_secret", None)

    if not api_key or not api_secret or not passphrase:
        await update.effective_chat.send_message(t("connect.missing_data", lang))
        return ConversationHandler.END

    # --- Validate by attempting a balance fetch --------------------------------
    await update.effective_chat.send_message(t("connect.validating", lang))

    try:
        client, balance = await _build_clob_client(api_key, api_secret, passphrase)
    except Exception as exc:
        logger.info(
            "Credential validation failed for user %s: %s",
            update.effective_user.id,
            exc,
        )
        await update.effective_chat.send_message(
            t("connect.validation_failed", lang, error=str(exc)),
            parse_mode="HTML",
        )
        return ConversationHandler.END

    # --- Encrypt and store -----------------------------------------------------
    db = _get_db()
    crypto_mod = _get_crypto()
    telegram_id = update.effective_user.id

    try:
        # crypto.encrypt_credentials returns (ciphertext, iv, auth_tag)
        encrypted_blob, iv, auth_tag = await asyncio.to_thread(
            crypto_mod.encrypt_credentials,
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=passphrase,
        )
        await db.store_credentials(
            telegram_user_id=telegram_id,
            encrypted_blob=encrypted_blob,
            iv=iv,
            auth_tag=auth_tag,
        )
    except Exception:
        logger.exception("Failed to store credentials for user %s", telegram_id)
        await update.effective_chat.send_message(t("connect.store_error", lang))
        return ConversationHandler.END

    # Cache the authenticated CLOB client for the remainder of the session
    context.user_data["clob_client"] = client

    balance_str = f"${balance:.2f}" if balance is not None else "connected"
    await update.effective_chat.send_message(
        t("connect.success", lang, balance=balance_str),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /disconnect
# ---------------------------------------------------------------------------

async def disconnect_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    /disconnect -- Immediately delete stored credentials.
    No confirmation prompt -- instant deletion per DEFENSIVE_SECURITY_SPEC 3.3.
    """
    lang = await get_user_lang(update, context)
    db = _get_db()
    telegram_id = update.effective_user.id

    try:
        success = await db.delete_credentials(
            telegram_user_id=telegram_id,
        )
    except Exception:
        logger.exception("Failed to delete credentials for user %s", telegram_id)
        await update.message.reply_text(t("disconnect.error", lang))
        return

    # Clear cached CLOB client
    context.user_data.pop("clob_client", None)

    if success:
        await update.message.reply_text(t("disconnect.success", lang))
    else:
        await update.message.reply_text(t("disconnect.no_credentials", lang))


# ---------------------------------------------------------------------------
# /cancel  (inside the conversation)
# ---------------------------------------------------------------------------

async def cancel_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """/cancel -- Abort the credential-linking conversation."""
    # Clean up any partial data
    context.user_data.pop("_connect_key", None)
    context.user_data.pop("_connect_secret", None)

    lang = context.user_data.get("lang", "en")
    await update.message.reply_text(t("connect.cancelled", lang))
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Build the ConversationHandler (importable by the application factory)
# ---------------------------------------------------------------------------

def build_connect_conversation() -> ConversationHandler:
    """Return the ConversationHandler for /connect."""
    return ConversationHandler(
        entry_points=[CommandHandler("connect", connect_start)],
        states={
            ASK_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_key),
            ],
            ASK_SECRET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_secret),
            ],
            ASK_PASSPHRASE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, receive_passphrase
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        per_user=True,
        per_chat=True,
    )
