@echo off
title JARVIS Installer
setlocal

rem ===== FlashierDisc341 =====
set REPO=https://github.com/YOUR_GITHUB_NAME/jarvis.git
rem =================================================

set TARGET=%USERPROFILE%\Jarvis

echo.
echo  JARVIS installer
echo  He will be installed in: %TARGET%
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo Git is not installed.
    echo Get it from https://git-scm.com/download/win ^(default options are fine^), then run this again.
    pause
    exit /b
)

rem JARVIS's packages are matched to Python 3.14, so find exactly that version
set PY=
py -3.14 --version >nul 2>&1
if not errorlevel 1 set PY=py -3.14
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,14) else 1)" >nul 2>&1
    if not errorlevel 1 set PY=python
)
if not defined PY (
    echo Python 3.14 is not installed.
    echo Get Python 3.14 from https://www.python.org/downloads/ - NOT a newer one -
    echo and CHECK "Add python.exe to PATH" in the installer.
    pause
    exit /b
)

if exist "%TARGET%\.git" (
    echo JARVIS is already installed. Just use Start_JARVIS.bat in that folder, it updates itself.
    pause
    exit /b
)

echo Downloading JARVIS... (a GitHub login window may pop up the first time)
git clone %REPO% "%TARGET%"
if errorlevel 1 (
    echo.
    echo Download failed. Make sure you accepted the GitHub invite and logged in.
    pause
    exit /b
)

cd /d "%TARGET%"

echo.
echo Setting up Python environment...
%PY% -m venv .venv-whisper
if errorlevel 1 (
    echo Could not create the environment.
    pause
    exit /b
)

echo.
echo Installing packages. This is a big download (around 2 GB), it can take a while...
".venv-whisper\Scripts\python.exe" -m pip install --upgrade pip
".venv-whisper\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Package install failed. Screenshot this window and send it to Disc.
    pause
    exit /b
)

echo.
echo Almost done. Pick your microphone:
".venv-whisper\Scripts\python.exe" -c "import jarvis_config"

echo.
echo ============================================
echo  JARVIS is installed!
echo  Start him with Start_JARVIS.bat in:
echo  %TARGET%
echo  (right-click it - Send to - Desktop for a shortcut)
echo ============================================
start "" "%TARGET%"
pause
