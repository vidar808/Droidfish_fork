# Integration Guide

## How DroidFish Connects to Chess-UCI-Server

### Overview

DroidFish communicates with Chess-UCI-Server using the UCI protocol over TCP:
- **Transport**: TCP socket with optional TLS encryption
- **Protocol**: UCI (Universal Chess Interface) text commands, newline-delimited
- **Authentication**: Optional token-based (AUTH_REQUIRED/AUTH/AUTH_OK handshake)
- **Encryption**: Optional TLS (server cert + key, client trust-all for user-configured servers)
- **Discovery**: mDNS (`_chess-uci._tcp`) and QR code pairing

### Step-by-Step Connection Flow

#### 1. Server Startup

When `chess.py` starts, it:
1. Loads and validates `config.json` (`load_config()` + `validate_config()`)
2. Calls `unblock_trusted_ips_and_subnets()` to clean firewall rules
3. Configures logging via `setup_logging()`
4. Creates TLS context if `enable_tls` is set (`create_ssl_context()`)
5. For each engine in `config["engines"]`:
   - Creates an `asyncio.start_server` listener on the engine's configured port
6. Starts mDNS advertisement if `enable_mdns` is set (`start_mdns_advertisement()`)
7. Starts the watchdog timer
8. Waits for shutdown signal
9. On shutdown: stops mDNS, shuts down SessionManager, closes connections

```
Server starts → Validating config...
                 TLS enabled (cert loaded)
                 Listening on port 9998 (Stockfish)
                 Listening on port 9999 (Dragon)
                 mDNS: advertising _chess-uci._tcp services
```

#### 2. DroidFish Configuration

In DroidFish, the user has four ways to configure a network engine:

**Option A: Manual Entry**
1. Opens the left drawer menu → "Manage Chess Engines"
2. Selects "New Network Engine"
3. Enters hostname/IP, port, TLS toggle, and optional auth token

**Option B: QR Code Scanning**
1. On the server, run `generate_qr_pairing()` to create a QR code image
2. In DroidFish, tap "Scan QR" in the network engine config dialog
3. The QR code JSON payload auto-fills host, port, TLS, and auth token

**Option C: mDNS Auto-Discovery**
1. Ensure the server has `enable_mdns: true` in config
2. In DroidFish, tap "Discover" in the network engine config dialog
3. After a 3-second scan, select from discovered servers

**Option D: Import Connection File**
1. On the server, run with `--pair` to generate a `connection.chessuci` file
2. Transfer the file to the Android device (USB, email, cloud storage, etc.)
3. In DroidFish, tap "Import Connection File" in the network engine config dialog
4. Select the `.chessuci` file from the system file picker
5. DroidFish imports the engine configuration(s) and creates NETE profiles automatically

DroidFish saves the config as a 14-line NETE file:
```
NETE
192.168.1.100
9998
tls
my-secret-token

token

relay.example.com
19000
a1b2c3d4e5f6
203.0.113.45
Stockfish._chess-uci._tcp.local.
Stockfish
```

Lines are: name, host, port, tls flag, auth token, certificate fingerprint, auth method, PSK key, relay host, relay port, relay session, external host, mDNS name, selected engine. Empty lines represent unused fields.

#### 3. Connection Establishment

When the user selects the network engine, `NetworkEngine.java` executes:

```
1. startProcess() is called
   ├── startupThread starts (monitors for 10s UCI timeout)
   ├── stdInThread starts:
   │   ├── connect() opens Socket or SSLSocket (host, port) with TCP_NODELAY
   │   ├── If TLS: wraps in SSLSocket via SSLSocketFactory (trust-all)
   │   ├── If auth token set: reads AUTH_REQUIRED, sends AUTH <token>, waits AUTH_OK
   │   └── Reads lines from socket → engineToGui pipe
   └── stdOutThread starts:
       ├── connect() (same socket, synchronized)
       └── Reads lines from guiToEngine pipe → writes to socket (async)
   On disconnect: exponential backoff reconnection (up to 5 attempts, 1s-30s)
```

#### 4. Server-Side Handling

When the TCP connection arrives at Chess-UCI-Server:

