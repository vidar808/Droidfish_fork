"""TCP client helper for testing the chess UCI server.

Provides a simple async client that can connect, authenticate, and exchange
UCI commands with the server - used by integration and e2e tests.
"""

import asyncio
import ssl
import os


class MockClient:
    """Async TCP client for testing chess UCI server interactions."""

    def __init__(self, host="127.0.0.1", port=9998, use_tls=False,
                 tls_cert=None, verify_ssl=False):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.tls_cert = tls_cert
        self.verify_ssl = verify_ssl
        self.reader = None
        self.writer = None

    async def connect(self, timeout=5):
        """Open a TCP connection to the server."""
        ssl_ctx = None
        if self.use_tls:
            ssl_ctx = ssl.create_default_context()
            if not self.verify_ssl:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
            elif self.tls_cert:
                ssl_ctx.load_verify_locations(self.tls_cert)

        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port, ssl=ssl_ctx),
            timeout=timeout,
        )

    async def close(self):
        """Close the connection."""
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError, ssl.SSLError):
                pass

    async def send(self, message):
        """Send a line to the server."""
        self.writer.write(f"{message}\n".encode())
        await self.writer.drain()

    async def recv_line(self, timeout=5):
        """Read a single line from the server."""
        data = await asyncio.wait_for(self.reader.readline(), timeout=timeout)
        if not data:
            return None
        return data.decode().strip()

    async def recv_until(self, marker, timeout=10):
        """Read lines until one contains `marker`. Returns all lines read."""
        lines = []
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError(
                    f"Timed out waiting for '{marker}'. Got: {lines}")
            line = await self.recv_line(timeout=remaining)
            if line is None:
                raise ConnectionError(
                    f"Connection closed before '{marker}'. Got: {lines}")
            lines.append(line)
            if marker in line:
                return lines

    async def authenticate_token(self, token, timeout=5):
        """Perform token-based authentication handshake.

        Returns True if AUTH_OK received.
        """
        line = await self.recv_line(timeout=timeout)
        if not line or not line.startswith("AUTH_REQUIRED"):
            return False
        await self.send(f"AUTH {token}")
        result = await self.recv_line(timeout=timeout)
        return result == "AUTH_OK"

    async def authenticate_psk(self, psk_key, timeout=5):
        """Perform PSK authentication handshake."""
        line = await self.recv_line(timeout=timeout)
        if not line or not line.startswith("AUTH_REQUIRED"):
            return False
        await self.send(f"PSK_AUTH {psk_key}")
        result = await self.recv_line(timeout=timeout)
        return result == "AUTH_OK"

    async def select_engine(self, engine_name, timeout=5):
        """Perform engine selection on a multiplex server.

        Sends ENGINE_LIST, reads the list, sends SELECT_ENGINE.
        Returns list of available engine names.
        """
        await self.send("ENGINE_LIST")
        engines = []
        while True:
            line = await self.recv_line(timeout=timeout)
            if line is None:
                break
            if line == "ENGINES_END":
                break
            if line.startswith("ENGINE "):
                engines.append(line[7:])

        await self.send(f"SELECT_ENGINE {engine_name}")
        result = await self.recv_line(timeout=timeout)
        if result != "ENGINE_SELECTED":
            raise RuntimeError(f"Engine selection failed: {result}")
        return engines

    async def uci_handshake(self, timeout=10):
        """Wait for UCI initialization (id lines + uciok).

        The server auto-sends 'uci' to the engine on connect, so the client
        just needs to read until uciok.
        Returns dict with 'name', 'author', 'options' parsed from response.
        """
        info = {"name": None, "author": None, "options": []}
        lines = await self.recv_until("uciok", timeout=timeout)
        for line in lines:
            if line.startswith("id name "):
                info["name"] = line[8:]
            elif line.startswith("id author "):
                info["author"] = line[10:]
            elif line.startswith("option "):
                info["options"].append(line)
        return info

    async def go_and_wait(self, depth=5, timeout=30):
        """Send position + go and wait for bestmove.

        Returns (bestmove_line, info_lines).
        """
        await self.send("position startpos")
        await self.send(f"go depth {depth}")
        info_lines = []
        while True:
            line = await self.recv_line(timeout=timeout)
            if line is None:
                raise ConnectionError("Connection closed before bestmove")
            if line.startswith("bestmove"):
                return line, info_lines
            info_lines.append(line)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()
