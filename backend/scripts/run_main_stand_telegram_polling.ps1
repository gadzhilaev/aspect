# TG-5: getUpdates polling for main stand (:8020 / real_news_613).
# Loads secrets from data/telegram_live/.env.secrets (not copied into Git / root .env).
# Mutually exclusive with the TG-3.1 live-stand polling process — stop that PID first.
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

# Order: competition stand first, then TG process flags, then secrets only (no telegram_live/stand.env —
# that file would overwrite ASSISTANT_PROVIDER and break COMPETITION_MODE).
Import-DotEnv (Join-Path $Root "data\competition_stand\real_news_613\stand.env")
Import-DotEnv (Join-Path $Root "data\competition_stand\real_news_613\telegram_process.env")
Import-DotEnv (Join-Path $Root "data\telegram_live\.env.secrets")
# Webhook secret for shared handler config (optional for polling-only).
$tlStand = Join-Path $Root "data\telegram_live\stand.env"
if (Test-Path $tlStand) {
  Get-Content $tlStand | ForEach-Object {
    $line = $_.Trim()
    if ($line -match '^(TELEGRAM_WEBHOOK_SECRET|TELEGRAM_LINK_TOKEN_TTL_MINUTES|TELEGRAM_TEST_SEND_COOLDOWN_SECONDS)=(.*)$') {
      Set-Item -Path ("Env:" + $Matches[1]) -Value $Matches[2]
    }
  }
}

# Force main-stand DB + TG-5 gates (never inherit telegram_live DATABASE_URL).
$env:DATABASE_URL = "sqlite:///./data/competition_stand/real_news_613/stand.db"
$env:PYTHONPATH = $Root
$runtime = Join-Path $Root "data\competition_stand\real_news_613\telegram_runtime"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$env:TELEGRAM_POLLING_STATE_DIR = $runtime
# Prefer telegram_process.env; defaults keep polling safe if file missing.
if (-not $env:TELEGRAM_OUTBOX_KINDS) { $env:TELEGRAM_OUTBOX_KINDS = "test,news" }
if (-not $env:TELEGRAM_NEWS_CONTROLLED_PAIR) { $env:TELEGRAM_NEWS_CONTROLLED_PAIR = "" }

if (-not $env:TELEGRAM_BOT_TOKEN) {
  Write-Error "TELEGRAM_BOT_TOKEN missing in data/telegram_live/.env.secrets"
  exit 2
}

Write-Host "Main-stand telegram polling → DATABASE_URL=$env:DATABASE_URL"
Write-Host "kinds=$env:TELEGRAM_OUTBOX_KINDS news_auto=$env:TELEGRAM_NEWS_NOTIFICATIONS_ENABLED state=$runtime"
python -m app.workers.telegram_polling
