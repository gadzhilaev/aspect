"""Company business-context endpoint — real twin data + ACL."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Company, User

COMPANY_ID = "cmp_severprom"


def test_company_context_for_member(client: TestClient, auth_headers: dict):
    resp = client.get(f"/api/v1/companies/{COMPANY_ID}/context", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["company_name"] == "СеверПром"
    assert body["profile_ready"] is True
    assert body["status_label"] == "Контекст настроен"
    assert body["setup_cta_label"] == "Изменить контекст"
    assert body["industry_label"]
    assert "draft" not in body["status_label"].lower()
    assert body["coverage_total"] >= 1
    assert body["coverage_filled"] <= body["coverage_total"]
    assert isinstance(body["tracking"], list)
    assert any(t["title"] for t in body["tracking"])
    # Additive case block (slot not configured in default test env)
    assert "case_context" in body
    assert body["case_context"]["status"] == "integration_not_configured"
    assert body["case_context"]["profile"] is None
    # No technical empties / snake display fields in human strings
    blob = str(body)
    for banned in ("None%", "null%", "undefined", "profile_status", "digital_twin"):
        assert banned not in blob
    # Map groups only for existing data
    assert body["map_groups"]
    keys = {g["key"] for g in body["map_groups"]}
    assert "supplies" in keys or "production" in keys
    # Example uses a real impact when present
    example = body.get("example") or {}
    if example.get("available"):
        assert example["event_id"]
        assert example["public_title"]
        assert example["impact_score"] is not None
        assert "None" not in str(example["public_title"])


def test_company_context_acl_forbidden(client: TestClient, db: Session):
    outsider = User(
        id=str(uuid4()),
        email=f"outsider_{uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Outsider1!"),
        display_name="Outsider",
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(outsider)
    db.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": outsider.email, "password": "Outsider1!"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.get(f"/api/v1/companies/{COMPANY_ID}/context", headers=headers)
    assert resp.status_code == 403


def test_company_context_requires_auth(client: TestClient):
    resp = client.get(f"/api/v1/companies/{COMPANY_ID}/context")
    assert resp.status_code in (401, 403)


def test_company_context_draft_status(client: TestClient, auth_headers: dict, db: Session):
    company = db.get(Company, COMPANY_ID)
    assert company is not None
    previous = company.profile_status
    company.profile_status = "draft"
    db.add(company)
    db.commit()
    try:
        resp = client.get(f"/api/v1/companies/{COMPANY_ID}/context", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["profile_ready"] is False
        assert body["status_label"] == "Нужно завершить настройку"
        assert body["setup_cta_label"] == "Продолжить настройку"
    finally:
        company.profile_status = previous
        db.add(company)
        db.commit()
