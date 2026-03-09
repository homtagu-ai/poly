#!/usr/bin/env bash
# ============================================================================
# PolyHunter Copy Trading Bot — Startup Script
# ============================================================================
#
# Usage:
#   ./start_bot.sh              # polling mode (local development)
#   ./start_bot.sh --webhook    # webhook mode (production)
#
# Prerequisites:
#   1. Python 3.10+
#   2. pip install -r requirements.txt
#   3. .env file with:
#        TELEGRAM_BOT_TOKEN=<your-bot-token>
#        ENCRYPTION_MASTER_KEY=<base64-encoded-32-byte-key>
#        SUPABASE_URL=<your-supabase-url>
#        SUPABASE_KEY=<your-supabase-service-role-key>
#        ETHERSCAN_API_KEY=<your-etherscan-key>
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Validate required environment variables
REQUIRED_VARS=(TELEGRAM_BOT_TOKEN ENCRYPTION_MASTER_KEY SUPABASE_URL SUPABASE_KEY)
MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        MISSING+=("$var")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "ERROR: Missing required environment variables:"
    for var in "${MISSING[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Please add them to your .env file."
    exit 1
fi

echo "============================================"
echo "  PolyHunter Copy Trading Bot"
echo "============================================"
echo "  Mode: ${1:-polling}"
echo "  Python: $(python3 --version 2>&1)"
echo "============================================"

# Run the bot
exec python3 -m bot.main "$@"
