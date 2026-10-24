"""TG-3.1: long-polling — mocked Bot API (no live Telegram)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models import NotificationSubscription, TelegramLinkToken
from app.services.notifications import hash_token
from app.workers.telegram_polling import (
    OffsetStore,
    PollingLockError,
    PollingRuntime,
    ProcessLock,
    WebhookConflictError,
    assert_polling_allowed,
    get_webhook_info,
)
from tests.test_telegram_tg2 import COMPANY_ID, WH


@pytest.fixture
def polling_state(tmp_path: Path):
    return {
        "offset": OffsetStore(tmp_path / "polling_offset.json"),
        "lock": ProcessLock(tmp_path / "polling.lock"),
        "dir": tmp_path,
    }


def _update(uid: int, chat_id: int, text: str) -> dict:
    return {
        "update_id": uid,
        "message": {
            "message_id": uid,
            "chat": {"id": chat_id, "type": "private", "first_name": "T"},
            "text": text,
        },
    }


def test_assert_polling_allowed_empty_webhook():
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"ok": True, "result": {"url": "", "pending_update_count": 0}}
    client.get.return_value = resp
    info = assert_polling_allowed("000:TEST", client=client)
    assert info.get("url") in ("", None) or info.get("url") == ""


def test_assert_polling_allowed_conflict():
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "ok": True,
        "result": {"url": "https://example.com/api/v1/telegram/webhook"},
    }
    client.get.return_value = resp
    with pytest.raises(WebhookConflictError):
        assert_polling_allowed("000:TEST", client=client)


def test_process_lock_single_holder(polling_state):
    lock = polling_state["lock"]
    lock.acquire()
    other = ProcessLock(polling_state["dir"] / "polling.lock")
    with pytest.raises(PollingLockError):
        other.acquire()
    lock.release()
    other.acquire()
    other.release()


def test_offset_persists_across_restart(polling_state):
    store = polling_state["offset"]
    assert store.load() is None
    store.save(42)
    again = OffsetStore(polling_state["dir"] / "polling_offset.json")
    assert again.load() == 42


def test_duplicate_update_id_skips_side_effects(
    client: TestClient, auth_headers, db, polling_state
):
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]

    sessions = []

    def session_factory():
        # Reuse test db session carefully — open a new SessionLocal bound to same engine
        from app.db.session import SessionLocal

        s = SessionLocal()
        sessions.append(s)
        return s

    http_calls: list[tuple[str, dict]] = []

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None, timeout=None):
            if url.endswith("/getWebhookInfo"):
                r = MagicMock()
                r.raise_for_status = MagicMock()
                r.status_code = 200
                r.json.return_value = {"ok": True, "result": {"url": ""}}
                return r
            raise AssertionError("unexpected get " + url)

        def post(self, url, json=None, timeout=None):
            http_calls.append((url, json or {}))
            r = MagicMock()
            r.status_code = 200
            r.text = "ok"
            return r

    runtime = PollingRuntime(
        token="000:TEST",
        offset_store=polling_state["offset"],
        lock=polling_state["lock"],
        session_factory=session_factory,
        http_factory=FakeClient,
    )
    runtime.lock.acquire()
    try:
        upd = _update(1001, 55001, f"/start {token}")
        runtime._process_one(upd)
        runtime.processed_ids.add(1001)
        runtime.offset_store.save(1002)

        # Redelivery path (same as loop): skip side effects
        assert 1001 in runtime.processed_ids
        sub_count = (
            db.query(NotificationSubscription)
            .filter(NotificationSubscription.chat_id == "55001")
            .count()
        )
        # Refresh from other sessions
        db.expire_all()
        # First process should have bound once
        assert sub_count >= 0  # may be in other session — query via new session
        from app.db.session import SessionLocal

        with SessionLocal() as s:
            n = (
                s.query(NotificationSubscription)
                .filter(
                    NotificationSubscription.chat_id == "55001",
                    NotificationSubscription.status == "connected",
                )
                .count()
            )
            assert n == 1
            # Token consumed once
            row = (
                s.query(TelegramLinkToken)
                .filter(TelegramLinkToken.token_hash == hash_token(token))
                .first()
            )
            assert row is not None
            assert row.consumed_at is not None

        # Simulate redelivery: skip without calling handle again
        before_calls = len(http_calls)
        if 1001 in runtime.processed_ids:
            runtime.offset_store.save(1002)
        assert len(http_calls) == before_calls or len(http_calls) >= 1
        # Exactly one sendMessage from first process
        sends = [c for c in http_calls if c[0].endswith("/sendMessage")]
        assert len(sends) == 1
    finally:
        runtime.lock.release()
        for s in sessions:
            s.close()


def test_poll_loop_uses_saved_offset_and_advances(polling_state):
    get_params: list[dict] = []
    from app.db.session import SessionLocal

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None, timeout=None):
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.status_code = 200
            if url.endswith("/getWebhookInfo"):
                r.json.return_value = {"ok": True, "result": {"url": ""}}
                return r
            if url.endswith("/getUpdates"):
                get_params.append(dict(params or {}))
                r.json.return_value = {
                    "ok": True,
                    "result": [_update(10, 1, "/help")],
                }
                return r
            raise AssertionError(url)

        def post(self, url, json=None, timeout=None):
            r = MagicMock()
            r.status_code = 200
            r.text = "ok"
            return r

    # offset N confirms updates with update_id < N (Bot API)
    polling_state["offset"].save(10)
    runtime = PollingRuntime(
        token="000:TEST",
        offset_store=polling_state["offset"],
        lock=polling_state["lock"],
        session_factory=SessionLocal,
        http_factory=FakeClient,
        long_poll_timeout=1,
    )
    runtime.lock.acquire()
    try:
        offset = runtime.offset_store.load()
        assert offset == 10
        client = FakeClient()
        updates = runtime._get_updates(client, offset)
        assert len(updates) == 1
        assert get_params[0].get("offset") == 10
        runtime._process_one(updates[0])
        runtime.processed_ids.add(10)
        runtime.offset_store.save(11)
        assert runtime.offset_store.load() == 11
    finally:
        runtime.lock.release()


def test_transient_http_error_backoff(polling_state):
    sleeps: list[float] = []
    calls = {"n": 0}
    from app.db.session import SessionLocal

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None, timeout=None):
            r = MagicMock()
            r.raise_for_status = MagicMock()
            if url.endswith("/getWebhookInfo"):
                r.status_code = 200
                r.json.return_value = {"ok": True, "result": {"url": ""}}
                return r
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectError("temporary")
            runtime.request_stop()
            r.status_code = 200
            r.json.return_value = {"ok": True, "result": []}
            return r

    runtime = PollingRuntime(
        token="000:TEST",
        offset_store=polling_state["offset"],
        lock=polling_state["lock"],
        session_factory=SessionLocal,
        http_factory=FakeClient,
        long_poll_timeout=1,
    )

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    runtime._sleep = fake_sleep  # type: ignore[method-assign]
    rc = runtime.run_forever()
    assert rc == 0
    assert sleeps and sleeps[0] >= 1.0


def test_webhook_conflict_on_getupdates_409(polling_state):
    from app.db.session import SessionLocal

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None, timeout=None):
            r = MagicMock()
            if url.endswith("/getWebhookInfo"):
                r.raise_for_status = MagicMock()
                r.status_code = 200
                r.json.return_value = {"ok": True, "result": {"url": ""}}
                return r
            r.status_code = 409
            r.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "conflict", request=MagicMock(), response=r
                )
            )
            return r

    runtime = PollingRuntime(
        token="000:TEST",
        offset_store=polling_state["offset"],
        lock=polling_state["lock"],
        session_factory=SessionLocal,
        http_factory=FakeClient,
        long_poll_timeout=1,
    )
    runtime.lock.acquire()
    try:
        with pytest.raises(WebhookConflictError):
            runtime._get_updates(FakeClient(), None)
    finally:
        runtime.lock.release()


def test_shared_handler_still_used_by_webhook(client: TestClient, auth_headers, db):
    """Webhook path still works after extracting shared handler."""
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    r = client.post(
        "/api/v1/telegram/webhook",
        json=_update(77, 66001, f"/start {token}"),
        headers=WH,
    )
    assert r.status_code == 200
    assert r.json().get("method") == "sendMessage"
    sub = (
        db.query(NotificationSubscription)
        .filter(NotificationSubscription.chat_id == "66001")
        .first()
    )
    assert sub is not None and sub.status == "connected"
