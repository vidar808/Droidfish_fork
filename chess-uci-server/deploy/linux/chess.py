"""Chess UCI Server - Network bridge for UCI chess engines.

Provides a TCP server that proxies UCI protocol between network clients
(such as DroidFish) and local chess engine processes.

License: GPL-3.0 (compatible with DroidFish)
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import platform
import secrets
import signal
import socket
import ssl
import stat
import subprocess
import sys
import time
import ipaddress
import re
from concurrent.futures import ProcessPoolExecutor

# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

REQUIRED_CONFIG_KEYS = {
    "host": str,
    "engines": dict,
    "max_connections": int,
    "trusted_sources": list,
    "trusted_subnets": list,
}

OPTIONAL_CONFIG_DEFAULTS = {
    "base_log_dir": "",
    "display_uci_communication": False,
    "enable_trusted_sources": True,
    "enable_auto_trust": False,
    "enable_server_log": True,
    "enable_uci_log": False,
    "detailed_log_verbosity": False,
    "enable_firewall_rules": False,
    "enable_firewall_subnet_blocking": False,
    "enable_firewall_ip_blocking": False,
    "max_connection_attempts": 5,
    "connection_attempt_period": 3600,
    "enable_subnet_connection_attempt_blocking": False,
    "max_connection_attempts_from_untrusted_subnet": 10,
    "Log_untrusted_connection_attempts": True,
    "inactivity_timeout": 900,
    "heartbeat_time": 300,
    "watchdog_timer_interval": 300,
    "custom_variables": {},
    "enable_tls": False,
    "tls_cert_path": "",
    "tls_key_path": "",
    "auth_token": "",
    "auth_method": "token",
    "psk_key": "",
    "session_keepalive_timeout": 0,
    "info_throttle_ms": 0,
    "enable_mdns": False,
    "engine_directory": "",
    "base_port": 9998,
    "enable_upnp": True,
    "upnp_lease_duration": 3600,
    "relay_server_url": "",
    "relay_server_port": 19000,
    "server_secret": "",
    "pid_file": "chess-uci-server.pid",
    "enable_single_port": False,
    "default_engine": "",
}

# Default relay server for NAT traversal (used by setup wizard and installers)
DEFAULT_RELAY_URL = "spacetosurf.com"
DEFAULT_RELAY_PORT = 19000


def derive_session_id(server_secret, engine_name):
    """Derive a deterministic relay session ID from server secret and engine name.

    Returns a 24-char hex string (matching existing token_hex(12) format).
    Same inputs always produce the same output; unpredictable without the secret.
    """
    return hmac.new(
        server_secret.encode(), engine_name.encode(), hashlib.sha256
    ).hexdigest()[:24]


def ensure_server_secret(config, config_path="config.json"):
    """Ensure config has a persistent server_secret, generating one if needed.

    If the secret is empty or too short (<32 chars), generates a new 64-hex-char
    secret and writes it back to the config file.

    Returns the secret string.
    """
    secret = config.get("server_secret", "")
    if not secret or len(secret) < 32:
        secret = secrets.token_hex(32)
        config["server_secret"] = secret
        write_config(config, config_path)
        logging.info("Generated new server_secret and saved to config")
    return secret


def validate_config(config):
    """Validate config.json has required keys with correct types.

    Returns list of error strings (empty if valid).
    """
    errors = []

    for key, expected_type in REQUIRED_CONFIG_KEYS.items():
        if key not in config:
            errors.append(f"Missing required config key: '{key}'")
        elif not isinstance(config[key], expected_type):
            errors.append(
                f"Config key '{key}' must be {expected_type.__name__}, "
                f"got {type(config[key]).__name__}"
            )

    # Apply defaults for optional keys
    for key, default in OPTIONAL_CONFIG_DEFAULTS.items():
        if key not in config:
            config[key] = default

    # Validate engines have required sub-keys
    engines = config.get("engines", {})
    if isinstance(engines, dict):
        seen_ports = {}
        for name, details in engines.items():
            if not isinstance(details, dict):
                errors.append(f"Engine '{name}' must be a dict, got {type(details).__name__}")
                continue
            if "path" not in details:
                errors.append(f"Engine '{name}' missing required key 'path'")
            else:
                path = details["path"]
                if path and not os.path.isfile(path):
                    errors.append(f"Engine '{name}' path does not exist: '{path}'")
                elif path and not os.access(path, os.X_OK):
                    errors.append(f"Engine '{name}' path is not executable: '{path}'")
            if "port" not in details:
                errors.append(f"Engine '{name}' missing required key 'port'")
            elif not isinstance(details["port"], int):
                errors.append(f"Engine '{name}' port must be int, got {type(details['port']).__name__}")
            else:
                port = details["port"]
                if port in seen_ports:
                    errors.append(
                        f"Port conflict: engines '{seen_ports[port]}' and '{name}' "
                        f"both use port {port}"
                    )
                seen_ports[port] = name

    # Validate trusted_sources are valid IPs
    for ip in config.get("trusted_sources", []):
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            errors.append(f"Invalid IP in trusted_sources: '{ip}'")

    # Validate trusted_subnets are valid CIDR
    for subnet in config.get("trusted_subnets", []):
        try:
            ipaddress.ip_network(subnet, strict=False)
        except ValueError:
            errors.append(f"Invalid subnet in trusted_subnets: '{subnet}'")

    # Validate numeric ranges (only if type is correct)
    max_conn = config.get("max_connections", 1)
    if isinstance(max_conn, int) and max_conn < 1:
        errors.append("max_connections must be >= 1")
    inact_timeout = config.get("inactivity_timeout", 1)
    if isinstance(inact_timeout, (int, float)) and inact_timeout < 0:
        errors.append("inactivity_timeout must be >= 0")

    # Validate TLS config
    if config.get("enable_tls", False):
        cert_path = config.get("tls_cert_path", "")
        key_path = config.get("tls_key_path", "")
        if not cert_path:
            errors.append("enable_tls is true but tls_cert_path is empty")
        elif not os.path.isfile(cert_path):
            errors.append(f"TLS certificate not found: '{cert_path}'")
        if not key_path:
            errors.append("enable_tls is true but tls_key_path is empty")
        elif not os.path.isfile(key_path):
            errors.append(f"TLS key not found: '{key_path}'")

    # Validate server_secret if explicitly set
    secret = config.get("server_secret", "")
    if secret:
        if not isinstance(secret, str):
            errors.append("server_secret must be a string")
        elif len(secret) < 32:
            errors.append("server_secret must be at least 32 characters")

    # Validate default_engine if set (must exist in engines dict)
    default_engine = config.get("default_engine", "")
    if default_engine and isinstance(engines, dict) and default_engine not in engines:
        errors.append(f"default_engine '{default_engine}' not found in engines")

    return errors


def load_config(path="config.json"):
    """Load and validate configuration from JSON file."""
    try:
        with open(path) as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {path}")
        print("Create a config.json file (see example_config.json for reference)")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {path}: {e}")
        sys.exit(1)

    errors = validate_config(config)
    if errors:
        print(f"ERROR: Invalid configuration in {path}:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    return config


# ---------------------------------------------------------------------------
# Deferred config loading - initialized by _init_from_config() before server
# starts, so CLI commands like --setup don't need a pre-existing config.json.
# ---------------------------------------------------------------------------

config = None
HOST = ""
BASE_LOG_DIR = ""
ENGINES = {}
CUSTOM_VARIABLES = {}
MAX_CONNECTIONS = 1

# Shared state with async lock protection
connection_attempts = {}
subnet_connection_attempts = {}
connection_lock = asyncio.Lock()

# Auto-trusted IPs (runtime additions when enable_auto_trust is active)
auto_trusted_ips = set()


def _init_from_config(cfg):
    """Initialize module globals from a loaded config dict."""
    global config, HOST, BASE_LOG_DIR, ENGINES, CUSTOM_VARIABLES, MAX_CONNECTIONS
    config = cfg
    HOST = cfg["host"]
    BASE_LOG_DIR = cfg.get("base_log_dir", "")
    ENGINES = cfg["engines"]
    CUSTOM_VARIABLES = cfg.get("custom_variables", {})
    MAX_CONNECTIONS = cfg["max_connections"]

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def setup_logging(config):
    """Configure logging based on config settings."""
    handlers = [logging.StreamHandler()]

    base_dir = config.get("base_log_dir", "")
    if config["enable_server_log"]:
        if not base_dir:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            try:
                os.makedirs(base_dir, exist_ok=True)
            except (FileNotFoundError, PermissionError) as e:
                print(f"Warning: Cannot create log dir '{base_dir}': {e}. Using script dir.")
                base_dir = os.path.dirname(os.path.abspath(__file__))

        try:
            handlers.append(logging.FileHandler(os.path.join(base_dir, "server.log")))
        except Exception as e:
            print(f"Warning: Cannot create server.log: {e}")

    # Use force=True so logging config takes effect even if a library
    # (e.g. zeroconf, asyncio) already attached a default handler.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )
    if config["enable_server_log"] and base_dir:
        log_path = os.path.join(base_dir, "server.log")
        print(f"  Logging to: {log_path}")
    return base_dir


# ---------------------------------------------------------------------------
# Firewall abstraction (cross-platform)
# ---------------------------------------------------------------------------


class FirewallBackend:
    """Base class for firewall operations. Subclass per platform."""

    async def block_ip(self, ip_address, ports):
        pass

    async def block_subnet(self, subnet, ports):
        pass

    async def unblock_trusted(self, trusted_ips, trusted_subnets):
        pass

    async def configure(self, config):
        pass


class WindowsFirewall(FirewallBackend):
    """Windows firewall backend using netsh (async subprocess)."""

    async def _run_netsh(self, args):
        """Run a netsh command asynchronously (never blocks event loop)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "netsh", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, stdout.decode(), stderr.decode()
        except FileNotFoundError:
            logging.warning("netsh not found - firewall operations unavailable")
            return 1, "", "netsh not found"

    async def block_ip(self, ip_address, ports):
        if not ipaddress.ip_address(ip_address).is_global:
            logging.warning(f"Skipping blocking of non-global IP: {ip_address}")
            return

        rc, stdout, stderr = await self._run_netsh(
            ["advfirewall", "firewall", "show", "rule", "name=Chess-Block-IPs"]
        )

        if rc == 0:
            existing_ips = re.findall(r"RemoteIP:\s*(.*)", stdout)
            if existing_ips:
                existing_ips = existing_ips[0].split(",")
                if ip_address in existing_ips:
                    logging.info(f"IP {ip_address} already blocked")
                    return
            else:
                existing_ips = []

            updated = ",".join(existing_ips + [ip_address])
            rc2, _, stderr2 = await self._run_netsh(
                ["advfirewall", "firewall", "set", "rule", "name=Chess-Block-IPs",
                 "new", f"remoteip={updated}"]
            )
            if rc2 != 0:
                logging.error(f"Failed to update Chess-Block-IPs: {stderr2}")
            else:
                logging.info(f"Added {ip_address} to Chess-Block-IPs")
        else:
            rc2, _, stderr2 = await self._run_netsh(
                ["advfirewall", "firewall", "add", "rule", "name=Chess-Block-IPs",
                 "dir=in", "action=block", "protocol=TCP", f"localport={ports}",
                 f"remoteip={ip_address}", "enable=yes"]
            )
            if rc2 != 0:
                logging.error(f"Failed to create block rule for {ip_address}: {stderr2}")
            else:
                logging.info(f"Created Chess-Block-IPs rule for {ip_address}")

    async def block_subnet(self, subnet, ports):
        if not ipaddress.ip_network(subnet, strict=False).is_global:
            logging.warning(f"Skipping blocking of non-global subnet: {subnet}")
            return

        rc, stdout, stderr = await self._run_netsh(
            ["advfirewall", "firewall", "show", "rule", "name=Chess-Block-Other"]
        )

        if rc == 0:
            existing = re.findall(r"RemoteIP:\s*(.*)", stdout)
            if existing:
                existing = existing[0].split(",")
                if subnet in existing:
                    logging.info(f"Subnet {subnet} already blocked")
                    return
            else:
                existing = []

            updated = ",".join(existing + [subnet])
            rc2, _, stderr2 = await self._run_netsh(
                ["advfirewall", "firewall", "set", "rule", "name=Chess-Block-Other",
                 "new", f"remoteip={updated}"]
            )
            if rc2 != 0:
                logging.error(f"Failed to update Chess-Block-Other: {stderr2}")
            else:
                logging.info(f"Added {subnet} to Chess-Block-Other")
        else:
            rc2, _, stderr2 = await self._run_netsh(
                ["advfirewall", "firewall", "add", "rule", "name=Chess-Block-Other",
                 "dir=in", "action=block", "protocol=TCP", f"localport={ports}",
                 f"remoteip={subnet}", "enable=yes"]
            )
            if rc2 != 0:
                logging.error(f"Failed to create block rule for {subnet}: {stderr2}")
            else:
                logging.info(f"Created Chess-Block-Other rule for {subnet}")

    async def unblock_trusted(self, trusted_ips, trusted_subnets):
        rc, stdout, _ = await self._run_netsh(
            ["advfirewall", "firewall", "show", "rule", "name=Chess-Block-IPs"]
        )
        if rc == 0:
            existing = re.findall(r"RemoteIP:\s*(.*)", stdout)
            if existing:
                existing = existing[0].split(",")
                updated = [ip for ip in existing if ip not in trusted_ips]
                if len(updated) < len(existing):
                    await self._run_netsh(
                        ["advfirewall", "firewall", "set", "rule", "name=Chess-Block-IPs",
                         "new", f"remoteip={','.join(updated)}"]
                    )
                    logging.info("Removed trusted IPs from Chess-Block-IPs")

        rc, stdout, _ = await self._run_netsh(
            ["advfirewall", "firewall", "show", "rule", "name=Chess-Block-Other"]
        )
        if rc == 0:
            existing = re.findall(r"RemoteIP:\s*(.*)", stdout)
            if existing:
                existing = existing[0].split(",")
                updated = [
                    s for s in existing
                    if not any(
                        ipaddress.ip_network(s, strict=False).subnet_of(
                            ipaddress.ip_network(ts, strict=False)
                        )
                        for ts in trusted_subnets
                    )
                ]
                if len(updated) < len(existing):
                    await self._run_netsh(
                        ["advfirewall", "firewall", "set", "rule", "name=Chess-Block-Other",
                         "new", f"remoteip={','.join(updated)}"]
                    )
                    logging.info("Removed trusted subnets from Chess-Block-Other")

    async def configure(self, config):
        if not config.get("enable_firewall_subnet_blocking", False):
            return

        ports = ",".join(str(e["port"]) for e in config["engines"].values())
        ip_avoid = config["trusted_sources"]
        subnet_avoid = config["trusted_subnets"]

        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor() as pool:
            subnets_to_block = await loop.run_in_executor(
                pool, generate_subnets_to_avoid, ip_avoid, subnet_avoid
            )

        await self._run_netsh(
            ["advfirewall", "firewall", "delete", "rule", "name=Chess-Block-Other"]
        )

        combined = ",".join(subnets_to_block)
        rc, _, stderr = await self._run_netsh(
            ["advfirewall", "firewall", "add", "rule", "name=Chess-Block-Other",
             "dir=in", "action=block", "protocol=TCP", f"localport={ports}",
             f"remoteip={combined}", "enable=yes"]
        )
        if rc != 0:
            logging.error(f"Failed to add subnet block rule: {stderr}")
        else:
            logging.info(f"Blocked subnets on ports {ports}")


