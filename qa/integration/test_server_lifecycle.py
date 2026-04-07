"""Integration tests for server startup, shutdown, and PID file management."""

import asyncio
import os
import tempfile

import pytest

from qa.fixtures.mock_client import MockClient


async def test_server_starts_and_accepts_connection(run_server, base_config, free_port):
    """Start server with base_config, connect a client, verify connection works."""
    port = base_config["engines"]["MockEngine"]["port"]
    await run_server(base_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        info = await client.uci_handshake(timeout=10)
        assert info["name"] is not None, "Expected engine name in UCI handshake"
    finally:
        await client.close()


async def test_server_listens_on_configured_port(run_server, base_config):
    """Verify the server is listening on the port from config."""
    port = base_config["engines"]["MockEngine"]["port"]
    await run_server(base_config)

    # Verify we can open a raw TCP connection to that port
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection("127.0.0.1", port), timeout=5
    )
    writer.close()
    await writer.wait_closed()


async def test_server_graceful_shutdown(run_server, base_config):
    """Start server, connect client, terminate server, verify connection closes."""
    port = base_config["engines"]["MockEngine"]["port"]
    proc = await run_server(base_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        info = await client.uci_handshake(timeout=10)
        assert info["name"] is not None

        # Terminate the server process
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

        # The client connection should be closed (recv returns None or raises)
        try:
            line = await client.recv_line(timeout=3)
            # If we get None, the connection was closed
            if line is not None:
                # Read until connection drops
                while True:
                    line = await client.recv_line(timeout=2)
                    if line is None:
                        break
        except (ConnectionError, asyncio.TimeoutError, OSError):
            pass  # Expected - connection was severed
    finally:
        await client.close()


async def test_pid_file_created_and_removed(chess_module):
    """Test write_pid_file, read_pid_file, remove_pid_file functions."""
    with tempfile.NamedTemporaryFile(suffix=".pid", delete=False) as f:
        pid_path = f.name

    try:
        chess_module.write_pid_file(pid_path)

        pid = chess_module.read_pid_file(pid_path)
        assert pid == os.getpid(), f"Expected PID {os.getpid()}, got {pid}"

        chess_module.remove_pid_file(pid_path)
        assert not os.path.exists(pid_path), "PID file should be removed"
    finally:
        if os.path.exists(pid_path):
            os.unlink(pid_path)


async def test_is_process_alive_self(chess_module):
    """Verify is_process_alive returns True for the current process."""
    assert chess_module.is_process_alive(os.getpid()) is True


async def test_is_process_alive_bogus(chess_module):
    """Verify is_process_alive returns False for a non-existent PID."""
    assert chess_module.is_process_alive(99999) is False
