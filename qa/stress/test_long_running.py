"""Stress tests for long-running sessions."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


@pytest.mark.slow
async def test_sustained_session(run_server, base_config):
    """Connect once and perform 10 sequential go commands over one session."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        await client.uci_handshake()

        for i in range(10):
            bestmove, info_lines = await client.go_and_wait(depth=3, timeout=10)
            assert bestmove.startswith("bestmove"), (
                f"Iteration {i}: expected bestmove, got: {bestmove}"
            )
    finally:
        await client.close()


@pytest.mark.slow
async def test_many_isready(run_server, base_config):
    """Send 50 isready commands and verify 50 readyok responses."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        await client.uci_handshake()

        count = 50
        for _ in range(count):
            await client.send("isready")

        readyok_count = 0
        deadline = asyncio.get_event_loop().time() + 30
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
            f"Expected {count} readyok responses, got {readyok_count}"
        )
    finally:
        await client.close()
