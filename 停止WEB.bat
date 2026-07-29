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
  echo [ERROR] Refuse to run under System32. Copy project to Desktop first.
  pause
  exit /b 1
)
if not exist "app\mozilla_manager" (
  echo [ERROR] Not project root: %CD%
  pause
  exit /b 1
)
title Mozilla - Stop WEB
echo ============================================
echo   Stop WEB
echo   ROOT: %CD%
echo ============================================
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -u "scripts\win_actions.py" stop
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -u "scripts\win_actions.py" stop
  ) else (
    python -u "scripts\win_actions.py" stop
  )
)
set EC=%ERRORLEVEL%
if not "%EC%"=="0" pause
exit /b %EC%