class NoopFirewall(FirewallBackend):
    """No-op firewall backend for Linux/macOS or when firewall is disabled."""

    async def block_ip(self, ip_address, ports):
        logging.info(f"Firewall noop: would block IP {ip_address}")

    async def block_subnet(self, subnet, ports):
        logging.info(f"Firewall noop: would block subnet {subnet}")


def get_firewall_backend(config):
    """Select firewall backend based on platform and config."""
    if not config.get("enable_firewall_rules", False):
        return NoopFirewall()
    if platform.system() == "Windows":
        return WindowsFirewall()
    logging.warning(
        "Firewall rules enabled but platform is %s (not Windows). "
        "Firewall operations will be no-ops.", platform.system()
    )
    return NoopFirewall()


# ---------------------------------------------------------------------------
# PID file management
# ---------------------------------------------------------------------------


def write_pid_file(path):
    """Write current process PID to file."""
    with open(path, "w") as f:
        f.write(str(os.getpid()))


def read_pid_file(path):
    """Read PID from file. Returns int PID or None."""
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def remove_pid_file(path):
    """Delete PID file if it exists."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def is_process_alive(pid):
    """Check if a process with the given PID is running (cross-platform)."""
    if platform.system() == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # Process exists but we can't signal it


def stop_server(pid_path):
    """Stop a running server by PID file. Sends SIGTERM, waits, force-kills."""
    pid = read_pid_file(pid_path)
    if pid is None:
        print(f"No PID file found at {pid_path}")
        return False

    if not is_process_alive(pid):
        print(f"Process {pid} is not running (stale PID file)")
        remove_pid_file(pid_path)
        return False

    print(f"Stopping server (PID {pid})...")
    if platform.system() == "Windows":
        try:
            import ctypes
            PROCESS_TERMINATE = 0x0001
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if handle:
                kernel32.TerminateProcess(handle, 1)
                kernel32.CloseHandle(handle)
        except Exception as e:
            print(f"Failed to terminate process: {e}")
            return False
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            print(f"Process {pid} already exited")
            remove_pid_file(pid_path)
            return True

    # Wait up to 5 seconds for graceful exit
    for _ in range(50):
        if not is_process_alive(pid):
            break
        time.sleep(0.1)

    if is_process_alive(pid):
        print(f"Process {pid} did not exit gracefully, force-killing...")
        if platform.system() != "Windows":
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    remove_pid_file(pid_path)
    print("Server stopped")
    return True


# ---------------------------------------------------------------------------
# Engine registry (explicit + auto-discovered)
# ---------------------------------------------------------------------------

ALL_ENGINES = {}


def build_engine_registry(cfg):
    """Build merged engine registry from explicit config + auto-discovered.

    Explicit engines from config take precedence. Auto-discovered engines
    from engine_directory are added with ports starting after the highest
    explicit port.
    """
    global ALL_ENGINES
    ALL_ENGINES = dict(cfg.get("engines", {}))

    engine_dir = cfg.get("engine_directory", "")
    if engine_dir:
        discovered = discover_engines(engine_dir)
        if discovered:
            # Find the highest port already in use
            existing_ports = [d["port"] for d in ALL_ENGINES.values()
                              if isinstance(d, dict) and "port" in d]
            base = cfg.get("base_port", 9998)
            next_port = max(existing_ports + [base - 1]) + 1

            for name, path in discovered:
                if name not in ALL_ENGINES:
                    ALL_ENGINES[name] = {"path": path, "port": next_port}
                    logging.info(f"Auto-discovered engine: {name} -> port {next_port}")
                    next_port += 1

    # Resolve default engine
    default_name = cfg.get("default_engine", "")
    if default_name and default_name not in ALL_ENGINES:
        logging.warning(f"default_engine '{default_name}' not found in registry")
    if not default_name and ALL_ENGINES:
        cfg["default_engine"] = next(iter(ALL_ENGINES))

    return ALL_ENGINES


# ---------------------------------------------------------------------------
# Port availability helpers
# ---------------------------------------------------------------------------


def find_available_port(host, preferred_port, max_attempts=100, exclude=None):
    """Find an available TCP port starting from preferred_port.

    Skips ports in the exclude set. Returns the available port.
    Raises OSError if no port found within max_attempts.
    """
    if exclude is None:
        exclude = set()
    for offset in range(max_attempts):
        port = preferred_port + offset
        if port in exclude:
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, port))
                return port
        except OSError:
            continue
    raise OSError(
        f"No available port found in range "
        f"{preferred_port}-{preferred_port + max_attempts - 1}"
    )


def resolve_ports(host, config):
    """Resolve configured ports to available ones. Updates config and ALL_ENGINES in-place."""
    claimed = set()
    single_port = config.get("enable_single_port", False)

    if single_port:
        preferred = config.get("base_port", 9998)
        actual = find_available_port(host, preferred, exclude=claimed)
        if actual != preferred:
            logging.info(f"Port {preferred} in use, using port {actual}")
        config["base_port"] = actual
        claimed.add(actual)
    else:
        for name in sorted(ALL_ENGINES.keys()):
            details = ALL_ENGINES[name]
            if not isinstance(details, dict) or "port" not in details:
                continue
            preferred = details["port"]
            actual = find_available_port(host, preferred, exclude=claimed)
            if actual != preferred:
                logging.info(f"Port {preferred} for {name} in use, using port {actual}")
            details["port"] = actual
            claimed.add(actual)


def _prepare_engine_registry():
    """Build engine registry and resolve ports for CLI commands."""
    build_engine_registry(config)
    resolve_ports(HOST, config)


# ---------------------------------------------------------------------------
# UPnP port mapping
# ---------------------------------------------------------------------------


def _upnp_map_sync(internal_port, internal_ip, description, lease_duration):
    """Synchronous UPnP port mapping using miniupnpc.

    Tries the requested port first, then internal_port + 10000 as fallback.
    Returns (external_ip, external_port) or (None, None).
    """
    try:
        import miniupnpc
    except ImportError:
        logging.info("miniupnpc not installed - UPnP port mapping unavailable. "
                     "Install with: pip install miniupnpc")
        return None, None

    u = miniupnpc.UPnP()
    u.discoverdelay = 2000
    try:
        devices = u.discover()
        if devices == 0:
            logging.warning("UPnP: No IGD devices found")
            return None, None

        u.selectigd()
        external_ip = u.externalipaddress()

        # Try mapping the same external port first
        for ext_port in [internal_port, internal_port + 10000]:
            try:
                result = u.addportmapping(
                    ext_port, 'TCP', internal_ip, internal_port,
                    description, '', lease_duration
                )
                if result:
                    logging.info(f"UPnP: Mapped {internal_ip}:{internal_port} -> "
                                 f"{external_ip}:{ext_port} (lease {lease_duration}s)")
                    return external_ip, ext_port
            except Exception as e:
                logging.debug(f"UPnP: Port {ext_port} mapping failed: {e}")
                continue

        logging.warning(f"UPnP: Could not map port {internal_port}")
        return None, None
    except Exception as e:
        logging.warning(f"UPnP: Discovery/mapping error: {e}")
        return None, None


async def try_upnp_mapping(internal_port, internal_ip, description, lease_duration):
    """Async wrapper for UPnP port mapping (runs sync code in executor)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _upnp_map_sync, internal_port, internal_ip, description, lease_duration
    )


async def upnp_renewal_task(mappings, config):
    """Periodically renew UPnP port mappings.

    Runs at half the lease duration to prevent mappings from expiring.
    mappings: dict of engine_name -> (internal_port, internal_ip, description)
    """
    lease_duration = config.get("upnp_lease_duration", 3600)
    renewal_interval = lease_duration / 2

    while True:
        await asyncio.sleep(renewal_interval)
        for engine_name, (port, ip, desc) in mappings.items():
            ext_ip, ext_port = await try_upnp_mapping(port, ip, desc, lease_duration)
            if ext_ip:
                logging.info(f"UPnP: Renewed mapping for {engine_name}")
            else:
                logging.warning(f"UPnP: Renewal failed for {engine_name}")


# ---------------------------------------------------------------------------
# External IP detection
# ---------------------------------------------------------------------------


