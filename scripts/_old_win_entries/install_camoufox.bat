@echo off
setlocal EnableExtensions
title Mozilla - Fetch Camoufox (mirrors + resume)
set "SCRIPT_DIR=%~dp0"
echo %SCRIPT_DIR% | findstr /I /C:"wsl.localhost" /C:"\\wsl\\" >nul
if not errorlevel 1 (
  echo [ERROR] Do not run from WSL UNC. Use C:\Users\zhang\Desktop\Mozilla
  pause
  exit /b 1
)
cd /d "%SCRIPT_DIR%" 2>nul
if errorlevel 1 (
  echo [ERROR] cannot cd to %SCRIPT_DIR%
  pause
  exit /b 1
)
if not exist "app\mozilla_manager" (
  echo [ERROR] not project root
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] missing .venv - run install_windows_deps.bat first
  pause
  exit /b 1
)
set "PYTHONPATH=%CD%\app"
set "XDG_CACHE_HOME=%CD%\runtime\cache"
set "MOZILLA_MANAGER_ROOT=%CD%"
echo ============================================
echo  Camoufox fetch with mirrors + resume
echo  ROOT=%CD%
echo  Official GitHub is slow; mirrors auto-tried.
echo  Partial downloads resume from tmp\*.part
echo ============================================
".venv\Scripts\python.exe" "scripts\fetch_camoufox.py" %*
echo.
pause
