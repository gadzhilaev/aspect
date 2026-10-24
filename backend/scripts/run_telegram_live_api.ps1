# Start full Kontur API for TG-3 stand (localhost UI). Does not modify root .env.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:PYTHONPATH = $Root
python -c "from scripts.telegram_live_env import load_telegram_live_env; f=load_telegram_live_env(); assert f['database_url']; print('env_loaded token_present=' + str(f['telegram_bot_token']).lower())"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$port = if ($env:TELEGRAM_LIVE_API_PORT) { $env:TELEGRAM_LIVE_API_PORT } else { "8027" }
Write-Host "Starting API on 127.0.0.1:$port (stand DB, TELEGRAM_OUTBOX_KINDS from stand.env)"
python -m uvicorn app.main:app --host 127.0.0.1 --port $port
