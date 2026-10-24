"""TG-3: worker must honour TELEGRAM_OUTBOX_KINDS allowlist before live send."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.models import NotificationOutbox, NotificationSubscription
from app.services.notifications import TEST_MESSAGE_TEXT
from app.workers.notification_worker import process_outbox_once, worker_kind_allowlist
from tests.test_telegram_tg2 import COMPANY_ID, WH, _start


def test_worker_kind_allowlist_parses():
    with patch("app.workers.notification_worker.get_settings") as gs:
        s = gs.return_value
        s.telegram_outbox_kinds = "test"
        assert worker_kind_allowlist(s) == frozenset({"test"})
        s.telegram_outbox_kinds = " test , impact "
        assert worker_kind_allowlist(s) == frozenset({"test", "impact"})
        s.telegram_outbox_kinds = ""
        assert worker_kind_allowlist(s) is None
        s.telegram_outbox_kinds = None
        assert worker_kind_allowlist(s) is None


def test_worker_processes_only_test_kind(client: TestClient, auth_headers, db):
    """With TELEGRAM_OUTBOX_KINDS=test, impact rows stay pending; test rows are attempted."""
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    _start(client, token, chat_id=8801)
    sub = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.chat_id == "8801",
            NotificationSubscription.company_id == COMPANY_ID,
        )
        .first()
    )
    assert sub is not None

    impact = NotificationOutbox(
        id=str(uuid4()),
        company_id=COMPANY_ID,
        subscription_id=sub.id,
        kind="impact",
        channel_type="telegram_private",
        chat_id="8801",
        payload_json={"text": "news-should-not-send", "buttons": []},
        dedupe_key=f"impact-skip-{uuid4()}",
        status="pending",
        attempts=0,
        next_attempt_at=datetime.now(timezone.utc),
    )
    test_row = NotificationOutbox(
        id=str(uuid4()),
        company_id=COMPANY_ID,
        subscription_id=sub.id,
        kind="test",
        channel_type="telegram_private",
        chat_id="8801",
        payload_json={"text": TEST_MESSAGE_TEXT, "buttons": []},
        dedupe_key=f"test-ok-{uuid4()}",
        status="pending",
        attempts=0,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(impact)
    db.add(test_row)
    db.commit()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "ok"
    with patch("app.workers.notification_worker.httpx.Client") as cls:
        inst = cls.return_value.__enter__.return_value
        inst.post.return_value = mock_resp
        with patch("app.workers.notification_worker.get_settings") as gs:
            s = gs.return_value
            s.telegram_bot_token = "000:TEST"
            s.telegram_outbox_kinds = "test"
            n = process_outbox_once(db)

    db.refresh(impact)
    db.refresh(test_row)
    assert n >= 1
    assert impact.status == "pending"
    assert impact.attempts == 0
    assert test_row.status == "sent"
    # Only the test message was posted to Telegram HTTP
    assert inst.post.call_count == 1
    # Session-scoped DB: remove rows so later test-send cooldown checks stay isolated
    db.delete(impact)
    db.delete(test_row)
    db.commit()
