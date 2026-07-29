@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
echo %SCRIPT_DIR% | findstr /I /C:"wsl.localhost" /C:"\\wsl\\" >nul
if not errorlevel 1 (
  echo [错误] 不要从 WSL 网络路径运行！
  echo 请打开: C:\Users\zhang\Desktop\Mozilla
  echo 先在 WSL 执行: cd /home/baoge/Mozilla ^&^& bash scripts/export_to_windows.sh
  pause
  exit /b 1
)
cd /d "%SCRIPT_DIR%" 2>nul
if errorlevel 1 (
  echo [错误] 无法进入脚本目录
  pause
  exit /b 1
)
echo %CD% | findstr /I /C:"\Windows\System32" /C:"\Windows\SysWOW64" >nul
if not errorlevel 1 (
  echo [错误] 当前目录是系统目录，已中止
  pause
  exit /b 1
)
if not exist "app\mozilla_manager" (
  echo [错误] 不是 Mozilla 项目目录: %CD%
  pause
  exit /b 1
)
title Mozilla - 启动客户端
echo ============================================
echo   启动客户端
echo   目录: %CD%
echo ============================================
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\win_actions.py" client
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 "scripts\win_actions.py" client
  ) else (
    python "scripts\win_actions.py" client
  )
)
exit /b %ERRORLEVEL%
