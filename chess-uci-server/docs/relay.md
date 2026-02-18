# Relay Server Documentation

## 1. Overview

The Chess UCI Relay Server provides NAT traversal for chess engine servers and
DroidFish clients that cannot connect directly due to strict NAT, firewalls, or
carrier-grade NAT (CGNAT). It is a standalone Python asyncio TCP server designed
to be deployed on any publicly reachable VPS.

The relay acts as a rendezvous point: the chess server registers a named session
and waits; a DroidFish client connects to the same session; the relay pairs them
and pipes all data bidirectionally. Neither the server nor the client needs to
accept inbound connections -- both connect outward to the relay.

**Key properties:**

- Standalone single-file server (`relay_server.py`, ~263 lines)
- No dependencies beyond Python 3.8+ standard library
- Default port: 19000
- Maximum concurrent sessions: 100 (configurable)
- Stale session timeout: 1 hour
- License: GPL-3.0

**Source location:** `/chess-uci-server/deploy/linux/relay_server.py`


## 2. Architecture

```
                         Internet / VPS
                    ┌─────────────────────┐
                    │   Relay Server      │
                    │   (relay_server.py) │
                    │   port 19000        │
                    │                     │
                    │  ┌───────────────┐  │
  Chess Server ─────┼──► Session Store ◄──┼───── DroidFish Client
  (outbound TCP)    │  │               │  │     (outbound TCP)
                    │  │  session_id:  │  │
                    │  │   server_rw   │  │
                    │  │   client_rw   │  │
                    │  └───────┬───────┘  │
                    │          │          │
                    │    Bidirectional    │
                    │    pipe(4096 buf)   │
                    └─────────────────────┘

Connection flow:

  Chess Server                  Relay                     DroidFish
       │                          │                           │
       │──SESSION <id> server\n──►│                           │
       │◄──────REGISTERED\n───────│                           │
       │         (waiting)        │                           │
       │                          │◄──SESSION <id> client\n───│
       │                          │────CONNECTED\n──────────►│
       │◄────────PAIRED\n─────────│                           │
       │                          │                           │
       │◄═══════ bidirectional UCI data piping ══════════════►│
       │                          │                           │
       │      (disconnect)        │        (disconnect)       │
       │──────────EOF────────────►│──────────EOF─────────────►│
```


## 3. Protocol Reference

All messages are newline-terminated ASCII text. The relay expects the first
message from any connection within 10 seconds, or the connection is closed.

### 3.1 Handshake Messages

| Direction       | Message                      | Description                                  |
|-----------------|------------------------------|----------------------------------------------|
| Server -> Relay | `SESSION <id> server\n`      | Register as the server for session `<id>`    |
| Relay -> Server | `REGISTERED\n`               | Registration accepted; waiting for client    |
| Client -> Relay | `SESSION <id> client\n`      | Connect as client to session `<id>`          |
| Relay -> Client | `CONNECTED\n`                | Client is connected; data relay begins       |
| Relay -> Server | `PAIRED\n`                   | A client has connected; data relay begins    |

### 3.2 Error Responses

| Message                          | Cause                                            |
|----------------------------------|--------------------------------------------------|
| `ERROR max sessions reached\n`   | Session limit exceeded (default 100)             |
| `ERROR unknown session\n`        | Client requested a session ID with no registered server |
| `ERROR invalid protocol\n`       | First line is not `SESSION <id> <role>`           |
| `ERROR invalid role\n`           | Role is not `server` or `client`                 |

### 3.3 Data Relay Phase

After the server receives `PAIRED` and the client receives `CONNECTED`, the
relay enters a transparent bidirectional pipe. All bytes sent by the server are
forwarded to the client and vice versa, using a 4096-byte read buffer. The pipe
continues until either side disconnects (EOF, connection reset, or broken pipe).

### 3.4 Full Exchange Example

```
Server                          Relay                          Client
  |                               |                              |
  |-- SESSION abc123 server\n --->|                              |
  |<-- REGISTERED\n --------------|                              |
  |                               |                              |
  |          ... time passes ...  |                              |
  |                               |<-- SESSION abc123 client\n --|
  |                               |--- CONNECTED\n ------------>|
  |<-- PAIRED\n ------------------|                              |
  |                               |                              |
  |== "uci\n" ===================>|== "uci\n" =================>|
  |<= "id name Stockfish 18\n" ==|<= "id name Stockfish 18\n" =|
  |<= "uciok\n" =================|<= "uciok\n" ================|
  |                               |                              |
  |          ... UCI protocol ... |                              |
  |                               |                              |
  |-- EOF (disconnect) ---------->|-- EOF (disconnect) -------->|
```

