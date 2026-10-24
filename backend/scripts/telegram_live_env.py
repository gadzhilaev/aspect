"""Load TG-3 stand.env + .env.secrets into os.environ (no printing of secrets)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAND_DIR = ROOT / "data" / "telegram_live"
STAND_ENV = STAND_DIR / "stand.env"
SECRETS_ENV = STAND_DIR / ".env.secrets"


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip()
    return out


def load_telegram_live_env(*, override: bool = True) -> dict[str, bool]:
    """Merge stand + secrets into process env. Returns presence flags only."""
    merged = {}
    merged.update(_parse_env_file(STAND_ENV))
    merged.update(_parse_env_file(SECRETS_ENV))
    for key, val in merged.items():
        if override or key not in os.environ:
            os.environ[key] = val
    return {
        "telegram_bot_token": bool((merged.get("TELEGRAM_BOT_TOKEN") or "").strip()),
        "telegram_bot_username": bool((merged.get("TELEGRAM_BOT_USERNAME") or "").strip()),
        "telegram_webhook_secret": bool((merged.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()),
        "database_url": bool((merged.get("DATABASE_URL") or "").strip()),
    }


def token_present() -> bool:
    return bool((_parse_env_file(SECRETS_ENV).get("TELEGRAM_BOT_TOKEN") or "").strip())
