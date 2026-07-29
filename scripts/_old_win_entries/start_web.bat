@echo off
setlocal EnableExtensions
title Mozilla Browser Manager - Web

REM ---- ROOT guard: never run from WSL UNC or fall into System32 ----
set "SCRIPT_DIR=%~dp0"
echo %SCRIPT_DIR% | findstr /I /C:"wsl.localhost" /C:"\\wsl\\" >nul
if not errorlevel 1 (
  echo.
  echo [ERROR] You started this bat from a WSL UNC path:
  echo   %SCRIPT_DIR%
  echo.
  echo CMD cannot use UNC as current directory, so it would
  echo wrongly use C:\Windows\System32 and create files there.
  echo.
  echo DO NOT run bats under:
  echo   \\wsl.localhost\Ubuntu\home\baoge\Mozilla
  echo.
  echo That folder is DEV-only ^(edit in WSL^).
  echo For Windows use/test, open and run bats in:
  echo   C:\Users\zhang\Desktop\Mozilla
  echo.
  echo Sync from WSL first:
  echo   cd /home/baoge/Mozilla
  echo   bash scripts/export_to_windows.sh
  echo.
  pause
  exit /b 1
)

cd /d "%SCRIPT_DIR%" 2>nul
if errorlevel 1 (
  echo [ERROR] cannot cd to script directory:
  echo   %SCRIPT_DIR%
  echo Use local path C:\Users\zhang\Desktop\Mozilla
  pause
  exit /b 1
)

REM reject if still on UNC after cd
echo %CD% | findstr /B /C:"\\" >nul
if not errorlevel 1 (
  echo [ERROR] Working dir is still UNC: %CD%
  echo Use C:\Users\zhang\Desktop\Mozilla
  pause
  exit /b 1
)

REM reject System32 / Windows directory disaster
echo %CD% | findstr /I /C:"\Windows\System32" /C:"\Windows\SysWOW64" /C:"\Windows\" >nul
if not errorlevel 1 (
  echo [ERROR] Working dir is system folder: %CD%
  echo Aborting to avoid creating .venv under Windows.
  echo Run bats from C:\Users\zhang\Desktop\Mozilla
  pause
  exit /b 1
)

REM require expected project markers
if not exist "%CD%\app\mozilla_manager" (
  echo [ERROR] Not a Mozilla project root: %CD%
  echo Missing app\mozilla_manager
  echo Use C:\Users\zhang\Desktop\Mozilla
  pause
  exit /b 1
)
if not exist "%CD%\requirements.txt" (
  echo [ERROR] Missing requirements.txt in %CD%
  pause
  exit /b 1
)

echo ============================================
echo  Mozilla Browser Manager - Web UI
echo  http://127.0.0.1:17888
echo  ROOT=%CD%
echo ============================================

if exist ".venv\Scripts\python.exe" goto :venv_ok
echo [1/3] Creating .venv ...
py -3.12 -m venv .venv
if errorlevel 1 py -3.11 -m venv .venv
if errorlevel 1 py -3 -m venv .venv
if errorlevel 1 python -m venv .venv
if errorlevel 1 (
  echo [ERROR] Python 3.11+ not found.
  pause
  exit /b 1
)
:venv_ok

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERROR] failed to activate .venv
  pause
  exit /b 1
)

python -c "import fastapi,uvicorn" 1>nul 2>nul
if errorlevel 1 (
  echo [2/3] Installing requirements.txt ...
  python -m pip install -U pip
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] pip install failed. Try install_windows_deps.bat first.
    pause
    exit /b 1
  )
)

set "PYTHONPATH=%CD%\app"
set "PLAYWRIGHT_BROWSERS_PATH=%CD%\runtime\browsers"
set "XDG_CACHE_HOME=%CD%\runtime\cache"
set "XDG_CONFIG_HOME=%CD%\runtime\xdg-config"
set "XDG_DATA_HOME=%CD%\runtime\xdg-data"
set "MOZILLA_MANAGER_ROOT=%CD%"

if not exist "runtime\browsers" mkdir "runtime\browsers"
if not exist "logs" mkdir "logs"
if not exist "runtime" mkdir "runtime"

echo [3/3] Starting Web: http://127.0.0.1:17888
echo Stop: double-click stop_web.bat   or close this window
echo Tip: use start_client.bat for close-window = full stop.
echo.
python -m mozilla_manager.web %*
set "EC=%ERRORLEVEL%"
echo.
echo [exit code] %EC%
pause
endlocal & exit /b %EC%