```
1. client_handler() coroutine starts
2. TLS handshake (if enable_tls is set)
3. Token authentication (if auth_token is configured):
   ├── Send "AUTH_REQUIRED" to client
   ├── Wait for "AUTH <token>" from client
   ├── If token matches: send "AUTH_OK"
   └── If token wrong/timeout: send "AUTH_FAIL", close connection
4. Extract client IP from socket peername
5. Trust verification:
   ├── Check if IP is in trusted_sources
   ├── Check if IP is in any trusted_subnet
   ├── If auto-trust enabled: handle_auto_trust() adds IP at runtime
   └── If untrusted: log attempt, close connection
6. Acquire semaphore (max_connections limit)
7. SessionManager: try to reattach to existing warm session, or spawn new engine:
   engine_process = session_manager.get_or_create(engine_name, engine_path)
8. Start heartbeat task (sends "isready" to engine)
9. Process initial UCI handshake:
   ├── Send "uci" command to engine
   ├── Send custom_variables as setoption commands
   └── Wait for "uciok" response
10. Start bidirectional proxy:
    ├── process_client_commands(): client → engine
    │   (with setoption override logic)
    └── process_engine_responses(): engine → client
        (filtered through OutputThrottler for rate limiting)
11. On disconnect: release to SessionManager (keeps engine warm for reattach)
```

#### 5. UCI Communication

Example session (with TLS and auth enabled):

```
Client (DroidFish)              Server (chess.py)           Engine (Stockfish)
      │                              │                            │
      │═══ TLS handshake ═══════════►│                            │
      │◄═════════════════════════════│                            │
      │                              │                            │
      │◄── "AUTH_REQUIRED" ──────────│                            │
      │──── "AUTH my-secret" ───────►│                            │
      │◄── "AUTH_OK" ────────────────│                            │
      │                              │                            │
      │──── "uci" ──────────────────►│──── "uci" ────────────────►│
      │                              │◄─── "id name Stockfish" ───│
      │                              │     (injects custom vars)  │
      │                              │──── "setoption name Hash   │
      │                              │      value 32000" ────────►│
      │                              │◄─── "uciok" ──────────────│
      │◄─── "id name Stockfish" ─────│                            │
      │◄─── "uciok" ────────────────│                            │
      │                              │                            │
      │──── "isready" ──────────────►│──── "isready" ────────────►│
      │◄─── "readyok" ──────────────│◄─── "readyok" ────────────│
      │                              │                            │
      │──── "position startpos      │                            │
      │      moves e2e4" ──────────►│──── (same) ───────────────►│
      │                              │                            │
      │──── "go depth 20" ─────────►│──── (same) ───────────────►│
      │◄─── "info depth 1..." ──────│◄─── "info depth 1..." ────│
      │◄─── "info depth 2..." ──────│◄─── "info depth 2..." ────│
      │     ...                      │     ...                    │
      │◄─── "bestmove e2e4" ────────│◄─── "bestmove e2e4" ──────│
      │                              │                            │
      │──── "quit" ─────────────────►│──── terminate engine ──────│
      │     (connection closes)      │     (cleanup)              │
```

#### 6. UCI Option Override Logic

When a `setoption` command arrives from the client:

```python
if option is in engine-specific custom_variables:
    if value is "override":
        pass through client's value  # Client controls this option
    else:
        substitute server's value    # Server enforces its value
elif option is in global custom_variables:
    substitute server's value        # Server enforces its value
else:
    pass through client's value      # Client controls this option
```

Example with config:
```json
{
  "custom_variables": {"Hash": "32000", "Threads": "32"},
  "engines": {
    "Stockfish": {
      "custom_variables": {"Threads": "40"}
    },
    "Tal": {
      "custom_variables": {"Threads": "override"}
    }
  }
}
```

- Client sends `setoption name Hash value 128` → Server sends `setoption name Hash value 32000`
- Client sends `setoption name Threads value 4` to Stockfish → Server sends `setoption name Threads value 40`
- Client sends `setoption name Threads value 4` to Tal → Server sends `setoption name Threads value 4` (override)

#### 7. Connection Termination

**Normal disconnect (client-initiated)**:
- DroidFish sends `quit` command or TCP connection closes
- Chess-UCI-Server releases engine to SessionManager
- If `session_keepalive_seconds > 0`: engine stays warm for reconnection
- If keepalive is 0 or expires: engine process is terminated

**Reconnection (DroidFish)**:
- On disconnect, DroidFish attempts reconnection with exponential backoff
- Up to 5 attempts, delays from 1s to 30s
- Stores `lastPosition`/`lastGo` for future position recovery

**SessionManager (server-side)**:
- Keeps engine subprocess alive after TCP disconnect
- On reconnect within keepalive window: reattaches to warm engine (preserves hash tables)
- On keepalive expiry: terminates engine process and cleans up

**Inactivity timeout**:
- Server monitors last activity time
- After `inactivity_timeout` seconds (default: 900), server closes connection

**Error conditions**:
- Engine process crashes → Server logs error, closes client connection
- Network interruption → Both sides detect broken pipe, clean up
- DroidFish reports "Engine terminated" to user, attempts reconnection

---

## Setup Instructions

### Setting Up Chess-UCI-Server

#### Option A: Direct Python

