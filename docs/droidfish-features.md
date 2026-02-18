# DroidFish Application - Complete Feature Documentation

## Overview

DroidFish is a feature-rich, open-source Android chess application (GPL-3.0) originally developed by Peter Osterlund. It provides a full-featured chess interface supporting UCI-compatible engines, opening books, endgame tablebases, PGN import/export, network engine play, and extensive UI customization.

**Key Stats:**
- Main activity: `DroidFish.java` (~3,850 lines)
- Architecture: MVC pattern (DroidChessController / Game+GameTree / GUIInterface)
- Engine protocol: UCI (Universal Chess Interface)
- Built-in engine: Stockfish 18 (via JNI)
- Min SDK: 21 (Android 5.0) / Target SDK: 34

---

## 1. User Interface Layout

### Main Screen

The main UI (`res/layout/main.xml`) consists of:

| Component | Description |
|-----------|-------------|
| **Title Bar** | Shows engine name, player names, or opening ECO code |
| **Second Title Line** | Material difference display (captured pieces) |
| **Chess Board** | Interactive `ChessBoardPlay` view with touch/drag input |
| **Move List** | Scrollable `MoveListView` showing game notation |
| **Thinking Info** | Engine analysis output (PV lines, scores, depth) |
| **Button Row** | 6 buttons: 3 custom + Mode + Undo + Redo |
| **Left Drawer** | Main menu (New Game, Settings, etc.) |
| **Right Drawer** | Game actions (Resign, Force Move, Draw) |

### Navigation Drawers

**Left Drawer Menu:**
1. New Game - Start fresh game with side selection
2. Set Strength - Adjust engine ELO/playing strength
3. Edit Board - Manual position setup via `EditBoard` activity
4. File Menu - Load/save PGN, FEN, SCID files
5. Select Book - Choose opening book
6. Manage Engines - Engine selection and configuration
7. Set Color Theme - Board appearance presets
8. Settings - Full preferences screen
9. About - Version and license info

**Right Drawer Menu:**
1. Resign - Resign current game
2. Force Move - Stop engine thinking, play current best
3. Draw - Offer or claim draw

### Button Row

Six bottom buttons, three of which are user-configurable:

| Button | Default Action | Long-Press |
|--------|---------------|------------|
| Custom 1 | Flip Board | Submenu (headers, comments, arrows, book/TB hints) |
| Custom 2 | Toggle Analysis | Submenu (select engine, engine options) |
| Custom 3 | Load Last File | Submenu (load game) |
| Mode | Game mode dialog | - |
| Undo | Go back one move | Go-back menu (start, variation start, auto-backward) |
| Redo | Go forward one move | Go-forward menu (end, next variation, auto-forward) |

Each custom button supports 7 configurable action slots (1 main + 6 submenu).

**Available Button Actions:**
`flipboard`, `showThinking`, `bookHints`, `tbHints`, `viewVariations`, `viewComments`, `viewHeaders`, `toggleAnalysis`, `forceMove`, `largeButtons`, `blindMode`, `loadLastFile`, `loadGame`, `selectEngine`, `engineOptions`, `toggleArrows`, `prevGame`, `nextGame`

---

## 2. Game Modes

Seven game modes available via the Mode button (Quick Play + 6 standard modes):

| Mode | ID | Description | Clocks |
|------|----|-------------|--------|
| **Quick Play** | - | One-tap game setup with ELO, time, color | Active |
| Play White | 1 | Human plays white vs computer | Active |
| Play Black | 2 | Human plays black vs computer | Active |
| Two Players | 3 | Human vs human on same device | Active |
| Analysis | 4 | Engine continuously analyzes position | Stopped |
| Two Computers | 5 | Watch two engines play each other | Active |
| Edit/Replay Game | 6 | Browse and edit game moves | Stopped |

### Quick Play Dialog

The Quick Play dialog (`QuickPlayDialog.java`) provides a streamlined game setup flow:

| Setting | Options | Default |
|---------|---------|---------|
| **Color** | White / Black radio buttons | White |
| **ELO Strength** | Slider 1320-3190 (Stockfish UCI_Elo range) | 2255 (midpoint) |
| **Time Control** | Bullet (1m), Blitz (3m, 5m), Rapid (10m, 15+10), Classical (30m), No limit | 5 min |

On "Start Game", the dialog:
1. Sets game mode to PLAYER_WHITE or PLAYER_BLACK
2. Enables `UCI_LimitStrength` and sets `UCI_Elo`
3. Configures the selected time control
4. Starts a new game immediately

### Mode Behavior Details

- **Play White/Black**: Engine thinks on its turn; optional pondering on human's turn
- **Two Players**: Both sides human-controlled, clocks run, no engine
- **Analysis**: Both sides human-controlled, engine provides continuous multi-PV analysis
- **Two Computers**: Engine plays both sides automatically
- **Edit/Replay**: Manual navigation through game tree, no engine involvement

---

## 3. Chess Board Features

