"""API-flow smoke — same user journey as the chat UI, via TestClient (not browser E2E)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ActionItem, Decision, Scenario

COMPANY_ID = "cmp_severprom"
EVENT_ID = "evt_china_export_001"


def test_api_flow_open_chat_compare_scenarios(client: TestClient, auth_headers: dict):
    """Open event assistant → ask for three scenarios → see calculation data."""
    conv = client.post(
        f"/api/v1/events/{EVENT_ID}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    )
    assert conv.status_code == 200, conv.text
    conv_id = conv.json()["id"]

    msgs = client.get(f"/api/v1/assistant/conversations/{conv_id}/messages", headers=auth_headers)
    assert msgs.status_code == 200
    assert len(msgs.json()) >= 1

    r = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=auth_headers,
        json={"content": "Покажи три сценария", "client_message_id": "api-flow-compare"},
    )
    assert r.status_code == 200, r.text
    content = r.json()["assistant_message"]["content"].lower()
    for banned in ("simulator", "stop_risk", "risk/cost", "lead time"):
        assert banned not in content, content
    blocks = r.json()["assistant_message"]["blocks"]
    cmp_blocks = [b for b in blocks if b["type"] == "scenario_comparison"]
    assert cmp_blocks
    assert cmp_blocks[0]["data"]["source"] == "calculation"
    scenarios = cmp_blocks[0]["data"]["scenarios"]
    assert len(scenarios) >= 2
    assert any(s.get("kind") == "baseline" for s in scenarios)
    assert any("stop_risk_percent" in str(s) for s in scenarios)


def test_api_flow_draft_confirm_survives_reload(client: TestClient, auth_headers: dict, db: Session):
    """Prepare draft → confirm → reload messages → decision stays confirmed, no second Decision."""
    conv = client.post(
        f"/api/v1/events/{EVENT_ID}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    ).json()
    conv_id = conv["id"]

    from app.services.assistant.tools import compare_scenarios

    before_decisions = db.query(Decision).count()
    before_actions = db.query(ActionItem).count()
    before_scenarios = db.query(Scenario).count()

    user_id = client.get("/api/v1/users/me", headers=auth_headers).json()["id"]
    cmp_result = compare_scenarios(
        db,
        conversation_id=conv_id,
        event_id=EVENT_ID,
        company_id=COMPANY_ID,
        inventory_days=27,
        delay_days=51,
        user_id=user_id,
    )
    db.commit()
    scenarios = [s for s in (cmp_result.get("scenarios") or []) if s.get("scenario_id")]
    assert scenarios
    scenario_id = scenarios[0]["scenario_id"]
    solution_id = scenarios[0].get("solution_id")
    assert db.query(Scenario).count() > before_scenarios
    assert db.query(Scenario).filter(Scenario.id == scenario_id).one_or_none() is not None

    draft = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/draft-decision",
        headers=auth_headers,
        json={
            "scenario_id": scenario_id,
            "solution_id": solution_id,
            "confirm": False,
            "client_request_id": f"api-draft-{scenario_id}",
        },
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "draft"
    assert draft.json()["decision_id"] is None

    confirmed = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/draft-decision",
        headers=auth_headers,
        json={
            "scenario_id": scenario_id,
            "solution_id": solution_id,
            "confirm": True,
            "client_request_id": f"api-confirm-{scenario_id}",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    decision_id = confirmed.json()["decision_id"]
    assert confirmed.json()["status"] == "confirmed"
    assert decision_id
    assert db.query(Decision).count() == before_decisions + 1
    assert db.query(ActionItem).count() == before_actions + 3

    reloaded = client.get(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=auth_headers,
    )
    assert reloaded.status_code == 200
    confirmed_blocks = [
        b
        for m in reloaded.json()
        for b in (m.get("blocks") or [])
        if b.get("type") == "action_plan_draft" and (b.get("data") or {}).get("status") == "confirmed"
    ]
    assert confirmed_blocks
    assert confirmed_blocks[-1]["data"]["decision_id"] == decision_id

    again = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/draft-decision",
        headers=auth_headers,
        json={
            "scenario_id": scenario_id,
            "solution_id": solution_id,
            "confirm": True,
            "client_request_id": f"api-confirm-{scenario_id}",
        },
    )
    assert again.status_code == 200
    assert again.json()["decision_id"] == decision_id
    assert db.query(Decision).count() == before_decisions + 1
    assert db.query(ActionItem).count() == before_actions + 3
