"""End-to-end tests for multiple simultaneous client connections."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


async def test_two_clients_same_engine(run_server, base_config):
    """Two clients connect to the same engine port in per-engine mode."""
    await run_server(base_config)

    port = next(iter(base_config["engines"].values()))["port"]
    client1 = MockClient(host="127.0.0.1", port=port)
    client2 = MockClient(host="127.0.0.1", port=port)

    try:
        await client1.connect()
        info1 = await client1.uci_handshake()
        assert info1["name"] is not None

        await client2.connect()
        info2 = await client2.uci_handshake()
        assert info2["name"] is not None

        # Both clients should be able to execute go commands
        bestmove1, infos1 = await client1.go_and_wait(depth=3, timeout=10)
        assert bestmove1.startswith("bestmove")

        bestmove2, infos2 = await client2.go_and_wait(depth=3, timeout=10)
        assert bestmove2.startswith("bestmove")
    finally:
        await client1.close()
        await client2.close()


async def test_multiplex_two_clients_different_engines(
    run_server, multiplex_config
):
    """In multiplex mode, two clients select different engines."""
    await run_server(multiplex_config)

    port = multiplex_config["base_port"]
    client1 = MockClient(host="127.0.0.1", port=port)
    client2 = MockClient(host="127.0.0.1", port=port)

    try:
        # Client 1 selects Engine_A
        await client1.connect()
        engines1 = await client1.select_engine("Engine_A")
        assert "Engine_A" in engines1
        assert "Engine_B" in engines1
        info1 = await client1.uci_handshake()
        assert info1["name"] is not None

        # Client 2 selects Engine_B
        await client2.connect()
        engines2 = await client2.select_engine("Engine_B")
        info2 = await client2.uci_handshake()
        assert info2["name"] is not None

        # Both should work independently
        bestmove1, infos1 = await client1.go_and_wait(depth=3, timeout=10)
        assert bestmove1.startswith("bestmove")

        bestmove2, infos2 = await client2.go_and_wait(depth=3, timeout=10)
        assert bestmove2.startswith("bestmove")
    finally:
        await client1.close()
        await client2.close()


async def test_multiplex_two_clients_same_engine(
    run_server, multiplex_config
):
    """In multiplex mode, two clients select the same engine."""
    await run_server(multiplex_config)

    port = multiplex_config["base_port"]
    client1 = MockClient(host="127.0.0.1", port=port)
    client2 = MockClient(host="127.0.0.1", port=port)

    try:
        # Both clients select Engine_A
        await client1.connect()
        await client1.select_engine("Engine_A")
        info1 = await client1.uci_handshake()
        assert info1["name"] is not None

        await client2.connect()
        await client2.select_engine("Engine_A")
        info2 = await client2.uci_handshake()
        assert info2["name"] is not None

        # Both should work
        bestmove1, infos1 = await client1.go_and_wait(depth=3, timeout=10)
        assert bestmove1.startswith("bestmove")

        bestmove2, infos2 = await client2.go_and_wait(depth=3, timeout=10)
        assert bestmove2.startswith("bestmove")
    finally:
        await client1.close()
        await client2.close()
