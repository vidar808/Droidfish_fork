# Chess960 (Fischer Random Chess) Enhancement

**Priority**: P2 | **Effort**: High | **Impact**: High
**Status**: Planning

## Overview

Add full Chess960 (Fischer Random Chess) support to DroidFish, enabling players to
start games from any of the 960 legal starting positions. Chess960 uses the same
board and pieces as standard chess, but randomizes the back-rank piece placement
following three rules:

1. Bishops must be on opposite-colored squares
2. The king must be between the two rooks
3. Black's pieces mirror White's placement

The bundled Rodent IV 0.33 engine already supports Chess960 natively (UCI_Chess960,
Shredder-FEN, dynamic castling). Stockfish 18 also supports it via the UCI_Chess960
option. What's missing is DroidFish's game logic, FEN handling, and UI.

## Current State

### What exists
- **Rodent IV 0.33**: Full Chess960 engine support (castling, FEN, book, `guide_960.bin`)
- **Stockfish 18**: Supports `UCI_Chess960` UCI option natively
- **Data files**: `guide_960.bin` (2.1 MB Chess960 opening guide) bundled in assets
- **Network engine**: UCI protocol already passes through `setoption` commands

### What's missing
- No Chess960 position generator
- No UI to start a Chess960 game
- Game logic hardcoded for standard chess (castling, FEN, move generation)
- No UCI_Chess960 option communication to engines

## Implementation Plan

### Phase 1: Position Model & FEN (Core)

These changes are the foundation — everything else depends on them.

#### 1.1 Extend `Position.java` castling representation

**File**: `DroidFishApp/src/main/java/org/petero/droidfish/gamelogic/Position.java`

**Current**: Castling stored as 4-bit mask (`1=A1_ROOK, 2=H1_ROOK, 4=A8_ROOK, 8=H8_ROOK`),
assumes rooks start on a-file and h-file.

**Change**: Store the actual file (0-7) of each rook that retains castling rights,
plus the king's starting file per side. This is backward-compatible: standard chess
is simply king on e-file with rooks on a-file and h-file.

```java
// New fields
int wKingFile = 4;   // e-file (standard)
int wRookQFile = 0;  // a-file queenside rook
int wRookKFile = 7;  // h-file kingside rook
int bKingFile = 4;
int bRookQFile = 0;
int bRookKFile = 7;
boolean chess960 = false;
```

**Constraint**: Existing PGN/FEN for standard chess must continue to work identically.

#### 1.2 Update FEN parser/emitter in `TextIO.java`

**File**: `DroidFishApp/src/main/java/org/petero/droidfish/gamelogic/TextIO.java`

**Current**: Parses `KQkq` castling notation only. Hardcoded to standard rook positions.

**Change**: Support three FEN castling notations:
- Standard: `KQkq` (king/queen side, implies a/h files)
- Shredder-FEN: `AHah` (explicit file letters for each rook)
- X-FEN: `KQkq` with disambiguation when rook files differ from standard

```
Standard:    rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1
Shredder:    rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w HAha - 0 1
X-FEN:       bbqnnrkr/pppppppp/8/8/8/8/PPPPPPPP/BBQNNRKR w KQkq - 0 1
             (K/Q refer to king-side/queen-side relative to king position)
```

**Detection logic**: If castling character is a file letter (A-H or a-h), use
Shredder-FEN decoding. Otherwise use standard/X-FEN decoding with king-relative
king-side/queen-side interpretation.

#### 1.3 Update move generation for Chess960 castling

**File**: `DroidFishApp/src/main/java/org/petero/droidfish/gamelogic/MoveGen.java`

**Current**: Castling hardcoded — white king on e1, rooks on a1/h1. Checks specific
squares for obstruction and attack.

**Change**: Generalize castling to work with any king and rook starting positions:
- King moves from its starting square to the target square (c1/g1 or c8/g8)
- Rook moves from its starting square to the target square (d1/f1 or d8/f8)
- All squares between king's start and end must be free (excluding king and rook)
- All squares between rook's start and end must be free (excluding king and rook)
- No square the king passes through (including start and end) may be attacked
- King and rook may swap positions (they aren't "blocking" each other)

```
Castling rules (same for standard and 960):
  King-side:  King → g-file, Rook → f-file
  Queen-side: King → c-file, Rook → d-file

The difference in 960: the starting squares vary, so the path checks
must be computed dynamically instead of using hardcoded square lists.
```

#### 1.4 Update move notation

**Files**: `TextIO.java`, any PGN export code

**Change**: In Chess960, castling is always written as `O-O` or `O-O-O` (not as
the king's literal movement like `Ke1g1`), regardless of the actual squares involved.
UCI communication should use king-takes-rook notation when `UCI_Chess960` is set
(e.g., `e1h1` for king-side castling with rook on h1).

### Phase 2: Position Generator

#### 2.1 Create `Chess960.java`

**File**: New file `DroidFishApp/src/main/java/org/petero/droidfish/gamelogic/Chess960.java`

Implements the standard Chess960 position numbering (0-959) using the
well-known derivation algorithm:

```
Given position number N (0-959):
  1. Place bishops: N mod 4 → dark-square bishop, (N/4) mod 4 → light-square bishop
  2. Place queen: (N/16) mod 6 → queen on remaining squares
  3. Place knights: (N/96) → lookup table for two knights on remaining 5 squares
  4. Place rooks and king: R-K-R on the three remaining squares (deterministic)
```

Public API:
```java
public class Chess960 {
    /** Generate FEN for a Chess960 position number (0-959). */
    public static String positionToFEN(int positionNumber);

    /** Generate a random Chess960 position FEN. */
    public static String randomPosition();

    /** Identify the position number from a back-rank arrangement, or -1 if not valid 960. */
    public static int identifyPosition(String backRank);

    /** Standard chess is position 518. */
    public static final int STANDARD_POSITION = 518;
}
```

### Phase 3: UCI Engine Communication

#### 3.1 Send UCI_Chess960 option to engines

**Files**:
- `DroidFishApp/src/main/java/org/petero/droidfish/engine/UCIEngine.java`
- `DroidFishApp/src/main/java/org/petero/droidfish/engine/DroidComputerPlayer.java`

**Change**: When starting a Chess960 game, send `setoption name UCI_Chess960 value true`
before `ucinewgame`. Only send to engines that advertise the option (check the
`option name UCI_Chess960` line during UCI handshake).

For standard chess, send `setoption name UCI_Chess960 value false` (or omit it).

#### 3.2 Use king-takes-rook move notation in UCI

When `UCI_Chess960` is active, castling moves sent to the engine must use
king-takes-rook notation (e.g., `e1a1` for O-O-O when king is on e1 and
queenside rook is on a1). This differs from standard mode where `e1c1` is used.

### Phase 4: UI Integration

#### 4.1 New Game dialog enhancement

**File**: `DroidFishApp/src/main/java/org/petero/droidfish/DroidFish.java`

**Change**: Add Chess960 option to the "New Game" flow:

```
New Game
├── Standard Chess          (current behavior)
└── Chess960
    ├── Random Position     (generates random 0-959)
    ├── Enter Position #    (number input 0-959)
    └── Position 518        (standard start, for testing)
```

Implementation: Add a dialog before game start. If Chess960 is selected, generate
the FEN from `Chess960.java` and pass it to `Game.newGame(fen)` instead of the
standard starting FEN.

#### 4.2 String resources

**File**: `DroidFishApp/src/main/res/values/strings.xml` (and translations)

New strings needed (~10):
```xml
<string name="chess960">Chess960</string>
<string name="chess960_random">Random Position</string>
<string name="chess960_enter_number">Position Number (0-959)</string>
<string name="chess960_standard">Standard Position (518)</string>
<string name="new_game_variant">Game Variant</string>
<string name="standard_chess">Standard Chess</string>
<string name="chess960_position_number">Chess960 #%d</string>
<string name="invalid_position_number">Position number must be 0-959</string>
```

#### 4.3 Display position number

When a Chess960 game is active, optionally show the position number in the
status bar or game info area (e.g., "Chess960 #534").

#### 4.4 Edit Board support

**File**: `DroidFishApp/src/main/java/org/petero/droidfish/EditBoard.java`

**Change**: When setting up a position in Edit Board that has a non-standard
back rank, detect it as Chess960 and preserve the correct castling rights
based on king and rook positions rather than assuming standard squares.

### Phase 5: Testing

#### 5.1 Unit tests

```
Chess960Test.java:
  - testPositionGeneration()        → All 960 positions produce valid FEN
  - testPosition518IsStandard()     → Position 518 = standard chess setup
  - testBishopOppositeColors()      → Verify bishop color constraint for all 960
  - testKingBetweenRooks()          → Verify king placement constraint for all 960
  - testIdentifyPosition()          → Round-trip: number → FEN → backrank → number
  - testRandomPosition()            → Returns valid position (0-959)

TextIOTest.java (additions):
  - testShredderFEN()               → Parse/emit Shredder-FEN castling
  - testXFEN()                      → Parse/emit X-FEN castling
  - testStandardFENUnchanged()      → Existing standard FEN still works

MoveGenTest.java (additions):
  - testChess960Castling()          → Castling from various 960 positions
  - testCastlingPathBlocked()       → Blocked castling in 960 positions
  - testCastlingThroughCheck()      → King path through check in 960
  - testKingRookSwap()              → King and rook on adjacent squares
  - testCastlingNotation()          → O-O / O-O-O output for 960 castling
```

#### 5.2 Integration tests

- Start a Chess960 game against Stockfish, verify engine receives UCI_Chess960
- Start a Chess960 game against Rodent IV, verify engine accepts position
- Play a full game from a random 960 position through to checkmate/draw
- Load/save PGN with Chess960 game and verify round-trip

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `gamelogic/Position.java` | Modify | Add per-side king/rook file tracking, chess960 flag |
| `gamelogic/TextIO.java` | Modify | Shredder-FEN and X-FEN castling parsing/emitting |
| `gamelogic/MoveGen.java` | Modify | Generalize castling move generation |
| `gamelogic/Chess960.java` | **New** | Position generator (0-959), FEN builder |
| `engine/UCIEngine.java` | Modify | Send UCI_Chess960 option to engines |
| `engine/DroidComputerPlayer.java` | Modify | Pass chess960 flag to engine setup |
| `DroidFish.java` | Modify | New Game dialog with variant selection |
| `EditBoard.java` | Modify | Chess960 castling right detection |
| `res/values/strings.xml` | Modify | Add ~10 Chess960 UI strings |
| `res/layout/` | Possibly modify | Dialog layout for variant selection |

## Dependencies

- **Rodent IV 0.33**: Already integrated with Chess960 support
- **Stockfish 18**: Already supports UCI_Chess960
- **No external libraries needed**: Position generation is pure arithmetic

## Risks & Considerations

1. **Backward compatibility**: All existing PGN files and saved games must continue
   to load correctly. The castling representation change must default to standard
   chess behavior when `chess960 = false`.

2. **Network engines**: When connected to a remote engine via Chess-UCI-Server,
   the UCI_Chess960 option must be forwarded correctly. The server's custom_variables
   feature may need to be aware of this.

3. **Opening book**: DroidFish's built-in opening book is for standard chess only.
   In Chess960 mode, the book should be disabled (or use the engine's own 960 book
   like Rodent's `guide_960.bin`).

4. **Analysis mode**: "Paste FEN" should auto-detect Chess960 positions and set
   the chess960 flag accordingly.

5. **PGN export**: Chess960 games should include the `[Variant "Chess960"]` and
   `[SetUp "1"]` / `[FEN "..."]` PGN headers.

## References

- [FIDE Chess960 rules](https://handbook.fide.com/chapter/C9601)
- [Shredder-FEN specification](https://www.shredderchess.com/chess-features/general/chess960.html)
- [X-FEN specification](https://en.wikipedia.org/wiki/X-FEN)
- [Chess960 numbering scheme](https://en.wikipedia.org/wiki/Fischer_random_chess_numbering_scheme)
- [UCI protocol - Chess960 section](https://backscattering.de/chess/uci/#gui-position)
