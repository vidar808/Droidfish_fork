# Chessify Cloud Engine Integration Plan

**Status**: Planned
**Priority**: P2 | **Effort**: High | **Impact**: High

## Overview

Integrate [Chessify](https://chessify.me/) as a selectable cloud chess engine in DroidFish. Chessify offers powerful cloud engines (Stockfish up to 1BN NPS, Lc0, asmFish, SugaR, Koivisto, Berserk, RubiChess) accessible via WebSocket.

## Protocol Discovery

Chessify's open-source frontend ([ornicar/chessify-frontend](https://github.com/ornicar/chessify-frontend), GPL-3.0) reveals two connection tiers:

### Pro Tier (WebSocket + raw UCI) — Implemented in this plan
- Transport: Raw WebSocket (`wss://` channel URL)
- Protocol: Standard UCI text lines sent/received bidirectionally
- On connect, the client sends:
  ```
  stop
  setoption name MultiPV value N
  position fen <FEN>
  go infinite
  ```
- Server responds with standard UCI output:
  ```
  info depth 32 score cp 45 nodes 1234567 nps 500000000 pv e2e4 e7e5 ...
  bestmove e2e4 ponder e7e5
  ```
- WSS channel URLs are obtained from the Chessify dashboard after renting a dedicated server
- Source: `src/connections/pro.js` — uses `new WebSocket(channel)`

### Free Tier (Socket.IO + custom events) — Deferred
- Transport: Socket.IO to `https://chessify.me`
- Auth token passed in `extraHeaders` of polling transport
- Analysis via `get_analyze` event (not raw UCI)
- Requires UCI translation layer (synthesize handshake, convert events to info lines)
- Source: `src/connections/free.js` — uses `socket.io-client`

### Authentication
- Firebase Auth (project: `chessfimee-31ab3`)
- API key: `AIzaSyBYr7oDq5DZFvR-QkDFYWyiUl-h-Nl0Yh4` (public client key)
- Supports anonymous sign-in and email/password
- Firebase REST API can be used without the Firebase Android SDK
- Auth endpoints:
  - Sign up (anonymous): `POST https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=API_KEY`
  - Sign in (email): `POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=API_KEY`
  - Refresh token: `POST https://securetoken.googleapis.com/v1/token?key=API_KEY`
- Returns: `idToken`, `refreshToken`, `expiresIn`

### Available Engines
| Engine | Speed (Dedicated) |
|--------|-------------------|
| Stockfish | 10 MN/s (free shared), 110/300/700 MN/s, 1 BN/s |
| Lc0 (LCZero) | 100 kN/s |
| asmFish | 130 MN/s |
| SugaR | 130 MN/s |
| Koivisto | 130 MN/s |
| Berserk | 130 MN/s |
| RubiChess | 130 MN/s |

---

## Architecture

```
┌─────────────────────────┐     WebSocket (WSS)      ┌────────────────────────┐
│   DroidFish App         │ ◄══════════════════════► │   Chessify Cloud       │
│                         │    Raw UCI Protocol       │                        │
│  ChessifyEngine.java    │                           │   Dedicated Server     │
│  ├─ OkHttp WebSocket    │    Firebase REST Auth     │   (Stockfish/Lc0/etc)  │
│  ├─ LocalPipe (in/out)  │ ─────────────────────►   │                        │
│  └─ UCI bridge          │    idToken in headers     │   Up to 1BN NPS        │
│                         │                           │                        │
│  ChessifyAuth.java      │                           │   WSS channel URL      │
│  ├─ HttpURLConnection   │                           │   from user dashboard  │
│  └─ Token refresh       │                           │                        │
│                         │                           └────────────────────────┘
│  ChessifyConfig.java    │
│  └─ SharedPreferences   │
│                         │
│  ChessifyEngineConfig   │
│  └─ Login + WSS URL UI  │
└─────────────────────────┘
```

Engine identification: Reserved name `"chessify"` (like `"stockfish"`, `"rodent4"`, `"patricia"`). Config stored in SharedPreferences rather than NETE file since Chessify uses Firebase auth + WebSocket, not TCP auth + raw socket.

---

## New Files

### 1. `ChessifyEngine.java`
**Path**: `droidfish/DroidFishApp/src/main/java/org/petero/droidfish/engine/ChessifyEngine.java`

UCIEngineBase subclass. Mirrors NetworkEngine's architecture (LocalPipe pair, startup/read/write threads, Report callbacks).

**Key methods:**

| Method | Responsibility |
|--------|---------------|
| `startProcess()` | Load config from SharedPreferences, refresh token if expired via `ChessifyAuth.refreshToken()`, create OkHttp WebSocket to WSS URL, start write thread |
| `onMessage(text)` | Split received text on newlines, push each line to `engineToGui` pipe |
| Write thread loop | Read lines from `guiToEngine` pipe, send via `webSocket.send(line)` |
| `readLineFromEngine(timeout)` | Delegate to `engineToGui.readLine(timeout)` |
| `writeLineToEngine(data)` | Push to `guiToEngine.addLine(data)` |
| `shutDown()` | Close WebSocket (code 1000), interrupt threads |
| `getOptionsFile()` | Returns `context.getFilesDir() + "/chessify.ini"` |
| `optionsOk(options)` | Returns `!isError` |

**Error handling:** Single retry with token refresh on WebSocket failure. On persistent failure, report error via `report.reportError()`.

**Template:** Follow `NetworkEngine.java` (989 lines) patterns for threading, LocalPipe usage, shutdown coordination, and error reporting.

### 2. `ChessifyAuth.java`
**Path**: `droidfish/DroidFishApp/src/main/java/org/petero/droidfish/engine/ChessifyAuth.java`

Firebase REST API authentication using `HttpURLConnection` (zero external dependencies). ~120 lines.

```java
public class ChessifyAuth {
    private static final String API_KEY = "AIzaSyBYr7oDq5DZFvR-QkDFYWyiUl-h-Nl0Yh4";

    // All methods are synchronous — call from background thread
    public static AuthResult signInAnonymously() throws IOException { ... }
    public static AuthResult signInWithEmail(String email, String password) throws IOException { ... }
    public static AuthResult refreshToken(String refreshToken) throws IOException { ... }

    public static class AuthResult {
        public final String idToken;
        public final String refreshToken;
        public final long expiresInSeconds;
    }
}
```

### 3. `ChessifyConfig.java`
**Path**: `droidfish/DroidFishApp/src/main/java/org/petero/droidfish/engine/ChessifyConfig.java`

SharedPreferences wrapper for Chessify settings. ~60 lines.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `authMode` | String | `"anonymous"` | `"anonymous"` or `"email"` |
| `email` | String | `""` | User's email (if email auth) |
| `idToken` | String | `""` | Firebase ID token |
| `refreshToken` | String | `""` | Firebase refresh token |
| `tokenExpiry` | long | `0` | Epoch millis when token expires |
| `engineName` | String | `"stockfish"` | Selected engine |
| `proWssUrl` | String | `""` | WebSocket channel URL |

Methods: `load(Context)`, `save(Context)`, `isTokenExpired()`, `isConfigured()`

### 4. `ChessifyEngineConfig.java` + Layout
**Path**: `droidfish/DroidFishApp/src/main/java/org/petero/droidfish/activities/ChessifyEngineConfig.java`
**Layout**: `droidfish/DroidFishApp/src/main/res/layout/activity_chessify_config.xml`

Configuration activity with sections:

```
┌────────────────────────────────────────┐
│  ★ Chessify Cloud Engine               │
├────────────────────────────────────────┤
│  Authentication                        │
│  ○ Anonymous  ● Email/Password         │
│  Email:    [user@example.com        ]  │
│  Password: [••••••••                ]  │
│  [Login]   Status: Logged in as user@  │
├────────────────────────────────────────┤
│  Engine                                │
│  [▼ Stockfish                       ]  │
├────────────────────────────────────────┤
│  WebSocket Channel URL                 │
│  [wss://...from chessify dashboard  ]  │
│                                        │
│  [Test Connection]   ✓ Connected (42ms)│
├────────────────────────────────────────┤
│          [Cancel]         [Save]       │
└────────────────────────────────────────┘
```

**Test connection flow:** Creates a temporary OkHttp WebSocket, sends `uci`, waits up to 5s for a response containing `uciok`, reports success/failure with latency.

---

## Modified Files

### 1. `UCIEngineBase.java`
**File**: `droidfish/DroidFishApp/src/main/java/org/petero/droidfish/engine/UCIEngineBase.java`
**Line**: 50 (in `getEngine()` factory method)

Add after the `"patricia"` check, before `isOpenExchangeEngine`:
```java
else if ("chessify".equals(engine))
    return new ChessifyEngine(report, engineOptions);
```

### 2. `EngineUtil.java`
**File**: `droidfish/DroidFishApp/src/main/java/org/petero/droidfish/engine/EngineUtil.java`

Add:
```java
public static boolean isChessifyEngine(String engine) {
    return "chessify".equals(engine);
}
```

### 3. `DroidFish.java`
**File**: `droidfish/DroidFishApp/src/main/java/org/petero/droidfish/DroidFish.java`

Five edits:

| Location | Change |
|----------|--------|
| `reservedEngineName()` (line 2860) | Add `"chessify".equals(name)` to the OR chain |
| `isBuiltinEngine()` (line 1556) | Add `"chessify".equals(engine)` to the OR chain |
| `selectEngineDialog()` (line 2872) | After patricia: `ids.add("chessify"); items.add(getString(R.string.chessify_engine));` |
| `setEngineTitle()` (line 1589) | Before final `else`: `} else if ("chessify".equals(engine)) { eName = getString(R.string.chessify_engine); }` |
| `manageEnginesDialog()` (line 3577) | Add `CONFIG_CHESSIFY = 4` action, menu entry "Configure Chessify Cloud", handler launching `ChessifyEngineConfig`. Add `RESULT_CHESSIFY_CONFIG` constant and handler in `onActivityResult()`. |

### 4. `build.gradle`
**File**: `droidfish/DroidFishApp/build.gradle`
**Line**: After line 79 (last dependency)

```groovy
implementation 'com.squareup.okhttp3:okhttp:4.12.0'
```

APK size impact: ~2MB (126MB → 128MB).

### 5. `AndroidManifest.xml`
**File**: `droidfish/DroidFishApp/src/main/AndroidManifest.xml`

Register activity:
```xml
<activity android:name=".activities.ChessifyEngineConfig"
          android:label="@string/chessify_config_title" />
```

### 6. `strings.xml`
**File**: `droidfish/DroidFishApp/src/main/res/values/strings.xml`

New strings (~20):
```xml
<!-- Chessify Cloud Engine -->
<string name="chessify_engine">Chessify Cloud</string>
<string name="chessify_config_title">Chessify Cloud Engine</string>
<string name="configure_chessify">Configure Chessify Cloud</string>
<string name="chessify_section_auth">Authentication</string>
<string name="chessify_auth_anonymous">Anonymous</string>
<string name="chessify_auth_email">Email / Password</string>
<string name="chessify_email_hint">email@example.com</string>
<string name="chessify_password_hint">Password</string>
<string name="chessify_login">Login</string>
<string name="chessify_logout">Logout</string>
<string name="chessify_logged_in_anon">Logged in anonymously</string>
<string name="chessify_logged_in_email">Logged in as %s</string>
<string name="chessify_not_logged_in">Not logged in</string>
<string name="chessify_auth_failed">Authentication failed: %s</string>
<string name="chessify_logging_in">Logging in\u2026</string>
<string name="chessify_section_engine">Engine</string>
<string name="chessify_section_connection">WebSocket Channel URL</string>
<string name="chessify_pro_url_hint">wss://channel-url-from-chessify-dashboard</string>
<string name="chessify_connecting">Connecting to Chessify\u2026</string>
<string name="chessify_connected">Connected to Chessify %s</string>
<string name="chessify_disconnected">Disconnected from Chessify</string>
<string name="chessify_no_wss_url">Enter your WSS channel URL from the Chessify dashboard</string>
<string name="chessify_test_connection">Test Connection</string>
<string name="chessify_test_success">Connected (%dms)</string>
<string name="chessify_test_failed">Connection failed: %s</string>
```

---

## Implementation Sequence

### Phase 1: Foundation
1. Add OkHttp dependency to `build.gradle`
2. Create `ChessifyConfig.java` (SharedPreferences persistence)
3. Create `ChessifyAuth.java` (Firebase REST API auth)
4. Create `ChessifyEngine.java` (WebSocket UCI bridge, modeled on NetworkEngine)
5. Wire into `UCIEngineBase.getEngine()` factory
6. Add `"chessify"` to reserved/builtin name checks in `DroidFish.java` and `EngineUtil.java`
7. Add "Chessify Cloud" to engine selection dialog and engine title
8. Add all string resources

### Phase 2: Configuration UI
9. Create `activity_chessify_config.xml` layout
10. Create `ChessifyEngineConfig.java` activity
11. Register in `AndroidManifest.xml`
12. Add "Configure Chessify Cloud" to manage engines dialog in `DroidFish.java`
13. Handle `RESULT_CHESSIFY_CONFIG` in `onActivityResult()`

### Phase 3: Build & Test
14. Build APK via `build-apk.sh`
15. Verify Chessify appears in engine list after Patricia
16. Verify config activity launches and auth flow works
17. Verify WebSocket connection and UCI analysis with a live WSS URL
18. Verify existing engines (Stockfish, network engines) are unaffected

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Reserved name `"chessify"` (not NETE file) | Chessify uses Firebase auth + WebSocket, not TCP auth handshake. NETE's 14-line format doesn't fit. |
| OkHttp only (no socket.io-client) | Pro tier uses raw WebSocket; OkHttp handles this natively. Free tier deferred. |
| Firebase REST API (no Firebase SDK) | SDK adds ~10MB + Google Play Services. REST API is 3 HTTP calls via `HttpURLConnection`. |
| User-provided WSS URL | Chessify's backend API for obtaining WSS channels is undocumented. User copies URL from their dashboard. Avoids fragile undocumented API calls. |
| SharedPreferences (not file-based config) | Chessify is a single fixed cloud service, not a user-configured network endpoint. SharedPreferences is simpler than a file format. |

---

## Future Enhancements

- **Free tier support**: Add Socket.IO transport with UCI command translation layer
- **Auto WSS URL**: If Chessify documents their server rental API, automate obtaining WSS channel URLs
- **Coin balance display**: Show remaining Chessify coins in the config activity
- **Server speed selection**: Let users choose speed tier (110/300/700/1000 MN/s) if API supports it
- **Multiple engines**: Support switching between multiple active Chessify servers

---

## Risk Factors

| Risk | Mitigation |
|------|------------|
| Chessify changes WebSocket protocol | Protocol is standard UCI over WebSocket — unlikely to change. Frontend is GPL-3.0 so changes are visible. |
| Firebase API key rotated | Key is extracted from public GPL-3.0 source. Can be updated in a point release. |
| WSS URLs expire/change format | User re-copies URL from dashboard. Could add URL validation in config. |
| OkHttp version conflicts | Pin to 4.12.0; no other OkHttp users in the project. |