### Move Input Methods
- **Tap-Tap**: Tap source square, then destination square
- **Drag & Drop**: Drag piece from source to destination
- **One-Touch Mode**: Source and destination can be tapped in any order
- **Toggle Selection**: Alternative square selection behavior (sticky vs toggle)

### Visual Features
- **Board Flip**: Manual toggle or automatic based on player name / side to move
- **Last Move Highlight**: Rectangle around last moved piece
- **Square Labels**: A-H and 1-8 coordinate display
- **Move Arrows**: Configurable (0-8) arrows showing engine thinking
- **Book Hints**: Visual indicators for opening book moves
- **Tablebase Hints**: Endgame evaluation decorations on legal moves
- **ECO Display**: Opening classification (Off / Auto / Always)
- **Blind Mode**: Hide all pieces (blindfold training)
- **Piece Animation**: Animated piece movements between squares
- **Material Difference**: Show captured piece advantage in title bar

### Piece Sets
17 available piece styles: chesscases (default), alfonso, alpha, cburnett, chessicons, chessmonk, freestaunton, kilfiger, leipzig, magnetic, maya, merida, merida_new, metaltops, pirat, regular, wikimedia

### Color Themes
7 predefined themes: Original, XBoard, Blue (default), Grey, Scid Default, Scid Brown, Scid Green. Plus full individual color customization for 18+ color properties.

---

## 4. Engine System

### Built-in Engine
- **Stockfish 18** (bundled via JNI, C++ compiled for ARM/x86)
- NNUE evaluation with two network files
- Supports all standard UCI options (Hash, Threads, MultiPV, etc.)

### External Engine Support
- **Open Exchange Engines (OEX)**: Third-party Android UCI engines installed as apps
- **Custom UCI Engines**: User-installed engine binaries on device storage
- **Network Engines**: Remote UCI engines via TCP socket connection

### Network Engine Configuration
- Create/edit/delete network engine profiles
- Each profile stores connection parameters including host, port, TLS, auth, relay, and engine selection
- Configuration saved as `.ini` files in 14-line NETE format:
  ```
  NETE
  <host>
  <port>
  <tls|notls>
  <auth_token>
  <fingerprint>
  <auth_method>
  <psk>
  <relay_host>
  <relay_port>
  <relay_session>
  <external_host>
  <mdns_name>
  <selected_engine>
  ```
- Connects via TCP socket with optional TLS encryption
- Optional token-based authentication (AUTH_REQUIRED/AUTH/AUTH_OK handshake)
- Automatic reconnection with exponential backoff (up to 5 attempts, 1s-30s)
- Position tracking for future recovery after reconnect

### Network Engine Discovery
- **QR Code Scanning**: Scan QR codes generated by Chess-UCI-Server to auto-fill connection details. Uses ZXing library (`zxing-android-embedded:4.3.0`). Parses JSON payload with host, engines, TLS, token fields.
- **mDNS Auto-Discovery**: "Discover" button uses Android `NsdManager` to find `_chess-uci._tcp` services on the local network. 3-second scan, presents found servers in a selection dialog. Extracts host, port, TLS, and auth properties from service TXT records.
- **Import Connection File**: "Import Connection File" button opens the Android SAF file picker to select a `.chessuci` file. The server's `--pair` mode generates this file. On import, DroidFish creates NETE config profiles for each engine in the file. Validates the file extension before importing.

### Engine Strength Control
- **UCI_LimitStrength**: Checkbox to enable ELO-based strength limiting
- **UCI_Elo**: Slider to set target ELO rating
- Stockfish 18 range: 1320-3190 ELO (calibrated at TC 60s+0.6s)
- Accessible via Left Drawer > "Set Strength"

### Engine Options
- **Hash Table**: 16 MB to 16,384 MB
- **Ponder Mode**: Think on opponent's time
- **Multi-PV**: 1-100 principal variations for analysis
- **Custom UCI Options**: Editable via Engine Options dialog
- Options persisted in `.ini` files per engine

---

## 5. Opening Book System

### Supported Formats
- **Polyglot (.bin)**: Standard binary opening book format
- **CTG**: ChessBase format
- **ABK**: Arena format

### Built-in Books
- **Internal Book**: Default built-in opening database
- **ECO Book**: Encyclopedia of Chess Openings classification data

### Book Options
| Option | Default | Description |
|--------|---------|-------------|
| Max Length | Unlimited | Maximum book depth in plies |
| Prefer Main Lines | Off | Favor popular/main moves |
| Tournament Mode | Off | Ignore non-tournament moves |
| Randomness | 0.0 | Move selection variability (-3.0 to +3.0) |

---

## 6. Endgame Tablebases

### Supported Formats
- **Gaviota (GTB)**: Compressed tablebases, default path `DroidFish/gtb`
- **Syzygy (RTB)**: Modern format, default path `DroidFish/rtb`

### Tablebase Options
| Option | Default | Description |
|--------|---------|-------------|
| Hints | On | Show TB evaluation when touching pieces |
| Hints in Edit Mode | On | TB hints during position editing |
| Root Probe | On | Filter non-optimal moves at root |
| Engine Probe | On | Let engine use tablebases internally |
| GTB Path | (empty) | Local Gaviota tablebase directory |
| GTB Network Path | (empty) | Network path for remote engines |
| RTB Path | (empty) | Local Syzygy tablebase directory |
| RTB Network Path | (empty) | Network path for remote engines |

