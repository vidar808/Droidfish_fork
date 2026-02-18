#!/bin/bash
# Deploy Chess UCI Relay Server on a public VPS
# Usage: scp this script + relay_server.py to VPS, then run
#
# Example deployment to spacetosurf.com:
#   scp deploy-relay.sh relay_server.py root@62.72.26.179:/tmp/
#   ssh root@62.72.26.179 'bash /tmp/deploy-relay.sh'
#
# The relay server listens on TCP port 19000 and pairs chess servers
# with DroidFish clients that cannot connect directly (NAT/firewall).

set -e

RELAY_DIR="/opt/chess-relay"
SERVICE_FILE="/etc/systemd/system/chess-relay.service"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELAY_PORT=19000

echo ""
echo "  Chess UCI Relay Server - Deployment"
echo "  ===================================="
echo ""

# ── Step 1: Check Python ──────────────────────────────────────────

if ! command -v python3 &> /dev/null; then
    echo "  ERROR: Python 3 is not installed."
    echo "  Install it with: sudo apt install python3"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  [1/5] Python $PYTHON_VERSION .............. OK"

# ── Step 2: Install relay_server.py ───────────────────────────────

echo "  [2/5] Installing relay server..."
sudo mkdir -p "$RELAY_DIR"

# Find relay_server.py: same directory as this script, or /tmp/
if [ -f "$SCRIPT_DIR/relay_server.py" ]; then
    sudo cp "$SCRIPT_DIR/relay_server.py" "$RELAY_DIR/relay_server.py"
elif [ -f "/tmp/relay_server.py" ]; then
    sudo cp "/tmp/relay_server.py" "$RELAY_DIR/relay_server.py"
else
    echo "  ERROR: relay_server.py not found"
    echo "  Place it next to this script or in /tmp/"
    exit 1
fi

sudo chmod 644 "$RELAY_DIR/relay_server.py"
echo "  [2/5] Relay server installed ........ OK"
echo "        Path: $RELAY_DIR/relay_server.py"

# ── Step 3: Install systemd service ──────────────────────────────

echo "  [3/5] Installing systemd service..."

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Chess UCI Relay Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $RELAY_DIR/relay_server.py --port $RELAY_PORT
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable chess-relay
echo "  [3/5] Service installed ............. OK"

# ── Step 4: Open firewall port ────────────────────────────────────

echo "  [4/5] Configuring firewall..."

if command -v ufw &> /dev/null; then
    if sudo ufw status | grep -q "Status: active"; then
        sudo ufw allow "$RELAY_PORT/tcp" comment "Chess UCI Relay"
        echo "  [4/5] UFW: port $RELAY_PORT/tcp ...... OK"
    else
        echo "  [4/5] UFW inactive .................. SKIPPED"
    fi
elif command -v firewall-cmd &> /dev/null; then
    sudo firewall-cmd --permanent --add-port="$RELAY_PORT/tcp"
    sudo firewall-cmd --reload
    echo "  [4/5] firewalld: port $RELAY_PORT/tcp . OK"
else
    echo "  [4/5] No firewall manager found ..... SKIPPED"
    echo "        Manually open port $RELAY_PORT/tcp if needed"
fi

# ── Step 5: Start service ─────────────────────────────────────────

echo "  [5/5] Starting relay server..."
sudo systemctl start chess-relay

# Verify it's running
sleep 1
if systemctl is-active --quiet chess-relay; then
    echo "  [5/5] Relay server .................. RUNNING"
else
    echo "  [5/5] Relay server .................. FAILED"
    echo ""
    echo "  Check logs with: journalctl -u chess-relay -n 20"
    exit 1
fi

# ── Done ──────────────────────────────────────────────────────────

echo ""
echo "  ===================================="
echo "  Deployment complete!"
echo "  ===================================="
echo ""
echo "  Relay:    0.0.0.0:$RELAY_PORT"
echo "  Service:  chess-relay.service"
echo ""
echo "  Commands:"
echo "    systemctl status chess-relay"
echo "    journalctl -u chess-relay -f"
echo "    systemctl restart chess-relay"
echo ""
echo "  Test with:"
echo "    echo 'SESSION test123 server' | nc localhost $RELAY_PORT"
echo ""
