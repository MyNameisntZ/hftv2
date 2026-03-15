@echo off
setlocal

cd /d "%~dp0"

set "BOOTSTRAP_PYTHON="
if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
  goto :launch
)

where py >nul 2>nul
if not errorlevel 1 (
  set "BOOTSTRAP_PYTHON=py -3.11"
) else (
  where python >nul 2>nul
  if not errorlevel 1 (
    set "BOOTSTRAP_PYTHON=python"
  )
)

if "%BOOTSTRAP_PYTHON%"=="" (
  echo Python 3.11+ was not found.
  echo Install Python and try again.
  pause
  exit /b 1
)

echo Creating local virtual environment...
call %BOOTSTRAP_PYTHON% -m venv ".venv"
if errorlevel 1 (
  echo Failed to create .venv
  pause
  exit /b 1
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

echo Installing platform dependencies...
call "%PYTHON_EXE%" -m pip install --upgrade pip
call "%PYTHON_EXE%" -m pip install -r requirements.txt
call "%PYTHON_EXE%" -m pip install -e .
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)

:launch

echo Starting Local Trading Platform launcher...
echo This launcher can pull Git updates and restart the backend automatically.
echo.

"%PYTHON_EXE%" scripts\run_with_auto_update.py --open-browser

endlocal

