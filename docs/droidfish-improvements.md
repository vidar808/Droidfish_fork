# DroidFish - Issues & Improvement Proposals

## Overview

This document catalogs known issues, UX gaps, and proposed improvements for DroidFish. Items are organized by priority and complexity.

---

## ~~Critical Improvement: ELO-Based Difficulty for Casual Play~~ IMPLEMENTED

> **Status: DONE** - Implemented as `QuickPlayDialog` in Phase 2. The "Quick Play" option is now the first item in the game mode dialog, providing a single-screen flow for color selection, ELO strength (1320-3190), and time control presets.

### Problem Statement (Original)

DroidFish is a powerful chess analysis and play application, but it lacks an intuitive way for casual users to simply **"play chess against an opponent at a specific difficulty level."** While the app technically supports engine strength limiting, the feature is buried in menus and not presented in a user-friendly way.

**~~Current~~ Previous user journey to play at a specific ELO:**
1. Open left drawer menu
2. Select "Set Strength"
3. Check "Limit Strength" checkbox
4. Adjust ELO slider or type exact value
5. The game mode must also be set to "Play White" or "Play Black"

This requires prior knowledge of UCI engine strength settings and is not discoverable for casual users who just want to play chess.

### Current Implementation

DroidFish already has engine strength limiting infrastructure:

**UI Components:**
- `res/layout/set_strength.xml` - Dialog with checkbox, EditText, and SeekBar
- `DroidFish.java` `setStrengthDialog()` (lines 2088-2186) - Dialog setup
- Left drawer menu item "Set Strength"

**Engine Support:**
- `UCIEngineBase.setEloStrength(elo)` - Sends `UCI_LimitStrength` and `UCI_Elo` to engine
- `DroidComputerPlayer.EloData` - Stores `limitStrength` flag and `elo` value
- Stockfish 18 supported range: **1320-3190 ELO** (calibrated at TC 60s+0.6s)

**Code Path:**
```
DroidFish.setStrengthDialog()
  → DroidChessController.setStrength(limitStrength, elo)
    → DroidComputerPlayer.setStrength(limitStrength, elo)
      → UCIEngineBase.setEloStrength(elo)
        → writeLineToEngine("setoption name UCI_LimitStrength value true")
        → writeLineToEngine("setoption name UCI_Elo value 1800")
```

### Proposed Improvement: "Quick Play" Feature

#### Goal
Add a prominent, intuitive entry point for casual play that combines game mode selection and difficulty setting into a single flow.

#### Design Proposal

**Option A: "Play Chess" Button (Recommended)**

Add a prominent "Play Chess" option as the first item in the left drawer or as a floating action button. When tapped, it presents a streamlined dialog:

```
┌─────────────────────────────────┐
│         Play Chess              │
│                                 │
│  Play as:  ○ White  ○ Black     │
│                                 │
│  Difficulty:                    │
│  ┌─────────────────────────┐    │
│  │ Beginner    (1300 ELO)  │    │
│  │ Easy        (1500 ELO)  │    │
│  │ Medium      (1800 ELO)  │    │
│  │ Hard        (2200 ELO)  │    │
│  │ Expert      (2600 ELO)  │    │
│  │ Maximum     (3190 ELO)  │    │
│  │ Custom ELO: [____]      │    │
│  └─────────────────────────┘    │
│                                 │
│     [Cancel]    [Start Game]    │
└─────────────────────────────────┘
```

This single dialog would:
1. Set game mode to PLAYER_WHITE or PLAYER_BLACK
2. Enable UCI_LimitStrength
3. Set UCI_Elo to the chosen level
4. Start a new game immediately

**Option B: Difficulty Presets in New Game Dialog**

Modify the existing "New Game" dialog to include difficulty presets. Currently the dialog only asks which side to play. Adding difficulty levels here would make the feature discoverable.

#### Implementation Steps

1. Create new layout `res/layout/quick_play.xml` with side selection and difficulty list
2. Add dialog handler in `DroidFish.java`
3. Wire to left drawer menu (insert before "New Game" or replace it)
4. Add corresponding strings to all 14 locale files
5. On "Start Game": call `newGame()` with selected mode, then `setStrength(true, elo)`

#### Difficulty Preset Mapping

| Preset | ELO | Stockfish Behavior |
|--------|-----|-------------------|
| Beginner | 1320 | Minimum strength, many mistakes |
| Easy | 1500 | Club beginner level |
| Casual | 1800 | Average online player |
| Intermediate | 2000 | Strong club player |
| Advanced | 2200 | Candidate Master level |
| Expert | 2500 | International Master level |
| Master | 2800 | Super Grandmaster level |
| Maximum | 3190 | Full Stockfish strength |

