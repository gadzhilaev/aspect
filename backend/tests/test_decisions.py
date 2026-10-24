"""Decision detail + action-item ACL / status updates."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.models import Company, CompanyMembership, User


COMPANY_ID = "cmp_severprom"
EVENT_ID = "evt_china_export_001"


def _create_decision(client: TestClient, auth_headers: dict) -> dict:
    # Unique simulate params → unique Scenario (one Decision per scenario).
    nonce = uuid4().int % 50
    sim = client.post(
        f"/api/v1/events/{EVENT_ID}/simulate",
        params={"company_id": COMPANY_ID},
        json={
            "solution_id": "sol_thailand_a",
            "inventory_days": 10 + nonce,
            "delay_days": 40 + (nonce % 7),
        },
        headers=auth_headers,
    )
    assert sim.status_code == 200, sim.text
    decision = client.post(
        "/api/v1/decisions",
        json={"scenario_id": sim.json()["scenario_id"], "decision_note": "Снижаем риск линии"},
        headers=auth_headers,
    )
    assert decision.status_code == 200, decision.text
    return decision.json()


def test_get_decision_enriched_shape(client: TestClient, auth_headers):
    created = _create_decision(client, auth_headers)
    got = client.get(f"/api/v1/decisions/{created['id']}", headers=auth_headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status_label"] == "Решение принято"
    assert body["progress"]["total"] >= 3
    assert body["progress"]["done"] == 0
    assert "из" in body["progress"]["label"]
    assert body["event"]["title"]
    assert body["event"]["category_label"]
    assert body["scenario"]["reason"]
    assert body["news_href"].startswith("/news/")
    assert len(body["action_items"]) >= 3
    assert body["action_items"][0]["status_label"] == "Запланировано"
    assert "snake_case" not in str(body).lower()


def test_get_decision_for_event(client: TestClient, auth_headers):
    created = _create_decision(client, auth_headers)
    by_id = client.get(f"/api/v1/decisions/{created['id']}", headers=auth_headers)
    assert by_id.status_code == 200, by_id.text

    got = client.get(
        f"/api/v1/events/{EVENT_ID}/decision",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["event"]["id"] == EVENT_ID
    assert body["status_label"] == "Решение принято"
    assert len(body["action_items"]) >= 1
    # Event lookup returns a confirmed decision for this company/event
    # (latest among possibly several scenarios from prior tests).
    assert body["id"]


def test_patch_action_item_updates_progress(client: TestClient, auth_headers):
    created = _create_decision(client, auth_headers)
    item_id = created["action_items"][0]["id"]
    patched = client.patch(
        f"/api/v1/action-items/{item_id}",
        json={"status": "done"},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["status"] == "done"
    assert body["status_label"] == "Выполнено"
    assert body["progress"]["done"] == 1
    assert body["progress"]["total"] == created["progress"]["total"]

    detail = client.get(f"/api/v1/decisions/{created['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["progress"]["done"] == 1
    assert detail.json()["action_items"][0]["status"] == "done"


def test_action_item_acl_foreign_user_forbidden(client: TestClient, auth_headers, db):
    created = _create_decision(client, auth_headers)
    item_id = created["action_items"][0]["id"]

    email = f"outsider_{uuid4().hex[:8]}@test.app"
    user = User(
        id=str(uuid4()),
        email=email,
        password_hash=hash_password("Password1!"),
        display_name="Outsider",
        email_verified_at=datetime.now(timezone.utc),
    )
    other = Company(id=f"cmp_{uuid4().hex[:8]}", name="Чужая", is_demo=False, profile_status="draft")
    db.add(user)
    db.add(other)
    db.flush()
    db.add(
        CompanyMembership(
            id=str(uuid4()),
            user_id=user.id,
            company_id=other.id,
            role="owner",
        )
    )
    db.commit()

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "Password1!"})
    assert login.status_code == 200, login.text
    foreign = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied_get = client.get(f"/api/v1/decisions/{created['id']}", headers=foreign)
    assert denied_get.status_code == 403

    denied_patch = client.patch(
        f"/api/v1/action-items/{item_id}",
        json={"status": "done"},
        headers=foreign,
    )
    assert denied_patch.status_code == 403

    still = client.get(f"/api/v1/decisions/{created['id']}", headers=auth_headers)
    assert still.status_code == 200
    assert still.json()["progress"]["done"] == 0


def test_decision_not_found(client: TestClient, auth_headers):
    r = client.get(f"/api/v1/decisions/{uuid4()}", headers=auth_headers)
    assert r.status_code == 404


def test_cancel_active_decision(client: TestClient, auth_headers):
    created = _create_decision(client, auth_headers)
    decision_id = created["id"]
    item_id = created["action_items"][0]["id"]

    cancelled = client.post(
        f"/api/v1/decisions/{decision_id}/cancel",
        json={"reason": "Выбрали другой вариант"},
        headers=auth_headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["status_label"] == "План отменён"
    assert body["cancel_reason"] == "Выбрали другой вариант"
    assert body["cancelled_at"]
    assert body["actions_locked"] is True
    # Decision row kept — action items still listed
    assert len(body["action_items"]) >= 3

    # Event lookup must not return cancelled as active plan
    by_event = client.get(
        f"/api/v1/events/{EVENT_ID}/decision",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    if by_event.status_code == 200:
        assert by_event.json()["id"] != decision_id
        assert by_event.json()["status"] != "cancelled"
    else:
        assert by_event.status_code == 404

    # Action items frozen
    denied_patch = client.patch(
        f"/api/v1/action-items/{item_id}",
        json={"status": "done"},
        headers=auth_headers,
    )
    assert denied_patch.status_code == 409


def test_cancel_decision_idempotent(client: TestClient, auth_headers):
    created = _create_decision(client, auth_headers)
    decision_id = created["id"]

    first = client.post(
        f"/api/v1/decisions/{decision_id}/cancel",
        json={"reason": "Первая отмена"},
        headers=auth_headers,
    )
    assert first.status_code == 200, first.text
    first_at = first.json()["cancelled_at"]

    second = client.post(
        f"/api/v1/decisions/{decision_id}/cancel",
        json={"reason": "Повтор не должен переписать"},
        headers=auth_headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "cancelled"
    assert second.json()["cancel_reason"] == "Первая отмена"
    assert second.json()["cancelled_at"] == first_at


def test_cancel_decision_acl_foreign_user_forbidden(client: TestClient, auth_headers, db):
    created = _create_decision(client, auth_headers)
    decision_id = created["id"]

    email = f"cancel_out_{uuid4().hex[:8]}@test.app"
    user = User(
        id=str(uuid4()),
        email=email,
        password_hash=hash_password("Password1!"),
        display_name="Outsider",
        email_verified_at=datetime.now(timezone.utc),
    )
    other = Company(id=f"cmp_{uuid4().hex[:8]}", name="Чужая", is_demo=False, profile_status="draft")
    db.add(user)
    db.add(other)
    db.flush()
    db.add(
        CompanyMembership(
            id=str(uuid4()),
            user_id=user.id,
            company_id=other.id,
            role="owner",
        )
    )
    db.commit()

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "Password1!"})
    assert login.status_code == 200, login.text
    foreign = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied = client.post(
        f"/api/v1/decisions/{decision_id}/cancel",
        json={"reason": "чужой"},
        headers=foreign,
    )
    assert denied.status_code == 403

    still = client.get(f"/api/v1/decisions/{decision_id}", headers=auth_headers)
    assert still.status_code == 200
    assert still.json()["status"] != "cancelled"


def test_event_decision_excludes_cancelled_prefers_newer_active(
    client: TestClient, auth_headers
):
    older = _create_decision(client, auth_headers)
    cancel = client.post(
        f"/api/v1/decisions/{older['id']}/cancel",
        json={},
        headers=auth_headers,
    )
    assert cancel.status_code == 200, cancel.text

    newer = _create_decision(client, auth_headers)
    by_event = client.get(
        f"/api/v1/events/{EVENT_ID}/decision",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert by_event.status_code == 200, by_event.text
    assert by_event.json()["id"] == newer["id"]
    assert by_event.json()["status"] != "cancelled"
    assert by_event.json()["status_label"] == "Решение принято"
