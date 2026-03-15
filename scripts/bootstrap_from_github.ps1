$ErrorActionPreference = "Stop"

$repoUrl = "https://github.com/MyNameisntZ/hftv2.git"
$defaultInstallDir = Join-Path $env:USERPROFILE "Desktop\HFT-Bot-2.0"
$installDir = if ($args.Count -gt 0 -and $args[0]) { $args[0] } else { $defaultInstallDir }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git is required but was not found on this machine."
    exit 1
}

if (Test-Path $installDir) {
    if (Test-Path (Join-Path $installDir ".git")) {
        Write-Host "Existing clone found. Pulling latest changes..."
        Set-Location $installDir
        git fetch --all --prune
        git pull --ff-only
    } else {
        Write-Host "Target folder exists but is not a git clone: $installDir"
        exit 1
    }
} else {
    $parentDir = Split-Path -Parent $installDir
    if (-not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir | Out-Null
    }
    Write-Host "Cloning trading platform from GitHub..."
    git clone $repoUrl $installDir
}

Set-Location $installDir
& ".\Open Trading Platform.bat"
