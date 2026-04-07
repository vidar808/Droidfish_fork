"""Integration tests for authentication over real TCP connections."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


async def test_no_auth_connects_directly(run_server, base_config):
    """With no auth configured, client connects and gets UCI response directly."""
    port = base_config["engines"]["MockEngine"]["port"]
    await run_server(base_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        info = await client.uci_handshake(timeout=10)
        assert info["name"] is not None, "Should receive engine name without auth"
    finally:
        await client.close()


async def test_token_auth_correct(run_server, auth_token_config):
    """With token auth, correct token should succeed."""
    port = auth_token_config["engines"]["MockEngine"]["port"]
    await run_server(auth_token_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        result = await client.authenticate_token("test_token_abc123")
        assert result is True, "Token auth should succeed with correct token"

        info = await client.uci_handshake(timeout=10)
        assert info["name"] is not None
    finally:
        await client.close()


async def test_token_auth_wrong(run_server, auth_token_config):
    """With token auth, wrong token should fail."""
    port = auth_token_config["engines"]["MockEngine"]["port"]
    await run_server(auth_token_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        # Read AUTH_REQUIRED
        line = await client.recv_line(timeout=5)
        assert "AUTH_REQUIRED" in line

        # Send wrong token
        await client.send("AUTH wrong_token_value")
        result = await client.recv_line(timeout=5)
        assert result == "AUTH_FAIL", f"Expected AUTH_FAIL, got {result}"

        # Connection should be closed by server
        follow_up = await client.recv_line(timeout=3)
        assert follow_up is None, "Connection should be closed after AUTH_FAIL"
    finally:
        await client.close()


async def test_psk_auth_correct(run_server, auth_psk_config):
    """With PSK auth, correct key should succeed."""
    port = auth_psk_config["engines"]["MockEngine"]["port"]
    await run_server(auth_psk_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        result = await client.authenticate_psk("test_psk_key_xyz789")
        assert result is True, "PSK auth should succeed with correct key"

        info = await client.uci_handshake(timeout=10)
        assert info["name"] is not None
    finally:
        await client.close()


async def test_psk_auth_wrong(run_server, auth_psk_config):
    """With PSK auth, wrong key should fail."""
    port = auth_psk_config["engines"]["MockEngine"]["port"]
    await run_server(auth_psk_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        # Read AUTH_REQUIRED
        line = await client.recv_line(timeout=5)
        assert "AUTH_REQUIRED" in line

        # Send wrong PSK
        await client.send("PSK_AUTH wrong_key_value")
        result = await client.recv_line(timeout=5)
        assert result == "AUTH_FAIL", f"Expected AUTH_FAIL, got {result}"

        # Connection should be closed
        follow_up = await client.recv_line(timeout=3)
        assert follow_up is None, "Connection should be closed after AUTH_FAIL"
    finally:
        await client.close()


async def test_auth_timeout(run_server, auth_token_config):
    """With token auth, not sending credentials should trigger timeout."""
    # The server has a 10s auth timeout hardcoded. We connect but never send auth.
    port = auth_token_config["engines"]["MockEngine"]["port"]
    await run_server(auth_token_config)

    client = MockClient(port=port)
    try:
        await client.connect(timeout=5)
        # Read AUTH_REQUIRED
        line = await client.recv_line(timeout=5)
        assert "AUTH_REQUIRED" in line

        # Don't send auth - wait for server to time out and close connection.
        # Server auth timeout is 10s, so we wait up to 15s.
        result = await client.recv_line(timeout=15)
        assert result is None, "Connection should close after auth timeout"
    finally:
        await client.close()
