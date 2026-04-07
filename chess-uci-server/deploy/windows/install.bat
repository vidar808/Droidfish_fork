@echo off
setlocal enabledelayedexpansion
REM Chess UCI Server - Windows Installation Script
echo.
echo   Chess UCI Server - Windows Installer
echo   =====================================
echo.

REM ── Step 1: Check Python ────────────────────────────────────────

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERROR: Python is not installed or not in PATH.
    echo   Download Python from https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo   [1/4] Python %PYVER% .............. OK

REM ── Step 2: Install dependencies ────────────────────────────────

set DEP_OK=0
set DEP_FAIL=0
set MISSING_DEPS=

REM Try installing all at once first (fastest path)
pip install -q -r "%~dp0requirements.txt" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [2/4] Dependencies ................ OK
    goto :deps_done
)

REM Bulk install failed — check each dependency individually
for %%d in (qrcode zeroconf miniupnpc) do (
    python -c "import %%d" >nul 2>&1
    if errorlevel 1 (
        pip install -q %%d >nul 2>&1
        if errorlevel 1 (
            set /a DEP_FAIL+=1
            set "MISSING_DEPS=!MISSING_DEPS! %%d"
        ) else (
            set /a DEP_OK+=1
        )
    ) else (
        set /a DEP_OK+=1
    )
)

if %DEP_FAIL% equ 0 (
    echo   [2/4] Dependencies ................ OK
) else (
    echo   [2/4] Dependencies ................ PARTIAL
    echo         Failed to install:%MISSING_DEPS%
    echo         Features affected:
    for %%d in (%MISSING_DEPS%) do (
        if "%%d"=="qrcode" echo           - qrcode: QR pairing display unavailable
        if "%%d"=="zeroconf" echo           - zeroconf: mDNS auto-discovery disabled
        if "%%d"=="miniupnpc" echo           - miniupnpc: UPnP port mapping disabled
    )
    echo         Install manually: pip install%MISSING_DEPS%
)

:deps_done

REM ── Step 3: Generate config ─────────────────────────────────────

if not exist "%~dp0config.json" (
    copy "%~dp0example_config.json" "%~dp0config.json" >nul
    REM Generate a default auth token for security
    python -c "import json,secrets,sys; p=sys.argv[1]; f=open(p); cfg=json.load(f); f.close(); t=cfg.get('auth_token',''); cfg['auth_token']=(t if t else secrets.token_hex(16)); cfg['auth_method']='token'; f=open(p,'w'); json.dump(cfg,f,indent=2); f.close(); print('  Auth token: '+cfg['auth_token'])" "%~dp0config.json" 2>nul
    echo   [3/4] Config generated ............ OK
) else (
    echo   [3/4] Config exists ............... OK ^(kept existing^)
)

REM ── Check for engines ───────────────────────────────────────────

set ENGINE_COUNT=0
for %%f in ("%~dp0engines\*.exe") do set /a ENGINE_COUNT+=1

if %ENGINE_COUNT% equ 0 (
    echo.
    echo   NOTE: No engines found in engines\
    echo   Place your UCI engine .exe files there before starting.
    echo   Download Stockfish from: https://stockfishchess.org/download/
)

REM ── Step 4: Connectivity ────────────────────────────────────────

REM Read base_port from config (pass path via sys.argv to avoid backslash issues)
for /f %%p in ('python -c "import json,sys; f=open(sys.argv[1]); print(json.load(f).get('base_port',9998))" "%~dp0config.json" 2^>nul') do set BASE_PORT=%%p
if not defined BASE_PORT set BASE_PORT=9998

echo.
echo   [4/4] Connectivity
echo   How will clients connect?
echo     1^) LAN only     - mDNS + UPnP auto-discovery ^(default^)
echo     2^) Open firewall - Auto-opens port %BASE_PORT% for external access
echo     3^) Relay mode    - No port forwarding needed
set /p CONN_CHOICE="  Select [1]: "
if not defined CONN_CHOICE set CONN_CHOICE=1

if "!CONN_CHOICE!"=="2" (
    echo   Opening port %BASE_PORT% in Windows Firewall...
    netsh advfirewall firewall add rule name="Chess UCI Server" dir=in action=allow protocol=TCP localport=%BASE_PORT% >nul 2>&1
    if !errorlevel! equ 0 (
        echo   Firewall rule added for port %BASE_PORT%
    ) else (
        echo   WARNING: Failed to add firewall rule.
        echo   Try running this installer as Administrator.
    )
    echo   [4/4] Firewall ...................... OK
    goto :conn_done
)

if "!CONN_CHOICE!"=="3" goto :do_relay
goto :conn_lan

:do_relay
set RELAY_URL=spacetosurf.com
set /p RELAY_URL="  Relay server URL [spacetosurf.com]: "
if "!RELAY_URL!"=="" set RELAY_URL=spacetosurf.com
set RELAY_PORT=19000
set /p RELAY_PORT="  Relay port [19000]: "
if "!RELAY_PORT!"=="" set RELAY_PORT=19000

python -c "import json,secrets,sys; p=sys.argv[1]; f=open(p); cfg=json.load(f); f.close(); cfg['relay_server_url']=sys.argv[2]; cfg['relay_server_port']=int(sys.argv[3]); cfg['enable_upnp']=False; cfg['enable_single_port']=True; s=cfg.get('server_secret',''); cfg['server_secret']=(s if len(s)>=32 else secrets.token_hex(32)); f=open(p,'w'); json.dump(cfg,f,indent=2); f.close(); print('  Relay: '+cfg['relay_server_url']+':'+str(cfg['relay_server_port']))" "%~dp0config.json" "!RELAY_URL!" "!RELAY_PORT!"
if errorlevel 1 echo   WARNING: Failed to update config with relay settings
echo   [4/4] Relay mode .................... OK
goto :conn_done

:conn_lan
echo   [4/4] LAN mode ...................... OK

:conn_done

REM ── Done ────────────────────────────────────────────────────────

echo.
echo   ===========================================
echo   Installation complete^!
echo   ===========================================
echo.

set /p START_NOW="  Start server now with QR pairing? [Y/n] "
if /i "!START_NOW!"=="n" (
    echo.
    echo   To start later, run:
    echo     cd %~dp0
    echo     python chess.py --pair
    echo.
    echo   Or use the interactive setup wizard:
    echo     python chess.py --setup
    echo.
    pause
    exit /b 0
)

echo.
echo   Starting server with QR pairing...
echo.
cd /d "%~dp0"
python chess.py --pair
