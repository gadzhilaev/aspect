"""Static checks for competition Docker config when Docker daemon is unavailable.

Aspect mobile package: API + bootstrap (+ news_scheduler). React web / frontend/
is optional and not required for STATIC_OK.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def main() -> int:
    errors: list[str] = []
    files = [
        REPO_ROOT / "docker-compose.competition.yml",
        BACKEND_ROOT / "docker" / "competition" / "Dockerfile.api",
        BACKEND_ROOT / "docker" / "competition" / "entrypoint-api.sh",
        BACKEND_ROOT / "docker" / "competition" / "entrypoint-bootstrap.sh",
        BACKEND_ROOT / ".dockerignore",
        BACKEND_ROOT / ".env.competition.example",
        BACKEND_ROOT / "requirements-linux.lock",
        REPO_ROOT / "THIRD_PARTY_NOTICES",
    ]
    for p in files:
        if not p.is_file():
            try:
                rel = p.relative_to(REPO_ROOT)
            except ValueError:
                rel = p
            errors.append(f"missing:{rel}")

    compose_path = REPO_ROOT / "docker-compose.competition.yml"
    compose = compose_path.read_text(encoding="utf-8") if compose_path.is_file() else ""
    # Ignore comments when scanning for forbidden services.
    compose_code = "\n".join(
        ln for ln in compose.splitlines() if not ln.lstrip().startswith("#")
    )
    if re.search(r"(?im)^\s*image:\s*postgres", compose_code) or re.search(
        r"(?im)^\s*postgres:", compose_code
    ):
        errors.append("compose_contains_postgres")
    if re.search(r"(?im)^\s*worker:", compose_code):
        errors.append("compose_contains_worker")
    compact = compose.replace(" ", "")
    if "context:./backend" not in compact and "context: ./backend" not in compose:
        errors.append("compose_api_context_not_backend")
    if "dockerfile: docker/competition/Dockerfile.api" not in compose:
        errors.append("compose_api_dockerfile_missing")
    if re.search(r"(?im)^\s*api:", compose_code) is None:
        errors.append("compose_missing_api_service")
    if "bootstrap" not in compose_code:
        errors.append("compose_missing_bootstrap")

    if "HACKATHON_API_KEY" in (
        BACKEND_ROOT / "docker/competition/Dockerfile.api"
    ).read_text(encoding="utf-8"):
        errors.append("api_dockerfile_mentions_key")

    api_df = (BACKEND_ROOT / "docker/competition/Dockerfile.api").read_text(
        encoding="utf-8"
    )
    if "--require-hashes" not in api_df:
        errors.append("api_dockerfile_no_require_hashes")
    if "requirements-linux.lock" not in api_df:
        errors.append("api_dockerfile_no_linux_lock")

    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text(encoding="utf-8")
    for needle in (".env", "node_modules", "data/bank_materials/raw/", "*.db"):
        if needle not in dockerignore:
            errors.append(f"dockerignore_missing:{needle}")

    # Entrypoint must not run seed/import.
    api_ep = (BACKEND_ROOT / "docker/competition/entrypoint-api.sh").read_text(
        encoding="utf-8"
    )
    for bad in ("seed_demo", "bootstrap_competition", "import_bank", "alembic upgrade"):
        if bad in api_ep:
            errors.append(f"api_entrypoint_runs:{bad}")

    if errors:
        print("STATIC_FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("STATIC_OK competition docker config (API-only / Flutter UI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
