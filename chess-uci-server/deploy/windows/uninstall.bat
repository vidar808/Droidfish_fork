@echo off
setlocal enabledelayedexpansion
REM Chess UCI Server - Uninstall Script
echo.
echo   Chess UCI Server - Uninstall
echo   =============================
echo.
echo   This will:
echo     - Stop the running server (if any)
echo     - Remove the NSSM service (if installed)
echo     - Remove generated files (config, PID, logs, TLS certs)
echo     - Remove Python dependencies (qrcode, zeroconf, miniupnpc)
echo     - Optionally remove the server directory
echo.
set /p CONFIRM="  Are you sure? Type 'yes' to confirm: "
if /i not "!CONFIRM!"=="yes" (
    echo.
    echo   Uninstall cancelled.
    pause
    exit /b 0
)
echo.

REM ── Step 1: Stop the server ───────────────────────────────────

set "PID_FILE=%~dp0chess-uci-server.pid"
if exist "%PID_FILE%" (
    set /p OLD_PID=<"%PID_FILE%"
    tasklist /FI "PID eq !OLD_PID!" 2>nul | find "!OLD_PID!" >nul 2>&1
    if !errorlevel! equ 0 (
        echo   [1/5] Stopping server ^(PID !OLD_PID!^)...
        cd /d "%~dp0"
        python chess.py --stop >nul 2>&1
        if !errorlevel! neq 0 (
            taskkill /PID !OLD_PID! /F >nul 2>&1
        )
        timeout /t 2 /nobreak >nul
        echo          Server stopped.
    ) else (
        echo   [1/5] Server not running ^(stale PID file^).
        del /q "%PID_FILE%" >nul 2>&1
    )
) else (
    echo   [1/5] Server not running ........... OK
)

REM ── Step 2: Remove NSSM service ──────────────────────────────

where nssm >nul 2>&1
if %errorlevel% equ 0 (
    nssm status ChessUCIServer >nul 2>&1
    if !errorlevel! equ 0 (
        echo   [2/5] Removing NSSM service...
        nssm stop ChessUCIServer >nul 2>&1
        nssm remove ChessUCIServer confirm >nul 2>&1
        echo          Service removed.
    ) else (
        echo   [2/5] No NSSM service found ....... OK
    )
) else (
    echo   [2/5] No NSSM service found ....... OK
)

REM ── Step 3: Remove generated files ────────────────────────────

echo   [3/5] Removing generated files...
set REMOVED_COUNT=0

for %%f in (
    "%~dp0config.json"
    "%~dp0chess-uci-server.pid"
    "%~dp0server.log"
    "%~dp0connection.chessuci"
    "%~dp0cert.pem"
    "%~dp0key.pem"
    "%~dp0server_secret.key"
) do (
    if exist %%f (
        del /q %%f >nul 2>&1
        set /a REMOVED_COUNT+=1
    )
)

if exist "%~dp0logs" (
    rmdir /s /q "%~dp0logs" >nul 2>&1
    set /a REMOVED_COUNT+=1
)
if exist "%~dp0__pycache__" (
    rmdir /s /q "%~dp0__pycache__" >nul 2>&1
    set /a REMOVED_COUNT+=1
)

echo          Removed !REMOVED_COUNT! item^(s^).

REM ── Step 4: Remove Python dependencies ────────────────────────

echo   [4/5] Removing Python dependencies...
pip uninstall -y qrcode zeroconf miniupnpc >nul 2>&1
echo          Dependencies removed.

REM ── Step 5: Remove server directory ───────────────────────────

echo   [5/5] Server directory: %~dp0
echo.
set /p DELETE_DIR="  Delete the server directory and all contents? [y/N] "
if /i "!DELETE_DIR!"=="y" (
    echo.
    echo   Removing directory...
    cd /d "%USERPROFILE%"
    rmdir /s /q "%~dp0" >nul 2>&1
    if !errorlevel! equ 0 (
        echo   Directory removed.
    ) else (
        echo   Could not fully remove directory. Delete manually:
        echo     rmdir /s /q "%~dp0"
    )
) else (
    echo.
    echo   Directory kept. You can delete it manually:
    echo     rmdir /s /q "%~dp0"
)

REM ── Done ──────────────────────────────────────────────────────

echo.
echo   ===========================================
echo   Uninstall complete.
echo   ===========================================
echo.
pause
