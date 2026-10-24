# -*- coding: utf-8 -*-
"""Prepare a minimal competition-like stand dir for news_scheduler Docker smoke.

Does not touch real_news_613 / telegram / root .env.
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
    (stand / "storage").mkdir(parents=True, exist_ok=True)

    # Prefer compose-provided URL; default to container absolute sqlite path.
    db_url = (os.environ.get("DATABASE_URL") or "sqlite:////stand/stand.db").strip()
    os.environ["DATABASE_URL"] = db_url
    # Settings.app_env is Literal[development|test|production] — never "competition".
    os.environ["APP_ENV"] = "test"
    os.environ.setdefault("SECRET_KEY", "news-scheduler-smoke-secret")
    os.environ["COMPETITION_MODE"] = "true"
    os.environ["ASSISTANT_PROVIDER"] = "hackathon"
    os.environ.setdefault("HACKATHON_BASE_URL", "https://changellenge.up.railway.app/v1")
    os.environ.setdefault("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    os.environ["NEWS_SCHEDULER_STATE_DIR"] = str(stand / "news_scheduler_runtime")
    os.environ["TELEGRAM_BOT_TOKEN"] = ""
    os.environ["TELEGRAM_NEWS_NOTIFICATIONS_ENABLED"] = "false"
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["GIGACHAT_AUTH_KEY"] = ""
    os.environ["HACKATHON_API_KEY"] = ""

    sys.path.insert(0, str(ROOT))
    from app.core.config import get_settings
    from app.db.base import Base
    from app.db.session import engine

    get_settings.cache_clear()
    engine.dispose()
    Base.metadata.create_all(bind=engine)

    status = {
        "status": "ready",
        "ready_for_launch": True,
        "mode": "news_scheduler_smoke",
        "note": "minimal stand — no case CSV / no telegram",
    }
    (stand / "stand_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    env_lines = [
        f"DATABASE_URL={db_url}",
        "APP_ENV=test",
        "SECRET_KEY=news-scheduler-smoke-secret",
        "COMPETITION_MODE=true",
        "ASSISTANT_PROVIDER=hackathon",
        "HACKATHON_BASE_URL=https://changellenge.up.railway.app/v1",
        "HACKATHON_MODEL=deepseek/deepseek-v4.1-flash",
        "NEWS_SCHEDULER_STATE_DIR=/stand/news_scheduler_runtime",
        "TELEGRAM_NEWS_NOTIFICATIONS_ENABLED=false",
        "TELEGRAM_BOT_TOKEN=",
    ]
    (stand / "stand.env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "stand": str(stand), "database_url": db_url}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
