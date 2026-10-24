# Main-stand news scheduler (heuristic ingest every NEWS_SCHEDULER_INTERVAL_SECONDS).
# Separate process from FastAPI — do not start a second copy.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Import-DotEnv($path) {
  if (-not (Test-Path $path)) { return }
  Get-Content $path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#')) { return }
    $i = $line.IndexOf('=')
    if ($i -lt 1) { return }
    Set-Item -Path ("Env:" + $line.Substring(0, $i).Trim()) -Value $line.Substring($i + 1).Trim()
  }
}

Import-DotEnv (Join-Path $Root "data\competition_stand\real_news_613\stand.env")
Import-DotEnv (Join-Path $Root "data\competition_stand\real_news_613\news_scheduler.env")
Import-DotEnv (Join-Path $Root "data\competition_stand\real_news_613\telegram_process.env")

$env:DATABASE_URL = "sqlite:///./data/competition_stand/real_news_613/stand.db"
$env:PYTHONPATH = $Root
# Scheduler must never prefer live enrich / alternate providers.
$env:COMPETITION_MODE = "true"
$env:ASSISTANT_PROVIDER = "hackathon"

# Refuse if another scheduler already holds the process lock for this DB.
$state = Join-Path $Root "data\competition_stand\real_news_613\news_scheduler_runtime"
New-Item -ItemType Directory -Force -Path $state | Out-Null

Write-Host "Main-stand news scheduler interval=$env:NEWS_SCHEDULER_INTERVAL_SECONDS state=$env:NEWS_SCHEDULER_STATE_DIR"
python -m app.workers.news_scheduler @args
