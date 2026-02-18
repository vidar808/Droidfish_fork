# System Architecture

## Overview

This document describes the architecture of both projects and how they integrate to form a complete remote chess analysis system.

## DroidFish Architecture

### Module Structure

DroidFish is a Gradle multi-module Android project with two modules:

> **Note:** CuckooChess modules were removed during project optimization. See [droidfish-features.md](droidfish-features.md) for the complete feature reference.

```
droidfish/
├── DroidFishApp/          # Android application (main module)
│   ├── src/main/java/org/petero/droidfish/
│   │   ├── DroidFish.java           # Main activity (~3,850 lines)
│   │   ├── DroidFishApp.java        # Application class
│   │   ├── GameViewModel.java       # ViewModel for lifecycle persistence
│   │   ├── engine/                  # Engine abstraction layer
│   │   │   ├── UCIEngine.java       # UCI engine interface
│   │   │   ├── UCIEngineBase.java   # Base implementation
│   │   │   ├── InternalStockFish.java  # Built-in Stockfish 18 (JNI)
│   │   │   ├── NetworkEngine.java   # Remote engine via TCP/TLS ★
│   │   │   ├── NetworkDiscovery.java # mDNS service discovery
│   │   │   ├── ExternalEngine.java  # On-device external engines
│   │   │   ├── OpenExchangeEngine.java # OEX protocol engines
│   │   │   ├── DroidComputerPlayer.java # Engine controller
│   │   │   ├── UCIOptions.java      # UCI option management
│   │   │   └── LocalPipe.java       # Thread-safe pipe
│   │   ├── gamelogic/               # Chess game logic
│   │   ├── book/                    # Opening book support
│   │   ├── tb/                      # Tablebase support
│   │   ├── view/                    # Board rendering
│   │   └── activities/              # Android activities
│   │       └── QuickPlayDialog.java # Quick Play dialog (ELO/time/color)
│   ├── src/main/cpp/                # Native code (Stockfish 18)
│   │   └── Android.mk              # NDK build config
│   └── src/test/java/               # Unit tests
│       └── org/petero/droidfish/engine/
│           ├── LocalPipeTest.java
│           ├── UCIOptionsTest.java
│           └── UCIEngineBaseTest.java
│
└── chess-uci-server/      # Python network engine server (replaces EngineServer)
    ├── deploy/linux/          # Linux deployment (chess.py, install.sh, Docker)
    ├── deploy/windows/        # Windows deployment (chess.py, install.bat)
    ├── docs/                  # Server-specific documentation
    └── tests/                 # 228 pytest tests
```

### Engine Abstraction Layer

DroidFish supports multiple engine types through a clean abstraction:

```
UCIEngine (interface)
  └── UCIEngineBase (abstract base)
       ├── InternalStockFish  - Bundled Stockfish via JNI
       ├── ExternalEngine     - On-device executables
       ├── NetworkEngine      - Remote engine via TCP socket ★
       └── OpenExchangeEngine - OEX protocol engines
```

Each engine type implements:
- `startProcess()` - Initialize the engine
- `readLineFromEngine()` - Read UCI responses
- `writeLineToEngine()` - Send UCI commands
- `initOptions()` - Set engine options (hash, tablebases, etc.)
- `optionsOk()` - Validate current options
- `shutDown()` - Clean shutdown

### NetworkEngine Detail

The `NetworkEngine` class handles remote engine communication with security and resilience:

1. **Connection**: Opens TCP or TLS socket to `host:port` (read from 14-line NETE config file)
2. **Security**:
   - Optional TLS encryption via `SSLSocket` (trust-all for user-configured servers)
   - Optional token-based authentication (AUTH_REQUIRED/AUTH/AUTH_OK handshake)
3. **Threading Model**: Uses 3 threads:
   - `startupThread` - Monitors for UCI startup timeout (10s)
   - `stdInThread` - Reads from socket → `engineToGui` LocalPipe
   - `stdOutThread` - Reads from `guiToEngine` LocalPipe → writes to socket (async)
4. **Data Flow**: `GUI ↔ LocalPipe ↔ Socket (TLS) ↔ Server ↔ Engine`
5. **Reconnection**: Exponential backoff (up to 5 attempts, 1s-30s delay)
6. **Position Tracking**: Stores `lastPosition`/`lastGo` for future recovery after reconnect
7. **Options**: Passes Hash, SyzygyPath, GaviotaTbPath to remote engine
8. **Config Format**: 14-line NETE file: `NETE\n<host>\n<port>\n<tls|notls>\n<auth_token>\n<fingerprint>\n<auth_method>\n<psk>\n<relay_host>\n<relay_port>\n<relay_session>\n<external_host>\n<mdns_name>\n<selected_engine>`

### NetworkDiscovery

The `NetworkDiscovery` class provides mDNS-based automatic server discovery:

1. **Protocol**: Uses Android `NsdManager` to discover `_chess-uci._tcp` services on the local network
2. **Discovery Flow**: Start scan → resolve each service → extract host, port, TXT attributes (engine, tls, auth)
3. **Thread Safety**: Uses `CopyOnWriteArrayList` and `Handler` for main thread callbacks
4. **Integration**: "Discover" button in network engine config dialog triggers 3-second scan

### Connection File Import

The "Import Connection File" button in the network engine config dialog opens the Android Storage Access Framework (SAF) file picker to select a `.chessuci` file generated by the server's `--pair` mode. The selected file URI is passed back to `DroidFish.handleChessUciImport()`, which parses the JSON and creates NETE config profiles for each engine.

### EngineServer (Removed)

