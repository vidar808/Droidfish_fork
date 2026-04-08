# CLAUDE.md - Chess UCI Integration Project

## Project Overview

This workspace integrates two complementary open-source chess projects to create a unified, enhanced chess engine server and client system:

1. **DroidFish** (`/droidfish/`) - Feature-rich Android chess GUI with UCI engine support
2. **Chess-UCI-Server** (`/chess-uci-server/`) - Python-based network UCI engine server

## Architecture

```
┌─────────────────────┐    TCP/TLS       ┌──────────────────────┐
│   DroidFish App     │ ◄══════════════► │  Chess-UCI-Server    │
│   (Android Client)  │   UCI Protocol   │  (Python Server)     │
│                     │   + Auth Token   │                      │
│  NetworkEngine.java │                  │  chess.py (asyncio)  │
│  - TLS encryption   │   Discovery:     │  Manages engines:    │
│  - Token auth       │  mDNS/QR/Import  │  - Stockfish         │
│  - Reconnection     │                  │  - Dragon, etc.      │
│                     │                  │                      │
│  Built-in engine:   │                  │  Features:           │
│  - Stockfish 18     │                  │  - TLS + token auth  │
│                     │                  │  - SessionManager    │
│  Discovery:         │                  │  - OutputThrottler   │
│  - NsdManager/mDNS  │                  │  - mDNS + QR pairing │
│  - QR code scanner  │                  │  - Docker support    │
└─────────────────────┘                  └──────────────────────┘
```

## Repository Structure

```
/var/opt/CHESS/
├── CLAUDE.md              # This file - project context for Claude
├── README.md              # Project overview and roadmap
├── docs/                  # Documentation
│   ├── architecture.md    # System architecture deep-dive
│   ├── enhanced-opening-book.md # Enhanced opening book with gambit colors
│   ├── droidfish-features.md    # Complete feature reference
│   ├── droidfish-settings.md    # All ~90+ settings
│   ├── droidfish-game-logic.md  # MVC architecture internals
│   ├── droidfish-improvements.md # Issues and proposals
│   ├── strengths-weaknesses.md  # Analysis of both projects
│   ├── improvement-plan.md      # Planned enhancements
│   └── integration-guide.md     # Setup, TLS, auth, discovery
├── book-library/          # Opening book research & build tools
│   ├── enhanced-eco.pgn   # Master enhanced PGN (4,107 lines, gambit-tagged)
│   ├── sources.md         # Public source catalog with licenses
│   ├── gambit-catalog.md  # Gambit inventory by color
│   ├── pgn/eco/           # Source datasets (Lichess, SCID, original)
│   └── analysis/          # Coverage analysis & build test scripts
├── droidfish/             # DroidFish source (cloned from GitHub)
│   ├── DroidFishApp/      # Main Android app module (compileSdk 34, minSdk 21)
│   ├── EngineServer/      # Built-in Java engine server
│   └── build.gradle       # Gradle 8.4 / AGP 8.2.0
└── chess-uci-server/      # Chess-UCI-Server source (cloned)
    ├── deploy/
    │   ├── linux/
    │   │   ├── chess.py          # Main Python server (~3,100 lines)
    │   │   ├── relay_server.py   # Relay server for NAT traversal (~263 lines)
    │   │   ├── engines/          # Linux engine binaries
    │   │   ├── install.sh        # Installation script
    │   │   └── Dockerfile        # Docker image
    │   └── windows/
    │       ├── chess.py          # Windows variant
    │       ├── engines/          # Windows engine .exe files
    │       └── install.bat       # Installation script
    ├── tests/
    │   ├── test_chess.py         # Server tests (228 total across both files)
    │   └── test_relay.py         # Relay server tests
    ├── docs/                     # Configuration, protocol, relay, troubleshooting
    └── config.json               # Server configuration (auto-generated)
```

## Key Integration Points

### DroidFish NetworkEngine (Client Side)
- **File**: `droidfish/DroidFishApp/src/main/java/org/petero/droidfish/engine/NetworkEngine.java`
- Connects via TCP or TLS socket to `host:port`
- Optional token-based authentication (AUTH_REQUIRED/AUTH/AUTH_OK)
- Reads engine config from a 14-line NETE file (name, host, port, tls, token, fingerprint, auth_method, psk, relay_host, relay_port, relay_session, external_host, mdns_name, selected_engine)
- Reconnection with exponential backoff (up to 5 attempts)
- Position tracking for future recovery
- Uses `LocalPipe` for thread-safe command buffering

### DroidFish Discovery
- **NetworkDiscovery.java**: NsdManager-based mDNS discovery of `_chess-uci._tcp` services
- **QR Scanner**: ZXing integration parses JSON payload (host, engines, tls, token)
- Both accessed via buttons in network engine config dialog

### DroidFish EngineServer (Built-in Java Server)
- **File**: `droidfish/EngineServer/src/main/java/org/petero/engineserver/EngineServer.java`
- Simple Java TCP server with Swing GUI
- Supports up to 20 engine slots
- No security, no logging, no connection management

### Chess-UCI-Server (Python Server - Enhanced Replacement)
- **File**: `chess-uci-server/deploy/linux/chess.py` (~3,100 lines)
- Python asyncio-based TCP server with optional TLS and token/PSK auth
- Multi-engine support with single-port mode and per-engine ports
- Engine auto-discovery from `engine_directory`
- SessionManager: keeps engines alive after disconnect for warm reattach
- OutputThrottler: rate-limits UCI info lines for bandwidth control
- mDNS advertisement via zeroconf (`_chess-uci._tcp`)
- UPnP automatic port mapping
- QR code pairing, connection file generation
- Relay server support for NAT traversal (`relay_server.py`, ~263 lines)
- Security: trusted IPs, subnets, auto-trust, firewall abstraction
- Comprehensive logging and watchdog timer
- 228 pytest tests (in `tests/` directory)

## UCI Protocol Basics

The Universal Chess Interface (UCI) protocol is text-based:
- **GUI → Engine**: `uci`, `isready`, `position startpos moves e2e4 e7e5`, `go depth 20`
- **Engine → GUI**: `id name Stockfish`, `uciok`, `readyok`, `bestmove e2e4`, `info depth 20 score cp 30 pv e2e4`

## Development Guidelines

- DroidFish is GPL-3.0 licensed - all modifications must remain open source
- DroidFish uses Java 1.8 with Android SDK 34 (min SDK 21) and Gradle 8.4 / AGP 8.2.0
- Chess-UCI-Server is Python 3.12+ with optional deps (qrcode, zeroconf)
- The TCP protocol supports optional TLS encryption and token authentication
- Both projects are cross-platform; DroidFish additionally targets Android
- Server tests: `python3 -m pytest tests/ -v` (228 tests)

## Recent Improvements

- **Enhanced Opening Book**: Internal book expanded from 2,014 to 4,107 lines with
  gambit-specific color coding (943 white gambit, 203 black gambit, 7 mutual).
  Binary format v2 with metadata. See `docs/enhanced-opening-book.md`.

## Current Improvement Focus

1. **REST API**: Add HTTP API alongside raw TCP for status monitoring
2. **Multi-client per engine**: Allow multiple DroidFish clients to share engines
3. **Engine management**: Hot-reload engine configs without server restart
4. **Position recovery**: Resend position after reconnect
5. **Linux/macOS firewall**: Add iptables/pfctl backends
6. **Activity refactoring**: Break up monolithic DroidFish.java
