"""
PolyScalping - Unified Dashboard Server
Combines all features: Event Analyzer, ROI Calculator, Hot Markets, Whale Tracking
Now with FULL comprehensive analysis pipeline using all APIs
"""
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import sys
import os
import threading
import time
import json
import hashlib
import requests
import re
import uuid
import numpy as np
from scipy.stats import norm
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=True)

# Try to import anthropic for Claude reports
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# Try to import yfinance for stock data
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

app = Flask(__name__)

# Production vs development config
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"
app.config['TEMPLATES_AUTO_RELOAD'] = not IS_PRODUCTION

# CORS — restrict origins in production
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "")
if _allowed_origins:
    CORS(app, origins=[o.strip() for o in _allowed_origins.split(",") if o.strip()])
else:
    CORS(app)

# Supabase config — injected into all templates
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

@app.context_processor
def inject_supabase():
    return {
        'SUPABASE_URL': SUPABASE_URL,
        'SUPABASE_ANON_KEY': SUPABASE_ANON_KEY,
    }

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=4)

# ============================================================================
# CONFIGURATION
# ============================================================================
GAMMA_API = os.getenv("POLYMARKET_API_BASE", "https://gamma-api.polymarket.com")
KALSHI_API = os.getenv("KALSHI_API_BASE", "https://api.elections.kalshi.com")
DERIBIT_API = os.getenv("DERIBIT_API_BASE", "https://www.deribit.com/api/v2")
POLYGONSCAN_API = "https://api.etherscan.io/v2/api"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Contract addresses
EXCHANGE_PROXY = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC_E_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# API Keys
POLYGONSCAN_KEY = os.getenv("POLYGONSCAN_API_KEY", "")
ETHERSCAN_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Job storage for async analysis - FILE-BASED for multi-worker compatibility
import tempfile
JOBS_DIR = os.path.join(tempfile.gettempdir(), "polysnap_jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

def _job_path(job_id):
    """Get file path for a job."""
    return os.path.join(JOBS_DIR, f"{job_id}.json")

def _save_job(job_id, job_data):
    """Save job data to file (works across multiple workers/processes)."""
    path = _job_path(job_id)
    # Write to temp file then rename for atomicity
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(job_data, f, default=str)
    os.replace(tmp_path, path)

def _load_job(job_id):
    """Load job data from file. Returns None if not found."""
    path = _job_path(job_id)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def _update_job(job_id, updates):
    """Update specific fields in a job."""
    job = _load_job(job_id)
    if job:
        job.update(updates)
        _save_job(job_id, job)
    return job

# Cache
_cache = {}
_cache_ttl = {}

def get_cached(key, ttl=60):
    """Get cached value if not expired."""
    if key in _cache and key in _cache_ttl:
        if (datetime.now() - _cache_ttl[key]).seconds < ttl:
            return _cache[key]
    return None

def set_cached(key, value):
    """Set cache value."""
    _cache[key] = value
    _cache_ttl[key] = datetime.now()

# ============================================================================
# ANALYSIS PIPELINE STEPS
# ============================================================================
PIPELINE_STEPS = [
    "Fetching Polymarket event data...",
    "Fetching stock/asset data...",
    "Running probability models...",
    "Fetching sports odds (if applicable)...",
    "Searching Kalshi for cross-platform opportunities...",
    "Tracking whale wallets on Polygon...",
    "Fetching CLOB orderbook depth...",
    "Calculating Kelly sizing & strategy...",
    "Generating AI analysis report...",
    "Finalizing results..."
]

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def generate_avatar_url(address):
    """Generate avatar URL for wallet address."""
    seed = (address or "unknown").lower()
    return f"https://api.dicebear.com/7.x/identicon/svg?seed={seed}&backgroundColor=1a1f2e"

def format_usd(n):
    """Format number as USD."""
    if n is None:
        return "$0"
    if n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n/1_000:.1f}K"
    return f"${n:.2f}"

def extract_ticker(event_title):
    """Extract stock ticker from event title."""
    match = re.search(r"\(([A-Z]{1,5})\)", event_title)
    return match.group(1) if match else None

def is_sports_event(title):
    """Check if event is sports-related."""
    sports_keywords = ['vs', 'nba', 'nfl', 'mlb', 'nhl', 'ufc', 'game', 'match',
                      'bulls', 'lakers', 'celtics', 'warriors', 'pacers', 'cavaliers',
                      'hawks', 'heat', 'knicks', 'nets', 'sixers', 'raptors',
                      'super bowl', 'championship', 'playoff', 'finals']
    title_lower = title.lower()
    return any(kw in title_lower for kw in sports_keywords)

