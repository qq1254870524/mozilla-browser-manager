@echo off
setlocal EnableExtensions
title Mozilla - Stop Web

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
echo  Stop Mozilla Web  (port 17888)
echo  ROOT=%CD%
echo ============================================

if not exist "runtime" mkdir "runtime"
if not exist "logs" mkdir "logs"

if exist "runtime\mozilla-web.pid" (
  set /p WPID=<"runtime\mozilla-web.pid"
  if defined WPID (
    echo [1] taskkill pid file %WPID%
    taskkill /F /PID %WPID% 2>nul
  )
  del /f /q "runtime\mozilla-web.pid" 2>nul
)
if exist "logs\web.pid" (
  set /p WPID2=<"logs\web.pid"
  if defined WPID2 (
    echo [1b] taskkill logs\web.pid %WPID2%
    taskkill /F /PID %WPID2% 2>nul
  )
  del /f /q "logs\web.pid" 2>nul
)

echo [2] PowerShell sweep port 17888 + mozilla_manager.web ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue';" ^
  "$killed=@();" ^
  "try { Get-NetTCPConnection -LocalPort 17888 -State Listen | ForEach-Object { $killed += $_.OwningProcess; Stop-Process -Id $_.OwningProcess -Force } } catch {};" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|uvicorn' -and $_.CommandLine -and ( $_.CommandLine -match 'mozilla_manager\.web' -or $_.CommandLine -match 'uvicorn.*mozilla_manager' -or ($_.CommandLine -match '17888' -and $_.CommandLine -match 'mozilla_manager') ) } | ForEach-Object { $killed += $_.ProcessId; Stop-Process -Id $_.ProcessId -Force };" ^
  "$u=$killed | Select-Object -Unique; if($u){ $u | ForEach-Object { Write-Host ('  killed pid=' + $_) } } else { Write-Host '  no web process found' }"

echo [3] netstat fallback ...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":17888" ^| findstr "LISTENING"') do (
  echo   taskkill /F /PID %%P
  taskkill /F /PID %%P 2>nul
)

echo.
echo [DONE] Web stop finished.
pause
endlocal
