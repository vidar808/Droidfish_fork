"""Tests for network error conditions and trust/security handling."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


async def test_client_abrupt_disconnect(run_server, base_config):
    """Client disconnects without quit; server stays healthy for next client."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    # Connect and get uciok, then close abruptly
    client1 = MockClient(port=port)
    await client1.connect()
    await client1.uci_handshake()
    # Close without sending quit
    await client1.close()

    await asyncio.sleep(0.5)

    # Verify server still works
    client2 = MockClient(port=port)
    await client2.connect()
    try:
        info = await client2.uci_handshake()
        assert info["name"] is not None
        bestmove, _ = await client2.go_and_wait(depth=3, timeout=10)
        assert bestmove.startswith("bestmove")
    finally:
        await client2.close()


async def test_connect_to_wrong_port(run_server, base_config):
    """Connecting to a port that isn't the server should fail."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    wrong_port = port + 1
    client = MockClient(port=wrong_port)
    with pytest.raises((ConnectionRefusedError, OSError)):
        await client.connect(timeout=3)


async def test_untrusted_ip_rejected(run_server, base_config):
    """With trusted_sources excluding localhost, connection should be rejected."""
    base_config["enable_trusted_sources"] = True
    base_config["trusted_sources"] = ["10.0.0.1"]
    base_config["trusted_subnets"] = ["10.0.0.0/8"]
    base_config["enable_auto_trust"] = False
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        # Server should reject untrusted IP - expect connection closed or timeout
        with pytest.raises((ConnectionError, asyncio.TimeoutError)):
            await client.uci_handshake(timeout=5)
    finally:
        await client.close()


async def test_auto_trust(run_server, base_config):
    """With enable_auto_trust=True and empty trusted_sources, client should connect."""
    base_config["enable_auto_trust"] = True
    base_config["enable_trusted_sources"] = True
    base_config["trusted_sources"] = []
    base_config["trusted_subnets"] = []
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        info = await client.uci_handshake()
        assert info["name"] is not None
    finally:
        await client.close()


async def test_connection_refused_after_shutdown(run_server, base_config):
    """After server is stopped, connections should be refused."""
    proc = await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    # Verify server is running
    client = MockClient(port=port)
    await client.connect()
    await client.uci_handshake()
    await client.close()

    # Stop the server
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()

    await asyncio.sleep(0.5)

    # Now connection should be refused
    client2 = MockClient(port=port)
    with pytest.raises((ConnectionRefusedError, OSError)):
        await client2.connect(timeout=3)
