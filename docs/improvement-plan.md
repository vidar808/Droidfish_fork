# Improvement Plan

## Phase 1: Foundation (Code Quality & Cross-Platform)

### 1.1 Chess-UCI-Server Refactoring

**Priority**: High | **Effort**: Medium

**Current state**: ~3,100-line `chess.py` with 228 tests, platform-specific deploy scripts, and Docker packaging.

**Tasks**:
- [ ] Split `chess.py` into modules:
  - `server.py` - Main server and asyncio loop
  - `engine_manager.py` - Engine process management
  - `security.py` - Trust verification, connection tracking
  - `firewall.py` - Platform-specific firewall integration
  - `config.py` - Configuration loading and validation
  - `logging_config.py` - Logging setup
- [x] Add config validation with helpful error messages for missing/invalid keys
- [x] Fix duplicate `logging.basicConfig` calls
- [x] Replace blocking `subprocess.run()` calls with `asyncio.create_subprocess_exec()`
- [x] Add async locks for shared `connection_attempts` dictionary
- [x] Implement the `enable_auto_trust` feature (currently in config but not functional)
- [x] Fix heartbeat to use a UCI-compatible keepalive (empty line or `isready` instead of `ping`)
- [ ] Add `pyproject.toml` and proper Python packaging
- [x] Create `Dockerfile` for containerized deployment
- [ ] Add `systemd` service file for Linux deployment

### 1.2 Cross-Platform Firewall Support

**Priority**: High | **Effort**: Medium

**Current state**: Firewall abstraction implemented with `FirewallBackend` base class.

**Tasks**:
- [x] Create platform abstraction for firewall management (`FirewallBackend` base class)
- [x] Implement `WindowsFirewall` (async `netsh` calls via `asyncio.create_subprocess_exec()`)
- [ ] Implement `LinuxFirewallManager` (using `iptables` or `nftables`)
- [ ] Implement `MacOSFirewallManager` (using `pfctl`)
- [x] Implement `NoopFirewall` (for when firewall integration is disabled or non-Windows)
- [x] Auto-detect platform and select appropriate manager

### 1.3 Testing Infrastructure

**Priority**: High | **Effort**: Medium

**Tasks**:
- [x] Add `pytest` test suite for Chess-UCI-Server (228 tests):
  - Config validation tests (14 tests)
  - Trust verification tests (12 tests)
  - UCI command processing tests (10 tests)
  - Connection handling tests (mock socket)
  - Firewall manager tests (5 tests)
  - TLS tests (6 tests)
  - Authentication tests (6 tests)
  - SessionManager tests (10 tests)
  - OutputThrottler tests (10 tests)
  - mDNS tests (5 tests)
  - QR pairing tests (5 tests)
- [x] Add JUnit tests for DroidFish engine layer (LocalPipe, UCIOptions, UCIEngineBase)
- [ ] Add mock UCI engine for integration testing
- [ ] Add JUnit tests for DroidFish `NetworkEngine` (connection, TLS, auth)
- [ ] Set up CI/CD pipeline (GitHub Actions)

---

## Phase 2: Security & Reliability

### 2.1 TLS Encryption

**Priority**: Critical | **Effort**: High | **Status: DONE**

**Tasks**:
- [x] Add TLS support to Chess-UCI-Server:
  - Config options: `enable_tls`, `tls_cert_path`, `tls_key_path`
  - `create_ssl_context()` loads cert/key for server-side TLS
  - Fallback to plain text for backward compatibility
- [x] Add TLS support to DroidFish `NetworkEngine`:
  - `SSLSocket` via `SSLSocketFactory` (trust-all for user-configured servers)
  - TLS checkbox in network engine config dialog
  - Stored in 14-line NETE config file (TLS flag is line 4)
- [ ] Certificate pinning option (TOFU model)
- [ ] Let's Encrypt integration (for production)
- [ ] Document certificate setup process

