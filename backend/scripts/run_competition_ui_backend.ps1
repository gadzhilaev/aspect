# Competition UI acceptance backend (stage 6.11).
# Ports from stand.env (default 8018). Does NOT use or free :8003.
# Does not kill foreign processes. Does not rewrite root .env / web/.env.

param(
    [string]$StandDir = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $StandDir) {
    $StandDir = Join-Path $RepoRoot "data\competition_stand\ui_acceptance_611"
} elseif (-not [System.IO.Path]::IsPathRooted($StandDir)) {
    $StandDir = Join-Path $RepoRoot $StandDir
}
$StandEnv = Join-Path $StandDir "stand.env"
$PidFile = Join-Path $StandDir "backend.pid"
$ApiPort = 8018

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
    Write-Host "Stand missing. Run first:"
    Write-Host "  python scripts/prepare_competition_ui_stand.py"
    exit 2
}

$stand = Read-DotEnv $StandEnv
if ($stand.ContainsKey("AGENT_DEMO_API_PORT") -and $stand["AGENT_DEMO_API_PORT"]) {
    $ApiPort = [int]$stand["AGENT_DEMO_API_PORT"]
}

Write-Host "=== Competition UI acceptance backend ==="
Write-Host "Stand: $StandDir"
Write-Host "API port: $ApiPort (not :8003)"
Write-Host "DB: $($stand['DATABASE_URL'])"

$pidOnPort = Get-PortOwner $ApiPort
if ($pidOnPort) {
    Write-Host "Port $ApiPort is already in use by PID $pidOnPort"
    Write-Host "Refusing to kill a foreign process. Free the port, then re-run."
    exit 1
}

foreach ($k in $stand.Keys) {
    if ($k -eq "HACKATHON_API_KEY") { continue }
    [Environment]::SetEnvironmentVariable($k, $stand[$k], "Process")
}

$root = Read-DotEnv (Join-Path $RepoRoot ".env")
$keyConfigured = $false
if ($root.ContainsKey("HACKATHON_API_KEY") -and $root["HACKATHON_API_KEY"]) {
    [Environment]::SetEnvironmentVariable("HACKATHON_API_KEY", $root["HACKATHON_API_KEY"], "Process")
    $keyConfigured = $true
}
Write-Host "hackathon_key_configured: $($keyConfigured.ToString().ToLower()) (not printed)"
Write-Host "competition_mode: $([Environment]::GetEnvironmentVariable('COMPETITION_MODE','Process'))"
Write-Host "assistant_provider: $([Environment]::GetEnvironmentVariable('ASSISTANT_PROVIDER','Process'))"
Write-Host "assistant_agent_loop: $([Environment]::GetEnvironmentVariable('ASSISTANT_AGENT_LOOP','Process'))"

$python = $null
if (Test-Path ".venv\Scripts\python.exe") {
    $python = (Resolve-Path ".venv\Scripts\python.exe").Path
} else {
    $python = (Get-Command python -ErrorAction Stop).Source
}

Write-Host "Starting uvicorn on http://127.0.0.1:$ApiPort ..."
$PID | Set-Content -Path $PidFile -Encoding ascii
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort
