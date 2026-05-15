#!/bin/bash
# Install API as systemd service on Ubuntu

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER="$(whoami)"

echo "=== SERP API Service Installer ==="

# Prompt for configuration
read -p "Service name [serp-api]: " SERVICE_NAME
SERVICE_NAME="${SERVICE_NAME:-serp-api}"

read -p "Host [0.0.0.0]: " HOST
HOST="${HOST:-0.0.0.0}"

read -p "Port [8000]: " PORT
PORT="${PORT:-8000}"

read -p "Debug mode (yes/no) [no]: " DEBUG_INPUT
case "${DEBUG_INPUT,,}" in
    yes|y) DEBUG="true" ;;
    *) DEBUG="false" ;;
esac

# Create venv if not exists
if [ ! -d "$APP_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$APP_DIR/venv"
fi

# Install dependencies
echo "Installing dependencies..."
"$APP_DIR/venv/bin/pip" install -e ".[api]" -q

# Create logs directory
mkdir -p "$APP_DIR/logs"

# Create systemd service file
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
echo "Creating systemd service: $SERVICE_FILE"
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=SERP Scraper API
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
Environment="API_DEBUG=$DEBUG"
ExecStart=$APP_DIR/venv/bin/python -m uvicorn api.main:app --host $HOST --port $PORT
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd, enable and start service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "Service '$SERVICE_NAME' installed and running."
systemctl status "$SERVICE_NAME" --no-pager