### Stockfish ELO Accuracy Considerations

Stockfish's `UCI_LimitStrength` mechanism:
- Calibrated at time control 60 seconds + 0.6 seconds increment
- Uses `Skill Level` internally (maps ELO range to skill 0-20)
- At lower levels, engine deliberately plays suboptimal moves
- Weakness formula: `120 - 2 * level` determines error margin
- Randomized move selection from top-N candidates

**Limitations:**
- Below ~1320 ELO, Stockfish cannot play weaker (minimum skill level)
- The ELO mapping was calibrated on CCRL conditions, may not match human ELO exactly
- At very low levels, moves can feel "random" rather than "human-like"

### Alternative Engines for Better Human-Like Play

If Stockfish's strength limiting feels too artificial at lower levels, consider integrating alternative engines:

#### Maia Chess (Recommended for Human-Like Play)

**Repository:** https://github.com/CSSLab/maia-chess
**License:** GPL-3.0

- Neural network engine trained to play like humans at specific ratings
- Available in fixed-rating models: 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900
- Trained on millions of Lichess games at each rating bracket
- Produces **human-like mistakes and patterns**, not random blunders
- Based on Leela Chess Zero architecture
- Much more realistic opponent for training and casual play

**Integration approach:**
- Download ONNX or LC0 weight files for each rating level
- Bundle as alternative engine alongside Stockfish
- When user selects difficulty 1100-1900, use Maia model
- Above 1900, fall back to Stockfish UCI_Elo

**Pros:**
- Most realistic human-like play at lower levels
- Calibrated per 100-ELO increments
- Research-backed (Cornell University)

**Cons:**
- Only covers 1100-1900 range
- Requires LC0 backend or custom inference
- Larger app size (multiple model files)
- Models may need retraining for specific time controls

#### Alexander Chess Engine

- UCI engine with `UCI_Elo` support, range 1350-2850
- Designed specifically for adjustable strength play
- More natural feeling than Stockfish at low levels
- Smaller and lighter than Stockfish

**Integration approach:**
- Bundle as additional engine binary
- Auto-select when user wants < 2000 ELO play

#### Hybrid Approach (Recommended)

```
ELO Range       Engine Used
──────────────  ────────────────────
1100 - 1900     Maia Chess (human-like play)
1900 - 3190     Stockfish UCI_Elo (strong play)
```

This provides the most natural experience across the full range.

---

## UX Issues

### 1. Monolithic Main Activity
**Severity:** Medium (developer impact)
**File:** `DroidFish.java` (~3,850 lines)

The main activity handles everything: menus, dialogs, game control, file I/O, engine management, preferences, notifications. This makes the code difficult to maintain and test.

**Recommendation:** Refactor into fragments or delegate classes:
- `EngineManagerFragment` - Engine selection and configuration
- `FileManagerDelegate` - PGN/FEN file operations
- `GameDialogDelegate` - New game, strength, mode dialogs
- `AnalysisDelegate` - Thinking display and multi-PV

### 2. Outdated First-Time User Experience
**Severity:** Medium (user impact)

The TourGuide overlay is a legacy approach. Modern Android apps use Material Design onboarding flows or contextual tooltips.

**Recommendation:** Replace with Material Design onboarding that highlights the "Play Chess" flow for new users.

### 3. No Landscape Optimization
**Severity:** Low

The main layout doesn't have a dedicated landscape variant. The `leftHanded` preference only affects landscape orientation but there's no optimized landscape layout.

**Recommendation:** Create `res/layout-land/main.xml` with side-by-side board and move list.

### 4. Menu Depth
**Severity:** Medium (user impact)

Key features require multiple navigation steps:
- Engine strength: Drawer → Set Strength → Dialog
- Engine selection: Drawer → Manage Engines → Dialog → Sub-dialog
- Opening book: Drawer → Select Book → File picker

**Recommendation:** Add quick-access toolbar or bottom sheet for common actions.

---

## Technical Issues

### ~~5. No Authentication on Network Engine Connection~~ IMPLEMENTED
**Severity:** High (security) | **Status: DONE**

~~`NetworkEngine.java` connects via plain TCP with no authentication or encryption. Any entity on the network can intercept or inject UCI commands.~~

**Implemented:**
- TLS encryption via `SSLSocket` (toggle in config dialog)
- Token-based authentication (AUTH_REQUIRED/AUTH/AUTH_OK handshake)
- 14-line NETE config format stores TLS, auth, relay, and engine selection
- Chess-UCI-Server also supports TLS and token auth on its side

