"""Macro/FX assessment_state + financial scenarios without supply-chain CTA."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Company, Event, EventImpact, EventSource
from app.services.impact import (
    assessment_state_for_impact,
    has_finance_context,
    recompute_company_impact,
    resolve_assessment_state,
)
from app.services.assistant.tools import compare_scenarios

COMPANY_ID = "cmp_severprom"
EVENT_RATE = "evt_rate_hike_001"
EVENT_CHINA = "evt_china_export_001"

FULL_FINANCE = {
    "debt_amount": 100_000_000,
    "floating_rate_share_percent": 40,
    "near_term_payments_90d": 8_000_000,
    "fx_purchase_volume": 25_000_000,
    "cash_reserve_days": 21,
}


def test_resolve_macro_without_finance_is_finance_data_required():
    event = Event(
        id="tmp",
        title="Ключевая ставка повышена",
        summary="s",
        category="macro",
        event_type="risk",
        severity=55,
        urgency_default="this_week",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_countries_json=["Россия"],
        match_categories_json=[],
        match_currencies_json=["RUB"],
        match_materials_json=[],
        attributes_json={},
        is_demo=True,
    )
    assert (
        resolve_assessment_state(
            event, has_supply_path=True, has_exposure=True, optional_finance={}
        )
        == "finance_data_required"
    )
    assert (
        resolve_assessment_state(
            event,
            has_supply_path=False,
            has_exposure=False,
            optional_finance=FULL_FINANCE,
        )
        == "finance_ready"
    )


def test_key_rate_without_finance_blocks_scenario_cta(
    client: TestClient, auth_headers: dict, db: Session
):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_RATE)
    assert company and event

    # Ensure no full finance context
    settings = company.settings
    assert settings is not None
    settings.optional_finance_json = {"demo_loan_note": "stub"}
    db.commit()

    impact = recompute_company_impact(db, event, company)
    db.commit()

    state = assessment_state_for_impact(db, event, impact)
    assert state == "finance_data_required"
    assert impact.exposure_value is None
    paths = (
        db.query(EventImpact)
        .filter(EventImpact.id == impact.id)
        .one()
    )
    assert paths.exposure_value is None

    from app.models import ImpactPath

    assert (
        db.query(ImpactPath).filter(ImpactPath.event_impact_id == impact.id).count() == 0
    )

    api = client.get(
        f"/api/v1/events/{EVENT_RATE}/impact",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert api.status_code == 200, api.text
    body = api.json()
    assert body["assessment_state"] == "finance_data_required"
    assert body["finance_setup_href"] == "/company/setup?step=finance"
    assert body["paths"] == []
    assert "финанс" in body["reason_summary"].lower() or "ставк" in body["reason_summary"].lower()

    conv = client.post(
        f"/api/v1/events/{EVENT_RATE}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    )
    assert conv.status_code == 200, conv.text
    chips = conv.json()["suggestion_chips"]
    assert "Покажи три сценария" not in chips
    assert any("финанс" in c.lower() or "данн" in c.lower() for c in chips)

    msgs = client.get(
        f"/api/v1/assistant/conversations/{conv.json()['id']}/messages",
        headers=auth_headers,
    )
    assert msgs.status_code == 200
    opening = msgs.json()[0]["content"].lower()
    assert "цепочк" not in opening
    assert "финанс" in opening or "долг" in opening


def test_after_finance_financial_scenario_available(
    client: TestClient, auth_headers: dict, db: Session
):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_RATE)
    assert company and event

    patch = client.patch(
        f"/api/v1/companies/{COMPANY_ID}/finance",
        headers=auth_headers,
        json={
            "purchase_currencies": ["RUB", "CNY"],
            "optional_finance": {
                **FULL_FINANCE,
                # Clear typed FX if a prior test merged them (PATCH is merge since 5.5).
                "fx_exposure_amount": None,
                "fx_exposure_currency": None,
                "fx_exposure_direction": None,
                "fx_quote_currency": None,
                "fx_quote_convention": None,
                "fx_rate_from": None,
            },
        },
    )
    assert patch.status_code == 200, patch.text
    assert has_finance_context(FULL_FINANCE)

    impact = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == EVENT_RATE, EventImpact.company_id == COMPANY_ID)
        .one()
    )
    db.refresh(impact)
    assert assessment_state_for_impact(db, event, impact) == "finance_ready"

    user_id = client.get("/api/v1/users/me", headers=auth_headers).json()["id"]
    conv = client.post(
        f"/api/v1/events/{EVENT_RATE}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    ).json()

    # Ensure trusted observed rate attrs (seed 5.2); severity must not invent Δ.
    attrs = dict(event.attributes_json or {})
    attrs.update(
        {
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
        }
    )
    event.attributes_json = attrs
    db.commit()

    result = compare_scenarios(
        db,
        conversation_id=conv["id"],
        event_id=EVENT_RATE,
        company_id=COMPANY_ID,
        user_id=user_id,
    )
    db.commit()
    assert result.get("source") == "financial_calculation"
    assert result.get("status") == "ok"
    scenarios = result.get("scenarios") or []
    # Rate-only profile: baseline + refinance; FX-reduction is not a personal plan.
    assert len(scenarios) >= 2
    labels = {s.get("label") or s.get("solution_name") for s in scenarios}
    assert "Без действий" in labels
    assert not any("валютн" in (l or "").lower() for l in labels)
    assert any("финанс" in (l or "").lower() for l in labels)
    assert all(s.get("action_id") != "reduce_fx_exposure" for s in scenarios)
    omitted = (result.get("parameters") or {}).get("omitted_action_hypotheses") or []
    assert any(h.get("action_id") == "reduce_fx_exposure" for h in omitted)
    assert all("estimate" in (s.get("labels") or ["estimate"]) for s in scenarios)
    assert all(s.get("solution_id") is None for s in scenarios)
    rc = (result.get("parameters") or {}).get("rate_change") or {}
    assert rc.get("basis") == "observed"
    assert rc.get("observed_delta_pp") == 1.0
    assert all(s.get("near_term_pressure") is None for s in scenarios)


def test_china_export_keeps_supply_chain_flow(
    client: TestClient, auth_headers: dict, db: Session
):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_CHINA)
    assert company and event
    impact = recompute_company_impact(db, event, company)
    db.commit()

    assert assessment_state_for_impact(db, event, impact) == "supply_chain_ready"
    assert impact.exposure_value is not None

    api = client.get(
        f"/api/v1/events/{EVENT_CHINA}/impact",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert api.status_code == 200
    body = api.json()
    assert body["assessment_state"] == "supply_chain_ready"
    assert body["paths"]
    assert body["exposure"] is not None

    conv = client.post(
        f"/api/v1/events/{EVENT_CHINA}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    )
    assert conv.status_code == 200
    chips = conv.json()["suggestion_chips"]
    assert "Покажи три сценария" in chips
