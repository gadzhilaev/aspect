# Resolve monorepo frontend root (kontur_back/frontend). Dot-source or call.
# Prefer $env:KONTUR_FRONT_DIR, else ../frontend next to backend/.

function Get-KonturFrontRoot {
    $BackendRoot = Split-Path -Parent $PSScriptRoot
    $RepoRoot = Split-Path -Parent $BackendRoot
    if ($env:KONTUR_FRONT_DIR -and $env:KONTUR_FRONT_DIR.Trim()) {
        $p = $env:KONTUR_FRONT_DIR.Trim()
        if (-not [System.IO.Path]::IsPathRooted($p)) {
            $p = Join-Path $BackendRoot $p
        }
        $pkg = Join-Path $p "package.json"
        if (Test-Path $pkg) { return (Resolve-Path $p).Path }
        throw "KONTUR_FRONT_DIR set but package.json missing: $p"
    }
    $monorepo = Join-Path $RepoRoot "frontend"
    if (Test-Path (Join-Path $monorepo "package.json")) {
        return (Resolve-Path $monorepo).Path
    }
    $sibling = Join-Path (Split-Path -Parent $RepoRoot) "kontur_front"
    if (Test-Path (Join-Path $sibling "package.json")) {
        return (Resolve-Path $sibling).Path
    }
    foreach ($legacy in @((Join-Path $BackendRoot "web"), (Join-Path $RepoRoot "web"))) {
        if (Test-Path (Join-Path $legacy "package.json")) {
            return (Resolve-Path $legacy).Path
        }
    }
    throw "Frontend not found. Expected kontur_back/frontend (or set KONTUR_FRONT_DIR)."
}
