# Chess UCI Server - Linux Deployment

## Quick Deploy (3 steps)

```bash
# 1. Install
chmod +x install.sh
./install.sh

# 2. Place engine(s) in the engines folder
cp /path/to/stockfish engines/
chmod +x engines/stockfish

# 3. Start with QR pairing
python3 chess.py --pair
```

Scan the QR code from DroidFish (Network Engines > Scan QR) and you're playing.

**What happens automatically:**
- Engines in `engines/` are auto-discovered
- All engines are multiplexed on a single port (9998)
- mDNS advertises the server on your local network
- UPnP maps the port through your router
- Any connecting client is auto-trusted
- A QR code is displayed for instant DroidFish pairing

No config editing, port forwarding, firewall rules, or IP whitelisting required.

## Alternative: Interactive Setup Wizard

```bash
python3 chess.py --setup
```

The wizard walks you through engine selection, security, and connectivity options.

## Alternative: Docker

```bash
# Build the image
docker build -t chess-uci-server .

# Or with docker-compose
docker-compose up -d

# With relay server for NAT traversal
docker-compose --profile relay up -d
```

The Docker image includes Stockfish and all Python dependencies.

## Engine Binaries

Place UCI engine executables in `engines/` — they are auto-discovered on startup.

```bash
# System package
sudo apt install stockfish

# Or download and place manually
wget https://stockfishchess.org/files/stockfish-linux-x86-64-avx2.tar.gz
tar xzf stockfish-*.tar.gz -C engines/
chmod +x engines/stockfish
```

See `engines/README.md` for download links for popular engines.

## Other Commands

```bash
./start-server.sh                 # Start the server
./start-server.sh --pair          # Start with QR pairing
./start-server.sh --background    # Start in background (detached)
./stop-server.sh                  # Stop a running server
./uninstall.sh                    # Remove server, service, and dependencies

python3 chess.py --pair           # Start server + display QR code
python3 chess.py --pair-only      # Display QR code and exit
python3 chess.py --connection-file # Generate .chessuci file and exit
python3 chess.py --stop           # Stop a running server
python3 chess.py --help           # Show all CLI options
```

---

## Advanced Configuration

The sections below are optional. The default config enables all automated features. Edit `config.json` only if you need to customize behavior.

See `docs/configuration.md` for the complete reference of all config keys.

### systemd Service (auto-start on boot)

The installer offers this optionally. To set up manually:

1. Edit `chess-uci-server.service` with your paths and user
2. Install:
   ```bash
   sudo cp chess-uci-server.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now chess-uci-server
   ```
3. Manage:
   ```bash
   sudo systemctl status chess-uci-server
   journalctl -u chess-uci-server -f
   ```

### Firewall Rules

Only needed if your network blocks traffic or you've disabled UPnP:

```bash
# UFW
sudo ufw allow 9998/tcp

# iptables
sudo iptables -A INPUT -p tcp --dport 9998 -j ACCEPT
```

### TLS Encryption

```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

Add to `config.json`:
```json
{
  "enable_tls": true,
  "tls_cert_path": "cert.pem",
  "tls_key_path": "key.pem"
}
```

### Authentication

Add to `config.json`:
```json
{
  "auth_method": "token",
  "auth_token": "your-secret-token"
}
```

### IP Restrictions

To replace auto-trust with explicit IP control:
```json
{
  "enable_auto_trust": false,
  "enable_trusted_sources": true,
  "trusted_sources": ["192.168.1.50"],
  "trusted_subnets": ["192.168.1.0/24"]
}
```

### Relay Server (Remote Access Without Port Forwarding)

For accessing the server from outside your LAN without UPnP:
```json
{
  "relay_server_url": "your-vps.example.com",
  "relay_server_port": 19000,
  "server_secret": "a-random-secret-string"
}
```

### Multiple Ports (One Per Engine)

To use separate ports instead of single-port mode:
```json
{
  "enable_single_port": false,
  "engines": {
    "Stockfish": { "path": "engines/stockfish", "port": 9998 },
    "Dragon": { "path": "engines/dragon", "port": 9999 }
  }
}
```
