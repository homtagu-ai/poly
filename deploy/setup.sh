#!/bin/bash
# PolyHunter — Deployment setup for Ukrainian Hosting (hosting.ua)
#
# Hosting environment:
#   User:     te605656
#   App dir:  /home/te605656/poly-hunter.com/www/
#   Proxy:    www.poly-hunter.com → 127.1.7.92:3000
#   SSL:      Managed by hosting provider
#   Startup:  Hosting panel manages the process
#
# This script is for initial setup / updates via SSH.
# Usage: cd /home/te605656/poly-hunter.com/www && bash deploy/setup.sh

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "=========================================="
echo "  PolyHunter Setup"
echo "  App dir: $APP_DIR"
echo "=========================================="

# 1. Python virtualenv (need 3.10+ for modern packages)
echo "[1/4] Setting up Python virtualenv..."
cd "$APP_DIR"

# Find best available Python (prefer 3.12, then 3.13, 3.11, 3.10)
PYTHON_BIN=""
for v in python3.12 python3.13 python3.11 python3.10; do
    if command -v "$v" &>/dev/null; then
        PYTHON_BIN="$v"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "  ERROR: Python 3.10+ is required but not found!"
    echo "  Available: $(ls /usr/bin/python3.* 2>/dev/null | tr '\n' ' ')"
    exit 1
fi
echo "  Using $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"

if [ ! -d ".venv" ]; then
    $PYTHON_BIN -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "  Python dependencies installed."

# 2. Build Mini App (requires Node.js — pre-installed by hosting)
echo "[2/4] Building Telegram Mini App..."
if [ -d "miniapp" ]; then
    cd miniapp
    npm install --production=false
    npm run build
    cd "$APP_DIR"
    echo "  Mini App built to miniapp/dist/"
else
    echo "  SKIP: miniapp/ directory not found."
fi

# 3. Create logs directory
echo "[3/4] Creating logs directory..."
mkdir -p "$APP_DIR/logs"

# 4. Verify .env
echo "[4/4] Checking configuration..."
if [ ! -f "$APP_DIR/.env" ]; then
    echo "  WARNING: .env file not found! Copy from your local machine."
else
    echo "  .env found."
    if grep -q "TMA_URL" "$APP_DIR/.env"; then
        echo "  TMA_URL is configured."
    else
        echo "  WARNING: TMA_URL not in .env. Add: TMA_URL=https://poly-hunter.com/tma/"
    fi
fi

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo ""
echo "  Hosting panel settings:"
echo "    Launch dir:  $APP_DIR"
echo "    Command:     unalias python 2>/dev/null; source .venv/bin/activate && bash start.sh"
echo ""
echo "  URLs:"
echo "    Dashboard:   https://poly-hunter.com/"
echo "    Mini App:    https://poly-hunter.com/tma/"
echo ""
echo "  To start Telegram bot (in SSH):"
echo "    cd $APP_DIR && source .venv/bin/activate"
echo "    nohup python -m bot.main > logs/bot.log 2>&1 &"
echo "=========================================="
