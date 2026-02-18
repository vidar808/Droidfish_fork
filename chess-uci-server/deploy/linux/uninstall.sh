#!/bin/bash
# Chess UCI Server - Uninstall Script
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  Chess UCI Server - Uninstall"
echo "  ============================="
echo ""

# ── Confirmation ─────────────────────────────────────────────────

echo "  This will:"
echo "    - Stop the running server (if any)"
echo "    - Remove the systemd service (if installed)"
echo "    - Remove generated files (config, PID, logs, TLS certs)"
echo "    - Remove Python dependencies (qrcode, zeroconf, miniupnpc)"
echo "    - Remove the server directory: $SCRIPT_DIR"
echo ""
read -p "  Are you sure? Type 'yes' to confirm: " confirm
if [ "$confirm" != "yes" ]; then
    echo ""
    echo "  Uninstall cancelled."
    exit 0
fi

echo ""

# ── Step 1: Stop the server ─────────────────────────────────────

PID_FILE="$SCRIPT_DIR/chess-uci-server.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "  [1/5] Stopping server (PID $OLD_PID)..."
        python3 "$SCRIPT_DIR/chess.py" --stop 2>/dev/null || kill "$OLD_PID" 2>/dev/null || true
        sleep 1
        # Force kill if still alive
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill -9 "$OLD_PID" 2>/dev/null || true
        fi
        echo "         Server stopped."
    else
        echo "  [1/5] Server not running (stale PID file)."
        rm -f "$PID_FILE"
    fi
else
    echo "  [1/5] Server not running ........... OK"
fi

# ── Step 2: Remove systemd service ──────────────────────────────

SERVICE_FILE="/etc/systemd/system/chess-uci-server.service"
if [ -f "$SERVICE_FILE" ]; then
    echo "  [2/5] Removing systemd service..."
    sudo systemctl stop chess-uci-server 2>/dev/null || true
    sudo systemctl disable chess-uci-server 2>/dev/null || true
    sudo rm -f "$SERVICE_FILE"
    sudo systemctl daemon-reload 2>/dev/null || true
    echo "         Service removed."
else
    echo "  [2/5] No systemd service found ..... OK"
fi

# ── Step 3: Remove generated files ──────────────────────────────

echo "  [3/5] Removing generated files..."
REMOVED_COUNT=0

for f in \
    "$SCRIPT_DIR/config.json" \
    "$SCRIPT_DIR/chess-uci-server.pid" \
    "$SCRIPT_DIR/server.log" \
    "$SCRIPT_DIR/connection.chessuci" \
    "$SCRIPT_DIR/cert.pem" \
    "$SCRIPT_DIR/key.pem" \
    "$SCRIPT_DIR/server_secret.key"
do
    if [ -f "$f" ]; then
        rm -f "$f"
        REMOVED_COUNT=$((REMOVED_COUNT + 1))
    fi
done

# Remove log directories
for d in "$SCRIPT_DIR/logs" "$SCRIPT_DIR/__pycache__"; do
    if [ -d "$d" ]; then
        rm -rf "$d"
        REMOVED_COUNT=$((REMOVED_COUNT + 1))
    fi
done

echo "         Removed $REMOVED_COUNT item(s)."

# ── Step 4: Remove Python dependencies ──────────────────────────

echo "  [4/5] Removing Python dependencies..."
pip3 uninstall -y qrcode zeroconf miniupnpc 2>/dev/null || true
echo "         Dependencies removed."

# ── Step 5: Remove server directory ──────────────────────────────

echo "  [5/5] Removing server directory..."
echo ""
echo "  The server directory contains:"
ls -1 "$SCRIPT_DIR" 2>/dev/null | while read -r item; do echo "    $item"; done
echo ""
read -p "  Delete $SCRIPT_DIR and all contents? [y/N] " delete_dir
if [[ "$delete_dir" =~ ^[Yy]$ ]]; then
    # Move out of the directory before deleting
    cd /
    rm -rf "$SCRIPT_DIR"
    echo ""
    echo "  Directory removed."
else
    echo ""
    echo "  Directory kept. You can delete it manually:"
    echo "    rm -rf $SCRIPT_DIR"
fi

# ── Done ─────────────────────────────────────────────────────────

echo ""
echo "  ==========================================="
echo "  Uninstall complete."
echo "  ==========================================="
echo ""
