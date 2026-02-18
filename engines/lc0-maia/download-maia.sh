#!/bin/bash
# Download Lc0 binary and Maia weight files for DroidFish
# Usage: ./download-maia.sh [output_dir]
#
# This creates a ready-to-copy lc0-maia folder with:
#   - lc0 binary (arm64-v8a)
#   - 9 Maia weight files (1100-1900)
#   - engine.json manifest (already present)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${1:-$SCRIPT_DIR}"

MAIA_WEIGHTS_BASE="https://github.com/CSSLab/maia-chess/raw/master/maia_weights"
MAIA_LEVELS="1100 1200 1300 1400 1500 1600 1700 1800 1900"

echo "=== Maia Chess Engine Downloader ==="
echo "Output directory: $OUTPUT_DIR"
echo ""

# Download Maia weight files
echo "--- Downloading Maia weight files ---"
for level in $MAIA_LEVELS; do
    FILE="maia-${level}.pb.gz"
    if [ -f "$OUTPUT_DIR/$FILE" ]; then
        echo "  [skip] $FILE (already exists)"
    else
        echo "  [download] $FILE"
        curl -L -o "$OUTPUT_DIR/$FILE" "$MAIA_WEIGHTS_BASE/$FILE"
    fi
done

echo ""
echo "--- Lc0 binary ---"
if [ -f "$OUTPUT_DIR/lc0" ]; then
    echo "  [skip] lc0 binary already exists"
else
    echo "  Lc0 must be downloaded manually:"
    echo "    1. Go to https://github.com/LeelaChessZero/lc0/releases"
    echo "    2. Download the Android arm64-v8a build"
    echo "    3. Rename the binary to 'lc0' and place it in: $OUTPUT_DIR/"
    echo ""
    echo "  Alternatively, build from source:"
    echo "    git clone https://github.com/LeelaChessZero/lc0.git"
    echo "    cd lc0 && ./build.sh  # with Android NDK cross-compilation"
fi

echo ""
echo "=== Done ==="
echo ""
echo "To install on your device:"
echo "  adb push $OUTPUT_DIR/ /sdcard/DroidFish/uci/lc0-maia/"