Note: In this diagram, the UCI data direction depends on who is talking.
The chess server forwards engine output to the client; the client sends
UCI commands (like `go depth 20`) to the server. The relay is agnostic
to content -- it simply copies bytes in both directions.


## 4. Running the Relay Server

### 4.1 Command-Line Usage

```bash
python3 relay_server.py [--port PORT] [--max-sessions N]
```

| Flag              | Default | Description                        |
|-------------------|---------|------------------------------------|
| `--port`          | 19000   | TCP port to listen on              |
| `--max-sessions`  | 100     | Maximum concurrent sessions        |

The server listens on `0.0.0.0` (all interfaces) and logs to stdout with
timestamps.

### 4.2 Basic Deployment on a VPS

```bash
# Copy the single file to your VPS
scp deploy/linux/relay_server.py user@vps.example.com:~/

# Run directly
ssh user@vps.example.com
python3 relay_server.py --port 19000

# Or run in background with nohup
nohup python3 relay_server.py --port 19000 > relay.log 2>&1 &
```

### 4.3 Systemd Service (Recommended)

Create `/etc/systemd/system/chess-relay.service`:

```ini
[Unit]
Description=Chess UCI Relay Server
After=network.target

[Service]
Type=simple
User=chess-relay
ExecStart=/usr/bin/python3 /opt/chess-relay/relay_server.py --port 19000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable chess-relay
sudo systemctl start chess-relay
sudo systemctl status chess-relay
```

### 4.4 Firewall

Open the relay port on your VPS:

```bash
# UFW (Ubuntu/Debian)
sudo ufw allow 19000/tcp

# firewalld (RHEL/CentOS)
sudo firewall-cmd --permanent --add-port=19000/tcp
sudo firewall-cmd --reload

# iptables
sudo iptables -A INPUT -p tcp --dport 19000 -j ACCEPT
```

### 4.5 Docker

A minimal Dockerfile for the relay:

```dockerfile
FROM python:3.12-slim
COPY relay_server.py /app/relay_server.py
WORKDIR /app
EXPOSE 19000
CMD ["python3", "relay_server.py", "--port", "19000"]
```

```bash
docker build -t chess-relay .
docker run -d -p 19000:19000 --name chess-relay chess-relay
```


## 5. Chess Server Configuration

The chess server (`chess.py`) connects to the relay as a client in the TCP
sense, using the `server` role in the relay protocol. Configuration is set in
`config.json`:

### 5.1 Config Keys

| Key                  | Type   | Default | Description                                        |
|----------------------|--------|---------|----------------------------------------------------|
| `relay_server_url`   | string | `""`    | Hostname or IP of the relay server. Empty = disabled. |
| `relay_server_port`  | int    | `19000` | TCP port of the relay server.                      |
| `server_secret`      | string | `""`    | Secret used to derive deterministic session IDs. Auto-generated (64 hex chars) if empty when relay is enabled. |

### 5.2 Example config.json

```json
{
    "relay_server_url": "relay.example.com",
    "relay_server_port": 19000,
    "server_secret": ""
}
```

When the server starts with `relay_server_url` set, it will:

1. Call `ensure_server_secret()` to generate a `server_secret` if one does not
   exist (64-character hex string written back to `config.json`).
2. Derive a deterministic session ID for each engine using
   `derive_session_id(server_secret, engine_name)`.
3. In single-port mode, derive one shared session for `_server_multiplex`.
4. Start a `relay_listener` coroutine per engine (or one for multiplexed mode)
   that connects to the relay, registers, waits for clients, and handles UCI.

### 5.3 Default Relay Server

The setup wizard uses a default relay at `spacetosurf.com:19000`. This can be
overridden during setup or by editing `config.json` directly.

### 5.4 Keepalive

The chess server implements a keepalive timeout of 300 seconds (5 minutes). If
no client connects within this window, the server disconnects from the relay and
re-registers. This prevents NAT/firewall devices from silently dropping the idle
TCP connection (typically after 30-60 minutes).

### 5.5 Reconnection on Error

If the relay connection fails or a client disconnects, the server automatically
reconnects after a 10-second delay. This loop continues indefinitely until the
server is shut down.


## 6. Client Configuration (DroidFish)

