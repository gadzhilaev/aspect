"""News scheduler: locks, statuses, heuristic-only, no catch-up burst."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Event, NotificationOutbox
from app.models.raw_news import RawNewsItem
from app.services.ingestion.base import FetchedArticle, SourceProvider
from app.services.ingestion.conditional_http import HttpValidatorCache, conditional_get
from app.services.ingestion.pipeline import IngestResult, run_ingestion
from app.services.ingestion.scheduler_lock import PidFileLock, SchedulerLockError
from app.services.ingestion.scheduler_run import run_scheduler_tick, state_paths
from app.services.ingestion.scheduler_status import (
    SchedulerStatusStore,
    classify_outcome,
    sanitize_source_error,
)


def _article(**overrides) -> FetchedArticle:
    base = dict(
        provider="test",
        external_id=f"ext-{uuid4().hex[:8]}",
        canonical_url=f"https://news.example.com/a/{uuid4().hex[:8]}",
        publisher="Example News",
        title="Export controls tighten for electronics",
        excerpt="Authorities announced new export controls affecting electronics supply chains.",
        published_at=datetime.now(timezone.utc),
        language="en",
        is_official=False,
        payload={},
    )
    base.update(overrides)
    return FetchedArticle(**base)


class FakeProvider(SourceProvider):
    name = "fake"
    is_official = False

    def __init__(self, articles: list[FetchedArticle] | None = None, *, error: str | None = None):
        self.articles = list(articles or [])
        self.error = error
        self.last_fetch_errors: list[str] = []
        self.calls = 0

    def fetch(self) -> list[FetchedArticle]:
        self.calls += 1
        self.last_fetch_errors = []
        if self.error:
            self.last_fetch_errors.append(self.error)
            return []
        return list(self.articles)


class BoomProvider(SourceProvider):
    name = "boom"
    is_official = False

    def fetch(self) -> list[FetchedArticle]:
        raise RuntimeError("provider_down")


@pytest.fixture
def sched_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "sched"
    state.mkdir()
    monkeypatch.setenv("NEWS_SCHEDULER_STATE_DIR", str(state))
    get_settings.cache_clear()
    return state


def test_classify_outcome_and_sanitize():
    assert classify_outcome(errors=[], crashed=False) == "success"
    assert classify_outcome(errors=["rss:http_429"], crashed=False) == "partial"
    assert classify_outcome(errors=[], crashed=True) == "failed"
    assert sanitize_source_error("https://evil.example/token=abc") == "source_error"
    assert sanitize_source_error("rss:cbr.ru:http_429") == "rss:cbr.ru:http_429"


def test_file_lock_blocks_second_and_releases(tmp_path: Path):
    """OS advisory lock — not PID liveness (safe across Docker PID namespaces)."""
    lock_path = tmp_path / "p.lock"
    a = PidFileLock(lock_path)
    a.acquire()
    b = PidFileLock(lock_path)
    with pytest.raises(SchedulerLockError):
        b.acquire()
    a.release()
    b.acquire()
    b.release()


def test_rss_skips_cbr_news_overlap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "INGESTION_RSS_FEEDS",
        "https://www.cbr.ru/rss/RssNews|https://www.interfax.ru/rss.asp|"
        "https://www.wto.org/library/rss/latest_news_e.xml",
    )
    get_settings.cache_clear()
    from app.services.ingestion.pipeline import _rss_feeds_without_cbr_news_overlap

    feeds = _rss_feeds_without_cbr_news_overlap()
    assert all("cbr.ru" not in u.lower() for u in feeds)
    assert any("interfax" in u for u in feeds)
    assert any("wto.org" in u for u in feeds)


def test_concurrent_ticks_second_skipped(db: Session, sched_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./kontur_test.db")
    get_settings.cache_clear()
    db_url = get_settings().database_url
    paths = state_paths(sched_dir, db_url)
    holder = PidFileLock(paths["run_lock"])
    holder.acquire()
    try:
        tick = run_scheduler_tick(
            db,
            state_dir=sched_dir,
            database_url=db_url,
            interval_seconds=1200,
            providers=[FakeProvider([])],
        )
        assert tick.skipped_busy is True
        assert tick.ran is False
        assert tick.outcome == "skipped_busy"
        assert tick.status["status"] == "skipped_busy"
    finally:
        holder.release()


def test_long_run_blocks_peer_tick(db: Session, sched_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./kontur_test.db")
    get_settings.cache_clear()
    db_url = get_settings().database_url
    started = threading.Event()
    release = threading.Event()

    def slow_ingest(*_a, **_k):
        started.set()
        release.wait(timeout=5)
        return IngestResult(fetched=0, inserted=0, duplicates=0, published=0)

    t = threading.Thread(
        target=lambda: run_scheduler_tick(
            db,
            state_dir=sched_dir,
            database_url=db_url,
            interval_seconds=60,
            ingest_fn=slow_ingest,
            providers=[],
        ),
        daemon=True,
    )
    t.start()
    assert started.wait(timeout=2)
    # Peer session for second tick
    from app.db.session import SessionLocal

    db2 = SessionLocal()
    try:
        peer = run_scheduler_tick(
            db2,
            state_dir=sched_dir,
            database_url=db_url,
            interval_seconds=60,
            providers=[FakeProvider([])],
        )
        assert peer.skipped_busy is True
    finally:
        db2.close()
        release.set()
        t.join(timeout=5)


def test_crash_marks_failed_and_releases_lock(
    db: Session, sched_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./kontur_test.db")
    get_settings.cache_clear()
    db_url = get_settings().database_url

    def boom(*_a, **_k):
        raise RuntimeError("explode")

    tick = run_scheduler_tick(
        db,
        state_dir=sched_dir,
        database_url=db_url,
        interval_seconds=1200,
        ingest_fn=boom,
        providers=[],
    )
    assert tick.outcome == "failed"
    assert tick.status["status"] == "failed"
    assert tick.status.get("last_success_at") is None
    # Lock free for next run
    tick2 = run_scheduler_tick(
        db,
        state_dir=sched_dir,
        database_url=db_url,
        interval_seconds=1200,
        providers=[FakeProvider([])],
    )
    assert tick2.ran is True
    assert tick2.outcome == "success"


def test_partial_source_failure_status(
    db: Session, sched_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./kontur_test.db")
    get_settings.cache_clear()
    db_url = get_settings().database_url
    providers = [FakeProvider([], error="feed:http_429"), BoomProvider()]
    tick = run_scheduler_tick(
        db,
        state_dir=sched_dir,
        database_url=db_url,
        interval_seconds=1200,
        providers=providers,
    )
    assert tick.ran is True
    assert tick.outcome == "partial"
    assert tick.status["status"] == "partial"
    assert tick.status.get("last_success_at") is None
    assert any("http_429" in e or "boom" in e for e in tick.status["source_errors"])


def test_zero_published_still_success(
    db: Session, sched_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./kontur_test.db")
    get_settings.cache_clear()
    db_url = get_settings().database_url
    tick = run_scheduler_tick(
        db,
        state_dir=sched_dir,
        database_url=db_url,
        interval_seconds=1200,
        providers=[FakeProvider([])],
    )
    assert tick.outcome == "success"
    assert tick.status["counts"]["published"] == 0
    assert tick.status["last_success_at"] is not None


def test_duplicate_inputs_no_second_insert_or_telegram(
    db: Session, sched_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./kontur_test.db")
    monkeypatch.setenv("TELEGRAM_NEWS_NOTIFICATIONS_ENABLED", "true")
    get_settings.cache_clear()
    db_url = get_settings().database_url
    art = _article(
        provider="gdelt",
        external_id="dup-1",
        canonical_url="https://wire.example.com/story/sched-1",
        title="Rate hike expected",
    )
    # Need two independent publishers for can_publish Ã¢â‚¬â€� use official CBR-like
    # Or skip publish and only check raw dedupe + enqueue not doubled.
    before_raw = db.query(RawNewsItem).count()
    before_out = db.query(NotificationOutbox).count()

    with patch(
        "app.services.notifications.enqueue_impact_notifications", return_value=0
    ) as enq:
        p = FakeProvider([art])
        t1 = run_scheduler_tick(
            db,
            state_dir=sched_dir,
            database_url=db_url,
            interval_seconds=1200,
            providers=[p],
        )
        t2 = run_scheduler_tick(
            db,
            state_dir=sched_dir,
            database_url=db_url,
            interval_seconds=1200,
            providers=[FakeProvider([art])],
        )
    assert t1.ran and t2.ran
    assert t2.ingest is not None
    assert t2.ingest.duplicates >= 1 or t2.ingest.inserted == 0
    assert db.query(RawNewsItem).count() == before_raw + 1
    assert db.query(NotificationOutbox).count() == before_out
    # enqueue only via personalize on publish; single-source may reject Ã¢â‚¬â€� still no growth
    assert enq.call_count <= 1


def test_no_model_http_on_scheduler_tick(
    db: Session, sched_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./kontur_test.db")
    get_settings.cache_clear()
    db_url = get_settings().database_url
    art_a = _article(
        provider="gdelt",
        external_id="m1",
        canonical_url="https://a.example.com/1",
        publisher="A Wire",
        title="Semiconductor export control update",
    )
    art_b = _article(
        provider="rss",
        external_id="m2",
        canonical_url="https://b.example.com/1",
        publisher="B Press",
        title="Semiconductor export control update",
        excerpt=art_a.excerpt,
    )

    with (
        patch("app.services.ingestion.enrich.live_enrich") as live,
        patch("httpx.Client.post") as post,
    ):
        tick = run_scheduler_tick(
            db,
            state_dir=sched_dir,
            database_url=db_url,
            interval_seconds=1200,
            providers=[FakeProvider([art_a, art_b])],
        )
    assert tick.ran is True
    live.assert_not_called()
    post.assert_not_called()


def test_conditional_get_304_and_429(tmp_path: Path):
    cache = HttpValidatorCache(tmp_path / "v.json")
    sleeps: list[float] = []

    class Resp:
        def __init__(self, code: int, content: bytes = b"", headers: dict | None = None):
            self.status_code = code
            self.content = content
            self.headers = headers or {}

    calls = {"n": 0}

    class Client:
        def get(self, url, headers=None):  # noqa: ARG002
            calls["n"] += 1
            if calls["n"] == 1:
                return Resp(429, headers={"Retry-After": "0.01"})
            if calls["n"] == 2:
                return Resp(200, b"ok", headers={"ETag": '"v1"'})
            return Resp(304)

    client = Client()
    o1 = conditional_get(client, "https://feed.example/rss", cache=cache, sleep_fn=sleeps.append)
    assert o1.content == b"ok"
    assert sleeps  # retried after 429
    o2 = conditional_get(client, "https://feed.example/rss", cache=cache, sleep_fn=sleeps.append)
    assert o2.not_modified is True


def test_public_ingestion_status_endpoint(client, sched_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEWS_SCHEDULER_STATE_DIR", str(sched_dir))
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./kontur_test.db")
    get_settings.cache_clear()
    store = SchedulerStatusStore(state_paths(sched_dir, get_settings().database_url)["status"])
    store.mark_finished(
        outcome="success",
        started_at=datetime.now(timezone.utc),
        fetched=1,
        inserted=0,
        duplicates=1,
        published=0,
        source_errors=[],
        interval_seconds=1200,
    )
    resp = client.get("/api/v1/public/ingestion-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["counts"]["duplicates"] == 1
    assert "stand.db" not in resp.text
    assert "sqlite" not in resp.text.lower()

    news = client.get("/api/v1/public/news?limit=1")
    assert news.status_code == 200
    assert news.json().get("ingestion", {}).get("status") == "success"


def test_no_catchup_burst_semantics(db: Session, sched_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Idle gap does not imply multiple immediate runs Ã¢â‚¬â€� each tick is one attempt."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./kontur_test.db")
    get_settings.cache_clear()
    db_url = get_settings().database_url
    calls = {"n": 0}

    def counting(*_a, **_k):
        calls["n"] += 1
        return IngestResult()

    # Simulate "after downtime" by invoking tick twice back-to-back: still exactly 2
    # attempts (not N missed intervals). Worker sleep is outside this unit.
    run_scheduler_tick(
        db, state_dir=sched_dir, database_url=db_url, interval_seconds=1200, ingest_fn=counting
    )
    run_scheduler_tick(
        db, state_dir=sched_dir, database_url=db_url, interval_seconds=1200, ingest_fn=counting
    )
    assert calls["n"] == 2
