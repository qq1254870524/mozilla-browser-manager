@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
if not exist ".venv\Scripts\activate.bat" (
  echo [ERROR] Missing .venv. Run install_windows_deps.bat first.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
set "PYTHONPATH=%CD%\app"
set "PLAYWRIGHT_BROWSERS_PATH=%CD%\runtime\browsers"
set "XDG_CACHE_HOME=%CD%\runtime\cache"
set "MOZILLA_MANAGER_ROOT=%CD%"
python -m mozilla_manager.cli %*
