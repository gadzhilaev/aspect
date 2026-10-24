# Start Aspect FastAPI from the repo root (Windows).
# Official local demo port: 8003 (8000 is often blocked by a stale listener on this machine).
# Does not kill foreign processes — if :8003 is busy, prints how to check and exits.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$ApiPort = 8003

Write-Host "Repo: $RepoRoot"
Write-Host "Official demo API port: $ApiPort"

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

$pidOnPort = Get-PortOwner $ApiPort
if ($pidOnPort) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pidOnPort" -ErrorAction SilentlyContinue
    $cmd = if ($proc) { $proc.CommandLine } else { "(unknown process)" }
    $isOurs = $cmd -and ($cmd -match "uvicorn" -or $cmd -match "kontur_back" -or $cmd -match "app\.main")
    Write-Host "Port $ApiPort is already in use by PID $pidOnPort"
    Write-Host "  $cmd"
    if ($isOurs) {
        Write-Host "Looks like Aspect/uvicorn is already running. Open http://127.0.0.1:$ApiPort/health"
        Write-Host "To verify OpenAPI fields: http://127.0.0.1:$ApiPort/docs — ImpactOut must include assessment_state, finance_setup_href"
        exit 0
    }
    Write-Host ""
    Write-Host "Refusing to kill a foreign process. Free the port manually, then re-run:"
    Write-Host "  netstat -ano | findstr :$ApiPort"
    Write-Host '  taskkill /PID <pid> /F   # only if you own that process'
    exit 1
}

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example (edit secrets locally if needed)."
    } else {
        Write-Host "WARNING: no .env found"
    }
}

$python = $null
if (Test-Path ".venv\Scripts\python.exe") {
    $python = (Resolve-Path ".venv\Scripts\python.exe").Path
} else {
    $python = (Get-Command python -ErrorAction Stop).Source
}

Write-Host "Python: $python"
Write-Host "Starting uvicorn on http://127.0.0.1:$ApiPort ..."
Write-Host "Check after start: /health and /openapi.json (ImpactOut.assessment_state)"
Write-Host "Frontend is ../frontend — set VITE_API_BASE_URL=http://127.0.0.1:$ApiPort there"

& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port $ApiPort
