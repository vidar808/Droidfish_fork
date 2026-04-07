# Chess UCI Integration Project

A unified development workspace combining **DroidFish** (Android chess GUI) and **Chess-UCI-Server** (Python network engine server) to create an enhanced, secure, cross-platform chess analysis system.

## Project Goals

- Improve interoperability between DroidFish and Chess-UCI-Server
- Add security and reliability features missing from both projects
- Create cross-platform server support (Linux, macOS, Windows)
- Build comprehensive documentation and testing infrastructure
- Develop new features that leverage the combined strengths of both projects

## Sub-Projects

### DroidFish (`/droidfish/`)

**Source**: [peterosterlund2/droidfish](https://github.com/peterosterlund2/droidfish)
**Language**: Java/C++ | **License**: GPL-3.0 | **Stars**: 400+

A feature-rich Android chess application that serves as the primary client in our architecture.

**Key Features:**
- Bundled Stockfish 18 engine (compiled via NDK/JNI) with UCI_Elo strength limiting (1320-3190)
- **Quick Play dialog** - one-tap game setup with ELO, time control, and color selection
- Full PGN/FEN support for game import/export (including SAF `content://` URIs)
- Opening book integration (Polyglot, CTG, ABK formats)
- Endgame tablebase support (Syzygy 3-4-5-6 piece, Gaviota)
- Multi-PV engine analysis with real-time display
- Remote/network engine support via **TCP/TLS** with **token authentication**
- **QR code scanning**, **mDNS auto-discovery**, and **connection file import** for network engine pairing
- **Reconnection** with exponential backoff on network disconnect
- **GameViewModel** for game state persistence across configuration changes
- Built-in Java EngineServer for hosting engines on desktop
- Board editor, game annotations, ECO classification
- Localized in 15+ languages

**Architecture** (Gradle 8.4 / AGP 8.2.0):
| Module | Purpose |
|--------|---------|
| `DroidFishApp` | Main Android application (Java, compileSdk 34, minSdk 21) |
| `EngineServer` | Desktop Java server for hosting UCI engines |

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

## Development Setup

### Prerequisites
- **DroidFish**: Android Studio, JDK 8+, Android SDK 34, NDK
- **Chess-UCI-Server**: Python 3.12+ (or Docker)
- **Optional Server Deps**: `pip install qrcode zeroconf` (for QR pairing and mDNS)
- **Chess Engines**: At least one UCI engine (e.g., Stockfish)

### Quick Start

```bash
# Clone this workspace (already done)
cd /var/opt/CHESS

# Option A: Start server directly
cd chess-uci-server
pip install qrcode zeroconf  # optional deps
# Edit config.json with your engine paths
python chess.py

# Option B: Start server with Docker
cd chess-uci-server
docker-compose up -d

# Build DroidFish (requires Android SDK)
cd ../droidfish
./gradlew assembleDebug

# Run server tests
cd chess-uci-server
python3 -m pytest tests/ -v  # 228 tests
```

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