# ============================================================================
# BLACK-SCHOLES PROBABILITY MODEL
# ============================================================================
def black_scholes_prob(spot, strike, iv, days_to_expiry, direction="above", risk_free=0.045):
    """Calculate probability via Black-Scholes."""
    if spot <= 0 or strike <= 0 or iv <= 0:
        return {
            "spot": spot, "strike": strike, "iv": iv,
            "days_to_expiry": days_to_expiry, "true_probability": 0.5,
            "model": "Invalid inputs"
        }

    T = max(days_to_expiry / 365.0, 0.001)
    d1 = (np.log(spot / strike) + (risk_free + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
    d2 = d1 - iv * np.sqrt(T)

    prob_above = float(norm.cdf(d2))
    prob_below = 1.0 - prob_above
    delta = float(norm.cdf(d1))

    return {
        "spot": spot,
        "strike": strike,
        "iv": iv,
        "days_to_expiry": days_to_expiry,
        "T_years": T,
        "d1": round(d1, 4),
        "d2": round(d2, 4),
        "prob_above": round(prob_above, 6),
        "prob_below": round(prob_below, 6),
        "delta": round(delta, 4),
        "true_probability": round(prob_above if direction == "above" else prob_below, 6),
        "model": "Black-Scholes",
    }

# ============================================================================
# ARBITRAGE DETECTION
# ============================================================================
def detect_arbitrage(poly_price, true_prob):
    """Detect mispricing between market price and true probability - AGGRESSIVE VERSION."""
    edge = abs(poly_price - true_prob)
    edge_pct = (edge / true_prob * 100) if true_prob > 0 else 0

    # AGGRESSIVE thresholds - lowered from 0.15/0.05 to 0.08/0.02
    if edge >= 0.08:  # Was 0.15 - now flags opportunities with 8%+ edge
        verdict, color = "ARBITRAGE", "purple"
    elif edge < 0.02:  # Was 0.05 - only truly flat markets are "FAIR"
        verdict, color = "FAIR", "yellow"
    elif poly_price < true_prob:
        verdict, color = "CHEAP", "green"
    else:
        verdict, color = "EXPENSIVE", "red"

    # AGGRESSIVE: Always recommend a side unless edge is tiny
    if edge < 0.01:
        rec = "PASS"
        direction = "fair"
    elif poly_price < true_prob:
        rec = "BUY YES"
        direction = "underpriced"
    else:
        rec = "BUY NO"
        direction = "overpriced"

    return {
        "verdict": verdict,
        "color": color,
        "recommendation": rec,
        "edge_absolute": round(edge, 4),
        "edge_percent": round(edge_pct, 2),
        "polymarket_yes": poly_price,
        "true_probability": true_prob,
        "mispricing": direction,
    }

# ============================================================================
# KELLY CRITERION SIZING
# ============================================================================
def kelly_sizing(bankroll, true_prob, poly_price):
    """Calculate position sizing — REALISTIC RETURNS philosophy.

    Core principle: Bet BIG on high-probability outcomes for achievable ROI (5-30%),
    not small bets on longshots hoping for 1000%+ returns.

    The higher the win probability, the bigger the position (because you're more
    likely to actually collect). Lower probability = smaller position (speculative).
    """
    results = {}
    for side in ["YES", "NO"]:
        if side == "YES":
            price = poly_price
            p = true_prob
        else:
            price = 1.0 - poly_price
            p = 1.0 - true_prob

        if price <= 0 or price >= 1 or p <= 0:
            results[side] = {"kelly_pct": 0, "bet_amount": 0, "ev": 0, "reason": "Invalid",
                             "position_pct": 0, "confidence": "none"}
            continue

        decimal_odds = 1.0 / price
        b = decimal_odds - 1.0
        q = 1.0 - p
        full_kelly = (b * p - q) / b if b > 0 else 0
        full_kelly = max(0, min(full_kelly, 0.35))
        ev = p * (decimal_odds - 1) - q
        roi_if_win = (1.0 / price) - 1.0
        edge = abs(poly_price - true_prob)

        # ============================================================
        # REALISTIC POSITION SIZING
        # Philosophy: bet BIG on likely outcomes, small on longshots
        # Win probability drives position size — you want to COLLECT
        # ============================================================

        if full_kelly > 0.001:
            # Kelly has a real signal — use it (aggressive 75%)
            position_pct = full_kelly * 0.75
            confidence = "high" if position_pct >= 0.10 else "medium"
        else:
            # No Kelly edge — size by win probability
            # Higher probability = bigger position = more realistic bet
            if price >= 0.80:
                # Strong favorite (80%+): BIG position, small but reliable ROI (5-25%)
                position_pct = 0.20  # 20% of bankroll
                confidence = "high"
            elif price >= 0.65:
                # Solid favorite (65-80%): large position, moderate ROI (25-54%)
                position_pct = 0.15  # 15%
                confidence = "high"
            elif price >= 0.50:
                # Slight favorite (50-65%): good position, decent ROI (54-100%)
                position_pct = 0.12  # 12%
                confidence = "medium"
            elif price >= 0.30:
                # Competitive underdog (30-50%): moderate position
                position_pct = 0.08  # 8%
                confidence = "medium"
            elif price >= 0.10:
                # Underdog (10-30%): smaller position, speculative
                position_pct = 0.05  # 5%
                confidence = "low"
            else:
                # Longshot (<10%): tiny position, lottery ticket
                position_pct = 0.02  # 2%
                confidence = "low"

            # Edge boosts (if model detects mispricing)
            if edge >= 0.05:
                position_pct = min(position_pct * 1.3, 0.30)
                if confidence == "low":
                    confidence = "medium"
            if edge >= 0.10:
                position_pct = min(position_pct * 1.5, 0.35)
                confidence = "high"

        # Apply to bankroll
        bet = round(bankroll * position_pct, 2)
        # Minimum $5, maximum 35% of bankroll
        bet = max(5.0, min(bet, bankroll * 0.35))
        position_pct = bet / bankroll if bankroll > 0 else 0

        results[side] = {
            "price": round(price, 4),
            "decimal_odds": round(decimal_odds, 2),
            "true_prob": round(p, 4),
            "full_kelly_pct": round(full_kelly * 100, 2),
            "aggressive_kelly_pct": round(position_pct * 100, 2),
            "bet_amount": round(bet, 2),
            "ev_per_dollar": round(ev, 4),
            "roi_if_win": round(roi_if_win * 100, 2),
            "position_pct": round(position_pct * 100, 2),
            "confidence": confidence,
        }

    return results

# ============================================================================
# ROI CALCULATOR
# ============================================================================
def polyscalping_roi(buy_price, sell_price, num_shares):
    """Calculate ROI matching PolyScalping.org logic."""
    buy_cost = buy_price * num_shares
    sell_revenue = sell_price * num_shares
    net_profit = sell_revenue - buy_cost
    roi = (net_profit / buy_cost * 100) if buy_cost > 0 else 0

    return {
        "buy_price": buy_price,
        "sell_price": sell_price,
        "num_shares": num_shares,
        "buy_cost": round(buy_cost, 2),
        "sell_revenue": round(sell_revenue, 2),
        "net_profit": round(net_profit, 2),
        "roi_percent": round(roi, 2),
    }

# ============================================================================
# POLYMARKET DATA FETCHER
# ============================================================================
def fetch_polymarket_event(slug):
    """Fetch full event + all markets from Gamma API."""
    url = f"{GAMMA_API}/events?slug={slug}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data:
            return None

        event = data[0]
        markets = event.get("markets", [])

        parsed_markets = []
        for m in markets:
            q = m.get("question", "")
            strike_match = re.search(r"\$([0-9,.]+)", q)
            strike = float(strike_match.group(1).replace(",", "")) if strike_match else 0

            prices_raw = m.get("outcomePrices", "[]")
            try:
                p = json.loads(prices_raw)
                yes_price = float(p[0])
                no_price = float(p[1])
            except:
                yes_price = 0
                no_price = 0

            parsed_markets.append({
                "id": m.get("id", ""),
                "question": q,
                "strike": strike,
                "yes_price": yes_price,
                "no_price": no_price,
                "volume": float(m.get("volume", 0) or 0),
                "liquidity": float(m.get("liquidity", 0) or 0),
                "spread": float(m.get("spread", 0) or 0),
                "bestBid": m.get("bestBid"),
                "bestAsk": m.get("bestAsk"),
                "lastTradePrice": m.get("lastTradePrice"),
                "oneDayPriceChange": m.get("oneDayPriceChange"),
                "slug": m.get("slug", ""),
                "conditionId": m.get("conditionId", ""),
                "clobTokenIds": m.get("clobTokenIds", ""),
                "endDate": m.get("endDate", ""),
            })

        parsed_markets.sort(key=lambda x: x["strike"])

        return {
            "event_title": event.get("title", ""),
            "event_description": event.get("description", ""),
            "event_volume": event.get("volume", 0),
            "event_liquidity": event.get("liquidity", 0),
            "event_end": event.get("endDate", ""),
            "event_active": event.get("active", False),
            "event_closed": event.get("closed", False),
            "volume_24h": event.get("volume24hr", 0),
            "image": event.get("image", ""),
            "markets": parsed_markets,
        }
    except Exception as e:
        print(f"Error fetching event: {e}")
        return None

# ============================================================================
# STOCK DATA FETCHER (yfinance)
# ============================================================================
def fetch_stock_data(ticker):
    """Fetch stock data via yfinance."""
    if not YFINANCE_AVAILABLE:
        return None

    try:
        t = yf.Ticker(ticker)
        info = t.info
        spot = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")

        if not spot:
            return None

        expirations = t.options
        iv = 0.30
        options_data = {}

        if expirations and spot:
            try:
                chain = t.option_chain(expirations[0])
                calls = chain.calls
                atm_strike = min(calls["strike"], key=lambda x: abs(x - spot))
                atm = calls[calls["strike"] == atm_strike].iloc[0]
                iv = atm["impliedVolatility"] if atm["impliedVolatility"] > 0.001 else 0.30
                options_data = {
                    "nearest_expiry": expirations[0],
                    "atm_strike": float(atm_strike),
                    "atm_iv": float(iv),
                }
            except:
                pass

        hist = t.history(period="5d")
        recent = []
        for idx, row in hist.iterrows():
            recent.append({
                "date": str(idx.date()),
                "close": round(row["Close"], 2),
                "volume": int(row["Volume"]),
            })

        return {
            "ticker": ticker,
            "spot_price": spot,
            "implied_volatility": iv,
            "options": options_data,
            "recent_history": recent,
            "market_cap": info.get("marketCap"),
            "day_high": info.get("dayHigh"),
            "day_low": info.get("dayLow"),
            "previous_close": info.get("previousClose"),
        }
    except Exception as e:
        print(f"Error fetching stock data: {e}")
        return None

# ============================================================================
# SPORTS ODDS FETCHER (The Odds API)
# ============================================================================
def fetch_sports_odds(event_title):
    """Fetch sports odds from The Odds API."""
    if not ODDS_API_KEY:
        return {"error": "No Odds API key configured", "odds": []}

    try:
        # Get available sports
        sports_url = f"{ODDS_API_BASE}/sports?apiKey={ODDS_API_KEY}"
        r = requests.get(sports_url, timeout=10)
        if r.status_code != 200:
            return {"error": "Failed to fetch sports", "odds": []}

        sports = r.json()

        # Try to match event to a sport
        title_lower = event_title.lower()
        matched_sport = None

        for sport in sports:
            if sport.get("key", "").lower() in title_lower or sport.get("title", "").lower() in title_lower:
                matched_sport = sport.get("key")
                break

        # Default to basketball if no match but contains NBA keywords
        if not matched_sport:
            if any(kw in title_lower for kw in ['bulls', 'lakers', 'celtics', 'warriors', 'nba']):
                matched_sport = "basketball_nba"
            elif any(kw in title_lower for kw in ['nfl', 'chiefs', 'eagles', 'super bowl']):
                matched_sport = "americanfootball_nfl"

        if not matched_sport:
            return {"error": "Could not match event to sport", "odds": [], "sports_available": [s["key"] for s in sports[:10]]}

        # Fetch odds for the sport
        odds_url = f"{ODDS_API_BASE}/sports/{matched_sport}/odds?apiKey={ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals"
        r = requests.get(odds_url, timeout=10)
        if r.status_code != 200:
            return {"error": f"Failed to fetch odds for {matched_sport}", "odds": []}

        odds_data = r.json()

        # Try to find matching game
        matching_games = []
        for game in odds_data:
            home = game.get("home_team", "").lower()
            away = game.get("away_team", "").lower()
            if home in title_lower or away in title_lower:
                matching_games.append({
                    "id": game.get("id"),
                    "home_team": game.get("home_team"),
                    "away_team": game.get("away_team"),
                    "commence_time": game.get("commence_time"),
                    "bookmakers": game.get("bookmakers", [])[:3],  # Top 3 bookmakers
                })

        return {
            "sport": matched_sport,
            "matching_games": matching_games,
            "total_games_found": len(odds_data),
        }
    except Exception as e:
        return {"error": str(e), "odds": []}

# ============================================================================
# KALSHI CROSS-PLATFORM COMPARISON
# ============================================================================
def fetch_kalshi_markets(search_keywords):
    """Search Kalshi for similar markets."""
    results = {
        "platform": "Kalshi",
        "matching_markets_found": False,
        "matching_markets": [],
        "related_events": [],
        "conclusion": "",
    }

    try:
        base = f"{KALSHI_API}/trade-api/v2"
        url = f"{base}/events?status=open&with_nested_markets=true&limit=100"
        r = requests.get(url, timeout=10)

        if r.status_code == 200:
            data = r.json()
            events = data.get("events", [])
            keywords_lower = [k.lower() for k in search_keywords]

            for e in events:
                title = (e.get("title", "") or "").lower()
                ticker = (e.get("event_ticker", "") or "").lower()
                if keywords_lower and any(kw in title or kw in ticker for kw in keywords_lower):
                    results["related_events"].append({
                        "event_ticker": e.get("event_ticker", ""),
                        "title": e.get("title", ""),
                        "category": e.get("category", ""),
                    })
                    results["matching_markets_found"] = True
                    results["matching_markets"].append(e)

        if not results["matching_markets_found"]:
            results["conclusion"] = "No matching markets found on Kalshi. Polymarket is the only venue."
        else:
            results["conclusion"] = f"Found {len(results['matching_markets'])} related markets on Kalshi."
    except Exception as e:
        results["error"] = str(e)

    return results

# ============================================================================
# WHALE WALLET TRACKING
# ============================================================================
def fetch_whale_activity():
    """Track whale wallets on Polymarket Exchange via Etherscan v2."""
    api_key = POLYGONSCAN_KEY or ETHERSCAN_KEY
    if not api_key:
        return {"error": "No Polygonscan/Etherscan API key configured", "whale_wallets": []}

    url = (
        f"https://api.etherscan.io/v2/api?chainid=137"
        f"&module=account&action=tokentx"
        f"&address={EXCHANGE_PROXY}"
        f"&contractaddress={USDC_E_ADDRESS}"
        f"&page=1&offset=200&sort=desc"
        f"&apikey={api_key}"
    )

    result = {
        "source": "Etherscan v2 (Polygon)",
        "contract_monitored": EXCHANGE_PROXY,
        "wallets_analyzed": 0,
        "whale_count": 0,
        "total_volume_tracked": 0,
        "net_flow_direction": "",
        "whale_wallets": [],
        "summary": {},
    }

    try:
        r = requests.get(url, timeout=15)
        data = r.json()

        if not (data.get("result") and isinstance(data["result"], list)):
            result["error"] = data.get("message", "Unknown error")
            return result

        txs = data["result"]
        wallet_activity = {}

        for tx in txs:
            value = int(tx.get("value", "0"))
            decimals = int(tx.get("tokenDecimal", "6"))
            usd_value = value / (10 ** decimals)
            from_addr = tx.get("from", "")
            to_addr = tx.get("to", "")

            if to_addr.lower() == EXCHANGE_PROXY.lower():
                wallet = from_addr
                action = "deposit"
            else:
                wallet = to_addr
                action = "withdrawal"

            if wallet not in wallet_activity:
                wallet_activity[wallet] = {
                    "total_volume": 0, "tx_count": 0,
                    "deposits": 0, "withdrawals": 0, "max_tx": 0,
                }

            wallet_activity[wallet]["total_volume"] += usd_value
            wallet_activity[wallet]["tx_count"] += 1
            wallet_activity[wallet]["max_tx"] = max(wallet_activity[wallet]["max_tx"], usd_value)
            if action == "deposit":
                wallet_activity[wallet]["deposits"] += usd_value
            else:
                wallet_activity[wallet]["withdrawals"] += usd_value

        exclude = {EXCHANGE_PROXY.lower(), CTF_ADDRESS.lower()}
        sorted_wallets = sorted(
            [(w, v) for w, v in wallet_activity.items() if w.lower() not in exclude],
            key=lambda x: x[1]["total_volume"],
            reverse=True
        )

        total_deposits = 0
        total_withdrawals = 0
        whale_list = []

        for wallet, info in sorted_wallets[:20]:
            is_whale = info["total_volume"] > 1000
            direction = "NET BUYER" if info["deposits"] > info["withdrawals"] else "NET SELLER"
            total_deposits += info["deposits"]
            total_withdrawals += info["withdrawals"]

            whale_list.append({
                "address": wallet,
                "total_volume_usd": round(info["total_volume"], 2),
                "tx_count": info["tx_count"],
                "max_single_tx_usd": round(info["max_tx"], 2),
                "deposits_usd": round(info["deposits"], 2),
                "withdrawals_usd": round(info["withdrawals"], 2),
                "net_direction": direction,
                "is_whale": is_whale,
                "whale_tag": "WHALE" if is_whale else "fish",
            })
            if is_whale:
                result["whale_count"] += 1

        result["wallets_analyzed"] = len(sorted_wallets)
        result["total_volume_tracked"] = round(sum(v["total_volume"] for _, v in sorted_wallets), 2)
        result["net_flow_direction"] = "NET INFLOW (Bullish)" if total_deposits > total_withdrawals else "NET OUTFLOW (Bearish)"
        result["whale_wallets"] = whale_list
        result["summary"] = {
            "total_deposits": round(total_deposits, 2),
            "total_withdrawals": round(total_withdrawals, 2),
            "net_flow": round(total_deposits - total_withdrawals, 2),
            "whale_count": result["whale_count"],
            "fish_count": len(whale_list) - result["whale_count"],
        }
    except Exception as ex:
        result["error"] = str(ex)

    return result

# ============================================================================
# ORDERBOOK DEPTH
# ============================================================================
def fetch_orderbook_depth(markets):
    """Fetch CLOB orderbook data for all markets."""
    all_books = {}

    for m in markets:
        strike = m.get("strike", 0)
        market_key = m.get("slug") or m.get("id") or (f"${int(strike)}" if strike > 0 else m.get("question", "unknown")[:30])
        clob_raw = m.get("clobTokenIds", "[]")
        try:
            token_ids = json.loads(clob_raw)
        except:
            continue

        if len(token_ids) < 2:
            continue

        book = {"question": m.get("question", ""), "strike": strike}
        for idx, side in enumerate(["yes", "no"]):
            token_id = token_ids[idx]
            try:
                url = f"https://clob.polymarket.com/book?token_id={token_id}"
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    bids = data.get("bids", [])
                    asks = data.get("asks", [])
                    book[side] = {
                        "best_bid": float(bids[0]["price"]) if bids else 0,
                        "best_ask": float(asks[0]["price"]) if asks else 0,
                        "num_bids": len(bids),
                        "num_asks": len(asks),
                        "total_bid_size": round(sum(float(b.get("size", 0)) for b in bids), 2),
                        "total_ask_size": round(sum(float(a.get("size", 0)) for a in asks), 2),
                        "bid_depth_usd": round(sum(float(b["price"]) * float(b["size"]) for b in bids), 2),
                        "ask_depth_usd": round(sum(float(a["price"]) * float(a["size"]) for a in asks), 2),
                        "top_3_bids": [{"price": b["price"], "size": b["size"]} for b in bids[:3]],
                        "top_3_asks": [{"price": a["price"], "size": a["size"]} for a in asks[:3]],
                    }
            except:
                book[side] = {"error": "Failed to fetch"}

        all_books[market_key] = book

    return all_books

# ============================================================================
# CLAUDE AI REPORT GENERATION
# ============================================================================
def generate_claude_report(full_data):
    """Generate comprehensive report using Anthropic API."""
    if not ANTHROPIC_AVAILABLE or not ANTHROPIC_KEY:
        return "AI report generation not available (Anthropic API key not configured)"

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

        event_info = full_data.get("event", {})
        event_title = event_info.get("event_title", "Unknown Event")
        markets_data = full_data.get("strike_analysis", [])
        budget = full_data.get("budget", 1000)

        market_lines = []
        num_markets = len(markets_data)
        is_multi_choice = num_markets > 1
        for m in markets_data[:8]:  # Show top 8 for multi-choice context
            q = m.get("question", "")
            yp = m.get("polymarket", {}).get("yes_price", 0)
            vol = m.get("polymarket", {}).get("volume", 0)
            kelly_yes = m.get("kelly", {}).get("YES", {})
            kelly_no = m.get("kelly", {}).get("NO", {})
            best_k = kelly_yes if kelly_yes.get("bet_amount", 0) >= kelly_no.get("bet_amount", 0) else kelly_no
            best_side_k = "YES" if best_k == kelly_yes else "NO"
            roi = best_k.get("roi_if_win", 0)
            pos = best_k.get("bet_amount", 0)
            market_lines.append(f"- {q}: YES={yp:.1%}, Vol=${vol:,.0f}, Best={best_side_k} ${pos:.0f} ({roi:.0f}% ROI)")
        market_summary = "\n".join(market_lines)

        # Build strategy summary for the prompt
        strat = full_data.get("strategy", {})
        strat_line = ""
        if strat.get("best_market"):
            strat_line = f"\nSTRATEGY ENGINE RECOMMENDATION:\n- Best Market: {strat['best_market']}\n- Side: {strat.get('best_side', 'YES')}\n- Position Size: ${strat.get('recommended_position', 0):,.0f} ({strat.get('position_pct', 0):.1f}% of bankroll)\n- Confidence: {strat.get('confidence', 'low')}\n- Potential Profit: ${strat.get('potential_profit', 0):,.0f}\n- Risk/Reward: {strat.get('risk_reward', 0):.1f}x\n"

        multi_choice_note = ""
        if is_multi_choice:
            multi_choice_note = f"""
NOTE: This is a MULTI-CHOICE event with {num_markets} markets/outcomes.
You MUST specify the EXACT outcome/company/person to bet on by name.
Example: "Buy YES on Alphabet at 83¢" NOT just "Buy YES".
Each market is a separate bet — be specific about WHICH one."""

        prompt = f"""You are PolySnap Bot, an AGGRESSIVE prediction market analyst. You ALWAYS recommend a position to enter. NEVER say "PASS" or "wait". Every market has an opportunity.

Generate a concise but ACTIONABLE analysis report for this event.

EVENT: {event_title}
BUDGET: ${budget:,.0f}
NUMBER OF MARKETS: {num_markets}
{multi_choice_note}

MARKETS:
{market_summary}
{strat_line}
WHALE ACTIVITY:
{json.dumps(full_data.get('whale_tracking', {}).get('summary', {}), indent=2)}

Write a brief report with:
1. **Executive Summary** - 2-3 sentences on the event and the best realistic trade.
2. **Primary Trade** - The MAIN recommendation. Focus on the MOST LIKELY outcome. Name the SPECIFIC market (e.g. "Alphabet YES at 84¢"). Calculate the realistic ROI. Recommend a large position size (15-25% of bankroll for high-probability bets).
3. **Position Details** - SPECIFIC dollar amount, side, and market name. Format: "Buy [YES/NO] on [SPECIFIC MARKET NAME] — $X (Y% of bankroll) → Z% ROI if correct". Use the strategy engine's position (${strat.get('recommended_position', 0):,.0f} at {strat.get('position_pct', 0):.1f}%) as baseline.
4. **Key Risks** - Top 2 risks, but frame them as manageable.

CRITICAL RULES:
- ALWAYS recommend entering a trade. NEVER say "PASS" or "wait".
- ALWAYS name the SPECIFIC market/outcome — never just say "YES" or "NO" generically.
- PRIORITIZE high-probability outcomes with REALISTIC ROI (5-30% returns on big positions).
  Example: "Buy Alphabet YES at 84¢ → 19% ROI, $500 position" is BETTER than "Buy Tesla YES at 0.4¢ → 28000% ROI, $30 position".
- The user wants to ACTUALLY COLLECT profits, not gamble on longshots.
- Bet SIZE matters — a $500 bet with 19% ROI ($95 profit) beats a $30 bet with 300% ROI ($90 profit) because it's far more likely to pay out.
- For multi-choice events: lead with the favorite/most-likely outcome, then optionally mention a smaller speculative side bet.

Keep it under 500 words. Be specific with numbers and position sizes."""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return f"AI report generation failed: {str(e)}"

# ============================================================================
# FULL ANALYSIS PIPELINE
# ============================================================================
def run_full_analysis(job_id, slug, budget):
    """Run the full 10-step analysis pipeline."""

    try:
        # Step 1: Polymarket event
        _update_job(job_id, {"step": 1, "step_label": PIPELINE_STEPS[0]})
        event = fetch_polymarket_event(slug)
        if not event:
            _update_job(job_id, {"status": "error", "error": "Event not found"})
            return

        markets = event["markets"]
        has_strikes = any(m["strike"] > 0 for m in markets)
        ticker = extract_ticker(event["event_title"])
        is_sports = is_sports_event(event["event_title"])

        # Step 2: Stock/Asset data
        _update_job(job_id, {"step": 2, "step_label": PIPELINE_STEPS[1]})
        stock = None
        spot = 0
        iv = 0.30
        if ticker and has_strikes:
            stock = fetch_stock_data(ticker)
            if stock:
                spot = stock["spot_price"]
                iv = stock["implied_volatility"]

        # Calculate expiry
        try:
            end_dt = datetime.fromisoformat(event["event_end"].replace("Z", "+00:00"))
            days_left = max((end_dt - datetime.now(timezone.utc)).total_seconds() / 86400, 0.01)
        except:
            days_left = 7  # Default to 7 days

        # Step 3: Probability models
        _update_job(job_id, {"step": 3, "step_label": PIPELINE_STEPS[2]})
        all_analysis = []
        for m in markets:
            strike = m["strike"]
            yes_price = m["yes_price"]

            if has_strikes and strike > 0 and spot > 0:
                bs = black_scholes_prob(spot, strike, iv, days_left, "above")
                true_prob = bs["true_probability"]
            else:
                true_prob = yes_price if yes_price > 0 else 0.5
                bs = {
                    "spot": spot, "strike": strike, "iv": iv,
                    "days_to_expiry": days_left,
                    "true_probability": true_prob,
                    "model": "Market-Implied",
                }

            arb = detect_arbitrage(yes_price, true_prob)
            kelly = kelly_sizing(budget, true_prob, yes_price)
            roi_yes = polyscalping_roi(yes_price, 1.0, 100) if yes_price > 0 else {}
            roi_no = polyscalping_roi(1.0 - yes_price, 1.0, 100) if yes_price < 1.0 else {}

            all_analysis.append({
                "strike": strike,
                "question": m["question"],
                "polymarket": {
                    "yes_price": yes_price,
                    "no_price": m["no_price"],
                    "volume": m["volume"],
                    "liquidity": m["liquidity"],
                    "spread": m["spread"],
                },
                "black_scholes": bs,
                "arbitrage": arb,
                "kelly": kelly,
                "roi_yes_wins": roi_yes,
                "roi_no_wins": roi_no,
            })

        # Step 4: Sports odds
        _update_job(job_id, {"step": 4, "step_label": PIPELINE_STEPS[3]})
        sports_odds = {}
        if is_sports:
            sports_odds = fetch_sports_odds(event["event_title"])

        # Step 5: Kalshi comparison
        _update_job(job_id, {"step": 5, "step_label": PIPELINE_STEPS[4]})
        title_words = re.findall(r'[A-Za-z]{3,}', event["event_title"])
        skip_words = {"will", "the", "and", "for", "that", "this", "are", "was", "above", "below", "close"}
        search_kws = [w for w in title_words if w.lower() not in skip_words][:5]
        if ticker:
            search_kws.insert(0, ticker)
        kalshi_data = fetch_kalshi_markets(search_kws)

        # Step 6: Whale tracking
        _update_job(job_id, {"step": 6, "step_label": PIPELINE_STEPS[5]})
        whale_data = fetch_whale_activity()

        # Step 7: Orderbook depth
        _update_job(job_id, {"step": 7, "step_label": PIPELINE_STEPS[6]})
        orderbook_data = fetch_orderbook_depth(markets)

        # Step 8: Strategy calculations
        _update_job(job_id, {"step": 8, "step_label": PIPELINE_STEPS[7]})

        # Find best opportunity - REALISTIC RETURNS philosophy
        # Prioritize: high win probability × decent ROI × big position × volume
        # Goal: "Bet $500 on Alphabet YES at 84¢ for 19% ROI" not "$30 on Tesla for 28000% ROI"
        best_market = None
        best_score = -999
        best_ev = 0
        best_side = "YES"

        for m in all_analysis:
            vol = m.get("polymarket", {}).get("volume", 0)
            liq = m.get("polymarket", {}).get("liquidity", 0)
            for side in ["YES", "NO"]:
                k = m["kelly"].get(side, {})
                ev = k.get("ev_per_dollar", 0)
                roi = k.get("roi_if_win", 0)
                price = k.get("price", 0.5)
                bet = k.get("bet_amount", 0)

                # ============================================================
                # REALISTIC SCORING - favors achievable, high-confidence bets
                # ============================================================

                # 1. Win probability score (DOMINANT factor — we want to COLLECT)
                #    Higher probability = much higher score
                prob_score = price * 40  # 83% → 33 pts, 13% → 5 pts, 1% → 0.4 pts

                # 2. Expected dollar return (position × ROI × probability)
                #    This captures "how much money do I realistically expect to make?"
                expected_return = bet * (roi / 100) * price if roi > 0 else 0
                return_score = min(expected_return / 10, 20)  # Up to 20 pts

                # 3. EV bonus (strongest signal when model detects edge)
                ev_score = max(ev * 50, 0)  # Only positive EV counts

                # 4. Volume/liquidity (can I actually execute this trade?)
                vol_score = min(vol / 3000, 8) if vol else 0  # Up to 8 pts for $24k+ vol

                # 5. Position size score — bigger positions = more commitment from our model
                pos_score = min(bet / (budget * 0.05), 5) if budget > 0 else 0  # Up to 5 pts

                # 6. ROI sanity — prefer 5-100% ROI (achievable), penalize extreme ROI
                if 5 <= roi <= 100:
                    roi_score = 10  # Sweet spot: achievable and worthwhile
                elif 100 < roi <= 300:
                    roi_score = 5   # Good but less certain
                elif roi > 300:
                    roi_score = 1   # Longshot territory
                else:
                    roi_score = 3   # Very low ROI (<5%)

                total_score = prob_score + return_score + ev_score + vol_score + pos_score + roi_score

                if total_score > best_score:
                    best_score = total_score
                    best_ev = ev
                    best_market = m
                    best_side = side

        # Extract a short answer name from market question for multi-choice events
        # e.g. "Will Tesla be the second-largest..." → "Tesla"
        # e.g. "Will Trump nominate Kevin Warsh..." → "Kevin Warsh"
        def extract_answer_name(question, event_title, all_questions):
            """Extract the unique differentiating part of a market question vs other questions."""
            if not question:
                return ""
            q = question.strip().rstrip("?")

            # Strategy 1: Find the word(s) that differ between this question and others
            # Split all questions into word sets to find common words
            all_words_sets = []
            for oq in all_questions:
                all_words_sets.append(set(oq.lower().strip().rstrip("?").split()))
            # Words that appear in ALL questions (these are the template/common words)
            if len(all_words_sets) >= 2:
                common_words = all_words_sets[0]
                for ws in all_words_sets[1:]:
                    common_words = common_words & ws
            else:
                common_words = set()

            # Also add generic stop words
            common_words.update({"will", "the", "be", "by", "on", "in", "at", "for", "and", "or", "of",
                                 "to", "a", "an", "is", "as", "that", "this", "it", "its", "are", "was"})

            # Find unique words (present in this question but not in common set)
            q_words = q.split()
            if q_words and q_words[0].lower() == "will":
                q_words = q_words[1:]

            unique_words = []
            for w in q_words:
                if w.lower().rstrip(",.!?") not in common_words:
                    unique_words.append(w)

            if unique_words:
                return " ".join(unique_words)

            # Fallback: first capitalized entity after "Will"
            for w in q_words:
                clean = re.sub(r'[^a-zA-Z]', '', w)
                if clean and clean[0].isupper() and clean.lower() not in common_words:
                    return clean

            return q[:40]

        best_question = best_market["question"] if best_market else None
        best_answer_name = ""
        is_multi_choice = len(all_analysis) > 1
        all_questions = [m["question"] for m in all_analysis]
        if best_market and is_multi_choice:
            best_answer_name = extract_answer_name(best_question, event.get("event_title", ""), all_questions)

        strategy = {
            "best_market": best_question,
            "best_market_short": best_answer_name,
            "best_side": best_side if best_market else None,
            "best_ev": best_ev,
            "is_multi_choice": is_multi_choice,
            "num_markets": len(all_analysis),
            "recommended_position": 0,
            "position_pct": 0,
            "confidence": "none",
            "max_loss": 0,
            "potential_profit": 0,
            "risk_reward": 0,
        }

        if best_market:
            k = best_market["kelly"].get(best_side, {})
            position = k.get("bet_amount", 0)

            # ALWAYS have a position - fallback to 5% of budget
            if position <= 0:
                position = round(budget * 0.05, 2)

            strategy["recommended_position"] = position
            strategy["position_pct"] = k.get("position_pct", round(position / budget * 100, 2) if budget > 0 else 0)
            strategy["confidence"] = k.get("confidence", "low")
            strategy["max_loss"] = position
            strategy["entry_price"] = k.get("price", 0.5)
            strategy["roi_if_win"] = k.get("roi_if_win", 0)
            price = k.get("price", 0.5)
            if price > 0:
                strategy["potential_profit"] = round(position * ((1 / price) - 1), 2)
                if strategy["max_loss"] > 0:
                    strategy["risk_reward"] = round(strategy["potential_profit"] / strategy["max_loss"], 2)

        # Step 9: AI Report
        _update_job(job_id, {"step": 9, "step_label": PIPELINE_STEPS[8]})
        full_data = {
            "event": event,
            "stock_data": stock,
            "days_to_expiry": days_left,
            "strike_analysis": all_analysis,
            "sports_odds": sports_odds,
            "kalshi_comparison": kalshi_data,
            "whale_tracking": whale_data,
            "orderbook_depth": orderbook_data,
            "strategy": strategy,
            "budget": budget,
        }
        claude_report = generate_claude_report(full_data)

        # Step 10: Finalize
        _update_job(job_id, {"step": 10, "step_label": PIPELINE_STEPS[9]})

        result = {
            "generated_at": datetime.now().isoformat(),
            "event": event,
            "stock_data": stock,
            "days_to_expiry": days_left,
            "strike_analysis": all_analysis,
            "sports_odds": sports_odds,
            "kalshi_comparison": kalshi_data,
            "whale_tracking": whale_data,
            "orderbook_depth": orderbook_data,
            "strategy": strategy,
            "claude_report": claude_report,
            "budget": budget,
            "ticker": ticker,
            "is_sports": is_sports,
        }

        _update_job(job_id, {"status": "completed", "step": 10, "step_label": "Analysis complete!", "result": result})

    except Exception as e:
        import traceback
        _update_job(job_id, {"status": "error", "error": str(e), "traceback": traceback.format_exc()})

# ============================================================================
# TRENDING MARKETS ENGINE
# ============================================================================
def fetch_trending_events(limit=50):
    """Fetch trending events from Polymarket."""
    cached = get_cached("trending_events", ttl=60)
    if cached:
        return cached

    try:
        url = f"{GAMMA_API}/events"
        params = {
            "active": "true",
            "closed": "false",
            "limit": str(limit),
            "order": "volume24hr",
            "ascending": "false"
        }
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            events = r.json()
            set_cached("trending_events", events)
            return events
    except Exception as e:
        print(f"Error fetching trending: {e}")
    return []

def compute_polysnap_score(market):
    """Compute PolySnap score for a market - RISKY OPPORTUNITIES VERSION.

    Favors uncertain, volatile markets with high ROI potential.
    PENALIZES "sure things" (90%+ or 10%- probability).
    REWARDS markets in the 20-40% or 60-80% "uncertain zone".
    """
    try:
        prices_raw = market.get("outcomePrices", "[]")
        prices = json.loads(prices_raw)
        yes_price = float(prices[0]) if prices else 0.5

        volume = float(market.get("volume", 0) or 0)
        volume_24h = float(market.get("volume24hr", 0) or 0)
        liquidity = float(market.get("liquidity", 0) or 0)
        spread = float(market.get("spread", 0) or 0)

        # Get price change (volatility indicator)
        price_change = abs(float(market.get("oneDayPriceChange", 0) or 0))

        # ============ RISKY OPPORTUNITIES SCORING ============

        # 1. UNCERTAINTY SCORE (max 30 pts) - Favor uncertain outcomes
        # Best zone: 25-40% or 60-75% (uncertain but with edge)
        # Penalty zone: 90%+ or 10%- (too obvious/straightforward)
        cheap_side = min(yes_price, 1 - yes_price)

        if cheap_side <= 0.10:
            # Very cheap side = very likely outcome for the other side = OBVIOUS, penalize
            uncertainty_score = cheap_side * 100  # 0-10 pts (penalized)
        elif cheap_side <= 0.25:
            # Sweet spot: 10-25c = uncertain with good ROI (75-90% for other side)
            uncertainty_score = 15 + (cheap_side - 0.10) * 100  # 15-30 pts
        elif cheap_side <= 0.40:
            # Good zone: 25-40c = genuinely uncertain (60-75% for other side)
            uncertainty_score = 25 + (0.40 - cheap_side) * 33  # 25-30 pts
        else:
            # Near 50/50 - high uncertainty but lower ROI
            uncertainty_score = 20  # Moderate score

        # 2. ROI POTENTIAL SCORE (max 35 pts) - Favor high ROI cheap bets
        # Buy the cheap side and win = huge ROI
        potential_roi = (1 / max(cheap_side, 0.05) - 1) * 100  # e.g., 10c = 900% ROI
        roi_score = min(potential_roi / 300, 1) * 35  # Up to 35 pts for 300%+ ROI

        # 3. VOLATILITY SCORE (max 15 pts) - Favor moving markets
        # Higher price change = more uncertainty/opportunity
        volatility_score = min(price_change * 100, 15)  # 1% change = 1 pt, max 15

        # 4. LIQUIDITY SCORE (max 10 pts) - Some liquidity needed to trade
        # But don't over-reward massive liquidity (those are often the "safe" markets)
        if liquidity < 1000:
            liq_score = liquidity / 1000 * 5  # 0-5 pts for tiny markets
        elif liquidity < 10000:
            liq_score = 5 + (liquidity - 1000) / 9000 * 5  # 5-10 pts
        else:
            liq_score = 10  # Max out at $10k liquidity

        # 5. ACTIVITY SCORE (max 10 pts) - Recent volume = active market
        activity_ratio = volume_24h / max(volume, 1)  # What % of total vol is recent
        activity_score = min(activity_ratio * 100, 10)  # Up to 10 pts

        # 6. SPREAD PENALTY (up to -10 pts) - High spread = hard to trade
        spread_penalty = min(spread * 100, 10)  # 10% spread = -10 pts

        # 7. "SURE THING" PENALTY (up to -20 pts) - Heavily penalize obvious outcomes
        if cheap_side < 0.08:  # 92%+ probability for one side
            sure_thing_penalty = 20  # Heavy penalty
        elif cheap_side < 0.12:  # 88%+ probability
            sure_thing_penalty = 10
        else:
            sure_thing_penalty = 0

        total_score = (
            uncertainty_score +
            roi_score +
            volatility_score +
            liq_score +
            activity_score -
            spread_penalty -
            sure_thing_penalty
        )

        return round(max(total_score, 0), 1)
    except:
        return 0

def get_trending_markets(params):
    """Get trending markets with filters."""
    events = fetch_trending_events(limit=100)
    markets = []

    for event in events:
        for market in event.get("markets", []):
            try:
                prices_raw = market.get("outcomePrices", "[]")
                prices = json.loads(prices_raw)
                yes_price = float(prices[0]) if prices else 0.5
                no_price = float(prices[1]) if len(prices) > 1 else 1 - yes_price

                volume = float(market.get("volume", 0) or 0)
                volume_24h = float(market.get("volume24hr", 0) or 0)
                liquidity = float(market.get("liquidity", 0) or 0)
                spread = float(market.get("spread", 0) or 0)
                price_change = abs(float(market.get("oneDayPriceChange", 0) or 0))

                score = compute_polysnap_score(market)

                # Determine verdict - RISKY OPPORTUNITIES VERSION
                # Favor uncertain outcomes with high ROI, penalize "sure things"
                cheap_side = min(yes_price, 1 - yes_price)
                potential_roi = (1 / max(cheap_side, 0.05) - 1) * 100

                # HOT = Risky but lucrative opportunities
                # - Price in the "uncertain zone" (15-40c cheap side)
                # - Good ROI potential (150%+)
                # - Some price movement (volatility)
                is_uncertain = 0.12 <= cheap_side <= 0.42
                is_high_roi = potential_roi >= 150
                is_volatile = price_change >= 0.02  # 2%+ price change
                is_not_dead = volume_24h >= 100  # Some recent activity

                if is_uncertain and is_high_roi and is_not_dead:
                    verdict = "HOT"
                elif is_uncertain and (is_high_roi or is_volatile):
                    verdict = "WARM"
                elif cheap_side < 0.10:  # Very one-sided = boring/obvious
                    verdict = "OBVIOUS"  # New verdict for sure-thing markets
                else:
                    verdict = "COOL"

                markets.append({
                    "id": market.get("id", ""),
                    "question": market.get("question", ""),
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "volume": volume,
                    "volume_24h": volume_24h,
                    "liquidity": liquidity,
                    "spread": spread,
                    "change_24h": price_change,  # Price change for display
                    "potential_roi": round(potential_roi, 1),  # ROI potential
                    "polysnap_score": score,
                    "verdict": verdict,
                    "event_slug": event.get("slug", ""),
                    "event_title": event.get("title", ""),
                    "event_image": event.get("image", ""),
                    "end_date": market.get("endDate", ""),
                })
            except Exception as e:
                continue

    # Apply filters
    min_vol = params.get("min_volume", 0)
    min_score = params.get("min_score", 0)

    if min_vol > 0:
        markets = [m for m in markets if m["volume"] >= min_vol]
    if min_score > 0:
        markets = [m for m in markets if m["polysnap_score"] >= min_score]

    # Sort
    sort_by = params.get("sort_by", "score")
    if sort_by == "score":
        markets.sort(key=lambda x: x["polysnap_score"], reverse=True)
    elif sort_by == "volume":
        markets.sort(key=lambda x: x["volume"], reverse=True)
    elif sort_by == "liquidity":
        markets.sort(key=lambda x: x["liquidity"], reverse=True)

    # Limit
    limit = params.get("limit", 50)
    return markets[:limit]

def fetch_event_analysis(slug):
    """Quick event analysis for markets page."""
    event = fetch_polymarket_event(slug)
    if not event:
        return None

    markets = []
    for m in event["markets"]:
        yes_price = m["yes_price"]
        true_prob = yes_price  # Simple estimate

        kelly_yes = max(0, (true_prob - yes_price) / (1 - yes_price)) * 100 if yes_price < 1 else 0
        kelly_no = max(0, ((1 - true_prob) - (1 - yes_price)) / yes_price) * 100 if yes_price > 0 else 0

        ev_yes = (true_prob * (1/yes_price - 1) - (1 - true_prob)) * 100 if yes_price > 0 else 0
        ev_no = ((1 - true_prob) * (1/(1-yes_price) - 1) - true_prob) * 100 if yes_price < 1 else 0

        recommended = "YES" if ev_yes > ev_no else "NO"

        markets.append({
            "id": m["id"],
            "question": m["question"],
            "yes_price": yes_price,
            "no_price": m["no_price"],
            "volume": m["volume"],
            "liquidity": m["liquidity"],
            "true_prob": true_prob * 100,
            "kelly_yes": kelly_yes,
            "kelly_no": kelly_no,
            "ev_yes": ev_yes,
            "ev_no": ev_no,
            "recommended_side": recommended,
        })

    return {
        "event": {
            "title": event["event_title"],
            "volume": event["event_volume"],
            "liquidity": event["event_liquidity"],
            "image": event.get("image", ""),
        },
        "markets": markets,
        "summary": {
            "total_markets": len(markets),
            "best_ev": max([max(m["ev_yes"], m["ev_no"]) for m in markets]) if markets else 0,
        }
    }

# ============================================================================
# ROUTES - PAGES
# ============================================================================
@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/register")
def register_page():
    return render_template("register.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot-password.html")

@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html", page="dashboard")

@app.route("/markets")
def markets_page():
    return render_template("markets.html", page="markets")

@app.route("/whales")
def whales_page():
    return render_template("whales.html", page="whales")

@app.route("/calculator")
def calculator_page():
    return render_template("calculator.html", page="calculator")

@app.route("/analyzer")
def analyzer_page():
    return render_template("analyzer.html", page="analyzer")

@app.route("/settings")
def settings_page():
    return render_template("settings.html", page="settings")

@app.route("/terms")
def terms_page():
    return render_template("terms.html")

@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")

@app.route("/refund-policy")
def refund_policy_page():
    return render_template("refund-policy.html")

@app.route("/acceptable-use")
def acceptable_use_page():
    return render_template("acceptable-use.html")

# ============================================================================
# ROUTES - API
# ============================================================================
@app.route("/api/trending")
def api_trending():
    """Get trending markets."""
    params = {
        "limit": int(request.args.get("limit", 50)),
        "min_volume": float(request.args.get("min_volume", 0)),
        "min_score": float(request.args.get("min_score", 0)),
        "sort_by": request.args.get("sort_by", "score"),
    }
    markets = get_trending_markets(params)
    return jsonify({"markets": markets, "count": len(markets)})

@app.route("/api/whales")
def api_whales():
    """Get whale activity."""
    data = fetch_whale_activity()
    return jsonify(data)

@app.route("/api/trades")
def api_trades():
    """Get trades for a specific wallet or platform-wide."""
    address = request.args.get("address", "")

    # This would normally fetch from a trades database or API
    # For now, return mock data based on whale activity
    trades = []

    if address:
        # Get activity for specific wallet
        api_key = POLYGONSCAN_KEY or ETHERSCAN_KEY
        if api_key:
            try:
                url = (
                    f"https://api.etherscan.io/v2/api?chainid=137"
                    f"&module=account&action=tokentx"
                    f"&address={address}"
                    f"&page=1&offset=50&sort=desc"
                    f"&apikey={api_key}"
                )
                r = requests.get(url, timeout=15)
                data = r.json()

                if data.get("result") and isinstance(data["result"], list):
                    for tx in data["result"][:20]:
                        value = int(tx.get("value", "0"))
                        decimals = int(tx.get("tokenDecimal", "6"))
                        usd_value = value / (10 ** decimals)

                        is_deposit = tx.get("to", "").lower() == EXCHANGE_PROXY.lower()

                        trades.append({
                            "side": "buy" if is_deposit else "sell",
                            "market_name": tx.get("tokenName", "USDC"),
                            "market_image": None,
                            "amount": usd_value,
                            "price": None,
                            "timestamp": datetime.fromtimestamp(int(tx.get("timeStamp", 0))).isoformat(),
                            "time_ago": format_time_ago(int(tx.get("timeStamp", 0))),
                            "tx_hash": tx.get("hash", ""),
                        })
            except Exception as e:
                print(f"Error fetching trades: {e}")

    return jsonify({"trades": trades, "address": address})

def format_time_ago(timestamp):
    """Format timestamp as time ago string."""
    if not timestamp:
        return "-"
    seconds = int(datetime.now().timestamp() - timestamp)
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"

@app.route("/api/roi", methods=["POST"])
def api_roi():
    """Calculate ROI."""
    data = request.json or {}
    buy_price = float(data.get("buy_price", 0.5))
    sell_price = float(data.get("sell_price", 1.0))
    num_shares = float(data.get("shares", 100))
    result = polyscalping_roi(buy_price, sell_price, num_shares)
    return jsonify(result)

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Start comprehensive analysis (returns job_id for polling)."""
    data = request.json or {}
    slug = data.get("slug", "")
    budget = data.get("budget", 1000)

    # Extract slug from URL if needed
    if "polymarket.com" in slug:
        parts = slug.split("/")
        for i, p in enumerate(parts):
            if p == "event" and i + 1 < len(parts):
                slug = parts[i + 1].split("?")[0]
                break

    if not slug:
        return jsonify({"error": "No event slug provided"}), 400

    # Create job
    job_id = str(uuid.uuid4())
    _save_job(job_id, {
        "status": "running",
        "step": 0,
        "total_steps": len(PIPELINE_STEPS),
        "step_label": "Starting...",
        "result": None,
        "error": None,
    })

    # Run in background thread
    thread = threading.Thread(target=run_full_analysis, args=(job_id, slug, budget))
    thread.start()

    return jsonify({"job_id": job_id})

@app.route("/api/analyze/status/<job_id>")
def api_analyze_status(job_id):
    """Get analysis job status."""
    job = _load_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "status": job["status"],
        "step": job["step"],
        "total_steps": job.get("total_steps", len(PIPELINE_STEPS)),
        "step_label": job["step_label"],
        "error": job.get("error"),
    })

@app.route("/api/analyze/result/<job_id>")
def api_analyze_result(job_id):
    """Get analysis job result."""
    job = _load_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job["status"] != "completed":
        return jsonify({"error": f"Job not ready: {job['status']}", "status": job["status"]}), 400

    return jsonify(job["result"])

@app.route("/api/stats")
def api_stats():
    """Get dashboard stats - matching polyscalping.org format."""
    # Check cache first
    cached = get_cached("dashboard_stats", ttl=30)
    if cached:
        return jsonify(cached)

    # Fetch all events for comprehensive stats
    try:
        url = f"{GAMMA_API}/events"
        params = {
            "active": "true",
            "closed": "false",
            "limit": "500",  # Get more events for accurate totals
        }
        r = requests.get(url, params=params, timeout=15)
        all_events = r.json() if r.status_code == 200 else []
    except:
        all_events = []

    # Calculate totals across ALL markets
    total_volume_24h = 0
    total_liquidity = 0
    total_markets = 0
    best_liquidity_market = None
    best_liquidity = 0

    for event in all_events:
        for market in event.get("markets", []):
            total_markets += 1
            vol_24h = float(market.get("volume24hr", 0) or 0)
            liq = float(market.get("liquidity", 0) or 0)

            total_volume_24h += vol_24h
            total_liquidity += liq

            if liq > best_liquidity:
                best_liquidity = liq
                best_liquidity_market = {
                    "question": market.get("question", ""),
                    "liquidity": liq,
                    "event_slug": event.get("slug", ""),
                }

    # Get previous stats from cache for change calculation
    prev_stats = get_cached("prev_dashboard_stats", ttl=86400) or {}

    # Calculate changes (percentage for volume/liquidity, absolute for markets)
    prev_vol = prev_stats.get("total_volume_24h", total_volume_24h)
    prev_liq = prev_stats.get("total_liquidity", total_liquidity)
    prev_markets = prev_stats.get("total_markets", total_markets)

    vol_change_pct = ((total_volume_24h - prev_vol) / max(prev_vol, 1)) * 100 if prev_vol > 0 else 0
    liq_change_pct = ((total_liquidity - prev_liq) / max(prev_liq, 1)) * 100 if prev_liq > 0 else 0
    markets_change = total_markets - prev_markets

    # Store current as previous for next comparison (only if significantly different)
    if abs(vol_change_pct) > 1 or abs(liq_change_pct) > 1 or abs(markets_change) > 10:
        set_cached("prev_dashboard_stats", {
            "total_volume_24h": total_volume_24h,
            "total_liquidity": total_liquidity,
            "total_markets": total_markets,
        })

    # Get hot markets count
    markets_data = get_trending_markets({"limit": 100})
    hot_count = sum(1 for m in markets_data if m["verdict"] == "HOT")

    stats = {
        # Main stats matching polyscalping.org
        "total_volume_24h": total_volume_24h,
        "volume_change_pct": round(vol_change_pct, 1),
        "total_liquidity": total_liquidity,
        "liquidity_change_pct": round(liq_change_pct, 1),
        "total_markets": total_markets,
        "markets_change": markets_change,
        "best_liquidity_market": best_liquidity_market,

        # Legacy stats for backwards compatibility
        "markets_count": len(markets_data),
        "hot_markets": hot_count,
    }

    set_cached("dashboard_stats", stats)
    return jsonify(stats)

# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    import os
    debug = os.getenv("DEBUG", "false").lower() == "true"
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5050))

    print("\n" + "="*60)
    print("  POLYHUNTER - Unified Dashboard")
    print("  Full Analysis Pipeline Enabled")
    print("="*60)
    print(f"  http://{host}:{port}")
    print(f"  Debug: {debug}")
    print("="*60 + "\n")

    app.run(host=host, port=port, debug=debug)
