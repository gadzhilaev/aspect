# Stop main-stand news scheduler process(es).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -match 'run_main_stand_news_scheduler|app\.workers\.news_scheduler'
} | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  Write-Host "stopped $($_.ProcessId)"
}
$lockDir = Join-Path $Root "data\competition_stand\real_news_613\news_scheduler_runtime"
Get-ChildItem -Path $lockDir -Filter "scheduler_*.lock" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $lockDir -Filter "run_*.lock" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "Main-stand news scheduler stopped."
