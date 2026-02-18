# Chess UCI Server

A Python server that lets you play and analyze chess remotely using UCI engines like Stockfish, Dragon, and others. Connects to DroidFish and other UCI-compatible clients over your network.

## Quick Deploy

### Linux

```bash
./deploy/linux/install.sh                      # 1. Install dependencies
cp /path/to/stockfish deploy/linux/engines/     # 2. Add engine
chmod +x deploy/linux/engines/stockfish
python3 chess.py --pair                         # 3. Start + show QR code
```

### Windows

```cmd
deploy\windows\install.bat                                          &REM 1. Install
copy C:\Downloads\stockfish.exe deploy\windows\engines\             &REM 2. Add engine
python chess.py --pair                                              &REM 3. Start + show QR
```

### Connect

Scan the QR code from DroidFish: **Network Engines > Scan QR** — done.

**What happens automatically:**
- Engines in the `engines/` folder are auto-discovered (no config editing)
- All engines multiplexed on a single port (9998)
- mDNS advertises the server on your local network
- UPnP maps the port through your router (no port forwarding needed)
- Any connecting client is auto-trusted (no IP whitelisting needed)
- QR code displayed for instant mobile pairing

## Features

- **Auto-discovery** — drop engines in a folder, they're found automatically
- **Single-port mode** — all engines on one port, no multi-port setup
- **mDNS discovery** — clients find the server automatically on LAN
- **UPnP port mapping** — router configured automatically
- **QR code pairing** — scan to connect from DroidFish
- **Connection files** — `.chessuci` files for zero-config client setup
- **Relay server** — NAT traversal for remote access without port forwarding
- **TLS encryption** — optional secure connections
- **Authentication** — token-based and PSK authentication
- **Session management** — keep engines alive across reconnections
- **Output throttling** — bandwidth-friendly UCI info rate limiting
- **Firewall integration** — automatic Windows Firewall rule management

## CLI Commands

```bash
python3 chess.py --pair             # Start server + display QR code
python3 chess.py --pair-only        # Display QR code and exit
python3 chess.py --setup            # Interactive setup wizard
python3 chess.py --connection-file  # Generate .chessuci file and exit
python3 chess.py --add-engine PATH  # Add an engine to config
python3 chess.py --stop             # Stop a running server
python3 chess.py --help             # Show all options
```

## Testing

```bash
python3 -m pytest tests/ -v
```

## Documentation

| Guide | Description |
|-------|-------------|
| [deploy/linux/README.md](deploy/linux/README.md) | Linux: install, Docker, systemd |
| [deploy/windows/README.md](deploy/windows/README.md) | Windows: install, ChessServer.exe, NSSM |
| [docs/configuration.md](docs/configuration.md) | All config keys with types and defaults |
| [docs/protocol.md](docs/protocol.md) | TCP, auth, engine selection, mDNS, relay |
| [docs/relay.md](docs/relay.md) | Relay server for NAT traversal |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common issues and fixes |

## Project Structure

```
chess-uci-server/
├── chess.py                 # Main server
├── relay_server.py          # Relay server for NAT traversal
├── config.json              # Your configuration (auto-generated)
├── requirements.txt         # Python dependencies
├── deploy/
│   ├── linux/
│   │   ├── engines/         # Place Linux engine binaries here
│   │   ├── install.sh       # Installation script
│   │   ├── example_config.json  # Auto-deploy config template
│   │   ├── Dockerfile       # Docker image
│   │   └── ...
│   └── windows/
│       ├── engines/         # Place Windows engine .exe files here
│       ├── install.bat      # Installation script
│       ├── example_config.json  # Auto-deploy config template
│       └── ...
├── docs/                    # Configuration, protocol, troubleshooting
└── tests/                   # test_chess.py, test_relay.py
```

## Advanced Configuration

The default config enables all automated features. Edit `config.json` only when you need to:

- **Add TLS/authentication** — see platform README "Advanced" sections
- **Restrict access by IP** — disable auto-trust, add trusted_sources
- **Use separate ports per engine** — disable single-port mode
- **Configure relay server** — for remote access without UPnP
- **Manage firewall rules** — when UPnP is unavailable

See [docs/configuration.md](docs/configuration.md) for the complete reference.
