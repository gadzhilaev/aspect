# Stop only the TG-3.1 live-stand getUpdates process (PID from pids.json).
# Does not stop :8027 API / :5187 UI / outbox worker.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$pidsFile = Join-Path $Root "data\telegram_live\pids.json"
if (-not (Test-Path $pidsFile)) {
  Write-Host "No data/telegram_live/pids.json - nothing recorded."
  exit 0
}
$j = Get-Content $pidsFile -Raw | ConvertFrom-Json
$pollPid = $j.polling.process_id
if (-not $pollPid) {
  Write-Host "No polling.process_id in pids.json"
  exit 0
}
$proc = Get-Process -Id $pollPid -ErrorAction SilentlyContinue
if ($null -eq $proc) {
  Write-Host "Polling PID $pollPid already stopped"
} else {
  Write-Host "Stopping telegram_live polling PID $pollPid"
  Stop-Process -Id $pollPid -Force
}
$lock = Join-Path $Root "data\telegram_live\polling.lock"
if (Test-Path $lock) { Remove-Item $lock -Force }
Write-Host "Done. Restore later: scripts/run_telegram_live_polling.ps1 (after stopping main-stand polling)."
