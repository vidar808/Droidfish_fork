# DroidFish Settings Reference

Complete reference of all user-configurable settings in DroidFish.

## Settings Architecture

**Key Files:**
- `DroidFishApp/src/main/res/xml/preferences.xml` - Preference screen definitions
- `DroidFishApp/src/main/java/org/petero/droidfish/activities/Preferences.java` - Preference activity
- `DroidFishApp/src/main/java/org/petero/droidfish/DroidFish.java` - Settings consumer
- `DroidFishApp/src/main/java/org/petero/droidfish/ColorTheme.java` - Color theme definitions

**Storage**: Android `SharedPreferences` API (default shared preferences for the app)

---

## 1. Time Control (`prefs_time_control`)

| Key | Type | Default | Values | Description |
|-----|------|---------|--------|-------------|
| `movesPerSession` | List | `60` | 0, 1, 10, 20, 30, 40, 50, 60 | Moves between time controls (0 = whole game) |
| `timeControl` | List | `120000` | 15s-120min (ms) | Base thinking time |
| `timeIncrement` | List | `0` | 0s-60s (ms) | Fischer increment per move |

---

## 2. Engine Settings (`prefs_engine_settings`)

| Key | Type | Default | Values | Description |
|-----|------|---------|--------|-------------|
| `ponderMode` | Checkbox | `false` | boolean | Engine thinks on opponent's time |
| `hashMB` | List | `64` | 16-16384 MB | Hash table memory allocation |

---

## 3. Hints (`prefs_hints`)

| Key | Type | Default | Values | Description |
|-----|------|---------|--------|-------------|
| `showThinking` | Checkbox | `false` | boolean | Display engine analysis |
| `whiteBasedScores` | Checkbox | `true` | boolean | Positive scores favor white |
| `bookHints` | Checkbox | `true` | boolean | Show opening book moves |
| `ecoHints` | List | `1` | 0=Off, 1=Auto, 2=Always | ECO opening classification |
| `thinkingArrows` | List | `4` | 0-8 | Number of move arrows on board |
| `highlightLastMove` | Checkbox | `true` | boolean | Highlight last move square |
| `materialDiff` | Checkbox | `false` | boolean | Show material difference |

---

## 4. Playing Options (`prefs_playing_options`)

| Key | Type | Default | Values | Description |
|-----|------|---------|--------|-------------|
| `playerName` | EditText | `"Player"` | text | Default player name |
| `autoSwapSides` | Checkbox | `false` | boolean | Auto-flip by side to move |
| `playerNameFlip` | Checkbox | `true` | boolean | Auto-flip by player name |

---

## 5. Appearance (`prefs_user_interface_appearance`)

| Key | Type | Default | Values | Description |
|-----|------|---------|--------|-------------|
| `fullScreenMode` | Checkbox | `false` | boolean | Hide status bar |
| `language` | List | `"default"` | 15 languages | UI language |
| `fontSize` | List | `12` | 10, 12, 16, 21 | Font size |
| `viewPieceType` | List | `1` | 0=English, 1=Local, 2=Figurine | Piece name display |
| `viewPieceSet` | List | `"chesscases"` | 17 piece sets | Chess piece graphics |
| `blindMode` | Checkbox | `false` | boolean | Blindfold mode |
| `vibrateEnabled` | Checkbox | `false` | boolean | Vibrate on computer move |
| `moveSoundEnabled` | Checkbox | `false` | boolean | Sound on computer move |
| `moveAnnounceType` | List | `"off"` | off, speech_en/de/es | Move announcement |
| `wakeLock` | Checkbox | `false` | boolean | Prevent screen timeout |
| `drawSquareLabels` | Checkbox | `false` | boolean | Show coordinates |
| `leftHanded` | Checkbox | `false` | boolean | Left-hand layout |
| `animateMoves` | Checkbox | `true` | boolean | Animate piece movement |
| `autoScrollTitle` | Checkbox | `true` | boolean | Marquee scroll title |

### 5a. Color Settings (`colors`)

**Board Colors:**

| Key | Default | Description |
|-----|---------|-------------|
| `color_brightSquare` | `#FFFFFFFA` | Light squares |
| `color_darkSquare` | `#FF83A5D2` | Dark squares |
| `color_selectedSquare` | `#FF3232D1` | Selected square |
| `color_brightPiece` | `#FFF0F0F0` | White pieces |
| `color_darkPiece` | `#FF282828` | Black pieces |
| `color_squareLabel` | `#FFFF0000` | Coordinate labels |
| `color_decoration` | `#FF808080` | TB hint decoration |
| `color_arrow0` - `color_arrow7` | Various | Analysis arrows (8 colors) |

**Move List Colors:**

| Key | Default | Description |
|-----|---------|-------------|
| `color_currentMove` | `#FF3333FF` | Current move highlight |
| `color_pgnComment` | `#FFC0C000` | Comment text |
| `color_fontForeground` | `#FFFFFF00` | Font color |
| `color_generalBackground` | `#FF2E2B53` | Background |

---

## 6. Behavior (`prefs_user_interface_behavior`)

| Key | Type | Default | Values | Description |
|-----|------|---------|--------|-------------|
| `oneTouchMoves` | Checkbox | `false` | boolean | Any-order square tapping |
| `squareSelectType` | List | `1` | 0=Sticky, 1=Toggle | Selection behavior |
| `dragMoveEnabled` | Checkbox | `true` | boolean | Drag-and-drop moves |
| `scrollSensitivity` | List | `2` | 0=Off to 0.5=Fastest | Scroll speed |
| `invertScrollDirection` | Checkbox | `false` | boolean | Reverse scroll |
| `scrollGames` | Checkbox | `false` | boolean | Horizontal scroll loads games |
| `autoScrollMoveList` | Checkbox | `true` | boolean | Follow current move |
| `autoDelay` | List | `5000` | 500ms-60s | Auto-play delay |
| `discardVariations` | Checkbox | `false` | boolean | Discard non-mainline moves |

### 6a. Button Settings (`buttonSettings`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `largeButtons` | Checkbox | `false` | Large navigation buttons |

**Custom Button Action Slots** (each button has 7 slots: main + 6 submenu):

| Button | Slot 0 (Main) | Slot 1 | Slot 2 | Slot 3 | Slot 4 | Slot 5 | Slot 6 |
|--------|---------------|--------|--------|--------|--------|--------|--------|
| Custom 1 | `flipboard` | `viewHeaders` | `viewComments` | `toggleArrows` | `bookHints` | `tbHints` | (empty) |
| Custom 2 | `toggleAnalysis` | `selectEngine` | `engineOptions` | (empty) | (empty) | (empty) | (empty) |
| Custom 3 | `loadLastFile` | `loadGame` | (empty) | (empty) | (empty) | (empty) | (empty) |

---

## 7. Other Settings (`prefs_other`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `guideShowOnStart` | Checkbox | `true` | Show startup tutorial |

### 7a. Opening Book Settings (`bookSettings`)

| Key | Type | Default | Values | Description |
|-----|------|---------|--------|-------------|
| `bookFile` | EditFile | `""` | file path | Book file (bin/ctg/abk) |
| `bookMaxLength` | List | `1000000` | 5-1000000 | Max book depth |
| `bookPreferMainLines` | Checkbox | `false` | boolean | Prefer main moves |
| `bookTournamentMode` | Checkbox | `false` | boolean | Tournament-only moves |
| `bookRandom` | SeekBar | `500` | 0-1000 | Randomness (-3.0 to +3.0) |

### 7b. PGN Settings (`pgnSettings`)

**PGN Viewer:**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `viewVariations` | Checkbox | `true` | Show variations |
| `viewComments` | Checkbox | `true` | Show comments |
| `viewNAG` | Checkbox | `true` | Show annotation glyphs |
| `viewHeaders` | Checkbox | `false` | Show PGN headers |
| `showVariationLine` | Checkbox | `false` | Show variation path |

**PGN Import:**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `importVariations` | Checkbox | `true` | Import variations |
| `importComments` | Checkbox | `true` | Import comments |
| `importNAG` | Checkbox | `true` | Import NAGs |

**PGN Export:**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `exportVariations` | Checkbox | `true` | Export variations |
| `exportComments` | Checkbox | `true` | Export comments |
| `exportNAG` | Checkbox | `true` | Export NAGs |
| `exportPlayerAction` | Checkbox | `false` | Export draw/resign actions |
| `exportTime` | Checkbox | `false` | Export clock times |

### 7c. Endgame Tablebases (`egtbSettings`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `tbHints` | Checkbox | `true` | Show TB move evaluations |
| `tbHintsEdit` | Checkbox | `true` | TB hints in edit mode |
| `tbRootProbe` | Checkbox | `true` | Filter non-optimal root moves |
| `tbEngineProbe` | Checkbox | `true` | Engine uses tablebases |
| `gtbPath` | EditFile | `""` | Gaviota TB directory |
| `gtbPathNet` | EditText | `""` | Gaviota network path |
| `rtbPath` | EditFile | `""` | Syzygy TB directory |
| `rtbPathNet` | EditText | `""` | Syzygy network path |

---

## 8. Programmatic Settings (Not in Preferences UI)

These settings are managed in code but not exposed in the Settings screen:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `boardFlipped` | boolean | `false` | Current board orientation |
| `engine` | String | `"stockfish"` | Active engine identifier |
| `currentPGNFile` | String | `""` | Last opened PGN file |
| `gameState` | String | null | Serialized game state (also stored in GameViewModel) |
| `gameStateVersion` | int | varies | Serialization version |
| `showStats` | boolean | `true` | Show analysis statistics |
| `fullPVLines` | boolean | `false` | Full PV line display |
| `numPV` | int | `1` | Number of PV lines |
| `oldThinkingArrows` | String | `"0"` | Arrow toggle backup |
| `prefsViewInitialItem` | int | `-1` | Preferences scroll position |

---

## Summary

- **Total preference categories**: 7 main + 5 nested screens
- **Total individual settings**: ~90+
- **CheckBoxPreference**: ~40 boolean toggles
- **ListPreference**: ~20 dropdown selections
- **EditTextPreference**: ~4 text inputs
- **ColorPickerPreference**: 18 color customizations
- **SeekBarPreference**: 1 (book randomness)
- **EditFilePreference**: 4 file/directory pickers
