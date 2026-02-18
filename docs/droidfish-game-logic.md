# DroidFish Game Logic - Technical Documentation

## Architecture Overview

DroidFish implements a Model-View-Controller (MVC) pattern:

```
┌──────────────────────────────────────────────────────────────────┐
│                         DroidFish.java                           │
│                     (Activity / View Layer)                      │
│          Implements GUIInterface for callbacks                   │
└──────────────────────┬───────────────────────────────────────────┘
                       │ GUIInterface callbacks
┌──────────────────────▼───────────────────────────────────────────┐
│                  DroidChessController.java                       │
│                    (Controller Layer)                             │
│     Coordinates GUI, Game model, and DroidComputerPlayer         │
└──────────┬───────────────────────────────┬───────────────────────┘
           │                               │
┌──────────▼──────────┐     ┌──────────────▼──────────────────────┐
│   Game.java         │     │   DroidComputerPlayer.java          │
│   GameTree.java     │     │   (Engine Interface)                │
│   (Model Layer)     │     │                                     │
│                     │     │   UCIEngineBase                     │
│   Position          │     │   ├─ InternalStockFish              │
│   TimeControl       │     │   ├─ ExternalEngine                 │
│   GameMode          │     │   ├─ NetworkEngine                  │
│                     │     │   └─ OpenExchangeEngine              │
└─────────────────────┘     └─────────────────────────────────────┘
```

**Total core game logic: ~4,000 lines across 6 key files.**

---

## 1. DroidChessController (Main Controller)

**File:** `DroidFishApp/src/main/java/org/petero/droidfish/gamelogic/DroidChessController.java` (1,245 lines)

### Responsibilities
- Glue layer between engine (`DroidComputerPlayer`) and GUI (`GUIInterface`)
- Game mode transitions and clock management
- Computer and human move coordination
- Search/analysis/ponder mode management
- Book hints, ECO classification, and thinking info display

### Key Instance Variables
```
computerPlayer    : DroidComputerPlayer - UCI engine wrapper
game              : Game - current game state
gameMode          : GameMode - current play mode
ponderMove        : Move - expected next move for pondering
promoteMove       : Move - partial move awaiting promotion choice
searchId          : int - monotonic counter for invalidating stale results
latestThinkingInfo: ThinkingInfo - cached engine analysis
```

### Core Methods

**Game Lifecycle:**
- `newGame(gameMode, tcData)` - Create new game, auto-save previous
- `startGame()` - Begin play, start engine if computer's turn
- `shutdownEngine()` - Set TWO_PLAYERS mode, stop engine

**Mode Management:**
- `setGameMode(newMode)` - Change mode, restart search
- `analysisMode()` - Check if continuous analysis active
- `humansTurn()` - Check if current side is human-controlled

**Move Processing:**
- `makeHumanMove(m, animate)` - Validate and execute human move
- `reportPromotePiece(choice)` - Complete pawn promotion (0=Q, 1=R, 2=B, 3=N)
- `makeHumanNullMove()` - Insert null move for analysis

**Draw/Resign:**
- `claimDrawIfPossible()` - Attempt draw claim (repetition, 50-move, agreement)
- `resignGame()` - Process resignation

**Navigation:**
- `undoMove()` - Go back (2 plies in human vs computer)
- `redoMove()` - Follow default variation
- `gotoMove(moveNr)` - Jump to specific move number
- `goNode(node)` - Jump to specific tree node

**Engine Control:**
- `setEngine(engine)` - Change active engine
- `setStrength(limitStrength, elo)` - Set ELO strength
- `setMultiPVMode(numPV)` - Set analysis PV count
- `stopSearch()` / `stopPonder()` - Force move / stop pondering

### Search ID System

The `searchId` counter prevents stale search results:
- Incremented on: new game, mode change, position change, FEN/PGN load
- All search results tagged with current ID
- Results with wrong ID silently dropped
- Prevents race conditions during rapid position changes

### updateComputeThreads() Logic

```
if (analysis mode && game alive)     → Queue analyze request
elif (computer's turn && game alive) → Queue search request
elif (ponder enabled && human turn)  → Queue ponder request
else                                 → Stop search
```

---

## 2. Game (Game State Model)

**File:** `DroidFishApp/src/main/java/org/petero/droidfish/gamelogic/Game.java` (619 lines)

### Responsibilities
- Game state management via GameTree
- Time control integration
- Move string parsing (UCI, SAN, draw/resign commands)
- Draw offer tracking and game termination

