# Start Aspect API for the agent-loop demo stand (stage 4.7).
# Ports: 8017 only. Does NOT use or free :8003.
# Does not kill foreign processes. Does not rewrite root .env / web/.env.
# HACKATHON_API_KEY is read from root .env into process env (never printed).

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$StandDir = Join-Path $RepoRoot "data\agent_demo"
$StandEnv = Join-Path $StandDir "stand.env"
$PidFile = Join-Path $StandDir "backend.pid"
$ApiPort = 8017

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
    Write-Host "Stand profile missing. Run first:"
    Write-Host "  python scripts/prepare_agent_demo_stand.py"
    exit 2
}

$stand = Read-DotEnv $StandEnv
if ($stand.ContainsKey("AGENT_DEMO_API_PORT") -and $stand["AGENT_DEMO_API_PORT"]) {
    $ApiPort = [int]$stand["AGENT_DEMO_API_PORT"]
}

Write-Host "=== Agent demo backend ==="
Write-Host "Repo: $RepoRoot"
Write-Host "API port: $ApiPort (stand-only; ordinary demo stays on :8003)"
Write-Host "DB: $($stand['DATABASE_URL'])"

$pidOnPort = Get-PortOwner $ApiPort
if ($pidOnPort) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pidOnPort" -ErrorAction SilentlyContinue
    $cmd = if ($proc) { $proc.CommandLine } else { "(unknown)" }
    Write-Host "Port $ApiPort is already in use by PID $pidOnPort"
    Write-Host "  $cmd"
    Write-Host "Refusing to kill a foreign process or switch ports."
    Write-Host "Free the port manually, then re-run this script."
    exit 1
}

# Apply stand profile to process env (non-secret fields).
foreach ($k in $stand.Keys) {
    if ($k -eq "HACKATHON_API_KEY") { continue }
    [Environment]::SetEnvironmentVariable($k, $stand[$k], "Process")
}

# Pull API key from root .env only — never from stand files / never print.
$root = Read-DotEnv (Join-Path $RepoRoot ".env")
$keyConfigured = $false
if ($root.ContainsKey("HACKATHON_API_KEY") -and $root["HACKATHON_API_KEY"]) {
    [Environment]::SetEnvironmentVariable("HACKATHON_API_KEY", $root["HACKATHON_API_KEY"], "Process")
    $keyConfigured = $true
}
Write-Host "hackathon_key_configured: $($keyConfigured.ToString().ToLower())"
Write-Host "assistant_provider: $([Environment]::GetEnvironmentVariable('ASSISTANT_PROVIDER','Process'))"
Write-Host "assistant_agent_loop: $([Environment]::GetEnvironmentVariable('ASSISTANT_AGENT_LOOP','Process'))"
Write-Host "hackathon_model: $([Environment]::GetEnvironmentVariable('HACKATHON_MODEL','Process'))"

$python = $null
if (Test-Path ".venv\Scripts\python.exe") {
    $python = (Resolve-Path ".venv\Scripts\python.exe").Path
} else {
    $python = (Get-Command python -ErrorAction Stop).Source
}

Write-Host "Python: $python"
Write-Host "Starting uvicorn on http://127.0.0.1:$ApiPort ..."
Write-Host "Health: http://127.0.0.1:$ApiPort/health"
Write-Host "PID will be recorded in $PidFile"

# Foreground server; record PID of this PowerShell wrapper's child via Start-Process -NoNewWindow alternative:
# uvicorn runs in-process under this shell — write current process id for stop script matching by port.
$PID | Set-Content -Path $PidFile -Encoding ascii
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort
