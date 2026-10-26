param(
    [Parameter(Mandatory=$true)][uri]$ApiUrl,
    [int]$Port = 5181
)
$ErrorActionPreference = 'Stop'
if ($ApiUrl.Scheme -notin @('http', 'https') -or $ApiUrl.UserInfo -or $ApiUrl.Query -or $ApiUrl.Fragment -or $ApiUrl.AbsolutePath -ne '/') {
    throw 'ApiUrl must be an API origin, e.g. http://127.0.0.1:8020 (without credentials or /api).'
}
Push-Location $PSScriptRoot
$previousTarget = $env:VITE_PROXY_TARGET
$previousBase = $env:VITE_API_BASE_URL
try {
    $env:VITE_PROXY_TARGET = $ApiUrl.GetLeftPart([System.UriPartial]::Authority)
    $env:VITE_API_BASE_URL = ''
    Invoke-RestMethod -Uri "$env:VITE_PROXY_TARGET/health" -TimeoutSec 5 | Out-Null
    Write-Host "Frontend -> $env:VITE_PROXY_TARGET. Backend is not started or modified by this script."
    npm run dev -- --mode mobile --host 127.0.0.1 --port $Port --strictPort
} finally {
    $env:VITE_PROXY_TARGET = $previousTarget
    $env:VITE_API_BASE_URL = $previousBase
    Pop-Location
}
