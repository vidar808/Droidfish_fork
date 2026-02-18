@echo off
REM Chess UCI Server - Show Pairing QR Code
REM Generates a QR code for adding new clients without restarting the server.
echo.
echo   Chess UCI Server - Pairing QR
echo   =============================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERROR: Python is not installed or not in PATH.
    pause
    exit /b 1
)

if not exist "%~dp0chess.py" (
    echo   ERROR: chess.py not found.
    pause
    exit /b 1
)

if not exist "%~dp0config.json" (
    echo   ERROR: config.json not found.
    pause
    exit /b 1
)

cd /d "%~dp0"
python chess.py --pair --pair-only
echo.
pause
