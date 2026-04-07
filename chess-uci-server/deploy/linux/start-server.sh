#!/bin/bash
# Chess UCI Server - Start Script
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  Chess UCI Server - Start"
echo "  ========================"
echo ""

# ── Pre-flight checks ───────────────────────────────────────────

if ! command -v python3 &> /dev/null; then
    echo "  ERROR: Python 3 is not installed."
    echo "  Run install.sh first, or install Python manually."
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/chess.py" ]; then
    echo "  ERROR: chess.py not found in $SCRIPT_DIR"
    echo "  Run install.sh first."
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/config.json" ]; then
    echo "  ERROR: config.json not found."
    echo "  Run install.sh to generate a config, or copy example_config.json to config.json."
    exit 1
fi

# ── Check if already running ────────────────────────────────────

PID_FILE="$SCRIPT_DIR/chess-uci-server.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "  Server is already running (PID $OLD_PID)."
        echo "  Use ./stop-server.sh to stop it first."
        exit 1
    else
        echo "  Removing stale PID file..."
        rm -f "$PID_FILE"
    fi
fi

# ── Parse arguments ─────────────────────────────────────────────

EXTRA_ARGS=""
PAIR_FLAG=""

for arg in "$@"; do
    case "$arg" in
        --pair)       PAIR_FLAG="--pair" ;;
        --background) ;; # handled below
        *)            EXTRA_ARGS="$EXTRA_ARGS $arg" ;;
    esac
done

# ── Start ────────────────────────────────────────────────────────

if echo "$@" | grep -q -- "--background"; then
    echo "  Starting server in background..."
    if [ -n "$PAIR_FLAG" ]; then
        # Show QR first, then background the server
        python3 chess.py --pair-only $EXTRA_ARGS 2>/dev/null || true
        echo ""
    fi
    nohup python3 chess.py $EXTRA_ARGS > "$SCRIPT_DIR/server.log" 2>&1 &
    sleep 1
    if [ -f "$PID_FILE" ]; then
        echo "  Server started (PID $(cat "$PID_FILE"))"
        echo "  Log: $SCRIPT_DIR/server.log"
    else
        echo "  Server started (PID $!)"
        echo "  Log: $SCRIPT_DIR/server.log"
    fi
else
    echo "  Starting server..."
    echo "  Press Ctrl+C to stop."
    echo ""
    exec python3 chess.py $PAIR_FLAG $EXTRA_ARGS
fi
