# Poll outbox for TG-3 stand — kinds filtered by TELEGRAM_OUTBOX_KINDS (test only).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:PYTHONPATH = $Root
python -c "from scripts.telegram_live_env import load_telegram_live_env; f=load_telegram_live_env(); assert f['database_url']; print('env_loaded token_present=' + str(f['telegram_bot_token']).lower())"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Worker loop: kind allowlist from TELEGRAM_OUTBOX_KINDS (expect test)"
while ($true) {
  python -m app.workers.notification_worker
  Start-Sleep -Seconds 5
}
