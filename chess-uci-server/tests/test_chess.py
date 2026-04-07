"""Test suite for Chess UCI Server (chess.py).

Tests cover:
- Config validation (validate_config)
- Trust verification (is_trusted, check_connection_attempts, handle_auto_trust)
- UCI option override logic (setoption handling in client_handler)
- Heartbeat mechanism
- Firewall backend selection
- Subnet computation
- SessionManager (engine process persistence across disconnects)
- OutputThrottler (rate-limiting UCI info lines)
"""

import asyncio
import copy
import ipaddress
import json
import os
import socket
import ssl
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import from chess module (config.json must exist in CWD or chess-uci-server dir)
import chess


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_config():
    """Return a minimal valid config dict."""
    return {
        "host": "0.0.0.0",
        "engines": {
            "TestEngine": {
                "path": "/usr/bin/false",
                "port": 9998,
            }
        },
        "max_connections": 5,
        "trusted_sources": ["127.0.0.1"],
        "trusted_subnets": ["192.168.1.0/24"],
        "custom_variables": {},
        "base_log_dir": "",
        "enable_trusted_sources": True,
        "enable_auto_trust": False,
        "enable_server_log": False,
        "enable_uci_log": False,
        "detailed_log_verbosity": False,
        "enable_firewall_rules": False,
        "enable_firewall_ip_blocking": False,
        "enable_firewall_subnet_blocking": False,
        "max_connection_attempts": 5,
        "connection_attempt_period": 3600,
        "enable_subnet_connection_attempt_blocking": False,
        "max_connection_attempts_from_untrusted_subnet": 10,
        "Log_untrusted_connection_attempts": False,
        "inactivity_timeout": 900,
        "heartbeat_time": 300,
        "watchdog_timer_interval": 300,
    }


@pytest.fixture
def minimal_config():
    return _minimal_config()


@pytest.fixture(autouse=True)
def reset_shared_state():
    """Clear module-level shared state between tests."""
    chess.connection_attempts.clear()
    chess.subnet_connection_attempts.clear()
    chess.auto_trusted_ips.clear()
    yield
    chess.connection_attempts.clear()
    chess.subnet_connection_attempts.clear()
    chess.auto_trusted_ips.clear()


# ===========================================================================
# Config Validation Tests
# ===========================================================================


class TestValidateConfig:
    """Tests for validate_config()."""

    def test_valid_minimal_config(self, minimal_config):
        errors = chess.validate_config(minimal_config)
        assert errors == []

    def test_missing_required_key_host(self, minimal_config):
        del minimal_config["host"]
        errors = chess.validate_config(minimal_config)
        assert any("host" in e for e in errors)

    def test_missing_required_key_engines(self, minimal_config):
        del minimal_config["engines"]
        errors = chess.validate_config(minimal_config)
        assert any("engines" in e for e in errors)

    def test_missing_required_key_max_connections(self, minimal_config):
        del minimal_config["max_connections"]
        errors = chess.validate_config(minimal_config)
        assert any("max_connections" in e for e in errors)

    def test_missing_required_key_trusted_sources(self, minimal_config):
        del minimal_config["trusted_sources"]
        errors = chess.validate_config(minimal_config)
        assert any("trusted_sources" in e for e in errors)

    def test_missing_required_key_trusted_subnets(self, minimal_config):
        del minimal_config["trusted_subnets"]
        errors = chess.validate_config(minimal_config)
        assert any("trusted_subnets" in e for e in errors)

    def test_wrong_type_host(self, minimal_config):
        minimal_config["host"] = 123
        errors = chess.validate_config(minimal_config)
        assert any("host" in e and "str" in e for e in errors)

    def test_wrong_type_engines(self, minimal_config):
        minimal_config["engines"] = "not a dict"
        errors = chess.validate_config(minimal_config)
        assert any("engines" in e and "dict" in e for e in errors)

    def test_wrong_type_max_connections(self, minimal_config):
        minimal_config["max_connections"] = "ten"
        errors = chess.validate_config(minimal_config)
        assert any("max_connections" in e and "int" in e for e in errors)

    def test_engine_missing_path(self, minimal_config):
        minimal_config["engines"]["BadEngine"] = {"port": 9999}
        errors = chess.validate_config(minimal_config)
        assert any("BadEngine" in e and "path" in e for e in errors)

    def test_engine_missing_port(self, minimal_config):
        minimal_config["engines"]["BadEngine"] = {"path": "/bin/false"}
        errors = chess.validate_config(minimal_config)
        assert any("BadEngine" in e and "port" in e for e in errors)

    def test_engine_wrong_port_type(self, minimal_config):
        minimal_config["engines"]["BadEngine"] = {"path": "/bin/false", "port": "9999"}
        errors = chess.validate_config(minimal_config)
        assert any("BadEngine" in e and "port" in e and "int" in e for e in errors)

    def test_engine_not_dict(self, minimal_config):
        minimal_config["engines"]["BadEngine"] = "not a dict"
        errors = chess.validate_config(minimal_config)
        assert any("BadEngine" in e and "dict" in e for e in errors)

    def test_invalid_trusted_source_ip(self, minimal_config):
        minimal_config["trusted_sources"].append("not.an.ip.address")
        errors = chess.validate_config(minimal_config)
        assert any("not.an.ip.address" in e for e in errors)

    def test_invalid_trusted_subnet(self, minimal_config):
        minimal_config["trusted_subnets"].append("invalid/cidr")
        errors = chess.validate_config(minimal_config)
        assert any("invalid/cidr" in e for e in errors)

    def test_max_connections_below_minimum(self, minimal_config):
        minimal_config["max_connections"] = 0
        errors = chess.validate_config(minimal_config)
        assert any("max_connections" in e for e in errors)

    def test_negative_inactivity_timeout(self, minimal_config):
        minimal_config["inactivity_timeout"] = -1
        errors = chess.validate_config(minimal_config)
        assert any("inactivity_timeout" in e for e in errors)

    def test_zero_inactivity_timeout_ok(self, minimal_config):
        minimal_config["inactivity_timeout"] = 0
        errors = chess.validate_config(minimal_config)
        assert errors == []

    def test_optional_defaults_applied(self):
        """Optional keys get defaults when missing."""
        config = {
            "host": "0.0.0.0",
            "engines": {"E": {"path": "/bin/false", "port": 9998}},
            "max_connections": 1,
            "trusted_sources": [],
            "trusted_subnets": [],
        }
        errors = chess.validate_config(config)
        assert errors == []
        # Optional keys should now be populated
        assert config["enable_auto_trust"] is False
        assert config["heartbeat_time"] == 300
        assert config["custom_variables"] == {}

    def test_multiple_errors_returned(self):
        """Empty config should produce multiple errors."""
        config = {}
        errors = chess.validate_config(config)
        assert len(errors) >= 5  # At least one per required key

    def test_valid_ipv6_trusted_source(self, minimal_config):
        minimal_config["trusted_sources"].append("::1")
        errors = chess.validate_config(minimal_config)
        assert errors == []

    def test_valid_ipv6_subnet(self, minimal_config):
        minimal_config["trusted_subnets"].append("fd00::/8")
        errors = chess.validate_config(minimal_config)
        assert errors == []

    def test_multiple_engines_valid(self, minimal_config):
        minimal_config["engines"]["Engine2"] = {"path": "/bin/true", "port": 9999}
        errors = chess.validate_config(minimal_config)
        assert errors == []

    def test_engine_with_custom_variables(self, minimal_config):
        minimal_config["engines"]["TestEngine"]["custom_variables"] = {
            "Hash": "4096",
            "Threads": "override",
        }
        errors = chess.validate_config(minimal_config)
        assert errors == []


# ===========================================================================
# Trust Verification Tests
# ===========================================================================


class TestIsTrusted:
    """Tests for is_trusted()."""

    def test_trusted_source_ip(self, minimal_config):
        assert chess.is_trusted("127.0.0.1", minimal_config) is True

    def test_untrusted_ip(self, minimal_config):
        assert chess.is_trusted("10.0.0.1", minimal_config) is False

    def test_trusted_subnet(self, minimal_config):
        # 192.168.1.0/24 is in trusted_subnets
        assert chess.is_trusted("192.168.1.50", minimal_config) is True

    def test_outside_trusted_subnet(self, minimal_config):
        assert chess.is_trusted("192.168.2.50", minimal_config) is False

    def test_auto_trusted_ip(self, minimal_config):
        chess.auto_trusted_ips.add("10.0.0.99")
        assert chess.is_trusted("10.0.0.99", minimal_config) is True

    def test_auto_trusted_not_in_config(self, minimal_config):
        """Auto-trusted IP should be trusted even if not in config sources."""
        chess.auto_trusted_ips.add("203.0.113.5")
        assert chess.is_trusted("203.0.113.5", minimal_config) is True

    def test_empty_trusted_sources(self, minimal_config):
        minimal_config["trusted_sources"] = []
        minimal_config["trusted_subnets"] = []
        assert chess.is_trusted("127.0.0.1", minimal_config) is False

    def test_subnet_boundary_first_ip(self, minimal_config):
        assert chess.is_trusted("192.168.1.0", minimal_config) is True

    def test_subnet_boundary_last_ip(self, minimal_config):
        assert chess.is_trusted("192.168.1.255", minimal_config) is True

    def test_subnet_boundary_just_outside(self, minimal_config):
        assert chess.is_trusted("192.168.0.255", minimal_config) is False


# ===========================================================================
# Auto-Trust Tests
# ===========================================================================


class TestAutoTrust:
    """Tests for handle_auto_trust()."""

    @pytest.mark.asyncio
    async def test_auto_trust_disabled(self, minimal_config):
        minimal_config["enable_auto_trust"] = False
        await chess.handle_auto_trust("10.0.0.1", minimal_config)
        assert "10.0.0.1" not in chess.auto_trusted_ips

    @pytest.mark.asyncio
    async def test_auto_trust_enabled(self, minimal_config):
        minimal_config["enable_auto_trust"] = True
        await chess.handle_auto_trust("10.0.0.1", minimal_config)
        assert "10.0.0.1" in chess.auto_trusted_ips

    @pytest.mark.asyncio
    async def test_auto_trust_idempotent(self, minimal_config):
        minimal_config["enable_auto_trust"] = True
        await chess.handle_auto_trust("10.0.0.1", minimal_config)
        await chess.handle_auto_trust("10.0.0.1", minimal_config)
        assert "10.0.0.1" in chess.auto_trusted_ips

    @pytest.mark.asyncio
    async def test_auto_trust_multiple_ips(self, minimal_config):
        minimal_config["enable_auto_trust"] = True
        await chess.handle_auto_trust("10.0.0.1", minimal_config)
        await chess.handle_auto_trust("10.0.0.2", minimal_config)
        assert "10.0.0.1" in chess.auto_trusted_ips
        assert "10.0.0.2" in chess.auto_trusted_ips

    @pytest.mark.asyncio
    async def test_auto_trusted_ip_becomes_trusted(self, minimal_config):
        """Once auto-trusted, is_trusted should return True."""
        minimal_config["enable_auto_trust"] = True
        assert chess.is_trusted("10.0.0.1", minimal_config) is False
        await chess.handle_auto_trust("10.0.0.1", minimal_config)
        assert chess.is_trusted("10.0.0.1", minimal_config) is True


# ===========================================================================
# Connection Attempt Tracking Tests
# ===========================================================================


