# Enhanced Opening Book

## Overview

The DroidFish internal opening book has been significantly enhanced with broader coverage,
gambit-specific metadata, and color-coded display support. The book now covers 4,107 opening
lines (up from 2,014) with 1,153 gambit-tagged entries that display in distinct colors.

## What Changed

### Expanded Coverage

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total opening lines | 2,014 | 4,107 | +104% |
| Category A (Flank) | 338 | 871 | +158% |
| Category B (Semi-open) | 350 | 822 | +135% |
| Category C (Open) | 804 | 1,327 | +65% |
| Category D (Closed) | 324 | 686 | +112% |
| Category E (Indian) | 198 | 401 | +103% |
| book.bin size | 45 KB | 181 KB | +299% |
| eco.dat size | 96 KB | 214 KB | +123% |
| All 500 ECO codes | Yes | Yes | — |

Sources merged: DroidFish original eco.pgn + Lichess Chess Openings dataset (3,687 lines,
AGPL-3.0 / CC0 data). All moves validated as legal with python-chess.

### Gambit Classification

Every opening line is now classified with a `LineType`:

| LineType | Count | Color | Description |
|----------|-------|-------|-------------|
| `normal` | 2,954 | Default text | Standard openings |
| `gambit-white` | 943 | Warm golden | White sacrifices material (King's Gambit, Evans, Smith-Morra, etc.) |
| `gambit-black` | 203 | Cool steel blue | Black sacrifices material (Benko, Budapest, Marshall, counter-gambits) |
| `gambit-mutual` | 7 | Copper | Both sides sacrifice (complex tactical lines) |

Each line also carries a `Quality` tag:
- `mainline` (2,613) — well-established theoretical lines
- `sideline` (1,487) — less common alternatives
- `dubious` (7) — known weak openings (Fool's Mate, etc.)

### Gambit Arrow Colors

Book move arrows on the chess board now display in distinct colors for gambit lines:
- **White gambit arrows**: warm golden tone (lighter) — e.g. King's Gambit, Evans, Smith-Morra
- **Black gambit arrows**: cool steel blue tone (darker) — e.g. Benko, Budapest, Marshall Attack
- **Mutual gambit arrows**: copper/muted red tone — complex tactical lines
- **Normal book arrows**: unchanged (standard arrow colors by position)

The book notation text at the bottom remains in the default font color. When a gambit
move is played, the ECO opening name automatically updates to show the gambit name
(e.g. "King's Gambit Accepted" or "Benko Gambit"), since all gambit lines are included
in the expanded ECO database (eco.dat).

Colors are theme-aware — each of the 7 color themes has tuned gambit arrow colors.

## Technical Details

### Binary Format v2

The book binary format was extended from 2-byte to 4-byte entries, with a magic header
for backward compatibility:

```
Header: "DFB2" (4 bytes) — identifies v2 format

Per move entry (4 bytes):
  Bytes 0-1: Move encoding (unchanged)
    Bits 0-5:   from square
    Bits 6-11:  to square
    Bits 12-14: promotion type
    Bit 15:     bad move flag

  Bytes 2-3: Metadata (new)
    Bits 0-1:   LineType (0=normal, 1=gambit-white, 2=gambit-black, 3=gambit-mutual)
    Bits 2-3:   Quality  (0=unrated, 1=mainline, 2=sideline, 3=dubious)
    Bits 4-15:  Reserved

Terminator: 0x00000000 (4 zero bytes)
```

InternalBook.java auto-detects v1 (legacy 2-byte) vs v2 (4-byte) format by checking
for the `DFB2` magic header, so old book.bin files continue to work.

### eco.pgn Extended Headers

The PGN source file now supports two new optional headers per entry:

```pgn
[ECO "C33"]
[Opening "King's Gambit Accepted"]
[Variation "Bishop's Gambit"]
[LineType "gambit-white"]
[Quality "mainline"]

e4 e5 f4 exf4 Bc4 *
```

These are processed during the Gradle `buildBook` task, converted to `# META` comment
lines in the intermediate book.txt, and encoded into the 2-byte metadata field by Book.java.

EcoBuilder.java ignores these headers (it only reads ECO, Opening, Variation), so eco.dat
generation is unaffected.

### Files Modified

| File | Purpose |
|------|---------|
| `buildSrc/src/main/java/chess/eco.pgn` | Expanded from 2,014 to 4,107 entries with LineType/Quality headers |
| `buildSrc/src/main/java/chess/Book.java` | 4-byte entries, DFB2 magic header, META line parsing |
| `DroidFishApp/build.gradle` | buildBook task preserves LineType/Quality as META comments |
| `DroidFishApp/.../book/InternalBook.java` | Auto-detects v1/v2 format, parses metadata, stores in BookEntry |
| `DroidFishApp/.../book/DroidBook.java` | BookEntry gains lineType/quality; getAllBookMoves() emits color tags |
| `DroidFishApp/.../ColorTheme.java` | 3 new color constants (GAMBIT_WHITE, GAMBIT_BLACK, GAMBIT_MUTUAL) per theme |
| `DroidFishApp/.../DroidFish.java` | styledText() extended for color tags; gambit arrow types passed to board |
| `DroidFishApp/.../GUIInterface.java` | ThinkingInfo gains bookMoveTypes field |
| `DroidFishApp/.../DroidChessController.java` | Threads bookMoveTypes through SearchListener → ThinkingInfo |
| `DroidFishApp/.../SearchListener.java` | notifyBookInfo() gains bookMoveTypes parameter |
| `DroidFishApp/.../view/ChessBoard.java` | Gambit-colored arrow paints; setMoveHints() accepts hint types |
| `DroidFishApp/src/main/assets/book.bin` | Rebuilt: 181 KB v2 format |
| `DroidFishApp/src/main/assets/eco.dat` | Rebuilt: 214 KB with expanded ECO tree |

### Gambit Classification Logic

Gambit color is determined by opening name pattern matching:
- **Black gambits**: Counter-gambits, Benko, Budapest, Albin, Englund, Latvian, Schliemann,
  Marshall Attack, Blumenfeld, Falkbeer, Stafford, Elephant Gambit, etc.
- **White gambits**: King's Gambit family, Evans, Scotch, Danish, Smith-Morra, Wing,
  Blackmar-Diemer, Vienna, Urusov, Max Lange, Halloween, QGA, etc.
- **Mutual**: Complex lines where both sides sacrifice (e.g., Two Knights Defense sharp lines)

## Research & Build Tools

The `book-library/` directory contains all research materials and tooling:

```
book-library/
��── enhanced-eco.pgn              # Master enhanced PGN (source of truth)
├── README.md                     # Project overview
├── sources.md                    # Public source catalog with licenses
├── gambit-catalog.md             # Complete gambit inventory by color
├── tools.md                      # Build workflow and tool reference
├── pgn/eco/
│   ├── lichess-openings/         # Lichess Chess Openings dataset
│   ├── scid.eco                  # SCID ECO reference database
│   └── original-eco.pgn          # Backup of original DroidFish eco.pgn
└── analysis/
    ├── analyze_coverage.py       # Coverage statistics across sources
    ├── merge_sources.py          # Merge + gambit classification tool
    ├── validate_enhanced_eco.py  # Legal move + metadata validation
    ├── test_book_build.py        # End-to-end build pipeline test
    └── coverage_report.txt       # Comparative coverage report
```

### Adding New Lines

To add opening lines to the book:

1. Edit `book-library/enhanced-eco.pgn` (the master source)
2. Add entries with proper ECO/Opening/Variation/LineType/Quality headers
3. Run `python3 book-library/analysis/validate_enhanced_eco.py` to verify
4. Copy to `droidfish/buildSrc/src/main/java/chess/eco.pgn`
5. Rebuild with `./gradlew assembleDebug`

### Adjusting Gambit Colors

Edit the theme arrays in `ColorTheme.java`. The last 3 values in each theme array are:
`gambitWhite`, `gambitBlack`, `gambitMutual` (ARGB hex strings).
