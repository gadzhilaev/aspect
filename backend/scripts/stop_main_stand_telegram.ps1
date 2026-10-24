# Stop TG-5 main-stand polling + test worker (real_news_613).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$pidsFile = Join-Path $Root "data\competition_stand\real_news_613\telegram_runtime\pids.json"
if (Test-Path $pidsFile) {
  $j = Get-Content $pidsFile -Raw | ConvertFrom-Json
  foreach ($id in @($j.polling_shell, $j.worker_shell) + @($j.polling_python) + @($j.worker_python)) {
    if ($id) {
      Stop-Process -Id ([int]$id) -Force -ErrorAction SilentlyContinue
      Write-Host "stopped $id"
    }
  }
}
Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -match 'run_main_stand_telegram|app\.workers\.telegram_polling|app\.workers\.notification_worker'
} | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  Write-Host "stopped orphan $($_.ProcessId)"
}
$lock = Join-Path $Root "data\competition_stand\real_news_613\telegram_runtime\polling.lock"
if (Test-Path $lock) { Remove-Item $lock -Force }
Write-Host "Main-stand TG stopped. Optional restore of TG-3.1: scripts/run_telegram_live_polling.ps1"
