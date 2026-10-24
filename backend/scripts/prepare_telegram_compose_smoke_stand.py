# -*- coding: utf-8 -*-
"""Prepare isolated stand volume for Telegram Compose smoke.

Runs alembic upgrade head (expects 010). Does not touch real_news_613 / root .env /
main-stand polling PIDs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    stand = Path(os.environ.get("COMPETITION_STAND_DIR") or "/stand")
    stand.mkdir(parents=True, exist_ok=True)
    (stand / "news_scheduler_runtime").mkdir(parents=True, exist_ok=True)
    (stand / "telegram_runtime").mkdir(parents=True, exist_ok=True)
    (stand / "storage").mkdir(parents=True, exist_ok=True)

    db_path = stand / "stand.db"
    db_url = (os.environ.get("DATABASE_URL") or f"sqlite:///{db_path.as_posix()}").strip()
    # Normalize container path
    if db_url.startswith("sqlite:////stand"):
        pass
    elif "stand.db" not in db_url:
        db_url = f"sqlite:///{db_path.as_posix()}"

    os.environ["DATABASE_URL"] = db_url
    os.environ["APP_ENV"] = "test"
    os.environ.setdefault("SECRET_KEY", "telegram-compose-smoke-secret")
    os.environ["COMPETITION_MODE"] = "true"
    os.environ["ASSISTANT_PROVIDER"] = "hackathon"
    os.environ.setdefault("HACKATHON_BASE_URL", "https://changellenge.up.railway.app/v1")
    os.environ.setdefault("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    os.environ["NEWS_SCHEDULER_STATE_DIR"] = str(stand / "news_scheduler_runtime")
    os.environ["TELEGRAM_POLLING_STATE_DIR"] = str(stand / "telegram_runtime")
    os.environ["TELEGRAM_BOT_TOKEN"] = ""
    os.environ["TELEGRAM_NEWS_NOTIFICATIONS_ENABLED"] = "false"
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["GIGACHAT_AUTH_KEY"] = ""
    os.environ["HACKATHON_API_KEY"] = ""

    sys.path.insert(0, str(ROOT))
    from alembic import command
    from alembic.config import Config
    from app.core.config import get_settings
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    get_settings.cache_clear()

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")

    engine = create_engine(db_url, poolclass=NullPool)
    with engine.connect() as conn:
        ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    if ver != "010":
        print(json.dumps({"ok": False, "error": "expected_alembic_010", "got": ver}), file=sys.stderr)
        return 1

    status = {
        "status": "ready",
        "ready_for_launch": True,
        "mode": "telegram_compose_smoke",
        "alembic_head": ver,
        "note": "isolated volume — mocked Telegram only; no live bot",
    }
    (stand / "stand_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    env_lines = [
        f"DATABASE_URL={db_url}",
        "APP_ENV=test",
        "SECRET_KEY=telegram-compose-smoke-secret",
        "COMPETITION_MODE=true",
        "ASSISTANT_PROVIDER=hackathon",
        "HACKATHON_BASE_URL=https://changellenge.up.railway.app/v1",
        "HACKATHON_MODEL=deepseek/deepseek-v4.1-flash",
        "NEWS_SCHEDULER_STATE_DIR=/stand/news_scheduler_runtime",
        "TELEGRAM_POLLING_STATE_DIR=/stand/telegram_runtime",
        "TELEGRAM_NEWS_NOTIFICATIONS_ENABLED=false",
        "TELEGRAM_BOT_TOKEN=",
    ]
    (stand / "stand.env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"ok": True, "stand": str(stand), "database_url": db_url, "alembic": ver},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
