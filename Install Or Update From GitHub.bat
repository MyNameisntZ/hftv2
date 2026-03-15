@echo off
setlocal
cd /d "%~dp0"

powershell -ExecutionPolicy Bypass -File "scripts\bootstrap_from_github.ps1" %*

endlocal
