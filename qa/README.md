# Chess UCI Server - QA Test Suite

Dedicated QA testing suite for the Chess UCI Server and relay server. Tests the server's TCP handling, UCI protocol relay, authentication, TLS, session management, multiplexing, and error recovery using real socket connections and a mock UCI engine.

## Structure

```
qa/
├── conftest.py                  # Shared pytest fixtures (server, relay, configs)
├── pytest.ini                   # Pytest configuration
├── requirements.txt             # Test dependencies
│
├── fixtures/                    # Test helpers
│   ├── mock_engine.py           # Mock UCI engine (responds to uci, go, isready, etc.)
│   ├── mock_client.py           # Async TCP client helper for server interactions
│   └── certs/                   # Pre-generated test TLS certificates
│       ├── test.crt
│       └── test.key
│
├── integration/                 # Server component tests over real TCP
│   ├── test_server_lifecycle.py # Startup, shutdown, PID file management (6 tests)
│   ├── test_auth_flows.py       # Token and PSK authentication (6 tests)
│   ├── test_tls.py              # TLS connections and cert handling (3 tests)
│   ├── test_multiplex.py        # Single-port engine multiplexing (4 tests)
│   ├── test_session_mgmt.py     # Session keepalive and warm reattach (3 tests)
│   └── test_throttler_live.py   # Output throttling with real timing (3 tests)
│
├── e2e/                         # End-to-end tests
│   ├── test_uci_protocol.py     # Full UCI command/response exchange (9 tests)
│   ├── test_reconnect.py        # Disconnect/reconnect behavior (3 tests)
│   ├── test_relay_e2e.py        # Relay server register/pair/passthrough (4 tests)
│   ├── test_multi_client.py     # Multiple simultaneous clients (3 tests)
│   └── test_engine_validation.py # Validate installed UCI engines (4 tests per engine)
│
├── stress/                      # Load and stability tests
│   ├── test_concurrent.py       # Many simultaneous clients (3 tests)
│   ├── test_long_running.py     # Extended session stability (2 tests)
│   └── test_throughput.py       # Command throughput and throttling (3 tests)
│
├── error/                       # Error handling and recovery
│   ├── test_engine_crash.py     # Engine crash/hang during session (3 tests)
│   ├── test_network_errors.py   # Connection errors, trust, rejection (5 tests)
│   └── test_malformed_input.py  # Invalid/oversized/binary input (4 tests)
│
└── android/                     # Android emulator tests
    └── test_emulator_engines.py # Validate bundled engines on emulator (29 tests)
                                 #   - UCI handshake (3 engines)
                                 #   - isready/readyok (3 engines)
                                 #   - Move calculation + bestmove (3 engines)
                                 #   - FEN positions + move sequences (3 engines)
                                 #   - UCI options (Hash, Threads) (3 engines)
                                 #   - APK build, install, app launch
                                 #   - Instrumented androidTest runner
```

## Quick Start

```bash
# Install dependencies
pip install -r qa/requirements.txt

# Run all tests
cd /var/opt/CHESS/qa
python3 -m pytest -v

# Run specific test category
python3 -m pytest integration/ -v
python3 -m pytest e2e/ -v
python3 -m pytest stress/ -v
python3 -m pytest error/ -v

# Run excluding slow tests
python3 -m pytest -v -m "not slow"

# Run only TLS tests
python3 -m pytest -v -m tls

# Run only relay tests
python3 -m pytest -v -m relay
```

## Engine Validation

The `e2e/test_engine_validation.py` module auto-discovers installed UCI engines and validates each one:

```bash
# Install an engine (e.g., stockfish)
apt install stockfish

# Run engine validation
python3 -m pytest e2e/test_engine_validation.py -v

# Or point to a custom engine directory
ENGINE_VALIDATION_DIR=/path/to/engines python3 -m pytest e2e/test_engine_validation.py -v
```

Each discovered engine is tested for:
- UCI handshake (uci -> id name + uciok)
- Readiness (isready -> readyok)
- Move calculation (position + go depth 5 -> bestmove)
- Clean shutdown (quit -> process exit)

Engines are discovered from:
1. System PATH (stockfish, lc0, komodo, etc.)
2. `chess-uci-server/deploy/linux/engines/` directory
3. Custom directory via `ENGINE_VALIDATION_DIR` environment variable

## Android Emulator Tests

Tests that push bundled engine binaries (Stockfish 18, Rodent IV, Patricia) to the Android emulator and validate them via adb shell:

```bash
# Run all Android engine tests (requires running emulator)
python3 -m pytest android/ -v -k "not APK and not Instrumented and not unit"

# Run including APK build/install tests (slow)
python3 -m pytest android/ -v

# Run only Stockfish tests
python3 -m pytest android/ -v -k "Stockfish"
```

Each engine is validated for:
- UCI handshake (uci -> id name + uciok)
- Readiness (isready -> readyok)
- Move calculation from starting position (go depth 5 -> bestmove)
- FEN position processing (Sicilian Defense)
- Position with move history (Ruy Lopez)
- UCI option acceptance (Hash, Threads -> readyok)

Additional APK tests (marked `slow`):
- Build debug APK via Gradle
- Install APK on emulator
- Launch DroidFish activity
- Run JVM unit tests
- Run instrumented androidTest suite

## Test Categories

| Category | Tests | What it covers |
|----------|-------|----------------|
| **Integration** | 25 | Server components over real TCP sockets |
| **E2E** | 19+ | Full protocol exchange through the server |
| **Stress** | 8 | Concurrency, sustained load, throughput |
| **Error** | 12 | Crashes, network errors, malformed input |
| **Android** | 29 | Emulator engine validation, APK build/install |
| **Total** | 93+ | (engine validation adds 4 per discovered engine) |

## Test Markers

- `slow` — Tests that take >5 seconds (session expiry waits, etc.)
- `tls` — Tests requiring TLS certificate handling
- `relay` — Tests that start a relay server
- `engine` — Tests that validate real UCI engine binaries
- `android` — Tests requiring an Android emulator

## Mock Engine

The mock engine (`fixtures/mock_engine.py`) is a minimal UCI-compliant engine that supports:
- `uci` → responds with id, options, uciok
- `isready` → readyok
- `go depth N` → info lines + bestmove e2e4
- `stop` → bestmove e2e4
- `quit` → clean exit

Special modes for error testing:
- `--hang` — Never sends uciok (timeout testing)
- `--crash` — Exits immediately on uci (crash testing)
- `--slow N` — Delays N seconds before each response

## Known Limitations

- **Session warm reattach**: The `SessionManager` warm reattach (reconnecting to a kept-alive engine) can lose engine stdout data between session handoffs. These tests are marked `xfail`.
- **Engine validation**: Skipped if no UCI engines are installed on the system.
- **Startup time**: Server startup includes a WAN IP lookup (up to 9s) which affects test speed. Tests allow up to 30s for server readiness.
