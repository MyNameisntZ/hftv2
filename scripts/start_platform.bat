@echo off
setlocal
cd /d %~dp0\..

if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe scripts\run_with_auto_update.py --open-browser
) else (
  call "Open Trading Platform.bat"
)

