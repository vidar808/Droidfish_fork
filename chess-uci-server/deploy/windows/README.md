# Chess UCI Server - Windows Deployment

## Quick Deploy (3 steps)

```cmd
REM 1. Install
install.bat

REM 2. Place engine(s) in the engines folder
copy C:\Downloads\stockfish-windows-x86-64-avx2.exe engines\

REM 3. Start with QR pairing
python chess.py --pair
```

Scan the QR code from DroidFish (Network Engines > Scan QR) and you're playing.

**What happens automatically:**
- Engines in `engines\` are auto-discovered
- All engines are multiplexed on a single port (9998)
- mDNS advertises the server on your local network
- UPnP maps the port through your router
- Any connecting client is auto-trusted
- A QR code is displayed for instant DroidFish pairing

No config editing, port forwarding, firewall rules, or IP whitelisting required.

## Alternative: Standalone Executable

`ChessServer.exe` is a self-contained executable that includes Python. No installation needed.

1. Place `ChessServer.exe` and `config.json` in the same directory
2. Place engine `.exe` files in an `engines\` folder next to it
3. Double-click `ChessServer.exe` or run `ChessServer.exe --pair`

## Alternative: Interactive Setup Wizard

```cmd
python chess.py --setup
```

The wizard walks you through engine selection, security, and connectivity options.

## Engine Executables

Place UCI engine `.exe` files in `engines\` — they are auto-discovered on startup.

Download Stockfish from [stockfishchess.org](https://stockfishchess.org/download/).

See `engines\README.md` for download links for popular engines.

**Note:** Windows Defender or SmartScreen may block downloaded executables. Right-click the `.exe` > Properties > check "Unblock" if needed.

## Other Commands

```cmd
start-server.bat                   Start the server
start-server.bat --pair            Start with QR pairing
stop-server.bat                    Stop a running server
uninstall.bat                      Remove server, service, and dependencies

python chess.py --pair             Start server + display QR code
python chess.py --pair-only        Display QR code and exit
python chess.py --connection-file  Generate .chessuci file and exit
python chess.py --stop             Stop a running server
python chess.py --help             Show all CLI options
```

---

## Advanced Configuration

The sections below are optional. The default config enables all automated features. Edit `config.json` only if you need to customize behavior.

See `docs\configuration.md` for the complete reference of all config keys.

### Windows Firewall

Only needed if UPnP is unavailable or disabled. The server can manage firewall rules automatically:

```json
{
  "enable_firewall_rules": true
}
```

This requires running the server as Administrator.

To manually allow the port (as Administrator):

```cmd
netsh advfirewall firewall add rule name="Chess UCI Server" dir=in action=allow protocol=TCP localport=9998
```

### TLS Encryption

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

### Running as a Windows Service

Use [NSSM](https://nssm.cc/) to run as a background service:

```cmd
nssm install ChessUCIServer python.exe "C:\path\to\chess.py"
nssm set ChessUCIServer AppDirectory "C:\path\to\deploy\windows"
nssm start ChessUCIServer
```

### Multiple Ports (One Per Engine)

To use separate ports instead of single-port mode:
```json
{
  "enable_single_port": false,
  "engines": {
    "Stockfish": { "path": "engines\\stockfish.exe", "port": 9998 },
    "Dragon": { "path": "engines\\dragon.exe", "port": 9999 }
  }
}
```
