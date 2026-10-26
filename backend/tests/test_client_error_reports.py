"""Public client error reporting endpoint."""

import json

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.client_error_report import ClientErrorReport


def test_client_error_report_accepts_and_persists(client):
    payload = {
        "source": "android",
        "screen": "login",
        "message": "Login failed: HTTP 401",
        "http_status": 401,
        "http_code": "INVALID_CREDENTIALS",
        "url": "https://example.com/api/v1/auth/login",
        "method": "POST",
        "details": {"password": "must-not-store", "extra": "ok"},
        "app_version": "1.0.0",
        "platform": "android",
        "device_info": "sdk 34",
        "email_attempted": "user@example.com",
    }
    resp = client.post("/api/v1/diagnostics/client-error", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] is True
    report_id = data["id"]

    db: Session = SessionLocal()
    try:
        row = db.get(ClientErrorReport, report_id)
        assert row is not None
        assert row.source == "android"
        assert row.screen == "login"
        assert row.email_attempted == "user@example.com"
        details = json.loads(row.details_json or "{}")
        assert details.get("password") == "(redacted)"
        assert details.get("extra") == "ok"
    finally:
        db.close()
