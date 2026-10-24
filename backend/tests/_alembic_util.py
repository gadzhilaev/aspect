"""Shared helpers for Alembic SQLite smoke tests (Windows-safe teardown)."""

from __future__ import annotations

import gc
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

ROOT = Path(__file__).resolve().parents[1]

# Current migration head (keep in sync with alembic/versions).
ALEMBIC_HEAD = "011"

HEAD_TABLES = {
    "users",
    "events",
    "companies",
    "company_nodes",
    "company_edges",
    "assistant_conversations",
    "assistant_messages",
    "assistant_tool_runs",
    "decisions",
    "raw_news_items",
    "case_snapshots",
    "case_active_snapshot",
    "case_org_company_links",
    "bank_documents",
    "bank_fragments",
    "notification_outbox",
    "notification_subscriptions",
    "company_registry_lookups",
}


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@contextmanager
def with_db_url(db_url: str):
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    get_settings.cache_clear()
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        get_settings.cache_clear()


def sqlite_engine(path: Path):
    """NullPool so Windows can delete the temp file after dispose()."""
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url, poolclass=NullPool)
    return engine, url


@contextmanager
def temp_sqlite_path(filename: str = "alembic.db"):
    """Temp DB path; rmtree with ignore_errors to avoid WinError 32 masking asserts."""
    tmp = tempfile.mkdtemp(prefix="alembic_test_")
    path = Path(tmp) / filename
    try:
        yield path
    finally:
        gc.collect()
        shutil.rmtree(tmp, ignore_errors=True)


def assert_head_schema(engine) -> str:
    """Assert revision is head and key 008–010 artifacts exist. Returns version_num."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "alembic_version" in tables
    missing = HEAD_TABLES - tables
    assert not missing, f"missing tables at head: {sorted(missing)}"

    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == ALEMBIC_HEAD, f"expected head {ALEMBIC_HEAD}, got {version!r}"

    event_cols = {c["name"] for c in inspector.get_columns("events")}
    assert "severity" in event_cols
    # 009: severity nullable (unknown significance)
    sev = next(c for c in inspector.get_columns("events") if c["name"] == "severity")
    assert sev["nullable"] is True

    outbox_cols = {c["name"] for c in inspector.get_columns("notification_outbox")}
    assert "subscription_id" in outbox_cols
    assert "kind" in outbox_cols

    sub_cols = {c["name"] for c in inspector.get_columns("notification_subscriptions")}
    assert "auto_notify_since" in sub_cols  # 010

    decision_cols = {c["name"] for c in inspector.get_columns("decisions")}
    assert "cancelled_at" in decision_cols
    assert "cancelled_by_user_id" in decision_cols
    assert "cancel_reason" in decision_cols

    # 011: external company registry lookup cache
    reg_cols = {c["name"] for c in inspector.get_columns("company_registry_lookups")}
    assert {"user_id", "inn", "candidates_json", "expires_at"} <= reg_cols
    return version