async def get_external_ip():
    """Get the machine's public/external IP address via ipify API.

    Returns IP string or None on failure.
    """
    import urllib.request

    loop = asyncio.get_running_loop()

    def _fetch():
        try:
            req = urllib.request.Request("https://api.ipify.org", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                ip = resp.read().decode().strip()
                # Validate it looks like an IP
                ipaddress.ip_address(ip)
                return ip
        except Exception as e:
            logging.debug(f"External IP lookup failed: {e}")
            return None

    return await loop.run_in_executor(None, _fetch)


# ---------------------------------------------------------------------------
# Subnet computation (CPU-bound, runs in ProcessPoolExecutor)
# ---------------------------------------------------------------------------


def generate_subnets_to_avoid(ip_addresses_to_avoid, subnets_to_avoid):
    """Compute public IP subnets excluding trusted ranges. CPU-bound."""
    ip_addresses_to_avoid = [ipaddress.ip_network(ip + '/32') for ip in ip_addresses_to_avoid]
    subnets_to_avoid = [ipaddress.ip_network(subnet) for subnet in subnets_to_avoid]

    public_ranges = [
        ipaddress.ip_network('1.0.0.0/8'),
        ipaddress.ip_network('2.0.0.0/7'),
        ipaddress.ip_network('4.0.0.0/6'),
        ipaddress.ip_network('8.0.0.0/7'),
        ipaddress.ip_network('11.0.0.0/8'),
        ipaddress.ip_network('12.0.0.0/6'),
        ipaddress.ip_network('16.0.0.0/4'),
        ipaddress.ip_network('32.0.0.0/3'),
        ipaddress.ip_network('64.0.0.0/2'),
        ipaddress.ip_network('128.0.0.0/2'),
        ipaddress.ip_network('192.0.0.0/9'),
        ipaddress.ip_network('208.0.0.0/4'),
        ipaddress.ip_network('224.0.0.0/3'),
    ]

    addresses_to_exclude = ip_addresses_to_avoid + subnets_to_avoid
    subnets_to_use = []
    for public_range in public_ranges:
        current_ranges = [public_range]
        for address_to_exclude in addresses_to_exclude:
            new_ranges = []
            for current_range in current_ranges:
                try:
                    excluded = current_range.address_exclude(address_to_exclude)
                    new_ranges.extend(excluded)
                except ValueError:
                    new_ranges.append(current_range)
            current_ranges = new_ranges
        subnets_to_use.extend(current_ranges)

    return [str(subnet) for subnet in subnets_to_use]


# ---------------------------------------------------------------------------
# Heartbeat (valid UCI keepalive)
# ---------------------------------------------------------------------------


async def heartbeat(writer, engine_process, interval):
    """Send periodic isready keepalive to engine (valid UCI command).

    Unlike the previous \\nping\\n approach, isready is a standard UCI
    command that every UCI engine must respond to with readyok.
    The readyok response is forwarded to the client naturally through
    the engine response handler.
    """
    while True:
        try:
            await asyncio.sleep(interval)
            # Send isready to engine - a valid UCI keepalive
            engine_process.stdin.write(b"isready\n")
            await engine_process.stdin.drain()
        except Exception as e:
            logging.debug(f"Heartbeat stopped: {e}")
            break


# ---------------------------------------------------------------------------
# Watchdog timer
# ---------------------------------------------------------------------------


async def watchdog_timer(interval):
    """Periodic health check log message."""
    while True:
        await asyncio.sleep(interval)
        logging.info("Watchdog timer: Server is responsive")


# ---------------------------------------------------------------------------
# Trust verification (with async lock)
# ---------------------------------------------------------------------------


def is_trusted(client_ip, config):
    """Check if an IP is trusted (static config or auto-trusted)."""
    if client_ip in config["trusted_sources"]:
        return True
    if client_ip in auto_trusted_ips:
        return True
    if any(
        ipaddress.ip_address(client_ip) in ipaddress.ip_network(subnet, strict=False)
        for subnet in config["trusted_subnets"]
    ):
        return True
    return False


async def check_connection_attempts(client_ip, config, firewall):
    """Track and act on connection attempts from untrusted IPs.

    Uses async lock to protect shared state.
    """
    if is_trusted(client_ip, config):
        return

    async with connection_lock:
        current_time = time.time()
        period = config["connection_attempt_period"]

        # Clean expired entries
        expired = [
            ip for ip, attempts in connection_attempts.items()
            if current_time - attempts[-1] > period
        ]
        for ip in expired:
            del connection_attempts[ip]

        if client_ip not in connection_attempts:
            connection_attempts[client_ip] = []
        connection_attempts[client_ip].append(current_time)

        attempt_count = len(connection_attempts[client_ip])

    # Log outside lock
    if config["Log_untrusted_connection_attempts"]:
        log_msg = f"Untrusted connection attempt from {client_ip}. Count: {attempt_count}"
        logging.warning(log_msg)
        try:
            log_dir = config.get("base_log_dir") or os.path.dirname(os.path.abspath(__file__))
            log_path = os.path.join(log_dir, "untrusted_connection_attempts.log")
            with open(log_path, "a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {log_msg}\n")
        except OSError as e:
            logging.error(f"Failed to write untrusted log: {e}")

    # Check thresholds
    if attempt_count > config["max_connection_attempts"]:
        if config["enable_firewall_ip_blocking"]:
            logging.warning(f"Blocking IP {client_ip} due to excessive attempts")
            ports = ",".join(str(e["port"]) for e in ENGINES.values())
            await firewall.block_ip(client_ip, ports)

        async with connection_lock:
            connection_attempts.pop(client_ip, None)

    # Subnet tracking
    subnet = str(ipaddress.ip_network(f"{client_ip}/24", strict=False))
    async with connection_lock:
        if subnet not in subnet_connection_attempts:
            subnet_connection_attempts[subnet] = []
        subnet_connection_attempts[subnet].append(time.time())
        subnet_count = len(subnet_connection_attempts[subnet])

    if subnet_count > config["max_connection_attempts_from_untrusted_subnet"]:
        if config["enable_subnet_connection_attempt_blocking"]:
            logging.warning(f"Blocking subnet {subnet} due to excessive attempts")
            ports = ",".join(str(e["port"]) for e in ENGINES.values())
            await firewall.block_subnet(subnet, ports)

        async with connection_lock:
            subnet_connection_attempts.pop(subnet, None)


# ---------------------------------------------------------------------------
# Auto-trust implementation
# ---------------------------------------------------------------------------


async def handle_auto_trust(client_ip, config):
    """Auto-trust: add IP to runtime trusted set after first successful connection.

    SECURITY WARNING: Auto-trust is convenient for initial setup but should
    be disabled in production. Any IP that connects will be permanently
    trusted for the server's lifetime. Use only on private networks.
    """
    if not config.get("enable_auto_trust", False):
        return

    if client_ip in auto_trusted_ips:
        return

    auto_trusted_ips.add(client_ip)
    logging.warning(
        f"AUTO-TRUST: IP {client_ip} added to trusted set. "
        f"Disable 'enable_auto_trust' in config for production use."
    )


# ---------------------------------------------------------------------------
# TLS support
# ---------------------------------------------------------------------------


def create_ssl_context(config):
    """Create an SSL context for TLS-encrypted connections.

    Returns an ssl.SSLContext if TLS is enabled and configured, else None.
    Supports self-signed certificates (clients must trust the CA or disable
    verification on their end).
    """
    if not config.get("enable_tls", False):
        return None

    cert_path = config["tls_cert_path"]
    key_path = config["tls_key_path"]

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    except (ssl.SSLError, OSError) as e:
        logging.error(f"Failed to load TLS certificate/key: {e}")
        logging.error("Server will start WITHOUT TLS encryption.")
        return None

    logging.info("TLS enabled with cert: %s", cert_path)
    return ctx


# ---------------------------------------------------------------------------
# Token authentication
# ---------------------------------------------------------------------------


async def authenticate_client(reader, writer, config):
    """Perform token-based authentication handshake.

    Protocol:
      1. Server sends: AUTH_REQUIRED\\n
      2. Client sends: AUTH <token>\\n
      3. Server sends: AUTH_OK\\n  or  AUTH_FAIL\\n

    Returns True if auth succeeds (or auth not configured).
    """
    token = config.get("auth_token", "")
    if not token:
        return True  # No auth configured

    try:
        writer.write(b"AUTH_REQUIRED\n")
        await writer.drain()

        data = await asyncio.wait_for(reader.readline(), timeout=10)
        if not data:
            return False

        client_msg = data.decode().strip()
        if client_msg.startswith("AUTH ") and client_msg[5:] == token:
            writer.write(b"AUTH_OK\n")
            await writer.drain()
            return True
        else:
            writer.write(b"AUTH_FAIL\n")
            await writer.drain()
            return False
    except asyncio.TimeoutError:
        logging.warning("Auth timeout - client did not respond")
        return False
    except Exception as e:
        logging.error(f"Auth error: {e}")
        return False


# ---------------------------------------------------------------------------
# Session Manager (keeps engine alive between disconnects)
# ---------------------------------------------------------------------------


class SessionManager:
    """Manages engine process sessions across client disconnects.

    When a client disconnects, the engine process is kept alive for up to
    session_keepalive_timeout seconds. If a new client connects before the
    timeout, it reattaches to the warm engine (preserving hash tables, etc.).
    """

    def __init__(self):
        self._sessions = {}  # engine_name -> {process, expiry_task, last_position}
        self._lock = asyncio.Lock()

    async def get_or_create(self, engine_name, engine_path, config):
        """Get an existing warm session or create a new engine process."""
        async with self._lock:
            if engine_name in self._sessions:
                session = self._sessions[engine_name]
                if session["expiry_task"] is not None:
                    session["expiry_task"].cancel()
                    session["expiry_task"] = None
                proc = session["process"]
                if proc.returncode is None:  # Still alive
                    logging.info(f"Reattaching to warm engine session: {engine_name}")
                    return proc, True  # True = reattached
                else:
                    del self._sessions[engine_name]

        # Create new engine process
        engine_dir = os.path.dirname(engine_path)
        proc = await asyncio.create_subprocess_exec(
            engine_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=engine_dir,
        )
        async with self._lock:
            self._sessions[engine_name] = {
                "process": proc,
                "expiry_task": None,
                "last_position": None,
            }
        return proc, False

    async def release(self, engine_name, config):
        """Release an engine session. Keeps it alive if keepalive > 0."""
        keepalive = config.get("session_keepalive_timeout", 0)
        if keepalive <= 0:
            await self._terminate(engine_name)
            return

        async with self._lock:
            if engine_name not in self._sessions:
                return
            session = self._sessions[engine_name]
            logging.info(
                f"Engine {engine_name} released. Keeping alive for {keepalive}s"
            )
            session["expiry_task"] = asyncio.create_task(
                self._expire_session(engine_name, keepalive)
            )

    async def _expire_session(self, engine_name, timeout):
        """Terminate engine after timeout if no client reattaches."""
        await asyncio.sleep(timeout)
        logging.info(f"Session keepalive expired for {engine_name}")
        await self._terminate(engine_name)

    async def _terminate(self, engine_name):
        """Terminate an engine process and remove from sessions."""
        async with self._lock:
            session = self._sessions.pop(engine_name, None)
        if session and session["process"].returncode is None:
            try:
                session["process"].stdin.write(b"quit\n")
                await session["process"].stdin.drain()
                session["process"].terminate()
                await session["process"].wait()
            except (ProcessLookupError, BrokenPipeError, OSError):
                pass

    async def shutdown_all(self):
        """Terminate all active sessions."""
        async with self._lock:
            names = list(self._sessions.keys())
        for name in names:
            await self._terminate(name)


# Global session manager
session_manager = SessionManager()


# ---------------------------------------------------------------------------
# Output Throttler (rate-limits info lines to client)
# ---------------------------------------------------------------------------


class OutputThrottler:
    """Rate-limits UCI info lines sent to the client.

    Only forwards info lines every throttle_ms milliseconds, unless the
    depth changes or it's a non-info line (bestmove, readyok, etc.).
    When throttle_ms is 0, all lines pass through unfiltered.
    """

    def __init__(self, throttle_ms):
        self.throttle_ms = throttle_ms
        self.last_send_time = 0
        self.last_depth = None
        self.pending_info = None

    def should_forward(self, line):
        """Returns True if this line should be forwarded to the client."""
        if self.throttle_ms <= 0:
            return True

        # Always forward non-info lines immediately
        if not line.startswith("info "):
            # Flush any pending info before non-info lines
            self.pending_info = None
            return True

        # Check if depth changed
        current_depth = self._extract_depth(line)
        if current_depth is not None and current_depth != self.last_depth:
            self.last_depth = current_depth
            self.last_send_time = time.time() * 1000
            self.pending_info = None
            return True

        # Time-based throttle
        now = time.time() * 1000
        if now - self.last_send_time >= self.throttle_ms:
            self.last_send_time = now
            self.pending_info = None
            return True

        # Store as pending (will be sent when next allowed)
        self.pending_info = line
        return False

    def _extract_depth(self, line):
        """Extract 'depth N' value from UCI info string."""
        parts = line.split()
        for i, part in enumerate(parts):
            if part == "depth" and i + 1 < len(parts):
                try:
                    return int(parts[i + 1])
                except ValueError:
                    pass
        return None


# ---------------------------------------------------------------------------
# Client handler
# ---------------------------------------------------------------------------


async def client_handler(reader, writer, engine_path, log_file, engine_name,
                         config, firewall):
    """Handle a single client connection."""
    peername = writer.get_extra_info('peername')
    client_ip = peername[0] if peername else "unknown"
    logging.info(f"Connection opened from {client_ip}")

    # Trust check (with auto-trust support)
    if config.get("enable_trusted_sources", False):
        if not is_trusted(client_ip, config):
            # If auto-trust enabled, trust this IP going forward
            if config.get("enable_auto_trust", False):
                await handle_auto_trust(client_ip, config)
            else:
                logging.warning(f"Rejected untrusted connection from {client_ip}")
                await check_connection_attempts(client_ip, config, firewall)
                writer.close()
                return

    # Authentication (after trust check, before engine spawn)
    auth_method = config.get("auth_method", "token")
    has_auth = (auth_method != "none" and
                (config.get("auth_token", "") or config.get("psk_key", "")))
    if has_auth:
        if not await authenticate_client_multi(reader, writer, config):
            logging.warning(f"Auth failed for {client_ip}")
            writer.close()
            return
        logging.info(f"Auth succeeded for {client_ip}")

    inactivity_timeout = config.get("inactivity_timeout", 900)
    heartbeat_interval = config.get("heartbeat_time", 300)
    last_activity_time = time.time()

    async def check_inactivity():
        nonlocal last_activity_time
        while True:
            await asyncio.sleep(60)
            if time.time() - last_activity_time > inactivity_timeout:
                logging.warning(f"Connection to {client_ip} closed due to inactivity")
                writer.close()
                return

    inactivity_task = asyncio.create_task(check_inactivity())
    heartbeat_task = None
    engine_process = None
    sem = asyncio.Semaphore(MAX_CONNECTIONS)

    async with sem:
        reattached = False
        try:
            logging.info(f"Starting engine {engine_name} for {client_ip}")

            # Use session manager if keepalive is configured
            keepalive = config.get("session_keepalive_timeout", 0)
            if keepalive > 0:
                engine_process, reattached = await session_manager.get_or_create(
                    engine_name, engine_path, config
                )
            else:
                engine_dir = os.path.dirname(engine_path)
                engine_process = await asyncio.create_subprocess_exec(
                    engine_path,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=engine_dir,
                )

            # Start heartbeat (sends isready to engine, not ping to client)
            heartbeat_task = asyncio.create_task(
                heartbeat(writer, engine_process, heartbeat_interval)
            )

            # Output throttler
            throttle_ms = config.get("info_throttle_ms", 0)
            throttler = OutputThrottler(throttle_ms)

            async def process_command(command):
                """Send a command to the engine process."""
                try:
                    engine_process.stdin.write(f"{command}\n".encode())
                    await engine_process.stdin.drain()
                    if config["enable_uci_log"]:
                        with open(log_file, "a") as f:
                            f.write(f"Client: {command}\n")
                    if config["detailed_log_verbosity"]:
                        logging.debug(f"Client -> Engine: {command}")
                except Exception as e:
                    logging.error(f"Error sending to engine: {e}")

            # UCI initialization
            await process_command("uci")

            # Send per-engine custom variables
            for opt_name, opt_value in ALL_ENGINES.get(engine_name, {}).get("custom_variables", {}).items():
                await process_command(f"setoption name {opt_name} value {opt_value}")

            # Read until uciok (with 30-second timeout to avoid hanging on
            # broken engines that never respond, which would block the relay)
            UCIOK_TIMEOUT = 30
            got_uciok = False
            while True:
                try:
                    data = await asyncio.wait_for(
                        engine_process.stdout.readline(), timeout=UCIOK_TIMEOUT)
                except asyncio.TimeoutError:
                    logging.error(f"Engine {engine_name} did not send uciok within "
                                  f"{UCIOK_TIMEOUT}s (path: {engine_path}) — killing")
                    try:
                        engine_process.kill()
                    except Exception:
                        pass
                    writer.close()
                    return
                if not data:
                    break
                decoded = data.decode().strip()
                writer.write(data)
                await writer.drain()
                if config["enable_uci_log"]:
                    with open(log_file, "a") as f:
                        f.write(f"Engine: {decoded}\n")
                if config["detailed_log_verbosity"]:
                    logging.debug(f"Engine -> Client: {decoded}")
                if "uciok" in decoded:
                    got_uciok = True
                    break

            if not got_uciok:
                rc = engine_process.returncode
                logging.error(f"Engine {engine_name} exited before uciok "
                              f"(exit code: {rc}, path: {engine_path})")
                writer.close()
                return

            async def process_client_commands():
                nonlocal last_activity_time
                while True:
                    try:
                        data = await asyncio.wait_for(reader.readline(), timeout=60)
                        if not data:
                            break

                        last_activity_time = time.time()
                        client_data = data.decode().strip()
                        commands = client_data.split('\n')

                        for command in commands:
                            command = command.strip()
                            if not command:
                                continue

                            if command.startswith('setoption name'):
                                parts = command.split(' ')
                                if len(parts) >= 5 and parts[1] == 'name' and parts[3] == 'value':
                                    opt_name = parts[2]
                                    opt_value = ' '.join(parts[4:])
                                    engine_customs = ALL_ENGINES.get(engine_name, {}).get("custom_variables", {})

                                    if opt_name in engine_customs:
                                        if engine_customs[opt_name] == "override":
                                            await process_command(command)
                                        else:
                                            modified = f"setoption name {opt_name} value {engine_customs[opt_name]}"
                                            await process_command(modified)
                                    elif opt_name in CUSTOM_VARIABLES:
                                        modified = f"setoption name {opt_name} value {CUSTOM_VARIABLES[opt_name]}"
                                        await process_command(modified)
                                    else:
                                        await process_command(command)
                                else:
                                    await process_command(command)
                            else:
                                await process_command(command)

                    except asyncio.TimeoutError:
                        continue  # Timeout is normal, keep waiting
                    except ConnectionResetError:
                        logging.warning(f"Connection reset from {client_ip}")
                        break
                    except Exception as e:
                        logging.error(f"Error processing client command from {client_ip}: {e}")
                        break

            async def process_engine_responses():
                while True:
                    try:
                        data = await asyncio.wait_for(
                            engine_process.stdout.readline(), timeout=60
                        )
                        if not data:
                            break
                        decoded = data.decode().strip()
                        # Apply output throttling
                        if throttler.should_forward(decoded):
                            writer.write(data)
                            await writer.drain()
                        if config["enable_uci_log"]:
                            with open(log_file, "a") as f:
                                f.write(f"Engine: {decoded}\n")
                        if config["detailed_log_verbosity"]:
                            logging.debug(f"Engine -> Client: {decoded}")
                    except asyncio.TimeoutError:
                        continue  # Timeout is normal for engine responses
                    except ConnectionResetError:
                        logging.warning(f"Connection reset while sending to {client_ip}")
                        break
                    except Exception as e:
                        logging.error(f"Engine response error for {client_ip}: {e}")
                        break

            await asyncio.gather(
                process_client_commands(),
                process_engine_responses(),
            )

        except ConnectionResetError:
            logging.warning(f"Client {client_ip} disconnected")
        except asyncio.IncompleteReadError:
            logging.warning(f"Incomplete read from {client_ip}")
        except asyncio.TimeoutError:
            logging.warning(f"Connection timeout for {client_ip}")
        except Exception as e:
            logging.error(f"Error in client_handler for {client_ip}: {e}")
        finally:
            inactivity_task.cancel()
            if heartbeat_task:
                heartbeat_task.cancel()
            if engine_process:
                keepalive = config.get("session_keepalive_timeout", 0)
                if keepalive > 0:
                    await session_manager.release(engine_name, config)
                else:
                    try:
                        engine_process.terminate()
                        await engine_process.wait()
                    except ProcessLookupError:
                        pass
            if not writer.is_closing():
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionResetError, BrokenPipeError):
                    pass
            logging.info(f"Connection closed for {client_ip}")


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


