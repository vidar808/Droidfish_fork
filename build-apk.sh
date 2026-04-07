#!/usr/bin/env bash
#
# build-apk.sh - Build DroidFish APK from source
#
# Downloads and configures Android SDK + NDK, then runs the Gradle build.
# Produces a debug APK (no signing key required) or a release APK
# (if signing properties are provided).
#
# Usage:
#   ./build-apk.sh              # debug APK
#   ./build-apk.sh release      # unsigned release APK
#   ./build-apk.sh clean        # clean build artifacts
#
# Prerequisites: Java 17+ (JDK), curl, unzip
#
# Output: droidfish/DroidFishApp/build/outputs/apk/

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/droidfish"
SDK_DIR="$SCRIPT_DIR/.android-sdk"
CMDLINE_TOOLS_VERSION="11076708"  # Latest command-line tools (Jan 2025)
NDK_VERSION="25.1.8937393"
BUILD_TOOLS_VERSION="34.0.0"
PLATFORM_VERSION="android-34"

export ANDROID_HOME="$SDK_DIR"
export ANDROID_SDK_ROOT="$SDK_DIR"
export PATH="$SDK_DIR/cmdline-tools/latest/bin:$SDK_DIR/platform-tools:$PATH"

# ── Functions ──────────────────────────────────────────────────────────

log() { echo -e "\033[1;34m[build]\033[0m $*"; }
err() { echo -e "\033[1;31m[error]\033[0m $*" >&2; }

check_java() {
    if ! command -v java &>/dev/null; then
        err "Java not found. Install JDK 17+ and try again."
        exit 1
    fi
    local ver
    ver=$(java -version 2>&1 | head -1 | grep -oP '(?<=")[0-9]+' | head -1)
    if [[ "$ver" -lt 17 ]]; then
        err "Java $ver found, but JDK 17+ is required."
        exit 1
    fi
    log "Java $ver OK"
}

install_sdk() {
    if [[ -x "$SDK_DIR/cmdline-tools/latest/bin/sdkmanager" ]]; then
        log "Android SDK already installed at $SDK_DIR"
        return
    fi

    log "Downloading Android command-line tools..."
    mkdir -p "$SDK_DIR/cmdline-tools"
    local zip_file="$SDK_DIR/cmdline-tools.zip"
    curl -fSL -o "$zip_file" \
        "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS_VERSION}_latest.zip"

    log "Extracting command-line tools..."
    unzip -q "$zip_file" -d "$SDK_DIR/cmdline-tools"
    # The zip extracts to "cmdline-tools/", we need it at "cmdline-tools/latest/"
    mv "$SDK_DIR/cmdline-tools/cmdline-tools" "$SDK_DIR/cmdline-tools/latest"
    rm "$zip_file"

    log "Android command-line tools installed."
}

install_sdk_packages() {
    log "Accepting licenses..."
    yes 2>/dev/null | sdkmanager --licenses >/dev/null 2>&1 || true

    log "Installing SDK packages (this may take a few minutes)..."
    sdkmanager --install \
        "platform-tools" \
        "platforms;$PLATFORM_VERSION" \
        "build-tools;$BUILD_TOOLS_VERSION" \
        "ndk;$NDK_VERSION" \
        2>&1 | grep -E "^(Installed|Installing|  )" || true

    log "SDK packages installed."
}

verify_sdk() {
    local missing=()
    [[ -d "$SDK_DIR/platforms/$PLATFORM_VERSION" ]] || missing+=("platforms;$PLATFORM_VERSION")
    [[ -d "$SDK_DIR/build-tools/$BUILD_TOOLS_VERSION" ]] || missing+=("build-tools;$BUILD_TOOLS_VERSION")
    [[ -d "$SDK_DIR/ndk/$NDK_VERSION" ]] || missing+=("ndk;$NDK_VERSION")

    if [[ ${#missing[@]} -gt 0 ]]; then
        err "Missing SDK components: ${missing[*]}"
        return 1
    fi
    log "All SDK components verified."
}

do_clean() {
    log "Cleaning build artifacts..."
    cd "$PROJECT_DIR"
    ./gradlew clean 2>&1
    log "Clean complete."
}

do_build() {
    local build_type="${1:-debug}"
    cd "$PROJECT_DIR"

    # Set ANDROID_HOME in local.properties for Gradle
    echo "sdk.dir=$SDK_DIR" > local.properties
    echo "ndk.dir=$SDK_DIR/ndk/$NDK_VERSION" >> local.properties

    log "Building $build_type APK..."
    log "This will compile native Stockfish + Java sources. First build takes ~5-10 min."

    if [[ "$build_type" == "release" ]]; then
        ./gradlew assembleRelease 2>&1
        local apk_dir="$PROJECT_DIR/DroidFishApp/build/outputs/apk/release"
    else
        ./gradlew assembleDebug 2>&1
        local apk_dir="$PROJECT_DIR/DroidFishApp/build/outputs/apk/debug"
    fi

    echo ""
    log "──────────────────────────────────────────────────"
    log "Build complete!"
    if [[ -d "$apk_dir" ]]; then
        log "APK location:"
        ls -lh "$apk_dir"/*.apk 2>/dev/null | while read -r line; do
            log "  $line"
        done
    fi
    log "──────────────────────────────────────────────────"
}

# ── Main ───────────────────────────────────────────────────────────────

main() {
    local cmd="${1:-debug}"

    log "DroidFish APK Builder"
    log "Project: $PROJECT_DIR"

    if [[ "$cmd" == "clean" ]]; then
        do_clean
        exit 0
    fi

    check_java
    install_sdk
    install_sdk_packages
    verify_sdk
    do_build "$cmd"
}

main "$@"
