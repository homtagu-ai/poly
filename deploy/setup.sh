#!/bin/bash
# PolySnap Production Setup Script
# Run this on your EC2 instance after cloning the repo to /home/ubuntu/poly
#
# Usage: sudo bash /home/ubuntu/poly/deploy/setup.sh

set -e

APP_DIR="/home/ubuntu/poly"
DEPLOY_DIR="$APP_DIR/deploy"

echo "=========================================="
echo "  PolySnap Production Setup"
echo "=========================================="

# 1. System updates & install Nginx
echo "[1/8] Installing system packages..."
apt-get update -y
apt-get install -y nginx python3-venv python3-pip

# 2. Create swap file (prevents OOM kills on t3.micro)
echo "[2/8] Setting up 1GB swap file..."
if [ ! -f /swapfile ]; then
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "  Swap created."
else
    echo "  Swap already exists, skipping."
fi

# 3. Create virtualenv and install dependencies
echo "[3/8] Setting up Python virtualenv..."
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 4. Create logs directory
echo "[4/8] Creating logs directory..."
mkdir -p "$APP_DIR/logs"
chown -R ubuntu:ubuntu "$APP_DIR/logs"

# 5. Install systemd service
echo "[5/8] Installing systemd service..."
cp "$DEPLOY_DIR/polysnap.service" /etc/systemd/system/polysnap.service
systemctl daemon-reload
systemctl enable polysnap.service

# 6. Install Nginx config
echo "[6/8] Configuring Nginx..."
rm -f /etc/nginx/sites-enabled/default
cp "$DEPLOY_DIR/nginx-polysnap.conf" /etc/nginx/sites-available/polysnap
ln -sf /etc/nginx/sites-available/polysnap /etc/nginx/sites-enabled/polysnap
nginx -t

# 7. Start services
echo "[7/8] Starting services..."
systemctl restart nginx
systemctl restart polysnap.service

# 8. Verify
echo "[8/8] Verifying..."
sleep 3
systemctl status polysnap.service --no-pager
echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "  Your app should be live at:"
echo "  http://44.207.97.34/"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status polysnap"
echo "    sudo systemctl restart polysnap"
echo "    sudo journalctl -u polysnap -f"
echo "    tail -f $APP_DIR/logs/gunicorn-error.log"
echo "=========================================="
