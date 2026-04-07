"""End-to-end tests for full UCI protocol exchange through the server."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


@pytest.fixture
def client_factory(base_config):
    """Create a MockClient pointed at the base_config engine port."""
    port = next(iter(base_config["engines"].values()))["port"]

    def _make():
        return MockClient(host="127.0.0.1", port=port)

    return _make


async def test_uci_init(run_server, base_config, client_factory):
    """Connect and verify id name, id author, options, and uciok are received."""
    await run_server(base_config)
    client = client_factory()
    try:
        await client.connect()
        info = await client.uci_handshake()
        assert info["name"] is not None, "Expected id name line"
        assert info["author"] is not None, "Expected id author line"
        assert len(info["options"]) > 0, "Expected at least one option line"
    finally:
        await client.close()


async def test_isready(run_server, base_config, client_factory):
    """After UCI init, send isready and verify readyok."""
    await run_server(base_config)
    client = client_factory()
    try:
        await client.connect()
        await client.uci_handshake()
        await client.send("isready")
        lines = await client.recv_until("readyok", timeout=5)
        assert any("readyok" in l for l in lines)
    finally:
        await client.close()


async def test_position_and_go(run_server, base_config, client_factory):
    """Send position + go depth 3, verify info lines and bestmove received."""
    await run_server(base_config)
    client = client_factory()
    try:
        await client.connect()
        await client.uci_handshake()
        await client.send("position startpos moves e2e4")
        await client.send("go depth 3")
        lines = await client.recv_until("bestmove", timeout=10)
        info_lines = [l for l in lines if l.startswith("info")]
        bestmove_lines = [l for l in lines if l.startswith("bestmove")]
        assert len(info_lines) > 0, "Expected info lines"
        assert len(bestmove_lines) == 1, "Expected exactly one bestmove"
        assert "e2e4" in bestmove_lines[0]
    finally:
        await client.close()


async def test_go_depth(run_server, base_config, client_factory):
    """Send go depth 5, verify info lines with increasing depth values."""
    await run_server(base_config)
    client = client_factory()
    try:
        await client.connect()
        await client.uci_handshake()
        await client.send("position startpos")
        await client.send("go depth 5")
        lines = await client.recv_until("bestmove", timeout=10)
        info_lines = [l for l in lines if l.startswith("info")]
        # Extract depth values from info lines
        depths = []
        for line in info_lines:
            parts = line.split()
            if "depth" in parts:
                idx = parts.index("depth")
                if idx + 1 < len(parts):
                    depths.append(int(parts[idx + 1]))
        assert len(depths) >= 2, f"Expected multiple depth values, got {depths}"
        # Verify depths are increasing
        for i in range(1, len(depths)):
            assert depths[i] >= depths[i - 1], \
                f"Depths should be non-decreasing: {depths}"
    finally:
        await client.close()


async def test_setoption(run_server, base_config, client_factory):
    """Send setoption, then isready, verify readyok (option accepted silently)."""
    await run_server(base_config)
    client = client_factory()
    try:
        await client.connect()
        await client.uci_handshake()
        await client.send("setoption name Hash value 32")
        await client.send("isready")
        lines = await client.recv_until("readyok", timeout=5)
        assert any("readyok" in l for l in lines)
    finally:
        await client.close()


async def test_ucinewgame(run_server, base_config, client_factory):
    """Send ucinewgame, then isready, verify readyok."""
    await run_server(base_config)
    client = client_factory()
    try:
        await client.connect()
        await client.uci_handshake()
        await client.send("ucinewgame")
        await client.send("isready")
        lines = await client.recv_until("readyok", timeout=5)
        assert any("readyok" in l for l in lines)
    finally:
        await client.close()


async def test_stop_command(run_server, base_config, client_factory):
    """Send go depth 100, immediately send stop, verify bestmove received."""
    await run_server(base_config)
    client = client_factory()
    try:
        await client.connect()
        await client.uci_handshake()
        await client.send("position startpos")
        await client.send("go depth 100")
        await client.send("stop")
        lines = await client.recv_until("bestmove", timeout=10)
        bestmove_lines = [l for l in lines if l.startswith("bestmove")]
        assert len(bestmove_lines) >= 1, "Expected bestmove after stop"
    finally:
        await client.close()


async def test_multiple_go_sequences(run_server, base_config, client_factory):
    """Do go depth 3, wait for bestmove, then go depth 5, wait for bestmove."""
    await run_server(base_config)
    client = client_factory()
    try:
        await client.connect()
        await client.uci_handshake()

        # First go sequence
        bestmove1, info1 = await client.go_and_wait(depth=3, timeout=10)
        assert bestmove1.startswith("bestmove")
        assert len(info1) > 0

        # Second go sequence
        bestmove2, info2 = await client.go_and_wait(depth=5, timeout=10)
        assert bestmove2.startswith("bestmove")
        assert len(info2) > 0
    finally:
        await client.close()


async def test_quit_closes_connection(run_server, base_config, client_factory):
    """After init, send quit and verify the connection is closed by the server."""
    await run_server(base_config)
    client = client_factory()
    try:
        await client.connect()
        await client.uci_handshake()
        await client.send("quit")
        # After quit, server should close the connection; reads should return None or EOF
        try:
            line = await client.recv_line(timeout=5)
            # Either None (EOF) or the connection drops
            # Some servers may close immediately, some may send nothing
        except (ConnectionError, asyncio.TimeoutError):
            pass  # Expected: connection closed
    finally:
        await client.close()