async def start_server(host, port, engine_path, log_file, engine_name,
                       config, firewall, ssl_ctx=None):
    """Start a TCP server for a single engine."""
    retries = 5
    while retries > 0:
        try:
            server = await asyncio.start_server(
                lambda r, w: client_handler(
                    r, w, engine_path, log_file, engine_name, config, firewall
                ),
                host, port,
                ssl=ssl_ctx,
            )
            addr = server.sockets[0].getsockname()
            tls_status = " (TLS)" if ssl_ctx else ""
            logging.info(f"Listening on {addr[0]}:{addr[1]} for engine {engine_name}{tls_status}")

            async with server:
                await server.serve_forever()
            break
        except asyncio.CancelledError:
            logging.info(f"Server for {engine_name} shutting down")
            break
        except Exception as e:
            retries -= 1
            logging.error(f"Error starting server for {engine_name}: {e}")
            if retries > 0:
                logging.info("Retrying in 5 seconds...")
                await asyncio.sleep(5)
            else:
                logging.error(f"Max retries reached for {engine_name}")
                break


async def multiplex_handler(reader, writer, config, firewall, ssl_ctx=None):
    """Handle a client on the single-port multiplexed server.

    Performs trust check + auth, then engine negotiation:
    - If client sends ENGINE_LIST: respond with available engines, wait for SELECT_ENGINE
    - If client sends anything else (e.g. 'uci'): use default engine

    Then delegates to client_handler() with the resolved engine.
    """
    peername = writer.get_extra_info('peername')
    client_ip = peername[0] if peername else "unknown"

    # Trust check
    if config.get("enable_trusted_sources", False):
        if not is_trusted(client_ip, config):
            if config.get("enable_auto_trust", False):
                await handle_auto_trust(client_ip, config)
            else:
                logging.warning(f"Multiplex: Rejected untrusted connection from {client_ip}")
                await check_connection_attempts(client_ip, config, firewall)
                writer.close()
                return

    # Authentication
    auth_method = config.get("auth_method", "token")
    has_auth = (auth_method != "none" and
                (config.get("auth_token", "") or config.get("psk_key", "")))
    if has_auth:
        if not await authenticate_client_multi(reader, writer, config):
            logging.warning(f"Multiplex: Auth failed for {client_ip}")
            writer.close()
            return

    # Engine negotiation: read first line
    try:
        data = await asyncio.wait_for(reader.readline(), timeout=30)
        if not data:
            writer.close()
            return
        first_line = data.decode().strip()
    except asyncio.TimeoutError:
        logging.warning(f"Multiplex: Timeout waiting for first command from {client_ip}")
        writer.close()
        return

    engine_name = config.get("default_engine", "")
    if not engine_name and ALL_ENGINES:
        engine_name = next(iter(ALL_ENGINES))

    if first_line == "ENGINE_LIST":
        # Send sorted engine list
        for name in sorted(ALL_ENGINES.keys()):
            writer.write(f"ENGINE {name}\n".encode())
        writer.write(b"ENGINES_END\n")
        await writer.drain()

        # Wait for SELECT_ENGINE
        try:
            sel_data = await asyncio.wait_for(reader.readline(), timeout=30)
            if not sel_data:
                writer.close()
                return
            sel_line = sel_data.decode().strip()
        except asyncio.TimeoutError:
            writer.close()
            return

        if sel_line.startswith("SELECT_ENGINE "):
            requested = sel_line[len("SELECT_ENGINE "):]
            if requested in ALL_ENGINES:
                engine_name = requested
                writer.write(b"ENGINE_SELECTED\n")
                await writer.drain()
                logging.info(f"Multiplex: {client_ip} selected engine '{engine_name}'")
            else:
                writer.write(f"ENGINE_ERROR unknown engine\n".encode())
                await writer.drain()
                logging.warning(f"Multiplex: {client_ip} requested unknown engine '{requested}'")
                writer.close()
                return
        else:
            # Not a SELECT_ENGINE command — treat as default engine + first UCI command
            # We consumed the line, but client_handler sends its own 'uci' at line 1125
            logging.info(f"Multiplex: {client_ip} sent '{sel_line}' instead of SELECT_ENGINE, "
                         f"using default engine '{engine_name}'")
    else:
        # Old client or immediate UCI — use default engine
        # The first_line (likely 'uci') was consumed; client_handler will send its own
        logging.info(f"Multiplex: {client_ip} using default engine '{engine_name}' "
                     f"(first line: '{first_line}')")

    if engine_name not in ALL_ENGINES:
        logging.error(f"Multiplex: No engine available for {client_ip}")
        writer.close()
        return

    details = ALL_ENGINES[engine_name]
    base_log_dir = config.get("base_log_dir", "") or os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(base_log_dir, f"communication_log_{engine_name}.txt")

    # Delegate to client_handler (trust/auth already done, so we skip those in client_handler
    # by passing config with enable_trusted_sources=False for this invocation)
    inner_config = dict(config)
    inner_config["enable_trusted_sources"] = False
    inner_config["auth_token"] = ""
    inner_config["psk_key"] = ""
    inner_config["auth_method"] = "none"

    await client_handler(reader, writer, details["path"], log_file,
                         engine_name, inner_config, firewall)


