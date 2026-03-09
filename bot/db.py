"""
PolyHunter Bot -- Supabase CRUD Layer
All database operations for the copy-trading bot, using the shared
``_supabase_rest`` helper (no Supabase SDK dependency).

Tables:
    telegram_users, user_trading_credentials, copy_trade_configs,
    copy_trade_positions, trade_log, wallet_monitor_state
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone

from shared.supabase import _supabase_rest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _first(rows):
    """Return the first element of *rows*, or ``None``."""
    if rows and isinstance(rows, list) and len(rows) > 0:
        return rows[0]
    return None


# ============================================================================
# telegram_users
# ============================================================================
def get_or_create_telegram_user(
    telegram_user_id: int,
    username: str = None,
    chat_id: int = None,
) -> dict | None:
    """Find or create a row in ``telegram_users``.

    Uses Supabase ``resolution=merge-duplicates`` (upsert) on the
    ``telegram_user_id`` column so the call is idempotent.

    Returns:
        The user row dict, or ``None`` on failure.
    """
    data = {
        'telegram_user_id': telegram_user_id,
        'telegram_username': username,
        'telegram_chat_id': chat_id,
        'updated_at': _now_iso(),
    }
    rows = _supabase_rest('telegram_users', method='POST', data=data)
    result = _first(rows)
    if result:
        logger.info('telegram_users upsert OK for tg_id=%s', telegram_user_id)
    else:
        logger.error('telegram_users upsert FAILED for tg_id=%s', telegram_user_id)
    return result


def get_user_language(telegram_user_id: int) -> str | None:
    """Fetch the user's language preference."""
    rows = _supabase_rest(
        'telegram_users',
        method='GET',
        match={'telegram_user_id': telegram_user_id},
        select='language',
    )
    row = _first(rows)
    if row:
        return row.get('language')
    return None


def set_user_language(telegram_user_id: int, language: str) -> bool:
    """Update the user's language preference."""
    result = _supabase_rest(
        'telegram_users',
        method='PATCH',
        data={'language': language, 'updated_at': _now_iso()},
        match={'telegram_user_id': telegram_user_id},
    )
    return result is not None


# ============================================================================
# user_trading_credentials
# ============================================================================
def _store_credentials_sync(
    telegram_user_id: int,
    encrypted_blob: bytes,
    iv: bytes,
    auth_tag: bytes,
) -> dict | None:
    """Insert or update encrypted API credentials.

    Binary fields are stored as base64 strings in Supabase (text columns).

    Returns:
        The credential row, or ``None`` on failure.
    """
    data = {
        'telegram_user_id': telegram_user_id,
        'encrypted_blob': '\\x' + encrypted_blob.hex(),
        'iv': '\\x' + iv.hex(),
        'auth_tag': '\\x' + auth_tag.hex(),
        'is_active': True,
    }
    rows = _supabase_rest('user_trading_credentials', method='POST', data=data)
    result = _first(rows)
    if result:
        logger.info('Credentials stored for tg_id=%s', telegram_user_id)
    else:
        logger.error('Failed to store credentials for tg_id=%s', telegram_user_id)
    return result


def get_active_credentials(telegram_user_id: int) -> dict | None:
    """Retrieve active encrypted credentials for a user.

    Returns the row dict with base64-encoded ``encrypted_blob``, ``iv``,
    ``auth_tag``, or ``None`` if not found.
    """
    rows = _supabase_rest(
        'user_trading_credentials',
        method='GET',
        match={'telegram_user_id': telegram_user_id, 'is_active': True},
    )
    return _first(rows)


def _delete_credentials_sync(telegram_user_id: int) -> bool:
    """Soft-delete credentials by setting ``is_active = false``.

    Returns ``True`` on success.
    """
    result = _supabase_rest(
        'user_trading_credentials',
        method='PATCH',
        data={'is_active': False, 'updated_at': _now_iso()},
        match={'telegram_user_id': telegram_user_id},
    )
    if result is not None:
        logger.info('Credentials deactivated for tg_id=%s', telegram_user_id)
        return True
    logger.error('Failed to deactivate credentials for tg_id=%s', telegram_user_id)
    return False


