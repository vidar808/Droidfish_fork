@echo off
setlocal enabledelayedexpansion
REM Chess UCI Server - Start Script
echo.
echo   Chess UCI Server - Start
echo   ========================
echo.

REM ── Pre-flight checks ─────────────────────────────────────────

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERROR: Python is not installed or not in PATH.
    echo   Run install.bat first, or install Python manually.
    pause
    exit /b 1
)

if not exist "%~dp0chess.py" (
    echo   ERROR: chess.py not found.
    echo   Run install.bat first.
    pause
    exit /b 1
)

if not exist "%~dp0config.json" (
    echo   ERROR: config.json not found.
    echo   Run install.bat to generate a config, or copy example_config.json to config.json.
    pause
    exit /b 1
)

REM ── Check if already running ──────────────────────────────────

set "PID_FILE=%~dp0chess-uci-server.pid"
if exist "%PID_FILE%" (
    set /p OLD_PID=<"%PID_FILE%"
    tasklist /FI "PID eq !OLD_PID!" 2>nul | find "!OLD_PID!" >nul 2>&1
    if !errorlevel! equ 0 (
        echo   Server is already running ^(PID !OLD_PID!^).
        echo   Use stop-server.bat to stop it first.
        pause
        exit /b 1
    ) else (
        echo   Removing stale PID file...
        del /q "%PID_FILE%" >nul 2>&1
    )
)

REM ── Start ──────────────────────────────────────────────────────

echo   Starting server...
echo   Press Ctrl+C to stop.
echo.
cd /d "%~dp0"
python chess.py %*
