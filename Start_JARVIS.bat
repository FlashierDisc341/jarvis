@echo off
title JARVIS
rem Runs from wherever this file sits, so keep it in the Jarvis folder.
cd /d "%~dp0"
".venv-whisper\Scripts\python.exe" jarvis_whisper.py
echo.
echo JARVIS has stopped. Press any key to close this window.
pause >nul
