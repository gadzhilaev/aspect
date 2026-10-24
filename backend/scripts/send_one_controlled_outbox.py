# -*- coding: utf-8 -*-
"""TG-5: send exactly one pending outbox row (controlled news). No auto-retry on uncertain."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "data/competition_stand/real_news_613/telegram_runtime"
PAIR_ENV = RUNTIME / "controlled_pair.env"
PREVIEW = RUNTIME / "controlled_preview.json"
RESULT = RUNTIME / "controlled_send_result.json"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    _load_dotenv(ROOT / "data/competition_stand/real_news_613/stand.env")
    _load_dotenv(ROOT / "data/competition_stand/real_news_613/telegram_process.env")
    _load_dotenv(ROOT / "data/telegram_live/.env.secrets")
    _load_dotenv(PAIR_ENV)

    os.environ["DATABASE_URL"] = "sqlite:///./data/competition_stand/real_news_613/stand.db"
    os.environ["TELEGRAM_NEWS_NOTIFICATIONS_ENABLED"] = "false"
    os.environ["TELEGRAM_OUTBOX_KINDS"] = "test"  # do not open general news worker
    os.environ.setdefault("COMPETITION_MODE", "false")
    os.environ.setdefault("ASSISTANT_PROVIDER", "mock")
    os.environ["PUBLIC_WEB_BASE_URL"] = ""
    os.environ["DEEP_LINK_BASE"] = ""

    outbox_id = (os.environ.get("CONTROLLED_OUTBOX_ID") or "").strip()
    if not outbox_id and PREVIEW.is_file():
        outbox_id = json.loads(PREVIEW.read_text(encoding="utf-8")).get("outbox_id") or ""
    if not outbox_id:
        print("ERROR: CONTROLLED_OUTBOX_ID missing", file=sys.stderr)
        return 2

    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models import NotificationOutbox
    from app.services.notifications import subscription_allows_send
    from app.workers.notification_worker import _send

    get_settings.cache_clear()
    engine.dispose()
    settings = get_settings()
    if not settings.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN missing", file=sys.stderr)
        return 2

    db = SessionLocal()
    row = db.get(NotificationOutbox, outbox_id)
    if row is None:
        print("ERROR: outbox not found", outbox_id, file=sys.stderr)
        return 3
    if row.kind != "news":
        print("ERROR: refusing non-news kind", row.kind, file=sys.stderr)
        return 4
    if row.status not in {"pending", "retry"}:
        print("ERROR: refusing status", row.status, file=sys.stderr)
        return 5

    allowed, reason = subscription_allows_send(db, outbox=row)
    if not allowed:
        row.status = "skipped"
        row.last_error = f"pre_send_denied:{reason}"
        row.attempts += 1
        db.commit()
        result = {
            "outbox_id": outbox_id,
            "outcome": "skipped",
            "reason": reason,
            "sent_at": None,
            "auto_retry": False,
        }
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 6

    outcome = _send(row, settings.telegram_bot_token)
    row.attempts += 1
    now = datetime.now(timezone.utc)
    if outcome == "sent":
        row.status = "sent"
        row.sent_at = now
        row.last_error = None
    elif outcome == "blocked":
        row.status = "blocked"
        row.last_error = "telegram_403_blocked"
    elif outcome == "uncertain":
        # Explicit: do NOT schedule automatic retry for controlled one-shot.
        row.status = "uncertain"
        row.next_attempt_at = None
        row.last_error = "timeout_uncertain_no_auto_retry"
    elif outcome == "rate_limited":
        row.status = "failed"
        row.next_attempt_at = None
        row.last_error = "telegram_429_no_auto_retry_controlled"
    else:
        row.status = "failed"
        row.next_attempt_at = None

    db.commit()

    # Idempotency: same subscription+event must not get a second outbox row.
    from uuid import uuid4

    from sqlalchemy.exc import IntegrityError

    from app.models import Event, EventImpact
    from app.services.telegram_news_policy import news_dedupe_key

    impact = db.get(EventImpact, row.event_impact_id) if row.event_impact_id else None
    event = db.get(Event, impact.event_id) if impact else None
    dup_created = None
    if impact is not None and event is not None and row.subscription_id:
        dedupe = news_dedupe_key(subscription_id=row.subscription_id, event_id=event.id)
        before = db.query(NotificationOutbox).filter(NotificationOutbox.dedupe_key == dedupe).count()
        dup = NotificationOutbox(
            id=str(uuid4()),
            company_id=row.company_id,
            subscription_id=row.subscription_id,
            kind="news",
            event_impact_id=impact.id,
            channel_type="telegram_private",
            chat_id=row.chat_id,
            payload_json={"text": "should-not-insert"},
            dedupe_key=dedupe,
            status="pending",
            attempts=0,
            next_attempt_at=datetime.now(timezone.utc),
        )
        db.add(dup)
        integrity_blocked = False
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            integrity_blocked = True
        db.rollback()
        after = db.query(NotificationOutbox).filter(NotificationOutbox.dedupe_key == dedupe).count()
        dup_created = {
            "rows_before": before,
            "rows_after": after,
            "integrity_blocked": integrity_blocked,
            "second_row_created": after > before,
        }

    result = {
        "outbox_id": outbox_id,
        "event_id": event.id if event else None,
        "company_id": row.company_id,
        "kind": row.kind,
        "outcome": outcome,
        "outbox_status": row.status,
        "attempts": row.attempts,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "last_error": row.last_error,
        "auto_news_enabled": False,
        "auto_retry": False,
        "general_news_worker": False,
        "dedupe_reenqueue": dup_created,
        "note": "User must confirm receipt in Telegram chat separately.",
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # Safe print — no token / chat_id
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if outcome == "sent" else 10


if __name__ == "__main__":
    raise SystemExit(main())
