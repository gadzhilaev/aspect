"""Regression: mobile user preferences / password / delete-account."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Company, CompanyMembership, User
from app.models.notification import NotificationSubscription, TelegramLinkToken


def _register_verified(client: TestClient, *, email: str, password: str, name: str) -> dict:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": name},
    )
    assert r.status_code == 200, r.text
    code = (r.json().get("details") or {}).get("demo_code") or "123456"
    v = client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "code": code},
    )
    assert v.status_code == 200, v.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return login.json()


def test_preferences_partial_patch_keeps_other_keys(client: TestClient):
    tokens = _register_verified(
        client,
        email=f"prefs_{uuid4().hex[:8]}@example.com",
        password="Password1!",
        name="Prefs User",
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    r1 = client.patch(
        "/api/v1/users/me/preferences",
        headers=headers,
        json={"language": "en", "theme_mode": "dark"},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["preferences"]["language"] == "en"
    assert r1.json()["preferences"]["theme_mode"] == "dark"

    r2 = client.patch(
        "/api/v1/users/me/preferences",
        headers=headers,
        json={"language": "ru"},
    )
    assert r2.status_code == 200, r2.text
    prefs = r2.json()["preferences"]
    assert prefs["language"] == "ru"
    assert prefs["theme_mode"] == "dark"

    bad = client.patch(
        "/api/v1/users/me/preferences",
        headers=headers,
        json={"language": "de"},
    )
    assert bad.status_code == 422


def test_change_password_checks_current_and_keeps_me_working_after_relogin(
    client: TestClient,
):
    email = f"pwd_{uuid4().hex[:8]}@example.com"
    tokens = _register_verified(
        client, email=email, password="OldPass123!", name="Pwd User"
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    wrong = client.post(
        "/api/v1/users/me/change-password",
        headers=headers,
        json={"current_password": "wrong", "new_password": "NewPass123!"},
    )
    assert wrong.status_code == 401

    ok = client.post(
        "/api/v1/users/me/change-password",
        headers=headers,
        json={"current_password": "OldPass123!", "new_password": "NewPass123!"},
    )
    assert ok.status_code == 200, ok.text
    assert "token_policy" in (ok.json().get("details") or {})

    # Old password no longer works
    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "OldPass123!"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "NewPass123!"},
    )
    assert new_login.status_code == 200


def test_delete_account_requires_password_and_blocks_sole_owner(
    client: TestClient, auth_headers: dict[str, str]
):
    # Demo owner is sole owner of СеверПром — must refuse.
    missing = client.request(
        "DELETE",
        "/api/v1/users/me",
        headers=auth_headers,
        json={},
    )
    assert missing.status_code == 422

    refuse = client.request(
        "DELETE",
        "/api/v1/users/me",
        headers=auth_headers,
        json={"password": "DemoKontur1!"},
    )
    assert refuse.status_code == 409, refuse.text
    assert refuse.json()["error"]["code"] == "SOLE_OWNER"


def test_delete_account_member_cleans_telegram(client: TestClient):
    tokens = _register_verified(
        client,
        email=f"del_{uuid4().hex[:8]}@example.com",
        password="DeleteMe1!",
        name="Del User",
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = client.get("/api/v1/users/me", headers=headers).json()
    user_id = me["id"]

    db: Session = SessionLocal()
    try:
        company = Company(
            id=f"cmp_{uuid4().hex[:8]}",
            name="Shared Co",
            profile_status="ready",
        )
        owner = User(
            id=f"usr_{uuid4().hex[:8]}",
            email=f"owner_{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("OwnerPass1!"),
            display_name="Other Owner",
            email_verified_at=datetime.now(timezone.utc),
            preferences_json={},
        )
        db.add(owner)
        db.add(company)
        db.flush()
        db.add(
            CompanyMembership(
                id=str(uuid4()),
                user_id=owner.id,
                company_id=company.id,
                role="owner",
            )
        )
        db.add(
            CompanyMembership(
                id=str(uuid4()),
                user_id=user_id,
                company_id=company.id,
                role="member",
            )
        )
        db.add(
            NotificationSubscription(
                id=str(uuid4()),
                company_id=company.id,
                user_id=user_id,
                channel_type="telegram_private",
                chat_id="12345",
                status="connected",
                event_categories_json=[],
            )
        )
        db.add(
            TelegramLinkToken(
                id=str(uuid4()),
                user_id=user_id,
                company_id=company.id,
                token_hash=f"hash_{uuid4().hex}",
                purpose="private",
                expires_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        company_id = company.id
    finally:
        db.close()

    deleted = client.request(
        "DELETE",
        "/api/v1/users/me",
        headers=headers,
        json={"password": "DeleteMe1!"},
    )
    assert deleted.status_code == 200, deleted.text

    gone = client.get("/api/v1/users/me", headers=headers)
    assert gone.status_code == 401

    db = SessionLocal()
    try:
        assert db.get(User, user_id) is None
        assert db.get(Company, company_id) is not None
        assert (
            db.query(NotificationSubscription)
            .filter(NotificationSubscription.user_id == user_id)
            .count()
            == 0
        )
        assert (
            db.query(TelegramLinkToken)
            .filter(TelegramLinkToken.user_id == user_id)
            .count()
            == 0
        )
        assert (
            db.query(CompanyMembership)
            .filter(CompanyMembership.company_id == company_id)
            .count()
            >= 1
        )
    finally:
        db.close()