### 2.2 Authentication

**Priority**: Critical | **Effort**: High | **Status: DONE**

**Tasks**:
- [x] Design authentication protocol:
  - Server sends `AUTH_REQUIRED` → Client responds `AUTH <token>` → Server sends `AUTH_OK` or `AUTH_FAIL`
- [x] Implement server-side auth verification (`authenticate_client()` in chess.py)
- [x] Implement client-side auth (DroidFish `NetworkEngine`)
- [x] Add auth token to server config (`auth_token` key)
- [x] Add auth token field to DroidFish network engine config dialog
- [ ] Rate limit authentication attempts

### 2.3 Connection Reliability

**Priority**: High | **Effort**: Medium | **Status: Partially DONE**

**Tasks**:
- [x] DroidFish `NetworkEngine` improvements:
  - Automatic reconnection with exponential backoff (up to 5 attempts, 1s-30s)
  - Position tracking (`lastPosition`/`lastGo`) for future recovery
- [ ] DroidFish `NetworkEngine` remaining:
  - Configurable timeout values (not hardcoded 10s/60s)
  - Connection health indicator in UI
  - Queued command buffering during reconnection
  - Position recovery after reconnect (resend position command)
- [x] Chess-UCI-Server improvements:
  - SessionManager keeps engine alive after disconnect for warm reattach
  - OutputThrottler rate-limits UCI info lines for bandwidth control
- [ ] Chess-UCI-Server remaining:
  - Automatic engine restart on crash
  - Client notification on engine failure

---

## Phase 3: Enhanced Features

### 3.1 REST API & Monitoring

**Priority**: Medium | **Effort**: Medium

**Tasks**:
- [ ] Add HTTP REST API to Chess-UCI-Server (using `aiohttp` or built-in):
  - `GET /status` - Server health, uptime, connected clients
  - `GET /engines` - List configured engines and their status
  - `GET /connections` - Active connections
  - `GET /logs` - Recent log entries
  - `POST /engines/{name}/restart` - Restart an engine
  - `POST /config/reload` - Hot-reload configuration
- [ ] Add web-based admin dashboard (static HTML + REST API)
- [ ] Prometheus metrics endpoint for monitoring
- [ ] Health check endpoint for load balancers

### 3.2 Hot-Reload Configuration

**Priority**: Medium | **Effort**: Low

**Tasks**:
- [ ] Watch `config.json` for changes (using `watchdog` or polling)
- [ ] Apply non-disruptive changes without restart:
  - Add/remove trusted sources
  - Change logging settings
  - Update custom variables
- [ ] Restart affected engines for disruptive changes:
  - Port changes
  - Engine path changes
- [ ] Add `SIGHUP` handler for manual reload trigger

### 3.3 Multi-Client Engine Sharing

**Priority**: Medium | **Effort**: High

**Tasks**:
- [ ] Allow multiple clients to connect to the same engine port
- [ ] Implement request queuing for analysis requests
- [ ] Design session isolation:
  - Each client gets independent `position` state
  - Engine time-shares between clients
  - Priority queuing (optional)
- [ ] Add config option: `max_clients_per_engine`

### 3.4 Engine Tournament Mode

**Priority**: Low | **Effort**: High

**Tasks**:
- [ ] Add tournament configuration:
  - Engine matchups
  - Time controls
  - Opening books
  - PGN output
- [ ] Implement game adjudication
- [ ] Statistics tracking (Elo estimation)
- [ ] Integration with existing tournament tools (cutechess-cli compatible)

---

## Phase 4: DroidFish Integration

### 4.1 Server Discovery

**Priority**: Medium | **Effort**: Medium | **Status: DONE**

**Tasks**:
- [x] Add mDNS/Bonjour service advertisement to Chess-UCI-Server (zeroconf, `_chess-uci._tcp`)
- [x] Add server discovery to DroidFish:
  - Auto-discover servers via NsdManager (Android mDNS)
  - "Discover" button in network engine config dialog (3-second scan)
  - Show available engines per server in selection dialog
