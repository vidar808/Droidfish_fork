"""Stress tests for throughput and data handling."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


@pytest.mark.slow
async def test_rapid_commands(run_server, base_config):
    """Send 20 isready commands as fast as possible, verify all readyok received."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        await client.uci_handshake()

        count = 20
        # Send all isready commands without waiting
        for _ in range(count):
            await client.send("isready")

        readyok_count = 0
        deadline = asyncio.get_event_loop().time() + 15
        while readyok_count < count:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            line = await client.recv_line(timeout=remaining)
            if line is None:
                break
            if line == "readyok":
                readyok_count += 1

        assert readyok_count == count, (
            f"Expected {count} readyok, got {readyok_count}"
        )
    finally:
        await client.close()


@pytest.mark.slow
async def test_large_position(run_server, base_config):
    """Send a position with a very long move list (50+ moves), then go depth 1."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    # Generate a plausible long move list (doesn't need to be legal for mock engine)
    moves = [
        "e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6",
        "e1g1", "f8e7", "f1e1", "b7b5", "a4b3", "d7d6", "c2c3", "e8g8",
        "h2h3", "c6b8", "d2d4", "b8d7", "b3c2", "c7c5", "d4d5", "d7b6",
        "b1d2", "a6a5", "a2a4", "b5a4", "c2a4", "b6a4", "a1a4", "f6d7",
        "d2f1", "f7f5", "f1g3", "f5e4", "g3e4", "d7f6", "e4f6", "e7f6",
        "c1g5", "f6g5", "f3g5", "d8f6", "g5e4", "f6f5", "e4g3", "f5f6",
        "d1d3", "a8a6", "g3e4", "f6f7",
    ]
    position_cmd = "position startpos moves " + " ".join(moves)

    client = MockClient(port=port)
    await client.connect()
    try:
        await client.uci_handshake()

        await client.send(position_cmd)
        await client.send("go depth 1")

        lines = await client.recv_until("bestmove", timeout=10)
        bestmove_line = lines[-1]
        assert bestmove_line.startswith("bestmove"), (
            f"Expected bestmove, got: {bestmove_line}"
        )
    finally:
        await client.close()


@pytest.mark.slow
async def test_throttle_under_load(run_server, base_config):
    """With info_throttle_ms=100, do go depth 5, verify bestmove still arrives."""
    base_config["info_throttle_ms"] = 100
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        await client.uci_handshake()

        bestmove, info_lines = await client.go_and_wait(depth=5, timeout=15)
        assert bestmove.startswith("bestmove"), (
            f"Expected bestmove, got: {bestmove}"
        )
    finally:
        await client.close()