async def start_multiplex_server(host, port, config, firewall, ssl_ctx=None):
    """Start a single-port server that multiplexes all engines."""
    retries = 5
    while retries > 0:
        try:
            server = await asyncio.start_server(
                lambda r, w: multiplex_handler(r, w, config, firewall, ssl_ctx),
                host, port,
                ssl=ssl_ctx,
            )
            addr = server.sockets[0].getsockname()
            tls_status = " (TLS)" if ssl_ctx else ""
            engine_count = len(ALL_ENGINES)
            logging.info(
                f"Single-port server listening on {addr[0]}:{addr[1]}{tls_status} "
                f"({engine_count} engines available)"
            )

            async with server:
                await server.serve_forever()
            break
        except asyncio.CancelledError:
            logging.info("Single-port server shutting down")
            break
        except Exception as e:
            retries -= 1
            logging.error(f"Error starting single-port server: {e}")
            if retries > 0:
                logging.info("Retrying in 5 seconds...")
                await asyncio.sleep(5)
            else:
                logging.error("Max retries reached for single-port server")
                break


async def relay_listener(engine_name, engine_path, log_file, config, firewall,
                         relay_host, relay_port, session_id, ssl_ctx=None):
    """Connect to relay server as the 'server' role, bridging clients to the engine.

    Registers with the relay using SESSION <id> server, waits for a client
    to connect via the relay, then passes the relay reader/writer to the
    appropriate handler for transparent UCI proxying.

    For single-port mode (engine_name="_multiplex"), delegates to
    multiplex_handler() which handles ENGINE_LIST/SELECT_ENGINE negotiation.
    For per-engine mode, delegates directly to client_handler().

    Reconnects automatically after each client disconnects or on errors.

    A keepalive timeout (RELAY_KEEPALIVE_SEC) ensures the relay connection is
    refreshed periodically even when no clients connect.  Without this, idle
    TCP connections are silently dropped by NAT/firewalls (typically 30-60 min)
    and the server never learns the session is dead.
    """
    RELAY_KEEPALIVE_SEC = 300  # 5 minutes — reconnect if no client pairs
    is_multiplex = (engine_name == "_multiplex")
    while True:
        try:
            logging.info(f"Relay: Connecting to {relay_host}:{relay_port} "
                         f"for {engine_name} (session {session_id})")
            reader, writer = await asyncio.open_connection(relay_host, relay_port)

            # Register as server role
            writer.write(f"SESSION {session_id} server\n".encode())
            await writer.drain()

            # Wait for REGISTERED
            response = await asyncio.wait_for(reader.readline(), timeout=10)
            if not response:
                raise ConnectionError("Relay closed connection during registration")
            resp_text = response.decode().strip()
            if resp_text.startswith("ERROR"):
                raise ConnectionError(f"Relay registration failed: {resp_text}")
            if resp_text != "REGISTERED":
                raise ConnectionError(f"Unexpected relay response: {resp_text}")

            logging.info(f"Relay: Registered session {session_id} for {engine_name}")

            # Wait for PAIRED (client connected), with keepalive timeout.
            # If no client pairs within RELAY_KEEPALIVE_SEC, disconnect and
            # re-register to refresh the TCP connection (prevents NAT/firewall
            # from silently dropping the idle connection).
            try:
                paired = await asyncio.wait_for(
                    reader.readline(), timeout=RELAY_KEEPALIVE_SEC)
            except asyncio.TimeoutError:
                logging.info(f"Relay: Keepalive timeout ({RELAY_KEEPALIVE_SEC}s) "
                             f"for {engine_name}, reconnecting")
                writer.close()
                continue
            if not paired:
                raise ConnectionError("Relay closed connection while waiting for client")
            paired_text = paired.decode().strip()
            if paired_text != "PAIRED":
                raise ConnectionError(f"Unexpected relay paired response: {paired_text}")

            logging.info(f"Relay: Client paired for {engine_name} via relay")

            # Hand off to the appropriate handler.
            # Bypass IP trust checks — peername is the relay server, not
            # the actual client.  Session-ID already authenticates the link.
            relay_config = dict(config)
            relay_config["enable_trusted_sources"] = False
            if is_multiplex:
                await multiplex_handler(reader, writer, relay_config, firewall, ssl_ctx)
            else:
                await client_handler(reader, writer, engine_path, log_file,
                                     engine_name, relay_config, firewall)

            logging.info(f"Relay: Client disconnected from {engine_name}")

        except asyncio.CancelledError:
            logging.info(f"Relay: Listener cancelled for {engine_name}")
            break
        except (ConnectionError, OSError) as e:
            logging.warning(f"Relay: Error for {engine_name}: {e}. Retrying in 10s...")
            await asyncio.sleep(10)
        except Exception as e:
            logging.error(f"Relay: Unexpected error for {engine_name}: {e}. Retrying in 10s...")
            await asyncio.sleep(10)


def log_startup_summary(config, upnp_results, relay_sessions, zc, mdns_services):
    """Log a boxed connectivity summary at server startup."""
    host_ip = get_local_ip()
    single_port = config.get("enable_single_port", False)
    base_port = config.get("base_port", 9998)

    # LAN info
    if single_port:
        lan_str = f"{host_ip}:{base_port} (single-port)"
    else:
        ports = sorted(set(d["port"] for d in ALL_ENGINES.values()))
        if len(ports) == 1:
            lan_str = f"{host_ip}:{ports[0]}"
        else:
            lan_str = f"{host_ip}:{ports[0]}-{ports[-1]} ({len(ports)} ports)"

    # mDNS status
    if zc and mdns_services:
        mdns_str = f"ACTIVE ({len(mdns_services)} service{'s' if len(mdns_services) != 1 else ''} advertised)"
    elif config.get("enable_mdns", False):
        mdns_str = "FAILED (zeroconf unavailable)"
    else:
        mdns_str = "disabled"

    # UPnP status
    if upnp_results:
        active = [(k, v) for k, v in upnp_results.items() if v[0]]
        if active:
            name, (ext_ip, ext_port) = active[0]
            label = f" ({name})" if name != "_server" else " (server)"
            upnp_str = f"{ext_ip}:{ext_port}{label}"
        else:
            upnp_str = "FAILED (no mappings created)"
    elif config.get("enable_upnp", False):
        upnp_str = "FAILED (miniupnpc unavailable)"
    else:
        upnp_str = "disabled"

    # Relay status
    relay_url = config.get("relay_server_url", "")
    if relay_url and relay_sessions:
        relay_port = config.get("relay_server_port", DEFAULT_RELAY_PORT)
        count = len(relay_sessions)
        relay_str = f"{relay_url}:{relay_port} ({count} session{'s' if count != 1 else ''})"
    elif relay_url:
        relay_str = f"{relay_url} (no sessions)"
    else:
        relay_str = "disabled"

    # Firewall status
    if config.get("enable_firewall_rules", False):
        fw_str = "ACTIVE (Windows)"
    else:
        fw_str = "disabled"

    # Security status
    sec_parts = []
    if config.get("enable_tls", False):
        sec_parts.append("TLS")
    else:
        sec_parts.append("plaintext")
    auth_method = config.get("auth_method", "token")
    if auth_method != "none" and (config.get("auth_token", "") or config.get("psk_key", "")):
        sec_parts.append(f"{auth_method} auth")
    else:
        sec_parts.append("no auth")
    sec_str = ", ".join(sec_parts)

    # WAN IP (informational, non-blocking)
    wan_ip = get_wan_ip()
    wan_str = wan_ip if wan_ip else "unavailable"

    lines = [
        "=======================================================",
        "  Connectivity Summary",
        "=======================================================",
        f"  LAN:      {lan_str}",
        f"  WAN:      {wan_str}",
        f"  mDNS:     {mdns_str}",
        f"  UPnP:     {upnp_str}",
        f"  Relay:    {relay_str}",
        f"  Firewall: {fw_str}",
        f"  Security: {sec_str}",
        f"  Engines:  {len(ALL_ENGINES)}",
        "=======================================================",
    ]
    summary = "\n".join(lines)
    logging.info("\n" + summary)
    print(summary)