DroidFish connects to the relay as a client using the `client` role. Relay
parameters are stored in lines 9-11 of the 14-line NETE configuration file:

| NETE Line | Field            | Example                    |
|-----------|------------------|----------------------------|
| Line 9    | Relay host       | `relay.example.com`        |
| Line 10   | Relay port       | `19000`                    |
| Line 11   | Relay session ID | `a1b2c3d4e5f6a1b2c3d4e5f6` |

### 6.1 Connection Strategy

DroidFish uses a multi-strategy connection approach. When relay parameters are
configured, the relay is attempted as step 3 in the sequence:

1. **mDNS discovery** (1.5s timeout) -- local network auto-discovery
2. **LAN direct** (2s timeout) -- connect to configured host:port
3. **UPnP external** (5s timeout) -- connect via port-forwarded address
4. **Relay** (10s timeout) -- connect via relay server
5. **Retry** -- if relay was not available, retry LAN direct

The relay timeout (`RELAY_TIMEOUT_MS`) is 10 seconds.

### 6.2 How the Client Connects

1. Opens a plain TCP socket to `relayHost:relayPort`.
2. Sends `SESSION <sessionId> client\n`.
3. Reads the response byte-by-byte (to avoid buffering past the relay handshake
   into UCI data).
4. If `CONNECTED\n` is received, the socket is returned as the active connection.
5. If `ERROR ...` is received, an IOException is thrown.
6. After connection, UCI protocol proceeds normally over the relay socket.

### 6.3 Importing Relay Configuration

Relay parameters are populated automatically when importing a `.chessuci`
connection file or scanning a QR code. Both formats include relay endpoint
information when the server has relay configured:

```json
{
    "relay": {
        "host": "relay.example.com",
        "port": 19000
    },
    "engines": [
        {
            "name": "Stockfish 18",
            "relay_session": "a1b2c3d4e5f6a1b2c3d4e5f6"
        }
    ]
}
```


## 7. Session Management

### 7.1 Deterministic Session IDs

Session IDs are derived deterministically from the server secret and engine name
using HMAC-SHA256:

```python
session_id = HMAC-SHA256(server_secret, engine_name).hexdigest()[:24]
```

This produces a 24-character hex string (96 bits). The same inputs always
produce the same output, which means:

- Session IDs survive server restarts (the secret is persisted in `config.json`).
- Clients can reconnect without re-pairing (the session ID is stable).
- Session IDs are unpredictable without knowing the server secret.

For single-port mode, the engine name `_server_multiplex` is used to derive a
single shared session ID for all engines.

### 7.2 Server Reconnection

If a chess server reconnects with the same session ID (e.g., after a restart),
the relay handles it gracefully:

1. The old server connection is closed.
2. Any paired client connection is also closed.
3. The old handler's `paired_event` is set so it exits cleanly.
4. The new server takes over the session slot and receives `REGISTERED`.
5. Reconnection bypasses the max-sessions limit (it replaces, not adds).

This is critical for persistent/deterministic session IDs: the relay must not
reject a legitimate server restart as a duplicate.

### 7.3 Stale Session Cleanup

A background task runs every 5 minutes and removes sessions older than 3600
seconds (1 hour). Stale cleanup:

- Closes both server and client writers if they are still open.
- Removes the session from the session store.
- Logs the cleanup event.

This prevents abandoned sessions from accumulating if a server disconnects
without the relay detecting the TCP close (e.g., network outage).

### 7.4 Session Lifecycle

```
 register         client pairs        disconnect
    |                  |                   |
    v                  v                   v
 REGISTERED ──► WAITING ──► PAIRED ──► RELAY ──► CLEANUP
                  │                              ▲
                  │  (keepalive timeout: 5min)    │
                  └──── reconnect ───────────────►│
                                                  │
                  (stale timeout: 1 hour) ────────┘
```


## 8. Security Considerations

### 8.1 Session ID as Authentication

The session ID serves as a shared secret between the chess server and the
DroidFish client. Anyone who knows the session ID can connect as a client and
interact with the engine. Therefore:

- Keep `server_secret` confidential. It is stored in `config.json` on the
  server machine. Do not commit it to version control.
- The 24-character hex session ID provides 96 bits of entropy (derived from the
  HMAC), making brute-force guessing infeasible.
- Distribute session IDs only through trusted channels (QR code, `.chessuci`
  file, or direct configuration).

### 8.2 No Encryption on the Relay Link

