# FPS Drop & Visual Glitching Fix

**Priority**: P1 | **Effort**: Medium | **Impact**: Critical
**Status**: In Progress
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
**Severity**: Moderate | **File**: `ChessBoard.java`

The ChessBoard custom View does not configure `setLayerType()`. Path-based
drawing (arrow hints, decorations) may fall back to software rendering on
some devices.

## Fix Plan

### Fix 1: Throttle SearchListener UI updates
**Target**: `DroidChessController.java`
**Approach**: Batch engine info updates with a minimum interval before posting
to the UI thread.

Instead of posting every SearchListener callback immediately:

```java
// BEFORE (every info line posts immediately):
gui.runOnUIThread(() -> setThinkingInfo(ti));

// AFTER (coalesce updates, post at most every 100ms):
private volatile ThinkingInfo pendingThinkingInfo;
private final Runnable thinkingInfoUpdater = () -> {
    ThinkingInfo ti = pendingThinkingInfo;
    if (ti != null) {
        setThinkingInfo(ti);
    }
};

// In setSearchInfo():
pendingThinkingInfo = ti;
gui.removeCallbacks(thinkingInfoUpdater);
gui.postOnUIThreadDelayed(thinkingInfoUpdater, 100);
```

This reduces UI thread posts from 10-50/sec to a fixed 10/sec maximum while
always showing the latest info.

**Files to modify**:
- `DroidChessController.java` — add coalescing logic
- `GUIInterface.java` — may need `removeCallbacks()` and `postDelayed()` methods

### Fix 2: Replace Html.fromHtml() with SpannableStringBuilder
**Target**: `DroidFish.java` — `updateThinkingInfo()` method

Replace HTML string construction + parsing with direct `SpannableStringBuilder`
manipulation. This avoids the HTML tokenizer entirely.

```java
// BEFORE:
String s = "<font color=#...>" + text + "</font>";
thinking.append(Html.fromHtml(s));

// AFTER:
SpannableStringBuilder ssb = new SpannableStringBuilder(text);
ssb.setSpan(new ForegroundColorSpan(color), 0, text.length(),
            Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
thinking.append(ssb);
```

**Files to modify**:
- `DroidFish.java` — rewrite `updateThinkingInfo()` to use SpannableStringBuilder

### Fix 3: Move PV formatting to background thread
**Target**: `DroidChessController.java` — `notifyPV()` method

The Position copy + makeMove() loop for formatting PV strings should run on
the engine's background thread, not in the callback that bridges to the UI.

```java
// BEFORE (in SearchListener.notifyPV):
// ... format PV string with Position copies and makeMove() ...
gui.runOnUIThread(() -> setThinkingInfo(ti));

// AFTER:
// Format PV string here (already on engine thread) — this is fine,
// the issue is that setSearchInfo() does formatting AND posts.
// Move the formatting into the SearchListener callback (engine thread)
// and only post the pre-formatted result to UI.
```

Specifically: pre-format the PV display strings in `notifyPV()` (which runs
on the engine thread) and store them as plain Strings in `ThinkingInfo`.
The UI thread then only needs to apply spans/colors — no chess logic.

**Files to modify**:
- `DroidChessController.java` — restructure `notifyPV()` and `setSearchInfo()`
- `ThinkingInfo.java` (or inner class) — carry pre-formatted strings

### Fix 4: Sync animation to display refresh rate
**Target**: `ChessBoard.java` — animation timing

Replace the hardcoded 10ms `postDelayed` with Android's `Choreographer` to
sync animation frames to the display's vsync signal.

```java
// BEFORE:
long delay = 10 - (now2 - now);
if (delay < 1) delay = 1;
handlerTimer.postDelayed(ChessBoard.this::invalidate, delay);

// AFTER:
private final Choreographer choreographer = Choreographer.getInstance();
private final Choreographer.FrameCallback animCallback = frameTimeNanos -> {
    if (anim.isRunning()) {
        invalidate();
        choreographer.postFrameCallback(animCallback);
    }
};
// Start animation:
choreographer.postFrameCallback(animCallback);
```

This renders exactly once per vsync (60fps = 16.7ms) instead of busy-looping,
reducing CPU usage and eliminating frame timing mismatches.

**Files to modify**:
- `ChessBoard.java` — replace `handlerTimer.postDelayed` animation loop

### Fix 5: Synchronize position access in animation
**Target**: `ChessBoard.java` — `MoveAnimation` inner class

Make the position reference used by the animation thread-safe.

```java
// BEFORE:
return !paused && startTime >= 0 && now < stopTime && posHash == pos.zobristHash();

// AFTER:
private volatile long animPosHash;  // Set when animation starts
// In setAnimation():
animPosHash = pos.zobristHash();
// In isRunning():
return !paused && startTime >= 0 && now < stopTime && posHash == animPosHash;
```

By capturing the hash at animation start and comparing against that snapshot
(rather than re-reading a potentially mutated `pos`), we eliminate the race.

**Files to modify**:
- `ChessBoard.java` — capture position hash at animation start

### Fix 6: Enable hardware acceleration
**Target**: `ChessBoard.java` or `AndroidManifest.xml`

Ensure hardware-accelerated rendering is active for the board view.

```java
// In ChessBoard constructor or onAttachedToWindow():
setLayerType(View.LAYER_TYPE_HARDWARE, null);
```

Or in the manifest (likely already enabled by default for API 14+, but verify):
```xml
<application android:hardwareAccelerated="true" ... >
```

**Files to modify**:
- `ChessBoard.java` — add `setLayerType` call, OR
- `AndroidManifest.xml` — verify `hardwareAccelerated="true"`

## Implementation Order & Status

Fixes are ordered by impact and independence:

| Order | Fix | Impact | Risk | Status |
|-------|-----|--------|------|--------|
| 1 | Fix 1: Throttle UI updates | Critical | Low | **Done** |
| 2 | Fix 2: Replace Html.fromHtml | Critical | Low | **Done** |
| 3 | Fix 4: Vsync animation | Major | Low | **Done** |
| 4 | Fix 5: Position race condition | Major | Low | **Done** |
| 5 | Fix 3: Background PV formatting | Major | Medium | Open (depends on Fix 1) |
| 6 | Fix 6: Hardware acceleration | Moderate | Low | **Done** |

### Changes Made

**Fix 1** (`DroidChessController.java`): Added `UI_UPDATE_INTERVAL_MS = 100` throttle
to `setSearchInfo()`. Only posts to UI thread if 100ms+ elapsed since last post.
`clearSearchInfo()` resets the timer to force immediate updates on search clear.

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

## Testing

### Manual testing
- Open DroidFish, start analysis with Stockfish multiPV=3
- Make moves rapidly while engine is analyzing
- Monitor for smooth animation and responsive UI
- Test on low-end device if available

### Measurable metrics
- Frame render time: should stay under 16ms (use Android GPU profiling)
- UI thread message queue: should not accumulate backlog
- Animation smoothness: consistent 60fps during move animation

### Regression checks
- Engine analysis display still updates (not frozen by over-throttling)
- PV lines display correctly (no formatting errors from SpannableString change)
- Move animation still plays (Choreographer change doesn't break timing)
- Analysis info is current (throttled updates still show latest data)
