@echo off
rem Installs CineLocal for the current user (Windows 10/11).
rem Creates a virtual environment with PySide6 and a Start Menu shortcut.
setlocal EnableExtensions
set "SRC=%~dp0"
set "PREFIX=%LOCALAPPDATA%\Programs\cinelocal"
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\CineLocal.lnk"

echo ==^> Looking for Python 3
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY goto nopython

echo ==^> Copying files to %PREFIX%
if not exist "%PREFIX%" mkdir "%PREFIX%"
if exist "%PREFIX%\cinelocal" rmdir /s /q "%PREFIX%\cinelocal"
if exist "%PREFIX%\assets" rmdir /s /q "%PREFIX%\assets"
xcopy /e /i /y /q "%SRC%cinelocal" "%PREFIX%\cinelocal" >nul || goto fail
xcopy /e /i /y /q "%SRC%assets" "%PREFIX%\assets" >nul || goto fail
copy /y "%SRC%main.py" "%PREFIX%\" >nul || goto fail
copy /y "%SRC%requirements.txt" "%PREFIX%\" >nul || goto fail
for /d /r "%PREFIX%" %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"

echo ==^> Creating the virtual environment and installing PySide6 (needs internet, ~200 MB)
if not exist "%PREFIX%\venv\Scripts\python.exe" %PY% -m venv "%PREFIX%\venv" || goto fail
"%PREFIX%\venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"%PREFIX%\venv\Scripts\python.exe" -m pip install -r "%PREFIX%\requirements.txt" || goto fail

echo ==^> Creating the Start Menu shortcut
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%'); $s.TargetPath='%PREFIX%\venv\Scripts\pythonw.exe'; $s.Arguments='\"%PREFIX%\main.py\"'; $s.WorkingDirectory='%PREFIX%'; $s.IconLocation='%PREFIX%\assets\cinelocal.ico'; $s.Description='CineLocal'; $s.Save()" || goto fail

if not exist "%ProgramFiles%\VideoLAN\VLC\libvlc.dll" echo WARNING: VLC not found. To use the built-in player, install 64-bit VLC: winget install VideoLAN.VLC
echo.
echo Done! Open CineLocal from the Start Menu (type "CineLocal").
pause
exit /b 0

:nopython
echo.
echo Python 3 not found. Install it from https://www.python.org/downloads/windows/
echo (version 3.10 to 3.12, checking "Add python.exe to PATH") and run this script again.
pause
exit /b 1

:fail
echo.
echo The installation failed. See the messages above.
pause
exit /b 1
