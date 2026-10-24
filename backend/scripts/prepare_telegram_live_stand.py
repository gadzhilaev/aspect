"""Prepare isolated Telegram live stand (TG-3).

- Fresh SQLite DB under data/telegram_live/ (alembic upgrade head + seed_demo)
- Non-secret stand.env for process launch
- Optional secrets file path for manual/bot token fill (gitignored directory)
- Does NOT modify root .env, kontur.db, or other stands
- Does NOT call Telegram API / setWebhook
"""

from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAND_DIR = ROOT / "data" / "telegram_live"
STAND_DB = STAND_DIR / "telegram_live.db"
STAND_ENV = STAND_DIR / "stand.env"
SECRETS_ENV = STAND_DIR / ".env.secrets"
MANIFEST = STAND_DIR / "stand_manifest.json"
SECRETS_TEMPLATE = STAND_DIR / "SECRETS_FILL_ME.txt"

API_PORT = 8027
WEBHOOK_PORT = 8028
WEB_PORT = 5187
WORKER_KINDS = "test"


def _write_stand_env(*, webhook_secret: str) -> None:
    db_url = f"sqlite:///./{STAND_DB.relative_to(ROOT).as_posix()}"
    lines = [
        "# Telegram live stand (TG-3) — process profile.",
        "# Secrets live in .env.secrets (gitignored). Do not copy tokens into web/.env.",
        f"DATABASE_URL={db_url}",
        "APP_ENV=development",
        "DEBUG=true",
        "ASSISTANT_PROVIDER=mock",
        "OPENAI_API_KEY=",
        "GIGACHAT_AUTH_KEY=",
        "HACKATHON_API_KEY=",
        f"TELEGRAM_OUTBOX_KINDS={WORKER_KINDS}",
        f"TELEGRAM_WEBHOOK_SECRET={webhook_secret}",
        "TELEGRAM_LINK_TOKEN_TTL_MINUTES=15",
        "TELEGRAM_TEST_SEND_COOLDOWN_SECONDS=30",
        "# PUBLIC_WEB_BASE_URL left empty — test message has no button (localhost forbidden).",
        "PUBLIC_WEB_BASE_URL=",
        f"TELEGRAM_LIVE_API_PORT={API_PORT}",
        f"TELEGRAM_LIVE_WEBHOOK_PORT={WEBHOOK_PORT}",
        f"TELEGRAM_LIVE_WEB_PORT={WEB_PORT}",
        "TELEGRAM_LIVE_STAND=true",
    ]
    STAND_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ensure_secrets_placeholder() -> None:
    if SECRETS_ENV.exists():
        return
    SECRETS_ENV.write_text(
        "\n".join(
            [
                "# Fill locally. Never commit. Never paste into chat.",
                "TELEGRAM_BOT_TOKEN=",
                "TELEGRAM_BOT_USERNAME=",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    SECRETS_TEMPLATE.write_text(
        "\n".join(
            [
                "Положите токен и username бота в файл:",
                f"  {SECRETS_ENV.relative_to(ROOT).as_posix()}",
                "",
                "Формат:",
                "  TELEGRAM_BOT_TOKEN=<token from BotFather>",
                "  TELEGRAM_BOT_USERNAME=<bot username without @>",
                "",
                "Не присылайте токен в чат. Не копируйте в web/.env или Git.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _secrets_flags() -> dict:
    token = False
    username = False
    if SECRETS_ENV.exists():
        for line in SECRETS_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN=") and line.split("=", 1)[1].strip():
                token = True
            if line.startswith("TELEGRAM_BOT_USERNAME=") and line.split("=", 1)[1].strip():
                username = True
    return {"telegram_bot_token": token, "telegram_bot_username": username}


def _migrate_and_seed(db_url: str) -> str:
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    # Isolate from root .env telegram / LLM while preparing schema
    os.environ.setdefault("ASSISTANT_PROVIDER", "mock")
    try:
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "alembic"))
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")
        head = ScriptDirectory.from_config(cfg).get_current_head()

        # Refresh engine/session bindings for seed
        from app.core.config import get_settings
        from app.db import session as db_session

        get_settings.cache_clear()
        db_session.engine.dispose()
        # Recreate engine against stand URL
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        eng = create_engine(db_url, connect_args={"check_same_thread": False})
        db_session.engine = eng
        db_session.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=eng)

        from scripts.seed_demo import main as seed_main

        seed_main()
        return head or "unknown"
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev


def main() -> int:
    STAND_DIR.mkdir(parents=True, exist_ok=True)
    if STAND_DB.exists():
        STAND_DB.unlink()

    webhook_secret = secrets.token_urlsafe(32)
    _write_stand_env(webhook_secret=webhook_secret)
    _ensure_secrets_placeholder()

    db_url = f"sqlite:///{STAND_DB.resolve().as_posix()}"
    head = _migrate_and_seed(db_url)
    flags = _secrets_flags()

    import json

    manifest = {
        "stage": "TG-3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stand_dir": STAND_DIR.relative_to(ROOT).as_posix(),
        "stand_db": STAND_DB.relative_to(ROOT).as_posix(),
        "stand_env": STAND_ENV.relative_to(ROOT).as_posix(),
        "secrets_env": SECRETS_ENV.relative_to(ROOT).as_posix(),
        "alembic_head": head,
        "worker_kinds": WORKER_KINDS,
        "api_port": API_PORT,
        "webhook_only_port": WEBHOOK_PORT,
        "web_port": WEB_PORT,
        "demo_login_email": "demo@kontur.app",
        "demo_company_id": "cmp_severprom",
        "secrets_present": flags,
        "notes": [
            "Root .env and other stands were not modified.",
            "Worker allowlist TELEGRAM_OUTBOX_KINDS=test — impact/news outbox ignored.",
            "Public tunnel should target webhook-only port, not full API.",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("telegram_live_stand_ready")
    print(f"stand_dir={STAND_DIR.relative_to(ROOT).as_posix()}")
    print(f"alembic_head={head}")
    print(f"worker_kinds={WORKER_KINDS}")
    print(f"api_port={API_PORT}")
    print(f"webhook_only_port={WEBHOOK_PORT}")
    print(f"token_present={str(flags['telegram_bot_token']).lower()}")
    print(f"username_present={str(flags['telegram_bot_username']).lower()}")
    if not flags["telegram_bot_token"]:
        print(f"fill_secrets={SECRETS_ENV.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
