# Restart / run main-stand API :8020 with Telegram process overlay (no root .env edits).
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
Import-DotEnv (Join-Path $Root "data\telegram_live\.env.secrets")
$tlStand = Join-Path $Root "data\telegram_live\stand.env"
if (Test-Path $tlStand) {
  Get-Content $tlStand | ForEach-Object {
    $line = $_.Trim()
    if ($line -match '^(TELEGRAM_WEBHOOK_SECRET|TELEGRAM_LINK_TOKEN_TTL_MINUTES|TELEGRAM_TEST_SEND_COOLDOWN_SECONDS)=(.*)$') {
      Set-Item -Path ("Env:" + $Matches[1]) -Value $Matches[2]
    }
  }
}

$env:DATABASE_URL = "sqlite:///./data/competition_stand/real_news_613/stand.db"
$env:PYTHONPATH = $Root
$env:TELEGRAM_NEWS_CONTROLLED_PAIR = ""
$port = if ($env:AGENT_DEMO_API_PORT) { $env:AGENT_DEMO_API_PORT } else { "8020" }

Write-Host "Main API :$port news_auto=$env:TELEGRAM_NEWS_NOTIFICATIONS_ENABLED kinds=$env:TELEGRAM_OUTBOX_KINDS"
python -m uvicorn app.main:app --host 127.0.0.1 --port $port
