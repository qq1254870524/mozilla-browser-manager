@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 (
  echo [ERROR] cannot cd to script dir
  pause
  exit /b 1
)
echo %CD% | findstr /I /C:"wsl.localhost" /C:"\\wsl\\" >nul
if not errorlevel 1 (
  echo [ERROR] Do NOT run from WSL UNC path.
  echo Use: C:\Users\zhang\Desktop\Mozilla
  pause
  exit /b 1
)
echo %CD% | findstr /I /C:"\Windows\System32" /C:"\Windows\SysWOW64" >nul
if not errorlevel 1 (
  echo [ERROR] Refuse to run under System32.
  pause
  exit /b 1
)
if not exist "app\mozilla_manager" (
  echo [ERROR] Not project root: %CD%
  pause
  exit /b 1
)
if not exist "scripts\win_actions.py" (
  echo [ERROR] missing scripts\win_actions.py
  pause
  exit /b 1
)
if not exist "scripts\install_all_deps.py" (
  echo [ERROR] missing scripts\install_all_deps.py
  pause
  exit /b 1
)
title Mozilla - Download deps
echo ============================================
echo   Download / Install deps
echo   ROOT: %CD%
echo ============================================
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -u "scripts\win_actions.py" install
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -u "scripts\win_actions.py" install
  ) else (
    where python >nul 2>nul
    if not errorlevel 1 (
      python -u "scripts\win_actions.py" install
    ) else (
      echo [ERROR] Python not found. Install Python 3.11+ first.
      echo https://www.python.org/downloads/
      pause
      exit /b 1
    )
  )
)
set EC=%ERRORLEVEL%
echo.
echo [DONE] exit code %EC%
echo.
pause
exit /b %EC%
