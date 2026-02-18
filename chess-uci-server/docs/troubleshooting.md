# Troubleshooting

## Quick Deploy Issues

### No engines detected on startup

The server auto-discovers engines in the `engine_directory` (default: `deploy/<platform>/engines/`).

- Verify engine files are in the correct folder
- On Linux, ensure they are executable: `chmod +x deploy/linux/engines/*`
- On Windows, ensure `.exe` files are not blocked by SmartScreen (right-click > Properties > Unblock)
- Check server output for "Auto-discovered engine:" messages

### QR code not displaying (`--pair`)

- The `qrcode` package must be installed: `pip install qrcode`
- Run the install script first, or `pip install -r requirements.txt`

### DroidFish can't find the server (mDNS)

- Ensure `"enable_mdns": true` in config (default in example configs)
- The `zeroconf` package must be installed: `pip install zeroconf`
- Phone and server must be on the **same local network** (same WiFi)
- Some networks (corporate, guest WiFi, hotspots) block mDNS traffic
- Docker containers need `network_mode: host` for mDNS to work
- Alternative: use QR code pairing (`--pair`) which doesn't rely on mDNS for discovery

### UPnP port mapping failed

- Not all routers support UPnP or have it enabled
- Check router settings to enable UPnP/NAT-PMP
- The `miniupnpc` package must be installed: `pip install miniupnpc`
- If UPnP is unavailable, alternatives:
  - Set up manual port forwarding on your router
  - Use relay mode (`relay_server_url`) for NAT traversal
  - Connect via LAN only (mDNS or QR on same network)

### Can't connect from outside the local network

The automated deployment handles LAN connections. For remote access:

1. **UPnP** (automatic if router supports it) — check server logs for "UPnP: Mapped" message
2. **Relay server** — set `relay_server_url` and `relay_server_port` in config, deploy `relay_server.py` on a VPS
3. **Manual port forwarding** — forward port 9998 TCP on your router to the server's LAN IP

## Connection Issues

### "Connection refused"

- Verify the server is running: `python3 chess.py` should show "Listening on ..."
- Check the port matches your client config (default: 9998)
- The server auto-selects an available port if the configured one is occupied. Check server output for "Port XXXX in use, using port YYYY" messages.
- Ensure `host` in `config.json` is `"0.0.0.0"` (not `"127.0.0.1"`) for remote access

### "Connection timed out"

- Server may not be reachable from the client's network
- Check if UPnP mapping succeeded (look for "UPnP: Mapped" in server output)
- Try relay mode for NAT traversal

### Client disconnects immediately

- If authentication is configured, ensure the client sends the correct token/PSK
- Check server logs for `AUTH_FAIL` messages
- The default example configs use `"auth_method": "none"` — if you changed this, update the client too

### "Untrusted source" / connection rejected

With the default quick-deploy config (`enable_auto_trust: true`, `enable_trusted_sources: false`), this shouldn't happen. If you've tightened security:

- Add the client's IP to `trusted_sources` in `config.json`
- Or add the client's subnet to `trusted_subnets`
- Or re-enable `"enable_auto_trust": true`
- Restart the server after config changes

## Engine Issues

### Engine fails to start

- Verify the engine is in `deploy/<platform>/engines/` (or the path in config is correct)
- Check execute permission: `chmod +x deploy/linux/engines/stockfish`
- Test the engine directly: `./deploy/linux/engines/stockfish` should respond to the `uci` command
- On Linux, ensure the binary matches your CPU architecture (x86_64, ARM, etc.)

### Engine responds slowly

- Check `info_throttle_ms` isn't set too high
- Verify engine resource settings (`Threads`, `Hash` in `custom_variables`)
- The `inactivity_timeout` may be too short — increase it in config

### "Engine already in use"

- Another client is connected to the same engine
- Each engine handles one client at a time
- Disconnect the other client, or add a second instance of the engine with a different name

## TLS Issues (Advanced)

### "SSL certificate verify failed"

- Self-signed certificates require the client to accept the fingerprint
- Ensure `tls_cert_path` and `tls_key_path` point to valid files
- Check certificate hasn't expired: `openssl x509 -in cert.pem -noout -dates`

### Generating a self-signed certificate

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=chess-uci-server"
```

## Firewall (Advanced)

Only needed if UPnP is unavailable or disabled.

### Linux (UFW)

```bash
sudo ufw allow 9998/tcp
```

### Linux (iptables)

```bash
sudo iptables -A INPUT -p tcp --dport 9998 -j ACCEPT
```

### Windows

```cmd
REM As Administrator
netsh advfirewall firewall add rule name="Chess UCI Server" dir=in action=allow protocol=TCP localport=9998
```

Or enable automatic management in config: `"enable_firewall_rules": true` (requires Administrator).

## Relay Issues (Advanced)

See [relay.md](relay.md) for full relay server documentation.

### Relay connection failing

- Verify the relay server is running and accessible
- Check `relay_server_url` and `relay_server_port` in config
- The relay server must be reachable from both the server and client

### Session ID mismatch

- If using `server_secret`, ensure it hasn't changed since generating the connection file
- Regenerate the `.chessuci` file: `python3 chess.py --connection-file`

## Logging

### Finding logs

- Logs are in the directory specified by `base_log_dir` (empty = current directory)
- `server.log` — main server events
- Per-engine UCI logs (when `enable_uci_log` is true)

### Enabling verbose logging

```json
{
  "enable_server_log": true,
  "enable_uci_log": true,
  "detailed_log_verbosity": true,
  "display_uci_communication": true
}
```

## Server Management

### Server won't stop with `--stop`

- Check `pid_file` setting matches what was used when starting
- Manually find the process: `ps aux | grep chess.py` (Linux) or `tasklist | findstr python` (Windows)
- Kill manually: `kill <pid>` (Linux) or `taskkill /PID <pid>` (Windows)

### Server crashes on startup

- Validate `config.json` is valid JSON: `python3 -c "import json; json.load(open('config.json'))"`
- Check required keys are present (`host`, `max_connections`, `trusted_sources`, `trusted_subnets`)
- Ensure at least one engine is available (in `engines` or `engine_directory`)

## Permission Issues

### Linux

```bash
# Engine not executable
chmod +x deploy/linux/engines/*

# Port below 1024 requires root (use ports >= 1024 instead)
```

### Windows

- Run as Administrator for firewall rule management
- Ensure engine `.exe` is not blocked by SmartScreen (right-click > Properties > Unblock)
- Antivirus may block engine executables — add exceptions as needed
