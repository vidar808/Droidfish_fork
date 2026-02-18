# Linux Engine Binaries

Place your UCI engine executables here. Common engines:

| Engine | Download |
|--------|----------|
| Stockfish | `sudo apt install stockfish` or [stockfishchess.org](https://stockfishchess.org/download/) |
| Leela Chess Zero (lc0) | [lczero.org](https://lczero.org/) |
| Dragon | [komodo chess](https://komodochess.com/) |
| Berserk | [GitHub](https://github.com/jhonnold/berserk) |

After placing engines here, update `config.json` with the correct paths:

```json
{
  "engines": {
    "Stockfish": {
      "path": "deploy/linux/engines/stockfish",
      "port": 9998
    }
  }
}
```

Or use absolute paths if the server runs from a different working directory:

```json
{
  "engines": {
    "Stockfish": {
      "path": "/opt/chess-uci-server/deploy/linux/engines/stockfish",
      "port": 9998
    }
  }
}
```

Make sure engines are executable:

```bash
chmod +x stockfish lc0 dragon
```
