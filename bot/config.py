"""
PolyHunter Bot Configuration
Loads all environment variables and defines trading defaults.
"""
import os
from dotenv import load_dotenv

load_dotenv(override=True)

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_WEBHOOK_SECRET = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')
ENCRYPTION_MASTER_KEY = os.getenv('ENCRYPTION_MASTER_KEY', '')  # base64 encoded 32 bytes

# Polymarket
POLYGONSCAN_KEY = os.getenv('POLYGONSCAN_API_KEY', '') or os.getenv('ETHERSCAN_API_KEY', '')

# Telegram Mini App
TMA_URL = os.getenv('TMA_URL', '')  # e.g. https://yourdomain.com/tma/

# Trading defaults
DEFAULT_BUY_SLIPPAGE = 5.0
DEFAULT_SELL_SLIPPAGE = 5.0
DEFAULT_COPY_PERCENTAGE = 100.0
MIN_MARKET_LIQUIDITY = 10000  # $10,000
SIGNAL_MAX_AGE_SECONDS = 30
WALLET_POLL_INTERVAL = 8  # seconds
TP_SL_CHECK_INTERVAL = 30  # seconds
