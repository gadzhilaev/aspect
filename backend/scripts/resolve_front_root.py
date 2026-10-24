"""Resolve monorepo frontend path (kontur_back/frontend).

Order:
1. env KONTUR_FRONT_DIR (absolute or relative to backend root)
2. monorepo sibling ../frontend next to backend/
3. legacy Desktop/kontur_front (old split layout)
4. legacy backend/web or repo/web

Used by pytest contract checks and optional host scripts.
"""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def resolve_front_root() -> Path:
    env = (os.environ.get("KONTUR_FRONT_DIR") or "").strip()
    if env:
        p = Path(env)
        if not p.is_absolute():
            p = (BACKEND_ROOT / p).resolve()
        if (p / "package.json").is_file():
            return p
        raise FileNotFoundError(f"KONTUR_FRONT_DIR set but package.json missing: {p}")

    monorepo = (REPO_ROOT / "frontend").resolve()
    if (monorepo / "package.json").is_file():
        return monorepo

    sibling = (REPO_ROOT.parent / "kontur_front").resolve()
    if (sibling / "package.json").is_file():
        return sibling

    for legacy in (BACKEND_ROOT / "web", REPO_ROOT / "web"):
        if (legacy / "package.json").is_file():
            return legacy

    raise FileNotFoundError(
        "Frontend not found. Expected kontur_back/frontend "
        "(or set KONTUR_FRONT_DIR)."
    )


def resolve_front_src() -> Path:
    return resolve_front_root() / "src"


if __name__ == "__main__":
    print(resolve_front_root())
