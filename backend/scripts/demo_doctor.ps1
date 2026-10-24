# Aspect local demo readiness — never prints secret values.
# Usage (from repo root): .\scripts\demo_doctor.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Read-DotEnv([string]$Path) {
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $k = $line.Substring(0, $eq).Trim()
        $v = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
        $map[$k] = $v
    }
    return $map
}

Write-Host "=== Aspect demo doctor ==="
Write-Host "Repo: $RepoRoot"

$rootEnv = Read-DotEnv (Join-Path $RepoRoot ".env")
. (Join-Path $PSScriptRoot "resolve_front_root.ps1")
try {
    $webEnv = Read-DotEnv (Join-Path (Get-KonturFrontRoot) ".env")
} catch {
    Write-Host "WARNING: frontend (.env) not found — $($_.Exception.Message)"
    $webEnv = @{}
}

$provider = if ($rootEnv.ContainsKey("ASSISTANT_PROVIDER") -and $rootEnv["ASSISTANT_PROVIDER"]) {
    $rootEnv["ASSISTANT_PROVIDER"].ToLower()
} else { "mock" }
# Deprecated alias
if ($provider -eq "live") { $provider = "openai" }
$allowedProviders = @("openai", "gigachat", "hackathon", "mock")
if ($allowedProviders -notcontains $provider) { $provider = "mock" }

$keyConfigured = $false
if ($provider -eq "openai") {
    if ($rootEnv.ContainsKey("OPENAI_API_KEY") -and $rootEnv["OPENAI_API_KEY"]) { $keyConfigured = $true }
    elseif ($rootEnv.ContainsKey("ASSISTANT_API_KEY") -and $rootEnv["ASSISTANT_API_KEY"]) { $keyConfigured = $true }
} elseif ($provider -eq "gigachat") {
    if ($rootEnv.ContainsKey("GIGACHAT_AUTH_KEY") -and $rootEnv["GIGACHAT_AUTH_KEY"]) { $keyConfigured = $true }
} elseif ($provider -eq "hackathon") {
    if ($rootEnv.ContainsKey("HACKATHON_API_KEY") -and $rootEnv["HACKATHON_API_KEY"]) { $keyConfigured = $true }
} else {
    $keyConfigured = $false
}

Write-Host "provider: $provider"
Write-Host "key_configured: $($keyConfigured.ToString().ToLower())"
if ($provider -eq "openai") {
    Write-Host "openai_model: $(if ($rootEnv.ContainsKey('OPENAI_MODEL') -and $rootEnv['OPENAI_MODEL']) { $rootEnv['OPENAI_MODEL'] } else { 'gpt-4o-mini (default)' })"
}
if ($provider -eq "gigachat") {
    Write-Host "gigachat_model: $(if ($rootEnv.ContainsKey('GIGACHAT_MODEL') -and $rootEnv['GIGACHAT_MODEL']) { $rootEnv['GIGACHAT_MODEL'] } else { 'GigaChat (default)' })"
    Write-Host "gigachat_scope: $(if ($rootEnv.ContainsKey('GIGACHAT_SCOPE') -and $rootEnv['GIGACHAT_SCOPE']) { $rootEnv['GIGACHAT_SCOPE'] } else { 'GIGACHAT_API_PERS' })"
}
if ($provider -eq "hackathon") {
    $hkModel = if ($rootEnv.ContainsKey('HACKATHON_MODEL') -and $rootEnv['HACKATHON_MODEL']) { $rootEnv['HACKATHON_MODEL'] } else { 'deepseek/deepseek-v4.1-flash (default)' }
    $hkBase = if ($rootEnv.ContainsKey('HACKATHON_BASE_URL') -and $rootEnv['HACKATHON_BASE_URL']) { $rootEnv['HACKATHON_BASE_URL'] } else { 'https://changellenge.up.railway.app/v1 (default)' }
    Write-Host "hackathon_model: $hkModel"
    Write-Host "hackathon_base_url: $hkBase"
}
Write-Host "ingestion_token_configured: $((($rootEnv.ContainsKey('INGESTION_RUN_TOKEN') -and $rootEnv['INGESTION_RUN_TOKEN'])).ToString().ToLower())"
Write-Host "secret_key_configured: $((($rootEnv.ContainsKey('SECRET_KEY') -and $rootEnv['SECRET_KEY'])).ToString().ToLower())"

$webKeys = @($webEnv.Keys)
$webOk = ($webKeys.Count -eq 1 -and $webKeys[0] -eq "VITE_API_BASE_URL")
Write-Host "web_env_public_only: $($webOk.ToString().ToLower())"
if ($webEnv.ContainsKey("VITE_API_BASE_URL")) {
    Write-Host "vite_api_base_url: $($webEnv['VITE_API_BASE_URL'])"
} else {
    Write-Host "vite_api_base_url: missing"
}

$forbiddenWeb = @(
    "OPENAI_API_KEY", "ASSISTANT_PROVIDER", "SECRET_KEY", "INGESTION_RUN_TOKEN",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET", "ASSISTANT_API_KEY", "GIGACHAT_AUTH_KEY",
    "HACKATHON_API_KEY"
)
$leak = @($forbiddenWeb | Where-Object { $webEnv.ContainsKey($_) })
if ($leak.Count -gt 0) {
    Write-Host "web_env_secret_leak: true (names only: $($leak -join ', '))"
} else {
    Write-Host "web_env_secret_leak: false"
}

$healthTargets = @()
if ($webEnv.ContainsKey("VITE_API_BASE_URL") -and $webEnv["VITE_API_BASE_URL"]) {
    $healthTargets += ($webEnv["VITE_API_BASE_URL"].TrimEnd("/") + "/health")
}
$healthTargets += "http://127.0.0.1:8003/health"
$healthTargets = $healthTargets | Select-Object -Unique
$healthOk = $false
$healthHit = "none"
foreach ($url in $healthTargets) {
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) {
            $healthOk = $true
            $healthHit = $url
            break
        }
    } catch {
        continue
    }
}
Write-Host "backend_health: $($healthOk.ToString().ToLower()) ($healthHit)"

if (($provider -eq "openai" -or $provider -eq "gigachat" -or $provider -eq "hackathon") -and -not $keyConfigured) {
    Write-Host "WARN: provider=$provider but auth key is empty; AI calls return provider unavailable."
}
if ($provider -eq "mock") {
    Write-Host "OK: mock mode (offline demo answers, no external AI calls)."
} elseif ($provider -eq "openai" -and $keyConfigured) {
    Write-Host "OK: openai mode ready (server-side only; key never sent to browser)."
} elseif ($provider -eq "gigachat" -and $keyConfigured) {
    Write-Host "OK: gigachat mode ready (server-side OAuth; auth key never sent to browser)."
} elseif ($provider -eq "hackathon" -and $keyConfigured) {
    Write-Host "OK: hackathon mode ready (organizers gateway; key never sent to browser; no OpenAI/GigaChat fallback)."
}

Write-Host "=== doctor done ==="
exit 0
