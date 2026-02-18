@echo off
REM Stop the Chess UCI Server
cd /d "%~dp0"
python chess.py --stop
