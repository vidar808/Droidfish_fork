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
- **New Gradle task**: `copyToJniLibs` copies engine binaries as `lib*.so` to `src/main/jniLibs/` so Android extracts them to `nativeLibraryDir` (which has execute permission on Android 10+)

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
- Replaced 6-step TourGuide overlay with a simple welcome dialog pointing to About/manual

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

- **`docs/droidfish_manual.md`**: Full markdown manual (converted from PDF, updated for fork)
- **`docs/droidfish_manual.pdf`**: Regenerated 15-page PDF from markdown

## Bug Fixes

### LichessExplorerBook Executor Crash
- `LichessExplorerBook` held a `final ExecutorService` that was permanently killed on `onDestroy()` via `shutdownNow()`
- Since `DroidBook` is a singleton, the dead executor persisted across activity recreations
- `fetchAsync()` would crash with `RejectedExecutionException` on next activity start
- **Fix:** Executor is now lazily recreated via `getExecutor()` if it was shut down

### Opening Book Defaults
- `bookFile` preference defaulted to empty string (no book selected on fresh install)
- `bookHints` preference defaulted to `false` (no book arrows on fresh install)
- **Fix:** Defaults changed to `"internal:"` and `true` respectively

### Lichess Explorer Empty Results
- `formatExplorerHtml()` displayed "Explorer" header even with no data, preventing local book info from showing
- Failed API requests cached for full 5 minutes
- **Fix:** Return empty string for empty results; added 30-second TTL for failed fetches

### Lichess Fallback in getAllBookMoves
- `getAllBookMoves()` (used for arrows/hints) had no fallback to local book when Lichess returned null
- **Fix:** Added fallback logic matching what `getBookMove()` already had

### Lichess Blocking Path Repeated Timeouts
- `getBookEntriesBlocking()` (used by engine for computer play) only cached successful Lichess fetches
- On timeout, offline, or rate limiting, the same position paid the full 5s network penalty every time before falling back to local book
- The async path already had negative-result caching, but the blocking path did not
- **Fix:** Cache failed/null results as empty `ExplorerResult` with 30s TTL, matching the async path pattern

### Welcome Dialog Cancel Behavior
- The replacement welcome dialog only cleared the `guideShowOnStart` flag on the positive button
- If the user backed out or tapped outside, the dialog returned on every launch
- **Fix:** Added `setOnCancelListener` to also clear the flag on dismiss

## Code Cleanup

### Dead Code Removal
- **InternalStockFish.java**: Removed `readCheckSum()`, `writeCheckSum()`, and `computeAssetsCheckSum()` — leftover from the old asset-extraction approach, unused since engines now load from `nativeLibraryDir`
- Removed unused imports (`DataInputStream`, `DataOutputStream`, `FileInputStream`, `MessageDigest`, `NoSuchAlgorithmException`)

### Build System Cleanup
- **Removed `copyToAssets` Gradle task**: Engine binaries were being copied to both `src/main/assets/` and `src/main/jniLibs/`. Since runtime loads engines from `nativeLibraryDir` (jniLibs), the assets copy was dead weight adding ~30MB to the APK
- **Removed stale engine binaries**: Deleted 15 generated engine binaries left in `src/main/assets/` from previous builds (stockfish, stockfish_nosimd, rodent4, patricia across 4 ABIs)
- **Updated `.gitignore`**: Added patterns for stale asset engine binaries to prevent future accumulation

### Unit Test Fix
- **`LichessExplorerBookTest.testFormatExplorerHtmlEmptyOpening`**: Updated assertion to match current implementation — `formatExplorerHtml()` now returns `""` for empty results, not `"<b>Explorer</b>"`

## QA Test Suite

Comprehensive Espresso UI test suite in `DroidFishApp/src/androidTest/java/org/petero/droidfish/ui/`:

| Test Class | Tests | Coverage |
|-----------|-------|----------|
| `MainActivityLaunchTest` | 7 | Activity launch, board/buttons/status visibility |
| `ChessBoardInteractionTest` | 4 | Touch moves, undo/redo, multi-move sequences |
| `GameModeTest` | 6 | All game mode switching |
| `OpeningBookDisplayTest` | 4 | Book info, ECO names, analysis mode |
| `EngineAnalysisTest` | 4 | Engine output, mode switching |
| `SettingsNavigationTest` | 5 | Drawer menu, settings, new game, explorer |
| `ScreenshotCaptureTest` | 5 | Visual regression screenshots |

**Supporting infrastructure:**
- `BoardTestUtils.java` — Chess square tap helper for Espresso
- `DisableTourGuideRule.java` — Disables first-launch tour guide for tests
- `qa/run_tests.sh` — Full test runner (emulator setup, build, test, screenshots)
- `qa/visual_diff.py` — Screenshot comparison with configurable threshold
- `qa/capture_and_validate.sh` — Pull and compare device screenshots

## What's Unchanged

- Core chess logic (game tree, move generation, PGN parsing, FEN handling)
- Board rendering and piece graphics
- Opening book support (Polyglot, CTG, ABK)
- Endgame tablebase support (Syzygy, Gaviota)
- Analysis mode and Multi-PV display
- Board editor
- ECO classification
- Localization (15+ languages, original strings preserved)
- ~~EngineServer module~~ (removed — replaced by chess-uci-server)
- GPL-3.0 license
