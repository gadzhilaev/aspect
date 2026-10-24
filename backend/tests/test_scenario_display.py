"""Typed scenario display — no None% in finance or supply-chain previews."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Decision, Scenario
from app.services.assistant.orchestrator import _blocks_from_tool_result
from app.services.assistant.tools import compare_scenarios
from app.services.scenario_display import (
    format_scenario_comparison_lines,
    format_scenario_metric_line,
    sanitize_ui_text,
)


COMPANY_ID = "cmp_severprom"
EVENT_RATE = "evt_rate_hike_001"
EVENT_OPP = "evt_market_opp_001"

FULL_FINANCE = {
    "debt_amount": 120_000_000,
    "floating_rate_share_percent": 40,
    "near_term_payments_90d": 18_000_000,
    "fx_purchase_volume": 5_000_000,
    "cash_reserve_days": 45,
}


def test_finance_lines_never_contain_none_percent():
    scenarios = [
        {
            "kind": "baseline",
            "label": "Без действий",
            "funding_pressure_percent": 55.0,
            "extra_annual_cost": 1_200_000,
        },
        {
            "kind": "alternative",
            "label": "Снизить валютную экспозицию",
            "funding_pressure_percent": 40.0,
            "near_term_pressure": 500_000,
        },
        {"kind": "alternative", "label": "Broken finance row"},
    ]
    lines = format_scenario_comparison_lines(
        scenarios, assessment_state="finance_ready", source="financial_calculation"
    )
    blob = "\n".join(lines)
    assert "None" not in blob
    assert "null" not in blob.lower()
    assert "NaN" not in blob
    assert "риск остановки" not in blob
    # Stage 5.3: legacy finance rows use historical presentation, not funding_pressure %
    assert "Историческ" in blob or "чувствительност" in blob or "основание" in blob


def test_supply_chain_lines_keep_stop_risk():
    scenarios = [
        {
            "kind": "baseline",
            "baseline": {"label": "Без действий", "stop_risk_percent": 20.1},
        },
        {
            "kind": "alternative",
            "solution_name": "Поставщик A (Таиланд)",
            "alternative": {"label": "Поставщик A (Таиланд)", "stop_risk_percent": 3.65},
        },
    ]
    lines = format_scenario_comparison_lines(
        scenarios, assessment_state="supply_chain_ready", source="calculation"
    )
    blob = "\n".join(lines)
    assert "модельная оценка риска остановки" in blob or "риск остановки" in blob
    assert "None" not in blob
    assert "3.6%" in blob or "3.65%" in blob or "3.7%" in blob


def test_missing_stop_risk_does_not_emit_none_percent():
    line = format_scenario_metric_line(
        {"kind": "alternative", "label": "Вариант без цифр"},
        assessment_state="supply_chain_ready",
    )
    assert line == "• Вариант без цифр"
    assert "None" not in line


def test_sanitize_ui_text_strips_technical_empties():
    raw = "• Без действий: риск остановки None%"
    clean = sanitize_ui_text(raw)
    assert "None" not in clean
    assert "null%" not in clean.lower()
    assert "undefined" not in clean.lower()
    for banned in ("None%", "null%", "NaN%", "undefined%"):
        assert banned.lower() not in sanitize_ui_text(f"метрика {banned}").lower()


def test_compare_scenarios_finance_has_no_none(
    client: TestClient, auth_headers: dict, db: Session
):
    client.patch(
        f"/api/v1/companies/{COMPANY_ID}/finance",
        headers=auth_headers,
        json={"purchase_currencies": ["RUB", "CNY"], "optional_finance": FULL_FINANCE},
    )
    conv = client.post(
        f"/api/v1/events/{EVENT_RATE}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    ).json()
    user_id = client.get("/api/v1/users/me", headers=auth_headers).json()["id"]
    result = compare_scenarios(
        db,
        conversation_id=conv["id"],
        event_id=EVENT_RATE,
        company_id=COMPANY_ID,
        user_id=user_id,
    )
    db.commit()
    assert result.get("assessment_state") == "finance_ready"
    lines = format_scenario_comparison_lines(
        list(result.get("scenarios") or []),
        assessment_state=result.get("assessment_state"),
        source=result.get("source"),
    )
    blob = "\n".join(lines)
    assert "None%" not in blob
    assert "риск остановки" not in blob
    # Stage 5.2: rate framing / sensitivity — not severity-derived «давление» / ₽
    assert "₽" not in blob
    assert (
        "п.п." in blob
        or "чувствительност" in blob
        or "допущени" in blob.lower()
        or "Факт изменения" in blob
    )
    blocks = _blocks_from_tool_result("compare_scenarios", result)
    assert blocks[0]["data"]["assessment_state"] == "finance_ready"


def _clear_event_decisions(db: Session, event_id: str) -> None:
    sc_ids = [
        row.id
        for row in db.query(Scenario.id)
        .filter(Scenario.company_id == COMPANY_ID, Scenario.event_id == event_id)
        .all()
    ]
    if sc_ids:
        db.query(Decision).filter(Decision.scenario_id.in_(sc_ids)).delete(
            synchronize_session=False
        )
        db.commit()


def test_event_decision_prefers_confirmed(client: TestClient, auth_headers: dict, db: Session):
    user_id = client.get("/api/v1/users/me", headers=auth_headers).json()["id"]
    _clear_event_decisions(db, EVENT_OPP)

    draft_sc = Scenario(
        id=str(uuid4()),
        company_id=COMPANY_ID,
        event_id=EVENT_OPP,
        solution_id=None,
        created_by=user_id,
        parameters_json={"kind": "test_draft"},
        results_json={"label": "Черновик"},
        model_version="test",
        is_estimate=True,
    )
    confirmed_sc = Scenario(
        id=str(uuid4()),
        company_id=COMPANY_ID,
        event_id=EVENT_OPP,
        solution_id=None,
        created_by=user_id,
        parameters_json={"kind": "test_confirmed"},
        results_json={"label": "Подтверждённый план", "funding_pressure_percent": 40},
        model_version="test-finance",
        is_estimate=True,
    )
    db.add(draft_sc)
    db.add(confirmed_sc)
    db.flush()

    confirmed = Decision(
        id=str(uuid4()),
        scenario_id=confirmed_sc.id,
        status="selected",
        decision_note="Подтверждённый план",
        created_by=user_id,
    )
    draft = Decision(
        id=str(uuid4()),
        scenario_id=draft_sc.id,
        status="draft",
        decision_note="Неполный черновик",
        created_by=user_id,
    )
    db.add(confirmed)
    db.add(draft)
    db.commit()

    draft.created_at = datetime.now(timezone.utc) + timedelta(days=1)
    confirmed.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.add(draft)
    db.add(confirmed)
    db.commit()

    got = client.get(
        f"/api/v1/events/{EVENT_OPP}/decision",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["id"] == confirmed.id
    assert body["status"] == "selected"
    assert body["id"] != draft.id


def test_event_decision_404_when_only_draft(client: TestClient, auth_headers: dict, db: Session):
    user_id = client.get("/api/v1/users/me", headers=auth_headers).json()["id"]
    _clear_event_decisions(db, EVENT_OPP)

    sc = Scenario(
        id=str(uuid4()),
        company_id=COMPANY_ID,
        event_id=EVENT_OPP,
        solution_id=None,
        created_by=user_id,
        parameters_json={},
        results_json={"label": "Draft only"},
        model_version="test",
        is_estimate=True,
    )
    db.add(sc)
    db.flush()
    db.add(
        Decision(
            id=str(uuid4()),
            scenario_id=sc.id,
            status="draft",
            decision_note="draft",
            created_by=user_id,
        )
    )
    db.commit()

    got = client.get(
        f"/api/v1/events/{EVENT_OPP}/decision",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert got.status_code == 404
