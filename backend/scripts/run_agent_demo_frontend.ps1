# Start Vite for the agent-loop demo stand (stage 4.7).
# Port: 5177 only. Does NOT rewrite web/.env (sets VITE_API_BASE_URL in-process).
# Expects backend on :8017.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "resolve_front_root.ps1")
$WebRoot = Get-KonturFrontRoot
Set-Location $WebRoot

$StandDir = Join-Path $RepoRoot "data\agent_demo"
$StandWebEnv = Join-Path $StandDir "web.env"
$PidFile = Join-Path $StandDir "frontend.pid"
$WebPort = 5177
$ApiBase = "http://127.0.0.1:8017"

function Get-PortOwner([int]$Port) {
    $lines = netstat -ano | Select-String ":$Port\s+.*LISTENING"
    foreach ($line in $lines) {
        $parts = ($line.ToString() -split "\s+") | Where-Object { $_ -ne "" }
        if ($parts.Length -ge 5) {
            return [int]$parts[-1]
        }
    }
    return $null
}

function Read-DotEnv([string]$Path) {
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $k = $line.Substring(0, $eq).Trim()
        $v = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
        $map[$k] = $v
    }
    return $map
}

if (Test-Path $StandWebEnv) {
    $w = Read-DotEnv $StandWebEnv
    if ($w.ContainsKey("VITE_API_BASE_URL") -and $w["VITE_API_BASE_URL"]) {
        $ApiBase = $w["VITE_API_BASE_URL"].TrimEnd("/")
    }
}

Write-Host "=== Agent demo frontend ==="
Write-Host "Web root: $WebRoot"
Write-Host "Web port: $WebPort (ordinary demo stays on :5173)"
Write-Host "VITE_API_BASE_URL (process): $ApiBase"
Write-Host "Note: web/.env is NOT modified."

$pidOnPort = Get-PortOwner $WebPort
if ($pidOnPort) {
    Write-Host "Port $WebPort is already in use by PID $pidOnPort"
    Write-Host "Refusing to kill a foreign process or switch ports."
    exit 1
}

try {
    $health = Invoke-RestMethod -Uri "$ApiBase/health" -TimeoutSec 3
    Write-Host "API health: $($health.status) ($ApiBase)"
} catch {
    Write-Host "WARNING: API not reachable at $ApiBase/health"
    Write-Host "Start backend first: ..\scripts\run_agent_demo_backend.ps1"
}

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing npm dependencies..."
    npm install
}

$env:VITE_API_BASE_URL = $ApiBase
# Stage 4.8: demo entry panel (/agent-demo). Ordinary product builds leave this unset.
$env:VITE_AGENT_DEMO = "true"
if (Test-Path $StandWebEnv) {
    $w = Read-DotEnv $StandWebEnv
    if ($w.ContainsKey("VITE_AGENT_DEMO") -and $w["VITE_AGENT_DEMO"]) {
        $env:VITE_AGENT_DEMO = $w["VITE_AGENT_DEMO"]
    }
}
Write-Host "VITE_AGENT_DEMO (process): $($env:VITE_AGENT_DEMO)"
$PID | Set-Content -Path $PidFile -Encoding ascii
Write-Host "Starting Vite on http://127.0.0.1:$WebPort ..."
npm run dev -- --host 127.0.0.1 --port $WebPort --strictPort
