@echo off
rem Removes CineLocal. Use "uninstall.bat --purge" to also delete the library, posters and settings.
setlocal EnableExtensions
if exist "%LOCALAPPDATA%\Programs\cinelocal" rmdir /s /q "%LOCALAPPDATA%\Programs\cinelocal"
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\CineLocal.lnk" del /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\CineLocal.lnk"
if /i "%~1"=="--purge" goto purge
echo Removed. Your data is still in %LOCALAPPDATA%\cinelocal (use --purge to delete it).
exit /b 0

:purge
if exist "%APPDATA%\cinelocal" rmdir /s /q "%APPDATA%\cinelocal"
if exist "%LOCALAPPDATA%\cinelocal" rmdir /s /q "%LOCALAPPDATA%\cinelocal"
echo Removed, including data and settings.
exit /b 0
