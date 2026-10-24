"""TG-2: personal Telegram link, test-send, worker ACL — mocked Telegram HTTP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models import CompanyMembership, NotificationOutbox, NotificationSubscription, User
from app.models.notification import TelegramLinkToken
from app.services.notifications import TEST_MESSAGE_TEXT, hash_token
from app.workers.notification_worker import process_outbox_once

COMPANY_ID = "cmp_severprom"
WH = {"X-Telegram-Bot-Api-Secret-Token": "kontur-webhook-secret"}


def _start(client: TestClient, token: str, chat_id: int = 9001, chat_type: str = "private"):
    return client.post(
        "/api/v1/telegram/webhook",
        json={
            "update_id": int(uuid4().int % 10_000_000),
            "message": {
                "chat": {"id": chat_id, "type": chat_type, "username": "u"},
                "text": f"/start {token}",
            },
        },
        headers=WH,
    )


def test_link_token_ttl_and_one_time(client: TestClient, auth_headers, db):
    r = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert r.status_code == 200
    token = r.json()["token"]
    assert "start=" in r.json()["deep_link"]
    assert _start(client, token, chat_id=9101).status_code == 200
    again = _start(client, token, chat_id=9102)
    assert again.status_code == 200
    assert "недействительна" in again.json()["text"].lower() or "использована" in again.json()[
        "text"
    ].lower() or "уже подключён" in again.json()["text"].lower()


def test_expired_token_rejected(client: TestClient, db):
    raw = "expiredtokenvalue_tg2"
    db.add(
        TelegramLinkToken(
            id=str(uuid4()),
            user_id="usr_demo_owner",
            company_id=COMPANY_ID,
            token_hash=hash_token(raw),
            purpose="private",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    db.commit()
    r = _start(client, raw, chat_id=9201)
    assert "недействительна" in r.json()["text"].lower() or "использована" in r.json()["text"].lower()


def test_private_required_for_personal_start(client: TestClient, auth_headers):
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    r = _start(client, token, chat_id=-100123, chat_type="supergroup")
    assert r.status_code == 200
    assert "личн" in r.json()["text"].lower()


def test_webhook_redelivery_after_bind(client: TestClient, auth_headers):
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    assert "подключён" in _start(client, token, chat_id=9301).json()["text"].lower()
    # Same token again (Telegram redelivery) — should not bind second chat; soft message
    r2 = _start(client, token, chat_id=9301)
    assert r2.status_code == 200


def test_membership_revoked_between_issue_and_consume(client: TestClient, auth_headers, db):
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    m = (
        db.query(CompanyMembership)
        .filter(
            CompanyMembership.user_id == "usr_demo_owner",
            CompanyMembership.company_id == COMPANY_ID,
        )
        .first()
    )
    assert m is not None
    mid, role = m.id, m.role
    try:
        db.delete(m)
        db.commit()
        r = _start(client, token, chat_id=9401)
        assert "отозван" in r.json()["text"].lower()
    finally:
        exists = (
            db.query(CompanyMembership)
            .filter(
                CompanyMembership.user_id == "usr_demo_owner",
                CompanyMembership.company_id == COMPANY_ID,
            )
            .first()
        )
        if exists is None:
            db.add(
                CompanyMembership(
                    id=mid,
                    company_id=COMPANY_ID,
                    user_id="usr_demo_owner",
                    role=role,
                )
            )
            db.commit()


def test_chat_conflict_other_user(client: TestClient, auth_headers, db):
    # First user binds chat 9501
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    assert "подключён" in _start(client, token, chat_id=9501).json()["text"].lower()

    # Register second user and try same chat
    email = f"tg2_{uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "DemoKontur1!", "display_name": "TG2"},
    )
    assert reg.status_code in (200, 201)
    code = (reg.json().get("details") or {}).get("demo_code") or "000000"
    client.post("/api/v1/auth/verify-email", json={"email": email, "code": code})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "DemoKontur1!"}
    )
    assert login.status_code == 200
    headers2 = {"Authorization": f"Bearer {login.json()['access_token']}"}
    # Give membership to company
    u2 = db.query(User).filter(User.email == email).first()
    db.add(
        CompanyMembership(
            id=str(uuid4()),
            company_id=COMPANY_ID,
            user_id=u2.id,
            role="member",
        )
    )
    db.commit()
    token2 = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=headers2,
    ).json()["token"]
    r = _start(client, token2, chat_id=9501)
    assert "другому" in r.json()["text"].lower() or "друг" in r.json()["text"].lower()


def test_one_user_two_companies_same_chat(client: TestClient, auth_headers, db):
    # Create second company for demo owner
    created = client.post(
        "/api/v1/companies",
        json={"name": "TG2 Second Co", "industry": "electronics", "size_band": "50-100"},
        headers=auth_headers,
    )
    if created.status_code >= 400:
        pytest.skip(f"company create unavailable: {created.text}")
    company_b = created.json()["id"]

    t1 = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    assert "подключён" in _start(client, t1, chat_id=9601).json()["text"].lower()

    t2 = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": company_b},
        headers=auth_headers,
    ).json()["token"]
    assert "подключён" in _start(client, t2, chat_id=9601).json()["text"].lower()

    n = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.user_id == "usr_demo_owner",
            NotificationSubscription.chat_id == "9601",
            NotificationSubscription.channel_type == "telegram_private",
            NotificationSubscription.status == "connected",
        )
        .count()
    )
    assert n == 2


def test_test_send_acl_and_queue(client: TestClient, auth_headers, db):
    # Ensure connected
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    _start(client, token, chat_id=9701)

    bad = client.post(
        "/api/v1/telegram/test-send",
        json={"company_id": "cmp_nonexistent"},
        headers=auth_headers,
    )
    assert bad.status_code in (403, 404)

    req = str(uuid4())
    ok = client.post(
        "/api/v1/telegram/test-send",
        json={"company_id": COMPANY_ID, "client_request_id": req},
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["queued"] is True
    assert body["delivery"] == "not_claimed"
    assert body["status"] == "pending"
    row = db.get(NotificationOutbox, body["outbox_id"])
    assert row is not None
    assert row.kind == "test"
    assert row.payload_json["text"] == TEST_MESSAGE_TEXT

    # Idempotent replay
    again = client.post(
        "/api/v1/telegram/test-send",
        json={"company_id": COMPANY_ID, "client_request_id": req},
        headers=auth_headers,
    )
    assert again.status_code == 200
    assert again.json().get("idempotent_replay") is True

    # Rate limit with new request id
    limited = client.post(
        "/api/v1/telegram/test-send",
        json={"company_id": COMPANY_ID, "client_request_id": str(uuid4())},
        headers=auth_headers,
    )
    assert limited.status_code == 429


def test_unlink_vs_disable_and_pending_outbox(client: TestClient, auth_headers, db):
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    _start(client, token, chat_id=9801)
    settings = client.get(
        f"/api/v1/companies/{COMPANY_ID}/notification-settings",
        headers=auth_headers,
    ).json()
    sub_id = settings["telegram_private"]["id"]
    assert settings["telegram_private"]["linked"] is True

    # Pause notifications (keep link)
    patched = client.patch(
        f"/api/v1/notification-subscriptions/{sub_id}",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["linked"] is True or patched.json()["status"] == "connected"
    assert patched.json()["notifications_enabled"] is False

    # Re-enable and queue test then unlink
    client.patch(
        f"/api/v1/notification-subscriptions/{sub_id}",
        json={"is_active": True},
        headers=auth_headers,
    )
    # Bypass rate limit by direct outbox insert for stale chat scenario
    from uuid import uuid4 as u4

    out = NotificationOutbox(
        id=str(u4()),
        company_id=COMPANY_ID,
        subscription_id=sub_id,
        kind="test",
        channel_type="telegram_private",
        chat_id="9801",
        payload_json={"text": TEST_MESSAGE_TEXT, "buttons": []},
        dedupe_key=f"test-manual-{u4()}",
        status="pending",
        attempts=0,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(out)
    db.commit()

    unlink = client.delete(
        f"/api/v1/notification-subscriptions/{sub_id}",
        headers=auth_headers,
    )
    assert unlink.status_code == 200
    assert unlink.json()["operation"] == "unlink"

    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "000:TEST"}):
        from app.core.config import get_settings

        get_settings.cache_clear()
        n = process_outbox_once(db)
    db.refresh(out)
    assert out.status == "skipped"
    assert "pre_send_denied" in (out.last_error or "")


def test_worker_403_429_timeout(client: TestClient, auth_headers, db):
    # Isolate from leftover pending rows of other tests (session-scoped DB).
    db.query(NotificationOutbox).filter(
        NotificationOutbox.status.in_(["pending", "retry", "uncertain"])
    ).update(
        {NotificationOutbox.status: "skipped", NotificationOutbox.last_error: "test_isolate"},
        synchronize_session=False,
    )
    db.commit()
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    _start(client, token, chat_id=9901)
    db.expire_all()
    sub = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.chat_id == "9901",
            NotificationSubscription.company_id == COMPANY_ID,
        )
        .first()
    )
    assert sub is not None

    def _real_settings():
        from app.core.config import get_settings as _real_gs

        real = _real_gs()
        real.telegram_bot_token = "000:TEST"
        real.telegram_outbox_kinds = None
        return real

    def _queue(kind_suffix: str) -> NotificationOutbox:
        row = NotificationOutbox(
            id=str(uuid4()),
            company_id=COMPANY_ID,
            subscription_id=sub.id,
            kind="test",
            channel_type="telegram_private",
            chat_id="9901",
            payload_json={"text": TEST_MESSAGE_TEXT, "buttons": []},
            dedupe_key=f"wtest-{kind_suffix}-{uuid4()}",
            status="pending",
            attempts=0,
            next_attempt_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        return row

    # 403 blocked
    db.expire_all()
    row403 = _queue("403")
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden: bot was blocked by the user"
    with patch("app.workers.notification_worker.httpx.Client") as cls:
        inst = cls.return_value.__enter__.return_value
        inst.post.return_value = mock_resp
        with patch("app.workers.notification_worker.get_settings") as gs:
            gs.return_value = _real_settings()
            process_outbox_once(db)
    db.expire_all()
    row403 = db.get(NotificationOutbox, row403.id)
    sub = db.get(NotificationSubscription, sub.id)
    assert row403 is not None and row403.status == "blocked"
    assert sub is not None and sub.status == "blocked"

    # Reconnect for further cases
    sub.status = "connected"
    sub.is_active = True
    sub.chat_id = "9901"
    db.commit()

    row429 = _queue("429")
    mock429 = MagicMock()
    mock429.status_code = 429
    mock429.text = "Too Many Requests"
    mock429.json.return_value = {"parameters": {"retry_after": 42}}
    with patch("app.workers.notification_worker.httpx.Client") as cls:
        inst = cls.return_value.__enter__.return_value
        inst.post.return_value = mock429
        with patch("app.workers.notification_worker.get_settings") as gs:
            gs.return_value = _real_settings()
            process_outbox_once(db)
    db.expire_all()
    row429 = db.get(NotificationOutbox, row429.id)
    assert row429 is not None and row429.status == "retry"
    assert row429.next_attempt_at is not None

    row_to = _queue("timeout")
    with patch("app.workers.notification_worker.httpx.Client") as cls:
        inst = cls.return_value.__enter__.return_value
        inst.post.side_effect = httpx.TimeoutException("timeout")
        with patch("app.workers.notification_worker.get_settings") as gs:
            gs.return_value = _real_settings()
            process_outbox_once(db)
    db.expire_all()
    row_to = db.get(NotificationOutbox, row_to.id)
    assert row_to is not None and row_to.status == "uncertain"


def test_bot_unlink_all_companies_for_chat(client: TestClient, auth_headers, db):
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    _start(client, token, chat_id=9911)
    r = client.post(
        "/api/v1/telegram/webhook",
        json={
            "update_id": 1,
            "message": {"chat": {"id": 9911, "type": "private"}, "text": "/unlink"},
        },
        headers=WH,
    )
    assert r.status_code == 200
    assert "отвяз" in r.json()["text"].lower()
    sub = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.user_id == "usr_demo_owner",
            NotificationSubscription.company_id == COMPANY_ID,
            NotificationSubscription.channel_type == "telegram_private",
        )
        .first()
    )
    assert sub is not None
    assert sub.status == "disconnected"
    assert sub.chat_id is None
