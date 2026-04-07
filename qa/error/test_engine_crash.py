"""Tests for engine crash and failure scenarios."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


async def test_engine_crash_on_uci(run_server, base_config, mock_engine_executable_crash):
    """Engine crashes on uci command; verify server handles it gracefully."""
    base_config["engines"]["MockEngine"]["path"] = mock_engine_executable_crash
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        # The engine crashes on "uci", so we expect either:
        # - connection closed (None from recv_line)
        # - a timeout
        # - an error message from the server
        with pytest.raises((ConnectionError, asyncio.TimeoutError)):
            await client.uci_handshake(timeout=5)
    finally:
        await client.close()


async def test_engine_hang_on_uci(run_server, base_config, mock_engine_executable_hang):
    """Engine never sends uciok; verify client-side timeout handling."""
    base_config["engines"]["MockEngine"]["path"] = mock_engine_executable_hang
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        # Engine hangs, so uci_handshake should time out
        with pytest.raises((asyncio.TimeoutError, ConnectionError)):
            await client.uci_handshake(timeout=5)
    finally:
        await client.close()


async def test_engine_process_dies_midstream(run_server, base_config):
    """Disconnect abruptly mid-stream, reconnect, verify server still works."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    # First client: connect, start a go, then disconnect abruptly
    client1 = MockClient(port=port)
    await client1.connect()
    try:
        await client1.uci_handshake()
        await client1.send("position startpos")
        await client1.send("go depth 5")
        # Don't wait for bestmove - disconnect abruptly
    finally:
        # Force close without sending quit
        if client1.writer and not client1.writer.is_closing():
            client1.writer.close()

    # Brief pause for server to detect disconnect and clean up
    await asyncio.sleep(1.0)

    # Second client: verify server still works
    client2 = MockClient(port=port)
    await client2.connect()
    try:
        info = await client2.uci_handshake()
        assert info["name"] is not None
        bestmove, _ = await client2.go_and_wait(depth=3, timeout=10)
        assert bestmove.startswith("bestmove")
    finally:
        await client2.close()