async def main():
    """Main entry point."""
    base_log_dir = setup_logging(config)

    # PID file management
    pid_path = config.get("pid_file", "chess-uci-server.pid")
    stale_pid = read_pid_file(pid_path)
    if stale_pid is not None:
        if is_process_alive(stale_pid):
            logging.error(f"Server already running (PID {stale_pid}). "
                          f"Use --stop to stop it first.")
            return
        else:
            logging.info(f"Removing stale PID file (PID {stale_pid})")
            remove_pid_file(pid_path)
    write_pid_file(pid_path)
    logging.info(f"PID {os.getpid()} written to {pid_path}")

    # Build engine registry (explicit + auto-discovered)
    build_engine_registry(config)

    firewall = get_firewall_backend(config)
    await firewall.unblock_trusted(config["trusted_sources"], config["trusted_subnets"])

    if config.get("enable_firewall_rules", False):
        await firewall.configure(config)

    # Log auto-trust status
    if config.get("enable_auto_trust", False):
        logging.info(
            "Auto-trust enabled (any LAN client can connect without "
            "IP allowlist). Set \"enable_auto_trust\": false in config.json "
            "to restrict access."
        )

    # TLS context (shared across all engine servers)
    ssl_ctx = create_ssl_context(config)

    # Log auth status
    auth_method = config.get("auth_method", "token")
    if auth_method != "none" and (config.get("auth_token", "") or config.get("psk_key", "")):
        logging.info(f"Authentication enabled (method: {auth_method})")

    single_port = config.get("enable_single_port", False)

    # Resolve ports to available ones (auto-adjusts if occupied)
    resolve_ports(HOST, config)
    base_port = config.get("base_port", 9998)

    # mDNS advertisement
    zc, mdns_services = None, []
    if config.get("enable_mdns", False):
        if single_port:
            zc, mdns_services = start_mdns_advertisement_single(config, base_port)
        else:
            zc, mdns_services = start_mdns_advertisement(config)

    # UPnP port mapping
    upnp_results = {}
    upnp_mappings = {}
    if config.get("enable_upnp", False):
        local_ip = get_local_ip()
        lease = config.get("upnp_lease_duration", 3600)
        if single_port:
            # Single mapping for the multiplexed port
            desc = "Chess-UCI-Server"
            ext_ip, ext_port = await try_upnp_mapping(base_port, local_ip, desc, lease)
            if ext_ip:
                upnp_results["_server"] = (ext_ip, ext_port)
                upnp_mappings["_server"] = (base_port, local_ip, desc)
        else:
            for engine_name, details in ALL_ENGINES.items():
                port = details["port"]
                desc = f"Chess-UCI-{engine_name}"
                ext_ip, ext_port = await try_upnp_mapping(port, local_ip, desc, lease)
                if ext_ip:
                    upnp_results[engine_name] = (ext_ip, ext_port)
                    upnp_mappings[engine_name] = (port, local_ip, desc)
                else:
                    upnp_results[engine_name] = (None, None)

    # Relay session setup (deterministic IDs from server_secret)
    relay_sessions = {}
    relay_url = config.get("relay_server_url", "")
    if relay_url:
        server_secret = ensure_server_secret(config)
        if single_port:
            relay_sessions["_server_multiplex"] = derive_session_id(
                server_secret, "_server_multiplex")
        else:
            for engine_name in ALL_ENGINES:
                relay_sessions[engine_name] = derive_session_id(server_secret, engine_name)

    # Generate connection file (always — LAN-only setups benefit too)
    generate_connection_file(config, upnp_results or None, relay_sessions or None)

    # Log connectivity summary
    log_startup_summary(config, upnp_results, relay_sessions, zc, mdns_services)

    watchdog_interval = config.get("watchdog_timer_interval", 300)
    tasks = []

    try:
        if single_port:
            # Single-port multiplexed server
            task = asyncio.create_task(
                start_multiplex_server(HOST, base_port, config, firewall, ssl_ctx)
            )
            tasks.append(task)
            tls_tag = " (TLS)" if ssl_ctx else ""
            logging.info(
                f"Single-port mode: {len(ALL_ENGINES)} engines on port {base_port}{tls_tag}"
            )

            # Start single relay listener for multiplexed port
            if relay_url and "_server_multiplex" in relay_sessions:
                relay_port = config.get("relay_server_port", 19000)
                base_log = base_log_dir or os.path.dirname(os.path.abspath(__file__))
                relay_task = asyncio.create_task(
                    relay_listener(
                        "_multiplex", "", os.path.join(base_log, "communication_log_multiplex.txt"),
                        config, firewall, relay_url, relay_port,
                        relay_sessions["_server_multiplex"], ssl_ctx,
                    )
                )
                tasks.append(relay_task)
        else:
            # Per-engine servers (legacy mode)
            for engine_name, details in ALL_ENGINES.items():
                log_file = os.path.join(
                    base_log_dir or os.path.dirname(os.path.abspath(__file__)),
                    f"communication_log_{engine_name}.txt",
                )
                task = asyncio.create_task(
                    start_server(
                        HOST, details["port"], details["path"], log_file,
                        engine_name, config, firewall, ssl_ctx,
                    )
                )
                tasks.append(task)
                tls_tag = " (TLS)" if ssl_ctx else ""
                auth_tag = f" ({auth_method})" if auth_method != "none" else ""
                logging.info(
                    f"Started server for {engine_name} on port {details['port']}{tls_tag}{auth_tag}"
                )

            # Start relay listeners for each engine
            if relay_url:
                relay_port = config.get("relay_server_port", 19000)
                for engine_name, details in ALL_ENGINES.items():
                    if engine_name in relay_sessions:
                        log_file = os.path.join(
                            base_log_dir or os.path.dirname(os.path.abspath(__file__)),
                            f"communication_log_{engine_name}.txt",
                        )
                        relay_task = asyncio.create_task(
                            relay_listener(
                                engine_name, details["path"], log_file, config, firewall,
                                relay_url, relay_port, relay_sessions[engine_name], ssl_ctx,
                            )
                        )
                        tasks.append(relay_task)
                        logging.info(
                            f"Relay: Listening for {engine_name} via "
                            f"{relay_url}:{relay_port} (session {relay_sessions[engine_name]})"
                        )

        # Start UPnP renewal task
        if upnp_mappings:
            renewal_task = asyncio.create_task(upnp_renewal_task(upnp_mappings, config))
            tasks.append(renewal_task)

        watchdog_task = asyncio.create_task(watchdog_timer(watchdog_interval))

        # Graceful shutdown
        shutdown_event = asyncio.Event()

        def signal_handler():
            logging.info("Shutdown signal received")
            shutdown_event.set()

        signal.signal(signal.SIGINT, lambda *_: signal_handler())
        signal.signal(signal.SIGTERM, lambda *_: signal_handler())

        try:
            await shutdown_event.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            logging.info("Server shutdown initiated")

        logging.info("Initiating graceful shutdown...")
        stop_mdns_advertisement(zc, mdns_services)
        await session_manager.shutdown_all()
        tasks.append(watchdog_task)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logging.info("Server shutdown completed")
    finally:
        remove_pid_file(pid_path)
        logging.info(f"PID file {pid_path} removed")


def get_cert_fingerprint(cert_path):
    """Get SHA-256 fingerprint of a TLS certificate."""
    import hashlib
    try:
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        # Parse PEM to DER
        import base64
        lines = cert_data.decode().strip().split("\n")
        der_lines = [l for l in lines if not l.startswith("-----")]
        der_data = base64.b64decode("".join(der_lines))
        digest = hashlib.sha256(der_data).hexdigest()
        return ":".join(digest[i:i+2] for i in range(0, len(digest), 2))
    except Exception:
        return ""


