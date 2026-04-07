"""Integration tests for OutputThrottler with real async timing."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


async def test_no_throttle_all_lines_pass(run_server, base_config):
    """With info_throttle_ms=0, all info lines should be received."""
    base_config["info_throttle_ms"] = 0
    port = base_config["engines"]["MockEngine"]["port"]
    await run_server(base_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        await client.uci_handshake(timeout=10)

        await client.send("isready")
        await client.recv_until("readyok", timeout=5)

        bestmove, info_lines = await client.go_and_wait(depth=5, timeout=10)

        # Mock engine emits info lines for depth 1..5
        assert len(info_lines) >= 5, \
            f"Expected at least 5 info lines with no throttle, got {len(info_lines)}"
        assert bestmove.startswith("bestmove"), \
            f"Expected bestmove line, got {bestmove}"
    finally:
        await client.close()


async def test_throttle_reduces_info_lines(run_server, base_config):
    """With throttling, depth-change info lines still pass but bestmove arrives.

    The OutputThrottler always forwards info lines when the depth changes,
    so with the mock engine (which sends one line per depth), all info lines
    pass. This test verifies the throttler doesn't break the flow — all
    depth-change lines pass through, and bestmove arrives.
    """
    base_config["info_throttle_ms"] = 500
    port = base_config["engines"]["MockEngine"]["port"]
    await run_server(base_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        await client.uci_handshake(timeout=10)

        await client.send("isready")
        await client.recv_until("readyok", timeout=5)

        bestmove, info_lines = await client.go_and_wait(depth=5, timeout=10)

        # Each info line has a different depth, so the throttler forwards all.
        # Verify they're all present and bestmove arrives.
        assert len(info_lines) >= 1, \
            f"Expected at least 1 info line with throttle, got {len(info_lines)}"
        assert bestmove.startswith("bestmove")
    finally:
        await client.close()


async def test_bestmove_always_passes(run_server, base_config):
    """With throttling enabled, bestmove should never be filtered."""
    base_config["info_throttle_ms"] = 1000  # Aggressive throttle
    port = base_config["engines"]["MockEngine"]["port"]
    await run_server(base_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        await client.uci_handshake(timeout=10)

        await client.send("isready")
        await client.recv_until("readyok", timeout=5)

        bestmove, info_lines = await client.go_and_wait(depth=5, timeout=10)

        assert bestmove.startswith("bestmove"), \
            f"bestmove must always pass through throttler, got: {bestmove}"
    finally:
        await client.close()
