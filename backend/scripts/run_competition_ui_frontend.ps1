# Competition UI acceptance frontend (stage 6.11).
# Port from stand (default 5178). Does NOT rewrite web/.env.

param(
    [string]$StandDir = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "resolve_front_root.ps1")
$WebRoot = Get-KonturFrontRoot
Set-Location $WebRoot

if (-not $StandDir) {
    $StandDir = Join-Path $RepoRoot "data\competition_stand\ui_acceptance_611"
} elseif (-not [System.IO.Path]::IsPathRooted($StandDir)) {
    $StandDir = Join-Path $RepoRoot $StandDir
}
$StandWebEnv = Join-Path $StandDir "web.env"
$StandEnv = Join-Path $StandDir "stand.env"
$PidFile = Join-Path $StandDir "frontend.pid"
$WebPort = 5178
$ApiBase = "http://127.0.0.1:8018"

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

if (-not (Test-Path $StandEnv)) {
    Write-Host "Stand missing. Run: python scripts/prepare_competition_ui_stand.py"
    exit 2
}

$stand = Read-DotEnv $StandEnv
if ($stand.ContainsKey("AGENT_DEMO_WEB_PORT") -and $stand["AGENT_DEMO_WEB_PORT"]) {
    $WebPort = [int]$stand["AGENT_DEMO_WEB_PORT"]
}
if ($stand.ContainsKey("AGENT_DEMO_API_PORT") -and $stand["AGENT_DEMO_API_PORT"]) {
    $ApiBase = "http://127.0.0.1:$($stand['AGENT_DEMO_API_PORT'])"
}
if (Test-Path $StandWebEnv) {
    $w = Read-DotEnv $StandWebEnv
    if ($w.ContainsKey("VITE_API_BASE_URL") -and $w["VITE_API_BASE_URL"]) {
        $ApiBase = $w["VITE_API_BASE_URL"].TrimEnd("/")
    }
}

Write-Host "=== Competition UI acceptance frontend ==="
Write-Host "Web port: $WebPort (not ordinary :5173)"
Write-Host "VITE_API_BASE_URL (process): $ApiBase"

$pidOnPort = Get-PortOwner $WebPort
if ($pidOnPort) {
    Write-Host "Port $WebPort is already in use by PID $pidOnPort"
    exit 1
}

try {
    $null = Invoke-RestMethod -Uri "$ApiBase/health" -TimeoutSec 3
    Write-Host "API health: ok"
} catch {
    Write-Host "WARNING: API not reachable at $ApiBase/health - start backend first"
}

if (-not (Test-Path "node_modules")) {
    npm install
}

$env:VITE_API_BASE_URL = $ApiBase
$env:VITE_AGENT_DEMO = "true"
$PID | Set-Content -Path $PidFile -Encoding ascii
Write-Host "Starting Vite on http://127.0.0.1:$WebPort"
npm run dev -- --host 127.0.0.1 --port $WebPort --strictPort
