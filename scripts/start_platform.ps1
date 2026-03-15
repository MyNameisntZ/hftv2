$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Test-Path ".venv\Scripts\python.exe") {
    & ".venv\Scripts\python.exe" "scripts/run_with_auto_update.py" "--open-browser"
} else {
    & ".\Open Trading Platform.bat"
}

