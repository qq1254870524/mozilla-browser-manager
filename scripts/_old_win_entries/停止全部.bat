@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
echo %SCRIPT_DIR% | findstr /I /C:"wsl.localhost" /C:"\wsl\" >nul
if not errorlevel 1 (
  echo [ERROR] Do not run from WSL UNC path.
  echo Use: C:\Users\zhang\Desktop\Mozilla\stop_all.bat
  pause
  exit /b 1
)
cd /d "%SCRIPT_DIR%" 2>nul
if errorlevel 1 (
  echo [ERROR] cannot cd to %SCRIPT_DIR%
  pause
  exit /b 1
)
call "%SCRIPT_DIR%stop_all.bat" %*
