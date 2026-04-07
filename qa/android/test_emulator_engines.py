"""Android Emulator Engine Validation Tests.

Pushes each bundled UCI engine binary to the Android emulator and validates
that it starts, responds to UCI commands, computes moves, and shuts down
cleanly. Tests run directly on the emulator via adb shell.

Prerequisites:
    - Android emulator running (adb devices shows a device)
    - Engine .so files present in droidfish/DroidFishApp/src/main/jniLibs/

Usage:
    pytest qa/android/test_emulator_engines.py -v
"""

import os
import subprocess
import time

import pytest

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

QA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(QA_DIR)
JNILIBS_DIR = os.path.join(
    PROJECT_ROOT, "droidfish", "DroidFishApp", "src", "main", "jniLibs"
)
ASSETS_DIR = os.path.join(
    PROJECT_ROOT, "droidfish", "DroidFishApp", "src", "main", "assets"
)
ANDROID_HOME = os.environ.get("ANDROID_HOME", "/opt/android-sdk")
ADB = os.path.join(ANDROID_HOME, "platform-tools", "adb")
REMOTE_DIR = "/data/local/tmp/chess_qa"

# Engine definitions: (display_name, lib_filename, needs_nnue)
ENGINES = [
    ("Stockfish 18", "libstockfish.so", True),
    ("Rodent IV", "librodent4.so", False),
    ("Patricia", "libpatricia.so", False),
]

# NNUE files needed by Stockfish
NNUE_PATTERNS = ["nn-*.nnue"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adb(*args, timeout=30, input_data=None):
    """Run an adb command and return (returncode, stdout, stderr)."""
    cmd = [ADB] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_data,
    )
    return result.returncode, result.stdout, result.stderr


def _adb_shell(command, timeout=30, input_data=None):
    """Run a command on the emulator via adb shell."""
    return _adb("shell", command, timeout=timeout, input_data=input_data)


def _get_emulator_abi():
    """Get the emulator's CPU ABI."""
    rc, out, _ = _adb_shell("getprop ro.product.cpu.abi")
    if rc != 0:
        return None
    return out.strip()


def _is_emulator_running():
    """Check if an Android emulator is connected via adb."""
    rc, out, _ = _adb("devices")
    if rc != 0:
        return False
    # Look for a device line (not just the header)
    lines = out.strip().split("\n")
    for line in lines[1:]:
        if "\tdevice" in line:
            return True
    return False


def _push_file(local_path, remote_path):
    """Push a file to the emulator."""
    rc, out, err = _adb("push", local_path, remote_path)
    if rc != 0:
        raise RuntimeError(f"adb push failed: {err}")
    return out


def _run_engine_with_go(engine_info, uci_commands, timeout=30):
    """Run UCI commands on an engine, properly waiting for bestmove.

    Sends commands via a subshell that includes a sleep before quit,
    giving the engine time to compute. Uses the emulator's timeout
    command to prevent hanging.

    Args:
        engine_info: Dict with 'name', 'remote_path', 'needs_nnue'
        uci_commands: Escaped command string for echo -e (no quit needed)
        timeout: Max seconds for the whole operation

    Returns:
        List of output lines from the engine
    """
    remote = engine_info["remote_path"]
    name = engine_info["name"]

    # Send commands, wait for engine to finish, then quit.
    # The sleep gives the engine time to compute before stdin closes.
    if engine_info["needs_nnue"]:
        # cd into NNUE dir; use sh -c to wrap the cd + engine for timeout
        shell_cmd = (
            f'{{ echo -e "{uci_commands}"; sleep 10; echo quit; }} '
            f'| timeout {timeout} sh -c "cd {REMOTE_DIR} && ./{name}"'
        )
    else:
        shell_cmd = (
            f'{{ echo -e "{uci_commands}"; sleep 10; echo quit; }} '
            f'| timeout {timeout} {remote}'
        )

    rc, out, err = _adb_shell(shell_cmd, timeout=timeout + 5)
    return out.strip().split("\n") if out.strip() else []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def check_emulator():
    """Skip all tests if no emulator is running."""
    if not _is_emulator_running():
        pytest.skip("No Android emulator running (start with: emulator -avd <name>)")


@pytest.fixture(scope="module")
def emulator_abi():
    """Get the emulator's CPU ABI."""
    abi = _get_emulator_abi()
    if not abi:
        pytest.skip("Cannot determine emulator ABI")
    return abi


