@echo off
rem Instala o CineLocal para o usuario atual (Windows 10/11).
rem Cria um ambiente virtual com o PySide6 e um atalho no Menu Iniciar.
setlocal EnableExtensions
set "SRC=%~dp0"
set "PREFIX=%LOCALAPPDATA%\Programs\cinelocal"
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\CineLocal.lnk"

echo ==^> Procurando o Python 3
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY goto nopython

echo ==^> Copiando arquivos para %PREFIX%
if not exist "%PREFIX%" mkdir "%PREFIX%"
if exist "%PREFIX%\cinelocal" rmdir /s /q "%PREFIX%\cinelocal"
if exist "%PREFIX%\assets" rmdir /s /q "%PREFIX%\assets"
xcopy /e /i /y /q "%SRC%cinelocal" "%PREFIX%\cinelocal" >nul || goto fail
xcopy /e /i /y /q "%SRC%assets" "%PREFIX%\assets" >nul || goto fail
copy /y "%SRC%main.py" "%PREFIX%\" >nul || goto fail
copy /y "%SRC%requirements.txt" "%PREFIX%\" >nul || goto fail
for /d /r "%PREFIX%" %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"

echo ==^> Criando ambiente virtual e instalando PySide6 (precisa de internet, ~200 MB)
if not exist "%PREFIX%\venv\Scripts\python.exe" %PY% -m venv "%PREFIX%\venv" || goto fail
"%PREFIX%\venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"%PREFIX%\venv\Scripts\python.exe" -m pip install -r "%PREFIX%\requirements.txt" || goto fail

echo ==^> Criando atalho no Menu Iniciar
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%'); $s.TargetPath='%PREFIX%\venv\Scripts\pythonw.exe'; $s.Arguments='\"%PREFIX%\main.py\"'; $s.WorkingDirectory='%PREFIX%'; $s.IconLocation='%PREFIX%\assets\cinelocal.ico'; $s.Description='CineLocal'; $s.Save()" || goto fail

echo.
echo Pronto! Abra o CineLocal pelo Menu Iniciar (digite "CineLocal").
pause
exit /b 0

:nopython
echo.
echo Python 3 nao encontrado. Instale em https://www.python.org/downloads/windows/
echo (versao 3.10 a 3.12, marcando "Add python.exe to PATH") e rode este script de novo.
pause
exit /b 1

:fail
echo.
echo A instalacao falhou. Veja as mensagens acima.
pause
exit /b 1
