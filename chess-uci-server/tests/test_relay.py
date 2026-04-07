"""Test suite for relay_server.py.

Tests cover:
- Session pairing flow
- Bidirectional data relay
- Disconnect cleanup
- Max sessions limit
- Stale session cleanup
- Invalid protocol handling
- Duplicate session detection
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import relay_server


@pytest.fixture(autouse=True)
def reset_sessions():
    """Clear sessions between tests."""
    relay_server.sessions.clear()
    relay_server.MAX_SESSIONS = 100
    yield
    relay_server.sessions.clear()


# ===========================================================================
# Pairing Flow Tests
# ===========================================================================


class TestRelayServer:
    """Tests for relay server session management."""

    @pytest.mark.asyncio
    async def test_server_registration(self):
        """Server role should register and get REGISTERED response."""
        reader = AsyncMock()
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)

        # Simulate: register, then cancel while waiting for pair
        reader.readline = AsyncMock(side_effect=[
            b"SESSION test123 server\n",
        ])

        # Run handle_connection which dispatches to handle_server_role
        # The server will wait for a paired event; we cancel it
        task = asyncio.create_task(relay_server.handle_connection(reader, writer))
        await asyncio.sleep(0.1)

        # Check REGISTERED was sent
        calls = writer.write.call_args_list
        assert any("REGISTERED" in str(call) for call in calls)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_client_connection(self):
        """Client should get CONNECTED when session exists."""
        # Pre-register a session
        paired_event = asyncio.Event()
        async with relay_server.sessions_lock:
            relay_server.sessions["test456"] = {
                "server_reader": AsyncMock(),
                "server_writer": MagicMock(is_closing=MagicMock(return_value=False)),
                "registered_at": time.time(),
                "paired_event": paired_event,
                "client_reader": None,
                "client_writer": None,
            }

        reader = AsyncMock()
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)

        reader.readline = AsyncMock(return_value=b"SESSION test456 client\n")

        task = asyncio.create_task(relay_server.handle_connection(reader, writer))
        await asyncio.sleep(0.1)

        calls = writer.write.call_args_list
        assert any("CONNECTED" in str(call) for call in calls)
        assert paired_event.is_set()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_unknown_session(self):
        """Client connecting to unknown session should get ERROR."""
        reader = AsyncMock()
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)

        reader.readline = AsyncMock(return_value=b"SESSION unknown123 client\n")

        await relay_server.handle_connection(reader, writer)

        calls = writer.write.call_args_list
        assert any("ERROR" in str(call) for call in calls)
        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_invalid_protocol(self):
        """Invalid first line should get ERROR response."""
        reader = AsyncMock()
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)

        reader.readline = AsyncMock(return_value=b"INVALID COMMAND\n")

        await relay_server.handle_connection(reader, writer)

        calls = writer.write.call_args_list
        assert any("ERROR" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_reconnect_replaces_old(self):
        """Server reconnect should replace old session and send REGISTERED."""
        # Pre-register a session
        old_writer = MagicMock()
        old_writer.is_closing = MagicMock(return_value=False)
        old_writer.close = MagicMock()
        paired_event = asyncio.Event()
        async with relay_server.sessions_lock:
            relay_server.sessions["recon123"] = {
                "server_reader": AsyncMock(),
                "server_writer": old_writer,
                "registered_at": time.time(),
                "paired_event": paired_event,
                "client_reader": None,
                "client_writer": None,
            }

        new_reader = AsyncMock()
        new_writer = MagicMock()
        new_writer.write = MagicMock()
        new_writer.drain = AsyncMock()
        new_writer.close = MagicMock()
        new_writer.is_closing = MagicMock(return_value=False)

        new_reader.readline = AsyncMock(return_value=b"SESSION recon123 server\n")

        task = asyncio.create_task(relay_server.handle_connection(new_reader, new_writer))
        await asyncio.sleep(0.1)

        # Old writer should be closed
        old_writer.close.assert_called()
        # New writer should get REGISTERED
        calls = new_writer.write.call_args_list
        assert any(b"REGISTERED" in call.args[0] for call in calls)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_max_sessions(self):
        """Exceeding max sessions should get ERROR."""
        relay_server.MAX_SESSIONS = 0  # Set to 0 for testing

        reader = AsyncMock()
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)

        reader.readline = AsyncMock(return_value=b"SESSION new123 server\n")

        await relay_server.handle_connection(reader, writer)

        calls = writer.write.call_args_list
        assert any("ERROR max sessions" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_stale_cleanup(self):
        """Stale sessions should be cleaned up."""
        # Add a stale session
        async with relay_server.sessions_lock:
            relay_server.sessions["stale123"] = {
                "server_reader": AsyncMock(),
                "server_writer": MagicMock(is_closing=MagicMock(return_value=False),
                                           close=MagicMock()),
                "registered_at": time.time() - 7200,  # 2 hours ago
                "paired_event": asyncio.Event(),
                "client_reader": None,
                "client_writer": None,
            }

        # Run cleanup once (patch sleep to avoid waiting)
        with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
            try:
                await relay_server.cleanup_stale_sessions()
            except asyncio.CancelledError:
                pass

        assert "stale123" not in relay_server.sessions

    @pytest.mark.asyncio
    async def test_bidirectional_pipe(self):
        """Data should flow in both directions through pipe."""
        reader = AsyncMock()
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)

        # Simulate reading two chunks then EOF
        reader.read = AsyncMock(side_effect=[b"data1", b"data2", b""])

        await relay_server.pipe(reader, writer, "test")

        assert writer.write.call_count == 2
        writer.write.assert_any_call(b"data1")
        writer.write.assert_any_call(b"data2")

    @pytest.mark.asyncio
    async def test_pipe_handles_disconnect(self):
        """Pipe should handle disconnection gracefully."""
        reader = AsyncMock()
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)

        reader.read = AsyncMock(side_effect=ConnectionResetError())

        # Should not raise
        await relay_server.pipe(reader, writer, "test")


# ===========================================================================
# Server Reconnection Tests
# ===========================================================================


class TestServerReconnect:
    """Tests for relay server reconnection support."""

    @pytest.mark.asyncio
    async def test_reconnect_closes_old_client(self):
        """Reconnecting server should also close a paired client."""
        old_server_writer = MagicMock()
        old_server_writer.is_closing = MagicMock(return_value=False)
        old_server_writer.close = MagicMock()
        old_client_writer = MagicMock()
        old_client_writer.is_closing = MagicMock(return_value=False)
        old_client_writer.close = MagicMock()
        paired_event = asyncio.Event()
        paired_event.set()  # Already paired

        async with relay_server.sessions_lock:
            relay_server.sessions["paired789"] = {
                "server_reader": AsyncMock(),
                "server_writer": old_server_writer,
                "registered_at": time.time(),
                "paired_event": paired_event,
                "client_reader": AsyncMock(),
                "client_writer": old_client_writer,
            }

        new_reader = AsyncMock()
        new_writer = MagicMock()
        new_writer.write = MagicMock()
        new_writer.drain = AsyncMock()
        new_writer.close = MagicMock()
        new_writer.is_closing = MagicMock(return_value=False)

        # Simulate new server registering with same session ID
        task = asyncio.create_task(
            relay_server.handle_server_role("paired789", new_reader, new_writer)
        )
        await asyncio.sleep(0.1)

        # Both old connections should be closed
        old_server_writer.close.assert_called()
        old_client_writer.close.assert_called()
        # New server gets REGISTERED
        calls = new_writer.write.call_args_list
        assert any(b"REGISTERED" in call.args[0] for call in calls)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_superseded_handler_exits(self):
        """Old handler should exit cleanly when superseded by reconnection."""
        # Start first server handler
        reader1 = AsyncMock()
        writer1 = MagicMock()
        writer1.write = MagicMock()
        writer1.drain = AsyncMock()
        writer1.close = MagicMock()
        writer1.is_closing = MagicMock(return_value=False)

        task1 = asyncio.create_task(
            relay_server.handle_server_role("super123", reader1, writer1)
        )
        await asyncio.sleep(0.1)

        # Verify session is registered
        assert "super123" in relay_server.sessions

        # Reconnect with new server (same session ID)
        reader2 = AsyncMock()
        writer2 = MagicMock()
        writer2.write = MagicMock()
        writer2.drain = AsyncMock()
        writer2.close = MagicMock()
        writer2.is_closing = MagicMock(return_value=False)

        task2 = asyncio.create_task(
            relay_server.handle_server_role("super123", reader2, writer2)
        )
        await asyncio.sleep(0.1)

        # Old handler (task1) should have exited (writer1 closed)
        writer1.close.assert_called()

        # New handler is now waiting for client
        calls2 = writer2.write.call_args_list
        assert any(b"REGISTERED" in call.args[0] for call in calls2)

        task2.cancel()
        try:
            await task2
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_reconnect_max_sessions_bypass(self):
        """Reconnection should work even at max sessions (not counted as new)."""
        relay_server.MAX_SESSIONS = 1

        # Register one session
        paired_event = asyncio.Event()
        async with relay_server.sessions_lock:
            relay_server.sessions["maxtest"] = {
                "server_reader": AsyncMock(),
                "server_writer": MagicMock(is_closing=MagicMock(return_value=False),
                                           close=MagicMock()),
                "registered_at": time.time(),
                "paired_event": paired_event,
                "client_reader": None,
                "client_writer": None,
            }

        # Reconnect should still work (replaces, doesn't add)
        reader = AsyncMock()
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)

        task = asyncio.create_task(
            relay_server.handle_server_role("maxtest", reader, writer)
        )
        await asyncio.sleep(0.1)

        calls = writer.write.call_args_list
        assert any(b"REGISTERED" in call.args[0] for call in calls)
        # Should NOT get "ERROR max sessions"
        assert not any(b"ERROR" in call.args[0] for call in calls)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