### Key Instance Variables
```
tree              : GameTree - game tree with variations
timeController    : TimeControl - chess clock management
treeHashSignature : long - hash for detecting unsaved changes
pendingDrawOffer  : boolean - draw offer in progress
gamePaused        : boolean - clocks paused
addMoveBehavior   : AddMoveBehavior - how new moves are added
```

### AddMoveBehavior
| Mode | Description | Used When |
|------|-------------|-----------|
| `ADD_FIRST` | New move becomes main line | Play mode with clocks |
| `ADD_LAST` | New move as last variation | Analysis mode |
| `REPLACE` | Remove all variations | "Discard variations" enabled |

### Move Processing

`processString(str)` parses these formats:
- `"e2e4"` - UCI move notation
- `"Nf3"` - Standard algebraic notation
- `"draw offer e2e4"` - Offer draw with move
- `"draw accept"` - Accept draw offer
- `"draw rep e2e4"` - Claim draw by repetition
- `"draw 50 e2e4"` - Claim draw by 50-move rule
- `"resign"` - Resign game

### Game States
```
ALIVE            - Game in progress
WHITE_MATE       - White checkmates black
BLACK_MATE       - Black checkmates white
WHITE_STALEMATE  - White is stalemated
BLACK_STALEMATE  - Black is stalemated
DRAW_REP         - Draw by 3-fold repetition
DRAW_50          - Draw by 50-move rule
DRAW_NO_MATE     - Insufficient material
DRAW_AGREE       - Draw by agreement
RESIGN_WHITE     - White resigned
RESIGN_BLACK     - Black resigned
```

### UCI Integration
`getUCIHistory()` returns `(startPosition, moveList)` for the UCI `position` command. Start position is after the last null move or game start.

---

## 3. GameTree (Game Tree Structure)

**File:** `DroidFishApp/src/main/java/org/petero/droidfish/gamelogic/GameTree.java` (1,716 lines)

### Responsibilities
- Tree structure with variation support
- PGN import/export
- Node navigation
- ECO opening classification
- Time control metadata

### PGN Headers (Seven Tag Roster)
`event`, `site`, `date`, `round`, `white`, `black`, `result`

### Tree Structure
```
rootNode    : Node - root (no move)
currentNode : Node - current position in tree
currentPos  : Position - cached chess position
startPos    : Position - starting position
```

### Node Class

Each node represents a position in the game tree:

```
moveStr        : String - UCI move (e.g., "e2e4")
moveStrLocal   : String - Localized notation (e.g., "e4")
move           : Move - parsed Move object (lazy)
ui             : UndoInfo - for unMakeMove()
playerAction   : String - "draw offer", "resign", etc.
remainingTime  : int - time left after move (ms)
nag            : int - Numeric Annotation Glyph
preComment     : String - comment before move
postComment    : String - comment after move
parent         : Node - parent (null for root)
defaultChild   : int - index of main variation
children       : ArrayList<Node> - child variations
```

### Key Operations

**Navigation:**
- `goBack()` - Move to parent node
- `goForward(variation)` - Move to child variation
- `goNode(node)` - Jump to specific node

**Modification:**
- `addMove(moveStr, playerAction, nag, preComment, postComment)` - Add move to tree
- `reorderVariation(varNo, newPos)` - Change variation order
- `deleteVariation(varNo)` - Remove variation branch

**PGN:**
- `toPGN(options)` - Export as PGN string
- `readPGN(pgn, options)` - Import from PGN string
- `pgnTreeWalker(options, receiver)` - Walk tree for display

---

## 4. GameMode

**File:** `DroidFishApp/src/main/java/org/petero/droidfish/GameMode.java` (100 lines)

| Mode | ID | playerWhite | playerBlack | clocksActive |
|------|----|-------------|-------------|--------------|
| PLAYER_WHITE | 1 | true | false | true |
| PLAYER_BLACK | 2 | false | true | true |
| TWO_PLAYERS | 3 | true | true | true |
| ANALYSIS | 4 | true | true | false |
| TWO_COMPUTERS | 5 | false | false | true |
| EDIT_GAME | 6 | true | true | false |

---

## 5. Time Control System

### TimeControlData
**File:** `DroidFishApp/src/main/java/org/petero/droidfish/gamelogic/TimeControlData.java` (123 lines)