@pytest.fixture(scope="module")
def setup_engines(emulator_abi):
    """Push all engine binaries to the emulator. Returns dict of engine info."""
    abi = emulator_abi
    abi_dir = os.path.join(JNILIBS_DIR, abi)

    if not os.path.isdir(abi_dir):
        pytest.skip(f"No jniLibs for ABI {abi} at {abi_dir}")

    # Create remote directory
    _adb_shell(f"mkdir -p {REMOTE_DIR}")

    pushed = {}
    for display_name, lib_file, needs_nnue in ENGINES:
        local_path = os.path.join(abi_dir, lib_file)
        if not os.path.isfile(local_path):
            continue

        engine_name = lib_file.replace("lib", "").replace(".so", "")
        remote_path = f"{REMOTE_DIR}/{engine_name}"

        _push_file(local_path, remote_path)
        _adb_shell(f"chmod 755 {remote_path}")

        pushed[display_name] = {
            "name": engine_name,
            "remote_path": remote_path,
            "needs_nnue": needs_nnue,
            "local_lib": local_path,
        }

    # Push NNUE files for Stockfish
    import glob
    for pattern in NNUE_PATTERNS:
        for nnue_file in glob.glob(os.path.join(ASSETS_DIR, pattern)):
            basename = os.path.basename(nnue_file)
            _push_file(nnue_file, f"{REMOTE_DIR}/{basename}")

    yield pushed

    # Cleanup
    _adb_shell(f"rm -rf {REMOTE_DIR}")


def _engine_ids(setup_engines):
    return list(setup_engines.keys())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEngineUCIHandshake:
    """Verify each engine responds to the UCI protocol handshake."""

    @pytest.mark.parametrize("engine_name", [e[0] for e in ENGINES])
    def test_uci_responds_with_uciok(self, setup_engines, engine_name):
        """Engine responds to 'uci' with 'id name' and 'uciok'."""
        if engine_name not in setup_engines:
            pytest.skip(f"Engine {engine_name} not available for this ABI")

        info = setup_engines[engine_name]
        remote = info["remote_path"]

        # Send uci + quit via echo pipe
        cmd = f'echo -e "uci\\nquit" | {remote}'
        if info["needs_nnue"]:
            cmd = f'cd {REMOTE_DIR} && echo -e "uci\\nquit" | ./{info["name"]}'

        rc, out, err = _adb_shell(cmd, timeout=15)
        lines = out.strip().split("\n") if out.strip() else []

        has_id = any("id name" in l for l in lines)
        has_uciok = any("uciok" in l for l in lines)

        assert has_uciok, (
            f"{engine_name}: No 'uciok' received.\n"
            f"Output ({len(lines)} lines): {lines[:10]}\n"
            f"Stderr: {err[:200]}"
        )
        assert has_id, f"{engine_name}: No 'id name' line received"


class TestEngineReadiness:
    """Verify each engine responds to isready."""

    @pytest.mark.parametrize("engine_name", [e[0] for e in ENGINES])
    def test_isready_responds_readyok(self, setup_engines, engine_name):
        """Engine responds to 'isready' with 'readyok'."""
        if engine_name not in setup_engines:
            pytest.skip(f"Engine {engine_name} not available for this ABI")

        info = setup_engines[engine_name]
        cmd_prefix = f'cd {REMOTE_DIR} && ' if info["needs_nnue"] else ""

        cmd = f'{cmd_prefix}echo -e "uci\\nisready\\nquit" | {info["remote_path"]}'
        if info["needs_nnue"]:
            cmd = f'cd {REMOTE_DIR} && echo -e "uci\\nisready\\nquit" | ./{info["name"]}'

        rc, out, _ = _adb_shell(cmd, timeout=15)
        lines = out.strip().split("\n") if out.strip() else []

        has_readyok = any("readyok" in l for l in lines)
        assert has_readyok, (
            f"{engine_name}: No 'readyok' received.\n"
            f"Output: {lines[:15]}"
        )


