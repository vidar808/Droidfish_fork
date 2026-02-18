# Drop-in Engine Packages

DroidFish supports installing additional chess engines by placing them in the
`/sdcard/DroidFish/uci/` folder on your Android device. Engines can live in
sub-folders with an optional `engine.json` manifest for pre-configuration.

## Structure

```
/sdcard/DroidFish/uci/
  stockfish_16          # flat file: appears as-is in engine list
  lc0-maia/             # sub-folder with manifest
    engine.json          # manifest: defines display names, UCI options, variants
    lc0                  # engine binary (arm64)
    maia-1100.pb.gz      # weight file (data, not shown as engine)
    maia-1500.pb.gz
    ...
```

## Available Packages

| Package | Description | Folder |
|---------|-------------|--------|
| [Lc0 + Maia](lc0-maia/) | Human-like chess at 9 Elo levels (1100-1900) | `lc0-maia/` |

## How It Works

- **Without `engine.json`**: Files in a sub-folder appear as engines (data files
  like `.pb.gz`, `.bin`, `.nnue` are excluded automatically).
- **With `engine.json`**: The manifest defines the binary, forced UCI options,
  hidden options, and optional variants. Each variant appears as a separate
  engine in the selection dialog.

## Installing a Package

1. Download or build the engine binary for your device's architecture (usually `arm64-v8a`).
2. Copy the entire folder (e.g., `lc0-maia/`) to `/sdcard/DroidFish/uci/` on your device.
3. Open DroidFish, tap the engine name, and select from the list.
