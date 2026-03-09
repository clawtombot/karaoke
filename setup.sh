#!/bin/bash
# PHANTOM Karaoke Pipeline — Setup & Launch Script
# Creates virtualenv, installs dependencies, and starts server.py in background.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[PHANTOM] Karaoke Pipeline setup starting..."
echo "[PHANTOM] Working directory: $SCRIPT_DIR"

# Create virtualenv if it doesn't exist
if [ ! -d "karaoke-venv" ]; then
    echo "[PHANTOM] Creating virtualenv at karaoke-venv/ ..."
    python3 -m venv karaoke-venv
else
    echo "[PHANTOM] Virtualenv already exists, skipping creation."
fi

# Activate and install requirements
echo "[PHANTOM] Installing requirements from requirements.txt ..."
karaoke-venv/bin/pip install --upgrade pip --quiet
karaoke-venv/bin/pip install -r requirements.txt

# Create logs directory
mkdir -p logs
echo "[PHANTOM] logs/ directory ready."

# Kill any existing server on port 8001
if lsof -ti:8001 &>/dev/null; then
    echo "[PHANTOM] Stopping existing process on port 8001 ..."
    lsof -ti:8001 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Start server in background via nohup
echo "[PHANTOM] Starting server.py in background ..."
nohup karaoke-venv/bin/python server.py > logs/server.log 2>&1 &
SERVER_PID=$!

echo ""
echo "================================================="
echo "  PHANTOM Karaoke Server started successfully"
echo "  PID: $SERVER_PID"
echo "  Port: 8001"
echo "  Log: $SCRIPT_DIR/logs/server.log"
echo "  Tailscale: https://thomasnguyens-macbook-pro-1.tail4fc6de.ts.net/karaoke-api"
echo "================================================="
echo ""
echo "To stop the server: kill $SERVER_PID"
echo "To tail logs:       tail -f $SCRIPT_DIR/logs/server.log"
