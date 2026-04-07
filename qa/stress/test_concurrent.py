"""Stress tests for concurrent client connections."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


@pytest.mark.slow
async def test_five_sequential_clients(run_server, base_config):
    """Connect 5 clients one after another, each doing uci_handshake + go."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    for i in range(5):
        client = MockClient(port=port)
        await client.connect()
        try:
            info = await client.uci_handshake()
            assert info["name"] is not None
            bestmove, info_lines = await client.go_and_wait(depth=3)
            assert bestmove.startswith("bestmove")
        finally:
            await client.close()


@pytest.mark.slow
async def test_ten_rapid_connections(run_server, base_config):
    """Open 10 connections rapidly without reading, close all, then verify server is alive."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    # Open 10 connections rapidly
    clients = []
    for _ in range(10):
        client = MockClient(port=port)
        try:
            await client.connect(timeout=3)
            clients.append(client)
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
            # Some connections may be refused due to max_connections; that's OK
            pass

    # Close them all
    for client in clients:
        await client.close()

    # Brief pause to let the server clean up
    await asyncio.sleep(0.5)

    # Verify server is still healthy
    verify_client = MockClient(port=port)
    await verify_client.connect()
    try:
        info = await verify_client.uci_handshake()
        assert info["name"] is not None
    finally:
        await verify_client.close()


@pytest.mark.slow
async def test_concurrent_go_commands(run_server, base_config):
    """Send multiple go commands without waiting for bestmove between them."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        await client.uci_handshake()

        # Send multiple go commands back-to-back
        await client.send("position startpos")
        await client.send("go depth 2")
        await client.send("position startpos moves e2e4")
        await client.send("go depth 2")
        await client.send("position startpos moves e2e4 e7e5")
        await client.send("go depth 2")

        # Collect bestmove responses
        bestmoves = []
        lines_read = []
        deadline = asyncio.get_event_loop().time() + 15
        while len(bestmoves) < 3:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            line = await client.recv_line(timeout=remaining)
            if line is None:
                break
            lines_read.append(line)
            if line.startswith("bestmove"):
                bestmoves.append(line)

        assert len(bestmoves) >= 1, f"Expected at least 1 bestmove, got {bestmoves}"
    finally:
        await client.close()
