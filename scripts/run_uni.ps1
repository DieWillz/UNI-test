$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

Write-Host "Starting UNI with Python 3.12..." -ForegroundColor Cyan
py -3.12 -m uni @args
