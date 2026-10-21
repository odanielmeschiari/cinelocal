@echo off
rem Runs CineLocal straight from the project folder (without installing to the Start Menu).
setlocal EnableExtensions
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run

set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python 3 not found. Install it from https://www.python.org/downloads/windows/
    pause
    exit /b 1
)
%PY% -m venv .venv || goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto fail

:run
".venv\Scripts\python.exe" main.py %*
exit /b %errorlevel%

:fail
echo Installing the dependencies failed.
pause
exit /b 1