# ============================================================================
# copy_trade_configs
# ============================================================================
def create_copy_config(
    telegram_user_id: int,
    target_wallet: str,
) -> dict | None:
    """Create a new copy-trade config with sensible defaults.

    Returns:
        The newly created config dict.
    """
    from bot.config import (
        DEFAULT_BUY_SLIPPAGE,
        DEFAULT_SELL_SLIPPAGE,
        DEFAULT_COPY_PERCENTAGE,
    )

    config_id = str(uuid.uuid4())
    data = {
        'id': config_id,
        'telegram_user_id': telegram_user_id,
        'target_wallet': target_wallet.lower(),
        'is_active': True,
        'copy_percentage': DEFAULT_COPY_PERCENTAGE,
        'buy_slippage': DEFAULT_BUY_SLIPPAGE,
        'sell_slippage': DEFAULT_SELL_SLIPPAGE,
        'take_profit': None,
        'stop_loss': None,
        'max_position_size': None,
        'max_open_positions': None,
        'total_budget': None,
        'total_spent': 0.0,
        'created_at': _now_iso(),
        'updated_at': _now_iso(),
    }
    rows = _supabase_rest('copy_trade_configs', method='POST', data=data)
    result = _first(rows)
    if result:
        logger.info('Copy config %s created for tg_id=%s -> wallet %s',
                     config_id, telegram_user_id, target_wallet)
    else:
        logger.error('Failed to create copy config for tg_id=%s', telegram_user_id)
    return result


def update_copy_config(config_id: str, updates: dict) -> dict | None:
    """Patch an existing copy-trade config.

    Args:
        config_id: UUID of the config row.
        updates:   Dict of columns to update.

    Returns:
        The updated row, or ``None`` on failure.
    """
    updates['updated_at'] = _now_iso()
    rows = _supabase_rest(
        'copy_trade_configs',
        method='PATCH',
        data=updates,
        match={'id': config_id},
    )
    result = _first(rows)
    if result:
        logger.debug('Config %s updated: %s', config_id, list(updates.keys()))
    else:
        logger.error('Failed to update config %s', config_id)
    return result


def get_user_configs(telegram_user_id: int) -> list[dict]:
    """Return all copy-trade configs for a user (active and inactive)."""
    rows = _supabase_rest(
        'copy_trade_configs',
        method='GET',
        match={'telegram_user_id': telegram_user_id},
    )
    return rows if isinstance(rows, list) else []


def get_active_configs_by_wallet(target_wallet: str) -> list[dict]:
    """Return all *active* configs tracking a specific wallet."""
    rows = _supabase_rest(
        'copy_trade_configs',
        method='GET',
        match={'target_wallet': target_wallet.lower(), 'is_active': True},
    )
    return rows if isinstance(rows, list) else []


def get_all_active_configs() -> list[dict]:
    """Return every active copy-trade config (used by the wallet poller)."""
    rows = _supabase_rest(
        'copy_trade_configs',
        method='GET',
        match={'is_active': True},
    )
    return rows if isinstance(rows, list) else []


def increment_config_spent(config_id: str, amount: float) -> dict | None:
    """Atomically increment ``total_spent`` by *amount*.

    NOTE: Supabase REST does not natively support atomic increments, so we
    read-then-write.  The race window is small for a single-user bot, but
    a Postgres function / RPC would be safer under high concurrency.
    """
    rows = _supabase_rest(
        'copy_trade_configs',
        method='GET',
        match={'id': config_id},
        select='id,total_spent',
    )
    current = _first(rows)
    if current is None:
        logger.error('increment_config_spent: config %s not found', config_id)
        return None

    new_total = float(current.get('total_spent', 0)) + amount
    return update_copy_config(config_id, {'total_spent': round(new_total, 6)})


# ============================================================================
# copy_trade_positions
# ============================================================================
def create_position(
    config_id: str,
    telegram_user_id: int,
    market_slug: str,
    condition_id: str,
    token_id: str,
    side: str,
    entry_price: float,
    shares: float,
    cost_basis: float,
) -> dict | None:
    """Record a new open position.

    Returns:
        The position row dict.
    """
    position_id = str(uuid.uuid4())
    data = {
        'id': position_id,
        'config_id': config_id,
        'telegram_user_id': telegram_user_id,
        'market_slug': market_slug,
        'condition_id': condition_id,
        'token_id': token_id,
        'side': side,
        'entry_price': entry_price,
        'shares': shares,
        'cost_basis_usd': cost_basis,
        'is_open': True,
        'opened_at': _now_iso(),
    }
    rows = _supabase_rest('copy_trade_positions', method='POST', data=data)
    result = _first(rows)
    if result:
        logger.info('Position %s opened: %s %s @ %.4f',
                     position_id, side, market_slug, entry_price)
    else:
        logger.error('Failed to open position for config %s', config_id)
    return result


def close_position(
    position_id: str,
    exit_price: float,
    exit_reason: str,
    realized_pnl: float,
) -> dict | None:
    """Close an existing position.

    Args:
        position_id:  UUID of the position.
        exit_price:   Price at which the position was exited.
        exit_reason:  E.g. ``'copy_sell'``, ``'take_profit'``, ``'stop_loss'``,
                      ``'manual'``, ``'market_resolved'``.
        realized_pnl: Profit/loss in USD.

    Returns:
        The updated position row.
    """
    data = {
        'is_open': False,
        'exit_price': exit_price,
        'exit_reason': exit_reason,
        'realized_pnl': realized_pnl,
        'closed_at': _now_iso(),
    }
    rows = _supabase_rest(
        'copy_trade_positions',
        method='PATCH',
        data=data,
        match={'id': position_id},
    )
    result = _first(rows)
    if result:
        logger.info('Position %s closed (%s) pnl=%.4f',
                     position_id, exit_reason, realized_pnl)
    else:
        logger.error('Failed to close position %s', position_id)
    return result


def _get_open_positions_sync(telegram_user_id: int) -> list[dict]:
    """Return all open positions for a user (sync version)."""
    rows = _supabase_rest(
        'copy_trade_positions',
        method='GET',
        match={'telegram_user_id': telegram_user_id, 'is_open': True},
    )
    return rows if isinstance(rows, list) else []


def get_positions_with_tp_sl() -> list[dict]:
    """Return open positions whose parent config has TP or SL set.

    This joins positions with their configs client-side.  A Postgres view
    would be more efficient, but this keeps the implementation SDK-free.
    """
    # Step 1 -- all open positions
    positions = _supabase_rest(
        'copy_trade_positions',
        method='GET',
        match={'is_open': True},
    )
    if not positions:
        return []

    # Step 2 -- unique config IDs
    config_ids = {p['config_id'] for p in positions if 'config_id' in p}
    if not config_ids:
        return []

    # Step 3 -- fetch those configs
    all_configs = _supabase_rest(
        'copy_trade_configs',
        method='GET',
        match={'is_active': True},
    )
    if not all_configs:
        return []

    config_map = {c['id']: c for c in all_configs if 'id' in c}

    # Step 4 -- filter positions where config has TP or SL
    result = []
    for pos in positions:
        cfg = config_map.get(pos.get('config_id'))
        if cfg and (cfg.get('tp_value') is not None
                    or cfg.get('sl_value') is not None):
            pos['_config'] = cfg   # attach config for caller convenience
            result.append(pos)

    return result


# ============================================================================
# trade_log
# ============================================================================
def log_trade(
    telegram_user_id: int,
    config_id: str,
    action: str,
    **kwargs,
) -> dict | None:
    """Insert a row into ``trade_log``.

    Args:
        telegram_user_id: Telegram user ID.
        config_id:        Copy-config UUID.
        action:           E.g. ``'copy_buy'``, ``'copy_sell'``, ``'tp_sell'``,
                          ``'sl_sell'``, ``'manual_sell'``.
        **kwargs:         Additional columns: ``market_slug``, ``condition_id``,
                          ``token_id``, ``side``, ``price``, ``shares``,
                          ``cost_usd``, ``tx_hash``, ``error``, ``status``,
                          ``latency_ms``, etc.

    Returns:
        The inserted trade-log row.
    """
    data = {
        'id': str(uuid.uuid4()),
        'telegram_user_id': telegram_user_id,
        'config_id': config_id,
        'action': action,
        'created_at': _now_iso(),
    }
    # Merge caller-supplied columns
    data.update(kwargs)

    rows = _supabase_rest('trade_log', method='POST', data=data)
    result = _first(rows)
    if result:
        logger.debug('trade_log: %s for tg_id=%s config=%s',
                      action, telegram_user_id, config_id)
    else:
        logger.error('trade_log insert FAILED: %s for tg_id=%s',
                      action, telegram_user_id)
    return result


