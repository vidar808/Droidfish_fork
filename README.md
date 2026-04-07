# Chess UCI Integration Project

A unified development workspace combining **DroidFish** (Android chess GUI) and **Chess-UCI-Server** (Python network engine server) to create an enhanced, secure, cross-platform chess analysis system.

## Architecture

```
┌─────────────────────┐    TCP/TLS       ┌──────────────────────┐
│   DroidFish App     │ ◄══════════════► │  Chess-UCI-Server    │
│   (Android Client)  │   UCI Protocol   │  (Python Server)     │
│                     │   + Auth Token   │                      │
│  NetworkEngine.java │                  │  chess.py (asyncio)  │
│  - TLS encryption   │   Discovery:     │  Manages engines:    │
│  - Token auth       │  mDNS/QR/Import  │  - Stockfish         │
│  - Reconnection     │                  │  - Rodent IV, etc.   │
│                     │                  │                      │
│  Built-in engines:  │                  │  Features:           │
│  - Stockfish 18     │                  │  - TLS + token auth  │
│  - Rodent IV        │                  │  - SessionManager    │
│  - Patricia         │                  │  - OutputThrottler   │
│                     │                  │  - mDNS + QR pairing │
│  Discovery:         │                  │  - Relay (NAT)       │
│  - NsdManager/mDNS  │                  │  - Docker support    │
│  - QR code scanner  │                  │                      │
└─────────────────────┘                  └──────────────────────┘
```

## Repository Structure

```
├── README.md                          # This file
├── docs/                              # Documentation (8 files)
│   ├── architecture.md                # System architecture deep-dive
│   ├── droidfish-features.md          # Complete feature reference
│   ├── droidfish-settings.md          # All ~90+ settings
│   ├── droidfish-game-logic.md        # MVC architecture internals
│   ├── droidfish-improvements.md      # Issues and proposals
│   ├── strengths-weaknesses.md        # Analysis of both projects
│   ├── improvement-plan.md            # Planned enhancements
│   └── integration-guide.md           # Setup, TLS, auth, discovery
├── droidfish/                         # DroidFish Android app
│   ├── DroidFishApp/                  # Main app module (compileSdk 34, minSdk 21)
│   └── build.gradle                   # Gradle 8.4 / AGP 8.2.0
├── chess-uci-server/                  # Python network engine server
│   ├── deploy/linux/                  # Linux deployment
│   │   ├── chess.py                   # Main server (~3,100 lines)
│   │   ├── relay_server.py            # Relay for NAT traversal
│   │   └── engines/                   # Engine binaries
│   ├── deploy/windows/                # Windows deployment
│   ├── tests/                         # Server tests (228 tests)
│   └── docs/                          # Server documentation
├── qa/                                # QA test suite (93 tests)
│   ├── integration/                   # Server integration tests
│   ├── e2e/                           # End-to-end protocol tests
│   ├── stress/                        # Load and stability tests
│   ├── error/                         # Error handling tests
│   ├── android/                       # Emulator engine validation
│   └── fixtures/                      # Mock engine, client, test certs
└── engines/                           # Engine configurations
```

## Sub-Projects

### DroidFish (`/droidfish/`)

**Fork of**: [peterosterlund2/droidfish](https://github.com/peterosterlund2/droidfish)
**Language**: Java/C++ | **License**: GPL-3.0

A feature-rich Android chess application with three bundled engines, secure networking, and new analysis features.

**Bundled Engines:**
| Engine | Description |
|--------|-------------|
| **Stockfish 18** | World's strongest open-source engine, ARM NEON + x86 SSE4.1 optimized, NNUE evaluation |
| **Rodent IV** | Personality-based engine with 15+ playing styles (Tal, Fischer, Karpov, etc.), Chess960 support |
| **Patricia** | Aggressive dual-NNUE engine known for sharp tactical play |

**Key Features:**
- UCI_Elo strength limiting (1320-3190) for adjustable difficulty
- **Quick Play dialog** - one-tap game setup with ELO, time control, and color selection
- Full PGN/FEN support for game import/export (including SAF `content://` URIs on Android 11+)
- **Lichess Opening Explorer** integration for opening study
- Opening book integration (Polyglot, CTG, ABK formats)
- Endgame tablebase support (Syzygy 3-4-5-6 piece, Gaviota)
- Multi-PV engine analysis with real-time display
- Remote/network engine support via **TCP/TLS** with **token/PSK authentication**
- **QR code scanning**, **mDNS auto-discovery**, and **connection file import** for network engine pairing
- **Reconnection** with exponential backoff on network disconnect
- **GameViewModel** for game state persistence across configuration changes
- Board editor, game annotations, ECO classification
- Localized in 15+ languages

**Build**: Gradle 8.4 / AGP 8.2.0 / Java 1.8 / Android SDK 34 (minSdk 21) / NDK 25

---

### Chess-UCI-Server (`/chess-uci-server/`)

**Source**: [vidar808/Chess-UCI-Server_Droidfish](https://github.com/vidar808/Chess-UCI-Server_Droidfish)
**Language**: Python | **License**: GPL-3.0 | **Commits**: 51

A Python asyncio-based server that bridges UCI chess engines to network clients (including DroidFish).

**Key Features:**
- Multi-engine support (Stockfish, Dragon, Berserk, ShashChess, Ethereal, etc.)
- Concurrent client handling via asyncio with configurable connection limits
- **TLS encryption** and **token-based authentication**
- **SessionManager** - keeps engine alive after disconnect for warm reattach
- **OutputThrottler** - rate-limits UCI info lines to save bandwidth
- **mDNS advertisement** (`_chess-uci._tcp`) for automatic discovery
- **QR code pairing** with JSON payload for instant client setup
- Dynamic UCI option management (global + per-engine custom variables)
- IP-based access control (individual IPs and CIDR subnets)
- Auto-trust mode for convenient setup
- Cross-platform firewall abstraction (Windows/Noop)
- Connection attempt monitoring and rate limiting
- Comprehensive logging (server events, UCI communication, untrusted attempts)
- Inactivity timeout and heartbeat mechanism (valid UCI `isready`)
- **Docker** support (Dockerfile + docker-compose.yml)
- **228 pytest tests** covering all components
- Watchdog timer for server health monitoring
- Standalone Windows executable (ChessServer.exe)

**Configuration** (`config.json`):
```json
{
  "host": "0.0.0.0",
  "engines": {
    "Stockfish": {
      "path": "/path/to/stockfish",
      "port": 9998
    }
  },
  "enable_trusted_sources": true,
  "trusted_sources": ["127.0.0.1"],
  "enable_tls": false,
  "auth_token": "",
  "enable_mdns": true,
  "session_keepalive_seconds": 300,
  "output_throttle_ms": 100,
  "custom_variables": {
    "Hash": "32000",
    "Threads": "32"
  }
}
```

---

## How They Connect

```
  DroidFish (Android)                    Chess-UCI-Server (Desktop/Cloud)
  ┌──────────────────┐                   ┌──────────────────────────────┐
  │  User Interface  │                   │  config.json (validated)     │
  │  Quick Play      │                   │  ┌────────┐  ┌────────────┐ │
  │  Game Logic      │   TCP/TLS Socket  │  │Port    │  │ Stockfish  │ │
  │  GameViewModel   │◄═════════════════►│  │9998    │──│ Process    │ │
  │                  │   UCI + Auth      │  │        │  │ (stdin/out)│ │
  │  NetworkEngine   │                   │  └────────┘  └────────────┘ │
  │  (TLS, Auth,     │   ┌──────────┐   │  ┌────────┐  ┌────────────┐ │
  │   Reconnect)     │   │ mDNS /   │   │  │Port    │  │ Dragon     │ │
  │                  │◄──│ QR Code  │──►│  │9999    │──│ Process    │ │
  │  NetworkDiscovery│   │ Discovery│   │  └────────┘  └────────────┘ │
  └──────────────────┘   └──────────┘   │  SessionManager / Throttler │
                                         │  Security / Logging / mDNS  │
                                         └──────────────────────────────┘
```

The connection flow:
1. Chess-UCI-Server starts, validates config, optionally enables TLS and mDNS
2. DroidFish discovers the server via **mDNS**, **QR scan**, **connection file import**, or **manual entry**
3. DroidFish opens a TCP/TLS socket, authenticates if required, sends UCI commands
4. The server proxies commands through SessionManager and OutputThrottler
5. On disconnect, engine stays warm via SessionManager for fast reconnection

## Documentation

See the [`docs/`](docs/) directory for detailed documentation:

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System architecture and component deep-dive |
| [DroidFish Features](docs/droidfish-features.md) | Complete feature reference (UI, engines, PGN, etc.) |
| [DroidFish Settings](docs/droidfish-settings.md) | All ~90+ configurable settings |
| [DroidFish Game Logic](docs/droidfish-game-logic.md) | MVC architecture, controller/model internals |
| [DroidFish Improvements](docs/droidfish-improvements.md) | Issues, proposals, and status |
| [Strengths & Weaknesses](docs/strengths-weaknesses.md) | Analysis of both projects |
| [Improvement Plan](docs/improvement-plan.md) | Planned enhancements and roadmap |
| [Integration Guide](docs/integration-guide.md) | Setup, TLS, auth, QR pairing, and connection instructions |

Server-specific documentation is in [`chess-uci-server/docs/`](chess-uci-server/docs/):
[Configuration](chess-uci-server/docs/configuration.md) |
[Protocol](chess-uci-server/docs/protocol.md) |
[Relay Server](chess-uci-server/docs/relay.md) |
[Troubleshooting](chess-uci-server/docs/troubleshooting.md)

## UCI Protocol Basics

The Universal Chess Interface (UCI) protocol is a text-based standard for communication between chess GUIs and engines:

| Direction | Commands | Description |
|-----------|----------|-------------|
| GUI → Engine | `uci` | Request engine identification |
| GUI → Engine | `isready` | Check if engine is ready |
| GUI → Engine | `position startpos moves e2e4 e7e5` | Set board position |
| GUI → Engine | `go depth 20` | Start searching |
| GUI → Engine | `stop` | Stop searching |
| Engine → GUI | `id name Stockfish`, `uciok` | Engine identification |
| Engine → GUI | `readyok` | Engine is ready |
| Engine → GUI | `info depth 20 score cp 30 pv e2e4` | Search progress |
| Engine → GUI | `bestmove e2e4` | Best move found |

## Development Setup

### Prerequisites
- **DroidFish**: JDK 8+, Android SDK 34, NDK 25
- **Chess-UCI-Server**: Python 3.12+ (or Docker)
- **QA Tests**: Python 3.12+, `pip install pytest pytest-asyncio pytest-timeout`
- **Optional Server Deps**: `pip install qrcode zeroconf` (for QR pairing and mDNS)
- **Chess Engines**: At least one UCI engine (e.g., Stockfish)

### Quick Start

```bash
# Clone
git clone https://github.com/vidar808/Droidfish_fork.git
cd Droidfish_fork

# Option A: Start server directly
cd chess-uci-server
pip install qrcode zeroconf  # optional deps
python chess.py --setup       # interactive setup wizard
python chess.py               # start server

# Option B: Start server with Docker
cd chess-uci-server/deploy/linux
docker-compose up -d

# Build DroidFish (requires Android SDK)
cd droidfish
./gradlew assembleDebug

# Run server unit tests
cd chess-uci-server
python3 -m pytest tests/ -v  # 228 tests

# Run QA integration suite
cd qa
pip install -r requirements.txt
python3 -m pytest -v          # 93 tests
```

## QA Test Suite (`/qa/`)

A comprehensive test suite covering the Chess-UCI-Server, relay server, and bundled engine binaries. Uses a mock UCI engine for server tests and validates real engines on the Android emulator.

| Category | Tests | Coverage |
|----------|-------|----------|
| **Integration** | 25 | Auth (token/PSK), TLS, multiplex, sessions, throttling, lifecycle |
| **E2E** | 19+ | Full UCI protocol exchange, reconnect, relay passthrough, multi-client |
| **Stress** | 8 | Concurrent clients, sustained sessions, throughput |
| **Error** | 12 | Engine crash/hang, network errors, malformed input |
| **Android** | 29 | Emulator engine validation (Stockfish 18, Rodent IV, Patricia), APK build/install |

```bash
# Run all tests (excluding slow Android APK tests)
cd qa
python3 -m pytest -v -m "not slow"

# Run Android emulator engine validation (requires running emulator)
python3 -m pytest android/ -v -k "not APK and not Instrumented"

# Run only server integration tests
python3 -m pytest integration/ -v
```

See [`qa/README.md`](qa/README.md) for full documentation.

## Improvement Roadmap

### Phase 1: Foundation - COMPLETE
- [x] Cross-platform firewall abstraction (WindowsFirewall, NoopFirewall)
- [x] Reconnection with exponential backoff in DroidFish NetworkEngine
- [x] 228 pytest tests for Chess-UCI-Server + 3 JUnit test classes for DroidFish
- [x] Config validation, async subprocess, async locks, auto-trust, heartbeat fix
- [x] CuckooChess removal, build modernization (Gradle 8.4, SDK 34), Stockfish 18
- [x] Engine I/O fixes (stderr logging, socket timeout, LocalPipe notifyAll, async writes)

### Phase 2: Security & Reliability - COMPLETE
- [x] TLS encryption for TCP connection (both server and client)
- [x] Token-based authentication (AUTH_REQUIRED/AUTH/AUTH_OK)
- [x] SessionManager - warm engine reattach after disconnect
- [x] OutputThrottler - rate-limited UCI info lines
- [x] Graceful shutdown with session cleanup
- [x] QR code pairing + mDNS discovery (server + client)
- [x] Quick Play dialog (ELO/time/color one-tap setup)
- [x] GameViewModel for lifecycle persistence
- [x] SAF migration for PGN files (content:// URI support)
- [x] Docker support (Dockerfile + docker-compose.yml)

### Phase 3: Enhanced Features - OPEN
- [ ] REST API for server monitoring and management
- [ ] Web-based admin dashboard for Chess-UCI-Server
- [ ] Hot-reload engine configuration without restart
- [ ] Multi-client engine sharing (analysis mode)
- [ ] Engine tournament mode
- [ ] Linux/macOS firewall backends (iptables, pfctl)
- [ ] pyproject.toml and proper Python packaging
- [ ] systemd service file

### Phase 4: Integration Improvements - OPEN
- [ ] Position recovery after reconnect (resend position command)
- [ ] Engine capability negotiation
- [ ] Connection health indicator in DroidFish UI
- [ ] Certificate pinning (TOFU model)
- [ ] Push notifications for long analyses
- [ ] Refactor DroidFish monolithic main activity

## License

- **DroidFish**: GPL-3.0 (Peter Osterlund)
- **Chess-UCI-Server**: GPL-3.0 (compatible with DroidFish)
- **Integration work**: GPL-3.0 (all components share the same license)
