# Configuration Reference

All settings are defined in `config.json` in the chess-uci-server root directory. The install scripts generate this file automatically from the example config.

## Quick Deploy Defaults

The example configs enable these automated features out of the box:

| Feature | Config Key | Default | What It Does |
|---------|-----------|---------|--------------|
| Single-port mode | `enable_single_port` | `true` | All engines on one port — no multi-port setup |
| Engine auto-discovery | `engine_directory` | `deploy/<platform>/engines` | Drop executables in folder, they're found automatically |
| mDNS advertisement | `enable_mdns` | `true` | Clients discover the server on LAN automatically |
| UPnP port mapping | `enable_upnp` | `true` | Router port forwarding configured automatically |
| Auto-trust | `enable_auto_trust` | `true` | Any connecting client is trusted (no IP whitelisting) |
| No authentication | `auth_method` | `"none"` | No token/password needed to connect |

With these defaults, the deployment flow is: install, drop engine, run `python3 chess.py --pair`, scan QR from DroidFish.

To tighten security for production use, see [Advanced: Security](#security) below.

---

## All Configuration Keys

### Network

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `host` | string | **required** | Bind address. Use `"0.0.0.0"` for all interfaces. |
| `base_port` | int | `9998` | Preferred port for single-port mode. If in use, the server automatically selects the next available port. |
| `max_connections` | int | **required** | Maximum concurrent client connections. |
| `enable_upnp` | bool | `true` | Automatically map port on the router via UPnP. |
| `upnp_lease_duration` | int | `3600` | UPnP lease renewal interval (seconds). |

### Engines

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `engines` | object | `{}` | Explicit engine definitions (see below). Can be empty if using `engine_directory`. |
| `engine_directory` | string | `""` | Directory to scan for engine executables. All executables found are added automatically. |
| `custom_variables` | object | `{}` | UCI options sent to all engines (e.g., `{"Hash": "256"}`). |
| `enable_single_port` | bool | `false` | Multiplex all engines on one port. |
| `default_engine` | string | `""` | Default engine in single-port mode (first engine if empty). |

#### Engine Entry (manual configuration)

Each engine is a key-value pair in `engines`. Only needed if you want explicit control over paths and ports instead of auto-discovery:

```json
"Stockfish": {
  "path": "/usr/games/stockfish",
  "port": 9998,
  "custom_variables": {
    "Threads": "4",
    "Hash": "512"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | Path to the engine executable. |
| `port` | int | yes | TCP port for this engine (ignored in single-port mode). |
| `custom_variables` | object | no | UCI options specific to this engine. Overrides global `custom_variables`. |

#### Auto-Discovery vs Manual Configuration

- **Auto-discovery** (`engine_directory`): The server scans the directory for executable files and assigns sequential ports. Engine names come from filenames (without extension). Best for quick deployment.
- **Manual** (`engines`): You specify exact paths, ports, and per-engine options. Best when you need specific port assignments or custom UCI options per engine.
- **Both**: You can use both. Auto-discovered engines are added alongside manually configured ones (without overriding them).

### Discovery & Connectivity

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enable_mdns` | bool | `false` | Advertise via mDNS (`_chess-uci._tcp`). Clients on the same LAN discover the server automatically. |
| `relay_server_url` | string | `""` | Relay server hostname for NAT traversal (connect from outside your LAN without port forwarding). |
| `relay_server_port` | int | `19000` | Relay server port. |
| `server_secret` | string | `""` | Secret for deterministic relay session IDs (HMAC-SHA256). |
| `connection_file_path` | string | `"connection.chessuci"` | Output path for `.chessuci` connection file. |

### Security

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `auth_method` | string | `"token"` | Authentication method: `"token"`, `"psk"`, or `"none"`. |
| `auth_token` | string | `""` | Token for token-based authentication. Empty = no auth. |
| `psk_key` | string | `""` | Pre-shared key for PSK authentication. |
| `enable_trusted_sources` | bool | `true` | Restrict connections to trusted IPs/subnets. |
| `enable_auto_trust` | bool | `false` | Auto-trust any IP that connects. Convenient for setup, disable for production. |
| `trusted_sources` | list | **required** | Allowed IP addresses (when `enable_trusted_sources` is true). |
| `trusted_subnets` | list | **required** | Allowed subnets in CIDR notation. |

#### Security Profiles

**Open (quick deploy default):**
```json
{
  "auth_method": "none",
  "enable_trusted_sources": false,
  "enable_auto_trust": true
}
```

**LAN-only (restrict to local network):**
```json
{
  "auth_method": "none",
  "enable_trusted_sources": true,
  "enable_auto_trust": false,
  "trusted_sources": ["127.0.0.1"],
  "trusted_subnets": ["192.168.0.0/16", "10.0.0.0/8"]
}
```

**Production (encrypted + authenticated):**
```json
{
  "auth_method": "token",
  "auth_token": "your-secret-token",
  "enable_tls": true,
  "tls_cert_path": "cert.pem",
  "tls_key_path": "key.pem",
  "enable_trusted_sources": true,
  "enable_auto_trust": false,
  "trusted_sources": ["192.168.1.50"],
  "trusted_subnets": ["192.168.1.0/24"]
}
```

### TLS

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enable_tls` | bool | `false` | Enable TLS encryption. |
| `tls_cert_path` | string | `""` | Path to TLS certificate file. |
| `tls_key_path` | string | `""` | Path to TLS private key file. |

### Firewall

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enable_firewall_rules` | bool | `false` | Enable automatic firewall rule management (Windows). |
| `enable_firewall_subnet_blocking` | bool | `false` | Block untrusted subnets via firewall. |
| `enable_firewall_ip_blocking` | bool | `false` | Block individual untrusted IPs via firewall. |
| `max_connection_attempts` | int | `5` | Max connection attempts before blocking an IP. |
| `connection_attempt_period` | int | `3600` | Time window for counting attempts (seconds). |
| `enable_subnet_connection_attempt_blocking` | bool | `false` | Enable subnet-level attempt blocking. |
| `max_connection_attempts_from_untrusted_subnet` | int | `10` | Max attempts from untrusted subnet. |

### Logging

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `base_log_dir` | string | `""` | Directory for log files. Empty = current directory. |
| `enable_server_log` | bool | `true` | Write `server.log` with server events. |
| `enable_uci_log` | bool | `false` | Write per-engine UCI communication logs. |
| `detailed_log_verbosity` | bool | `false` | Include UCI commands in logs. |
| `display_uci_communication` | bool | `false` | Print UCI traffic to console. |
| `Log_untrusted_connection_attempts` | bool | `true` | Log untrusted connection details. |

### Timeouts

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `inactivity_timeout` | int | `900` | Disconnect idle clients after N seconds. |
| `heartbeat_time` | int | `300` | Send heartbeat every N seconds. |
| `watchdog_timer_interval` | int | `300` | Watchdog check interval (seconds). |
| `session_keepalive_timeout` | int | `0` | Keep engine process alive after disconnect (seconds). 0 = disabled. |
| `info_throttle_ms` | int | `0` | Throttle UCI info output (milliseconds). 0 = disabled. |

### Server Management

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `pid_file` | string | `"chess-uci-server.pid"` | PID file path for `--stop` command. |

---

## Example Configurations

### Quick Deploy (auto-everything)

This is what the install scripts generate. No manual engine paths needed — engines are auto-discovered:

```json
{
  "host": "0.0.0.0",
  "base_port": 9998,
  "max_connections": 10,
  "enable_single_port": true,
  "enable_mdns": true,
  "enable_upnp": true,
  "enable_auto_trust": true,
  "enable_trusted_sources": false,
  "auth_method": "none",
  "engine_directory": "deploy/linux/engines",
  "engines": {},
  "trusted_sources": [],
  "trusted_subnets": []
}
```

### Secure Remote Access

```json
{
  "host": "0.0.0.0",
  "base_port": 9998,
  "max_connections": 10,
  "enable_single_port": true,
  "enable_mdns": true,
  "enable_upnp": true,
  "enable_tls": true,
  "tls_cert_path": "cert.pem",
  "tls_key_path": "key.pem",
  "auth_method": "token",
  "auth_token": "your-secret-token",
  "enable_auto_trust": false,
  "enable_trusted_sources": true,
  "trusted_sources": ["127.0.0.1"],
  "trusted_subnets": ["192.168.1.0/24"],
  "engine_directory": "deploy/linux/engines",
  "engines": {}
}
```

### Relay Server (Access From Anywhere)

```json
{
  "host": "0.0.0.0",
  "base_port": 9998,
  "max_connections": 10,
  "enable_single_port": true,
  "enable_mdns": true,
  "enable_upnp": true,
  "relay_server_url": "relay.example.com",
  "relay_server_port": 19000,
  "server_secret": "a-random-secret-string",
  "auth_method": "token",
  "auth_token": "your-secret-token",
  "engine_directory": "deploy/linux/engines",
  "engines": {},
  "trusted_sources": [],
  "trusted_subnets": []
}
```

### Multi-Port with Manual Engine Config

```json
{
  "host": "0.0.0.0",
  "max_connections": 10,
  "enable_single_port": false,
  "enable_mdns": true,
  "enable_upnp": true,
  "enable_auto_trust": true,
  "enable_trusted_sources": false,
  "auth_method": "none",
  "engines": {
    "Stockfish": {
      "path": "/usr/games/stockfish",
      "port": 9998,
      "custom_variables": { "Hash": "1024", "Threads": "4" }
    },
    "Dragon": {
      "path": "/usr/local/bin/dragon",
      "port": 9999
    }
  },
  "trusted_sources": [],
  "trusted_subnets": []
}
```