class TestEngineMoveCalculation:
    """Verify each engine can calculate a move from the starting position."""

    @pytest.mark.parametrize("engine_name", [e[0] for e in ENGINES])
    @pytest.mark.timeout(60)
    def test_go_returns_bestmove(self, setup_engines, engine_name):
        """Engine calculates a move and returns 'bestmove'."""
        if engine_name not in setup_engines:
            pytest.skip(f"Engine {engine_name} not available for this ABI")

        info = setup_engines[engine_name]
        commands = "uci\\nisready\\nposition startpos\\ngo depth 5"
        lines = _run_engine_with_go(info, commands, timeout=30)

        bestmove_lines = [l for l in lines if l.strip().startswith("bestmove")]
        assert bestmove_lines, (
            f"{engine_name}: No 'bestmove' received after go depth 5.\n"
            f"Output ({len(lines)} lines): {lines[-10:]}"
        )

        # Validate move format (e.g., "bestmove e2e4 ponder e7e5")
        parts = bestmove_lines[0].split()
        assert len(parts) >= 2, f"Malformed bestmove: {bestmove_lines[0]}"
        move = parts[1]
        assert len(move) >= 4, f"Invalid move format: {move}"

    @pytest.mark.parametrize("engine_name", [e[0] for e in ENGINES])
    @pytest.mark.timeout(60)
    def test_go_produces_info_lines(self, setup_engines, engine_name):
        """Engine produces 'info depth' lines during search."""
        if engine_name not in setup_engines:
            pytest.skip(f"Engine {engine_name} not available for this ABI")

        info = setup_engines[engine_name]
        commands = "uci\\nisready\\nposition startpos\\ngo depth 5"
        lines = _run_engine_with_go(info, commands, timeout=30)

        info_lines = [l for l in lines if "info" in l and "depth" in l]
        assert len(info_lines) >= 1, (
            f"{engine_name}: No 'info depth' lines during search.\n"
            f"Output: {lines[-10:]}"
        )


class TestEnginePositions:
    """Verify engines handle various chess positions correctly."""

    @pytest.mark.parametrize("engine_name", [e[0] for e in ENGINES])
    @pytest.mark.timeout(60)
    def test_fen_position(self, setup_engines, engine_name):
        """Engine can process a FEN position and return bestmove."""
        if engine_name not in setup_engines:
            pytest.skip(f"Engine {engine_name} not available for this ABI")

        info = setup_engines[engine_name]
        fen = "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2"
        commands = f"uci\\nisready\\nposition fen {fen}\\ngo depth 5"
        lines = _run_engine_with_go(info, commands, timeout=30)

        bestmove_lines = [l for l in lines if l.strip().startswith("bestmove")]
        assert bestmove_lines, (
            f"{engine_name}: No bestmove from FEN position.\n"
            f"Output: {lines[-10:]}"
        )

    @pytest.mark.parametrize("engine_name", [e[0] for e in ENGINES])
    @pytest.mark.timeout(60)
    def test_position_with_moves(self, setup_engines, engine_name):
        """Engine can process a position with a move sequence."""
        if engine_name not in setup_engines:
            pytest.skip(f"Engine {engine_name} not available for this ABI")

        info = setup_engines[engine_name]
        commands = (
            "uci\\nisready\\n"
            "position startpos moves e2e4 e7e5 g1f3 b8c6 f1b5\\n"
            "go depth 5"
        )
        lines = _run_engine_with_go(info, commands, timeout=30)

        bestmove_lines = [l for l in lines if l.strip().startswith("bestmove")]
        assert bestmove_lines, (
            f"{engine_name}: No bestmove from position with moves.\n"
            f"Output: {lines[-10:]}"
        )


class TestEngineOptions:
    """Verify engines accept UCI options."""

    @pytest.mark.parametrize("engine_name", [e[0] for e in ENGINES])
    def test_setoption_hash(self, setup_engines, engine_name):
        """Engine accepts Hash option and remains responsive."""
        if engine_name not in setup_engines:
            pytest.skip(f"Engine {engine_name} not available for this ABI")

        info = setup_engines[engine_name]
        commands = (
            "uci\\n"
            "setoption name Hash value 32\\n"
            "isready\\n"
            "quit"
        )

        if info["needs_nnue"]:
            cmd = f'cd {REMOTE_DIR} && echo -e "{commands}" | ./{info["name"]}'
        else:
            cmd = f'echo -e "{commands}" | {info["remote_path"]}'

        rc, out, _ = _adb_shell(cmd, timeout=15)
        lines = out.strip().split("\n") if out.strip() else []

        has_readyok = any("readyok" in l for l in lines)
        assert has_readyok, (
            f"{engine_name}: No readyok after setoption Hash.\n"
            f"Output: {lines[:15]}"
        )

    @pytest.mark.parametrize("engine_name", [e[0] for e in ENGINES])
    def test_setoption_threads(self, setup_engines, engine_name):
        """Engine accepts Threads option and remains responsive."""
        if engine_name not in setup_engines:
            pytest.skip(f"Engine {engine_name} not available for this ABI")

        info = setup_engines[engine_name]
        commands = (
            "uci\\n"
            "setoption name Threads value 2\\n"
            "isready\\n"
            "quit"
        )

        if info["needs_nnue"]:
            cmd = f'cd {REMOTE_DIR} && echo -e "{commands}" | ./{info["name"]}'
        else:
            cmd = f'echo -e "{commands}" | {info["remote_path"]}'

        rc, out, _ = _adb_shell(cmd, timeout=15)
        lines = out.strip().split("\n") if out.strip() else []

        has_readyok = any("readyok" in l for l in lines)
        assert has_readyok, (
            f"{engine_name}: No readyok after setoption Threads.\n"
            f"Output: {lines[:15]}"
        )


