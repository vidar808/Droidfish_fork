#!/bin/bash
# Chess UCI Server - Linux Installation Script
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINES_DIR="$SCRIPT_DIR/engines"

echo ""
echo "  Chess UCI Server - Linux Installer"
echo "  ==================================="
echo ""

# ── Step 1: Check Python ──────────────────────────────────────────

if ! command -v python3 &> /dev/null; then
    echo "  ERROR: Python 3 is not installed."
    echo "  Install it with: sudo apt install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 7 ]); then
    echo "  ERROR: Python 3.7+ is required (found $PYTHON_VERSION)"
    exit 1
fi

echo "  [1/5] Python $PYTHON_VERSION .............. OK"

# ── Step 2: Install Python dependencies ───────────────────────────

DEP_FAIL=0
MISSING_DEPS=""

if pip3 install -q -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null; then
    echo "  [2/5] Python dependencies ........... OK"
else
    # Bulk install failed — check each dependency individually
    for dep in qrcode zeroconf miniupnpc; do
        if ! python3 -c "import $dep" 2>/dev/null; then
            if ! pip3 install -q "$dep" 2>/dev/null; then
                DEP_FAIL=$((DEP_FAIL + 1))
                MISSING_DEPS="$MISSING_DEPS $dep"
            fi
        fi
    done

    if [ "$DEP_FAIL" -eq 0 ]; then
        echo "  [2/5] Python dependencies ........... OK"
    else
        echo "  [2/5] Python dependencies ........... PARTIAL"
        echo "        Failed to install:$MISSING_DEPS"
        for dep in $MISSING_DEPS; do
            case "$dep" in
                qrcode)   echo "          - qrcode: QR pairing display unavailable" ;;
                zeroconf) echo "          - zeroconf: mDNS auto-discovery disabled" ;;
                miniupnpc) echo "          - miniupnpc: UPnP port mapping disabled" ;;
            esac
        done
        echo "        Install manually: pip3 install$MISSING_DEPS"
    fi
fi

# ── Step 3: Detect engines ────────────────────────────────────────

ENGINE_COUNT=0

