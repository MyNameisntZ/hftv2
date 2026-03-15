$ErrorActionPreference = "Stop"

$repoUrl = "https://github.com/MyNameisntZ/hftv2.git"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git is required but was not found on this machine."
    exit 1
}

if (-not (Test-Path ".git")) {
    git init
}

$hasOrigin = git remote 2>$null | Select-String -SimpleMatch "origin"
if (-not $hasOrigin) {
    git remote add origin $repoUrl
} else {
    git remote set-url origin $repoUrl
}

git add .

try {
    git diff --cached --quiet
    $hasChanges = $LASTEXITCODE -ne 0
} catch {
    $hasChanges = $true
}

if ($hasChanges) {
    git commit -m "Initial platform publish"
}

git branch -M main
git push -u origin main
