"""Managed news ingestion scheduler — separate process from FastAPI workers.

Interval default 1200s. One active run per database. Missed ticks are not
queued as a burst after idle. Always uses heuristic enrich (no model HTTP).

  python -m app.workers.news_scheduler
  python -m app.workers.news_scheduler --once
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.services.ingestion.scheduler_lock import PidFileLock, SchedulerLockError
from app.services.ingestion.scheduler_run import run_scheduler_tick, state_paths

logger = logging.getLogger(__name__)


class _Stop(Exception):
    pass


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [news_scheduler] %(message)s",
    )
    # Avoid leaking URLs with tokens via httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scheduled heuristic news ingestion")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single tick and exit (no interval loop)",
    )
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="Use in-process mock providers (no outbound HTTP) — Docker/CI smoke only",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=None,
        help="Override NEWS_SCHEDULER_INTERVAL_SECONDS",
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        help="Override NEWS_SCHEDULER_STATE_DIR",
    )
    args = parser.parse_args(argv)

    _configure_logging()
    settings = get_settings()
    interval = int(
        args.interval_seconds
        if args.interval_seconds is not None
        else getattr(settings, "news_scheduler_interval_seconds", 1200) or 1200
    )
    interval = max(30, interval)
    state_dir = Path(
        args.state_dir
        or getattr(settings, "news_scheduler_state_dir", None)
        or "data/news_scheduler"
    )
    database_url = settings.database_url
    paths = state_paths(state_dir, database_url)
    process_lock = PidFileLock(paths["process_lock"])

    try:
        process_lock.acquire()
    except SchedulerLockError as exc:
        logger.error("another_scheduler_running: %s", exc)
        return 2

    stop = False

    def _handle_stop(signum: int, _frame: object) -> None:  # noqa: ARG001
        nonlocal stop
        stop = True
        logger.info("stop_signal signum=%s", signum)

    signal.signal(signal.SIGINT, _handle_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_stop)

    pending_limit = int(getattr(settings, "news_scheduler_pending_limit", 100) or 100)
    http_timeout = float(getattr(settings, "news_scheduler_http_timeout_seconds", 20) or 20)
    max_per_feed = int(getattr(settings, "news_scheduler_max_per_feed", 20) or 20)
    max_per_query = int(getattr(settings, "news_scheduler_max_per_query", 15) or 15)

    fixture_providers = None
    if args.fixtures or (os.environ.get("NEWS_SCHEDULER_USE_FIXTURES") or "").strip() in {
        "1",
        "true",
        "yes",
    }:
        from datetime import datetime, timezone

        from app.services.ingestion.base import FetchedArticle, SourceProvider

        class _FixtureProvider(SourceProvider):
            name = "fixture"
            is_official = False

            def fetch(self):
                # Stable ids so a second tick proves dedupe (no unique uuid4 per call).
                return [
                    FetchedArticle(
                        provider=self.name,
                        external_id="fx-smoke-stable-a",
                        canonical_url="https://fixture.example.com/a/smoke-stable",
                        publisher="Fixture Wire A",
                        title="Fixture export control signal",
                        excerpt="Deterministic fixture article for scheduler smoke.",
                        published_at=datetime.now(timezone.utc),
                        language="en",
                        is_official=False,
                        payload={"fixture": True},
                    ),
                    FetchedArticle(
                        provider=self.name,
                        external_id="fx-smoke-stable-b",
                        canonical_url="https://fixture.example.com/b/smoke-stable",
                        publisher="Fixture Wire B",
                        title="Fixture export control signal",
                        excerpt="Deterministic fixture article for scheduler smoke.",
                        published_at=datetime.now(timezone.utc),
                        language="en",
                        is_official=False,
                        payload={"fixture": True},
                    ),
                ]

        fixture_providers = [_FixtureProvider()]
        logger.info("fixture_providers=1 (no outbound HTTP)")

    logger.info(
        "started interval_s=%s competition=%s heuristic=1 state=%s",
        interval,
        bool(getattr(settings, "competition_mode", False)),
        state_dir.as_posix(),
    )

    exit_code = 0
    try:
        while True:
            if stop:
                break
            # Fresh settings cache not required; DB session per tick.
            get_settings.cache_clear()
            engine.dispose()
            db = SessionLocal()
            try:
                tick = run_scheduler_tick(
                    db,
                    state_dir=state_dir,
                    database_url=database_url,
                    interval_seconds=interval,
                    pending_limit=pending_limit,
                    http_timeout=http_timeout,
                    max_per_feed=max_per_feed,
                    max_per_query=max_per_query,
                    providers=fixture_providers,
                )
                logger.info(
                    "tick ran=%s outcome=%s fetched=%s inserted=%s dup=%s published=%s",
                    tick.ran,
                    tick.outcome,
                    (tick.ingest.fetched if tick.ingest else 0),
                    (tick.ingest.inserted if tick.ingest else 0),
                    (tick.ingest.duplicates if tick.ingest else 0),
                    (tick.ingest.published if tick.ingest else 0),
                )
            finally:
                db.close()

            if args.once:
                break

            # Fixed delay after each attempt — no catch-up burst after idle.
            deadline = time.monotonic() + interval
            while time.monotonic() < deadline:
                if stop:
                    break
                time.sleep(min(1.0, deadline - time.monotonic()))
    except Exception:  # noqa: BLE001
        logger.exception("scheduler_fatal")
        exit_code = 1
    finally:
        process_lock.release()
        logger.info("stopped")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
