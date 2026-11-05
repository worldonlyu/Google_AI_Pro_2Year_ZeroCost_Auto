@echo off
title Google AI Pro Provisioning Console - Setup
cd /d "%~dp0"

echo [1/2] Installing Python dependencies...
python -m pip install -r requirements.txt

echo.
echo [2/2] Starting console at http://127.0.0.1:8765 ...
start "" "http://127.0.0.1:8765"
python app.py
pause