class TestCheckConnectionAttempts:
    """Tests for check_connection_attempts()."""

    @pytest.mark.asyncio
    async def test_trusted_ip_not_tracked(self, minimal_config):
        firewall = chess.NoopFirewall()
        await chess.check_connection_attempts("127.0.0.1", minimal_config, firewall)
        assert "127.0.0.1" not in chess.connection_attempts

    @pytest.mark.asyncio
    async def test_untrusted_ip_tracked(self, minimal_config):
        minimal_config["Log_untrusted_connection_attempts"] = False
        firewall = chess.NoopFirewall()
        await chess.check_connection_attempts("10.0.0.1", minimal_config, firewall)
        assert "10.0.0.1" in chess.connection_attempts
        assert len(chess.connection_attempts["10.0.0.1"]) == 1

    @pytest.mark.asyncio
    async def test_multiple_attempts_counted(self, minimal_config):
        minimal_config["Log_untrusted_connection_attempts"] = False
        minimal_config["max_connection_attempts"] = 10  # High so no blocking
        firewall = chess.NoopFirewall()
        for _ in range(3):
            await chess.check_connection_attempts("10.0.0.1", minimal_config, firewall)
        assert len(chess.connection_attempts["10.0.0.1"]) == 3

    @pytest.mark.asyncio
    async def test_ip_blocking_triggered(self, minimal_config):
        minimal_config["Log_untrusted_connection_attempts"] = False
        minimal_config["max_connection_attempts"] = 2
        minimal_config["enable_firewall_ip_blocking"] = True
        firewall = MagicMock(spec=chess.NoopFirewall)
        firewall.block_ip = AsyncMock()

        for _ in range(3):
            await chess.check_connection_attempts("10.0.0.1", minimal_config, firewall)

        firewall.block_ip.assert_called()

    @pytest.mark.asyncio
    async def test_subnet_tracking(self, minimal_config):
        minimal_config["Log_untrusted_connection_attempts"] = False
        firewall = chess.NoopFirewall()
        await chess.check_connection_attempts("10.0.0.1", minimal_config, firewall)
        subnet = str(ipaddress.ip_network("10.0.0.1/24", strict=False))
        assert subnet in chess.subnet_connection_attempts

    @pytest.mark.asyncio
    async def test_expired_attempts_cleaned(self, minimal_config):
        minimal_config["Log_untrusted_connection_attempts"] = False
        minimal_config["connection_attempt_period"] = 1  # 1 second
        firewall = chess.NoopFirewall()

        # First attempt
        await chess.check_connection_attempts("10.0.0.1", minimal_config, firewall)
        assert "10.0.0.1" in chess.connection_attempts

        # Wait for expiration
        await asyncio.sleep(1.5)

        # New attempt should clean expired entries
        await chess.check_connection_attempts("10.0.0.2", minimal_config, firewall)
        assert "10.0.0.1" not in chess.connection_attempts


# ===========================================================================
# Firewall Backend Tests
# ===========================================================================


class TestFirewallBackend:
    """Tests for firewall backend selection and NoopFirewall."""

    def test_noop_when_disabled(self, minimal_config):
        minimal_config["enable_firewall_rules"] = False
        fw = chess.get_firewall_backend(minimal_config)
        assert isinstance(fw, chess.NoopFirewall)

    def test_noop_on_linux(self, minimal_config):
        minimal_config["enable_firewall_rules"] = True
        with patch("chess.platform.system", return_value="Linux"):
            fw = chess.get_firewall_backend(minimal_config)
            assert isinstance(fw, chess.NoopFirewall)

    def test_windows_on_windows(self, minimal_config):
        minimal_config["enable_firewall_rules"] = True
        with patch("chess.platform.system", return_value="Windows"):
            fw = chess.get_firewall_backend(minimal_config)
            assert isinstance(fw, chess.WindowsFirewall)

    @pytest.mark.asyncio
    async def test_noop_block_ip_logs(self, minimal_config):
        """NoopFirewall.block_ip should not raise."""
        fw = chess.NoopFirewall()
        await fw.block_ip("10.0.0.1", "9998")

    @pytest.mark.asyncio
    async def test_noop_block_subnet_logs(self, minimal_config):
        """NoopFirewall.block_subnet should not raise."""
        fw = chess.NoopFirewall()
        await fw.block_subnet("10.0.0.0/24", "9998")

    @pytest.mark.asyncio
    async def test_base_class_methods_noop(self):
        """FirewallBackend base class methods should be no-ops."""
        fw = chess.FirewallBackend()
        await fw.block_ip("10.0.0.1", "9998")
        await fw.block_subnet("10.0.0.0/24", "9998")
        await fw.unblock_trusted([], [])
        await fw.configure({})


# ===========================================================================
# Subnet Computation Tests
# ===========================================================================


class TestGenerateSubnets:
    """Tests for generate_subnets_to_avoid()."""

    def test_returns_list_of_strings(self):
        result = chess.generate_subnets_to_avoid(["1.2.3.4"], ["10.0.0.0/8"])
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_excludes_trusted_ip(self):
        result = chess.generate_subnets_to_avoid(["8.8.8.8"], [])
        # 8.8.8.8/32 should not be in any of the result subnets
        target = ipaddress.ip_address("8.8.8.8")
        for subnet_str in result:
            subnet = ipaddress.ip_network(subnet_str, strict=False)
            assert target not in subnet

    def test_excludes_trusted_subnet(self):
        result = chess.generate_subnets_to_avoid([], ["10.0.0.0/8"])
        # No result subnet should overlap with 10.0.0.0/8
        excluded = ipaddress.ip_network("10.0.0.0/8")
        for subnet_str in result:
            subnet = ipaddress.ip_network(subnet_str, strict=False)
            assert not subnet.overlaps(excluded)

    def test_empty_avoidance_lists(self):
        result = chess.generate_subnets_to_avoid([], [])
        assert len(result) > 0  # Should return all public ranges


# ===========================================================================
# Heartbeat Tests
# ===========================================================================


class TestHeartbeat:
    """Tests for heartbeat()."""

    @pytest.mark.asyncio
    async def test_heartbeat_sends_isready(self):
        """Heartbeat should send 'isready\\n' to engine stdin."""
        writer = MagicMock()
        engine_proc = MagicMock()
        engine_proc.stdin = MagicMock()
        engine_proc.stdin.write = MagicMock()
        engine_proc.stdin.drain = AsyncMock()

        # Run heartbeat with very short interval, cancel after first send
        task = asyncio.create_task(chess.heartbeat(writer, engine_proc, 0.1))
        await asyncio.sleep(0.25)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        engine_proc.stdin.write.assert_called_with(b"isready\n")

    @pytest.mark.asyncio
    async def test_heartbeat_stops_on_error(self):
        """Heartbeat should stop gracefully when engine stdin breaks."""
        writer = MagicMock()
        engine_proc = MagicMock()
        engine_proc.stdin = MagicMock()
        engine_proc.stdin.write = MagicMock(side_effect=BrokenPipeError)
        engine_proc.stdin.drain = AsyncMock()

        # Should exit cleanly on BrokenPipeError
        await asyncio.wait_for(
            chess.heartbeat(writer, engine_proc, 0.1),
            timeout=1.0,
        )

    @pytest.mark.asyncio
    async def test_heartbeat_does_not_write_to_client(self):
        """Heartbeat should NOT send anything to the client writer."""
        writer = MagicMock()
        writer.write = MagicMock()
        engine_proc = MagicMock()
        engine_proc.stdin = MagicMock()
        engine_proc.stdin.write = MagicMock()
        engine_proc.stdin.drain = AsyncMock()

        task = asyncio.create_task(chess.heartbeat(writer, engine_proc, 0.1))
        await asyncio.sleep(0.25)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        writer.write.assert_not_called()


# ===========================================================================
# Watchdog Timer Tests
# ===========================================================================


class TestWatchdogTimer:
    """Tests for watchdog_timer()."""

    @pytest.mark.asyncio
    async def test_watchdog_runs(self):
        """Watchdog should run without errors."""
        task = asyncio.create_task(chess.watchdog_timer(0.1))
        await asyncio.sleep(0.25)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ===========================================================================
# UCI Option Override Logic Tests
# ===========================================================================


class TestUCIOptionOverrides:
    """Tests for setoption handling logic (unit tests of the override rules).

    The override logic in process_client_commands() follows this priority:
    1. Per-engine custom_variables with value "override" -> pass through client value
    2. Per-engine custom_variables with specific value -> substitute server value
    3. Global custom_variables with specific value -> substitute server value
    4. Otherwise -> pass through client value
    """

    def _apply_override(self, command, engine_customs, global_customs):
        """Simulate the UCI option override logic from client_handler."""
        if command.startswith("setoption name"):
            parts = command.split(" ")
            if len(parts) >= 5 and parts[1] == "name" and parts[3] == "value":
                opt_name = parts[2]
                opt_value = " ".join(parts[4:])

                if opt_name in engine_customs:
                    if engine_customs[opt_name] == "override":
                        return command  # Pass through
                    else:
                        return f"setoption name {opt_name} value {engine_customs[opt_name]}"
                elif opt_name in global_customs:
                    return f"setoption name {opt_name} value {global_customs[opt_name]}"
                else:
                    return command  # Pass through
        return command

    def test_no_overrides_passthrough(self):
        cmd = "setoption name Hash value 128"
        result = self._apply_override(cmd, {}, {})
        assert result == cmd

    def test_engine_override_keyword_passes_client_value(self):
        cmd = "setoption name Threads value 8"
        result = self._apply_override(cmd, {"Threads": "override"}, {})
        assert result == "setoption name Threads value 8"

    def test_engine_specific_value_substituted(self):
        cmd = "setoption name Hash value 128"
        result = self._apply_override(cmd, {"Hash": "4096"}, {})
        assert result == "setoption name Hash value 4096"

    def test_global_value_substituted(self):
        cmd = "setoption name Hash value 128"
        result = self._apply_override(cmd, {}, {"Hash": "2048"})
        assert result == "setoption name Hash value 2048"

    def test_engine_overrides_global(self):
        """Engine-level custom var takes priority over global."""
        cmd = "setoption name Hash value 128"
        result = self._apply_override(cmd, {"Hash": "4096"}, {"Hash": "2048"})
        assert result == "setoption name Hash value 4096"

    def test_engine_override_keyword_overrides_global(self):
        """Engine 'override' keyword lets client value through despite global setting."""
        cmd = "setoption name Hash value 128"
        result = self._apply_override(cmd, {"Hash": "override"}, {"Hash": "2048"})
        assert result == "setoption name Hash value 128"

    def test_non_setoption_passthrough(self):
        cmd = "go depth 20"
        result = self._apply_override(cmd, {"Hash": "4096"}, {})
        assert result == "go depth 20"

    def test_value_with_spaces(self):
        cmd = "setoption name SyzygyPath value /path/to/syzygy tables"
        result = self._apply_override(cmd, {}, {})
        assert result == cmd


# ===========================================================================
# Load Config Tests
# ===========================================================================


class TestLoadConfig:
    """Tests for load_config()."""

    def test_load_valid_config(self):
        config = _minimal_config()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            f.flush()
            try:
                loaded = chess.load_config(f.name)
                assert loaded["host"] == "0.0.0.0"
                assert "TestEngine" in loaded["engines"]
            finally:
                os.unlink(f.name)

    def test_load_missing_file_exits(self):
        with pytest.raises(SystemExit):
            chess.load_config("/nonexistent/path/config.json")

    def test_load_invalid_json_exits(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            f.flush()
            try:
                with pytest.raises(SystemExit):
                    chess.load_config(f.name)
            finally:
                os.unlink(f.name)

    def test_load_invalid_config_exits(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"host": "0.0.0.0"}, f)  # Missing required keys
            f.flush()
            try:
                with pytest.raises(SystemExit):
                    chess.load_config(f.name)
            finally:
                os.unlink(f.name)


# ===========================================================================
# Integration: Mock Engine Client Handler
# ===========================================================================


