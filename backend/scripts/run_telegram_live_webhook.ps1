# Webhook-only ASGI for temporary public tunnel (no /docs, no full API).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:PYTHONPATH = $Root
python -c "from scripts.telegram_live_env import load_telegram_live_env; f=load_telegram_live_env(); assert f['database_url']; print('env_loaded token_present=' + str(f['telegram_bot_token']).lower())"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$port = if ($env:TELEGRAM_LIVE_WEBHOOK_PORT) { $env:TELEGRAM_LIVE_WEBHOOK_PORT } else { "8028" }
Write-Host "Starting webhook-only on 127.0.0.1:$port"
Write-Host "Public tunnel should forward ONLY to this port."
python -m uvicorn app.telegram_webhook_only:app --host 127.0.0.1 --port $port
