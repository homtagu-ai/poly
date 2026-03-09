"""
PolyHunter Shared Supabase REST Helper
Extracted from server.py with cache bug fix (.total_seconds() instead of .seconds).
No Supabase SDK dependency -- uses raw REST API via requests.
"""
import os
import logging
from datetime import datetime

import requests as _requests
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supabase credentials
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
_cache: dict = {}
_cache_ttl: dict = {}


def get_cached(key: str, ttl: int = 60):
    """Return cached value if it exists and has not expired.

    Args:
        key: Cache key.
        ttl: Time-to-live in seconds.

    Returns:
        The cached value, or ``None`` if missing / expired.
    """
    if key in _cache and key in _cache_ttl:
        elapsed = (datetime.now() - _cache_ttl[key]).total_seconds()
        if elapsed < ttl:
            return _cache[key]
    return None


def set_cached(key: str, value):
    """Store *value* under *key* with the current timestamp."""
    _cache[key] = value
    _cache_ttl[key] = datetime.now()


# ---------------------------------------------------------------------------
# Supabase REST helper
# ---------------------------------------------------------------------------
def _supabase_rest(table: str, method: str = 'GET', data=None,
                   match: dict = None, select: str = None):
    """Direct Supabase REST API call using requests (no SDK dependency).

    Args:
        table:  Supabase table name.
        method: HTTP verb -- ``GET``, ``POST``, or ``PATCH``.
        data:   JSON-serialisable body for POST / PATCH.
        match:  Column equality filters, e.g. ``{"id": "abc"}``.
        select: Columns to return, e.g. ``"id,name"``.

    Returns:
        Parsed JSON response (list or dict), or ``None`` on error.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.error('[SUPABASE REST] URL or service key not configured')
        return None

    url = f'{SUPABASE_URL}/rest/v1/{table}'
    headers = {
        'apikey': SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }
    params = {}
    if match:
        for k, v in match.items():
            params[k] = f'eq.{v}'
    if select:
        params['select'] = select

    try:
        if method == 'POST':
            headers['Prefer'] = 'resolution=merge-duplicates,return=representation'
            resp = _requests.post(url, json=data, headers=headers,
                                  params=params, timeout=10)
        elif method == 'PATCH':
            resp = _requests.patch(url, json=data, headers=headers,
                                   params=params, timeout=10)
        elif method == 'GET':
            resp = _requests.get(url, headers=headers, params=params,
                                 timeout=10)
        elif method == 'DELETE':
            resp = _requests.delete(url, headers=headers, params=params,
                                    timeout=10)
        else:
            logger.warning('[SUPABASE REST] Unsupported method: %s', method)
            return None

        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error('[SUPABASE REST] %s %s failed: %s', method, table, exc)
        return None