def get_local_ip():
    """Get the machine's LAN IP address."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_wan_ip():
    """Get the machine's public/WAN IP via external service.

    Returns the IP string, or None on failure (no internet, timeout, etc.).
    """
    import urllib.request
    for url in [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://checkip.amazonaws.com",
    ]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "chess-uci-server"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                ip = resp.read().decode().strip()
                if ip and ipaddress.ip_address(ip):
                    return ip
        except Exception:
            continue
    return None


def generate_pairing_qr(config, upnp_results=None, relay_sessions=None):
    """Generate a QR code containing the connection config for DroidFish.

    The QR encodes a JSON payload:
    {
        "type": "chess-uci-server",
        "host": "<LAN IP>",
        "engines": [{"name": "Stockfish", "port": 9998}, ...],
        "tls": true/false,
        "token": "<auth_token>",
        "fingerprint": "<cert SHA-256>",
        "external_host": "<UPnP external IP>",
        "relay": {"host": "relay.example.com", "port": 19000}
    }
    """
    try:
        import qrcode
        has_qrcode = True
    except ImportError:
        # Attempt auto-install
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "qrcode"],
                capture_output=True, timeout=30,
            )
            import qrcode
            has_qrcode = True
        except Exception:
            has_qrcode = False

    host_ip = get_local_ip()

    # Use ALL_ENGINES (resolved ports) if available, fall back to config
    engines_source = ALL_ENGINES if ALL_ENGINES else config.get("engines", {})
    engines_list = [
        {"name": name, "port": details["port"], "mdns_name": name}
        for name, details in engines_source.items()
        if isinstance(details, dict) and "port" in details
    ]

    auth_method = config.get("auth_method", "token")
    # Infer "none" when no credentials are configured
    if auth_method == "token" and not config.get("auth_token", "") and not config.get("enable_tls", False):
        auth_method = "none"
    payload = {
        "type": "chess-uci-server",
        "host": host_ip,
        "engines": engines_list,
        "tls": config.get("enable_tls", False),
        "token": config.get("auth_token", ""),
        "auth_method": auth_method,
    }

    # Include single-port info when enabled
    single_port = config.get("enable_single_port", False)
    if single_port:
        payload["single_port"] = True
        payload["port"] = config.get("base_port", 9998)
        # In single-port mode, override each engine's port with the shared port
        for eng in engines_list:
            eng["port"] = payload["port"]

    # Include PSK in payload when method is psk
    if auth_method == "psk" and config.get("psk_key", ""):
        payload["psk"] = config["psk_key"]

    if config.get("enable_tls", False) and config.get("tls_cert_path", ""):
        fp = get_cert_fingerprint(config["tls_cert_path"])
        if fp:
            payload["fingerprint"] = fp

    # Add UPnP external IP if available
    if upnp_results:
        # All engines share the same external IP
        for _, (ext_ip, _) in upnp_results.items():
            if ext_ip:
                payload["external_host"] = ext_ip
                break

    # Fallback: use WAN IP if no UPnP external IP
    if "external_host" not in payload:
        wan_ip = get_wan_ip()
        if wan_ip:
            payload["external_host"] = wan_ip

    # Add relay info if configured
    relay_url = config.get("relay_server_url", "")
    if relay_url and relay_sessions:
        payload["relay"] = {
            "host": relay_url,
            "port": config.get("relay_server_port", 19000),
        }
        # Add session IDs per engine
        if single_port and "_server_multiplex" in relay_sessions:
            # Single-port: all engines share the same relay session
            shared_session = relay_sessions["_server_multiplex"]
            for eng in engines_list:
                eng["relay_session"] = shared_session
        else:
            for eng in engines_list:
                if eng["name"] in relay_sessions:
                    eng["relay_session"] = relay_sessions[eng["name"]]

    payload_json = json.dumps(payload, separators=(",", ":"))

    print("\n" + "=" * 60)
    print("  Chess UCI Server - Pairing")
    print("=" * 60)
    print(f"\n  Server: {host_ip}")
    if single_port:
        print(f"  Port:   {payload['port']} (single-port mode)")
    if "external_host" in payload:
        print(f"  External: {payload['external_host']}")
    for eng in engines_list:
        tls_tag = " (TLS)" if payload["tls"] else ""
        auth_tag = " (AUTH)" if payload["token"] else ""
        if not single_port:
            print(f"  Engine: {eng['name']} on port {eng['port']}{tls_tag}{auth_tag}")
        else:
            print(f"  Engine: {eng['name']}{tls_tag}{auth_tag}")
    print(f"  Auth: method={payload.get('auth_method', 'N/A')}"
          f" token={'yes(' + str(len(payload.get('token', ''))) + 'ch)' if payload.get('token') else 'none'}"
          f" psk={'yes' if payload.get('psk') else 'none'}")
    if "relay" in payload:
        print(f"  Relay: {payload['relay']['host']}:{payload['relay']['port']}")

    if has_qrcode:
        print(f"\n  Scan this QR code in DroidFish > Network Engines > Scan QR")
        print()
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(payload_json)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    else:
        print(f"\n  NOTE: QR code display unavailable (auto-install of qrcode failed)")
        print(f"        Install manually with: pip install qrcode")
        print(f"        A .chessuci connection file will be generated instead.")
        print(f"\n  Manual setup in DroidFish:")
        print(f"    Network Engines > Add > enter host '{host_ip}' and port"
              f" {payload.get('port', engines_list[0]['port']) if engines_list else '?'}")

    print(f"\n  Payload (for manual import / QR generation):")
    print(f"  {payload_json}")
    print("=" * 60 + "\n")


def generate_connection_file(config, upnp_results=None, relay_sessions=None):
    """Generate a .chessuci connection file for DroidFish import.

    The file contains all connection endpoints (LAN, UPnP, relay) and
    security config, enabling zero-config setup on the client.
    Supports both per-engine and single-port modes.

    Returns the path of the written file.
    """
    from datetime import datetime, timezone

    host_ip = get_local_ip()
    single_port = config.get("enable_single_port", False)
    base_port = config.get("base_port", 9998)

    # Resolve WAN IP for external endpoint (fallback when no UPnP)
    wan_ip = None
    if not upnp_results:
        wan_ip = get_wan_ip()

    engines_source = ALL_ENGINES if ALL_ENGINES else config.get("engines", {})
    engines = []
    for name, details in engines_source.items():
        port = base_port if single_port else details["port"]
        engine_entry = {
            "name": name,
            "port": port,
            "mdns_name": name,
            "endpoints": {
                "lan": {"host": host_ip, "port": port},
            },
        }

        if single_port:
            # Single-port: shared UPnP/relay for all engines
            if upnp_results and "_server" in upnp_results:
                ext_ip, ext_port = upnp_results["_server"]
                if ext_ip:
                    engine_entry["endpoints"]["upnp"] = {
                        "host": ext_ip, "port": ext_port,
                    }
            elif wan_ip:
                engine_entry["endpoints"]["wan"] = {
                    "host": wan_ip, "port": port,
                }
            if relay_sessions and "_server_multiplex" in relay_sessions:
                relay_url = config.get("relay_server_url", "")
                relay_port = config.get("relay_server_port", 19000)
                if relay_url:
                    engine_entry["endpoints"]["relay"] = {
                        "host": relay_url,
                        "port": relay_port,
                        "session_id": relay_sessions["_server_multiplex"],
                    }
        else:
            # Per-engine mode
            if upnp_results and name in upnp_results:
                ext_ip, ext_port = upnp_results[name]
                if ext_ip:
                    engine_entry["endpoints"]["upnp"] = {
                        "host": ext_ip, "port": ext_port,
                    }
            elif wan_ip:
                engine_entry["endpoints"]["wan"] = {
                    "host": wan_ip, "port": port,
                }
            if relay_sessions and name in relay_sessions:
                relay_url = config.get("relay_server_url", "")
                relay_port = config.get("relay_server_port", 19000)
                if relay_url:
                    engine_entry["endpoints"]["relay"] = {
                        "host": relay_url,
                        "port": relay_port,
                        "session_id": relay_sessions[name],
                    }

        engines.append(engine_entry)

    fingerprint = ""
    if config.get("enable_tls", False) and config.get("tls_cert_path", ""):
        fingerprint = get_cert_fingerprint(config["tls_cert_path"])

    auth_method = config.get("auth_method", "token")
    # Infer "none" when no credentials are configured
    if auth_method == "token" and not config.get("auth_token", "") and not config.get("enable_tls", False):
        auth_method = "none"

    connection = {
        "version": 1,
        "type": "chess-uci-server",
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "server_name": f"Chess Server ({host_ip})",
        "engines": engines,
        "security": {
            "tls": config.get("enable_tls", False),
            "auth_method": auth_method,
            "token": config.get("auth_token", ""),
            "psk": config.get("psk_key", ""),
            "fingerprint": fingerprint,
        },
    }

    if single_port:
        connection["single_port"] = True
        connection["port"] = base_port
        connection["available_engines"] = sorted(engines_source.keys())

    file_path = config.get("connection_file_path", "connection.chessuci")
    with open(file_path, "w") as f:
        json.dump(connection, f, indent=2)

    logging.info(f"Connection file written to {file_path}")
    return file_path


async def _resolve_endpoints(cfg):
    """Resolve UPnP mappings and relay session IDs for CLI commands.

    Returns (upnp_results_or_None, relay_sessions_or_None).
    """
    upnp = {}
    if cfg.get("enable_upnp", False):
        local_ip = get_local_ip()
        lease = cfg.get("upnp_lease_duration", 3600)
        if cfg.get("enable_single_port", False):
            bp = cfg.get("base_port", 9998)
            ext_ip, ext_port = await try_upnp_mapping(
                bp, local_ip, "Chess-UCI-Server", lease
            )
            if ext_ip:
                upnp["_server"] = (ext_ip, ext_port)
        else:
            for name, det in ALL_ENGINES.items():
                if not isinstance(det, dict) or "port" not in det:
                    continue
                ext_ip, ext_port = await try_upnp_mapping(
                    det["port"], local_ip, f"Chess-UCI-{name}", lease
                )
                if ext_ip:
                    upnp[name] = (ext_ip, ext_port)

    relay = {}
    if cfg.get("relay_server_url", ""):
        secret = ensure_server_secret(cfg)
        if cfg.get("enable_single_port", False):
            relay["_server_multiplex"] = derive_session_id(
                secret, "_server_multiplex")
        else:
            for name in ALL_ENGINES:
                relay[name] = derive_session_id(secret, name)

    return upnp or None, relay or None


# ---------------------------------------------------------------------------
# mDNS / Zeroconf advertisement
# ---------------------------------------------------------------------------


def start_mdns_advertisement(config):
    """Advertise engine servers via mDNS/Zeroconf (DNS-SD).

    Each engine gets a service entry of type _chess-uci._tcp.local.
    DroidFish can discover these via NsdManager (Android) or Zeroconf.

    Returns (Zeroconf, [ServiceInfo]) tuple for cleanup, or (None, []) if
    zeroconf is not available.
    """
    try:
        from zeroconf import Zeroconf, ServiceInfo
    except ImportError:
        logging.warning(
            "zeroconf package not installed - mDNS advertisement disabled. "
            "Install with: pip install zeroconf"
        )
        return None, []

    import socket

    host_ip = get_local_ip()
    try:
        packed_ip = socket.inet_aton(host_ip)
    except OSError:
        logging.error(f"Cannot pack IP {host_ip} for mDNS")
        return None, []

    zc = Zeroconf()
    services = []

    tls_enabled = config.get("enable_tls", False)
    auth_enabled = bool(config.get("auth_token", ""))

    for engine_name, details in config["engines"].items():
        port = details["port"]
        # DNS-SD service name: <instance>._chess-uci._tcp.local.
        svc_type = "_chess-uci._tcp.local."
        svc_name = f"{engine_name}.{svc_type}"

        properties = {
            "engine": engine_name,
            "tls": str(tls_enabled).lower(),
            "auth": str(auth_enabled).lower(),
        }

        info = ServiceInfo(
            svc_type,
            svc_name,
            addresses=[packed_ip],
            port=port,
            properties=properties,
            server=f"{socket.gethostname()}.local.",
        )
        try:
            zc.register_service(info)
            services.append(info)
            logging.info(
                f"mDNS: Registered {engine_name} as {svc_name} on port {port}"
            )
        except Exception as e:
            logging.error(f"mDNS: Failed to register {engine_name}: {e}")

    return zc, services


def start_mdns_advertisement_single(config, port):
    """Advertise a single multiplexed service via mDNS with engine list in TXT.

    Registers one _chess-uci._tcp service with a TXT property listing
    all available engines as a comma-separated string.
    """
    try:
        from zeroconf import Zeroconf, ServiceInfo
    except ImportError:
        logging.warning("zeroconf not installed - mDNS advertisement disabled")
        return None, []

    import socket

    host_ip = get_local_ip()
    try:
        packed_ip = socket.inet_aton(host_ip)
    except OSError:
        logging.error(f"Cannot pack IP {host_ip} for mDNS")
        return None, []

    zc = Zeroconf()
    svc_type = "_chess-uci._tcp.local."
    svc_name = f"Chess-UCI-Server.{svc_type}"

    engine_names = ",".join(sorted(ALL_ENGINES.keys()))
    properties = {
        "engines": engine_names,
        "tls": str(config.get("enable_tls", False)).lower(),
        "auth": str(bool(config.get("auth_token", ""))).lower(),
        "single_port": "true",
    }

    info = ServiceInfo(
        svc_type,
        svc_name,
        addresses=[packed_ip],
        port=port,
        properties=properties,
        server=f"{socket.gethostname()}.local.",
    )
    try:
        zc.register_service(info)
        logging.info(f"mDNS: Registered single-port service on port {port} "
                     f"with {len(ALL_ENGINES)} engines")
        return zc, [info]
    except Exception as e:
        logging.warning(f"mDNS: Could not advertise service ({e}). "
                        "Clients can still connect via QR code or connection file.")
        return None, []


def stop_mdns_advertisement(zc, services):
    """Unregister all mDNS services and close Zeroconf."""
    if zc is None:
        return
    for info in services:
        try:
            zc.unregister_service(info)
        except Exception:
            pass
    zc.close()
    logging.info("mDNS: All services unregistered")


# ---------------------------------------------------------------------------
# Engine discovery & setup helpers
# ---------------------------------------------------------------------------


def _is_engine_candidate(full_path, entry, skip_names, skip_extensions, is_windows):
    """Check if a file looks like a chess engine executable."""
    if not os.path.isfile(full_path):
        return False

    name_no_ext = os.path.splitext(entry)[0]
    _, ext = os.path.splitext(entry)

    # Skip known non-engine files
    if name_no_ext.lower() in skip_names:
        return False
    if ext.lower() in skip_extensions:
        return False

    # Platform-specific executable check
    if is_windows:
        if ext.lower() != ".exe":
            return False
    else:
        if not os.access(full_path, os.X_OK):
            return False

    return True


def discover_engines(directory):
    """Scan a directory (and one level of subdirectories) for chess engines.

    On Windows, only .exe files are considered (os.access X_OK is unreliable).
    On Linux/macOS, checks the executable permission bit.
    Always skips common non-engine files (README, LICENSE, etc.).

    Subdirectory scanning: if engines/lc0/lc0.exe exists, it will be found.
    The engine name comes from the file, not the folder.

    Returns list of (name, absolute_path) tuples.
    """
    if not directory or not os.path.isdir(directory):
        return []

    # Skip files whose name (case-insensitive, without extension) matches these
    skip_names = {
        "readme", "license", "licence", "changelog", "changes", "copying",
        "notice", "authors", "contributors", "todo", "makefile", "cmakelists",
    }
    # Skip files with these extensions
    skip_extensions = {
        ".txt", ".md", ".rst", ".html", ".json", ".yml", ".yaml", ".xml",
        ".cfg", ".ini", ".log", ".sh", ".bat", ".py", ".c", ".h", ".cpp",
        ".zip", ".tar", ".gz", ".7z", ".dll", ".so", ".dylib", ".pdf",
    }

    is_windows = platform.system() == "Windows"

    engines = []
    seen_names = set()

    # Scan top-level files
    for entry in sorted(os.listdir(directory)):
        full_path = os.path.join(directory, entry)
        if _is_engine_candidate(full_path, entry, skip_names, skip_extensions, is_windows):
            name_no_ext = os.path.splitext(entry)[0]
            engines.append((name_no_ext, os.path.abspath(full_path)))
            seen_names.add(name_no_ext.lower())

    # Scan one level of subdirectories
    for entry in sorted(os.listdir(directory)):
        subdir = os.path.join(directory, entry)
        if not os.path.isdir(subdir):
            continue
        for sub_entry in sorted(os.listdir(subdir)):
            sub_path = os.path.join(subdir, sub_entry)
            if _is_engine_candidate(sub_path, sub_entry, skip_names, skip_extensions, is_windows):
                name_no_ext = os.path.splitext(sub_entry)[0]
                # Skip if a top-level engine with the same name already found
                if name_no_ext.lower() not in seen_names:
                    engines.append((name_no_ext, os.path.abspath(sub_path)))
                    seen_names.add(name_no_ext.lower())

    return engines


def assign_ports(engine_list, base_port=9998):
    """Assign sequential ports to a list of engines.

    engine_list: list of (name, path) tuples
    Returns dict: {name: {"path": path, "port": port}}
    """
    result = {}
    for i, (name, path) in enumerate(engine_list):
        result[name] = {"path": path, "port": base_port + i}
    return result


def generate_auth_token(length=32):
    """Generate a cryptographically secure hex token."""
    return secrets.token_hex(length)


def generate_tls_certs(cert_dir="./certs"):
    """Generate self-signed TLS certificate and key using openssl.

    Returns (cert_path, key_path, fingerprint) or raises on failure.
    """
    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, "server.crt")
    key_path = os.path.join(cert_dir, "server.key")

    result = subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", key_path, "-out", cert_path,
            "-days", "365", "-nodes",
            "-subj", "/CN=chess-uci-server",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"openssl failed: {result.stderr}")

    fingerprint = get_cert_fingerprint(cert_path)
    return os.path.abspath(cert_path), os.path.abspath(key_path), fingerprint


def write_config(cfg, path="config.json"):
    """Write config dict to JSON file with pretty formatting."""
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"Config written to {path}")


# ---------------------------------------------------------------------------
# Setup wizard (--setup)
# ---------------------------------------------------------------------------


def run_setup_wizard():
    """Interactive setup wizard for first-time configuration."""
    print()
    print("=" * 50)
    print("  Chess UCI Server Setup Wizard")
    print("=" * 50)

    # Step 1: Network
    print("\nStep 1/5: Network")
    host = input("  Listen address [0.0.0.0]: ").strip() or "0.0.0.0"
    base_port_str = input("  Base port [9998]: ").strip() or "9998"
    try:
        base_port = int(base_port_str)
    except ValueError:
        print(f"  Invalid port '{base_port_str}', using 9998")
        base_port = 9998

    # Step 2: Engines
    print("\nStep 2/5: Engines")
    engine_dir = input("  Engine directory [./engines]: ").strip() or "./engines"
    engines_list = discover_engines(engine_dir)
    engines_config = {}

    if engines_list:
        names = [e[0] for e in engines_list]
        print(f"  Found: {', '.join(names)}")
        selection = input("  Select engines to enable [all]: ").strip().lower() or "all"
        if selection == "all":
            engines_config = assign_ports(engines_list, base_port)
        else:
            selected = [s.strip() for s in selection.split(",")]
            filtered = [(n, p) for n, p in engines_list if n in selected]
            if filtered:
                engines_config = assign_ports(filtered, base_port)
            else:
                print("  No matching engines found.")
    else:
        print(f"  No engines found in '{engine_dir}'.")

    if not engines_config:
        manual = input("  Enter engine path manually (or press Enter to skip): ").strip()
        if manual:
            name = os.path.splitext(os.path.basename(manual))[0]
            engines_config = {name: {"path": manual, "port": base_port}}

    if not engines_config:
        print("\n  WARNING: No engines configured. Add them later with --add-engine")
        engines_config = {}

    # Step 3: Connectivity
    print("\nStep 3/5: Connectivity")
    print("  How will clients connect?")
    print("    1) LAN only     - mDNS + UPnP auto-discovery (default)")
    print("    2) Open firewall - Auto-opens port for direct external access")
    print("    3) Relay mode    - No port forwarding needed")
    conn_choice = input("  Select [1]: ").strip() or "1"

    enable_upnp = True
    relay_server_url = ""
    relay_server_port = DEFAULT_RELAY_PORT
    server_secret = ""
    enable_single_port = False

    if conn_choice == "2":
        # Open firewall port
        port_to_open = base_port
        if platform.system() == "Windows":
            print(f"  Opening port {port_to_open} in Windows Firewall...")
            result = subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 "name=Chess UCI Server", "dir=in", "action=allow",
                 "protocol=TCP", f"localport={port_to_open}"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  Firewall rule added for port {port_to_open}")
            else:
                print(f"  WARNING: Failed to add firewall rule: {result.stderr}")
                print(f"  You may need to run as administrator")
        else:
            # Linux: try ufw first, then iptables
            if subprocess.run(["which", "ufw"], capture_output=True).returncode == 0:
                print(f"  Opening port {port_to_open} in UFW...")
                result = subprocess.run(
                    ["sudo", "ufw", "allow", f"{port_to_open}/tcp"],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    print(f"  UFW rule added for port {port_to_open}")
                else:
                    print(f"  WARNING: Failed to add UFW rule (may need sudo)")
            else:
                print(f"  Opening port {port_to_open} in iptables...")
                result = subprocess.run(
                    ["sudo", "iptables", "-A", "INPUT", "-p", "tcp",
                     "--dport", str(port_to_open), "-j", "ACCEPT"],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    print(f"  iptables rule added for port {port_to_open}")
                else:
                    print(f"  WARNING: Failed to add iptables rule (may need sudo)")
    elif conn_choice == "3":
        # Relay mode
        enable_upnp = False
        enable_single_port = True
        default_url = DEFAULT_RELAY_URL
        custom = input(f"  Relay server URL [{default_url}]: ").strip()
        relay_server_url = custom if custom else default_url
        relay_port_str = input(f"  Relay port [{DEFAULT_RELAY_PORT}]: ").strip()
        if relay_port_str:
            try:
                relay_server_port = int(relay_port_str)
            except ValueError:
                print(f"  Invalid port, using {DEFAULT_RELAY_PORT}")
                relay_server_port = DEFAULT_RELAY_PORT
        server_secret = secrets.token_hex(32)
        print(f"  Relay: {relay_server_url}:{relay_server_port}")
        print(f"  Server secret generated (for deterministic relay sessions)")
    else:
        # LAN only (default)
        print("  LAN mode: mDNS + UPnP auto-discovery enabled")

    # Step 4: Security
    print("\nStep 4/5: Security")
    enable_tls = input("  Enable TLS? [Y/n]: ").strip().lower()
    enable_tls = enable_tls != "n"

    cert_path = ""
    key_path = ""
    fingerprint = ""
    if enable_tls:
        try:
            cert_path, key_path, fingerprint = generate_tls_certs()
            print(f"  Cert: {cert_path}")
            print(f"  Key:  {key_path}")
            print(f"  Fingerprint: {fingerprint}")
        except Exception as e:
            print(f"  TLS cert generation failed: {e}")
            print("  Continuing without TLS.")
            enable_tls = False

    print("  Auth method: 1=Token 2=PSK 3=None")
    auth_choice = input("  Select [1]: ").strip() or "1"
    auth_method = "none"
    auth_token = ""
    psk_key = ""
    if auth_choice == "1":
        auth_method = "token"
        auth_token = generate_auth_token()
        print(f"  Generated token: {auth_token}")
    elif auth_choice == "2":
        auth_method = "psk"
        psk_key = generate_auth_token(16)
        print(f"  Generated PSK: {psk_key}")
    else:
        auth_method = "none"
        print("  No authentication configured.")

    # Step 5: Review & Save
    cfg = {
        "host": host,
        "engines": engines_config,
        "max_connections": 5,
        "trusted_sources": ["127.0.0.1"],
        "trusted_subnets": ["192.168.0.0/16", "10.0.0.0/8"],
        "base_log_dir": "",
        "enable_trusted_sources": True,
        "enable_tls": enable_tls,
        "tls_cert_path": cert_path,
        "tls_key_path": key_path,
        "auth_method": auth_method,
        "auth_token": auth_token,
        "psk_key": psk_key,
        "engine_directory": engine_dir,
        "base_port": base_port,
        "enable_mdns": True,
        "enable_upnp": enable_upnp,
        "enable_single_port": enable_single_port,
        "enable_server_log": True,
        "relay_server_url": relay_server_url,
        "relay_server_port": relay_server_port,
        "server_secret": server_secret,
    }

    conn_mode = "LAN only" if conn_choice == "1" else (
        "Firewall (port opened)" if conn_choice == "2" else "Relay mode"
    )

    print("\nStep 5/5: Review")
    print(f"  Host: {host}")
    print(f"  Engines: {len(engines_config)}")
    for name, details in engines_config.items():
        print(f"    {name}: port {details['port']}")
    print(f"  Connectivity: {conn_mode}")
    if relay_server_url:
        print(f"  Relay: {relay_server_url}:{relay_server_port}")
    print(f"  TLS: {enable_tls}")
    print(f"  Auth: {auth_method}")
    print()

    write_config(cfg)
    print("\nSetup complete! Run 'python chess.py' to start the server.")


# ---------------------------------------------------------------------------
# Add engine CLI (--add-engine)
# ---------------------------------------------------------------------------


def run_add_engine(args):
    """Add an engine to an existing config.json.

    Usage: python chess.py --add-engine /path/to/engine [--name Name] [--port 10000]
    """
    # Parse arguments
    engine_path = None
    engine_name = None
    engine_port = None
    i = 0
    while i < len(args):
        if args[i] == "--add-engine":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                engine_path = args[i + 1]
                i += 2
            else:
                print("ERROR: --add-engine requires a path argument")
                sys.exit(1)
        elif args[i] == "--name" and i + 1 < len(args):
            engine_name = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            try:
                engine_port = int(args[i + 1])
            except ValueError:
                print(f"ERROR: Invalid port: {args[i + 1]}")
                sys.exit(1)
            i += 2
        else:
            i += 1

    if not engine_path:
        print("ERROR: No engine path specified")
        print("Usage: python chess.py --add-engine /path/to/engine [--name Name] [--port 10000]")
        sys.exit(1)

    # Resolve path
    engine_path = os.path.abspath(engine_path)
    if not os.path.isfile(engine_path):
        print(f"ERROR: Engine path does not exist: {engine_path}")
        sys.exit(1)

    # Default name from filename
    if not engine_name:
        engine_name = os.path.splitext(os.path.basename(engine_path))[0]

    # Load existing config
    try:
        with open("config.json") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print("ERROR: config.json not found. Run --setup first.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid config.json: {e}")
        sys.exit(1)

    engines = cfg.get("engines", {})

    # Check name not duplicate
    if engine_name in engines:
        print(f"ERROR: Engine '{engine_name}' already exists in config")
        sys.exit(1)

    # Auto-assign port if not specified
    if engine_port is None:
        existing_ports = [d["port"] for d in engines.values() if isinstance(d, dict) and "port" in d]
        base = cfg.get("base_port", 9998)
        engine_port = max(existing_ports + [base - 1]) + 1

    # Check port conflict
    for name, details in engines.items():
        if isinstance(details, dict) and details.get("port") == engine_port:
            print(f"ERROR: Port {engine_port} already used by engine '{name}'")
            sys.exit(1)

    # Add engine
    engines[engine_name] = {"path": engine_path, "port": engine_port}
    cfg["engines"] = engines
    write_config(cfg)
    print(f"Added engine '{engine_name}' on port {engine_port}")


# ---------------------------------------------------------------------------
# PSK authentication support (S5)
# ---------------------------------------------------------------------------


async def authenticate_client_multi(reader, writer, config):
    """Perform authentication handshake supporting token and PSK methods.

    Protocol:
      - token-only (backward-compat): AUTH_REQUIRED\\n
      - multi-method: AUTH_REQUIRED token,psk\\n
      - Client sends: AUTH <token>\\n  or  PSK_AUTH <key>\\n
      - Server sends: AUTH_OK\\n  or  AUTH_FAIL\\n

    Returns True if auth succeeds (or no auth configured).
    """
    auth_method = config.get("auth_method", "token")
    token = config.get("auth_token", "")
    psk = config.get("psk_key", "")

    # No auth configured
    if auth_method == "none" or (not token and not psk):
        return True

    try:
        # Build methods list for the header
        methods = []
        if token:
            methods.append("token")
        if psk:
            methods.append("psk")

        if len(methods) == 1 and methods[0] == "token":
            # Backward-compatible: bare AUTH_REQUIRED
            writer.write(b"AUTH_REQUIRED\n")
        else:
            writer.write(f"AUTH_REQUIRED {','.join(methods)}\n".encode())
        await writer.drain()

        data = await asyncio.wait_for(reader.readline(), timeout=10)
        if not data:
            logging.warning("Auth: client disconnected before sending credentials")
            return False

        client_msg = data.decode().strip()
        logging.info(f"Auth: received '{client_msg[:30]}' (len={len(client_msg)})")

        # Token auth
        if client_msg.startswith("AUTH ") and token and client_msg[5:] == token:
            writer.write(b"AUTH_OK\n")
            await writer.drain()
            return True

        # PSK auth
        if client_msg.startswith("PSK_AUTH ") and psk and client_msg[9:] == psk:
            writer.write(b"AUTH_OK\n")
            await writer.drain()
            return True

        logging.warning(f"Auth: credential mismatch (got prefix '{client_msg[:10]}')")
        writer.write(b"AUTH_FAIL\n")
        await writer.drain()
        return False

    except asyncio.TimeoutError:
        logging.warning("Auth timeout - client did not respond")
        return False
    except Exception as e:
        logging.error(f"Auth error: {e}")
        return False


# ---------------------------------------------------------------------------
# __main__ with CLI dispatch
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    # CLI dispatch: check argv before loading config
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Chess UCI Server - Network bridge for UCI chess engines")
        print()
        print("Usage: python chess.py [OPTIONS]")
        print()
        print("Options:")
        print("  --setup             Interactive setup wizard")
        print("  --stop              Stop a running server (via PID file)")
        print("  --add-engine PATH   Add an engine to config.json")
        print("    --name NAME       Custom engine name (with --add-engine)")
        print("    --port PORT       Custom port number (with --add-engine)")
        print("  --pair              Generate QR code + .chessuci connection file")
        print("  --pair-only         Generate QR + connection file and exit")
        print("  --connection-file   Generate .chessuci connection file and exit")
        print("  --help, -h          Show this help message")
        sys.exit(0)

    if "--setup" in sys.argv:
        run_setup_wizard()
        sys.exit(0)

    if "--add-engine" in sys.argv:
        run_add_engine(sys.argv)
        sys.exit(0)

    if "--stop" in sys.argv:
        # Load config just to get pid_file path
        try:
            with open("config.json") as f:
                _cfg = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _cfg = {}
        pid_path = _cfg.get("pid_file", "chess-uci-server.pid")
        success = stop_server(pid_path)
        sys.exit(0 if success else 1)

    # Normal server startup: load config
    _init_from_config(load_config())

    if "--connection-file" in sys.argv:
        _prepare_engine_registry()

        async def _generate_connection():
            upnp_res, relay_res = await _resolve_endpoints(config)
            path = generate_connection_file(config, upnp_res, relay_res)
            print(f"Connection file written to: {path}")
            with open(path) as f:
                print(f.read())
        asyncio.run(_generate_connection())
        sys.exit(0)

    if "--pair" in sys.argv:
        _prepare_engine_registry()

        async def _pair():
            upnp_res, relay_res = await _resolve_endpoints(config)
            generate_pairing_qr(config, upnp_res, relay_res)
            path = generate_connection_file(config, upnp_res, relay_res)
            print(f"  Connection file: {path}")
            print(f"  Transfer to device:")
            print(f"    adb push {path} /sdcard/Download/")
            print(f"    or share via file manager / USB")
            print()
        asyncio.run(_pair())
        if "--pair-only" in sys.argv:
            sys.exit(0)
    asyncio.run(main())
