"""End-to-end tests for the relay server.

Uses raw asyncio connections (not MockClient) since the relay uses its own
SESSION-based protocol, not UCI.
"""

import asyncio

import pytest


pytestmark = pytest.mark.relay


async def _relay_connect(port):
    """Open a raw TCP connection to the relay server."""
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection("127.0.0.1", port), timeout=5
    )
    return reader, writer


async def _send_line(writer, text):
    """Send a line to the relay."""
    writer.write(f"{text}\n".encode())
    await writer.drain()


async def _recv_line(reader, timeout=5):
    """Read a single line from the relay."""
    data = await asyncio.wait_for(reader.readline(), timeout=timeout)
    if not data:
        return None
    return data.decode().strip()


async def _close(writer):
    """Close a writer safely."""
    if not writer.is_closing():
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError):
            pass


async def test_relay_server_register_and_pair(run_relay, free_port):
    """Register as server, then connect as client, verify REGISTERED/CONNECTED/PAIRED."""
    await run_relay(free_port)

    session_id = "test_session_001"

    # Server role registers
    s_reader, s_writer = await _relay_connect(free_port)
    await _send_line(s_writer, f"SESSION {session_id} server")
    response = await _recv_line(s_reader)
    assert response == "REGISTERED", f"Expected REGISTERED, got: {response}"

    # Client role connects
    c_reader, c_writer = await _relay_connect(free_port)
    await _send_line(c_writer, f"SESSION {session_id} client")
    client_response = await _recv_line(c_reader)
    assert client_response == "CONNECTED", f"Expected CONNECTED, got: {client_response}"

    # Server should receive PAIRED
    paired_response = await _recv_line(s_reader, timeout=5)
    assert paired_response == "PAIRED", f"Expected PAIRED, got: {paired_response}"

    await _close(s_writer)
    await _close(c_writer)


async def test_relay_data_passthrough(run_relay, free_port):
    """After pairing, verify data passes bidirectionally through the relay."""
    await run_relay(free_port)

    session_id = "test_session_data"

    # Register server
    s_reader, s_writer = await _relay_connect(free_port)
    await _send_line(s_writer, f"SESSION {session_id} server")
    assert await _recv_line(s_reader) == "REGISTERED"

    # Connect client
    c_reader, c_writer = await _relay_connect(free_port)
    await _send_line(c_writer, f"SESSION {session_id} client")
    assert await _recv_line(c_reader) == "CONNECTED"
    assert await _recv_line(s_reader) == "PAIRED"

    # Send data from client to server
    await _send_line(c_writer, "hello from client")
    server_received = await _recv_line(s_reader, timeout=5)
    assert server_received == "hello from client", \
        f"Server should receive client data, got: {server_received}"

    # Send data from server to client
    await _send_line(s_writer, "hello from server")
    client_received = await _recv_line(c_reader, timeout=5)
    assert client_received == "hello from server", \
        f"Client should receive server data, got: {client_received}"

    await _close(s_writer)
    await _close(c_writer)


async def test_relay_unknown_session(run_relay, free_port):
    """Connect as client with non-existent session ID, verify ERROR response."""
    await run_relay(free_port)

    c_reader, c_writer = await _relay_connect(free_port)
    await _send_line(c_writer, "SESSION nonexistent_session client")
    response = await _recv_line(c_reader, timeout=5)
    assert response is not None and "ERROR" in response, \
        f"Expected ERROR for unknown session, got: {response}"

    await _close(c_writer)


async def test_relay_server_reconnect(run_relay, free_port):
    """Register a session, then register again with same ID, verify old session replaced."""
    await run_relay(free_port)

    session_id = "test_session_reconnect"

    # First server registers
    s1_reader, s1_writer = await _relay_connect(free_port)
    await _send_line(s1_writer, f"SESSION {session_id} server")
    response1 = await _recv_line(s1_reader)
    assert response1 == "REGISTERED"

    # Second server registers with same session ID
    s2_reader, s2_writer = await _relay_connect(free_port)
    await _send_line(s2_writer, f"SESSION {session_id} server")
    response2 = await _recv_line(s2_reader)
    assert response2 == "REGISTERED", f"Expected REGISTERED for reconnect, got: {response2}"

    # Now a client should pair with the second server, not the first
    c_reader, c_writer = await _relay_connect(free_port)
    await _send_line(c_writer, f"SESSION {session_id} client")
    client_resp = await _recv_line(c_reader, timeout=5)
    assert client_resp == "CONNECTED"

    # Second server should get PAIRED
    paired = await _recv_line(s2_reader, timeout=5)
    assert paired == "PAIRED", f"Expected new server to get PAIRED, got: {paired}"

    # Verify data flows through the new server
    await _send_line(c_writer, "test data")
    received = await _recv_line(s2_reader, timeout=5)
    assert received == "test data"

    await _close(s1_writer)
    await _close(s2_writer)
    await _close(c_writer)
