# Stop only agent-demo stand listeners on :8017 / :5177 (stage 4.7).
# Refuses to kill processes that do not look like this stand.
# Does not touch :8003 / :5173.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$StandDir = Join-Path $RepoRoot "data\agent_demo"
$ApiPort = 8017
$WebPort = 5177

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

function Stop-StandPort([int]$Port, [string[]]$Needles) {
    $pidOnPort = Get-PortOwner $Port
    if (-not $pidOnPort) {
        Write-Host "Port $Port: nothing listening"
        return
    }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pidOnPort" -ErrorAction SilentlyContinue
    $cmd = if ($proc) { [string]$proc.CommandLine } else { "" }
    $ok = $false
    foreach ($n in $Needles) {
        if ($cmd -and ($cmd -like "*$n*")) { $ok = $true; break }
    }
    # Also accept match on explicit stand port in command line
    if ($cmd -and ($cmd -match ":$Port\b" -or $cmd -match "--port $Port" -or $cmd -match "port $Port")) {
        $ok = $true
    }
    Write-Host "Port $Port PID $pidOnPort"
    Write-Host "  cmd: $cmd"
    if (-not $ok) {
        Write-Host "  REFUSE: command line does not match agent-demo stand markers."
        return
    }
    Write-Host "  Stopping PID $pidOnPort (stand-owned)"
    Stop-Process -Id $pidOnPort -Force -ErrorAction SilentlyContinue
}

Write-Host "=== Stop agent demo stand ==="
Stop-StandPort $ApiPort @("uvicorn", "app.main", "agent_demo")
Stop-StandPort $WebPort @("vite", "node", "5177")

foreach ($name in @("backend.pid", "frontend.pid")) {
    $p = Join-Path $StandDir $name
    if (Test-Path $p) { Remove-Item $p -Force }
}
Write-Host "Done. Ordinary :8003 / :5173 were not targeted."