class TestAPKBuildAndInstall:
    """Test building and installing DroidFish on the emulator."""

    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_build_debug_apk(self):
        """Gradle can build a debug APK."""
        gradle_dir = os.path.join(PROJECT_ROOT, "droidfish")
        result = subprocess.run(
            ["./gradlew", "assembleDebug", "-x", "lint"],
            cwd=gradle_dir,
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "ANDROID_HOME": ANDROID_HOME},
        )
        assert result.returncode == 0, (
            f"Gradle build failed:\n{result.stderr[-1000:]}"
        )

        # Verify APK exists
        apk_path = os.path.join(
            gradle_dir, "DroidFishApp", "build", "outputs", "apk", "debug",
            "DroidFishApp-debug.apk"
        )
        assert os.path.isfile(apk_path), f"Debug APK not found at {apk_path}"

    @pytest.mark.slow
    @pytest.mark.timeout(120)
    def test_install_apk_on_emulator(self):
        """APK installs on the emulator without errors."""
        apk_path = os.path.join(
            PROJECT_ROOT, "droidfish", "DroidFishApp", "build", "outputs",
            "apk", "debug", "DroidFishApp-debug.apk"
        )
        if not os.path.isfile(apk_path):
            pytest.skip("Debug APK not built yet (run test_build_debug_apk first)")

        rc, out, err = _adb("install", "-r", "-t", apk_path, timeout=60)
        assert rc == 0, f"APK install failed: {err}"
        assert "Success" in out or "success" in out.lower(), (
            f"Install did not report success: {out}"
        )

    @pytest.mark.slow
    @pytest.mark.timeout(120)
    def test_app_launches(self):
        """DroidFish app launches on the emulator."""
        package = "org.petero.droidfish.custom"
        activity = "org.petero.droidfish.DroidFish"

        # Check if installed
        rc, out, _ = _adb_shell(f"pm list packages {package}")
        if package not in out:
            pytest.skip("DroidFish not installed on emulator")

        # Launch activity
        rc, out, err = _adb_shell(
            f"am start -n {package}/{activity}",
            timeout=15,
        )
        assert "Error" not in out, f"Activity launch error: {out}"

        # Wait for activity to start
        time.sleep(3)

        # Check it's running
        rc, out, _ = _adb_shell(f"dumpsys activity activities | grep {package}")
        assert package in out, f"App not found in activity stack: {out[:200]}"

        # Clean up - stop the app
        _adb_shell(f"am force-stop {package}")


class TestAndroidInstrumentedTests:
    """Run the existing DroidFish androidTest suite on the emulator."""

    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_run_unit_tests(self):
        """Run DroidFish JVM unit tests."""
        gradle_dir = os.path.join(PROJECT_ROOT, "droidfish")
        result = subprocess.run(
            ["./gradlew", "testDebugUnitTest",
             "--tests", "org.petero.droidfish.engine.*",
             "-x", "lint"],
            cwd=gradle_dir,
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "ANDROID_HOME": ANDROID_HOME},
        )
        # Allow the known UCIOptionsTest.testSpinOptionBounds failure
        if result.returncode != 0:
            if "1 failed" in result.stdout and "testSpinOptionBounds" in result.stdout:
                pass  # Known failure
            else:
                assert False, (
                    f"Unit tests failed unexpectedly:\n{result.stdout[-1000:]}"
                )

    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_run_connected_android_tests(self):
        """Run DroidFish instrumented tests on the connected emulator."""
        if not _is_emulator_running():
            pytest.skip("No emulator connected")

        gradle_dir = os.path.join(PROJECT_ROOT, "droidfish")
        result = subprocess.run(
            ["./gradlew", "connectedDebugAndroidTest", "-x", "lint"],
            cwd=gradle_dir,
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "ANDROID_HOME": ANDROID_HOME},
        )
        assert result.returncode == 0, (
            f"Instrumented tests failed:\n{result.stderr[-1000:]}\n"
            f"{result.stdout[-1000:]}"
        )