The upstream DroidFish included a minimal Java desktop `EngineServer` module (Swing GUI, no security, no logging). This has been removed in the fork and replaced by the significantly more capable **Chess-UCI-Server** (Python).

---

## Chess-UCI-Server Architecture

### Component Overview

The Chess-UCI-Server is a Python asyncio server (`chess.py`, ~3,100 lines) with platform-specific deploy scripts:

```
chess.py
├── Configuration Layer
│   ├── config.json loading + validation (validate_config / load_config)
│   ├── Type, IP, subnet, and range checks
│   └── Optional config keys with defaults
├── Security Layer
│   ├── Trusted sources (IP whitelist)
│   ├── Trusted subnets (CIDR ranges)
│   ├── Auto-trust (handle_auto_trust)
│   ├── TLS encryption (create_ssl_context)
│   ├── Token authentication (authenticate_client)
│   ├── Connection attempt monitoring (async-locked)
│   └── Firewall abstraction (WindowsFirewall / NoopFirewall)
├── Server Layer (asyncio.start_server)
│   ├── Per-engine port listeners
│   ├── Semaphore-based connection limiting
│   ├── Graceful shutdown (signal handling)
│   └── mDNS advertisement (zeroconf, _chess-uci._tcp)
├── Client Handler
│   ├── Trust verification
│   ├── TLS/auth handshake
│   ├── SessionManager (warm engine reattach)
│   ├── UCI command proxying
│   ├── OutputThrottler (rate-limited info lines)
│   ├── Custom variable injection
│   ├── Inactivity timeout
│   └── Heartbeat mechanism (valid UCI isready)
├── Session Management
│   ├── SessionManager - keeps engine alive after disconnect
│   ├── Configurable keepalive timeout
│   └── Expiry task scheduling
├── Pairing
│   ├── QR code generation (generate_qr_pairing)
│   └── JSON payload with host, engines, TLS, token, fingerprint
├── Logging Layer
│   ├── Server event logs
│   ├── Per-engine UCI communication logs
│   └── Untrusted connection attempt logs
└── Monitoring
    └── Watchdog timer
```

### Data Flow

```
DroidFish Client
    │
    ▼ TCP/TLS connect to port (e.g., 9998)
┌───────────────────────────────────┐
│  client_handler() coroutine       │
│                                   │
│  1. TLS handshake (if enabled)    │
│  2. Token authentication          │
│  3. Verify trusted source         │
│  4. Acquire semaphore             │
│  5. SessionManager: reattach or   │
│     spawn new engine subprocess   │
│  6. Send "uci" command            │
│  7. Inject custom_variables       │
│  8. Wait for "uciok"             │
│  9. Start bidirectional proxy:    │
│     ┌──────────────────────────┐  │
│     │ process_client_commands()│  │
│     │ Client → Engine          │  │
│     │ (with option overrides)  │  │
│     ├──────────────────────────┤  │
│     │ process_engine_responses │  │
│     │ Engine → Client          │  │
│     │ (OutputThrottler filter) │  │
│     └──────────────────────────┘  │
│  10. Monitor inactivity           │
│  11. Send heartbeat (isready)     │
│                                   │
│  Finally: release to              │
│    SessionManager (warm keepalive)│
│    or terminate engine            │
└───────────────────────────────────┘
```

### UCI Command Processing

The server intelligently handles UCI `setoption` commands:

1. If the option has a per-engine `custom_variables` entry with value `"override"` → pass through client's value
2. If the option has a per-engine `custom_variables` entry → substitute server's value
3. If the option has a global `custom_variables` entry → substitute server's value
4. Otherwise → pass through client's value

This allows the server admin to enforce certain engine settings (e.g., hash size, thread count) while allowing clients to override others.

---

## Integration Architecture

### Current State

```
┌─────────────┐          ┌──────────────────┐          ┌──────────────┐
│  DroidFish  │ TCP/TLS  │ Chess-UCI-Server │ stdin/   │ UCI Engine   │
│  Android    │◄────────►│ Python asyncio   │ stdout   │ (Stockfish,  │
│  App        │  UCI     │                  │◄────────►│  Dragon,     │
│             │  text    │ Port per engine  │ process  │  etc.)       │
└─────────────┘          └──────────────────┘          └──────────────┘

Connection: TCP socket with optional TLS encryption
Authentication: Optional token-based (AUTH_REQUIRED/AUTH/AUTH_OK)
Discovery: mDNS (server advertises _chess-uci._tcp, client discovers via NsdManager)
Pairing: QR code with JSON payload (host, engines, TLS, token)
Protocol: UCI text commands (\n delimited)
```

The upstream EngineServer (Java/Swing) has been removed and replaced by Chess-UCI-Server.

---

## Technology Stack Summary

| Component | DroidFish | Chess-UCI-Server |
|-----------|-----------|------------------|
| Language | Java 1.8 + C++ (NDK) | Python 3.12+ |
| Build | Gradle 8.4 / AGP 8.2.0 | Docker / standalone |
| Platform | Android (SDK 21-34) | Cross-platform (Win/Lin/Mac) |
| Networking | java.net.Socket / SSLSocket | asyncio TCP server + TLS |
| Security | TLS, token auth | TLS, token auth, IP whitelist |
| Discovery | NsdManager (mDNS), QR scan | Zeroconf (mDNS), QR pairing |
| Concurrency | Java threads | asyncio coroutines |
| Config | 14-line NETE files | JSON (validated) |
| GUI | Android UI / Swing | Console output |
| License | GPL-3.0 | GPL-3.0 |
| Dependencies | AndroidX, AndroidSVG, ZXing, Lifecycle | qrcode, zeroconf |
| Tests | 3 JUnit test classes | 228 pytest tests |
