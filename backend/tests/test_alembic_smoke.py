"""Migration smoke: alembic upgrade head on an empty temporary SQLite DB."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from app.db.base import Base
from tests._alembic_util import (
    ALEMBIC_HEAD,
    alembic_config,
    assert_head_schema,
    sqlite_engine,
    temp_sqlite_path,
    with_db_url,
)


def _postgres_db_name(db_url: str) -> str:
    parsed = urlparse(db_url)
    name = (parsed.path or "").lstrip("/")
    if "?" in name:
        name = name.split("?", 1)[0]
    return name


def test_alembic_upgrade_head_on_empty_sqlite():
    with temp_sqlite_path("alembic_smoke.db") as db_path:
        engine, db_url = sqlite_engine(db_path)
        try:
            with with_db_url(db_url):
                cfg = alembic_config()
                command.upgrade(cfg, "head")
                command.upgrade(cfg, "head")  # idempotent
                assert_head_schema(engine)
        finally:
            engine.dispose()


def test_alembic_002_skips_existing_assistant_tables():
    """Historical 001 used create_all with current models — later revisions must not fail."""
    with temp_sqlite_path("legacy_create_all.db") as db_path:
        engine, db_url = sqlite_engine(db_path)
        try:
            with with_db_url(db_url):
                import app.models  # noqa: F401

                Base.metadata.create_all(bind=engine)
                engine.dispose()
                engine, _ = sqlite_engine(db_path)

                cfg = alembic_config()
                command.stamp(cfg, "001")
                command.upgrade(cfg, "head")
                assert_head_schema(engine)
                assert "assistant_conversations" in inspect(engine).get_table_names()
                assert "raw_news_items" in inspect(engine).get_table_names()
        finally:
            engine.dispose()


def test_alembic_upgrade_head_on_empty_postgres():
    db_url = os.getenv("ALEMBIC_POSTGRES_URL")
    if not db_url:
        pytest.skip("Set ALEMBIC_POSTGRES_URL to a disposable DB ending with _test")

    db_name = _postgres_db_name(db_url)
    if not db_name.endswith("_test"):
        pytest.fail(
            f"Refusing Postgres migration smoke: database name must end with '_test' "
            f"(got {db_name!r}). Use a disposable test database only."
        )

    with with_db_url(db_url):
        cfg = alembic_config()
        engine = create_engine(db_url, poolclass=NullPool)
        inspector = inspect(engine)
        with engine.begin() as conn:
            for table in reversed(inspector.get_table_names()):
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
        engine.dispose()

        command.upgrade(cfg, "head")
        engine = create_engine(db_url, poolclass=NullPool)
        try:
            ver = assert_head_schema(engine)
            assert ver == ALEMBIC_HEAD
        finally:
            engine.dispose()
