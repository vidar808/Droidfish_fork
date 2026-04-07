# FPS Drop & Visual Glitching Fix

**Priority**: P1 | **Effort**: Medium | **Impact**: Critical
**Status**: Resolved (5 of 6 fixes implemented; Fix 3 deferred — already mitigated by Fix 1)
**Issue**: [vidar808/Droidfish_fork#1](https://github.com/vidar808/Droidfish_fork/issues/1)

## Problem

Users report visual glitching and FPS drops when making moves. The stuttering
is most visible during active engine analysis. Root cause is a combination of
unthrottled UI updates, expensive text processing on the UI thread, and
animation timing issues.

## Root Causes

### 1. Unthrottled engine info flooding the UI thread
**Severity**: Critical | **File**: `DroidChessController.java`

Every engine `info` line triggers an immediate `gui.runOnUIThread()` call via
`SearchListener.notifyPV()`, `notifyStats()`, `notifyDepth()`, and
`notifyCurrMove()`. During deep analysis, engines emit 10-50+ info lines per
second. Each one posts a Runnable to the UI thread, creating a backlog that
starves frame rendering.

The existing 100ms `guiUpdateInterval` in `DroidComputerPlayer.java:725` only
throttles `notifyGUI()` calls — the SearchListener callbacks bypass it entirely.

### 2. Expensive Html.fromHtml() on every engine update
**Severity**: Critical | **File**: `DroidFish.java`

`updateThinkingInfo()` (called on every engine info update) invokes
`Html.fromHtml()` multiple times per call — once each for ECO info, book/explorer
info, and variation lines. HTML parsing involves tokenizing markup, building a
Spanned object, and computing text layout. At 10+ calls per second, this creates
sustained CPU spikes on the UI thread.

### 3. Synchronous PV string formatting
**Severity**: Major | **File**: `DroidChessController.java`

`notifyPV()` creates Position copies and calls `makeMove()` for each move in
every PV line to produce algebraic notation strings. This chess logic runs
synchronously in the callback chain before posting to the UI thread.

**Note**: This already runs on the engine's background thread, not the UI thread.
With Fix 1's throttle limiting UI posts to 10/sec, the impact is minimal. Deferred.

### 4. Animation timing hardcoded to 10ms
**Severity**: Major | **File**: `ChessBoard.java`

Move animation uses `handlerTimer.postDelayed(invalidate, 10ms)` instead of
syncing to the display refresh rate via `Choreographer`. When a frame takes
longer than 10ms to render, the next invalidation fires immediately, creating
a tight loop that competes with the info-update flood for UI thread time.

### 5. Race condition on position during animation
**Severity**: Major | **File**: `ChessBoard.java`

The animation's `isRunning()` check reads `pos.zobristHash()` without
synchronization. The `pos` field can be modified by the game logic thread
via `setPosition()` concurrently. An inconsistent read can abort the animation
mid-frame or cause a visual glitch.

### 6. No explicit hardware acceleration
**Severity**: Moderate | **File**: `AndroidManifest.xml`

The application element did not explicitly enable hardware-accelerated rendering.

### 7. Animation terminal frame dropped
**Severity**: Major | **File**: `ChessBoard.java`

The Choreographer callback only continued posting frames while `isRunning()`
returned true. When the animation window closed, no final redraw was requested.
The piece would remain visible at an intermediate position until some unrelated
`invalidate()` call happened to trigger a repaint.

### 8. Animation timer started too early
**Severity**: Major | **File**: `ChessBoard.java`

`setAnimMove()` recorded `startTime = System.currentTimeMillis()` immediately,
but the animation was paused (`paused = true`). When `setPosition()` later
unpaused it, frames had already been "consumed" by the delay between the two
calls. On slow devices or with background work, the piece could start its
animation already 30-50% through, appearing to jump.

## Implementation Status

| Order | Fix | Impact | Risk | Status |
|-------|-----|--------|------|--------|
| 1 | Throttle UI updates | Critical | Low | **Done** |
| 2 | Replace Html.fromHtml | Critical | Low | **Done** |
| 3 | Background PV formatting | Major | Medium | Deferred (mitigated by Fix 1) |
| 4 | Vsync animation | Major | Low | **Done** |
| 5 | Position race condition | Major | Low | **Done** |
| 6 | Hardware acceleration | Moderate | Low | **Done** |
| 7 | Animation terminal frame | Major | Low | **Done** |
| 8 | Animation timer start | Major | Low | **Done** |

## Changes Made

**Fix 1** (`DroidChessController.java`): Added `UI_UPDATE_INTERVAL_MS = 100` throttle
to `setSearchInfo()`. Only posts to UI thread if 100ms+ elapsed since last post.
`clearSearchInfo()` resets the timer to force immediate updates on search clear.

**Important caveat**: The throttle introduced a secondary bug where book/explorer
updates were also throttled, causing book hints to disappear (see Fix 1b below).

**Fix 1b** (`DroidChessController.java`): `notifyBookInfo()` now resets
`lastUIUpdateTime = 0` before calling `setSearchInfo()`, forcing book/explorer
updates to bypass the 100ms throttle. Without this, the sequence was:
1. `clearSearchInfo()` posts empty book state immediately (resets timer)
2. `updateBookHints()` calls `notifyBookInfo()` a few ms later
3. `setSearchInfo()` throttles the update (within 100ms window)
4. With engine off, no later callback flushes the pending data

Result: book arrows and text vanished permanently after the first move.

**Fix 2** (`DroidFish.java`): Added `styledText()` helper that parses `<b>` and `<br>`
tags directly into `SpannableStringBuilder` with `StyleSpan(BOLD)`. Replaced all 4
`Html.fromHtml()` calls in `updateThinkingInfo()`. Also added required imports.

**Fix 4** (`ChessBoard.java`): Replaced `handlerTimer.postDelayed(invalidate, 10ms)`
with `Choreographer.postFrameCallback()` which syncs to display vsync (typically 60Hz).
Added `animFrameCallbackActive` guard to prevent duplicate callbacks.

**Fix 5** (`ChessBoard.java`): Decoupled animation active check from live `pos` field.
`animActive()` no longer reads `pos.zobristHash()` — it only checks timing. The
`isRunning()` method used by the frame callback is purely time-based.

**Fix 6** (`AndroidManifest.xml`): Added `android:hardwareAccelerated="true"` to the
application element.

**Fix 7** (`ChessBoard.java`): The Choreographer callback now always requests one
final redraw after the animation window closes. Before this fix, when
`isRunning()` returned false at the end of the animation, no more frames were
scheduled. The piece remained at its last intermediate position until an
unrelated `invalidate()` triggered a repaint — matching the "piece hangs
partway and settles after extra taps" report.

**Fix 8** (`ChessBoard.java`): Added `animDuration` field to `AnimInfo`.
`setAnimMove()` now stores the duration without starting the timer.
`setPosition()` starts the timer (`startTime = now`, `stopTime = now + duration`)
when it unpauses the animation. This ensures the full animation duration is
available for rendering, regardless of delay between the two calls.

## Interaction Between Fixes

The throttle (Fix 1) and book display (Fix 1b) interact in a subtle way that
is important for future maintainers:

```
SearchListener callback flow:

  notifyPV/notifyStats/notifyCurrMove/notifyDepth
      → setSearchInfo(id)
          → if (now - lastUIUpdateTime >= 100ms)
                post to UI thread              ← THROTTLED (10/sec max)

  notifyBookInfo
      → lastUIUpdateTime = 0                   ← BYPASS THROTTLE
      → setSearchInfo(id)
          → posts immediately (timer was reset)

  clearSearchInfo
      → lastUIUpdateTime = 0                   ← FORCE IMMEDIATE
      → setSearchInfo(id)
          → posts immediately
```

If a new callback type is added that should always reach the UI (like book info),
it must reset `lastUIUpdateTime = 0` before calling `setSearchInfo()`.

## Testing

### Manual testing
- Open DroidFish, start analysis with Stockfish multiPV=3
- Make moves rapidly while engine is analyzing
- Monitor for smooth animation and responsive UI
- Verify book arrows stay visible with engine off
- Test on low-end device if available

### Regression checks
- Engine analysis display still updates (not frozen by over-throttling)
- PV lines display correctly (no formatting errors from SpannableString change)
- Move animation completes fully (piece reaches final square)
- Animation starts from the origin square (no mid-air jumps)
- Analysis info is current (throttled updates still show latest data)
- Book hints persist across moves when engine is off
- Book hints show alongside engine analysis when book is enabled

### Automated test results (verified 2026-04-07)

| Test Suite | Result | Notes |
|---|---|---|
| DroidFish JVM unit tests | 61/61 pass | testSpinOptionBounds + testDisabledWithoutToken added |
| DroidFish instrumented tests | 70/73 pass | 3 failures are env-specific (missing book/tablebase on emulator) |
| Android emulator engine validation | 24/24 pass | Stockfish 18, Rodent IV, Patricia all validated |
| QA server integration + E2E | 54/54 pass | 2 xfail (known SessionManager limitation) |
| QA stress tests | 8/8 pass | Concurrent clients, sustained sessions, throughput |
| Compilation | Clean | Forward reference in ChessBoard.java caught and fixed |

### Compilation fixes applied during development

1. The vsync animation fix (Fix 4) introduced an illegal forward reference —
   `animFrameCallback` referenced the `anim` field before its declaration.
   Fixed by moving the `AnimInfo anim` field declaration before the callback.

2. The `buildBook` Gradle task was running `chess.Book.main2()` at configuration
   time (outside `doLast`), causing build failures. Fixed by wrapping in `doLast`.
