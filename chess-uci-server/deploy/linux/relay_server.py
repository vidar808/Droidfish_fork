"""Chess UCI Relay Server - TCP relay for NAT traversal.

Standalone asyncio TCP server deployable on any VPS. Pairs chess servers
and DroidFish clients that cannot connect directly (strict NAT, firewalls).

Protocol:
  Server role:  SESSION <id> server\n  ->  REGISTERED\n  ... PAIRED\n
  Client role:  SESSION <id> client\n  ->  CONNECTED\n
  After pairing, data is piped bidirectionally until either side disconnects.

Usage:
  python relay_server.py [--port 19000] [--max-sessions 100]

License: GPL-3.0
"""

import argparse
import asyncio
import logging
import time

# Session storage: session_id -> {server_reader, server_writer, registered_at, paired_event}
sessions = {}
sessions_lock = asyncio.Lock()

MAX_SESSIONS = 100
STALE_TIMEOUT = 3600  # 1 hour


async def pipe(reader, writer, label=""):
    """Pipe data from reader to writer until EOF or error."""
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
    except Exception as e:
        logging.debug(f"Pipe {label} error: {e}")
    finally:
        if not writer.is_closing():
            writer.close()


async def handle_server_role(session_id, reader, writer):
    """Handle a chess server registering with the relay.

    If a session with the same ID already exists (server reconnect), the old
    server and any paired client are closed, and the new server takes over.
    This supports persistent/deterministic session IDs across server restarts.
    """
    async with sessions_lock:
        if session_id in sessions:
            # Server reconnection: close old connections, replace session
            old = sessions[session_id]
            old_server_writer = old.get("server_writer")
            old_client_writer = old.get("client_writer")
            old_event = old.get("paired_event")

            # Close old server connection
            if old_server_writer and not old_server_writer.is_closing():
                old_server_writer.close()
            # Close old client connection if paired
            if old_client_writer and not old_client_writer.is_closing():
                old_client_writer.close()
            # Wake up old handler so it can exit cleanly
            if old_event and not old_event.is_set():
                old_event.set()

            logging.info(f"Session {session_id}: server reconnected (replaced old)")

        elif len(sessions) >= MAX_SESSIONS:
            writer.write(b"ERROR max sessions reached\n")
            await writer.drain()
            writer.close()
            return

        paired_event = asyncio.Event()
        sessions[session_id] = {
            "server_reader": reader,
            "server_writer": writer,
            "registered_at": time.time(),
            "paired_event": paired_event,
            "client_reader": None,
            "client_writer": None,
        }

    writer.write(b"REGISTERED\n")
    await writer.drain()
    logging.info(f"Session {session_id}: server registered")

    # Capture our own event reference for supersession detection
    my_event = paired_event

    # Wait for a client to pair
    try:
        await my_event.wait()
    except asyncio.CancelledError:
        async with sessions_lock:
            sessions.pop(session_id, None)
        writer.close()
        return

    # Check if we were superseded by a newer server reconnection
    async with sessions_lock:
        session = sessions.get(session_id)
        if not session or session["paired_event"] is not my_event:
            # Superseded: a newer server took over this session ID
            if not writer.is_closing():
                writer.close()
            return
        if not session["client_reader"]:
            sessions.pop(session_id, None)
            writer.close()
            return
        client_reader = session["client_reader"]
        client_writer = session["client_writer"]

    writer.write(b"PAIRED\n")
    await writer.drain()
    logging.info(f"Session {session_id}: paired, starting data relay")

    # Bidirectional pipe
    try:
        await asyncio.gather(
            pipe(reader, client_writer, f"{session_id} s->c"),
            pipe(client_reader, writer, f"{session_id} c->s"),
        )
    finally:
        async with sessions_lock:
            sessions.pop(session_id, None)
        for w in [writer, client_writer]:
            if not w.is_closing():
                w.close()
        logging.info(f"Session {session_id}: relay ended")


async def handle_client_role(session_id, reader, writer):
    """Handle a DroidFish client connecting via the relay."""
    async with sessions_lock:
        session = sessions.get(session_id)
        if not session:
            writer.write(b"ERROR unknown session\n")
            await writer.drain()
            writer.close()
            return

        session["client_reader"] = reader
        session["client_writer"] = writer

    writer.write(b"CONNECTED\n")
    await writer.drain()
    logging.info(f"Session {session_id}: client connected")

    # Signal the server that we're paired
    session["paired_event"].set()

    # The server handler does the actual piping; client just waits
    # until the connection ends (pipe handles cleanup)
    try:
        await asyncio.sleep(float("inf"))
    except asyncio.CancelledError:
        pass


async def handle_connection(reader, writer):
    """Dispatch incoming connection to server or client role."""
    peername = writer.get_extra_info("peername")
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=10)
        if not line:
            writer.close()
            return

        text = line.decode().strip()
        parts = text.split()

        if len(parts) != 3 or parts[0] != "SESSION":
            writer.write(b"ERROR invalid protocol\n")
            await writer.drain()
            writer.close()
            return

        session_id = parts[1]
        role = parts[2]

        if role == "server":
            await handle_server_role(session_id, reader, writer)
        elif role == "client":
            await handle_client_role(session_id, reader, writer)
        else:
            writer.write(b"ERROR invalid role\n")
            await writer.drain()
            writer.close()

    except asyncio.TimeoutError:
        logging.warning(f"Connection from {peername}: protocol timeout")
        writer.close()
    except Exception as e:
        logging.error(f"Connection from {peername} error: {e}")
        if not writer.is_closing():
            writer.close()


async def cleanup_stale_sessions():
    """Periodically remove sessions older than STALE_TIMEOUT."""
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        now = time.time()
        async with sessions_lock:
            stale = [
                sid for sid, s in sessions.items()
                if now - s["registered_at"] > STALE_TIMEOUT
            ]
            for sid in stale:
                session = sessions.pop(sid)
                for key in ["server_writer", "client_writer"]:
                    w = session.get(key)
                    if w and not w.is_closing():
                        w.close()
                logging.info(f"Session {sid}: cleaned up (stale)")


async def run_server(port, max_sessions):
    """Start the relay server."""
    global MAX_SESSIONS
    MAX_SESSIONS = max_sessions

    server = await asyncio.start_server(handle_connection, "0.0.0.0", port)
    addr = server.sockets[0].getsockname()
    logging.info(f"Relay server listening on {addr[0]}:{addr[1]} "
                 f"(max {max_sessions} sessions)")

    cleanup_task = asyncio.create_task(cleanup_stale_sessions())

    try:
        async with server:
            await server.serve_forever()
    finally:
        cleanup_task.cancel()


def main():
    parser = argparse.ArgumentParser(description="Chess UCI Relay Server")
    parser.add_argument("--port", type=int, default=19000,
                        help="TCP port to listen on (default: 19000)")
    parser.add_argument("--max-sessions", type=int, default=100,
                        help="Maximum concurrent sessions (default: 100)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    asyncio.run(run_server(args.port, args.max_sessions))


if __name__ == "__main__":
    main()
