"""Integration tests for TLS connections."""

import asyncio

import pytest

from qa.fixtures.mock_client import MockClient


pytestmark = pytest.mark.tls


async def test_tls_connection_succeeds(run_server, tls_config):
    """Start server with TLS, connect with TLS client, verify UCI handshake."""
    port = tls_config["engines"]["MockEngine"]["port"]
    await run_server(tls_config)

    client = MockClient(port=port, use_tls=True, verify_ssl=False)
    try:
        await client.connect(timeout=5)
        info = await client.uci_handshake(timeout=10)
        assert info["name"] is not None, "Should complete UCI handshake over TLS"
    finally:
        await client.close()


async def test_plaintext_to_tls_server_fails(run_server, tls_config):
    """Connecting with plain TCP to a TLS server should fail."""
    port = tls_config["engines"]["MockEngine"]["port"]
    await run_server(tls_config)

    client = MockClient(port=port, use_tls=False)
    try:
        await client.connect(timeout=5)
        # Attempting to read should fail or return garbage
        try:
            line = await client.recv_line(timeout=3)
            # If we get a line back, it should not be valid UCI
            # (TLS handshake bytes would appear as garbage)
            if line is not None:
                assert "uciok" not in line, "Should not get valid UCI over plaintext"
        except (ConnectionError, asyncio.TimeoutError, UnicodeDecodeError, OSError):
            pass  # Expected - TLS server rejects plain TCP
    finally:
        await client.close()


async def test_tls_with_auth(run_server, tls_config):
    """Combine TLS + token auth and verify both work together."""
    # Add token auth to the TLS config
    tls_config["auth_method"] = "token"
    tls_config["auth_token"] = "test_token_abc123"

    port = tls_config["engines"]["MockEngine"]["port"]
    await run_server(tls_config)

    client = MockClient(port=port, use_tls=True, verify_ssl=False)
    try:
        await client.connect(timeout=5)
        result = await client.authenticate_token("test_token_abc123")
        assert result is True, "Token auth should work over TLS"

        info = await client.uci_handshake(timeout=10)
        assert info["name"] is not None, "UCI handshake should work after TLS + auth"
    finally:
        await client.close()
