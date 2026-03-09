"""
PolyHunter Etherscan / Polygonscan Query Helper
Queries the Etherscan v2 API for ERC-20 token transfers on Polygon.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from shared.constants import POLYGONSCAN_API, POLYGON_CHAIN_ID

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# API key -- prefer POLYGONSCAN_API_KEY, fall back to ETHERSCAN_API_KEY
_API_KEY = os.getenv('POLYGONSCAN_API_KEY', '') or os.getenv('ETHERSCAN_API_KEY', '')


def fetch_wallet_transfers(
    address: str,
    contract_address: str = None,
    limit: int = 50,
) -> list[dict]:
    """Fetch ERC-20 token transfers for *address* from Etherscan v2 API.

    Args:
        address:          Wallet address to query.
        contract_address: Optional ERC-20 contract address to filter by.
        limit:            Maximum number of results (capped at 10 000 by API).

    Returns:
        List of dicts with keys:
            tx_hash, from_addr, to_addr, value_usd, timestamp, token_name
    """
    if not _API_KEY:
        logger.error('[ETHERSCAN] No API key configured '
                     '(set POLYGONSCAN_API_KEY or ETHERSCAN_API_KEY)')
        return []

    params = {
        'chainid': POLYGON_CHAIN_ID,
        'module': 'account',
        'action': 'tokentx',
        'address': address,
        'page': 1,
        'offset': min(limit, 10000),
        'sort': 'desc',
        'apikey': _API_KEY,
    }
    if contract_address:
        params['contractaddress'] = contract_address

    try:
        resp = requests.get(POLYGONSCAN_API, params=params, timeout=15)
        resp.raise_for_status()
        body = resp.json()

        if body.get('status') != '1' or not body.get('result'):
            msg = body.get('message', 'Unknown error')
            if msg != 'No transactions found':
                logger.warning('[ETHERSCAN] API returned status=%s message=%s',
                               body.get('status'), msg)
            return []

        transfers = []
        for tx in body['result']:
            decimals = int(tx.get('tokenDecimal', 6))
            raw_value = int(tx.get('value', 0))
            value = raw_value / (10 ** decimals) if decimals > 0 else raw_value

            ts_unix = int(tx.get('timeStamp', 0))
            ts_dt = datetime.fromtimestamp(ts_unix, tz=timezone.utc) if ts_unix else None

            transfers.append({
                'tx_hash': tx.get('hash', ''),
                'from_addr': (tx.get('from') or '').lower(),
                'to_addr': (tx.get('to') or '').lower(),
                'value_usd': round(value, 6),
                'timestamp': ts_dt.isoformat() if ts_dt else None,
                'token_name': tx.get('tokenName', ''),
            })

        return transfers[:limit]

    except requests.RequestException as exc:
        logger.error('[ETHERSCAN] HTTP error fetching transfers for %s: %s',
                     address, exc)
        return []
    except (KeyError, ValueError, TypeError) as exc:
        logger.error('[ETHERSCAN] Parse error for %s: %s', address, exc)
        return []


def detect_trade_direction(tx: dict, exchange_proxy: str) -> str | None:
    """Determine whether a transfer represents a buy or sell on Polymarket.

    Args:
        tx:             A transfer dict (as returned by ``fetch_wallet_transfers``).
        exchange_proxy: The exchange proxy contract address (lower-cased for comparison).

    Returns:
        ``'buy'``  if tokens were sent **to** the exchange proxy (user is buying),
        ``'sell'`` if tokens came **from** the exchange proxy (user is selling),
        ``None``   if the exchange proxy is not involved in this transfer.
    """
    proxy = exchange_proxy.lower()
    to_addr = (tx.get('to_addr') or '').lower()
    from_addr = (tx.get('from_addr') or '').lower()

    if to_addr == proxy:
        return 'buy'
    if from_addr == proxy:
        return 'sell'
    return None