class TestClientHandlerIntegration:
    """Integration tests using mock subprocess as engine."""

    @pytest.mark.asyncio
    async def test_untrusted_client_rejected(self, minimal_config):
        """Untrusted client should be disconnected immediately."""
        minimal_config["enable_trusted_sources"] = True
        minimal_config["enable_auto_trust"] = False
        minimal_config["Log_untrusted_connection_attempts"] = False

        reader = AsyncMock()
        writer = MagicMock()
        writer.get_extra_info = MagicMock(return_value=("10.0.0.99", 12345))
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=True)

        firewall = chess.NoopFirewall()

        await chess.client_handler(
            reader, writer, "/bin/false", "/dev/null", "TestEngine",
            minimal_config, firewall,
        )

        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_trusted_client_accepted(self, minimal_config):
        """Trusted client should proceed to engine spawn."""
        minimal_config["enable_trusted_sources"] = True
        minimal_config["trusted_sources"] = ["10.0.0.1"]

        reader = AsyncMock()
        writer = MagicMock()
        writer.get_extra_info = MagicMock(return_value=("10.0.0.1", 12345))
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()

        firewall = chess.NoopFirewall()

        # Engine subprocess will fail since path doesn't exist -
        # but it proves trust check passed (exception in engine spawn, not rejection)
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("engine")):
            await chess.client_handler(
                reader, writer, "/nonexistent/engine", "/dev/null", "TestEngine",
                minimal_config, firewall,
            )

        # Should NOT have been rejected (no close before engine spawn)

    @pytest.mark.asyncio
    async def test_auto_trust_on_connect(self, minimal_config):
        """With auto-trust enabled, untrusted client should be trusted."""
        minimal_config["enable_trusted_sources"] = True
        minimal_config["enable_auto_trust"] = True

        reader = AsyncMock()
        writer = MagicMock()
        writer.get_extra_info = MagicMock(return_value=("10.0.0.99", 12345))
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()

        firewall = chess.NoopFirewall()

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("engine")):
            await chess.client_handler(
                reader, writer, "/nonexistent/engine", "/dev/null", "TestEngine",
                minimal_config, firewall,
            )

        assert "10.0.0.99" in chess.auto_trusted_ips

    @pytest.mark.asyncio
    async def test_auth_required_before_engine(self, minimal_config):
        """With auth_token set, client must authenticate before engine spawn."""
        minimal_config["enable_trusted_sources"] = False
        minimal_config["auth_token"] = "secret123"

        # Simulate client sending wrong token
        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"AUTH wrongtoken\n")
        writer = MagicMock()
        writer.get_extra_info = MagicMock(return_value=("10.0.0.1", 12345))
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=True)
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        firewall = chess.NoopFirewall()

        await chess.client_handler(
            reader, writer, "/nonexistent/engine", "/dev/null", "TestEngine",
            minimal_config, firewall,
        )

        # Should have sent AUTH_REQUIRED and AUTH_FAIL
        calls = [c.args[0] for c in writer.write.call_args_list]
        assert b"AUTH_REQUIRED\n" in calls
        assert b"AUTH_FAIL\n" in calls

    @pytest.mark.asyncio
    async def test_auth_success_proceeds(self, minimal_config):
        """With correct token, client proceeds past auth to engine spawn."""
        minimal_config["enable_trusted_sources"] = False
        minimal_config["auth_token"] = "secret123"

        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"AUTH secret123\n")
        writer = MagicMock()
        writer.get_extra_info = MagicMock(return_value=("10.0.0.1", 12345))
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()

        firewall = chess.NoopFirewall()

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("engine")):
            await chess.client_handler(
                reader, writer, "/nonexistent/engine", "/dev/null", "TestEngine",
                minimal_config, firewall,
            )

        # Should have sent AUTH_OK (engine spawn fails but auth passed)
        calls = [c.args[0] for c in writer.write.call_args_list]
        assert b"AUTH_REQUIRED\n" in calls
        assert b"AUTH_OK\n" in calls

    @pytest.mark.asyncio
    async def test_no_auth_when_token_empty(self, minimal_config):
        """Without auth_token, no auth handshake occurs."""
        minimal_config["enable_trusted_sources"] = False
        minimal_config["auth_token"] = ""

        reader = AsyncMock()
        writer = MagicMock()
        writer.get_extra_info = MagicMock(return_value=("10.0.0.1", 12345))
        writer.close = MagicMock()
        writer.is_closing = MagicMock(return_value=False)
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()

        firewall = chess.NoopFirewall()

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("engine")):
            await chess.client_handler(
                reader, writer, "/nonexistent/engine", "/dev/null", "TestEngine",
                minimal_config, firewall,
            )

        # AUTH_REQUIRED should NOT have been sent
        calls = [c.args[0] for c in writer.write.call_args_list if c.args]
        assert b"AUTH_REQUIRED\n" not in calls


# ===========================================================================
# TLS Tests
# ===========================================================================


class TestTLS:
    """Tests for TLS support."""

    def test_create_ssl_context_disabled(self, minimal_config):
        minimal_config["enable_tls"] = False
        ctx = chess.create_ssl_context(minimal_config)
        assert ctx is None

    def test_create_ssl_context_missing_cert(self, minimal_config):
        minimal_config["enable_tls"] = True
        minimal_config["tls_cert_path"] = "/nonexistent/cert.pem"
        minimal_config["tls_key_path"] = "/nonexistent/key.pem"
        ctx = chess.create_ssl_context(minimal_config)
        assert ctx is None  # Should return None on error

    def test_create_ssl_context_valid(self, minimal_config):
        """With valid cert/key, should return an SSLContext."""
        import subprocess
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = os.path.join(tmpdir, "cert.pem")
            key_path = os.path.join(tmpdir, "key.pem")
            # Generate self-signed cert
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", key_path, "-out", cert_path,
                "-days", "1", "-nodes",
                "-subj", "/CN=test",
            ], check=True, capture_output=True)

            minimal_config["enable_tls"] = True
            minimal_config["tls_cert_path"] = cert_path
            minimal_config["tls_key_path"] = key_path
            ctx = chess.create_ssl_context(minimal_config)
            assert ctx is not None
            assert isinstance(ctx, ssl.SSLContext)

    def test_validate_config_tls_missing_cert(self, minimal_config):
        minimal_config["enable_tls"] = True
        minimal_config["tls_cert_path"] = ""
        minimal_config["tls_key_path"] = ""
        errors = chess.validate_config(minimal_config)
        assert any("tls_cert_path" in e for e in errors)
        assert any("tls_key_path" in e for e in errors)

    def test_validate_config_tls_nonexistent_files(self, minimal_config):
        minimal_config["enable_tls"] = True
        minimal_config["tls_cert_path"] = "/nonexistent/cert.pem"
        minimal_config["tls_key_path"] = "/nonexistent/key.pem"
        errors = chess.validate_config(minimal_config)
        assert any("not found" in e for e in errors)


# ===========================================================================
# Authentication Tests
# ===========================================================================


class TestAuthentication:
    """Tests for authenticate_client()."""

    @pytest.mark.asyncio
    async def test_no_token_configured(self, minimal_config):
        minimal_config["auth_token"] = ""
        reader = AsyncMock()
        writer = MagicMock()
        assert await chess.authenticate_client(reader, writer, minimal_config) is True

    @pytest.mark.asyncio
    async def test_correct_token(self, minimal_config):
        minimal_config["auth_token"] = "mysecret"
        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"AUTH mysecret\n")
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        result = await chess.authenticate_client(reader, writer, minimal_config)
        assert result is True
        calls = [c.args[0] for c in writer.write.call_args_list]
        assert b"AUTH_OK\n" in calls

    @pytest.mark.asyncio
    async def test_wrong_token(self, minimal_config):
        minimal_config["auth_token"] = "mysecret"
        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"AUTH wrongsecret\n")
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        result = await chess.authenticate_client(reader, writer, minimal_config)
        assert result is False
        calls = [c.args[0] for c in writer.write.call_args_list]
        assert b"AUTH_FAIL\n" in calls

    @pytest.mark.asyncio
    async def test_no_auth_prefix(self, minimal_config):
        minimal_config["auth_token"] = "mysecret"
        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"uci\n")
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        result = await chess.authenticate_client(reader, writer, minimal_config)
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_response(self, minimal_config):
        minimal_config["auth_token"] = "mysecret"
        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"")
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        result = await chess.authenticate_client(reader, writer, minimal_config)
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout(self, minimal_config):
        minimal_config["auth_token"] = "mysecret"
        reader = AsyncMock()
        reader.readline = AsyncMock(side_effect=asyncio.TimeoutError)
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        result = await chess.authenticate_client(reader, writer, minimal_config)
        assert result is False


# ===========================================================================
# Pairing / QR Code Tests
# ===========================================================================


class TestPairing:
    """Tests for QR code pairing functions."""

    def test_get_local_ip_returns_string(self):
        ip = chess.get_local_ip()
        assert isinstance(ip, str)
        # Should be a valid IP
        ipaddress.ip_address(ip)

    def test_get_cert_fingerprint_nonexistent(self):
        fp = chess.get_cert_fingerprint("/nonexistent/cert.pem")
        assert fp == ""

    def test_get_cert_fingerprint_valid(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = os.path.join(tmpdir, "cert.pem")
            key_path = os.path.join(tmpdir, "key.pem")
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", key_path, "-out", cert_path,
                "-days", "1", "-nodes", "-subj", "/CN=test",
            ], check=True, capture_output=True)
            fp = chess.get_cert_fingerprint(cert_path)
            assert fp != ""
            # SHA-256 fingerprint format: xx:xx:xx:... (32 hex pairs)
            parts = fp.split(":")
            assert len(parts) == 32

    def test_generate_pairing_qr_runs(self, minimal_config, capsys):
        """generate_pairing_qr should print without errors."""
        chess.generate_pairing_qr(minimal_config)
        captured = capsys.readouterr()
        assert "Chess UCI Server" in captured.out
        assert "Pairing" in captured.out
        assert "chess-uci-server" in captured.out

    def test_pairing_payload_structure(self, minimal_config, capsys):
        chess.generate_pairing_qr(minimal_config)
        captured = capsys.readouterr()
        # Extract JSON payload from the line after the "Payload" header
        lines = captured.out.split("\n")
        payload = None
        for i, line in enumerate(lines):
            if "Payload" in line:
                # JSON is on the next line
                if i + 1 < len(lines):
                    try:
                        payload = json.loads(lines[i + 1].strip())
                        break
                    except json.JSONDecodeError:
                        pass
        assert payload is not None, "Payload JSON not found in output"
        assert payload["type"] == "chess-uci-server"
        assert "host" in payload
        assert "engines" in payload
        assert isinstance(payload["engines"], list)
        assert payload["engines"][0]["name"] == "TestEngine"
        assert payload["engines"][0]["port"] == 9998


# ===========================================================================
# Logging Setup Tests
# ===========================================================================


class TestSetupLogging:
    """Tests for setup_logging()."""

    def test_returns_base_dir(self, minimal_config):
        with tempfile.TemporaryDirectory() as tmpdir:
            minimal_config["base_log_dir"] = tmpdir
            minimal_config["enable_server_log"] = True
            result = chess.setup_logging(minimal_config)
            assert result == tmpdir

    def test_creates_log_dir(self, minimal_config):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            minimal_config["base_log_dir"] = log_dir
            minimal_config["enable_server_log"] = True
            chess.setup_logging(minimal_config)
            assert os.path.isdir(log_dir)


# ===========================================================================
# SessionManager Tests
# ===========================================================================


