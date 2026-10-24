# Main-stand outbox worker (kinds from telegram_process.env; default test,news).
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
Import-DotEnv (Join-Path $Root "data\competition_stand\real_news_613\telegram_process.env")
Import-DotEnv (Join-Path $Root "data\telegram_live\.env.secrets")

$env:DATABASE_URL = "sqlite:///./data/competition_stand/real_news_613/stand.db"
$env:PYTHONPATH = $Root
if (-not $env:TELEGRAM_OUTBOX_KINDS) { $env:TELEGRAM_OUTBOX_KINDS = "test,news" }
$env:TELEGRAM_NEWS_CONTROLLED_PAIR = ""
# Keep competition profile consistent with stand.env (do not reload telegram_live/stand.env).

if (-not $env:TELEGRAM_BOT_TOKEN) {
  Write-Error "TELEGRAM_BOT_TOKEN missing in data/telegram_live/.env.secrets"
  exit 2
}

Write-Host "Main-stand telegram worker kinds=$env:TELEGRAM_OUTBOX_KINDS news_auto=$env:TELEGRAM_NEWS_NOTIFICATIONS_ENABLED DB=$env:DATABASE_URL"
while ($true) {
  python -m app.workers.notification_worker
  Start-Sleep -Seconds 5
}
