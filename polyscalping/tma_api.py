"""
PolyHunter — Telegram Mini App API Blueprint
=============================================
Provides the /tma/api/* endpoints consumed by the React Mini App.

Auth: every request must carry ``Authorization: tma <initData>`` where
*initData* is the query-string produced by the Telegram WebApp client.
The server validates it via HMAC-SHA-256 using TELEGRAM_BOT_TOKEN.

All data access goes through ``_supabase_rest()`` from ``shared/supabase.py``,
filtered by the authenticated user's ``telegram_user_id``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import parse_qs, unquote

from flask import Blueprint, jsonify, request

# ---------------------------------------------------------------------------
# Imports from the shared layer
# ---------------------------------------------------------------------------
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.supabase import _supabase_rest  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
tma_blueprint = Blueprint('tma_api', __name__)

# ---------------------------------------------------------------------------
# Telegram initData validation (HMAC-SHA-256)
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')


def validate_init_data(init_data_raw: str, bot_token: str) -> dict | None:
    """Validate Telegram WebApp *initData* using HMAC-SHA-256.

    Returns the parsed data dict (including ``user`` as a parsed JSON
    object) on success, or ``None`` if validation fails.

    Reference:
        https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data_raw or not bot_token:
        return None

    try:
        parsed = parse_qs(init_data_raw, keep_blank_values=True)
        # Extract the hash sent by Telegram
        received_hash = parsed.pop('hash', [None])[0]
        if not received_hash:
            return None

        # Build the data-check-string: sorted key=value pairs joined by \n
        data_check_pairs = []
        for key in sorted(parsed.keys()):
            # parse_qs returns lists; take the first value
            val = parsed[key][0]
            data_check_pairs.append(f'{key}={val}')
        data_check_string = '\n'.join(data_check_pairs)

        # secret_key = HMAC-SHA-256("WebAppData", bot_token)
        secret_key = hmac.new(
            b'WebAppData',
            bot_token.encode('utf-8'),
            hashlib.sha256,
        ).digest()

        # calculated_hash = HMAC-SHA-256(secret_key, data_check_string)
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            logger.warning('[TMA AUTH] HMAC mismatch')
            return None

        # Parse the ``user`` JSON field
        result: dict = {}
        for key in parsed:
            val = parsed[key][0]
            result[key] = val
        if 'user' in result:
            try:
                result['user'] = json.loads(unquote(result['user']))
            except (json.JSONDecodeError, TypeError):
                pass

        return result

    except Exception as exc:
        logger.error('[TMA AUTH] Validation error: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------
def require_auth(fn):
    """Decorator that validates Telegram initData and injects
    ``telegram_user_id`` into ``request.tg_user_id``.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('tma '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401

        init_data_raw = auth_header[4:]  # strip "tma " prefix

        validated = validate_init_data(init_data_raw, TELEGRAM_BOT_TOKEN)
        if validated is None:
            return jsonify({'error': 'Invalid initData signature'}), 401

        user_info = validated.get('user')
        if not user_info or not isinstance(user_info, dict):
            return jsonify({'error': 'No user in initData'}), 401

        tg_user_id = user_info.get('id')
        if not tg_user_id:
            return jsonify({'error': 'No user id in initData'}), 401

        # Attach to request context for downstream handlers
        request.tg_user_id = int(tg_user_id)  # type: ignore[attr-defined]
        request.tg_user = user_info             # type: ignore[attr-defined]

        return fn(*args, **kwargs)

    return wrapper


# ============================================================================
# API Endpoints
# ============================================================================

# ---------- GET /tma/api/me ----------
@tma_blueprint.route('/tma/api/me', methods=['GET'])
@require_auth
def tma_get_me():
    """Return the authenticated user's profile.

    If the user does not exist yet in the ``users`` table an upsert is
    performed so that first-time Mini App visitors are auto-registered.
    """
    tg_user_id: int = request.tg_user_id  # type: ignore[attr-defined]
    tg_user: dict = request.tg_user        # type: ignore[attr-defined]

    # Try to fetch existing profile
    rows = _supabase_rest('users', 'GET', match={'telegram_user_id': tg_user_id})

    if rows and isinstance(rows, list) and len(rows) > 0:
        return jsonify(rows[0])

    # Auto-register (upsert)
    new_user = {
        'telegram_user_id': tg_user_id,
        'telegram_username': tg_user.get('username'),
        'language': tg_user.get('language_code', 'en'),
        'is_verified': False,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    result = _supabase_rest('users', 'POST', data=new_user)

    if result and isinstance(result, list) and len(result) > 0:
        return jsonify(result[0]), 201

    return jsonify(new_user), 201


# ---------- PATCH /tma/api/settings ----------
@tma_blueprint.route('/tma/api/settings', methods=['PATCH'])
@require_auth
def tma_update_settings():
    """Update the authenticated user's settings (language, etc.)."""
    tg_user_id: int = request.tg_user_id  # type: ignore[attr-defined]
    body = request.get_json(silent=True) or {}

    allowed_fields = {'language'}
    update_data = {k: v for k, v in body.items() if k in allowed_fields}

    if not update_data:
        return jsonify({'error': 'No valid fields to update'}), 400

    result = _supabase_rest(
        'users', 'PATCH',
        data=update_data,
        match={'telegram_user_id': tg_user_id},
    )

    if result and isinstance(result, list) and len(result) > 0:
        return jsonify(result[0])

    return jsonify({'error': 'Update failed'}), 500


# ---------- GET /tma/api/configs ----------
@tma_blueprint.route('/tma/api/configs', methods=['GET'])
@require_auth
def tma_list_configs():
    """List all copy-trade configs belonging to the authenticated user."""
    tg_user_id: int = request.tg_user_id  # type: ignore[attr-defined]

    rows = _supabase_rest(
        'copy_trade_configs', 'GET',
        match={'telegram_user_id': tg_user_id},
    )

    return jsonify(rows if isinstance(rows, list) else [])


# ---------- POST /tma/api/configs ----------
@tma_blueprint.route('/tma/api/configs', methods=['POST'])
@require_auth
def tma_create_config():
    """Create a new copy-trade config for the authenticated user."""
    tg_user_id: int = request.tg_user_id  # type: ignore[attr-defined]
    body = request.get_json(silent=True) or {}

    # Required field
    if not body.get('target_wallet'):
        return jsonify({'error': 'target_wallet is required'}), 400

    now = datetime.now(timezone.utc).isoformat()

    config = {
        'id': str(uuid.uuid4()),
        'telegram_user_id': tg_user_id,
        'target_wallet': body.get('target_wallet', ''),
        'tag': body.get('tag', ''),
        'is_active': body.get('is_active', True),
        'copy_mode': body.get('copy_mode', 'percentage'),
        'copy_percentage': body.get('copy_percentage', 100),
        'copy_fixed_amount': body.get('copy_fixed_amount'),
        'buy_order_type': body.get('buy_order_type', 'market'),
        'buy_slippage_pct': body.get('buy_slippage_pct', 5),
        'copy_buy': body.get('copy_buy', True),
        'sell_order_type': body.get('sell_order_type', 'market'),
        'sell_slippage_pct': body.get('sell_slippage_pct', 5),
        'copy_sell': body.get('copy_sell', True),
        'tp_mode': body.get('tp_mode', 'percentage'),
        'tp_value': body.get('tp_value'),
        'sl_mode': body.get('sl_mode', 'percentage'),
        'sl_value': body.get('sl_value'),
        'below_min_buy_at_min': body.get('below_min_buy_at_min', True),
        'ignore_trades_under_usd': body.get('ignore_trades_under_usd', 0),
        'min_price': body.get('min_price'),
        'max_price': body.get('max_price'),
        'total_spend_limit_usd': body.get('total_spend_limit_usd'),
        'min_per_trade_usd': body.get('min_per_trade_usd'),
        'max_per_trade_usd': body.get('max_per_trade_usd'),
        'max_per_yes_no_usd': body.get('max_per_yes_no_usd'),
        'max_per_market_usd': body.get('max_per_market_usd'),
        'max_markets': body.get('max_markets'),
        'limit_price_offset': body.get('limit_price_offset', 0),
        'limit_order_duration': body.get('limit_order_duration', 90),
        'total_spent_usd': 0,
        'markets_entered': 0,
        'created_at': now,
        'updated_at': now,
    }

    result = _supabase_rest('copy_trade_configs', 'POST', data=config)

    if result and isinstance(result, list) and len(result) > 0:
        return jsonify(result[0]), 201

    return jsonify(config), 201


# ---------- PATCH /tma/api/configs/<config_id> ----------
@tma_blueprint.route('/tma/api/configs/<config_id>', methods=['PATCH'])
@require_auth
def tma_update_config(config_id: str):
    """Update an existing copy-trade config (only if it belongs to the user)."""
    tg_user_id: int = request.tg_user_id  # type: ignore[attr-defined]
    body = request.get_json(silent=True) or {}

    # Verify ownership
    existing = _supabase_rest(
        'copy_trade_configs', 'GET',
        match={'id': config_id, 'telegram_user_id': tg_user_id},
    )

    if not existing or not isinstance(existing, list) or len(existing) == 0:
        return jsonify({'error': 'Config not found'}), 404

    # Only allow updating known fields
    allowed_fields = {
        'target_wallet', 'tag', 'is_active', 'copy_mode', 'copy_percentage',
        'copy_fixed_amount', 'buy_order_type', 'buy_slippage_pct', 'copy_buy',
        'sell_order_type', 'sell_slippage_pct', 'copy_sell', 'tp_mode',
        'tp_value', 'sl_mode', 'sl_value', 'below_min_buy_at_min',
        'ignore_trades_under_usd', 'min_price', 'max_price',
        'total_spend_limit_usd', 'min_per_trade_usd', 'max_per_trade_usd',
        'max_per_yes_no_usd', 'max_per_market_usd', 'max_markets',
        'limit_price_offset', 'limit_order_duration',
    }

    update_data = {k: v for k, v in body.items() if k in allowed_fields}
    if not update_data:
        return jsonify({'error': 'No valid fields to update'}), 400

    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()

    result = _supabase_rest(
        'copy_trade_configs', 'PATCH',
        data=update_data,
        match={'id': config_id, 'telegram_user_id': tg_user_id},
    )

    if result and isinstance(result, list) and len(result) > 0:
        return jsonify(result[0])

    return jsonify({'error': 'Update failed'}), 500


# ---------- GET /tma/api/positions ----------
@tma_blueprint.route('/tma/api/positions', methods=['GET'])
@require_auth
def tma_list_positions():
    """List all open positions for configs belonging to the authenticated user.

    We first fetch the user's config IDs, then query positions whose
    ``config_id`` is in that set and ``is_open`` is true.
    """
    tg_user_id: int = request.tg_user_id  # type: ignore[attr-defined]

    # Get user's config ids
    configs = _supabase_rest(
        'copy_trade_configs', 'GET',
        match={'telegram_user_id': tg_user_id},
        select='id',
    )

    if not configs or not isinstance(configs, list) or len(configs) == 0:
        return jsonify([])

    config_ids = [c['id'] for c in configs]

    # Fetch open positions for all user configs
    # Supabase REST supports `in` filter via special syntax
    all_positions = []
    for cid in config_ids:
        rows = _supabase_rest(
            'positions', 'GET',
            match={'config_id': cid, 'is_open': 'true'},
        )
        if rows and isinstance(rows, list):
            all_positions.extend(rows)

    return jsonify(all_positions)


# ---------- GET /tma/api/history ----------
@tma_blueprint.route('/tma/api/history', methods=['GET'])
@require_auth
def tma_list_history():
    """Return paginated trade log for the authenticated user.

    Query params: ``page`` (default 1), ``limit`` (default 20, max 100).
    """
    tg_user_id: int = request.tg_user_id  # type: ignore[attr-defined]

    page = max(1, request.args.get('page', 1, type=int))
    limit = min(100, max(1, request.args.get('limit', 20, type=int)))

    rows = _supabase_rest(
        'trade_log', 'GET',
        match={'telegram_user_id': tg_user_id},
    )

    if not rows or not isinstance(rows, list):
        return jsonify([])

    # Sort by created_at descending and paginate
    rows.sort(key=lambda r: r.get('created_at', ''), reverse=True)
    start = (page - 1) * limit
    end = start + limit

    return jsonify(rows[start:end])
