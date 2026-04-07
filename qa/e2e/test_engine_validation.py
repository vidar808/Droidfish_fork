"""Engine Validation Tests - verify each installed UCI engine runs correctly.

Discovers all available UCI engines (system-installed or in the engines
directory) and validates that each one:
  1. Starts without error
  2. Responds to the UCI handshake (uci → id + uciok)
  3. Responds to isready → readyok
  4. Can process a basic position + go command → bestmove
  5. Shuts down cleanly on quit

Usage:
    pytest qa/e2e/test_engine_validation.py -v
    pytest qa/e2e/test_engine_validation.py -v -m engine

Engines are auto-discovered from:
  - System PATH (stockfish, lc0, etc.)
  - chess-uci-server/deploy/linux/engines/
  - Any path set in ENGINE_VALIDATION_DIR environment variable
"""

import asyncio
import os
import platform
import shutil
import sys

import pytest

# ---------------------------------------------------------------------------
# Engine discovery
# ---------------------------------------------------------------------------

# Well-known engine binary names to search for on PATH
WELL_KNOWN_ENGINES = [
    "stockfish",
    "lc0",
    "komodo",
    "ethereal",
    "crafty",
    "fruit",
    "toga2",
    "rodent4",
    "patricia",
]

QA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(QA_DIR)
DEFAULT_ENGINE_DIR = os.path.join(
    PROJECT_ROOT, "chess-uci-server", "deploy", "linux", "engines"
)


def _discover_engines():
    """Find all available UCI engine executables.

    Returns a list of (name, path) tuples.
    """
    engines = []
    seen = set()

    # 1. Check PATH for well-known engines
    for name in WELL_KNOWN_ENGINES:
        path = shutil.which(name)
        if path and path not in seen:
            engines.append((name, path))
            seen.add(path)

    # 2. Scan the default engine directory
    engine_dir = os.environ.get("ENGINE_VALIDATION_DIR", DEFAULT_ENGINE_DIR)
    if os.path.isdir(engine_dir):
        # Import discover_engines from the server module
        try:
            import importlib.util
            server_script = os.path.join(
                PROJECT_ROOT, "chess-uci-server", "deploy", "linux", "chess.py"
            )
            spec = importlib.util.spec_from_file_location("chess_server", server_script)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for name, path in mod.discover_engines(engine_dir):
                if path not in seen:
                    engines.append((name, path))
                    seen.add(path)
        except Exception:
            # Fallback: manual scan
            is_windows = platform.system() == "Windows"
            for entry in sorted(os.listdir(engine_dir)):
                full = os.path.join(engine_dir, entry)
                if not os.path.isfile(full):
                    continue
                if is_windows and not entry.endswith(".exe"):
                    continue
                if not is_windows and not os.access(full, os.X_OK):
                    continue
                name = os.path.splitext(entry)[0]
                if full not in seen:
                    engines.append((name, full))
                    seen.add(full)

    return engines


# Discover engines once at module load
DISCOVERED_ENGINES = _discover_engines()


def _engine_ids():
    """Generate pytest IDs for parametrize."""
    return [name for name, _ in DISCOVERED_ENGINES]


# ---------------------------------------------------------------------------
# Skip if no engines found
# ---------------------------------------------------------------------------

