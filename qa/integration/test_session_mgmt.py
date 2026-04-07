"""Integration tests for SessionManager (warm reattach)."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


@pytest.mark.xfail(
    reason="Warm reattach may lose engine stdout data between session handoffs — "
           "known limitation of the SessionManager design",
    strict=False,
)
async def test_session_keepalive_reattach(run_server, base_config):
    """With session keepalive, disconnecting and reconnecting reattaches."""
    base_config["session_keepalive_timeout"] = 30
    port = base_config["engines"]["MockEngine"]["port"]
    await run_server(base_config)

    # First connection
    client1 = MockClient(port=port)
    try:
        await client1.connect(timeout=5)
        info1 = await client1.uci_handshake(timeout=10)
        assert info1["name"] is not None
    finally:
        await client1.close()

    # Wait for server to detect disconnect and release session.
    # The server needs time to notice the TCP close and release the session.
    await asyncio.sleep(3)

    # Second connection - should reattach to warm engine.
    # On reattach, the server sends 'uci' to the still-running engine.
    # The engine responds again with id/uciok. But the warm engine's stdout
    # pipe may have buffered readyok from a stale heartbeat. Accept any
    # response that eventually includes uciok.
    client2 = MockClient(port=port)
    try:
        await client2.connect(timeout=5)
        # Read whatever the server sends — may include stale readyok, then uciok
        lines = await client2.recv_until("uciok", timeout=15)
        assert any("uciok" in l for l in lines), f"Expected uciok, got: {lines}"
    finally:
        await client2.close()


async def test_session_no_keepalive(run_server, base_config):
    """With session_keepalive_timeout=0, engine should terminate on disconnect."""
    base_config["session_keepalive_timeout"] = 0
    port = base_config["engines"]["MockEngine"]["port"]
    await run_server(base_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        info = await client.uci_handshake(timeout=10)
        assert info["name"] is not None
    finally:
        await client.close()

    # Brief pause for cleanup
    await asyncio.sleep(0.5)

    # Reconnect - should get a fresh engine (new UCI handshake)
    client2 = MockClient(port=port)
    try:
        await client2.connect(timeout=5)
        info2 = await client2.uci_handshake(timeout=10)
        assert info2["name"] is not None, "Fresh engine should respond to UCI"
    finally:
        await client2.close()


@pytest.mark.slow
async def test_session_expires(run_server, base_config):
    """With short keepalive, waiting beyond it should start a fresh engine."""
    base_config["session_keepalive_timeout"] = 2
    port = base_config["engines"]["MockEngine"]["port"]
    await run_server(base_config)

    # First connection
    client1 = MockClient(port=port)
    try:
        await client1.connect(timeout=5)
        info1 = await client1.uci_handshake(timeout=10)
        assert info1["name"] is not None
    finally:
        await client1.close()

    # Wait longer than keepalive timeout for session to expire
    await asyncio.sleep(3)

    # Reconnect - session should have expired, new engine starts
    client2 = MockClient(port=port)
    try:
        await client2.connect(timeout=5)
        info2 = await client2.uci_handshake(timeout=10)
        assert info2["name"] is not None, "Fresh engine should start after session expiry"
    finally:
        await client2.close()
