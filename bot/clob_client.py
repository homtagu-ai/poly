"""
PolyHunter Bot -- Polymarket CLOB API Client Wrapper
Manages authenticated py_clob_client instances per Telegram user, with
credential decryption and connection caching.
"""
import base64
import logging
from datetime import datetime, timezone

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

from bot.crypto import decrypt_credentials
from shared.constants import CLOB_API, POLYGON_CHAIN_ID
from shared.supabase import _supabase_rest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_user_credentials(telegram_user_id: int) -> dict | None:
    """Fetch the active encrypted credential row for *telegram_user_id*.

    Joins through the ``telegram_users`` table to map Telegram ID to the
    Supabase ``user_id``, then queries ``user_trading_credentials``.

    Returns:
        A dict with ``encrypted_blob``, ``iv``, ``auth_tag``,
        ``user_id``, and ``key_version``; or ``None`` if not found.
    """
    # Step 1: resolve telegram_user_id -> user_id
    tg_rows = _supabase_rest(
        'telegram_users',
        method='GET',
        match={'telegram_id': str(telegram_user_id)},
        select='user_id',
    )
    if not tg_rows or not isinstance(tg_rows, list) or not tg_rows[0]:
        return None

    user_id = tg_rows[0].get('user_id', '')
    if not user_id:
        return None

    # Step 2: fetch active credentials for that user_id
    cred_rows = _supabase_rest(
        'user_trading_credentials',
        method='GET',
        match={'user_id': user_id, 'is_active': 'true'},
    )
    if not cred_rows or not isinstance(cred_rows, list) or not cred_rows[0]:
        return None

    row = cred_rows[0]
    row['_user_id'] = user_id
    return row


def _update_last_used(credential_id: str) -> None:
    """Bump the ``last_used_at`` timestamp on a credential row."""
    _supabase_rest(
        'user_trading_credentials',
        method='PATCH',
        data={'last_used_at': datetime.now(timezone.utc).isoformat()},
        match={'id': credential_id},
    )


# ---------------------------------------------------------------------------
# PolymarketClient
# ---------------------------------------------------------------------------

class PolymarketClient:
    """Manages authenticated ``ClobClient`` instances per Telegram user.

    Instances are cached in memory so that repeated calls within the same
    process do not re-decrypt credentials.  Call :meth:`clear_client` to
    evict a user's cached client (e.g. after ``/disconnect``).
    """

    def __init__(self) -> None:
        # telegram_user_id -> ClobClient
        self._cache: dict[int, ClobClient] = {}

    async def get_client(self, telegram_user_id: int) -> ClobClient | None:
        """Return an authenticated ``ClobClient`` for *telegram_user_id*.

        The first call decrypts the stored credentials and creates a new
        client; subsequent calls return the cached instance.

        Returns:
            A ready-to-use ``ClobClient``, or ``None`` if credentials
            are missing or decryption fails.
        """
        if telegram_user_id in self._cache:
            return self._cache[telegram_user_id]

        cred_row = _get_user_credentials(telegram_user_id)
        if cred_row is None:
            logger.debug('[CLOB] No active credentials for user %d',
                         telegram_user_id)
            return None

        try:
            # Decode binary fields stored as base64 strings in Supabase
            encrypted_blob = _decode_bytes(cred_row.get('encrypted_blob', ''))
            iv = _decode_bytes(cred_row.get('iv', ''))
            auth_tag = _decode_bytes(cred_row.get('auth_tag', ''))

            if not encrypted_blob or not iv:
                logger.error('[CLOB] Missing encrypted_blob or iv for user %d',
                             telegram_user_id)
                return None

            creds = decrypt_credentials(encrypted_blob, iv, auth_tag)

        except Exception:
            logger.exception(
                '[CLOB] Failed to decrypt credentials for user %d',
                telegram_user_id,
            )
            return None

        api_key = creds.get('api_key', '')
        api_secret = creds.get('api_secret', '')
        api_passphrase = creds.get('api_passphrase', '')

        if not api_key or not api_secret or not api_passphrase:
            logger.error('[CLOB] Incomplete credentials for user %d',
                         telegram_user_id)
            return None

        try:
            client = ClobClient(
                host=CLOB_API,
                chain_id=POLYGON_CHAIN_ID,
                creds=ApiCreds(
                    api_key=api_key,
                    api_secret=api_secret,
                    api_passphrase=api_passphrase,
                ),
            )

            # Validate by making a lightweight read call
            client.get_api_keys()

            self._cache[telegram_user_id] = client

            # Update last_used_at in DB
            cred_id = cred_row.get('id', '')
            if cred_id:
                _update_last_used(cred_id)

            logger.info('[CLOB] Client created and cached for user %d',
                        telegram_user_id)
            return client

        except Exception:
            logger.exception(
                '[CLOB] Failed to create/validate ClobClient for user %d',
                telegram_user_id,
            )
            return None

    def clear_client(self, telegram_user_id: int) -> None:
        """Remove the cached client for *telegram_user_id*.

        Called after ``/disconnect`` to ensure decrypted credentials are
        no longer held in memory.
        """
        removed = self._cache.pop(telegram_user_id, None)
        if removed is not None:
            logger.info('[CLOB] Cleared cached client for user %d',
                        telegram_user_id)

    def clear_all(self) -> None:
        """Remove all cached clients (e.g. on shutdown)."""
        count = len(self._cache)
        self._cache.clear()
        logger.info('[CLOB] Cleared %d cached clients', count)

    # ------------------------------------------------------------------
    # Convenience wrappers (all delegate to the underlying ClobClient)
    # ------------------------------------------------------------------

    async def get_balance(self, telegram_user_id: int) -> float | None:
        """Fetch USDC balance for *telegram_user_id*."""
        client = await self.get_client(telegram_user_id)
        if client is None:
            return None
        try:
            resp = client.get_balance_allowance()
            if resp and hasattr(resp, 'balance'):
                return float(resp.balance) / 1e6
            if isinstance(resp, dict):
                return float(resp.get('balance', 0)) / 1e6
            return None
        except Exception:
            logger.exception('[CLOB] Balance fetch failed for user %d',
                             telegram_user_id)
            return None

    async def get_positions(self, telegram_user_id: int) -> list:
        """Fetch open positions for *telegram_user_id*."""
        client = await self.get_client(telegram_user_id)
        if client is None:
            return []
        try:
            return client.get_positions() or []
        except Exception:
            logger.exception('[CLOB] Positions fetch failed for user %d',
                             telegram_user_id)
            return []

    async def create_and_post_order(
        self,
        telegram_user_id: int,
        order_args,
        order_type,
    ) -> dict | None:
        """Create, sign, and post an order for *telegram_user_id*.

        Args:
            order_args: ``OrderArgs`` instance from ``py_clob_client``.
            order_type: ``OrderType`` enum (GTC, FOK, GTD).

        Returns:
            The API response dict, or ``None`` on failure.
        """
        client = await self.get_client(telegram_user_id)
        if client is None:
            return None
        try:
            signed_order = client.create_order(order_args)
            return client.post_order(signed_order, order_type)
        except Exception:
            logger.exception('[CLOB] Order failed for user %d',
                             telegram_user_id)
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_bytes(value) -> bytes:
    """Decode a value that may be a base64 string, raw bytes, or None."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str) and value:
        try:
            return base64.b64decode(value)
        except Exception:
            return value.encode('latin-1')
    return b''