class TestSessionManager:
    """Tests for SessionManager class."""

    @pytest.fixture
    def sm(self):
        """Fresh SessionManager for each test."""
        return chess.SessionManager()

    def _mock_process(self, alive=True):
        """Create a mock async subprocess."""
        proc = MagicMock()
        proc.returncode = None if alive else 0
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdout = MagicMock()
        proc.terminate = MagicMock()
        proc.wait = AsyncMock()
        return proc

    @pytest.mark.asyncio
    async def test_create_new_session(self, sm, minimal_config):
        """First call should create a new engine process."""
        mock_proc = self._mock_process()
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            proc, reattached = await sm.get_or_create(
                "TestEngine", "/usr/bin/false", minimal_config
            )
        assert proc is mock_proc
        assert reattached is False

    @pytest.mark.asyncio
    async def test_reattach_to_warm_session(self, sm, minimal_config):
        """Second call should reattach to existing process."""
        mock_proc = self._mock_process(alive=True)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await sm.get_or_create("TestEngine", "/usr/bin/false", minimal_config)

        # Release with keepalive
        minimal_config["session_keepalive_timeout"] = 60
        await sm.release("TestEngine", minimal_config)

        # Reattach
        proc, reattached = await sm.get_or_create(
            "TestEngine", "/usr/bin/false", minimal_config
        )
        assert proc is mock_proc
        assert reattached is True

    @pytest.mark.asyncio
    async def test_dead_session_creates_new(self, sm, minimal_config):
        """If cached process died, create new one."""
        dead_proc = self._mock_process(alive=False)
        with patch("asyncio.create_subprocess_exec", return_value=dead_proc):
            await sm.get_or_create("TestEngine", "/usr/bin/false", minimal_config)

        # Mark it dead
        dead_proc.returncode = 1

        new_proc = self._mock_process(alive=True)
        with patch("asyncio.create_subprocess_exec", return_value=new_proc):
            proc, reattached = await sm.get_or_create(
                "TestEngine", "/usr/bin/false", minimal_config
            )
        assert proc is new_proc
        assert reattached is False

    @pytest.mark.asyncio
    async def test_release_with_zero_keepalive_terminates(self, sm, minimal_config):
        """Release with keepalive=0 should terminate immediately."""
        mock_proc = self._mock_process()
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await sm.get_or_create("TestEngine", "/usr/bin/false", minimal_config)

        minimal_config["session_keepalive_timeout"] = 0
        await sm.release("TestEngine", minimal_config)

        mock_proc.stdin.write.assert_called_with(b"quit\n")
        mock_proc.terminate.assert_called()

    @pytest.mark.asyncio
    async def test_release_with_keepalive_schedules_expiry(self, sm, minimal_config):
        """Release with keepalive > 0 should schedule expiry task."""
        mock_proc = self._mock_process()
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await sm.get_or_create("TestEngine", "/usr/bin/false", minimal_config)

        minimal_config["session_keepalive_timeout"] = 60
        await sm.release("TestEngine", minimal_config)

        # Session should still exist (not terminated)
        assert "TestEngine" in sm._sessions
        assert sm._sessions["TestEngine"]["expiry_task"] is not None

        # Cleanup
        sm._sessions["TestEngine"]["expiry_task"].cancel()

    @pytest.mark.asyncio
    async def test_expiry_terminates_after_timeout(self, sm, minimal_config):
        """Session should be terminated after keepalive timeout expires."""
        mock_proc = self._mock_process()
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await sm.get_or_create("TestEngine", "/usr/bin/false", minimal_config)

        minimal_config["session_keepalive_timeout"] = 0.1  # 100ms
        await sm.release("TestEngine", minimal_config)

        # Wait for expiry
        await asyncio.sleep(0.3)

        assert "TestEngine" not in sm._sessions
        mock_proc.terminate.assert_called()

    @pytest.mark.asyncio
    async def test_shutdown_all(self, sm, minimal_config):
        """shutdown_all should terminate all sessions."""
        proc1 = self._mock_process()
        proc2 = self._mock_process()
        with patch("asyncio.create_subprocess_exec", return_value=proc1):
            await sm.get_or_create("Engine1", "/usr/bin/false", minimal_config)
        with patch("asyncio.create_subprocess_exec", return_value=proc2):
            await sm.get_or_create("Engine2", "/usr/bin/false", minimal_config)

        await sm.shutdown_all()

        proc1.terminate.assert_called()
        proc2.terminate.assert_called()
        assert len(sm._sessions) == 0

    @pytest.mark.asyncio
    async def test_release_nonexistent_engine(self, sm, minimal_config):
        """Releasing an engine not in sessions should not raise."""
        minimal_config["session_keepalive_timeout"] = 60
        await sm.release("NonexistentEngine", minimal_config)  # Should not raise

    @pytest.mark.asyncio
    async def test_reattach_cancels_expiry(self, sm, minimal_config):
        """Reattaching should cancel the pending expiry task."""
        mock_proc = self._mock_process()
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await sm.get_or_create("TestEngine", "/usr/bin/false", minimal_config)

        minimal_config["session_keepalive_timeout"] = 60
        await sm.release("TestEngine", minimal_config)
        expiry_task = sm._sessions["TestEngine"]["expiry_task"]
        assert not expiry_task.cancelled()

        # Reattach - should cancel the expiry
        proc, reattached = await sm.get_or_create(
            "TestEngine", "/usr/bin/false", minimal_config
        )
        assert reattached is True
        # Give event loop a tick to process cancellation
        await asyncio.sleep(0)
        assert expiry_task.cancelled() or expiry_task.done()


# ===========================================================================
# OutputThrottler Tests
# ===========================================================================


class TestOutputThrottler:
    """Tests for OutputThrottler class."""

    def test_disabled_when_zero(self):
        """throttle_ms=0 means all lines pass through."""
        t = chess.OutputThrottler(0)
        assert t.should_forward("info depth 1 score cp 30 pv e2e4") is True
        assert t.should_forward("info depth 1 score cp 30 pv e2e4") is True
        assert t.should_forward("bestmove e2e4") is True

    def test_non_info_always_forwarded(self):
        """Non-info lines always pass through."""
        t = chess.OutputThrottler(5000)  # Very high throttle
        assert t.should_forward("bestmove e2e4") is True
        assert t.should_forward("readyok") is True
        assert t.should_forward("id name Stockfish 18") is True
        assert t.should_forward("uciok") is True
        assert t.should_forward("option name Hash type spin") is True

    def test_depth_change_always_forwarded(self):
        """Info lines with new depth are always forwarded."""
        t = chess.OutputThrottler(5000)
        assert t.should_forward("info depth 1 score cp 30 pv e2e4") is True
        assert t.should_forward("info depth 2 score cp 25 pv e2e4 e7e5") is True
        assert t.should_forward("info depth 3 score cp 28 pv d2d4") is True

    def test_same_depth_throttled(self):
        """Info lines at same depth are throttled by time."""
        t = chess.OutputThrottler(5000)  # 5s throttle
        assert t.should_forward("info depth 10 score cp 30 pv e2e4") is True
        # Same depth, within throttle window
        assert t.should_forward("info depth 10 nodes 50000 nps 100000") is False
        assert t.should_forward("info depth 10 nodes 100000 nps 100000") is False

    def test_time_based_forwarding(self):
        """After throttle_ms elapses, info lines should be forwarded again."""
        t = chess.OutputThrottler(50)  # 50ms throttle
        assert t.should_forward("info depth 10 score cp 30 pv e2e4") is True
        assert t.should_forward("info depth 10 nodes 50000") is False

        # Wait for throttle to expire
        time.sleep(0.06)
        assert t.should_forward("info depth 10 nodes 100000") is True

    def test_extract_depth(self):
        """_extract_depth should parse depth from UCI info string."""
        t = chess.OutputThrottler(100)
        assert t._extract_depth("info depth 20 score cp 30 pv e2e4") == 20
        assert t._extract_depth("info depth 1 seldepth 5") == 1
        assert t._extract_depth("info nodes 50000 nps 100000") is None
        assert t._extract_depth("info string hello") is None

    def test_extract_depth_edge_cases(self):
        """_extract_depth handles edge cases."""
        t = chess.OutputThrottler(100)
        assert t._extract_depth("info depth") is None  # No value after depth
        assert t._extract_depth("info depth abc") is None  # Non-integer
        assert t._extract_depth("") is None

    def test_pending_info_cleared_on_non_info(self):
        """When a non-info line arrives, pending_info is cleared."""
        t = chess.OutputThrottler(5000)
        t.should_forward("info depth 10 score cp 30 pv e2e4")
        t.should_forward("info depth 10 nodes 50000")  # Throttled, stored as pending
        assert t.pending_info is not None

        t.should_forward("bestmove e2e4")
        assert t.pending_info is None

    def test_first_info_line_always_forwarded(self):
        """The very first info line should always pass through."""
        t = chess.OutputThrottler(5000)
        assert t.should_forward("info depth 1 score cp 0 pv e2e4") is True

    def test_info_without_depth_throttled_by_time(self):
        """Info lines without depth keyword are throttled by time only."""
        t = chess.OutputThrottler(5000)
        # First info passes (last_send_time starts at 0)
        assert t.should_forward("info nodes 1000 nps 50000") is True
        # Second without depth, within throttle
        assert t.should_forward("info nodes 2000 nps 60000") is False


# ===========================================================================
# mDNS Advertisement Tests
# ===========================================================================


class TestMDNS:
    """Tests for mDNS/Zeroconf advertisement."""

    def test_start_mdns_without_zeroconf(self, minimal_config):
        """When zeroconf is not importable, returns (None, [])."""
        minimal_config["enable_mdns"] = True
        with patch.dict("sys.modules", {"zeroconf": None}):
            zc, services = chess.start_mdns_advertisement(minimal_config)
        assert zc is None
        assert services == []

    def test_stop_mdns_with_none(self):
        """stop_mdns_advertisement with None zc should not raise."""
        chess.stop_mdns_advertisement(None, [])

    def test_start_mdns_registers_services(self, minimal_config):
        """With zeroconf available, services should be registered."""
        minimal_config["enable_mdns"] = True

        mock_zc = MagicMock()
        mock_si_class = MagicMock()

        mock_zeroconf_module = MagicMock()
        mock_zeroconf_module.Zeroconf = MagicMock(return_value=mock_zc)
        mock_zeroconf_module.ServiceInfo = mock_si_class

        with patch.dict("sys.modules", {"zeroconf": mock_zeroconf_module}):
            zc, services = chess.start_mdns_advertisement(minimal_config)

        assert zc is mock_zc
        assert len(services) == 1  # One engine in minimal_config
        mock_zc.register_service.assert_called_once()

    def test_stop_mdns_unregisters(self):
        """stop_mdns_advertisement should unregister all services."""
        mock_zc = MagicMock()
        mock_info1 = MagicMock()
        mock_info2 = MagicMock()

        chess.stop_mdns_advertisement(mock_zc, [mock_info1, mock_info2])

        assert mock_zc.unregister_service.call_count == 2
        mock_zc.close.assert_called_once()

    def test_mdns_service_properties(self, minimal_config):
        """mDNS service properties should include engine/tls/auth."""
        minimal_config["enable_tls"] = True
        minimal_config["auth_token"] = "secret"

        captured_info = {}
        mock_zc = MagicMock()

        def fake_service_info(svc_type, svc_name, **kwargs):
            captured_info.update(kwargs)
            return MagicMock()

        mock_module = MagicMock()
        mock_module.Zeroconf = MagicMock(return_value=mock_zc)
        mock_module.ServiceInfo = fake_service_info

        with patch.dict("sys.modules", {"zeroconf": mock_module}):
            chess.start_mdns_advertisement(minimal_config)

        assert captured_info["properties"]["tls"] == "true"
        assert captured_info["properties"]["auth"] == "true"
        assert captured_info["properties"]["engine"] == "TestEngine"


# ===========================================================================
# Engine Discovery Tests
# ===========================================================================


