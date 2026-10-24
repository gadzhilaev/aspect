# Dev getUpdates polling for TG-3.1 stand — no public ports.
# Mutually exclusive with webhook; refuses to start if getWebhookInfo.url is set.
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

Import-DotEnv (Join-Path $Root "data\telegram_live\stand.env")
Import-DotEnv (Join-Path $Root "data\telegram_live\.env.secrets")
$env:PYTHONPATH = $Root
$env:TELEGRAM_POLLING_STATE_DIR = (Join-Path $Root "data\telegram_live")
if (-not $env:TELEGRAM_OUTBOX_KINDS) { $env:TELEGRAM_OUTBOX_KINDS = "test" }

if (-not $env:TELEGRAM_BOT_TOKEN) {
  Write-Error "TELEGRAM_BOT_TOKEN missing in data/telegram_live/.env.secrets"
  exit 2
}
if (-not $env:DATABASE_URL) {
  Write-Error "DATABASE_URL missing in stand.env"
  exit 2
}

Write-Host "Starting telegram polling (getUpdates). No public ports. kinds=$env:TELEGRAM_OUTBOX_KINDS"
python -m app.workers.telegram_polling