1. **Install Python 3.12+** and optional dependencies:
   ```bash
   pip install qrcode zeroconf  # optional: QR pairing + mDNS
   ```

2. **Download chess engines** (e.g., Stockfish from https://stockfishchess.org)

3. **Configure `config.json`**:
   ```json
   {
     "host": "0.0.0.0",
     "base_log_dir": "/path/to/logs",
     "display_uci_communication": true,
     "enable_trusted_sources": true,
     "trusted_sources": ["127.0.0.1", "YOUR_PHONE_IP"],
     "trusted_subnets": ["192.168.1.0/24"],
     "max_connections": 10,
     "enable_tls": false,
     "tls_cert_path": "",
     "tls_key_path": "",
     "auth_token": "",
     "enable_mdns": true,
     "session_keepalive_seconds": 300,
     "output_throttle_ms": 100,
     "engines": {
       "Stockfish": {
         "path": "/path/to/stockfish",
         "port": 9998
       }
     },
     "custom_variables": {
       "Hash": "4096",
       "Threads": "4"
     }
   }
   ```

4. **Start the server**:
   ```bash
   python chess.py
   ```

#### Option B: Docker

1. **Build and run**:
   ```bash
   docker-compose up -d
   ```

2. **Or build manually**:
   ```bash
   docker build -t chess-uci-server .
   docker run -p 9998:9998 -v ./config.json:/app/config.json chess-uci-server
   ```

#### TLS Setup (Recommended for WAN)

1. **Generate a self-signed certificate**:
   ```bash
   openssl req -x509 -newkey rsa:4096 -keyout server.key -out server.crt -days 365 -nodes
   ```

2. **Update config.json**:
   ```json
   {
     "enable_tls": true,
     "tls_cert_path": "/path/to/server.crt",
     "tls_key_path": "/path/to/server.key",
     "auth_token": "your-secret-token"
   }
   ```

3. **Configure port forwarding** (if accessing over internet):
   - Forward the engine ports (e.g., 9998) on your router
   - With TLS + auth enabled, WAN access is now reasonably secure

### Configuring DroidFish

#### Manual Configuration
1. **Open DroidFish** on your Android device
2. **Navigate**: Left drawer menu → "Manage Chess Engines"
3. **Add network engine**: Select "New Network Engine"
4. **Enter connection details**:
   - Host: Server IP address (e.g., `192.168.1.100`)
   - Port: Engine port (e.g., `9998`)
   - TLS: Check if server has TLS enabled
   - Auth Token: Enter the token if server requires authentication
5. **Select the engine**: It should now appear in the engine list
6. **Start analysis**: The engine runs remotely on your server

#### QR Code Pairing (Fastest)
1. On the server, the QR code is generated at startup (if `qrcode` is installed)
2. In DroidFish, go to "New Network Engine" → tap **"Scan QR"**
3. Point camera at the QR code → connection details auto-fill

#### mDNS Discovery (LAN only)
1. Ensure server has `enable_mdns: true`
2. In DroidFish, go to "New Network Engine" → tap **"Discover"**
3. Wait 3 seconds → select from discovered servers

### Verifying the Connection

On the server side, you should see:
```
Connection opened from 192.168.1.50
Authentication successful for 192.168.1.50
Initiating engine /path/to/stockfish for client 192.168.1.50
Client: uci
Engine: id name Stockfish 18
Engine: uciok
```

In DroidFish, the engine name should appear and analysis should begin.

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "Failed to start engine" | Can't reach server | Check IP, port, firewall, network |
| "UCI protocol error" | Engine didn't respond with `uciok` in 10s | Check engine path on server |
| "Engine terminated" | Connection dropped | Check server logs; DroidFish will auto-reconnect |
| "AUTH_FAIL" in logs | Wrong auth token | Verify token matches between client and server config |
| TLS handshake failure | Certificate issues | Ensure cert/key paths are correct; DroidFish trusts all certs |
| Untrusted connection log | Client IP not in trusted list | Add phone IP to `trusted_sources` or enable `enable_auto_trust` |
| No connection at all | Port not open | Configure port forwarding or use LAN |
| Slow analysis | Network latency / too many info lines | Use LAN; server's OutputThrottler reduces info line bandwidth |
| "Discover" finds nothing | mDNS not enabled or different subnet | Set `enable_mdns: true` on server; ensure same LAN |
| QR scan fails | Camera permission denied | Grant camera permission in Android settings |

---

## Network Requirements

- Both devices must be on the same network (LAN recommended)
- Or port forwarding configured on router (for WAN access)
- Typical bandwidth: ~1-10 KB/s (UCI text is very lightweight)
- Latency: <100ms recommended for responsive analysis
- Ports: One port per engine (default starting at 9998)
