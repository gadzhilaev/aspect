# Stop only competition UI acceptance stand processes on its ports (6.11).
# Does not touch :8003 / :5173 / other stands.

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$StandDir = Join-Path $RepoRoot "data\competition_stand\ui_acceptance_611"
$StandEnv = Join-Path $StandDir "stand.env"
$ApiPort = 8018
$WebPort = 5178

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

function Stop-Port([int]$Port) {
    $lines = netstat -ano | Select-String ":$Port\s+.*LISTENING"
    foreach ($line in $lines) {
        $parts = ($line.ToString() -split "\s+") | Where-Object { $_ -ne "" }
        if ($parts.Length -ge 5) {
            $procId = [int]$parts[-1]
            Write-Host "Stopping PID $procId on port $Port"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

if (Test-Path $StandEnv) {
    $stand = Read-DotEnv $StandEnv
    if ($stand.ContainsKey("AGENT_DEMO_API_PORT") -and $stand["AGENT_DEMO_API_PORT"]) {
        $ApiPort = [int]$stand["AGENT_DEMO_API_PORT"]
    }
    if ($stand.ContainsKey("AGENT_DEMO_WEB_PORT") -and $stand["AGENT_DEMO_WEB_PORT"]) {
        $WebPort = [int]$stand["AGENT_DEMO_WEB_PORT"]
    }
}

Write-Host "Stopping competition UI stand on API=$ApiPort WEB=$WebPort only"
Stop-Port $ApiPort
Stop-Port $WebPort
Write-Host "Done."