```
TimeControlField:
  timeControl      : int - initial time (ms)
  movesPerSession   : int - moves per TC (0 = sudden death)
  increment         : int - Fischer increment (ms)

Supports separate white/black time controls (tcW, tcB).
```

### TimeControl
**File:** `DroidFishApp/src/main/java/org/petero/droidfish/gamelogic/TimeControl.java` (196 lines)

```
whiteBaseTime, blackBaseTime : int - remaining time when clock stopped
currentMove                  : int - current full move number
elapsed                      : int - time used for current move
timerT0                      : long - system time when clock started (0 if stopped)
```

**Key Methods:**
- `startTimer(now)` / `stopTimer(now)` - Start/stop clock
- `moveMade(now, useIncrement)` - Process completed move, return new remaining time
- `getRemainingTime(whiteToMove, now)` - Calculate current remaining time
- `getMovesToTC(whiteMove)` - Moves until next time control

**Clock Rules:**
- Timer runs during: PLAYER_WHITE, PLAYER_BLACK, TWO_PLAYERS, TWO_COMPUTERS
- Timer stopped during: ANALYSIS, EDIT_GAME
- Additional `gamePaused` flag can stop clocks in any mode

---

## 6. Key Workflows

### Human Move Flow
```
1. GUI detects touch/drag gesture
2. Creates Move object (from/to squares)
3. DroidChessController.makeHumanMove(m, animate)
4. Validates humansTurn() and legal move
5. If promotion needed → gui.requestPromotePiece() → reportPromotePiece()
6. Game.processString() adds move to tree
7. TimeControl.moveMade() updates clock
8. Check ponder hit (move matches ponder move)
9. If computer's turn → start new search
10. GUI updated with new position
```

### Computer Move Flow
```
1. updateComputeThreads() detects computer's turn
2. Creates SearchRequest (position, time controls, ponder flag)
3. Queues to DroidComputerPlayer
4. Engine returns via SearchListener.notifySearchResult()
5. Callback posts to UI thread → makeComputerMove()
6. Move added to game tree, GUI updated
7. If ponder enabled → start pondering on expected reply
```

### Analysis Mode Flow
```
1. Mode set to ANALYSIS
2. updateComputeThreads() creates analyze request
3. Engine continuously sends PV updates
4. SearchListener.notifyPV() updates thinking info
5. GUI displays multi-PV lines, scores, stats
6. Continues until position changes or mode switches
```

---

## 7. Engine Communication

### UCIEngineBase (Abstract Base)
**File:** `DroidFishApp/src/main/java/org/petero/droidfish/engine/UCIEngineBase.java`

Factory method selects engine type:
```
"stockfish"           → InternalStockFish (JNI)
isOpenExchangeEngine  → OpenExchangeEngine (Android app)
isNetEngine           → NetworkEngine (TCP socket)
else                  → ExternalEngine (native binary)
```

### Engine Types

| Type | Class | Communication |
|------|-------|---------------|
| Internal Stockfish | `InternalStockFish` | JNI calls to native C++ |
| External Engine | `ExternalEngine` | Process stdin/stdout via pipes |
| Network Engine | `NetworkEngine` | TCP socket to remote server |
| OEX Engine | `OpenExchangeEngine` | Android IPC to engine app |

### Communication Pattern
All engines use `LocalPipe` for thread-safe buffered I/O:
- `readLineFromEngine(timeoutMillis)` - Read UCI response
- `writeLineToEngine(data)` - Send UCI command
- Background threads handle actual I/O (process streams or sockets)

---

## 8. Design Patterns

| Pattern | Implementation |
|---------|---------------|
| **Observer** | `PgnTokenReceiver`, `SearchListener`, `GUIInterface` |
| **Strategy** | `AddMoveBehavior` enum, time control periods |
| **State** | `GameMode`, `GameState` |
| **Memento** | `toByteArray()`/`fromByteArray()` serialization |
| **Factory** | `UCIEngineBase.getEngine()` |
| **Template Method** | `UCIEngineBase.startProcess()` (abstract) |

---

## 9. Thread Safety

- `DroidChessController` methods are `synchronized`
- Engine callbacks run on background thread, posted to UI via `gui.runOnUIThread()`
- `latestThinkingInfo` is volatile for cross-thread visibility
- `LocalPipe` uses `synchronized` + `wait()`/`notifyAll()` for producer-consumer
- `searchId` provides logical clock for stale result detection
