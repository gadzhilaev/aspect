# Start Aspect Vite web app pointed at local API.
# Does not kill foreign processes on :5173.

$ErrorActionPreference = "Stop"
$WebRoot = $PSScriptRoot
Set-Location $WebRoot

$EnvFile = Join-Path $WebRoot ".env"
$Example = Join-Path $WebRoot ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $Example) {
        Copy-Item $Example $EnvFile
        Write-Host "Created frontend/.env from .env.example"
    }
}

$apiBase = "http://127.0.0.1:8003"
if (Test-Path $EnvFile) {
    $line = Get-Content $EnvFile | Where-Object { $_ -match "^\s*VITE_API_BASE_URL\s*=" } | Select-Object -First 1
    if ($line) {
        $apiBase = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
    }
}

Write-Host "Web root: $WebRoot"
Write-Host "VITE_API_BASE_URL => $apiBase"

try {
    $health = Invoke-RestMethod -Uri "$apiBase/health" -TimeoutSec 3
    Write-Host "API health: $($health.status) ($apiBase)"
} catch {
    Write-Host "WARNING: API not reachable at $apiBase/health"
    Write-Host "Start backend first:  ..\backend\scripts\run_backend.ps1"
}

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing npm dependencies..."
    npm install
}

Write-Host "Starting Vite on http://127.0.0.1:5173 ..."
npm run dev -- --host 127.0.0.1 --port 5173
