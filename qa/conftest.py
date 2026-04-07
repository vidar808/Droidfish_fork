"""Shared pytest fixtures for the Chess UCI Server QA suite.

Provides reusable fixtures for spinning up servers, mock engines,
relay servers, and clients used across integration, e2e, stress,
and error test modules.
"""

import asyncio
import json
import os
import signal
import ssl
import subprocess
import sys
import tempfile
import time

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

QA_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(QA_DIR)
SERVER_SCRIPT = os.path.join(PROJECT_ROOT, "chess-uci-server", "deploy", "linux", "chess.py")
RELAY_SCRIPT = os.path.join(PROJECT_ROOT, "chess-uci-server", "deploy", "linux", "relay_server.py")
MOCK_ENGINE = os.path.join(QA_DIR, "fixtures", "mock_engine.py")
TEST_CERT = os.path.join(QA_DIR, "fixtures", "certs", "test.crt")
TEST_KEY = os.path.join(QA_DIR, "fixtures", "certs", "test.key")
ENGINE_DIR = os.path.join(PROJECT_ROOT, "chess-uci-server", "deploy", "linux", "engines")


# ---------------------------------------------------------------------------
# Helper: find a free port
# ---------------------------------------------------------------------------

def _free_port():
    """Find an available TCP port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def free_port():
    """Return a free TCP port number."""
    return _free_port()


@pytest.fixture
def mock_engine_path():
    """Path to the mock UCI engine script."""
    return MOCK_ENGINE


@pytest.fixture
def mock_engine_executable(tmp_path):
    """Create an executable mock engine wrapper script.

    Returns the path to a shell script that invokes mock_engine.py.
    This is needed because the server expects an executable path.
    """
    wrapper = tmp_path / "mock_engine"
    wrapper.write_text(
        f"#!/bin/sh\nexec {sys.executable} {MOCK_ENGINE} \"$@\"\n"
    )
    wrapper.chmod(0o755)
    return str(wrapper)


@pytest.fixture
def mock_engine_executable_hang(tmp_path):
    """Mock engine that never sends uciok (for timeout tests)."""
    wrapper = tmp_path / "mock_engine_hang"
    wrapper.write_text(
        f"#!/bin/sh\nexec {sys.executable} {MOCK_ENGINE} --hang \"$@\"\n"
    )
    wrapper.chmod(0o755)
    return str(wrapper)


@pytest.fixture
def mock_engine_executable_crash(tmp_path):
    """Mock engine that crashes on 'uci' (for crash tests)."""
    wrapper = tmp_path / "mock_engine_crash"
    wrapper.write_text(
        f"#!/bin/sh\nexec {sys.executable} {MOCK_ENGINE} --crash \"$@\"\n"
    )
    wrapper.chmod(0o755)
    return str(wrapper)


@pytest.fixture
def base_config(mock_engine_executable, free_port):
    """Return a minimal valid server config dict using the mock engine."""
    return {
        "host": "127.0.0.1",
        "engines": {
            "MockEngine": {
                "path": mock_engine_executable,
                "port": free_port,
            }
        },
        "max_connections": 5,
        "trusted_sources": ["127.0.0.1"],
        "trusted_subnets": ["127.0.0.0/8"],
        "enable_trusted_sources": True,
        "enable_auto_trust": False,
        "enable_server_log": False,
        "enable_uci_log": False,
        "enable_tls": False,
        "auth_token": "",
        "auth_method": "none",
        "psk_key": "",
        "enable_mdns": False,
        "enable_upnp": False,
        "enable_firewall_rules": False,
        "session_keepalive_timeout": 0,
        "info_throttle_ms": 0,
        "base_port": free_port,
        "enable_single_port": False,
        "inactivity_timeout": 900,
        "heartbeat_time": 300,
        "watchdog_timer_interval": 300,
        "pid_file": "test-server.pid",
        "base_log_dir": "",
        "relay_server_url": "",
        "default_engine": "MockEngine",
    }


@pytest.fixture
def tls_config(base_config):
    """Config with TLS enabled using test certificates."""
    base_config["enable_tls"] = True
    base_config["tls_cert_path"] = TEST_CERT
    base_config["tls_key_path"] = TEST_KEY
    return base_config


@pytest.fixture
def auth_token_config(base_config):
    """Config with token authentication enabled."""
    base_config["auth_method"] = "token"
    base_config["auth_token"] = "test_token_abc123"
    return base_config


@pytest.fixture
def auth_psk_config(base_config):
    """Config with PSK authentication enabled."""
    base_config["auth_method"] = "psk"
    base_config["psk_key"] = "test_psk_key_xyz789"
    return base_config


@pytest.fixture
def multiplex_config(mock_engine_executable, free_port):
    """Config for single-port multiplexed mode with two engines."""
    # Create a second mock engine wrapper with a different name
    return {
        "host": "127.0.0.1",
        "engines": {
            "Engine_A": {
                "path": mock_engine_executable,
                "port": free_port,
            },
            "Engine_B": {
                "path": mock_engine_executable,
                "port": free_port + 1,
            },
        },
        "max_connections": 5,
        "trusted_sources": ["127.0.0.1"],
        "trusted_subnets": ["127.0.0.0/8"],
        "enable_trusted_sources": True,
        "enable_auto_trust": False,
        "enable_server_log": False,
        "enable_uci_log": False,
        "enable_tls": False,
        "auth_token": "",
        "auth_method": "none",
        "psk_key": "",
        "enable_mdns": False,
        "enable_upnp": False,
        "enable_firewall_rules": False,
        "session_keepalive_timeout": 0,
        "info_throttle_ms": 0,
        "base_port": free_port,
        "enable_single_port": True,
        "inactivity_timeout": 900,
        "heartbeat_time": 300,
        "watchdog_timer_interval": 300,
        "pid_file": "test-server.pid",
        "base_log_dir": "",
        "relay_server_url": "",
        "default_engine": "Engine_A",
    }


# ---------------------------------------------------------------------------
# Server process fixture
# ---------------------------------------------------------------------------

def _write_config_file(config, tmp_path):
    """Write a config dict to a temp JSON file and return the path."""
    config_path = os.path.join(str(tmp_path), "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    return config_path


@pytest.fixture
async def run_server(tmp_path):
    """Fixture that starts a chess UCI server with a given config.

    Usage:
        server_proc = await run_server(config)
        # ... tests ...
        # server is automatically cleaned up
    """
    procs = []

    async def _start(config, extra_args=None):
        config_path = _write_config_file(config, tmp_path)
        cmd = [sys.executable, SERVER_SCRIPT]
        if extra_args:
            cmd.extend(extra_args)

        # Patch: set config path via env or write to cwd
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        # The server reads config.json from cwd, so we set cwd to tmp_path
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(tmp_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        procs.append(proc)

        # Wait for server to be ready (listen on port)
        port = config.get("base_port", 9998)
        if not config.get("enable_single_port", False):
            engine = next(iter(config.get("engines", {}).values()), {})
            port = engine.get("port", port)

        # Server startup can be slow due to WAN IP lookup (get_wan_ip tries
        # up to 3 URLs with 3s timeout each), so allow up to 30s.
        await _wait_for_port("127.0.0.1", port, timeout=30, proc=proc)
        return proc

    yield _start

    for proc in procs:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()


async def _wait_for_port(host, port, timeout=30, proc=None):
    """Wait until a TCP port is accepting connections.

    If proc is provided, checks whether the process has exited early
    (indicating a startup error) to fail fast instead of waiting.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Fail fast if server process died
        if proc is not None and proc.returncode is not None:
            stdout = ""
            try:
                out = await asyncio.wait_for(proc.stdout.read(8192), timeout=2)
                stdout = out.decode(errors="replace")
            except Exception:
                pass
            raise RuntimeError(
                f"Server process exited with code {proc.returncode} "
                f"before listening on port {port}.\nOutput:\n{stdout}"
            )
        try:
            r, w = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=1
            )
            w.close()
            await w.wait_closed()
            return
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
            await asyncio.sleep(0.2)
    raise TimeoutError(f"Port {host}:{port} not ready within {timeout}s")


@pytest.fixture
async def run_relay(tmp_path):
    """Fixture that starts a relay server."""
    procs = []

    async def _start(port, max_sessions=100):
        proc = await asyncio.create_subprocess_exec(
            sys.executable, RELAY_SCRIPT,
            "--port", str(port),
            "--max-sessions", str(max_sessions),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        procs.append(proc)
        await _wait_for_port("127.0.0.1", port, timeout=10, proc=proc)
        return proc

    yield _start

    for proc in procs:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()


# ---------------------------------------------------------------------------
# Import chess.py functions for direct unit-style integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
def chess_module():
    """Import the chess.py server module for direct function access."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("chess_server", SERVER_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# pytest configuration
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "tls: marks tests requiring TLS")
    config.addinivalue_line("markers", "relay: marks tests requiring relay server")
    config.addinivalue_line("markers", "engine: marks tests that validate real engines")