The relay itself operates over plain TCP. Data flowing through the relay
(including UCI commands and engine output) is **not encrypted** at the relay
transport layer. The relay can observe all traffic.

Mitigations:

- Deploy the relay on a trusted VPS that you control.
- UCI protocol data is not highly sensitive (chess positions and moves), but
  authentication tokens in the UCI stream are visible to the relay.
- The chess server bypasses IP trust checks for relay connections
  (`enable_trusted_sources` is set to `False`) since the peer address is the
  relay, not the actual client. The session ID itself authenticates the link.

### 8.3 Denial of Service

- The `--max-sessions` limit (default 100) prevents session exhaustion.
- The 10-second protocol timeout on initial connection prevents slowloris
  attacks.
- Stale session cleanup prevents abandoned sessions from accumulating.

### 8.4 Relay Server Trust

The relay operator can:

- See all UCI traffic (positions, moves, engine analysis).
- Inject or modify data in the stream (man-in-the-middle).
- Deny service by closing connections or refusing registrations.

Only use relay servers that you trust or operate yourself.


## 9. Troubleshooting

### 9.1 Server Cannot Register

**Symptom:** Chess server logs `Relay: Error for <engine>: ...`

| Cause                          | Solution                                               |
|--------------------------------|--------------------------------------------------------|
| Relay server not running       | Start `relay_server.py` on the VPS                     |
| Wrong host/port in config      | Verify `relay_server_url` and `relay_server_port`      |
| Firewall blocking port 19000   | Open port on VPS firewall (see section 4.4)            |
| DNS resolution failure         | Use IP address instead of hostname, or fix DNS         |
| `ERROR max sessions reached`   | Increase `--max-sessions` on the relay or wait for cleanup |

### 9.2 Client Cannot Connect

**Symptom:** DroidFish shows "Relay(...): connection failed" in the connection
strategy log.

| Cause                          | Solution                                               |
|--------------------------------|--------------------------------------------------------|
| `ERROR unknown session`        | Server has not registered yet; wait and retry          |
| Wrong session ID in NETE file  | Re-import the `.chessuci` file or re-scan the QR code  |
| Relay unreachable from client  | Check client network; try pinging the relay host       |
| 10s timeout exceeded           | Relay or server may be overloaded; try again later     |

### 9.3 Connection Drops During Play

**Symptom:** Game disconnects after some time, then reconnects.

| Cause                          | Solution                                               |
|--------------------------------|--------------------------------------------------------|
| NAT/firewall timeout on idle   | The server keepalive (5 min) should handle this. If drops occur sooner, check the NAT device settings. |
| Relay stale cleanup (1 hour)   | Sessions active for more than 1 hour are cleaned up. This is by design -- reconnection is automatic. |
| Network instability            | The chess server auto-reconnects after 10s on error    |

### 9.4 Session ID Mismatch After Server Restart

**Symptom:** Client gets `ERROR unknown session` after server restarts.

This should not happen if `server_secret` is configured, because session IDs are
deterministic. Check:

1. `server_secret` is present in `config.json` (at least 32 characters).
2. The engine name has not changed.
3. The server successfully called `ensure_server_secret()` at startup (check
   logs for "Generated new server_secret" -- if this appears, the secret was
   regenerated, which changes all session IDs).

### 9.5 Verifying the Relay

Test the relay manually using `nc` or `telnet`:

```bash
# Terminal 1: simulate the chess server
echo "SESSION test123 server" | nc relay.example.com 19000
# Should print: REGISTERED

# Terminal 2: simulate the DroidFish client
echo "SESSION test123 client" | nc relay.example.com 19000
# Should print: CONNECTED
# Terminal 1 should then print: PAIRED
```

### 9.6 Checking Relay Logs

The relay logs to stdout with timestamps. Key log lines:

```
2025-01-15 10:00:01 [INFO] Relay server listening on 0.0.0.0:19000 (max 100 sessions)
2025-01-15 10:00:10 [INFO] Session abc123def456: server registered
2025-01-15 10:00:15 [INFO] Session abc123def456: client connected
2025-01-15 10:00:15 [INFO] Session abc123def456: paired, starting data relay
2025-01-15 10:30:00 [INFO] Session abc123def456: relay ended
2025-01-15 11:00:01 [INFO] Session oldxyz789: cleaned up (stale)
```

If sessions are being superseded by reconnections, you will see:

```
2025-01-15 10:05:00 [INFO] Session abc123def456: server reconnected (replaced old)
```
