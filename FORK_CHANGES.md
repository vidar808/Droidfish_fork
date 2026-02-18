# DroidFish Fork — Changes from Upstream

**Upstream**: [peterosterlund2/droidfish](https://github.com/peterosterlund2/droidfish)
**Original Author**: Peter Osterlund
**License**: GPL-3.0 (unchanged)

This document lists all modifications made in this fork relative to the upstream DroidFish project.

---

## Build System

- **Gradle**: Updated to 8.4 / AGP 8.2.0
- **Target/Compile SDK**: 34 (was 33)
- **NDK**: 25.1.8937393
- **Version**: `1.90-custom`
- **Application ID**: `org.petero.droidfish.custom`
- **Dependency added**: ZXing QR scanner (`com.journeyapps:zxing-android-embedded:4.3.0`)
- **Dependency added**: AndroidX Lifecycle ViewModel (`lifecycle-viewmodel:2.6.2`)
- **Data binding**: Enabled
- **New Gradle tasks**: `copyToAssets`, `copyToJniLibs` for engine binary management

## Engines

### Stockfish 18
- Updated from upstream's bundled version to Stockfish 18
- Android.mk updated: `-DUSE_NEON=8` for proper ARM NEON support
- NEON dotprod instructions enabled for ARMv8.2+

### Rodent IV (new)
- Full source in `src/main/cpp/rodent/` (~30 source files)
- Compiled with C++14, O3, LTO, ARM NEON
- Configurable personality engine with UCI support

### Patricia (new)
- Full source in `src/main/cpp/patricia/`
- Compiled with C++20
- Includes Fathom tablebase library (`fathom/src/tbprobe.c`)

### CuckooChess (removed)
- Built-in Java engine removed entirely
- All references cleaned up

## New Java Files (9 files)

### UI & Architecture
| File | Purpose |
|------|---------|
| `GameViewModel.java` | MVVM lifecycle persistence — holds DroidChessController across config changes |
| `QuickPlayDialog.java` | One-tap game setup: ELO slider (1320–3190), time control presets, color selection |

### Lichess Opening Explorer
| File | Purpose |
|------|---------|
| `OpeningExplorerActivity.java` | Dedicated activity for Lichess Opening Explorer |
| `LichessExplorerBook.java` | Lichess API client with LRU cache (128 entries, 5-min TTL) and rate limiting |
| `ChessBoardExplorer.java` | Interactive board with tap-to-move for explorer |
| `ExplorerMoveAdapter.java` | ListView adapter showing move stats (win/draw/loss) |
| `WDLBarView.java` | Win/Draw/Loss percentage bar (Lichess dark theme style) |

### Network Engine Enhancements
| File | Purpose |
|------|---------|
| `NetworkDiscovery.java` | NsdManager-based mDNS discovery for `_chess-uci._tcp` services |
| `NetworkFileLogger.java` | Network engine debug logging utility |

## Modified Java Files

### NetworkEngine.java
Major extension of the upstream network engine:
- **TLS encryption**: Optional SSL socket wrapping with certificate fingerprint validation
- **Token authentication**: `AUTH_REQUIRED` / `AUTH` / `AUTH_OK` handshake
- **PSK authentication**: Alternative pre-shared key method
- **Engine selection**: `ENGINE_LIST` / `SELECT_ENGINE` for single-port servers
- **Relay support**: Connect through relay server for NAT traversal
- **Smart connection**: mDNS (1.5s) -> LAN (2s) -> UPnP (5s) -> relay (10s) -> retry
- **Reconnection**: Exponential backoff, up to 5 attempts
- **Position tracking**: Records last position for recovery after reconnect
- **14-line NETE config**: Extended from 5-line (name, host, port, tls, token, fingerprint, auth_method, psk, relay_host, relay_port, relay_session, external_host, mdns_name, selected_engine)

### NetworkEngineConfig.java
- QR code scanning button (ZXing integration)
- mDNS discovery button ("Find Servers")
- Fetch Engines button for single-port mode
- `.chessuci` connection file import (`handleChessUciImport`)
- Extended config fields for TLS, auth, relay, engine selection

### DroidFish.java (main activity)
- Quick Play dialog integration
- Opening Explorer launch
- GameViewModel integration for state persistence
- `.chessuci` intent handling

### PGNFile.java
- Migrated to Storage Access Framework (SAF)
- Supports `content://` URIs for Android 11+ compatibility

### AndroidManifest.xml
- `MANAGE_EXTERNAL_STORAGE` permission (Android 11+)
- `OpeningExplorerActivity` registration
- `.chessuci` file association (intent filter)
- Camera permission for QR scanning

## New Layout Resources

| File | Purpose |
|------|---------|
| `activity_opening_explorer.xml` | Opening Explorer activity layout |
| `explorer_move_row.xml` | Move statistics row in explorer list |
| `quick_play_dialog.xml` | Quick Play dialog layout |

## Documentation

- **`doc/droidfish_manual.md`**: Full markdown manual (converted from PDF, updated for fork)
- **`doc/droidfish_manual.pdf`**: Regenerated 15-page PDF from markdown

## What's Unchanged

- Core chess logic (game tree, move generation, PGN parsing, FEN handling)
- Board rendering and piece graphics
- Opening book support (Polyglot, CTG, ABK)
- Endgame tablebase support (Syzygy, Gaviota)
- Analysis mode and Multi-PV display
- Board editor
- ECO classification
- Localization (15+ languages, original strings preserved)
- EngineServer module (built-in Java server)
- GPL-3.0 license