def _get_trade_history_sync(telegram_user_id: int, limit: int = 20) -> list[dict]:
    """Return the most recent trade-log entries for a user.

    NOTE: Supabase REST supports ordering via query params.  We append
    ``order`` manually.
    """
    from shared.supabase import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    import requests as _req

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.error('get_trade_history: Supabase not configured')
        return []

    url = f'{SUPABASE_URL}/rest/v1/trade_log'
    headers = {
        'apikey': SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
        'Content-Type': 'application/json',
    }
    params = {
        'telegram_user_id': f'eq.{telegram_user_id}',
        'order': 'created_at.desc',
        'limit': limit,
    }

    try:
        resp = _req.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error('get_trade_history failed: %s', exc)
        return []


# ============================================================================
# wallet_monitor_state
# ============================================================================
def get_or_update_monitor_state(
    target_wallet: str,
    last_tx_hash: str = None,
    last_block: int = None,
) -> dict | None:
    """Get or update the wallet-monitor checkpoint for *target_wallet*.

    If called without ``last_tx_hash`` / ``last_block``, returns the
    current state.  If called with values, upserts them.

    Returns:
        The state row dict.
    """
    wallet = target_wallet.lower()

    if last_tx_hash is None and last_block is None:
        # Read only
        rows = _supabase_rest(
            'wallet_monitor_state',
            method='GET',
            match={'target_wallet': wallet},
        )
        return _first(rows)

    # Upsert
    data = {
        'target_wallet': wallet,
        'updated_at': _now_iso(),
    }
    if last_tx_hash is not None:
        data['last_tx_hash'] = last_tx_hash
    if last_block is not None:
        data['last_block'] = last_block

    rows = _supabase_rest('wallet_monitor_state', method='POST', data=data)
    result = _first(rows)
    if result:
        logger.debug('Monitor state updated for wallet %s', wallet)
    else:
        logger.error('Failed to update monitor state for wallet %s', wallet)
    return result


# ============================================================================
# Aggregate / exposure helpers
# ============================================================================
def get_outcome_exposure(config_id: str, side: str) -> float:
    """Sum of ``cost_basis`` for all open positions with the given *side*
    under *config_id*.
    """
    rows = _supabase_rest(
        'copy_trade_positions',
        method='GET',
        match={'config_id': config_id, 'is_open': True, 'side': side},
        select='cost_basis',
    )
    if not rows or not isinstance(rows, list):
        return 0.0
    return sum(float(r.get('cost_basis', 0)) for r in rows)


def get_market_exposure(config_id: str, market_slug: str) -> float:
    """Sum of ``cost_basis`` for all open positions in a specific market
    under *config_id*.
    """
    rows = _supabase_rest(
        'copy_trade_positions',
        method='GET',
        match={
            'config_id': config_id,
            'is_open': True,
            'market_slug': market_slug,
        },
        select='cost_basis',
    )
    if not rows or not isinstance(rows, list):
        return 0.0
    return sum(float(r.get('cost_basis', 0)) for r in rows)


def get_distinct_market_count(config_id: str) -> int:
    """Count of unique ``market_slug`` values among open positions for
    *config_id*.
    """
    rows = _supabase_rest(
        'copy_trade_positions',
        method='GET',
        match={'config_id': config_id, 'is_open': True},
        select='market_slug',
    )
    if not rows or not isinstance(rows, list):
        return 0
    slugs = {r.get('market_slug') for r in rows if r.get('market_slug')}
    return len(slugs)


# ============================================================================
# Async wrappers for Telegram handlers
# ============================================================================
# The Telegram handlers are async and call these via ``await db.xxx()``.
# These wrappers run the sync Supabase REST calls in a thread pool to
# avoid blocking the event loop.

import asyncio as _asyncio


async def get_copy_trade_configs(telegram_id: int = None, **kwargs) -> list[dict]:
    """Async wrapper for :func:`get_user_configs`."""
    tg_id = telegram_id or kwargs.get('telegram_user_id', 0)
    return await _asyncio.to_thread(get_user_configs, tg_id)


async def update_copy_trade_config(config_id: str, updates: dict) -> dict | None:
    """Async wrapper for :func:`update_copy_config`."""
    return await _asyncio.to_thread(update_copy_config, config_id, updates)


