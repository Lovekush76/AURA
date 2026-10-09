# Aura Assistant - Windows Zero-Residue Purge Script
$ErrorActionPreference = "SilentlyContinue"
$projectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ">>> AURA ZERO-RESIDUE PURGE ENGINE INITIALIZED (WINDOWS) <<<" -ForegroundColor Cyan
Write-Host "Target Root: $projectRoot" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Terminate background processes
Write-Host "[1/3] Terminating any running Aura background processes..." -ForegroundColor Yellow
Get-Process | Where-Object { $_.CommandLine -like "*aura*" -or $_.ProcessName -like "*aura*" } | Stop-Process -Force

# 2. Purge caches, run artifacts, logs, node_modules
Write-Host "[2/3] Purging caches, node_modules, logs, and artifacts..." -ForegroundColor Yellow
$targets = @(
    "$projectRoot\.venv",
    "$projectRoot\venv",
    "$projectRoot\frontend\node_modules",
    "$projectRoot\frontend\dist",
    "$projectRoot\run",
    "$projectRoot\data",
    "$projectRoot\logs",
    "$projectRoot\.pytest_cache",
    "$projectRoot\.ruff_cache",
    "$projectRoot\.mypy_cache"
)

foreach ($t in $targets) {
    if (Test-Path $t) {
        Write-Host "  Removing: $t"
        Remove-Item -Path $t -Recurse -Force | Out-Null
    }
}

# Recursively remove __pycache__
Get-ChildItem -Path $projectRoot -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force | Out-Null
Get-ChildItem -Path $projectRoot -Recurse -File -Filter "*.pyc" | Remove-Item -Force | Out-Null

Write-Host "[3/3] Purging project workspace files..." -ForegroundColor Yellow
Get-ChildItem -Path $projectRoot -Exclude "scripts" | Remove-Item -Recurse -Force | Out-Null

Write-Host "============================================================" -ForegroundColor Green
Write-Host ">>> ZERO-RESIDUE PURGE COMPLETE. SYSTEM RESTORED. <<<" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
