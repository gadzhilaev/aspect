"""Create a fresh verification SQLite DB and migrate to Alembic head."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
VER = ROOT / "data" / "case" / "verification"


def main() -> None:
    VER.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db_path = VER / f"case_verify_{stamp}.db"
    url = f"sqlite:///{db_path.resolve().as_posix()}"
    (VER / "latest_db_path.txt").write_text(str(db_path.resolve()), encoding="utf-8")
    (VER / "latest_db_url.txt").write_text(url, encoding="utf-8")

    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    try:
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "alembic"))
        command.upgrade(cfg, "head")
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        get_settings.cache_clear()

    eng = create_engine(url)
    with eng.connect() as conn:
        rev = MigrationContext.configure(conn).get_current_revision()
    head = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head()
    print(f"db={db_path}")
    print(f"url={url}")
    print(f"revision={rev} head={head}")
    print(f"case_snapshots={'case_snapshots' in inspect(eng).get_table_names()}")
    eng.dispose()


if __name__ == "__main__":
    main()
