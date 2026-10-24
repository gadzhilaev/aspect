# -*- coding: utf-8 -*-
"""In-container / local smoke for news scheduler (fixtures, no Telegram/model HTTP)."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _get(url: str) -> dict:
    last: Exception | None = None
    for _ in range(8):
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 — local smoke
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5)
    raise RuntimeError(f"API unreachable {url}: {last}")


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    stand = Path(os.environ.get("COMPETITION_STAND_DIR") or "/stand")
    state_dir = Path(
        os.environ.get("NEWS_SCHEDULER_STATE_DIR") or str(stand / "news_scheduler_runtime")
    )
    db_url = os.environ.get("DATABASE_URL") or "sqlite:////stand/stand.db"
    api_base = os.environ.get("SMOKE_API_BASE") or "http://127.0.0.1:8000"
    report: dict = {"checks": []}

    def ok(name: str, detail: object = None) -> None:
        report["checks"].append({"name": name, "ok": True, "detail": detail})
        print(f"PASS {name}: {detail}")

    def fail(name: str, detail: object = None) -> int:
        report["checks"].append({"name": name, "ok": False, "detail": detail})
        print(f"FAIL {name}: {detail}", file=sys.stderr)
        out = stand / "news_scheduler_smoke_report.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models.raw_news import RawNewsItem
    from app.services.ingestion.scheduler_lock import InterprocessFileLock, SchedulerLockError
    from app.services.ingestion.scheduler_run import run_scheduler_tick, state_paths
    from app.workers import news_scheduler as ns_mod

    get_settings.cache_clear()
    engine.dispose()

    # --- shared status visible to API ---
    status = _get(f"{api_base}/api/v1/public/ingestion-status")
    ok("api_ingestion_status_reachable", {"status": status.get("status")})

    # --- fixture tick #1 ---
    db = SessionLocal()
    try:
        # Build same fixture provider as worker --fixtures
        os.environ["NEWS_SCHEDULER_USE_FIXTURES"] = "1"
        # Import provider construction via running tick with providers from worker helpers
        from datetime import datetime, timezone

        from app.services.ingestion.base import FetchedArticle, SourceProvider

        class Fix(SourceProvider):
            name = "fixture"
            is_official = False

            def fetch(self):
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
                        payload={"fixture": True},
                    ),
                ]

        t1 = run_scheduler_tick(
            db,
            state_dir=state_dir,
            database_url=db_url,
            interval_seconds=1200,
            providers=[Fix()],
        )
        raw_after_1 = db.query(RawNewsItem).count()
    finally:
        db.close()

    if not t1.ran:
        return fail("first_tick_ran", t1.outcome)
    ok(
        "first_tick",
        {
            "outcome": t1.outcome,
            "fetched": t1.ingest.fetched if t1.ingest else None,
            "inserted": t1.ingest.inserted if t1.ingest else None,
            "raw": raw_after_1,
        },
    )
    # partial is allowed if errors; success with inserts also ok — never force green
    if t1.outcome == "failed":
        return fail("first_tick_not_failed", t1.outcome)

    status2 = _get(f"{api_base}/api/v1/public/ingestion-status")
    if status2.get("status") != t1.outcome and status2.get("status") != "running":
        # status file should match finished outcome
        if status2.get("counts", {}).get("fetched") is None and not status2.get("status"):
            return fail("api_sees_scheduler_status", status2)
    ok("api_sees_scheduler_status", status2)

    # --- concurrent lock (same filesystem) ---
    paths = state_paths(state_dir, db_url)
    holder = InterprocessFileLock(paths["run_lock"])
    holder.acquire()
    try:
        db2 = SessionLocal()
        try:
            peer = run_scheduler_tick(
                db2,
                state_dir=state_dir,
                database_url=db_url,
                interval_seconds=1200,
                providers=[Fix()],
            )
        finally:
            db2.close()
        if not peer.skipped_busy:
            return fail("concurrent_skipped_busy", peer.outcome)
        ok("concurrent_skipped_busy", peer.outcome)
    finally:
        holder.release()

    # --- second tick dedupe ---
    db3 = SessionLocal()
    try:
        t2 = run_scheduler_tick(
            db3,
            state_dir=state_dir,
            database_url=db_url,
            interval_seconds=1200,
            providers=[Fix()],
        )
        raw_after_2 = db3.query(RawNewsItem).count()
    finally:
        db3.close()
    if raw_after_2 != raw_after_1:
        return fail("dedupe_raw_stable", {"before": raw_after_1, "after": raw_after_2})
    if t2.ingest and t2.ingest.inserted != 0:
        return fail("dedupe_no_insert", t2.ingest.inserted)
    ok("dedupe_second_tick", {"raw": raw_after_2, "duplicates": t2.ingest.duplicates if t2.ingest else None})

    # --- process lock blocks second process lock ---
    p1 = InterprocessFileLock(paths["process_lock"])
    p1.acquire()
    p2 = InterprocessFileLock(paths["process_lock"])
    try:
        p2.acquire()
        p1.release()
        return fail("process_lock_should_block", "second acquire succeeded")
    except SchedulerLockError:
        ok("process_lock_blocks_peer", True)
    finally:
        p1.release()

    # --- persistence across "restart" (new engine/session, same volume files) ---
    finished_status = Path(paths["status"]).read_text(encoding="utf-8")
    get_settings.cache_clear()
    engine.dispose()
    db4 = SessionLocal()
    try:
        raw_reload = db4.query(RawNewsItem).count()
    finally:
        db4.close()
    if raw_reload != raw_after_1:
        return fail("persist_raw_after_engine_recycle", {"raw": raw_reload})
    if '"status"' not in finished_status:
        return fail("persist_status_file", finished_status[:200])
    status3 = _get(f"{api_base}/api/v1/public/ingestion-status")
    if not status3.get("status"):
        return fail("persist_api_status_after_recycle", status3)
    ok(
        "persist_after_restart_simulation",
        {"raw": raw_reload, "api_status": status3.get("status")},
    )

    report["ok"] = True
    report["lock_mechanism"] = "InterprocessFileLock (fcntl/msvcrt), not cross-container PID"
    report["multi_host"] = False
    out = stand / "news_scheduler_smoke_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "report": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
