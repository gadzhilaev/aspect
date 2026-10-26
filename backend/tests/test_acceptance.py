"""MVP acceptance tests from TZ §14."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.models import Company, CompanyMembership, NotificationOutbox, NotificationSubscription, User
from app.services.notifications import hash_token, issue_link_token
from app.models.notification import TelegramLinkToken


COMPANY_ID = "cmp_severprom"
EVENT_ID = "evt_china_export_001"


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_verify_login(client: TestClient):
    email = f"user_{uuid4().hex[:8]}@test.app"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password1!", "display_name": "Test"},
    )
    assert r.status_code == 200
    code = r.json()["details"]["demo_code"]
    assert client.post("/api/v1/auth/verify-email", json={"email": email, "code": code}).status_code == 200
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "Password1!"})
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_register_production_stand_uses_demo_email_code(
    client: TestClient, db, monkeypatch
):
    """Stand APP_ENV=production must still store DEMO_EMAIL_CODE (not random OTP)."""
    from app.core.config import get_settings
    from app.models import EmailVerification

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEMO_EMAIL_CODE", "123456")
    monkeypatch.setenv("DEBUG", "true")
    get_settings.cache_clear()

    email = f"prod_stand_{uuid4().hex[:8]}@test.app"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password1!", "display_name": "Stand"},
    )
    assert r.status_code == 200
    assert r.json()["details"]["demo_code"] == "123456"

    row = (
        db.query(EmailVerification)
        .filter(EmailVerification.email == email)
        .order_by(EmailVerification.created_at.desc())
        .first()
    )
    assert row is not None
    assert row.code == "123456"
    assert row.note == "demo_code"
    assert (
        client.post(
            "/api/v1/auth/verify-email",
            json={"email": email, "code": "123456"},
        ).status_code
        == 200
    )
    get_settings.cache_clear()


def test_cannot_read_foreign_company(client: TestClient, auth_headers, db):
    other = Company(id="cmp_other", name="Чужая", is_demo=False, profile_status="draft")
    db.add(other)
    stranger = User(
        id=str(uuid4()),
        email=f"stranger_{uuid4().hex[:6]}@t.app",
        password_hash=hash_password("Password1!"),
        display_name="Stranger",
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(stranger)
    db.add(
        CompanyMembership(
            id=str(uuid4()), user_id=stranger.id, company_id=other.id, role="owner"
        )
    )
    db.commit()

    r = client.get(f"/api/v1/companies/{other.id}/profile", headers=auth_headers)
    assert r.status_code == 403


def test_profile_and_finance_optional(client: TestClient, auth_headers):
    r = client.get(f"/api/v1/companies/{COMPANY_ID}/profile", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["company"]["name"] == "СеверПром"
    assert body["completeness"]["finance_optional"] is True
    assert any(n["name"] == "Shenzhen X" for n in body["nodes"])


def test_impact_path_shenzhen_to_line(client: TestClient, auth_headers):
    r = client.get(
        f"/api/v1/events/{EVENT_ID}/impact",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["exposure"]["value"] == 24
    full = [p for p in data["paths"] if p["sort_order"] == 100][0]
    names = [n["name"] for n in full["path_nodes"]]
    assert "Shenzhen X" in names
    assert "Электронный модуль B" in names or any("модуль" in n.lower() for n in names)
    assert "Линия №2" in names
    claim_types = {p["claim_type"] for p in data["paths"]}
    assert "confirmed_fact" in claim_types
    assert "assumption" in claim_types or "estimate" in claim_types
    assert "impact_score" in data and "confidence" in data
    assert data["score_breakdown"]


def test_simulate_deterministic(client: TestClient, auth_headers):
    payload = {
        "solution_id": "sol_thailand_a",
        "inventory_days": 14,
        "delay_days": 45,
    }
    r1 = client.post(
        f"/api/v1/events/{EVENT_ID}/simulate",
        params={"company_id": COMPANY_ID},
        json=payload,
        headers=auth_headers,
    )
    r2 = client.post(
        f"/api/v1/events/{EVENT_ID}/simulate",
        params={"company_id": COMPANY_ID},
        json=payload,
        headers=auth_headers,
    )
    assert r1.status_code == 200 and r2.status_code == 200
    a, b = r1.json(), r2.json()
    assert a["model_version"] == b["model_version"]
    assert a["baseline"] == b["baseline"]
    assert a["alternative"]["stop_risk_percent"] == b["alternative"]["stop_risk_percent"]
    assert a["is_estimate"] is True


def test_decision_persists(client: TestClient, auth_headers):
    sim = client.post(
        f"/api/v1/events/{EVENT_ID}/simulate",
        params={"company_id": COMPANY_ID},
        json={"solution_id": "sol_thailand_a", "inventory_days": 10, "delay_days": 40},
        headers=auth_headers,
    ).json()
    decision = client.post(
        "/api/v1/decisions",
        json={"scenario_id": sim["scenario_id"], "decision_note": "Берём Таиланд"},
        headers=auth_headers,
    )
    assert decision.status_code == 200
    did = decision.json()["id"]
    got = client.get(f"/api/v1/decisions/{did}", headers=auth_headers)
    assert got.status_code == 200
    assert len(got.json()["action_items"]) >= 3


def test_telegram_dedupe(client: TestClient, auth_headers, db, monkeypatch):
    """Two recomputes → one news outbox under normal TG-4 policy (flag + watermark).

    Seed evt_china_export_001 is demo and is correctly denied; use a fresh non-demo
    risk event with company_calculated Impact after recompute.
    """
    from app.core.config import get_settings
    from app.models import Event, EventImpact
    from app.services.telegram_news_policy import NEWS_KIND, stamp_auto_notify_watermark

    monkeypatch.setenv("TELEGRAM_NEWS_NOTIFICATIONS_ENABLED", "true")
    get_settings.cache_clear()

    now = datetime.now(timezone.utc)
    watermark = now - timedelta(hours=2)
    event_id = f"evt_tg_dedupe_{uuid4().hex[:8]}"
    db.add(
        Event(
            id=event_id,
            title="Ограничения на экспорт электроники из Китая (live)",
            summary="Контроль поставок компонентов",
            category="geopolitics",
            event_type="risk",
            severity=80.0,
            urgency_default="watch",
            status="active",
            occurred_at=now - timedelta(minutes=30),
            match_categories_json=["export_control"],
            match_countries_json=["Китай"],
            match_currencies_json=[],
            match_materials_json=["electronics"],
            attributes_json={},
            is_demo=False,
        )
    )
    sub = NotificationSubscription(
        id=str(uuid4()),
        company_id=COMPANY_ID,
        user_id="usr_demo_owner",
        channel_type="telegram_private",
        chat_id="10001",
        status="connected",
        is_active=True,
        risks_enabled=True,
        min_severity="medium",
        verified_at=now,
    )
    stamp_auto_notify_watermark(sub, when=watermark)
    db.add(sub)
    db.commit()

    r1 = client.post(
        f"/api/v1/events/{event_id}/recompute-impact",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert r1.status_code == 200, r1.text
    impact_body = r1.json()
    assert impact_body.get("impact_score") is not None
    score_after_first = impact_body["impact_score"]

    r2 = client.post(
        f"/api/v1/events/{event_id}/recompute-impact",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json().get("impact_score") == score_after_first

    db.expire_all()
    rows = (
        db.query(NotificationOutbox)
        .filter(
            NotificationOutbox.chat_id == "10001",
            NotificationOutbox.company_id == COMPANY_ID,
            NotificationOutbox.kind == NEWS_KIND,
        )
        .all()
    )
    assert len(rows) == 1
    impact = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event_id, EventImpact.company_id == COMPANY_ID)
        .one()
    )
    assert impact.impact_score == score_after_first
    assert impact.status in {"action_required", "monitor"}


def test_expired_pairing_token(client: TestClient, db):
    raw = "expiredtokenvalue123"
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
    r = client.post(
        "/api/v1/telegram/webhook",
        json={"message": {"chat": {"id": 42, "type": "private"}, "text": f"/start {raw}"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "kontur-webhook-secret"},
    )
    assert r.status_code == 200
    assert "недействительна" in r.json()["text"].lower() or "использована" in r.json()["text"].lower()


def test_works_without_telegram(client: TestClient, auth_headers):
    dash = client.get(f"/api/v1/companies/{COMPANY_ID}/dashboard", headers=auth_headers)
    assert dash.status_code == 200
    assert dash.json()["priority_events"]
    event = client.get(
        f"/api/v1/events/{EVENT_ID}",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert event.status_code == 200
    sols = client.get(
        f"/api/v1/events/{EVENT_ID}/solutions",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert sols.status_code == 200
    assert len(sols.json()) == 3


def test_link_token_flow(client: TestClient, auth_headers, db):
    r = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert r.status_code == 200
    token = r.json()["token"]
    start = client.post(
        "/api/v1/telegram/webhook",
        json={
            "message": {
                "chat": {"id": 777, "type": "private", "username": "boss"},
                "text": f"/start {token}",
            }
        },
        headers={"X-Telegram-Bot-Api-Secret-Token": "kontur-webhook-secret"},
    )
    assert start.status_code == 200
    assert "подключён" in start.json()["text"].lower()
    # reused token fails
    again = client.post(
        "/api/v1/telegram/webhook",
        json={"message": {"chat": {"id": 778, "type": "private"}, "text": f"/start {token}"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "kontur-webhook-secret"},
    )
    assert "недействительна" in again.json()["text"].lower() or "использована" in again.json()["text"].lower()
