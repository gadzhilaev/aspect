"""One scheduled ingestion tick — heuristic only, single-flight per DB."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.ingestion.conditional_http import HttpValidatorCache
from app.services.ingestion.pipeline import IngestResult, run_ingestion
from app.services.ingestion.scheduler_lock import PidFileLock, SchedulerLockError, db_fingerprint
from app.services.ingestion.scheduler_status import (
    SchedulerStatusStore,
    classify_outcome,
    resolve_status_path,
    sanitize_source_error,
)

logger = logging.getLogger(__name__)


@dataclass
class SchedulerTickResult:
    ran: bool
    skipped_busy: bool
    outcome: str
    ingest: IngestResult | None
    status: dict[str, Any]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def state_paths(state_dir: Path, database_url: str) -> dict[str, Path]:
    fp = db_fingerprint(database_url)
    return {
        "process_lock": state_dir / f"scheduler_{fp}.lock",
        "run_lock": state_dir / f"run_{fp}.lock",
        "status": resolve_status_path(state_dir, database_url),
        "http_cache": state_dir / f"http_validators_{fp}.json",
    }


def build_scheduler_providers(
    *,
    http_cache: HttpValidatorCache | None,
    http_timeout: float,
    max_per_feed: int,
    max_per_query: int,
) -> list[Any]:
    """Default providers with bounded timeouts + conditional GET cache."""
    from app.services.ingestion.cbr import CbrProvider
    from app.services.ingestion.gdelt import GdeltProvider
    from app.services.ingestion.rss import RssProvider

    from app.services.ingestion.pipeline import _rss_feeds_without_cbr_news_overlap

    return [
        CbrProvider(timeout=http_timeout, validator_cache=http_cache),
        GdeltProvider(
            timeout=http_timeout,
            max_per_query=max_per_query,
            validator_cache=http_cache,
        ),
        RssProvider(
            feed_urls=_rss_feeds_without_cbr_news_overlap(),
            timeout=http_timeout,
            max_per_feed=max_per_feed,
            validator_cache=http_cache,
        ),
    ]


def run_scheduler_tick(
    db: Session,
    *,
    state_dir: Path,
    database_url: str,
    interval_seconds: int = 1200,
    pending_limit: int = 100,
    http_timeout: float = 20.0,
    max_per_feed: int = 20,
    max_per_query: int = 15,
    providers: Sequence[Any] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    ingest_fn: Callable[..., IngestResult] | None = None,
) -> SchedulerTickResult:
    """Attempt one ingest. If a run lock is held, skip without queuing catch-up."""
    paths = state_paths(state_dir, database_url)
    status_store = SchedulerStatusStore(paths["status"])
    run_lock = PidFileLock(paths["run_lock"])
    started = _utc_now()

    try:
        run_lock.acquire()
    except SchedulerLockError:
        status_store.mark_finished(
            outcome="skipped_busy",
            started_at=started,
            finished_at=_utc_now(),
            interval_seconds=interval_seconds,
            skipped=True,
        )
        return SchedulerTickResult(
            ran=False,
            skipped_busy=True,
            outcome="skipped_busy",
            ingest=None,
            status=status_store.public_view(),
        )

    status_store.mark_running(started_at=started)
    settings = get_settings()
    # Competition / hackathon: never prefer live enrich in this path.
    prefer_live = False
    if getattr(settings, "competition_mode", False):
        prefer_live = False

    http_cache = HttpValidatorCache(paths["http_cache"])
    provider_list = (
        list(providers)
        if providers is not None
        else build_scheduler_providers(
            http_cache=http_cache,
            http_timeout=http_timeout,
            max_per_feed=max_per_feed,
            max_per_query=max_per_query,
        )
    )

    runner = ingest_fn or run_ingestion
    ingest: IngestResult | None = None
    crashed = False
    try:
        # sleep_fn reserved for provider 429 tests via conditional_http
        _ = sleep_fn
        ingest = runner(
            db,
            providers=provider_list,
            prefer_live_enrich=prefer_live,
            fetch=True,
            process=True,
            personalize=True,
            pending_limit=pending_limit,
        )
    except Exception:  # noqa: BLE001
        logger.exception("news_scheduler_tick_failed")
        crashed = True
        ingest = IngestResult(errors=["tick_crashed"])
    finally:
        run_lock.release()

    errors = [e for e in (sanitize_source_error(x) for x in (ingest.errors if ingest else [])) if e]
    outcome = classify_outcome(errors=errors, crashed=crashed)
    finished = _utc_now()
    status_store.mark_finished(
        outcome=outcome,
        started_at=started,
        finished_at=finished,
        fetched=ingest.fetched if ingest else 0,
        inserted=ingest.inserted if ingest else 0,
        duplicates=ingest.duplicates if ingest else 0,
        published=ingest.published if ingest else 0,
        source_errors=errors,
        interval_seconds=interval_seconds,
        skipped=False,
    )
    return SchedulerTickResult(
        ran=True,
        skipped_busy=False,
        outcome=outcome,
        ingest=ingest,
        status=status_store.public_view(),
    )
