@echo off
rem Remove o CineLocal. Use "uninstall.bat --purge" para apagar tambem biblioteca, capas e configuracoes.
setlocal EnableExtensions
if exist "%LOCALAPPDATA%\Programs\cinelocal" rmdir /s /q "%LOCALAPPDATA%\Programs\cinelocal"
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\CineLocal.lnk" del /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\CineLocal.lnk"
if /i "%~1"=="--purge" goto purge
echo Removido. Seus dados continuam em %LOCALAPPDATA%\cinelocal (use --purge para apagar).
exit /b 0

:purge
if exist "%APPDATA%\cinelocal" rmdir /s /q "%APPDATA%\cinelocal"
if exist "%LOCALAPPDATA%\cinelocal" rmdir /s /q "%LOCALAPPDATA%\cinelocal"
echo Removido, incluindo dados e configuracoes.
exit /b 0