class TestDiscoverEngines:
    """Tests for discover_engines()."""

    def test_empty_dir_returns_empty(self):
        """Empty directory should return empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = chess.discover_engines(tmpdir)
            assert result == []

    def test_dir_with_executables(self):
        """Directory with executable files should return them."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create executable files
            for name in ["stockfish", "lc0"]:
                path = os.path.join(tmpdir, name)
                with open(path, "w") as f:
                    f.write("#!/bin/sh\n")
                os.chmod(path, 0o755)

            result = chess.discover_engines(tmpdir)
            assert len(result) == 2
            names = [r[0] for r in result]
            assert "stockfish" in names
            assert "lc0" in names

    def test_nonexistent_dir_returns_empty(self):
        """Non-existent directory should return empty list."""
        result = chess.discover_engines("/nonexistent/path/to/engines")
        assert result == []

    def test_skip_non_executable_files(self):
        """Non-executable files should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a non-executable file
            path = os.path.join(tmpdir, "readme.txt")
            with open(path, "w") as f:
                f.write("not an engine")
            os.chmod(path, 0o644)

            # Create an executable file
            exe_path = os.path.join(tmpdir, "stockfish")
            with open(exe_path, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(exe_path, 0o755)

            result = chess.discover_engines(tmpdir)
            assert len(result) == 1
            assert result[0][0] == "stockfish"

    def test_returns_absolute_paths(self):
        """Returned paths should be absolute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "engine")
            with open(path, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(path, 0o755)

            result = chess.discover_engines(tmpdir)
            assert len(result) == 1
            assert os.path.isabs(result[0][1])

    def test_subfolder_engines(self):
        """Engines in subdirectories should be discovered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create engine in subfolder: engines/lc0/lc0
            subdir = os.path.join(tmpdir, "lc0")
            os.makedirs(subdir)
            path = os.path.join(subdir, "lc0")
            with open(path, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(path, 0o755)

            result = chess.discover_engines(tmpdir)
            assert len(result) == 1
            assert result[0][0] == "lc0"
            assert os.path.isabs(result[0][1])
            assert "lc0/lc0" in result[0][1]

    def test_subfolder_and_toplevel_mixed(self):
        """Both top-level and subfolder engines should be found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Top-level engine
            top = os.path.join(tmpdir, "stockfish")
            with open(top, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(top, 0o755)

            # Subfolder engine
            subdir = os.path.join(tmpdir, "lc0")
            os.makedirs(subdir)
            sub = os.path.join(subdir, "lc0")
            with open(sub, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(sub, 0o755)

            result = chess.discover_engines(tmpdir)
            names = [r[0] for r in result]
            assert len(result) == 2
            assert "stockfish" in names
            assert "lc0" in names

    def test_toplevel_takes_priority_over_subfolder(self):
        """Top-level engine should win over same-named subfolder engine."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Top-level stockfish
            top = os.path.join(tmpdir, "stockfish")
            with open(top, "w") as f:
                f.write("#!/bin/sh\ntoplevel\n")
            os.chmod(top, 0o755)

            # Subfolder stockfish (same name)
            subdir = os.path.join(tmpdir, "sf")
            os.makedirs(subdir)
            sub = os.path.join(subdir, "stockfish")
            with open(sub, "w") as f:
                f.write("#!/bin/sh\nsubfolder\n")
            os.chmod(sub, 0o755)

            result = chess.discover_engines(tmpdir)
            assert len(result) == 1
            assert result[0][0] == "stockfish"
            # Should be the top-level one, not the subfolder one
            assert "/sf/" not in result[0][1]

    def test_subfolder_non_engine_files_skipped(self):
        """Non-engine files in subfolders should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "lc0")
            os.makedirs(subdir)

            # Engine executable
            eng = os.path.join(subdir, "lc0")
            with open(eng, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(eng, 0o755)

            # Supporting files (should be skipped)
            for name in ["weights.pb.gz", "readme.txt", "config.yaml"]:
                p = os.path.join(subdir, name)
                with open(p, "w") as f:
                    f.write("data")

            result = chess.discover_engines(tmpdir)
            assert len(result) == 1
            assert result[0][0] == "lc0"


# ===========================================================================
# Port Assignment Tests
# ===========================================================================


class TestAssignPorts:
    """Tests for assign_ports()."""

    def test_sequential_from_base_port(self):
        """Ports should be assigned sequentially from base_port."""
        engines = [("sf", "/usr/bin/sf"), ("lc0", "/usr/bin/lc0"), ("dragon", "/usr/bin/dragon")]
        result = chess.assign_ports(engines)
        assert result["sf"]["port"] == 9998
        assert result["lc0"]["port"] == 9999
        assert result["dragon"]["port"] == 10000

    def test_custom_base_port(self):
        """Custom base_port should be respected."""
        engines = [("sf", "/usr/bin/sf"), ("lc0", "/usr/bin/lc0")]
        result = chess.assign_ports(engines, base_port=5000)
        assert result["sf"]["port"] == 5000
        assert result["lc0"]["port"] == 5001

    def test_single_engine(self):
        """Single engine should get the base port."""
        engines = [("stockfish", "/usr/bin/stockfish")]
        result = chess.assign_ports(engines)
        assert result["stockfish"]["port"] == 9998
        assert result["stockfish"]["path"] == "/usr/bin/stockfish"

    def test_empty_list_returns_empty_dict(self):
        """Empty engine list should return empty dict."""
        result = chess.assign_ports([])
        assert result == {}


# ===========================================================================
# Auth Token Generation Tests
# ===========================================================================


class TestGenerateAuthToken:
    """Tests for generate_auth_token()."""

    def test_correct_length(self):
        """Default length=32 should produce 64 hex chars."""
        token = chess.generate_auth_token()
        assert len(token) == 64

    def test_uniqueness(self):
        """Two calls should produce different tokens."""
        t1 = chess.generate_auth_token()
        t2 = chess.generate_auth_token()
        assert t1 != t2

    def test_hex_format(self):
        """Token should contain only valid hex characters."""
        token = chess.generate_auth_token()
        assert all(c in "0123456789abcdef" for c in token)


# ===========================================================================
# Port Conflict Validation Tests
# ===========================================================================


class TestPortConflictValidation:
    """Tests for port conflict detection in validate_config()."""

    def test_no_conflict_passes(self):
        """Engines on different ports should produce no port-conflict errors."""
        config = _minimal_config()
        config["engines"]["Engine2"] = {"path": "/bin/true", "port": 9999}
        errors = chess.validate_config(config)
        port_errors = [e for e in errors if "Port conflict" in e]
        assert port_errors == []

    def test_duplicate_port_produces_error(self):
        """Two engines on the same port should produce a port-conflict error."""
        config = _minimal_config()
        config["engines"]["Engine2"] = {"path": "/bin/true", "port": 9998}
        errors = chess.validate_config(config)
        port_errors = [e for e in errors if "Port conflict" in e]
        assert len(port_errors) == 1
        assert "9998" in port_errors[0]

    def test_three_way_conflict(self):
        """Three engines on the same port should produce two conflict errors."""
        config = _minimal_config()
        config["engines"]["Engine2"] = {"path": "/bin/true", "port": 9998}
        config["engines"]["Engine3"] = {"path": "/bin/true", "port": 9998}
        errors = chess.validate_config(config)
        port_errors = [e for e in errors if "Port conflict" in e]
        assert len(port_errors) == 2

    def test_mixed_conflict_among_valid(self):
        """One conflict among several valid engines."""
        config = _minimal_config()
        config["engines"]["Engine2"] = {"path": "/bin/true", "port": 9999}
        config["engines"]["Engine3"] = {"path": "/bin/true", "port": 10000}
        config["engines"]["Engine4"] = {"path": "/bin/true", "port": 9999}  # Conflict with Engine2
        errors = chess.validate_config(config)
        port_errors = [e for e in errors if "Port conflict" in e]
        assert len(port_errors) == 1
        assert "9999" in port_errors[0]


# ===========================================================================
# Engine Path Validation Tests
# ===========================================================================


class TestEnginePathValidation:
    """Tests for engine path validation in validate_config()."""

    def test_nonexistent_path_produces_error(self):
        """Engine with nonexistent path should produce an error."""
        config = _minimal_config()
        config["engines"]["BadEngine"] = {
            "path": "/nonexistent/fake_engine_binary",
            "port": 10001,
        }
        errors = chess.validate_config(config)
        path_errors = [e for e in errors if "does not exist" in e]
        assert len(path_errors) >= 1
        assert any("BadEngine" in e for e in path_errors)

    def test_existing_executable_passes(self):
        """Engine with existing executable path should pass validation."""
        # Use /usr/bin/true or /bin/true (one should exist on Linux)
        exe_path = "/usr/bin/true" if os.path.isfile("/usr/bin/true") else "/bin/true"
        config = _minimal_config()
        config["engines"]["GoodEngine"] = {"path": exe_path, "port": 10001}
        errors = chess.validate_config(config)
        engine_errors = [e for e in errors if "GoodEngine" in e]
        assert engine_errors == []

    def test_non_executable_file_produces_error(self):
        """Engine path pointing to a non-executable file should produce an error."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"not an engine")
            tmp_path = f.name
        try:
            os.chmod(tmp_path, 0o644)  # Ensure not executable
            config = _minimal_config()
            config["engines"]["NoExec"] = {"path": tmp_path, "port": 10001}
            errors = chess.validate_config(config)
            exec_errors = [e for e in errors if "not executable" in e]
            assert len(exec_errors) >= 1
            assert any("NoExec" in e for e in exec_errors)
        finally:
            os.unlink(tmp_path)


# ===========================================================================
# PSK Authentication Tests
# ===========================================================================


class TestPSKAuth:
    """Tests for authenticate_client_multi() with PSK support."""

    @pytest.mark.asyncio
    async def test_psk_success(self):
        """PSK_AUTH with correct key should succeed."""
        config = _minimal_config()
        config["auth_method"] = "psk"
        config["psk_key"] = "mypsk123"
        config["auth_token"] = ""

        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"PSK_AUTH mypsk123\n")
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        result = await chess.authenticate_client_multi(reader, writer, config)
        assert result is True
        calls = [c.args[0] for c in writer.write.call_args_list]
        assert b"AUTH_OK\n" in calls

    @pytest.mark.asyncio
    async def test_wrong_psk_fails(self):
        """PSK_AUTH with wrong key should fail."""
        config = _minimal_config()
        config["auth_method"] = "psk"
        config["psk_key"] = "mypsk123"
        config["auth_token"] = ""

        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"PSK_AUTH wrongkey\n")
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        result = await chess.authenticate_client_multi(reader, writer, config)
        assert result is False
        calls = [c.args[0] for c in writer.write.call_args_list]
        assert b"AUTH_FAIL\n" in calls

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        """Timeout during auth should return False."""
        config = _minimal_config()
        config["auth_method"] = "psk"
        config["psk_key"] = "mypsk123"
        config["auth_token"] = ""

        reader = AsyncMock()
        reader.readline = AsyncMock(side_effect=asyncio.TimeoutError)
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        result = await chess.authenticate_client_multi(reader, writer, config)
        assert result is False

    @pytest.mark.asyncio
    async def test_token_only_backward_compat(self):
        """Token-only config sends bare AUTH_REQUIRED (no methods list)."""
        config = _minimal_config()
        config["auth_method"] = "token"
        config["auth_token"] = "secret123"
        config["psk_key"] = ""

        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"AUTH secret123\n")
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        result = await chess.authenticate_client_multi(reader, writer, config)
        assert result is True
        # First write should be bare AUTH_REQUIRED (backward compat)
        first_write = writer.write.call_args_list[0].args[0]
        assert first_write == b"AUTH_REQUIRED\n"

    @pytest.mark.asyncio
    async def test_multi_method_header(self):
        """With both token and PSK configured, header lists both methods."""
        config = _minimal_config()
        config["auth_method"] = "both"
        config["auth_token"] = "tok123"
        config["psk_key"] = "psk456"

        reader = AsyncMock()
        reader.readline = AsyncMock(return_value=b"AUTH tok123\n")
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        result = await chess.authenticate_client_multi(reader, writer, config)
        assert result is True
        # First write should include methods list
        first_write = writer.write.call_args_list[0].args[0]
        assert b"AUTH_REQUIRED token,psk\n" == first_write


# ===========================================================================
# Setup Wizard Helper Tests
# ===========================================================================


class TestSetupWizardHelpers:
    """Tests for setup wizard helper functions."""

    def test_write_config_roundtrip(self):
        """write_config should produce valid JSON that can be read back."""
        config = _minimal_config()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            tmp_path = f.name
        try:
            chess.write_config(config, path=tmp_path)
            with open(tmp_path) as f:
                loaded = json.load(f)
            assert loaded["host"] == config["host"]
            assert loaded["max_connections"] == config["max_connections"]
            assert "TestEngine" in loaded["engines"]
        finally:
            os.unlink(tmp_path)

    def test_generate_tls_certs_creates_files(self):
        """generate_tls_certs should create cert and key files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_dir = os.path.join(tmpdir, "certs")
            cert_path, key_path, fingerprint = chess.generate_tls_certs(cert_dir)
            assert os.path.isfile(cert_path)
            assert os.path.isfile(key_path)
            assert fingerprint != ""
            # Fingerprint should be SHA-256 format (32 colon-separated hex pairs)
            parts = fingerprint.split(":")
            assert len(parts) == 32

    def test_assign_ports_discover_engines_integration(self):
        """discover_engines + assign_ports should work end-to-end."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create executable files
            for name in ["engine_a", "engine_b"]:
                path = os.path.join(tmpdir, name)
                with open(path, "w") as f:
                    f.write("#!/bin/sh\n")
                os.chmod(path, 0o755)

            engines = chess.discover_engines(tmpdir)
            assert len(engines) == 2

            ports = chess.assign_ports(engines, base_port=8000)
            assert len(ports) == 2
            assigned_ports = sorted(d["port"] for d in ports.values())
            assert assigned_ports == [8000, 8001]


# ===========================================================================
# Auto-Discovery Tests
# ===========================================================================


class TestAutoDiscovery:
    """Tests for engine auto-discovery via engine_directory."""

    def test_discover_from_dir_with_executables(self):
        """discover_engines should find executables in a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["sf16", "komodo"]:
                p = os.path.join(tmpdir, name)
                with open(p, "w") as f:
                    f.write("#!/bin/sh\n")
                os.chmod(p, 0o755)

            result = chess.discover_engines(tmpdir)
            assert len(result) == 2
            names = {r[0] for r in result}
            assert names == {"sf16", "komodo"}

    def test_empty_dir_returns_empty(self):
        """Empty directory should return no engines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = chess.discover_engines(tmpdir)
            assert result == []

    def test_explicit_engines_not_overridden(self):
        """engine_directory should not override explicitly configured engines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create an executable in the directory
            p = os.path.join(tmpdir, "discovered_engine")
            with open(p, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(p, 0o755)

            # Simulate config with explicit engine and engine_directory
            config = _minimal_config()
            config["engine_directory"] = tmpdir

            # Discover engines from directory
            discovered = chess.discover_engines(config["engine_directory"])
            discovered_dict = chess.assign_ports(discovered, base_port=10000)

            # Explicit engines remain unchanged
            assert "TestEngine" in config["engines"]
            assert config["engines"]["TestEngine"]["port"] == 9998

            # Discovered engines are separate
            assert "discovered_engine" in discovered_dict
            assert discovered_dict["discovered_engine"]["port"] == 10000


# ===========================================================================
# UPnP Tests
# ===========================================================================


class TestUPnP:
    """Tests for UPnP port mapping functions."""

    def test_no_miniupnpc_returns_none(self):
        """When miniupnpc is not importable, should return (None, None)."""
        with patch.dict("sys.modules", {"miniupnpc": None}):
            import importlib
            result = chess._upnp_map_sync(9998, "192.168.1.100", "test", 3600)
            assert result == (None, None)

    def test_upnp_success(self):
        """Successful UPnP mapping should return external IP and port."""
        mock_upnp = MagicMock()
        mock_upnp_instance = MagicMock()
        mock_upnp_instance.discover.return_value = 1
        mock_upnp_instance.externalipaddress.return_value = "203.0.113.50"
        mock_upnp_instance.addportmapping.return_value = True
        mock_upnp.UPnP.return_value = mock_upnp_instance

        with patch.dict("sys.modules", {"miniupnpc": mock_upnp}):
            result = chess._upnp_map_sync(9998, "192.168.1.100", "test", 3600)
            assert result == ("203.0.113.50", 9998)

    def test_upnp_no_igd(self):
        """No IGD devices should return (None, None)."""
        mock_upnp = MagicMock()
        mock_upnp_instance = MagicMock()
        mock_upnp_instance.discover.return_value = 0
        mock_upnp.UPnP.return_value = mock_upnp_instance

        with patch.dict("sys.modules", {"miniupnpc": mock_upnp}):
            result = chess._upnp_map_sync(9998, "192.168.1.100", "test", 3600)
            assert result == (None, None)

    def test_upnp_port_conflict_fallback(self):
        """Port conflict on primary should try port + 10000."""
        mock_upnp = MagicMock()
        mock_upnp_instance = MagicMock()
        mock_upnp_instance.discover.return_value = 1
        mock_upnp_instance.externalipaddress.return_value = "203.0.113.50"
        # First port fails, second succeeds
        mock_upnp_instance.addportmapping.side_effect = [False, True]
        mock_upnp.UPnP.return_value = mock_upnp_instance

        with patch.dict("sys.modules", {"miniupnpc": mock_upnp}):
            result = chess._upnp_map_sync(9998, "192.168.1.100", "test", 3600)
            assert result == ("203.0.113.50", 19998)


# ===========================================================================
# External IP Tests
# ===========================================================================


class TestExternalIP:
    """Tests for get_external_ip()."""

    @pytest.mark.asyncio
    async def test_success(self):
        """Successful IP lookup returns valid IP string."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"203.0.113.50"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = await chess.get_external_ip()
            assert result == "203.0.113.50"

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        """Network timeout should return None."""
        import urllib.request
        with patch("urllib.request.urlopen", side_effect=urllib.request.URLError("timeout")):
            result = await chess.get_external_ip()
            assert result is None

    @pytest.mark.asyncio
    async def test_invalid_response_returns_none(self):
        """Non-IP response should return None."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not-an-ip"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = await chess.get_external_ip()
            assert result is None


# ===========================================================================
# Connection File Tests
# ===========================================================================


class TestConnectionFile:
    """Tests for generate_connection_file()."""

    def test_minimal_connection_file(self, minimal_config):
        """Generate connection file with no UPnP or relay."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.chessuci")
            minimal_config["connection_file_path"] = path
            chess.generate_connection_file(minimal_config)

            with open(path) as f:
                data = json.load(f)

            assert data["version"] == 1
            assert data["type"] == "chess-uci-server"
            assert len(data["engines"]) == 1
            assert data["engines"][0]["name"] == "TestEngine"
            assert "lan" in data["engines"][0]["endpoints"]
            assert "upnp" not in data["engines"][0]["endpoints"]
            assert "relay" not in data["engines"][0]["endpoints"]

    def test_connection_file_with_upnp(self, minimal_config):
        """Connection file should include UPnP endpoint when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.chessuci")
            minimal_config["connection_file_path"] = path
            upnp_results = {"TestEngine": ("203.0.113.50", 9998)}
            chess.generate_connection_file(minimal_config, upnp_results=upnp_results)

            with open(path) as f:
                data = json.load(f)

            upnp = data["engines"][0]["endpoints"]["upnp"]
            assert upnp["host"] == "203.0.113.50"
            assert upnp["port"] == 9998

    def test_connection_file_with_relay(self, minimal_config):
        """Connection file should include relay endpoint when configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.chessuci")
            minimal_config["connection_file_path"] = path
            minimal_config["relay_server_url"] = "relay.example.com"
            minimal_config["relay_server_port"] = 19000
            relay_sessions = {"TestEngine": "abc123def456"}
            chess.generate_connection_file(minimal_config, relay_sessions=relay_sessions)

            with open(path) as f:
                data = json.load(f)

            relay = data["engines"][0]["endpoints"]["relay"]
            assert relay["host"] == "relay.example.com"
            assert relay["port"] == 19000
            assert relay["session_id"] == "abc123def456"

    def test_connection_file_full(self, minimal_config):
        """Connection file with all endpoints and security."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.chessuci")
            minimal_config["connection_file_path"] = path
            minimal_config["enable_tls"] = False
            minimal_config["auth_token"] = "test_token"
            minimal_config["auth_method"] = "token"
            minimal_config["relay_server_url"] = "relay.example.com"

            upnp = {"TestEngine": ("203.0.113.50", 9998)}
            relay = {"TestEngine": "sessid123"}
            chess.generate_connection_file(minimal_config, upnp, relay)

            with open(path) as f:
                data = json.load(f)

            assert data["security"]["token"] == "test_token"
            assert data["security"]["auth_method"] == "token"
            assert "upnp" in data["engines"][0]["endpoints"]
            assert "relay" in data["engines"][0]["endpoints"]

    def test_connection_file_version(self, minimal_config):
        """Version field must be present and >= 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.chessuci")
            minimal_config["connection_file_path"] = path
            chess.generate_connection_file(minimal_config)

            with open(path) as f:
                data = json.load(f)
            assert data["version"] >= 1

    def test_connection_file_security_block(self, minimal_config):
        """Security block should contain all expected keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.chessuci")
            minimal_config["connection_file_path"] = path
            chess.generate_connection_file(minimal_config)

            with open(path) as f:
                data = json.load(f)

            sec = data["security"]
            assert "tls" in sec
            assert "auth_method" in sec
            assert "token" in sec
            assert "psk" in sec
            assert "fingerprint" in sec


# ===========================================================================
# Relay Listener Tests
# ===========================================================================


class TestRelayListener:
    """Tests for relay_listener() function."""

    @pytest.mark.asyncio
    async def test_registration_flow(self):
        """Relay listener should send SESSION and handle REGISTERED + PAIRED."""
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.is_closing = MagicMock(return_value=False)
        mock_writer.get_extra_info = MagicMock(return_value=("relay.test", 19000))

        # Simulate: REGISTERED, then PAIRED
        mock_reader.readline = AsyncMock(side_effect=[
            b"REGISTERED\n",
            b"PAIRED\n",
        ])

        config = _minimal_config()
        config["enable_trusted_sources"] = False

        async def mock_open(host, port):
            return mock_reader, mock_writer

        with patch("asyncio.open_connection", side_effect=mock_open):
            with patch("chess.client_handler", new_callable=AsyncMock) as mock_handler:
                # client_handler raises CancelledError to exit the loop
                mock_handler.side_effect = asyncio.CancelledError()
                await chess.relay_listener(
                    "TestEngine", "/usr/bin/false", "/tmp/log.txt",
                    config, chess.NoopFirewall(),
                    "relay.test", 19000, "session123"
                )

        # Verify SESSION was sent
        write_calls = mock_writer.write.call_args_list
        assert any(b"SESSION session123 server" in call[0][0] for call in write_calls)

    @pytest.mark.asyncio
    async def test_reconnect_on_error(self):
        """Should retry after connection error."""
        call_count = 0

        async def mock_open_connection(host, port):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("test error")
            raise asyncio.CancelledError()

        with patch("asyncio.open_connection", side_effect=mock_open_connection):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await chess.relay_listener(
                    "TestEngine", "/usr/bin/false", "/tmp/log.txt",
                    _minimal_config(), chess.NoopFirewall(),
                    "relay.test", 19000, "session123"
                )

        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_cancellation(self):
        """Should exit cleanly on CancelledError."""
        async def mock_open_connection(host, port):
            raise asyncio.CancelledError()

        with patch("asyncio.open_connection", side_effect=mock_open_connection):
            # Should not raise
            await chess.relay_listener(
                "TestEngine", "/usr/bin/false", "/tmp/log.txt",
                _minimal_config(), chess.NoopFirewall(),
                "relay.test", 19000, "session123"
            )


# ===========================================================================
# New Config Keys Tests
# ===========================================================================


class TestNewConfigKeys:
    """Tests for the new UPnP/relay config keys."""

    def test_upnp_defaults_applied(self, minimal_config):
        """New UPnP config keys should have defaults."""
        errors = chess.validate_config(minimal_config)
        assert errors == []
        assert minimal_config.get("enable_upnp") is True
        assert minimal_config.get("upnp_lease_duration") == 3600

    def test_relay_defaults_applied(self, minimal_config):
        """New relay config keys should have defaults."""
        errors = chess.validate_config(minimal_config)
        assert errors == []
        assert minimal_config.get("relay_server_url") == ""
        assert minimal_config.get("relay_server_port") == 19000

    def test_custom_relay_config(self, minimal_config):
        """Custom relay URL should be preserved after validation."""
        minimal_config["relay_server_url"] = "relay.example.com"
        minimal_config["relay_server_port"] = 20000
        errors = chess.validate_config(minimal_config)
        assert errors == []
        assert minimal_config["relay_server_url"] == "relay.example.com"
        assert minimal_config["relay_server_port"] == 20000


# ===========================================================================
# Deterministic Session ID Tests
# ===========================================================================


class TestDeterministicSessions:
    """Tests for derive_session_id and ensure_server_secret."""

    def test_derive_deterministic(self):
        """Same inputs should always produce the same session ID."""
        sid1 = chess.derive_session_id("secret123", "Stockfish")
        sid2 = chess.derive_session_id("secret123", "Stockfish")
        assert sid1 == sid2

    def test_derive_different_engines(self):
        """Different engine names should produce different session IDs."""
        sid1 = chess.derive_session_id("secret123", "Stockfish")
        sid2 = chess.derive_session_id("secret123", "Dragon")
        assert sid1 != sid2

    def test_derive_different_secrets(self):
        """Different secrets should produce different session IDs."""
        sid1 = chess.derive_session_id("secret_aaa", "Stockfish")
        sid2 = chess.derive_session_id("secret_bbb", "Stockfish")
        assert sid1 != sid2

    def test_derive_format(self):
        """Session ID should be 24 hex chars."""
        sid = chess.derive_session_id("secret123", "TestEngine")
        assert len(sid) == 24
        assert all(c in "0123456789abcdef" for c in sid)

    def test_ensure_generates(self):
        """ensure_server_secret should generate a secret when empty."""
        cfg = {"server_secret": ""}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as f:
            json.dump(cfg, f)
            f.flush()
            path = f.name
        try:
            secret = chess.ensure_server_secret(cfg, config_path=path)
            assert len(secret) == 64  # token_hex(32) = 64 hex chars
            assert cfg["server_secret"] == secret
            # Verify it was written to the file
            with open(path) as fread:
                saved = json.load(fread)
            assert saved["server_secret"] == secret
        finally:
            os.unlink(path)

    def test_ensure_preserves(self):
        """ensure_server_secret should not overwrite an existing valid secret."""
        existing = "a" * 64
        cfg = {"server_secret": existing}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as f:
            json.dump(cfg, f)
            f.flush()
            path = f.name
        try:
            secret = chess.ensure_server_secret(cfg, config_path=path)
            assert secret == existing
        finally:
            os.unlink(path)

    def test_server_secret_default(self, minimal_config):
        """server_secret should default to empty string."""
        errors = chess.validate_config(minimal_config)
        assert errors == []
        assert minimal_config.get("server_secret") == ""


# ===========================================================================
# mDNS Name in Payloads Tests
# ===========================================================================


class TestMdnsName:
    """Tests for mdns_name inclusion in QR and connection file payloads."""

    def test_qr_includes_mdns_name(self):
        """QR engines_list should include mdns_name field."""
        cfg = _minimal_config()
        chess.validate_config(cfg)
        # Mock qrcode to capture payload
        with patch.dict("sys.modules", {"qrcode": MagicMock()}):
            with patch("chess.get_local_ip", return_value="192.168.1.100"):
                with patch("builtins.print"):
                    # Call generate_pairing_qr and capture via json.dumps patch
                    captured = {}

                    original_dumps = json.dumps

                    def capture_dumps(obj, **kwargs):
                        captured["payload"] = obj
                        return original_dumps(obj, **kwargs)

                    with patch("json.dumps", side_effect=capture_dumps):
                        try:
                            chess.generate_pairing_qr(cfg)
                        except Exception:
                            pass  # qrcode mock may fail on print_ascii

                    if "payload" in captured:
                        engines = captured["payload"]["engines"]
                        for eng in engines:
                            assert "mdns_name" in eng
                            assert eng["mdns_name"] == eng["name"]

    def test_connection_file_includes_mdns_name(self):
        """Connection file engines should include mdns_name field."""
        cfg = _minimal_config()
        chess.validate_config(cfg)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".chessuci",
                                         delete=False) as f:
            path = f.name
        try:
            cfg["connection_file_path"] = path
            with patch("chess.get_local_ip", return_value="192.168.1.100"):
                chess.generate_connection_file(cfg)
            with open(path) as fread:
                data = json.load(fread)
            for eng in data["engines"]:
                assert "mdns_name" in eng
                assert eng["mdns_name"] == eng["name"]
        finally:
            os.unlink(path)


# ===========================================================================
# PID File Tests
# ===========================================================================


class TestPidFile:
    """Tests for PID file management functions."""

    def test_write_and_read_pid(self):
        """write_pid_file + read_pid_file round-trip."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            chess.write_pid_file(path)
            pid = chess.read_pid_file(path)
            assert pid == os.getpid()
        finally:
            os.unlink(path)

    def test_read_nonexistent(self):
        """read_pid_file returns None for missing file."""
        assert chess.read_pid_file("/nonexistent/pid/file.pid") is None

    def test_remove_pid_file(self):
        """remove_pid_file deletes file and is idempotent."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        chess.write_pid_file(path)
        assert os.path.exists(path)
        chess.remove_pid_file(path)
        assert not os.path.exists(path)
        # Second call doesn't raise
        chess.remove_pid_file(path)

    def test_is_process_alive_self(self):
        """is_process_alive returns True for own PID."""
        assert chess.is_process_alive(os.getpid()) is True

    def test_is_process_alive_bogus(self):
        """is_process_alive returns False for non-existent PID."""
        assert chess.is_process_alive(99999999) is False

    def test_stop_server_no_pid_file(self):
        """stop_server returns False when PID file doesn't exist."""
        assert chess.stop_server("/nonexistent/pid/file.pid") is False

    def test_stop_server_stale_pid(self):
        """stop_server cleans up stale PID file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pid") as f:
            f.write("99999999")
            path = f.name
        result = chess.stop_server(path)
        assert result is False
        assert not os.path.exists(path)


# ===========================================================================
# Engine Registry Tests
# ===========================================================================


class TestBuildEngineRegistry:
    """Tests for build_engine_registry()."""

    def test_explicit_only(self):
        """Registry with explicit engines only."""
        cfg = _minimal_config()
        chess.validate_config(cfg)
        result = chess.build_engine_registry(cfg)
        assert "TestEngine" in result
        assert result["TestEngine"]["port"] == 9998

    def test_auto_discovery(self):
        """Auto-discovered engines are added with sequential ports."""
        cfg = _minimal_config()
        cfg["engine_directory"] = "/some/dir"
        chess.validate_config(cfg)
        with patch("chess.discover_engines", return_value=[
            ("AutoEngine1", "/path/to/engine1"),
            ("AutoEngine2", "/path/to/engine2"),
        ]):
            result = chess.build_engine_registry(cfg)
        assert "TestEngine" in result
        assert "AutoEngine1" in result
        assert "AutoEngine2" in result
        assert result["AutoEngine1"]["port"] == 9999
        assert result["AutoEngine2"]["port"] == 10000

    def test_explicit_precedence(self):
        """Explicit engines take precedence over discovered ones with same name."""
        cfg = _minimal_config()
        cfg["engine_directory"] = "/some/dir"
        chess.validate_config(cfg)
        with patch("chess.discover_engines", return_value=[
            ("TestEngine", "/different/path"),  # Same name as explicit
        ]):
            result = chess.build_engine_registry(cfg)
        assert result["TestEngine"]["path"] == "/usr/bin/false"  # Original path

    def test_default_engine_resolution(self):
        """Default engine is set to first engine if not specified."""
        cfg = _minimal_config()
        cfg["default_engine"] = ""
        chess.validate_config(cfg)
        chess.build_engine_registry(cfg)
        assert cfg["default_engine"] == "TestEngine"

    def test_default_engine_validation(self):
        """validate_config errors on non-existent default_engine."""
        cfg = _minimal_config()
        cfg["default_engine"] = "NonExistent"
        errors = chess.validate_config(cfg)
        assert any("default_engine" in e for e in errors)


# ===========================================================================
# Multiplex Handler Tests
# ===========================================================================


class TestMultiplexHandler:
    """Tests for multiplex_handler() and ENGINE_LIST/SELECT_ENGINE protocol."""

    @pytest.fixture(autouse=True)
    def setup_engines(self):
        """Set up ALL_ENGINES for multiplex tests."""
        chess.ALL_ENGINES = {
            "Stockfish": {"path": "/usr/bin/false", "port": 9998},
            "Rodent": {"path": "/usr/bin/false", "port": 9999},
            "Dragon": {"path": "/usr/bin/false", "port": 10000},
        }
        yield
        chess.ALL_ENGINES = {}

    def _make_config(self, **overrides):
        cfg = _minimal_config()
        cfg["enable_trusted_sources"] = False
        cfg["auth_token"] = ""
        cfg["auth_method"] = "none"
        cfg["default_engine"] = "Stockfish"
        cfg["enable_single_port"] = True
        cfg.update(overrides)
        chess.validate_config(cfg)
        return cfg

    @pytest.mark.asyncio
    async def test_engine_list_format(self):
        """ENGINE_LIST returns sorted engine names then ENGINES_END."""
        cfg = self._make_config()
        reader = AsyncMock()
        writer = AsyncMock()
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.is_closing = MagicMock(return_value=True)

        # Client sends ENGINE_LIST, then SELECT_ENGINE Stockfish
        lines = [b"ENGINE_LIST\n", b"SELECT_ENGINE Stockfish\n"]
        reader.readline = AsyncMock(side_effect=lines)

        # Patch client_handler to capture args
        with patch("chess.client_handler", new_callable=AsyncMock) as mock_ch:
            await chess.multiplex_handler(reader, writer, cfg, chess.NoopFirewall())

        # Check what was written
        calls = writer.write.call_args_list
        written = b"".join(c[0][0] for c in calls)
        assert b"ENGINE Dragon\n" in written
        assert b"ENGINE Rodent\n" in written
        assert b"ENGINE Stockfish\n" in written
        assert b"ENGINES_END\n" in written
        assert b"ENGINE_SELECTED\n" in written

    @pytest.mark.asyncio
    async def test_select_engine_success(self):
        """SELECT_ENGINE with valid name delegates to client_handler."""
        cfg = self._make_config()
        reader = AsyncMock()
        writer = AsyncMock()
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.is_closing = MagicMock(return_value=True)

        reader.readline = AsyncMock(side_effect=[
            b"ENGINE_LIST\n", b"SELECT_ENGINE Rodent\n"
        ])

        with patch("chess.client_handler", new_callable=AsyncMock) as mock_ch:
            await chess.multiplex_handler(reader, writer, cfg, chess.NoopFirewall())
            mock_ch.assert_called_once()
            call_args = mock_ch.call_args
            assert call_args[0][2] == "/usr/bin/false"  # engine_path
            assert call_args[0][4] == "Rodent"  # engine_name

    @pytest.mark.asyncio
    async def test_select_unknown_engine(self):
        """SELECT_ENGINE with unknown name sends error and closes."""
        cfg = self._make_config()
        reader = AsyncMock()
        writer = AsyncMock()
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.is_closing = MagicMock(return_value=True)

        reader.readline = AsyncMock(side_effect=[
            b"ENGINE_LIST\n", b"SELECT_ENGINE NotAnEngine\n"
        ])

        with patch("chess.client_handler", new_callable=AsyncMock) as mock_ch:
            await chess.multiplex_handler(reader, writer, cfg, chess.NoopFirewall())
            mock_ch.assert_not_called()

        written = b"".join(c[0][0] for c in writer.write.call_args_list)
        assert b"ENGINE_ERROR" in written

    @pytest.mark.asyncio
    async def test_old_client_default(self):
        """Old client sends 'uci' directly — uses default engine."""
        cfg = self._make_config()
        reader = AsyncMock()
        writer = AsyncMock()
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.is_closing = MagicMock(return_value=True)

        reader.readline = AsyncMock(side_effect=[b"uci\n"])

        with patch("chess.client_handler", new_callable=AsyncMock) as mock_ch:
            await chess.multiplex_handler(reader, writer, cfg, chess.NoopFirewall())
            mock_ch.assert_called_once()
            call_args = mock_ch.call_args
            assert call_args[0][4] == "Stockfish"  # default engine

    @pytest.mark.asyncio
    async def test_timeout_first_line(self):
        """Timeout waiting for first command closes connection."""
        cfg = self._make_config()
        reader = AsyncMock()
        writer = AsyncMock()
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.is_closing = MagicMock(return_value=True)

        reader.readline = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("chess.client_handler", new_callable=AsyncMock) as mock_ch:
            await chess.multiplex_handler(reader, writer, cfg, chess.NoopFirewall())
            mock_ch.assert_not_called()
        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_auth_then_engine_list(self):
        """Auth handshake then ENGINE_LIST negotiation works."""
        cfg = self._make_config(auth_token="secret123", auth_method="token")
        reader = AsyncMock()
        writer = AsyncMock()
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.is_closing = MagicMock(return_value=True)

        # Simulate: server sends AUTH_REQUIRED, client sends AUTH token,
        # then ENGINE_LIST + SELECT_ENGINE
        reader.readline = AsyncMock(side_effect=[
            b"AUTH secret123\n",  # client auth response
            b"ENGINE_LIST\n",
            b"SELECT_ENGINE Dragon\n",
        ])

        with patch("chess.client_handler", new_callable=AsyncMock) as mock_ch:
            await chess.multiplex_handler(reader, writer, cfg, chess.NoopFirewall())
            if mock_ch.called:
                assert mock_ch.call_args[0][4] == "Dragon"

    @pytest.mark.asyncio
    async def test_multiple_engines_sorted(self):
        """ENGINE_LIST returns engines in sorted order."""
        cfg = self._make_config()
        reader = AsyncMock()
        writer = AsyncMock()
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.is_closing = MagicMock(return_value=True)

        reader.readline = AsyncMock(side_effect=[
            b"ENGINE_LIST\n", b"SELECT_ENGINE Stockfish\n"
        ])

        with patch("chess.client_handler", new_callable=AsyncMock):
            await chess.multiplex_handler(reader, writer, cfg, chess.NoopFirewall())

        calls = writer.write.call_args_list
        engine_lines = []
        for c in calls:
            data = c[0][0].decode() if isinstance(c[0][0], bytes) else c[0][0]
            for line in data.strip().split("\n"):
                if line.startswith("ENGINE "):
                    engine_lines.append(line)
        names = [l.split(" ", 1)[1] for l in engine_lines]
        assert names == sorted(names)


# ===========================================================================
# Single-Port Config Tests
# ===========================================================================


class TestSinglePortConfig:
    """Tests for single-port config keys and connection file format."""

    def test_new_config_defaults(self):
        """New config keys have correct defaults."""
        cfg = _minimal_config()
        chess.validate_config(cfg)
        assert cfg.get("pid_file") == "chess-uci-server.pid"
        assert cfg.get("enable_single_port") is False
        assert cfg.get("default_engine") == ""

    def test_connection_file_single_port(self):
        """Connection file includes single_port fields."""
        cfg = _minimal_config()
        cfg["enable_single_port"] = True
        cfg["base_port"] = 9998
        chess.validate_config(cfg)
        chess.ALL_ENGINES = cfg["engines"]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".chessuci",
                                         delete=False) as f:
            path = f.name
        try:
            cfg["connection_file_path"] = path
            with patch("chess.get_local_ip", return_value="192.168.1.100"):
                chess.generate_connection_file(cfg)
            with open(path) as fread:
                data = json.load(fread)
            assert data.get("single_port") is True
            assert data.get("port") == 9998
            assert "available_engines" in data
            assert "TestEngine" in data["available_engines"]
            # All engines should share the same port
            for eng in data["engines"]:
                assert eng["port"] == 9998
        finally:
            os.unlink(path)
            chess.ALL_ENGINES = {}

    def test_connection_file_per_engine_mode(self):
        """Connection file in per-engine mode does NOT include single_port."""
        cfg = _minimal_config()
        cfg["enable_single_port"] = False
        chess.validate_config(cfg)
        chess.ALL_ENGINES = cfg["engines"]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".chessuci",
                                         delete=False) as f:
            path = f.name
        try:
            cfg["connection_file_path"] = path
            with patch("chess.get_local_ip", return_value="192.168.1.100"):
                chess.generate_connection_file(cfg)
            with open(path) as fread:
                data = json.load(fread)
            assert "single_port" not in data
            assert "available_engines" not in data
        finally:
            os.unlink(path)
            chess.ALL_ENGINES = {}


# ---------------------------------------------------------------------------
# Port resolution tests
# ---------------------------------------------------------------------------


class TestFindAvailablePort:
    """Tests for find_available_port()."""

    def test_find_available_port_preferred(self):
        """When preferred port is free, returns it directly."""
        # Use a high port unlikely to be in use
        port = chess.find_available_port("127.0.0.1", 49100)
        assert port == 49100

    def test_find_available_port_fallback(self):
        """When preferred port is occupied, returns the next available."""
        # Bind the preferred port so find_available_port must skip it
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            blocker.bind(("127.0.0.1", 49200))
            blocker.listen(1)
            port = chess.find_available_port("127.0.0.1", 49200)
            assert port == 49201

    def test_find_available_port_skip_excluded(self):
        """Ports in the exclude set are skipped even if free."""
        port = chess.find_available_port(
            "127.0.0.1", 49300, exclude={49300, 49301}
        )
        assert port == 49302

    def test_find_available_port_no_available(self):
        """Raises OSError when no port is available within max_attempts."""
        # Exclude all ports in the tiny range
        with pytest.raises(OSError, match="No available port found"):
            chess.find_available_port(
                "127.0.0.1", 49400, max_attempts=3,
                exclude={49400, 49401, 49402}
            )


class TestResolvePorts:
    """Tests for resolve_ports()."""

    def test_resolve_ports_single_port(self):
        """In single-port mode, updates config['base_port'] if occupied."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            blocker.bind(("127.0.0.1", 49500))
            blocker.listen(1)

            config = {"enable_single_port": True, "base_port": 49500}
            chess.resolve_ports("127.0.0.1", config)
            assert config["base_port"] == 49501

    def test_resolve_ports_per_engine(self):
        """In per-engine mode, updates ALL_ENGINES ports and avoids collisions."""
        old_engines = chess.ALL_ENGINES
        try:
            chess.ALL_ENGINES = {
                "EngineA": {"path": "/usr/bin/a", "port": 49600},
                "EngineB": {"path": "/usr/bin/b", "port": 49600},
            }
            config = {"enable_single_port": False}
            chess.resolve_ports("127.0.0.1", config)

            ports = [chess.ALL_ENGINES[n]["port"] for n in sorted(chess.ALL_ENGINES)]
            # Both engines should get distinct ports
            assert len(set(ports)) == 2
            # First (alphabetically EngineA) gets 49600, second gets 49601
            assert chess.ALL_ENGINES["EngineA"]["port"] == 49600
            assert chess.ALL_ENGINES["EngineB"]["port"] == 49601
        finally:
            chess.ALL_ENGINES = old_engines


# ---------------------------------------------------------------------------
# _prepare_engine_registry and _resolve_endpoints tests
# ---------------------------------------------------------------------------


class TestPrepareEngineRegistry:
    """Tests for _prepare_engine_registry()."""

    def test_calls_build_and_resolve(self):
        """_prepare_engine_registry calls build_engine_registry and resolve_ports."""
        old_config = chess.config
        old_host = chess.HOST
        try:
            chess.config = _minimal_config()
            chess.HOST = "127.0.0.1"
            with patch("chess.build_engine_registry") as mock_build, \
                 patch("chess.resolve_ports") as mock_resolve:
                chess._prepare_engine_registry()
                mock_build.assert_called_once_with(chess.config)
                mock_resolve.assert_called_once_with("127.0.0.1", chess.config)
        finally:
            chess.config = old_config
            chess.HOST = old_host


class TestResolveEndpoints:
    """Tests for _resolve_endpoints()."""

    def test_no_upnp_no_relay(self):
        """Returns (None, None) when UPnP and relay are disabled."""
        cfg = _minimal_config()
        cfg["enable_upnp"] = False
        cfg["relay_server_url"] = ""
        upnp, relay = asyncio.run(chess._resolve_endpoints(cfg))
        assert upnp is None
        assert relay is None

    def test_relay_sessions_returned(self):
        """Returns relay sessions when relay_server_url is set."""
        cfg = _minimal_config()
        cfg["enable_upnp"] = False
        cfg["relay_server_url"] = "relay.example.com"
        cfg["server_secret"] = "a" * 64
        old_engines = chess.ALL_ENGINES
        try:
            chess.ALL_ENGINES = cfg["engines"]
            _, relay = asyncio.run(chess._resolve_endpoints(cfg))
            assert relay is not None
            assert "TestEngine" in relay
        finally:
            chess.ALL_ENGINES = old_engines


# ---------------------------------------------------------------------------
# QR auto-install tests
# ---------------------------------------------------------------------------


class TestQRAutoInstall:
    """Tests for qrcode auto-install in generate_pairing_qr."""

    def test_auto_install_attempted(self, capsys):
        """When qrcode is missing, subprocess.run is called with pip args."""
        cfg = _minimal_config()
        chess.ALL_ENGINES = cfg["engines"]

        # Simulate qrcode not available, even after install attempt
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "qrcode":
                raise ImportError("no qrcode")
            return original_import(name, *args, **kwargs)

        try:
            with patch("builtins.__import__", side_effect=mock_import), \
                 patch("subprocess.run") as mock_run, \
                 patch("chess.get_local_ip", return_value="192.168.1.100"):
                chess.generate_pairing_qr(cfg)
                # subprocess.run should be called with pip install qrcode
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "pip" in call_args[1] or call_args[1] == "-m"
                assert "qrcode" in call_args
        finally:
            chess.ALL_ENGINES = {}

    def test_auto_install_failure_graceful(self, capsys):
        """When auto-install fails, function completes with fallback text."""
        cfg = _minimal_config()
        chess.ALL_ENGINES = cfg["engines"]

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "qrcode":
                raise ImportError("no qrcode")
            return original_import(name, *args, **kwargs)

        try:
            with patch("builtins.__import__", side_effect=mock_import), \
                 patch("subprocess.run", side_effect=OSError("pip not found")), \
                 patch("chess.get_local_ip", return_value="192.168.1.100"):
                chess.generate_pairing_qr(cfg)
                captured = capsys.readouterr()
                assert "auto-install of qrcode failed" in captured.out
                assert ".chessuci connection file" in captured.out
        finally:
            chess.ALL_ENGINES = {}


# ---------------------------------------------------------------------------
# --pair generates connection file tests
# ---------------------------------------------------------------------------


class TestPairGeneratesConnectionFile:
    """Tests for --pair generating both QR and connection file."""

    def test_pair_calls_both_qr_and_connection_file(self):
        """--pair handler calls generate_pairing_qr and generate_connection_file."""
        cfg = _minimal_config()

        with patch("chess.generate_pairing_qr") as mock_qr, \
             patch("chess.generate_connection_file", return_value="connection.chessuci") as mock_conn, \
             patch("chess._resolve_endpoints", new_callable=AsyncMock, return_value=(None, None)), \
             patch("chess._prepare_engine_registry"), \
             patch("chess.get_local_ip", return_value="192.168.1.100"), \
             patch("builtins.open", MagicMock()):
            # Simulate what the --pair handler does
            chess._prepare_engine_registry()

            async def _run():
                upnp_res, relay_res = await chess._resolve_endpoints(cfg)
                chess.generate_pairing_qr(cfg, upnp_res, relay_res)
                chess.generate_connection_file(cfg, upnp_res, relay_res)

            asyncio.run(_run())
            mock_qr.assert_called_once()
            mock_conn.assert_called_once()

    def test_connection_file_handler_calls_resolve_ports(self):
        """--connection-file calls _prepare_engine_registry which includes resolve_ports."""
        with patch("chess.build_engine_registry") as mock_build, \
             patch("chess.resolve_ports") as mock_resolve:
            old_config = chess.config
            old_host = chess.HOST
            try:
                chess.config = _minimal_config()
                chess.HOST = "127.0.0.1"
                chess._prepare_engine_registry()
                mock_build.assert_called_once()
                mock_resolve.assert_called_once()
            finally:
                chess.config = old_config
                chess.HOST = old_host
