# Protocol Reference

The Chess UCI Server communicates over TCP (optionally TLS-encrypted). The protocol layers are:

1. **TLS handshake** (if enabled)
2. **Authentication** (if configured)
3. **Engine selection** (single-port mode only)
4. **UCI protocol** (standard chess engine communication)

All messages are newline-terminated (`\n`).

## Connection Flow

```
Client                          Server
  │                               │
  ├──── TCP connect ─────────────►│
  │                               │
  │  [TLS handshake if enabled]   │
  │                               │
  │◄──── AUTH_REQUIRED ───────────┤  (if auth configured)
  ├──── AUTH <token> ────────────►│
  │◄──── AUTH_OK ─────────────────┤
  │                               │
  │  [Engine selection if single-port]
  │                               │
  ├──── uci ─────────────────────►│  (standard UCI begins)
  │◄──── id name Stockfish ───────┤
  │◄──── uciok ───────────────────┤
  │                               │
```

## Authentication

### Token Authentication

```
Server → Client: AUTH_REQUIRED\n
Client → Server: AUTH <token>\n
Server → Client: AUTH_OK\n        (success)
                  AUTH_FAIL\n      (failure, connection closed)
```

### PSK Authentication

```
Server → Client: AUTH_REQUIRED psk\n
Client → Server: PSK_AUTH <key>\n
Server → Client: AUTH_OK\n
                  AUTH_FAIL\n
```

### Multi-Method Authentication

When both token and PSK are configured:

```
Server → Client: AUTH_REQUIRED token,psk\n
Client → Server: AUTH <token>\n       (token method)
         or
Client → Server: PSK_AUTH <key>\n     (PSK method)
Server → Client: AUTH_OK\n
```

The `AUTH_REQUIRED` header lists available methods. Clients choose one.

### No Authentication

If `auth_method` is `"none"` or no token/PSK is configured, the server skips authentication and proceeds directly to UCI or engine selection.

## Engine Selection (Single-Port Mode)

When `enable_single_port` is `true`, all engines are multiplexed on one port. After authentication, clients can list and select engines.

### Explicit Selection

```
Client → Server: ENGINE_LIST\n
Server → Client: ENGINE Stockfish\n
                  ENGINE Dragon\n
                  ENGINES_END\n
Client → Server: SELECT_ENGINE Stockfish\n
Server → Client: ENGINE_SELECTED\n
```

If the engine name is unknown:

```
Server → Client: ENGINE_ERROR unknown engine\n
(connection closed)
```

### Implicit Selection (Backward Compatible)

If the client sends any UCI command (e.g., `uci`) instead of `ENGINE_LIST`, the server uses the `default_engine` (or the first engine in the registry).

## UCI Protocol

After connection and optional auth/selection, standard UCI protocol is used:

### Initialization

```
Client → Server: uci
Server → Client: id name Stockfish 16
                  id author T. Romstad, M. Costalba, J. Kiiski, G. Linscott
                  option name Hash type spin default 16 min 1 max 33554432
                  ...
                  uciok

Client → Server: isready
Server → Client: readyok
```

### Analysis

```
Client → Server: position startpos moves e2e4 e7e5
Client → Server: go depth 20
Server → Client: info depth 1 score cp 30 pv e2e4
                  info depth 2 score cp 25 pv e2e4 e7e5
                  ...
                  bestmove d2d4
```

### Common Commands

| Direction | Command | Description |
|-----------|---------|-------------|
| GUI → Engine | `uci` | Initialize UCI mode |
| GUI → Engine | `isready` | Check if engine is ready |
| GUI → Engine | `position startpos moves ...` | Set board position |
| GUI → Engine | `go depth N` | Search to depth N |
| GUI → Engine | `go movetime N` | Search for N milliseconds |
| GUI → Engine | `stop` | Stop current search |
| GUI → Engine | `quit` | Disconnect |
| Engine → GUI | `uciok` | UCI initialization complete |
| Engine → GUI | `readyok` | Engine is ready |
| Engine → GUI | `bestmove e2e4` | Best move found |
| Engine → GUI | `info ...` | Search information |

## mDNS Discovery

The server advertises via mDNS using service type `_chess-uci._tcp.local.`.

### Per-Engine Mode

One service per engine:

```
Service: Stockfish._chess-uci._tcp.local.
Port: 9998
TXT: engine=Stockfish, tls=false, auth=false
```

### Single-Port Mode

One service for all engines:

```
Service: Chess-UCI-Server._chess-uci._tcp.local.
Port: 9998
TXT: engines=Stockfish,Dragon, tls=false, auth=false, single_port=true
```

## Relay Protocol

For NAT traversal, the server connects to a relay and registers sessions. See [relay.md](relay.md) for full relay server documentation, deployment, and configuration.

### Server Registration

```
Server → Relay: SESSION <session_id> server\n
Relay → Server: REGISTERED\n
```

### Client Connection

```
Client → Relay: SESSION <session_id> client\n
Relay → Client: PAIRED\n
```

After pairing, the relay proxies all traffic between server and client.

### Session IDs

When `server_secret` is configured, session IDs are deterministic:

```
session_id = HMAC-SHA256(server_secret, engine_name)[:24]
```

This produces a stable 24-character hex string for each engine, allowing clients to reconnect to the same session.

## Connection File (.chessuci)

The server generates a `.chessuci` JSON file for zero-config client setup:

```json
{
  "version": 1,
  "type": "chess-uci-server",
  "created": "2025-01-15T12:00:00Z",
  "server_name": "Chess Server (192.168.1.100)",
  "engines": [
    {
      "name": "Stockfish",
      "port": 9998,
      "mdns_name": "Stockfish",
      "endpoints": {
        "lan": { "host": "192.168.1.100", "port": 9998 },
        "upnp": { "host": "203.0.113.45", "port": 9998 },
        "relay": {
          "host": "relay.example.com",
          "port": 19000,
          "session_id": "a1b2c3d4e5f6a1b2c3d4e5f6"
        }
      }
    }
  ],
  "security": {
    "tls": false,
    "auth_method": "token",
    "token": "abc123",
    "fingerprint": ""
  }
}
```

In single-port mode, additional top-level fields are included:

```json
{
  "single_port": true,
  "port": 9998,
  "available_engines": ["Stockfish", "Dragon"]
}
```

DroidFish can import this file for automatic server configuration.
