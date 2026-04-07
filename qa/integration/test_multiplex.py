"""Integration tests for single-port engine multiplexing."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


async def test_engine_list(run_server, multiplex_config):
    """Connect to multiplex server, send ENGINE_LIST, verify engines returned."""
    port = multiplex_config["base_port"]
    await run_server(multiplex_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)

        await client.send("ENGINE_LIST")
        engines = []
        while True:
            line = await client.recv_line(timeout=5)
            if line is None:
                break
            if line == "ENGINES_END":
                break
            if line.startswith("ENGINE "):
                engines.append(line[7:])

        assert "Engine_A" in engines, f"Engine_A not in engine list: {engines}"
        assert "Engine_B" in engines, f"Engine_B not in engine list: {engines}"
    finally:
        await client.close()


async def test_select_engine(run_server, multiplex_config):
    """Connect, list engines, select Engine_A, verify ENGINE_SELECTED and UCI."""
    port = multiplex_config["base_port"]
    await run_server(multiplex_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)

        engines = await client.select_engine("Engine_A")
        assert "Engine_A" in engines

        # After ENGINE_SELECTED, the server sends UCI init
        info = await client.uci_handshake(timeout=10)
        assert info["name"] is not None, "Should get UCI handshake after selecting engine"
    finally:
        await client.close()


async def test_select_unknown_engine(run_server, multiplex_config):
    """Selecting a non-existent engine should return ENGINE_ERROR."""
    port = multiplex_config["base_port"]
    await run_server(multiplex_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)

        await client.send("ENGINE_LIST")
        while True:
            line = await client.recv_line(timeout=5)
            if line is None or line == "ENGINES_END":
                break

        await client.send("SELECT_ENGINE NonExistentEngine")
        result = await client.recv_line(timeout=5)
        assert result is not None and result.startswith("ENGINE_ERROR"), \
            f"Expected ENGINE_ERROR, got {result}"
    finally:
        await client.close()


async def test_default_engine_on_uci(run_server, multiplex_config):
    """Sending 'uci' directly (without ENGINE_LIST) should use default engine."""
    port = multiplex_config["base_port"]
    await run_server(multiplex_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)

        # Send "uci" directly instead of ENGINE_LIST
        await client.send("uci")

        # Server should treat this as using the default engine and forward to it
        lines = await client.recv_until("uciok", timeout=10)
        assert any("uciok" in line for line in lines), \
            f"Should get uciok from default engine, got: {lines}"
    finally:
        await client.close()
