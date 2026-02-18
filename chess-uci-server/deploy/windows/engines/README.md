# Windows Engine Executables

Place your UCI engine `.exe` files here. Common engines:

| Engine | Download |
|--------|----------|
| Stockfish | [stockfishchess.org](https://stockfishchess.org/download/) |
| Leela Chess Zero (lc0) | [lczero.org](https://lczero.org/) |
| Dragon | [komodochess.com](https://komodochess.com/) |
| Berserk | [GitHub](https://github.com/jhonnold/berserk) |

After placing engines here, update `config.json` with the correct paths.
Use double backslashes in JSON:

```json
{
  "engines": {
    "Stockfish": {
      "path": "deploy\\windows\\engines\\stockfish.exe",
      "port": 9998
    }
  }
}
```

Or use absolute paths:

```json
{
  "engines": {
    "Stockfish": {
      "path": "C:\\chess-uci-server\\deploy\\windows\\engines\\stockfish-windows-x86-64-avx2.exe",
      "port": 9998
    }
  }
}
```

Note: Windows Defender or SmartScreen may block downloaded executables.
Right-click the `.exe` → Properties → check "Unblock" if needed.