- [x] QR code pairing:
  - Server generates QR code with JSON payload (host, engines, TLS, token)
  - DroidFish "Scan QR" button (ZXing integration) parses payload and fills config
- [x] Fallback to manual host:port entry (existing behavior preserved)
- [x] "Import Connection File" button: SAF file picker for `.chessuci` files from server `--pair` mode

### 4.2 Enhanced DroidFish Network UI

**Priority**: Medium | **Effort**: Medium

**Tasks**:
- [ ] Show connection status indicator (connected/connecting/disconnected)
- [ ] Display remote engine info (name, version, options)
- [ ] Server management screen:
  - Save multiple server profiles
  - Quick-switch between servers
  - Connection history
- [ ] Remote engine option configuration from DroidFish UI

### 4.3 Bandwidth Optimization

**Priority**: Low | **Effort**: Medium

**Tasks**:
- [ ] Implement UCI command compression for mobile connections
- [ ] Filter unnecessary `info` lines based on connection speed
- [ ] Configurable analysis update frequency
- [ ] Delta position updates (send only new moves, not full position)

---

## Phase 5: Cloud Engine Integration

### 5.1 Chessify Cloud Engine

**Priority**: P2 | **Effort**: High | **Impact**: High

**Status**: Planned — see [`docs/chessify-integration.md`](chessify-integration.md) for full implementation plan.

**Summary**: Integrate Chessify as a selectable cloud engine in DroidFish via UCI-over-WebSocket bridge. Pro tier only (raw WebSocket + standard UCI protocol). Authentication via Firebase REST API. New `ChessifyEngine` class extending `UCIEngineBase`, configuration activity, OkHttp dependency for WebSocket support.

**Tasks**:
- [ ] Add OkHttp dependency to `build.gradle`
- [ ] Create `ChessifyAuth.java` (Firebase REST API authentication)
- [ ] Create `ChessifyConfig.java` (SharedPreferences persistence)
- [ ] Create `ChessifyEngine.java` (UCI-over-WebSocket bridge)
- [ ] Create `ChessifyEngineConfig.java` + layout (login, engine selection, WSS URL)
- [ ] Wire into `UCIEngineBase.getEngine()` factory
- [ ] Add "Chessify Cloud" to engine selection dialog in `DroidFish.java`
- [ ] Add "Configure Chessify Cloud" to manage engines dialog
- [ ] Register activity in `AndroidManifest.xml`
- [ ] Add string resources (~20 strings)
- [ ] Build and integration test

---

## Priority Matrix

| Task | Impact | Effort | Priority | Status |
|------|--------|--------|----------|--------|
| Server refactoring (1.1) | High | Medium | P1 | Mostly done (single-file remains) |
| Cross-platform (1.2) | High | Medium | P1 | Done (Win + Noop; Linux/Mac pending) |
| Testing (1.3) | High | Medium | P1 | **Done** (228 pytest + 3 JUnit) |
| TLS encryption (2.1) | Critical | High | P1 | **Done** |
| Authentication (2.2) | Critical | High | P1 | **Done** |
| Connection reliability (2.3) | High | Medium | P2 | Partially done |
| REST API (3.1) | Medium | Medium | P2 | Open |
| Hot-reload (3.2) | Medium | Low | P2 | Open |
| Chessify integration (5.1) | High | High | P2 | Planned |
| Multi-client (3.3) | Medium | High | P3 | Open |
| Tournament mode (3.4) | Low | High | P4 | Open |
| Server discovery (4.1) | Medium | Medium | P3 | **Done** |
| Enhanced network UI (4.2) | Medium | Medium | P3 | Partially done |
| Bandwidth optimization (4.3) | Low | Medium | P4 | Partially done (OutputThrottler) |