### 6. Engine Process Management
**Severity:** Medium

`ExternalEngine.java` uses reflection to access private `pid` field for `reNice()`. This is fragile and may break on newer Android versions or non-standard Process implementations.

**Recommendation:** Use `Process.pid()` (available since Java 9 / Android API 26+, compatible with minSdk 21 via try-catch fallback).

### 7. Memory Management for Large PGN Files
**Severity:** Medium

Loading large PGN databases loads the entire game tree into memory. No lazy loading or pagination.

**Recommendation:** Implement PGN indexing for large files, load games on demand.

### 8. Hardcoded String Constants
**Severity:** Low

Some UI strings and engine identifiers are hardcoded rather than using string resources:
- Engine names (`"stockfish"`)
- File format identifiers (`"NETE"`)
- Dialog button labels in some code paths

**Recommendation:** Extract to `strings.xml` for internationalization.

---

## Feature Gaps

### 9. No Online Play
**Severity:** Medium (feature gap)

DroidFish has no built-in support for online chess servers (Lichess, Chess.com). Users can only play against local engines or network engines they configure themselves.

**Recommendation:** Consider Lichess API integration (open-source, free API) for:
- Casual online games
- Puzzle training
- Opening explorer

### ~~10. No Engine Discovery~~ IMPLEMENTED
**Severity:** Medium (feature gap) | **Status: DONE**

~~Users must manually enter host:port for network engines; no auto-discovery.~~

**Implemented:**
- mDNS auto-discovery via Android `NsdManager` (discovers `_chess-uci._tcp` services)
- "Discover" button in network engine config dialog with 3-second scan
- QR code scanning via ZXing library for instant pairing with Chess-UCI-Server
- Server-side mDNS advertisement via zeroconf + QR code generation
- "Import Connection File" button opens SAF file picker for `.chessuci` files (generated by server `--pair` mode)

### 10b. No Puzzle/Training Mode
**Severity:** Medium (feature gap)

No built-in tactical puzzles or training exercises. The app is purely for playing and analyzing games.

**Recommendation:** Add puzzle mode with:
- Bundled tactical puzzles (Lichess puzzle database is CC0)
- "Find the best move" challenges
- Rating-based puzzle selection

### 11. No Game Database Browser
**Severity:** Low (feature gap)

While DroidFish can load PGN files, there's no database browser for managing a collection of games. Users must use external apps or SCID.

**Recommendation:** Add a simple game list view with search/filter by player, date, result, ECO code.

### 12. No Cloud Sync
**Severity:** Low (feature gap)

Game state and preferences are device-local only. No backup or sync across devices.

**Recommendation:** Optional Google Drive or local backup/restore for settings and saved games.

---

## Performance Improvements

### 13. Engine Startup Time
**Severity:** Low

`ExternalEngine.copyFile()` copies the engine binary on every startup if the file has changed. NNUE network loading also adds to startup time.

**Recommendation:** Cache engine binaries with content hash verification instead of size+timestamp check.

### 14. UI Thread Blocking
**Severity:** Low

Some operations in `DroidFish.java` (file I/O for PGN, preferences reading) run on the UI thread.

**Recommendation:** Move file I/O to background threads using `AsyncTask` replacement (Kotlin coroutines or `java.util.concurrent`).

---

## Summary: Priority Matrix

| # | Improvement | Impact | Effort | Priority | Status |
|---|-------------|--------|--------|----------|--------|
| - | Quick Play / ELO Difficulty | High | Medium | **P0** | **DONE** |
| 5 | Network Authentication | High | High | P1 | **DONE** |
| 10 | Engine Discovery (mDNS + QR) | Medium | Medium | P2 | **DONE** |
| 1 | Refactor Main Activity | Medium | High | P1 | Open |
| 4 | Menu Depth Reduction | Medium | Medium | P2 | Open |
| 9 | Online Play (Lichess) | Medium | High | P2 | Open |
| 10b | Puzzle Mode | Medium | Medium | P2 | Open |
| 2 | Onboarding Refresh | Medium | Medium | P3 | Open |
| 6 | Process.pid() Migration | Medium | Low | P3 | Open |
| 7 | Large PGN Handling | Medium | Medium | P3 | Open |
| 3 | Landscape Layout | Low | Medium | P3 | Open |
| 8 | String Extraction | Low | Low | P4 | Open |
| 11 | Game Database Browser | Low | Medium | P4 | Open |
| 12 | Cloud Sync | Low | High | P4 | Open |
| 13 | Engine Startup | Low | Low | P4 | Open |
| 14 | UI Thread Optimization | Low | Medium | P4 | Open |
