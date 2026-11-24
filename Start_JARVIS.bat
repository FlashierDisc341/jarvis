@echo off
title JARVIS
cd /d "%~dp0"

echo Checking for updates...
git pull --ff-only
if errorlevel 1 (
    echo Update check failed - starting the version you already have.
) else (
    echo Making sure packages are up to date...
    ".venv-whisper\Scripts\python.exe" -m pip install -q -r requirements.txt
)

echo.
".venv-whisper\Scripts\python.exe" jarvis_whisper.py
echo.
echo JARVIS has stopped. Press any key to close this window.
pause >nul
