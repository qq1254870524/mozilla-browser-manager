@echo off
setlocal EnableExtensions
title Mozilla - One-click dual-end deps (auto OS)

REM ---- ROOT guard: never run from WSL UNC or fall into System32 ----
set "SCRIPT_DIR=%~dp0"
echo %SCRIPT_DIR% | findstr /I /C:"wsl.localhost" /C:"\\wsl\\" >nul
if not errorlevel 1 (
  echo.
  echo [ERROR] Do not run bats from WSL UNC path:
  echo   %SCRIPT_DIR%
  echo.
  echo DEV only: \\wsl.localhost\Ubuntu\home\baoge\Mozilla
  echo RUN on Windows: C:\Users\zhang\Desktop\Mozilla
  echo.
  echo Sync first in WSL:
  echo   cd /home/baoge/Mozilla
  echo   bash scripts/export_to_windows.sh
  echo.
  pause
  exit /b 1
)

cd /d "%SCRIPT_DIR%" 2>nul
if errorlevel 1 (
  echo [ERROR] cannot cd to script directory: %SCRIPT_DIR%
  echo Use local path C:\Users\zhang\Desktop\Mozilla
  pause
  exit /b 1
)

echo %CD% | findstr /B /C:"\\" >nul
if not errorlevel 1 (
  echo [ERROR] Working dir is still UNC: %CD%
  echo Use C:\Users\zhang\Desktop\Mozilla
  pause
  exit /b 1
)

echo %CD% | findstr /I /C:"\Windows\System32" /C:"\Windows\SysWOW64" >nul
if not errorlevel 1 (
  echo [ERROR] Working dir is system folder: %CD%
  echo Aborting.
  pause
  exit /b 1
)

if not exist "%CD%\app\mozilla_manager" (
  echo [ERROR] Not a Mozilla project root: %CD%
  pause
  exit /b 1
)
if not exist "%CD%\requirements.txt" (
  echo [ERROR] Missing requirements.txt in %CD%
  pause
  exit /b 1
)
if not exist "%CD%\scripts\install_all_deps.py" (
  echo [ERROR] Missing scripts\install_all_deps.py
  echo Re-export from WSL: bash scripts/export_to_windows.sh
  pause
  exit /b 1
)

echo ============================================
echo  One-click install deps (auto by OS)
echo  Shared pip pkgs + this-OS browsers/mihomo
echo  ROOT=%CD%
echo ============================================

if exist ".venv\Scripts\python.exe" goto :have_venv
echo [pre] Creating Windows .venv ...
py -3.12 -m venv .venv
if errorlevel 1 py -3.11 -m venv .venv
if errorlevel 1 py -3 -m venv .venv
if errorlevel 1 python -m venv .venv
if errorlevel 1 (
  echo [ERROR] Python 3.11+ required. https://www.python.org/downloads/
  echo         Enable: Add python.exe to PATH
  pause
  exit /b 1
)
:have_venv

echo [pre] Running scripts\install_all_deps.py ...
".venv\Scripts\python.exe" "scripts\install_all_deps.py" %*
set "EC=%ERRORLEVEL%"
echo.
if not "%EC%"=="0" (
  echo [ERROR] install_all_deps exit %EC%
  pause
  exit /b %EC%
)
echo [DONE] Deps ready for Windows.
echo Next: start_client.bat
pause
endlocal & exit /b 0
