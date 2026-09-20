@echo off
title Academic Anki Deck Generator — Zero-Terminal UI Pipeline
cd /d "%~dp0"

echo =====================================================================
echo   ACADEMIC ANKI DECK GENERATOR — ZERO-TERMINAL UI PIPELINE
echo =====================================================================
echo.
echo Starting local UI server at http://localhost:5050...
echo Scanning classes from: H:\My Drive\Classes
echo.

if exist ".venv\Scripts\python.exe" (
    start "" http://localhost:5050
    ".venv\Scripts\python.exe" scripts\ui_server.py
) else (
    start "" http://localhost:5050
    python scripts\ui_server.py
)

pause
