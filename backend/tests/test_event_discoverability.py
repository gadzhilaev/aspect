"""Stage 4.8: discoverability of published events without EventImpact (no live LLM)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import (
    AssistantConversation,
    AssistantMessage,
    Decision,
    Event,
    EventImpact,
    Scenario,
)
from app.main import create_app


def _company_id(client: TestClient, headers: dict[str, str]) -> str:
    me = client.get("/api/v1/users/me", headers=headers).json()
    assert me["companies"], "demo user must have a company"
    return me["companies"][0]["company_id"]


def _add_event(
    db,
    *,
    event_id: str,
    title: str,
    status: str = "active",
    occurred_at: datetime | None = None,
    is_demo: bool = False,
) -> Event:
    event = Event(
        id=event_id,
        title=title,
        summary="Discoverability fixture summary.",
        category="macro",
        event_type="risk",
        severity=40.0,
        status=status,
        occurred_at=occurred_at or datetime(2026, 1, 15, tzinfo=timezone.utc),
        is_demo=is_demo,
        attributes_json={"synthetic_test": True} if "СИНТЕТИЧЕСКИЙ" in title else {},
    )
    db.add(event)
    db.commit()
    return event


def test_public_feed_includes_active_event_without_impact(client: TestClient, db):
    eid = f"evt_disc_pub_{uuid.uuid4().hex[:8]}"
    _add_event(db, event_id=eid, title="Published without impact")

    impacts = db.scalar(
        select(func.count()).select_from(EventImpact).where(EventImpact.event_id == eid)
    )
    assert impacts == 0

    r = client.get("/api/v1/public/news", params={"limit": 50})
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()["items"]}
    assert eid in ids

    detail = client.get(f"/api/v1/public/news/{eid}")
    assert detail.status_code == 200
    assert detail.json()["id"] == eid


def test_unpublished_event_not_in_public_feed(client: TestClient, db):
    eid = f"evt_disc_draft_{uuid.uuid4().hex[:8]}"
    _add_event(db, event_id=eid, title="Draft hidden", status="draft")

    r = client.get("/api/v1/public/news", params={"limit": 50})
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()["items"]}
    assert eid not in ids

    assert client.get(f"/api/v1/public/news/{eid}").status_code == 404


def test_personal_feed_not_polluted_by_no_impact(
    client: TestClient, auth_headers: dict[str, str], db
):
    company_id = _company_id(client, auth_headers)
    eid = f"evt_disc_pers_{uuid.uuid4().hex[:8]}"
    _add_event(db, event_id=eid, title="No impact personal")

    dash = client.get(f"/api/v1/companies/{company_id}/dashboard", headers=auth_headers)
    assert dash.status_code == 200
    priority_ids = {e["id"] for e in dash.json()["priority_events"]}
    assert eid not in priority_ids

    events = client.get(
        f"/api/v1/companies/{company_id}/events",
        headers=auth_headers,
    )
    assert events.status_code == 200
    listed = {e["id"] for e in events.json()["items"]}
    assert eid not in listed

    # Public feed still surfaces the same event (personal ≠ public).
    public_ids = {
        item["id"] for item in client.get("/api/v1/public/news", params={"limit": 50}).json()["items"]
    }
    assert eid in public_ids


def test_conversation_history_without_impact_no_fake_score(
    client: TestClient, auth_headers: dict[str, str], db
):
    company_id = _company_id(client, auth_headers)
    me = client.get("/api/v1/users/me", headers=auth_headers).json()
    user_id = me["id"]

    eid = f"evt_disc_hist_{uuid.uuid4().hex[:8]}"
    _add_event(db, event_id=eid, title="History without impact")

    before_impacts = db.scalar(select(func.count()).select_from(EventImpact))
    before_scenarios = db.scalar(select(func.count()).select_from(Scenario))
    before_decisions = db.scalar(select(func.count()).select_from(Decision))

    open_r = client.post(
        f"/api/v1/events/{eid}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": company_id},
    )
    assert open_r.status_code == 200, open_r.text
    conv_id = open_r.json()["id"]

    # Seed a historical assistant message without calling the model.
    db.add(
        AssistantMessage(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role="assistant",
            content="Исторический ответ без новой генерации.",
            blocks_json=[],
        )
    )
    db.commit()

    listed = client.get(
        f"/api/v1/assistant/conversations?company_id={company_id}",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    row = next(i for i in listed.json() if i["id"] == conv_id)
    assert row["event_id"] == eid
    assert row["impact_score"] is None
    assert row["has_impact_calculation"] is False
    assert row["assessment_state"] == "calculation_unavailable"
    assert row["status"] != "decision_ready"

    msgs = client.get(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=auth_headers,
    )
    assert msgs.status_code == 200
    assert any("Исторический ответ" in m["content"] for m in msgs.json())

    assert db.scalar(select(func.count()).select_from(EventImpact)) == before_impacts
    assert db.scalar(select(func.count()).select_from(Scenario)) == before_scenarios
    assert db.scalar(select(func.count()).select_from(Decision)) == before_decisions
    # conversation exists for user
    assert db.get(AssistantConversation, conv_id).user_id == user_id


def test_agent_demo_entry_gated(
    client: TestClient, auth_headers: dict[str, str], db, monkeypatch: pytest.MonkeyPatch
):
    assert client.get("/api/v1/agent-demo/entry", headers=auth_headers).status_code == 404

    eid = f"evt_synth_disc_{uuid.uuid4().hex[:8]}"
    _add_event(
        db,
        event_id=eid,
        title="[СИНТЕТИЧЕСКИЙ ТЕСТ 4.8] discoverability",
        is_demo=True,
    )
    company_id = _company_id(client, auth_headers)
    open_r = client.post(
        f"/api/v1/events/{eid}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": company_id},
    )
    assert open_r.status_code == 200
    conv_id = open_r.json()["id"]

    monkeypatch.setenv("AGENT_DEMO_STAND", "true")
    monkeypatch.setenv("AGENT_DEMO_EVENT_ID", eid)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as demo_client:
        login = demo_client.post(
            "/api/v1/auth/login",
            json={"email": "demo@kontur.app", "password": "DemoKontur1!"},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        r = demo_client.get("/api/v1/agent-demo/entry", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["event_id"] == eid
        assert body["news_path"] == f"/news/{eid}"
        assert body["assistant_path"] == f"/events/{eid}/assistant"
        assert body["conversation_id"] == conv_id
        assert body["scenarios_path"].startswith("/scenarios")
        assert "синтетич" in body["synthetic_notice"].lower()
        assert "ранее полученный" in body["prior_answer_notice"].lower()

    monkeypatch.delenv("AGENT_DEMO_STAND", raising=False)
    monkeypatch.delenv("AGENT_DEMO_EVENT_ID", raising=False)
    get_settings.cache_clear()


def test_agent_demo_entry_disabled_by_default(client: TestClient, auth_headers: dict[str, str]):
    get_settings.cache_clear()
    assert get_settings().agent_demo_stand is False
    assert client.get("/api/v1/agent-demo/entry", headers=auth_headers).status_code == 404