# Check engines/ folder
if [ -d "$ENGINES_DIR" ]; then
    for f in "$ENGINES_DIR"/*; do
        [ -f "$f" ] && [ -x "$f" ] && ENGINE_COUNT=$((ENGINE_COUNT + 1))
    done
fi

# Check system stockfish
if command -v stockfish &> /dev/null; then
    SYSTEM_SF=$(which stockfish)
    ENGINE_COUNT=$((ENGINE_COUNT + 1))
fi

if [ "$ENGINE_COUNT" -eq 0 ]; then
    echo "  [3/5] No engines found"
    echo ""
    echo "  You need at least one UCI engine. Options:"
    echo "    a) Install Stockfish:  sudo apt install stockfish"
    echo "    b) Place engine binaries in: $ENGINES_DIR/"
    echo "       (make sure they are executable: chmod +x <engine>)"
    echo ""
    read -p "  Install Stockfish via apt now? [Y/n] " install_sf
    if [[ ! "$install_sf" =~ ^[Nn]$ ]]; then
        sudo apt-get update -qq && sudo apt-get install -y -qq stockfish
        SYSTEM_SF=$(which stockfish)
        ENGINE_COUNT=1
        echo "  [3/5] Stockfish installed ........... OK"
    else
        echo ""
        echo "  WARNING: No engines available. Add engines before starting the server."
        echo "           Place executables in: $ENGINES_DIR/"
    fi
else
    echo "  [3/5] Found $ENGINE_COUNT engine(s) ........... OK"
fi

# ── Step 4: Generate config.json ──────────────────────────────────

if [ ! -f "$SCRIPT_DIR/config.json" ]; then
    cp "$SCRIPT_DIR/example_config.json" "$SCRIPT_DIR/config.json"

    # If system stockfish found but no engines in engines/, add it to config
    if [ -n "$SYSTEM_SF" ] && [ ! -d "$ENGINES_DIR" ] || [ "$(ls -A "$ENGINES_DIR" 2>/dev/null | wc -l)" -eq 0 ]; then
        python3 -c "
import json
with open('$SCRIPT_DIR/config.json') as f:
    cfg = json.load(f)
cfg['engines'] = {'Stockfish': {'path': '$SYSTEM_SF', 'port': 9998}}
with open('$SCRIPT_DIR/config.json', 'w') as f:
    json.dump(cfg, f, indent=2)
" 2>/dev/null || true
    fi

    # Generate a default auth token for security
    python3 -c "
import json, secrets
with open('$SCRIPT_DIR/config.json') as f:
    cfg = json.load(f)
if not cfg.get('auth_token'):
    cfg['auth_token'] = secrets.token_hex(16)
    cfg['auth_method'] = 'token'
    with open('$SCRIPT_DIR/config.json', 'w') as f:
        json.dump(cfg, f, indent=2)
    print('  Auth token: ' + cfg['auth_token'])
" 2>/dev/null || true

    echo "  [4/5] Config generated .............. OK"
else
    echo "  [4/5] Config exists ................. OK (kept existing)"
fi

# ── Step 5: Connectivity ─────────────────────────────────────────

# Read base_port from config (default 9998)
BASE_PORT=$(python3 -c "
import json
try:
    with open('$SCRIPT_DIR/config.json') as f:
        print(json.load(f).get('base_port', 9998))
except: print(9998)
" 2>/dev/null)

echo ""
echo "  [5/5] Connectivity"
echo "  How will clients connect?"
echo "    1) LAN only     - mDNS + UPnP auto-discovery (default)"
echo "    2) Open firewall - Auto-opens port $BASE_PORT for external access"
echo "    3) Relay mode    - No port forwarding needed"
read -p "  Select [1]: " conn_choice
conn_choice=${conn_choice:-1}

if [ "$conn_choice" = "2" ]; then
    # Open firewall port
    if command -v ufw &> /dev/null; then
        echo "  Opening port $BASE_PORT in UFW..."
        sudo ufw allow "$BASE_PORT/tcp" comment "Chess UCI Server" 2>/dev/null && \
            echo "  UFW rule added for port $BASE_PORT" || \
            echo "  WARNING: Failed to add UFW rule (may need sudo)"
    else
        echo "  Opening port $BASE_PORT in iptables..."
        sudo iptables -A INPUT -p tcp --dport "$BASE_PORT" -j ACCEPT 2>/dev/null && \
            echo "  iptables rule added for port $BASE_PORT" || \
            echo "  WARNING: Failed to add iptables rule (may need sudo)"
    fi
    echo "  [5/5] Firewall ...................... OK"

elif [ "$conn_choice" = "3" ]; then
    # Relay mode — update config.json with relay settings
    read -p "  Relay server URL [spacetosurf.com]: " relay_url
    relay_url=${relay_url:-spacetosurf.com}
    read -p "  Relay port [19000]: " relay_port
    relay_port=${relay_port:-19000}

    python3 -c "
import json, secrets
with open('$SCRIPT_DIR/config.json') as f:
    cfg = json.load(f)
cfg['relay_server_url'] = '$relay_url'
cfg['relay_server_port'] = $relay_port
cfg['enable_upnp'] = False
cfg['enable_single_port'] = True
if not cfg.get('server_secret') or len(cfg.get('server_secret', '')) < 32:
    cfg['server_secret'] = secrets.token_hex(32)
with open('$SCRIPT_DIR/config.json', 'w') as f:
    json.dump(cfg, f, indent=2)
print(f'  Relay configured: {cfg[\"relay_server_url\"]}:{cfg[\"relay_server_port\"]}')
" 2>/dev/null || echo "  WARNING: Failed to update config with relay settings"
    echo "  [5/5] Relay mode .................... OK"

else
    echo "  [5/5] LAN mode ...................... OK"
fi

# ── Done ──────────────────────────────────────────────────────────

echo ""
echo "  ==========================================="
echo "  Installation complete!"
echo "  ==========================================="
echo ""

read -p "  Start server now with QR pairing? [Y/n] " start_now
if [[ ! "$start_now" =~ ^[Nn]$ ]]; then
    echo ""
    echo "  Starting server with QR pairing..."
    echo ""
    cd "$SCRIPT_DIR"
    exec python3 chess.py --pair
fi

echo ""
echo "  To start later, run:"
echo "    cd $SCRIPT_DIR"
echo "    python3 chess.py --pair"
echo ""
echo "  Or use the interactive setup wizard:"
echo "    python3 chess.py --setup"
echo ""

# ── Optional: advanced setup ──────────────────────────────────────

read -p "  Install as systemd service? (for auto-start on boot) [y/N] " install_service
if [[ "$install_service" =~ ^[Yy]$ ]]; then
    SERVICE_FILE="/etc/systemd/system/chess-uci-server.service"

    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Chess UCI Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$(which python3) $SCRIPT_DIR/chess.py
ExecStop=$(which python3) $SCRIPT_DIR/chess.py --stop
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable chess-uci-server
    echo ""
    echo "  Service installed. Commands:"
    echo "    sudo systemctl start chess-uci-server"
    echo "    sudo systemctl status chess-uci-server"
    echo "    journalctl -u chess-uci-server -f"
fi
