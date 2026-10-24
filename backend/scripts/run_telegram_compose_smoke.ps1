# Isolated Telegram Compose smoke (mocked Bot API). Does not touch main stand.
$ErrorActionPreference = "Continue"
$BackendRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $BackendRoot
Set-Location $RepoRoot

$env:COMPOSE_PROJECT_NAME = "kontur_tg_compose_smoke"
$compose = "docker-compose.telegram_compose_smoke.yml"

docker compose -f $compose down -v --remove-orphans 2>&1 | Out-Null
docker compose -f $compose run --rm --no-deps verify
$code = $LASTEXITCODE
docker compose -f $compose down -v --remove-orphans 2>&1 | Out-Null
if ($null -eq $code) { $code = 1 }
Write-Host "telegram_compose_smoke_exit=$code"
exit $code