---

## 7. PGN Support

### Import Features
- Load PGN files from device storage (file paths and SAF `content://` URIs)
- Load from clipboard (auto-detects PGN vs FEN)
- Import from SCID databases via content provider
- Configurable: import variations, comments, NAG annotations
- Multi-game PGN file navigation (previous/next game)

### Export Features
- Save to existing or new PGN files (file paths and SAF `content://` URIs)
- Append to existing PGN via read-all + write-back for content:// URIs
- Copy to clipboard
- Share via Android share intent
- Configurable export of: variations, comments, NAG, player actions, clock times

### PGN Editing
- **Edit Headers**: Event, Site, Date, Round, White, Black, Result
- **Edit Comments**: Pre-move and post-move comments
- **NAG Annotations**: !, ?, !!, ??, !?, ?! and other standard annotations
- **Add ECO Code**: Automatic opening classification
- **Variation Management**: Add, reorder, delete variation branches
- **Null Moves**: Insert pass moves for analysis
- **Truncate Tree**: Remove all moves from current position

### PGN Display Options
| Option | Default | Description |
|--------|---------|-------------|
| View Variations | On | Show non-mainline moves |
| View Comments | On | Show text annotations |
| View NAG | On | Show !, ?, etc. |
| View Headers | Off | Show PGN header tags |
| Variation Line | Off | Show current variation path |
| Piece Display | Local | English letters, local letters, or figurine notation |

---

## 8. Analysis Features

### Thinking Display
- Real-time engine analysis output
- Depth, nodes searched, speed (kN/s)
- Score in centipawns or mate distance
- White-based or relative scoring
- Full or truncated PV lines

### Multi-PV Mode
- Display 1-100 principal variations simultaneously
- Non-linear slider scaling for UX convenience
- Direct text input for exact values

### Analysis Actions
- Add engine PV lines as game variations
- Copy analysis to clipboard
- Toggle statistics display
- Toggle full/truncated variation display

---

## 9. Time Control

### Configuration
| Setting | Default | Options |
|---------|---------|---------|
| Base Time | 2 minutes | 15s to 120 min |
| Moves Per Session | 60 | 0 (sudden death), 1, 10, 20, 30, 40, 50, 60 |
| Increment | 0 | 0s to 60s (Fischer) |

### Clock Display
- Separate clocks for white and black
- MM:SS format with negative time support
- Auto-update via handler-based refresh
- Clocks active in play modes, stopped in analysis/edit

---

## 10. Sound & Feedback

| Feature | Default | Description |
|---------|---------|-------------|
| Move Sound | Off | Play sound on computer moves |
| Speech | Off | Text-to-speech move announcement (EN, DE, ES) |
| Vibration | Off | Haptic feedback on computer moves (500ms) |
| Move Animation | On | Animate piece movements |

---

## 11. Clipboard & Sharing

- **Copy Game**: Full PGN to clipboard
- **Copy Position**: FEN string to clipboard
- **Paste**: Auto-detect and import PGN or FEN from clipboard
- **Share Game**: Share PGN via Android share intent
- **Share Text**: Share as plain text
- **Share Image**: Export board screenshot as image

---

## 12. Additional Features

### Auto-Play Mode
- **Auto Forward**: Automatically advance through game moves
- **Auto Backward**: Automatically rewind through game
- Configurable delay: 500ms to 60 seconds

### Position Editing
- Dedicated `EditBoard` activity for manual position setup
- Import/export via FEN notation
- Return to main activity with new position

### Tour Guide
- First-time user tutorial overlay
- Explains left/right drawers, move list, thinking display
- Can be re-enabled from Settings

### Game State Persistence
- Auto-save on pause (SharedPreferences)
- Byte array serialization with version tracking
- `GameViewModel` (AndroidX ViewModel) holds `DroidChessController` across configuration changes
- ViewModel survives Activity recreation and provides process death recovery via `saveGameState()`/`restoreGameState()`
- Deleted game recovery
- Intent handling for PGN/FEN from other apps

### Notification System
- "Heavy CPU usage" notification during engine computation
- Android O+ notification channel support
- Click to return to app

### Accessibility
- Large button mode
- Left-handed layout (landscape)
- Full-screen mode
- Configurable font size (10/12/16/21)
- 15 language localizations

---

## 13. File Format Support

| Format | Read | Write | Description |
|--------|------|-------|-------------|
| PGN | Yes | Yes | Portable Game Notation (primary) |
| FEN | Yes | Yes | Forsyth-Edwards Notation (positions) |
| SCID | Yes | No | Via external content provider |
| Polyglot .bin | Yes | No | Opening book format |
| CTG | Yes | No | ChessBase opening book |
| ABK | Yes | No | Arena opening book |
| Gaviota GTB | Yes | No | Endgame tablebases |
| Syzygy RTB | Yes | No | Endgame tablebases |
