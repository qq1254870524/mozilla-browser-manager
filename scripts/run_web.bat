@echo off
setlocal EnableExtensions
cd /d "%~dp0.." 2>nul
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\win_actions.py" web
) else (
  python "scripts\win_actions.py" web
)
