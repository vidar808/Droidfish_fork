"""End-to-end tests for disconnect and reconnect behavior."""

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


async def test_reconnect_after_disconnect(run_server, base_config, client_factory):
    """Connect, get uciok, close, reconnect, verify new session works."""
    await run_server(base_config)

    # First connection
    client1 = client_factory()
    await client1.connect()
    info1 = await client1.uci_handshake()
    assert info1["name"] is not None
    await client1.close()

    # Brief pause for server to clean up
    await asyncio.sleep(0.5)

    # Second connection
    client2 = client_factory()
    await client2.connect()
    info2 = await client2.uci_handshake()
    assert info2["name"] is not None

    # Verify the new session is functional
    bestmove, info_lines = await client2.go_and_wait(depth=3, timeout=10)
    assert bestmove.startswith("bestmove")
    await client2.close()


@pytest.mark.xfail(
    reason="Warm reattach may lose engine stdout data between session handoffs — "
           "known limitation of the SessionManager design",
    strict=False,
)
async def test_session_keepalive_reconnect(
    run_server, base_config, client_factory
):
    """With session_keepalive_timeout, reconnect reattaches to kept-alive session."""
    base_config["session_keepalive_timeout"] = 30
    await run_server(base_config)

    # First connection
    client1 = client_factory()
    await client1.connect()
    info1 = await client1.uci_handshake()
    assert info1["name"] is not None
    await client1.close()

    # Wait for server to detect disconnect and release session
    await asyncio.sleep(3)

    # Reconnect - session should still be alive (warm reattach).
    # On reattach the server re-sends 'uci' to the engine, which
    # responds again. Read until uciok.
    client2 = client_factory()
    await client2.connect()
    lines = await client2.recv_until("uciok", timeout=15)
    assert any("uciok" in l for l in lines)

    # Verify the reattached session is functional
    bestmove, info_lines = await client2.go_and_wait(depth=3, timeout=10)
    assert bestmove.startswith("bestmove")
    await client2.close()


async def test_rapid_connect_disconnect(run_server, base_config, client_factory):
    """Connect and disconnect 5 times rapidly, verify server stays healthy."""
    await run_server(base_config)

    for i in range(5):
        client = client_factory()
        await client.connect()
        # Just consume the UCI init
        await client.uci_handshake()
        await client.close()
        # Minimal delay between cycles
        await asyncio.sleep(0.2)

    # Final connection to verify server is still healthy
    final_client = client_factory()
    await final_client.connect()
    info = await final_client.uci_handshake()
    assert info["name"] is not None

    bestmove, info_lines = await final_client.go_and_wait(depth=3, timeout=10)
    assert bestmove.startswith("bestmove")
    await final_client.close()