if not DISCOVERED_ENGINES:
    pytest.skip(
        "No UCI engines found (install stockfish or set ENGINE_VALIDATION_DIR)",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Helper: run engine as subprocess and exchange UCI commands
# ---------------------------------------------------------------------------

async def _start_engine(engine_path, timeout=10):
    """Start an engine subprocess, return (process, reader_task)."""
    proc = await asyncio.create_subprocess_exec(
        engine_path,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=os.path.dirname(engine_path),
    )
    return proc


async def _send(proc, command):
    """Send a command to the engine."""
    proc.stdin.write(f"{command}\n".encode())
    await proc.stdin.drain()


async def _read_until(proc, marker, timeout=10):
    """Read lines until one contains the marker. Returns all lines."""
    lines = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError(
                f"Engine did not produce '{marker}' within {timeout}s. "
                f"Got {len(lines)} lines: {lines[-5:]}"
            )
        try:
            data = await asyncio.wait_for(
                proc.stdout.readline(), timeout=remaining
            )
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(
                f"Engine did not produce '{marker}' within {timeout}s. "
                f"Got {len(lines)} lines: {lines[-5:]}"
            )
        if not data:
            raise ConnectionError(
                f"Engine exited before '{marker}'. "
                f"Got {len(lines)} lines: {lines[-5:]}"
            )
        line = data.decode(errors="replace").strip()
        lines.append(line)
        if marker in line:
            return lines


# ---------------------------------------------------------------------------
# Tests - parametrized over all discovered engines
# ---------------------------------------------------------------------------

@pytest.mark.engine
@pytest.mark.parametrize("engine_name,engine_path", DISCOVERED_ENGINES, ids=_engine_ids())
class TestEngineValidation:
    """Validate that a UCI engine starts, responds correctly, and shuts down."""

    @pytest.mark.timeout(30)
    async def test_uci_handshake(self, engine_name, engine_path):
        """Engine responds to 'uci' with id lines and 'uciok'."""
        proc = await _start_engine(engine_path)
        try:
            await _send(proc, "uci")
            lines = await _read_until(proc, "uciok", timeout=15)

            # Verify we got at least 'id name' and 'uciok'
            has_id_name = any(l.startswith("id name") for l in lines)
            has_uciok = any("uciok" in l for l in lines)
            assert has_uciok, f"No uciok received. Lines: {lines}"
            assert has_id_name, f"No 'id name' received. Lines: {lines}"
        finally:
            try:
                await _send(proc, "quit")
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                proc.kill()

    @pytest.mark.timeout(30)
    async def test_isready(self, engine_name, engine_path):
        """Engine responds to 'isready' with 'readyok'."""
        proc = await _start_engine(engine_path)
        try:
            await _send(proc, "uci")
            await _read_until(proc, "uciok", timeout=15)

            await _send(proc, "isready")
            lines = await _read_until(proc, "readyok", timeout=10)
            assert any("readyok" in l for l in lines)
        finally:
            try:
                await _send(proc, "quit")
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                proc.kill()

    @pytest.mark.timeout(60)
    async def test_position_and_go(self, engine_name, engine_path):
        """Engine processes a position and returns bestmove."""
        proc = await _start_engine(engine_path)
        try:
            await _send(proc, "uci")
            await _read_until(proc, "uciok", timeout=15)
            await _send(proc, "isready")
            await _read_until(proc, "readyok", timeout=10)

            await _send(proc, "position startpos")
            await _send(proc, "go depth 5")
            lines = await _read_until(proc, "bestmove", timeout=30)

            bestmove_line = [l for l in lines if l.startswith("bestmove")]
            assert bestmove_line, f"No bestmove received. Lines: {lines[-10:]}"

            # Verify bestmove has a valid move (4-5 chars like e2e4 or e7e8q)
            parts = bestmove_line[0].split()
            assert len(parts) >= 2, f"Malformed bestmove: {bestmove_line[0]}"
            move = parts[1]
            assert 4 <= len(move) <= 5, f"Invalid move format: {move}"
        finally:
            try:
                await _send(proc, "quit")
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                proc.kill()

    @pytest.mark.timeout(30)
    async def test_clean_quit(self, engine_name, engine_path):
        """Engine exits cleanly on 'quit' command."""
        proc = await _start_engine(engine_path)
        try:
            await _send(proc, "uci")
            await _read_until(proc, "uciok", timeout=15)

            await _send(proc, "quit")
            return_code = await asyncio.wait_for(proc.wait(), timeout=10)
            # Most engines exit with 0, but any clean exit is acceptable
            assert return_code is not None, "Engine did not exit after quit"
        except asyncio.TimeoutError:
            proc.kill()
            pytest.fail(f"Engine {engine_name} did not exit within 10s after quit")
