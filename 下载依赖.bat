@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
echo %SCRIPT_DIR% | findstr /I /C:"wsl.localhost" /C:"\\wsl\\" >nul
if not errorlevel 1 (
  echo [] Ҫ WSL ·У
  echo : C:\Users\zhang\Desktop\Mozilla
  echo  WSL ִ: cd /home/baoge/Mozilla ^&^& bash scripts/export_to_windows.sh
  pause
  exit /b 1
)
cd /d "%SCRIPT_DIR%" 2>nul
if errorlevel 1 (
  echo [] ޷űĿ¼
  pause
  exit /b 1
)
echo %CD% | findstr /I /C:"\Windows\System32" /C:"\Windows\SysWOW64" >nul
if not errorlevel 1 (
  echo [] ǰĿ¼ϵͳĿ¼ֹ
  pause
  exit /b 1
)
if not exist "app\mozilla_manager" (
  echo []  Mozilla ĿĿ¼: %CD%
  pause
  exit /b 1
)
title Mozilla - 
echo ============================================
echo   
echo   Ŀ¼: %CD%
echo ============================================
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\win_actions.py" install
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 "scripts\win_actions.py" install
  ) else (
    python "scripts\win_actions.py" install
  )
)
exit /b %ERRORLEVEL%