async def create_copy_trade_config(telegram_id: int = None, config: dict = None, **kwargs) -> str:
    """Create a new copy-trade config from the full config dict.

    Inserts directly into Supabase with proper column mapping.
    Returns the new config's ID.
    """
    tg_id = telegram_id or kwargs.get('telegram_user_id', 0)
    cfg = config or {}

    config_id = str(uuid.uuid4())
    data = {
        'id': config_id,
        'telegram_user_id': tg_id,
        'target_wallet': (cfg.get('target_wallet') or '').lower(),
        'tag': cfg.get('tag') or '',
        'is_active': cfg.get('is_active', True),
        'copy_mode': cfg.get('copy_mode', 'percentage'),
        'copy_percentage': cfg.get('copy_percentage', 100),
        'buy_order_type': cfg.get('buy_order_type', 'market'),
        'buy_slippage_pct': cfg.get('buy_slippage_pct', 5.0),
        'sell_order_type': cfg.get('sell_order_type', 'market'),
        'sell_slippage_pct': cfg.get('sell_slippage_pct', 5.0),
        'copy_buy': cfg.get('copy_buy', True),
        'copy_sell': cfg.get('copy_sell', True),
        'tp_value': cfg.get('tp_value'),
        'sl_value': cfg.get('sl_value'),
        'below_min_buy_at_min': cfg.get('below_min_buy_at_min', True),
        'ignore_trades_under_usd': cfg.get('ignore_trades_under_usd', 0),
        'min_price': cfg.get('min_price'),
        'max_price': cfg.get('max_price'),
        'total_spend_limit_usd': cfg.get('total_spend_limit_usd'),
        'min_per_trade_usd': cfg.get('min_per_trade_usd'),
        'max_per_trade_usd': cfg.get('max_per_trade_usd'),
        'max_per_yes_no_usd': cfg.get('max_per_yes_no_usd'),
        'max_per_market_usd': cfg.get('max_per_market_usd'),
        'max_markets': cfg.get('max_markets'),
        'limit_price_offset': cfg.get('limit_price_offset', 0.0),
        'limit_order_duration': cfg.get('limit_order_duration', 90),
        'created_at': _now_iso(),
        'updated_at': _now_iso(),
    }

    def _insert():
        rows = _supabase_rest('copy_trade_configs', method='POST', data=data)
        return _first(rows)

    result = await _asyncio.to_thread(_insert)
    if result and isinstance(result, dict):
        logger.info('Copy config %s created for tg_id=%s', config_id, tg_id)
        return config_id
    logger.error('Failed to create copy config for tg_id=%s', tg_id)
    return ''


async def get_open_positions(telegram_id: int = None, **kwargs) -> list[dict]:
    """Async wrapper for :func:`_get_open_positions_sync`."""
    tg_id = telegram_id or kwargs.get('telegram_user_id', 0)
    return await _asyncio.to_thread(_get_open_positions_sync, tg_id)


async def get_trade_history(telegram_id: int = None, limit: int = 20, **kwargs) -> list[dict]:
    """Async wrapper for :func:`_get_trade_history_sync`."""
    tg_id = telegram_id or kwargs.get('telegram_user_id', 0)
    return await _asyncio.to_thread(_get_trade_history_sync, tg_id, limit)


async def store_credentials(
    telegram_user_id: int,
    encrypted_blob: bytes,
    iv: bytes,
    auth_tag: bytes,
) -> dict | None:
    """Async wrapper for :func:`store_credentials` (the sync version above)."""
    return await _asyncio.to_thread(
        _store_credentials_sync, telegram_user_id, encrypted_blob, iv, auth_tag
    )


async def delete_credentials(telegram_user_id: int) -> bool:
    """Async wrapper for :func:`delete_credentials` (the sync version above)."""
    return await _asyncio.to_thread(_delete_credentials_sync, telegram_user_id)


async def get_language(telegram_id: int) -> str | None:
    """Async wrapper for get_user_language."""
    return await _asyncio.to_thread(get_user_language, telegram_id)

async def update_language(telegram_id: int, language: str) -> bool:
    """Async wrapper for set_user_language."""
    return await _asyncio.to_thread(set_user_language, telegram_id, language)


async def reset_circuit_breaker(telegram_id: int = None, **kwargs) -> None:
    """Reset the in-memory circuit breaker for a user.

    This is a no-op at the DB level — the circuit breaker state lives
    in-memory in ``bot.engine.circuit_breaker``.
    """
    from bot.engine.circuit_breaker import circuit_breaker
    tg_id = telegram_id or kwargs.get('telegram_user_id', 0)
    circuit_breaker.reset_user(tg_id)
