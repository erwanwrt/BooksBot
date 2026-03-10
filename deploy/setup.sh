#!/bin/bash
# BooksBot VPS Setup Script
# Tested on Ubuntu 22.04 / Debian 12
set -euo pipefail

APP_DIR="/opt/booksbot"
APP_USER="booksbot"

echo "=== BooksBot VPS Setup ==="

# 1. System dependencies
echo "[1/6] Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-venv python3-pip git xvfb

# 2. Create dedicated user
echo "[2/6] Creating user '$APP_USER'..."
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --shell /usr/sbin/nologin --home-dir "$APP_DIR" "$APP_USER"
fi

# 3. Deploy application
echo "[3/6] Deploying application to $APP_DIR..."
mkdir -p "$APP_DIR"
cp -r ./*.py requirements.txt "$APP_DIR/"
mkdir -p "$APP_DIR/downloads" "$APP_DIR/browser_data"

# 4. Python environment
echo "[4/6] Setting up Python venv..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/playwright" install --with-deps chromium

# 5. .env file
if [ ! -f "$APP_DIR/.env" ]; then
    echo "[5/6] Creating .env file (EDIT THIS!)..."
    cp deploy/.env.example "$APP_DIR/.env" 2>/dev/null || cp .env.example "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo ">>> IMPORTANT: Edit /opt/booksbot/.env with your credentials!"
else
    echo "[5/6] .env already exists, skipping..."
fi

# 6. Set ownership
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# 7. Install systemd services
echo "[6/6] Installing systemd services..."
cp deploy/xvfb.service /etc/systemd/system/
cp deploy/booksbot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable xvfb booksbot

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit credentials:  sudo nano /opt/booksbot/.env"
echo "  2. Start services:    sudo systemctl start xvfb && sudo systemctl start booksbot"
echo "  3. Check status:      sudo systemctl status booksbot"
echo "  4. View logs:         sudo journalctl -u booksbot -f"
