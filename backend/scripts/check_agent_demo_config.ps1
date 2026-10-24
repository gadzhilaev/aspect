# Verify agent-demo stand config without starting servers or calling the model.
# Never prints secret values.

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

$StandDir = Join-Path $RepoRoot "data\agent_demo"
$StandEnv = Join-Path $StandDir "stand.env"
$Manifest = Join-Path $StandDir "stand_manifest.json"
$WebEnv = Join-Path $StandDir "web.env"

Write-Host "=== Agent demo config check ==="
if (-not (Test-Path $StandEnv) -or -not (Test-Path $Manifest)) {
    Write-Host "FAIL: stand not prepared. Run: python scripts/prepare_agent_demo_stand.py"
    exit 2
}

$stand = Read-DotEnv $StandEnv
$root = Read-DotEnv (Join-Path $RepoRoot ".env")
$web = Read-DotEnv $WebEnv
$m = Get-Content $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json

Write-Host "stand_db_exists: $((Test-Path (Join-Path $StandDir 'agent_demo.db')).ToString().ToLower())"
Write-Host "storage_exists: $((Test-Path (Join-Path $StandDir 'storage')).ToString().ToLower())"
Write-Host "api_port: $($stand['AGENT_DEMO_API_PORT'])"
Write-Host "web_port: $($stand['AGENT_DEMO_WEB_PORT'])"
Write-Host "vite_api_base: $($web['VITE_API_BASE_URL'])"
Write-Host "provider: $($stand['ASSISTANT_PROVIDER'])"
Write-Host "agent_loop: $($stand['ASSISTANT_AGENT_LOOP'])"
Write-Host "model: $($stand['HACKATHON_MODEL'])"
Write-Host "case_slot: $($stand['CASE_CONTEXT_SLOT_KEY'])"
Write-Host "ocr_ids_set: $(([string]::IsNullOrWhiteSpace($stand['BANK_MATERIALS_ALLOWED_OCR_RUN_IDS']) -eq $false).ToString().ToLower())"
Write-Host "hackathon_key_configured: $(($root.ContainsKey('HACKATHON_API_KEY') -and $root['HACKATHON_API_KEY']).ToString().ToLower())"
Write-Host "hackathon_key_in_stand_env: $(($stand.ContainsKey('HACKATHON_API_KEY') -and $stand['HACKATHON_API_KEY']).ToString().ToLower())"
Write-Host "root_env_untouched_note: launcher reads key from root .env into process only"
Write-Host "event_id: $($m.resolved.event_id)"
Write-Host "company: $($m.resolved.company_name)"
Write-Host "email: $($m.resolved.email)"
Write-Host "ordinary_ports_not_used: api!=8003 web!=5173 => $(($stand['AGENT_DEMO_API_PORT'] -ne '8003' -and $stand['AGENT_DEMO_WEB_PORT'] -ne '5173').ToString().ToLower())"
Write-Host "=== check done ==="
exit 0
