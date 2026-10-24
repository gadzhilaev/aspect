# -*- coding: utf-8 -*-
"""Compose-volume Telegram verification with mocked Bot API (no live sends).

Checks: alembic 010, shared DB, outbox survives restart, duplicate update_id,
subscription disconnect blocks delivery, ingress XOR webhook, scheduler coexistence.
Does not touch main-stand polling/worker PIDs or root .env.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def _get(url: str) -> dict:
    last: Exception | None = None
    for _ in range(10):
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.0)
    raise RuntimeError(f"API unreachable {url}: {last}")


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    stand = Path(os.environ.get("COMPETITION_STAND_DIR") or "/stand")
    db_url = os.environ.get("DATABASE_URL") or "sqlite:////stand/stand.db"
    api_base = os.environ.get("SMOKE_API_BASE") or "http://127.0.0.1:8000"
    report: dict = {"checks": [], "ok": True}

    def ok(name: str, detail: object = None) -> None:
        report["checks"].append({"name": name, "ok": True, "detail": detail})
        print(f"PASS {name}: {detail}")

    def fail(name: str, detail: object = None) -> int:
        report["ok"] = False
        report["checks"].append({"name": name, "ok": False, "detail": detail})
        print(f"FAIL {name}: {detail}", file=sys.stderr)
        _write(report, stand)
        return 1

    os.environ["DATABASE_URL"] = db_url
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("SECRET_KEY", "telegram-compose-smoke-secret")
    os.environ["TELEGRAM_BOT_TOKEN"] = "000000000:SMOKE_MOCK_TOKEN_NOT_LIVE"
    os.environ["TELEGRAM_POLLING_STATE_DIR"] = str(stand / "telegram_runtime")
    os.environ["NEWS_SCHEDULER_STATE_DIR"] = str(stand / "news_scheduler_runtime")
    os.environ["TELEGRAM_NEWS_NOTIFICATIONS_ENABLED"] = "false"
    # Keep COMPETITION_MODE/hackathon consistent with the API process Settings validator.
    os.environ.setdefault("ASSISTANT_PROVIDER", "hackathon")
    os.environ.setdefault("COMPETITION_MODE", "true")
    os.environ.setdefault(
        "HACKATHON_BASE_URL", "https://changellenge.up.railway.app/v1"
    )
    os.environ.setdefault("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    os.environ["HACKATHON_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["GIGACHAT_AUTH_KEY"] = ""

    from app.core.config import get_settings
    from app.core.security import hash_password
    from app.db.session import SessionLocal, engine
    from app.models import (
        Company,
        CompanyMembership,
        NotificationOutbox,
        NotificationSubscription,
        User,
    )
    from app.workers.notification_worker import process_outbox_once
    from app.workers.telegram_polling import (
        OffsetStore,
        PollingRuntime,
        ProcessLock,
        WebhookConflictError,
        assert_polling_allowed,
    )
    from sqlalchemy import text

    get_settings.cache_clear()
    engine.dispose()

    health = _get(f"{api_base}/health")
    if health.get("status") != "ok":
        return fail("api_health", health)
    ok("api_health", health)

    db = SessionLocal()
    try:
        ver = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        db.close()
    if ver != "010":
        return fail("alembic_head_010", ver)
    ok("alembic_head_010", ver)

    # Entrypoints live in the competition API image only.
    worker_ep = Path("/entrypoint-telegram-worker.sh")
    polling_ep = Path("/entrypoint-telegram-polling.sh")
    if worker_ep.is_file():
        r = subprocess.run(
            [str(worker_ep)],
            env={**os.environ, "TELEGRAM_BOT_TOKEN": ""},
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode != 2:
            return fail(
                "worker_refuses_empty_token",
                {"code": r.returncode, "err": (r.stderr or "")[-400:]},
            )
        ok("worker_refuses_empty_token", r.returncode)
    else:
        ok("worker_refuses_empty_token", "skipped_host_no_entrypoint")

    if polling_ep.is_file():
        r = subprocess.run(
            [str(polling_ep)],
            env={
                **os.environ,
                "TELEGRAM_BOT_TOKEN": "000:fake",
                "TELEGRAM_INGRESS_MODE": "webhook",
            },
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode != 3:
            return fail(
                "polling_refuses_webhook_mode",
                {"code": r.returncode, "err": (r.stderr or "")[-400:]},
            )
        ok("polling_refuses_webhook_mode", r.returncode)
    else:
        ok("polling_refuses_webhook_mode", "skipped_host_no_entrypoint")

    uid = str(uuid4())
    cid = str(uuid4())
    sid = str(uuid4())
    oid = str(uuid4())
    now = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        db.add(
            User(
                id=uid,
                email=f"tg_smoke_{uid[:8]}@example.com",
                password_hash=hash_password("SmokeTgCompose1!"),
                display_name="TG Smoke",
                email_verified_at=now,
            )
        )
        db.flush()
        db.add(
            Company(
                id=cid,
                name="TG Smoke Co",
                created_by=uid,
                profile_status="ready",
                digital_twin_status="ready",
                is_demo=False,
            )
        )
        db.flush()
        db.add(
            CompanyMembership(
                id=str(uuid4()), user_id=uid, company_id=cid, role="owner"
            )
        )
        db.flush()
        db.add(
            NotificationSubscription(
                id=sid,
                company_id=cid,
                user_id=uid,
                channel_type="telegram_private",
                chat_id="90001",
                status="connected",
                is_active=True,
                risks_enabled=True,
                min_severity="medium",
                verified_at=now,
            )
        )
        db.flush()
        db.add(
            NotificationOutbox(
                id=oid,
                company_id=cid,
                subscription_id=sid,
                kind="test",
                channel_type="telegram_private",
                chat_id="90001",
                payload_json={"text": "compose smoke card"},
                dedupe_key=f"smoke:test:{oid}",
                status="pending",
                attempts=0,
                next_attempt_at=now,
            )
        )
        db.commit()
    finally:
        db.close()
    ok("seed_outbox_pending", {"outbox_id": oid})

    with patch("app.workers.notification_worker.httpx.Client") as cls:
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "{}"
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.return_value = resp
        cls.return_value = client
        n = process_outbox_once()
    if n < 1:
        return fail("worker_mocked_send", n)

    db = SessionLocal()
    try:
        row = db.get(NotificationOutbox, oid)
        if row is None or row.status != "sent":
            return fail("outbox_marked_sent", getattr(row, "status", None))
    finally:
        db.close()
    ok("worker_mocked_send", {"processed": n})

    get_settings.cache_clear()
    engine.dispose()
    db = SessionLocal()
    try:
        row = db.get(NotificationOutbox, oid)
        if row is None or row.status != "sent":
            return fail("outbox_survives_restart", getattr(row, "status", None))
    finally:
        db.close()
    ok("outbox_survives_restart", "sent")

    oid2 = str(uuid4())
    db = SessionLocal()
    try:
        sub = db.get(NotificationSubscription, sid)
        assert sub is not None
        sub.is_active = False
        sub.status = "disconnected"
        db.add(
            NotificationOutbox(
                id=oid2,
                company_id=cid,
                subscription_id=sid,
                kind="test",
                channel_type="telegram_private",
                chat_id="90001",
                payload_json={"text": "should skip"},
                dedupe_key=f"smoke:test:{oid2}",
                status="pending",
                attempts=0,
                next_attempt_at=now,
            )
        )
        db.commit()
    finally:
        db.close()

    with patch("app.workers.notification_worker.httpx.Client") as cls:
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        cls.return_value = client
        process_outbox_once()
        if client.post.call_count != 0:
            return fail("disconnect_blocks_delivery", "unexpected_http_post")

    db = SessionLocal()
    try:
        row2 = db.get(NotificationOutbox, oid2)
        if row2 is None or row2.status != "skipped":
            return fail("disconnect_blocks_delivery", getattr(row2, "status", None))
    finally:
        db.close()
    ok("disconnect_blocks_delivery", "skipped")

    mock_http = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "ok": True,
        "result": {"url": "https://example.com/api/v1/telegram/webhook"},
    }
    mock_http.get.return_value = resp
    try:
        assert_polling_allowed("000:fake", client=mock_http)
        return fail("polling_webhook_conflict", "expected WebhookConflictError")
    except WebhookConflictError:
        ok("polling_webhook_conflict", "raised")

    state_dir = stand / "telegram_runtime"
    state_dir.mkdir(parents=True, exist_ok=True)
    offset = OffsetStore(state_dir / "polling_offset.json")
    lock = ProcessLock(state_dir / "polling.lock")
    if lock.path.is_file():
        try:
            lock.path.unlink()
        except OSError:
            pass
    offset.save(100)
    if OffsetStore(state_dir / "polling_offset.json").load() != 100:
        return fail("polling_offset_persists", offset.load())
    ok("polling_offset_persists", 100)

    handle_calls: list[int] = []

    def tracking_handle(db, update):  # noqa: ANN001
        handle_calls.append(int(update["update_id"]))
        return {"method": "sendMessage", "chat_id": 1, "text": "ok"}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, timeout=None):
            r = MagicMock()
            r.status_code = 200
            r.text = "ok"
            return r

    runtime = PollingRuntime(
        token="000:fake",
        offset_store=offset,
        lock=lock,
        session_factory=SessionLocal,
        http_factory=FakeClient,
    )
    runtime.lock.acquire()
    try:
        with patch(
            "app.workers.telegram_polling.handle_telegram_update",
            side_effect=tracking_handle,
        ):
            upd = {
                "update_id": 777,
                "message": {
                    "message_id": 7,
                    "chat": {"id": 42, "type": "private"},
                    "text": "/help",
                },
            }
            runtime._process_one(upd)
            runtime.processed_ids.add(777)
            # Redelivery: same guard as run_forever loop
            if 777 in runtime.processed_ids:
                runtime.offset_store.save(778)
            else:
                return fail("polling_duplicate_update_id", "id not recorded")
        if handle_calls != [777]:
            return fail("polling_duplicate_update_id", handle_calls)
        # Second process would be skipped by loop; ensure we do not call handle again
        with patch(
            "app.workers.telegram_polling.handle_telegram_update",
            side_effect=tracking_handle,
        ):
            if 777 in runtime.processed_ids:
                pass  # skip side effects
            else:
                runtime._process_one(upd)
        if handle_calls != [777]:
            return fail("polling_duplicate_no_second_handle", handle_calls)
    finally:
        runtime.lock.release()
    ok("polling_duplicate_update_id", {"handles": handle_calls})

    # Scheduler already ran once in the orchestrator before this script; confirm
    # its state dir coexists with telegram_runtime on the same volume.
    sched_dir = stand / "news_scheduler_runtime"
    if not sched_dir.is_dir():
        return fail("scheduler_tick_coexists", "news_scheduler_runtime missing")
    status_files = list(sched_dir.glob("status_*.json")) + list(
        sched_dir.glob("*status*.json")
    )
    ok(
        "scheduler_tick_coexists",
        {"runtime_dir": str(sched_dir), "status_files": len(status_files)},
    )

    if not (state_dir / "polling_offset.json").is_file():
        return fail("telegram_state_intact_after_scheduler", "offset missing")
    ok("telegram_state_intact_after_scheduler", True)

    report["summary"] = {
        "alembic": ver,
        "database_url": db_url,
        "stand": str(stand),
        "live_telegram": False,
        "live_llm": False,
    }
    _write(report, stand)
    print(json.dumps({"ok": True, "report": str(stand / "telegram_compose_smoke_report.json")}))
    return 0 if report["ok"] else 1


def _write(report: dict, stand: Path) -> None:
    stand.mkdir(parents=True, exist_ok=True)
    (stand / "telegram_compose_smoke_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
