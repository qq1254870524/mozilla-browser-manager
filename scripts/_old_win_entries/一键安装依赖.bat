@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
echo %SCRIPT_DIR% | findstr /I /C:"wsl.localhost" /C:"\\wsl\\" >nul
if not errorlevel 1 (
  echo [ERROR] Do not run from WSL UNC. Use C:\Users\zhang\Desktop\Mozilla
  pause
  exit /b 1
)
cd /d "%SCRIPT_DIR%" 2>nul
call "%SCRIPT_DIR%install_windows_deps.bat" %*
