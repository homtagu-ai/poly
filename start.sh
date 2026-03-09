#!/bin/bash
# PolyHunter — Production start script for Hosting Ukraine
#
# Hosting panel settings:
#   Launch directory: /home/te605656/poly-hunter.com/www/
#   Launch command:   unalias python 2>/dev/null; source .venv/bin/activate && bash start.sh
#   Port:             3000 (proxy: www.poly-hunter.com → 127.1.7.92:3000)

set -e
cd "$(dirname "$0")"

export PORT="${PORT:-3000}"
export BIND_IP="${BIND_IP:-127.1.7.92}"

echo "[PolyHunter] Starting on $BIND_IP:$PORT ..."

# Build Mini App if dist doesn't exist
if [ -d "miniapp" ] && [ ! -d "miniapp/dist" ]; then
    echo "[PolyHunter] Building Mini App..."
    cd miniapp && npm install --production=false && npm run build && cd ..
fi

# Activate venv if not already active
if [ -z "$VIRTUAL_ENV" ]; then
    [ -d .venv ] && source .venv/bin/activate || source venv/bin/activate
fi

# Start with Gunicorn (uses deploy/gunicorn.conf.py for bind/workers/logging)
exec gunicorn --config deploy/gunicorn.conf.py polyscalping.server:app
