# Lc0 + Maia Chess Engine Package

[Maia](https://maiachess.com/) is a human-like chess engine trained on millions
of Lichess games. It plays at specific Elo levels (1100-1900) by predicting
what a human of that rating would play, rather than finding the objectively
best move.

Maia runs on [Lc0](https://lc0.org/) (Leela Chess Zero), a neural network
chess engine.

## Requirements

- Android device with arm64-v8a architecture (most modern devices)
- ~15 MB storage (Lc0 binary + 9 weight files at ~1.2 MB each)

## Quick Setup

Run the download script to fetch everything:

```bash
./download-maia.sh
```

Then copy the resulting folder to your device:

```bash
adb push lc0-maia/ /sdcard/DroidFish/uci/lc0-maia/
```

## Manual Setup

1. **Download Lc0 for Android** from
   [Lc0 releases](https://github.com/LeelaChessZero/lc0/releases).
   You need the `arm64-v8a` binary. Rename it to `lc0` and place it here.

2. **Download Maia weight files** from
   [CSSLab maia-chess](https://github.com/CSSLab/maia-chess/tree/master/maia_weights).
   Download all 9 files (`maia-1100.pb.gz` through `maia-1900.pb.gz`).

3. Copy this entire `lc0-maia/` folder to `/sdcard/DroidFish/uci/` on your device.

4. Open DroidFish and select any "Maia XXXX" engine from the engine list.

## How It Works

The `engine.json` manifest configures Lc0 with:
- **Eigen backend**: CPU-only, no GPU required
- **Single node search** (`go nodes 1`): Maia outputs the most human-like move
  from its first evaluation, without tree search
- **Per-level weights**: Each Elo level uses a different neural network
- Hidden options: Backend-specific settings are hidden from the UI
