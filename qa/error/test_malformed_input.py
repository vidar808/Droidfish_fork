"""Tests for malformed and unexpected input handling."""

import asyncio
import os

import pytest

from qa.fixtures.mock_client import MockClient


async def test_binary_data(run_server, base_config):
    """Sending binary data should not crash the server."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    # Send random binary data
    client1 = MockClient(port=port)
    await client1.connect()
    try:
        # Write raw binary data directly to the socket
        binary_data = os.urandom(256) + b"\n"
        client1.writer.write(binary_data)
        await client1.writer.drain()
        # Give server a moment to process
        await asyncio.sleep(0.5)
    finally:
        await client1.close()

    await asyncio.sleep(0.5)

    # Verify server is still alive by connecting another client
    client2 = MockClient(port=port)
    await client2.connect()
    try:
        info = await client2.uci_handshake()
        assert info["name"] is not None
    finally:
        await client2.close()


async def test_empty_lines(run_server, base_config):
    """Sending empty lines should not break the session."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        await client.uci_handshake()

        # Send 10 empty lines
        for _ in range(10):
            client.writer.write(b"\n")
        await client.writer.drain()

        # Verify session is still functional
        await client.send("isready")
        line = await client.recv_line(timeout=5)
        assert line == "readyok"
    finally:
        await client.close()


async def test_very_long_line(run_server, base_config):
    """Sending a 10KB line should not crash the server."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        await client.uci_handshake()

        # Send a 10KB line
        long_line = "x" * 10240
        await client.send(long_line)

        # Give the server time to process
        await asyncio.sleep(0.3)

        # Verify session still works
        await client.send("isready")
        line = await client.recv_line(timeout=5)
        assert line == "readyok"
    finally:
        await client.close()


async def test_invalid_uci_command(run_server, base_config):
    """Sending an unknown UCI command should be ignored; session continues."""
    await run_server(base_config)
    port = base_config["engines"]["MockEngine"]["port"]

    client = MockClient(port=port)
    await client.connect()
    try:
        await client.uci_handshake()

        # Send an invalid command
        await client.send("invalid_command_xyz")

        # Engine (and server) should ignore it; session should still work
        await client.send("isready")
        line = await client.recv_line(timeout=5)
        assert line == "readyok"
    finally:
        await client.close()
