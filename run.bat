@echo off
rem Executa o CineLocal direto da pasta do projeto (sem instalar no Menu Iniciar).
setlocal EnableExtensions
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run

set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python 3 nao encontrado. Instale em https://www.python.org/downloads/windows/
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
echo A instalacao das dependencias falhou.
pause
exit /b 1
