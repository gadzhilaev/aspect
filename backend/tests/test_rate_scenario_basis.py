"""Stage 5.2: key-rate Δ basis — observed / assumed / none (no severity proxy)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Event, Scenario
from app.services.financial_simulator import (
    legacy_rate_basis_from_parameters,
    resolve_observed_rate_change,
    resolve_rate_change_for_scenario,
    simulate_financial_scenarios,
)
from app.services.scenario_display import format_scenario_metric_line


FULL = {
    "debt_amount": 100_000_000,
    "floating_rate_share_percent": 40,
    "near_term_payments_90d": 8_000_000,
    "fx_purchase_volume": 25_000_000,
    "cash_reserve_days": 21,
}


def _event(
    *,
    title: str,
    summary: str = "",
    severity: float | None = 55.0,
    attrs: dict | None = None,
) -> Event:
    return Event(
        id=f"evt_tmp_{uuid4().hex[:8]}",
        title=title,
        summary=summary or "audit",
        category="macro",
        event_type="risk",
        severity=55.0 if severity is None else float(severity),
        urgency_default="watch",
        status="active",
        occurred_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        match_countries_json=[],
        match_categories_json=[],
        match_currencies_json=[],
        match_materials_json=[],
        attributes_json=attrs or {},
        is_demo=True,
    )


def test_hold_high_severity_zero_annual_not_severity_shock():
    ev = _event(
        title="ЦБ сохранил ключевую ставку",
        summary="Регулятор оставил ставку без изменений.",
        severity=90.0,
    )
    fin = simulate_financial_scenarios(event=ev, optional_finance=FULL)
    assert fin["status"] == "ok"
    base = fin["scenarios"][0]
    assert base["rate_change_basis"] == "observed"
    assert base["rate_change_delta_pp"] == 0.0
    assert base["extra_annual_cost"] == 0.0
    assert base["near_term_pressure"] is None
    assert fin["parameters"]["rate_change"]["basis"] == "observed"
    assert fin["parameters"]["severity_used_as_rate_shock"] is False
    assert fin["parameters"]["shock_proxy_pp"] is None


def test_rate_only_hold_omits_fx_reduction_as_personal_plan():
    """RUB credit + hold: no confirmed FX → reduce_fx is hypothesis, not Scenario."""
    ev = _event(
        title="ЦБ сохранил ключевую ставку",
        summary="Регулятор оставил ставку без изменений.",
        severity=70.0,
    )
    rate_only = {
        "debt_amount": 100_000_000,
        "debt_amount_unit": "RUB",
        "floating_rate_share_percent": 40,
    }
    fin = simulate_financial_scenarios(event=ev, optional_finance=rate_only)
    assert fin["status"] == "ok"
    actions = {s.get("action_id") for s in fin["scenarios"]}
    labels = {s.get("label") for s in fin["scenarios"]}
    assert None in actions or "baseline" in {s.get("kind") for s in fin["scenarios"]}
    assert "reduce_fx_exposure" not in actions
    assert "Снизить валютную экспозицию" not in labels
    assert "review_financing" in actions
    omitted = fin["parameters"].get("omitted_action_hypotheses") or []
    assert any(h.get("action_id") == "reduce_fx_exposure" for h in omitted)

    with_fx = {
        **rate_only,
        "fx_exposure_amount": 1000,
        "fx_exposure_currency": "CNY",
        "fx_exposure_direction": "payment",
        "fx_quote_currency": "RUB",
        "fx_quote_convention": "quote_per_exposure",
        "fx_rate_from": 12.0,
    }
    fin_fx = simulate_financial_scenarios(event=ev, optional_finance=with_fx)
    assert any(s.get("action_id") == "reduce_fx_exposure" for s in fin_fx["scenarios"])
    assert not (fin_fx["parameters"].get("omitted_action_hypotheses") or [])


def test_severity_zero_and_none_do_not_invent_shock():
    # severity 0 must not become 50 via falsy `or`
    ev0 = _event(title="Макро-сигнал без решения по ставке", severity=0.0, attrs={})
    r0 = resolve_observed_rate_change(ev0)
    assert r0.basis == "none"
    fin0 = simulate_financial_scenarios(event=ev0, optional_finance=FULL)
    assert fin0["status"] == "unavailable"
    assert fin0["scenarios"] == []

    ev_n = _event(title="Макро-сигнал", severity=0.0, attrs={})
    # Simulate missing severity field semantics: resolve must ignore severity entirely
    assert resolve_rate_change_for_scenario(ev_n).basis == "none"


def test_explicit_what_if_on_hold():
    ev = _event(title="ЦБ сохранил ключевую ставку", severity=80.0)
    fin = simulate_financial_scenarios(
        event=ev, optional_finance=FULL, assumed_rate_change_pp=1.5
    )
    assert fin["status"] == "ok"
    bases = {s["rate_change_basis"] for s in fin["scenarios"]}
    assert "observed" in bases
    assert "assumed" in bases
    assumed_rows = [s for s in fin["scenarios"] if s.get("action_id") == "assumed_rate_shock"]
    assert assumed_rows
    assert assumed_rows[0]["rate_change_delta_pp"] == 1.5
    assert assumed_rows[0]["extra_annual_cost"] == pytest.approx(600_000.0)
    # Observed baseline stays at 0
    assert fin["scenarios"][0]["extra_annual_cost"] == 0.0
    rc = fin["parameters"]["rate_change"]
    assert rc["observed_delta_pp"] == 0.0
    assert rc["assumed_delta_pp"] == 1.5


def test_structured_hike_and_cut():
    hike = _event(
        title="Ключевая ставка повышена",
        attrs={
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
        },
    )
    fin_h = simulate_financial_scenarios(event=hike, optional_finance=FULL)
    assert fin_h["status"] == "ok"
    assert fin_h["scenarios"][0]["rate_change_delta_pp"] == 1.0
    assert fin_h["scenarios"][0]["extra_annual_cost"] == pytest.approx(400_000.0)

    cut = _event(
        title="Ключевая ставка снижена",
        attrs={
            "rate_decision_status": "observed",
            "rate_from": 17.0,
            "rate_to": 16.0,
        },
    )
    fin_c = simulate_financial_scenarios(event=cut, optional_finance=FULL)
    assert fin_c["scenarios"][0]["rate_change_delta_pp"] == -1.0
    assert fin_c["scenarios"][0]["extra_annual_cost"] == pytest.approx(-400_000.0)
    line = format_scenario_metric_line(
        fin_c["scenarios"][0], assessment_state="finance_ready", source="financial_calculation"
    )
    assert line and "снижение" in line.lower()
    assert "доп. годовая нагрузка" not in (line or "").lower()


def test_conflict_from_to_vs_delta():
    ev = _event(
        title="Ставка",
        attrs={
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
            "rate_delta_pp": 2.0,
        },
    )
    r = resolve_observed_rate_change(ev)
    assert r.basis == "conflict"
    fin = simulate_financial_scenarios(event=ev, optional_finance=FULL)
    assert fin["status"] == "unavailable"
    assert fin["scenarios"] == []


def test_forecast_expectation_not_observed():
    ev = _event(
        title="Прогноз: ожидается сохранение ключевой ставки",
        summary="Банк ожидает сохранения паузы до конца года.",
        severity=70.0,
        attrs={"bank_forecast_end_2027": 12.0, "claimed_delta_pp": 0.0},
    )
    r = resolve_observed_rate_change(ev)
    assert r.basis == "none"
    fin = simulate_financial_scenarios(event=ev, optional_finance=FULL)
    assert fin["status"] == "unavailable"


def test_claimed_delta_pp_not_trusted():
    ev = _event(
        title="Макро",
        attrs={"claimed_delta_pp": 2.5, "demo_story": "rate_hike"},
    )
    assert resolve_observed_rate_change(ev).basis == "none"


def test_numbers_without_status_not_observed():
    ev = _event(title="Макро", attrs={"rate_from": 16.0, "rate_to": 18.0})
    assert resolve_observed_rate_change(ev).basis == "none"


def test_unknown_delta_not_zero():
    ev = _event(title="Макросигнал без ставки", severity=55.0)
    fin = simulate_financial_scenarios(event=ev, optional_finance=FULL)
    assert fin["status"] == "unavailable"
    assert fin["scenarios"] == []
    # Must not silently treat as Δ=0 annual
    assert "parameters" in fin
    assert fin["parameters"]["rate_change"]["basis"] == "none"


def test_unknown_floating_share_unavailable():
    # Missing floating share → rate track not opened; no fictitious coerce to 0.
    from app.core.errors import AppError
    from app.services import financial_simulator as fs

    broken = {
        "debt_amount": 100_000_000,
        "near_term_payments_90d": 1,
        "fx_purchase_volume": 1,
        "cash_reserve_days": 1,
    }
    ev = _event(
        title="ЦБ сохранил ключевую ставку",
        attrs={},
    )
    with pytest.raises(AppError) as ei:
        fs.simulate_financial_scenarios(event=ev, optional_finance=broken)
    assert ei.value.code == "INSUFFICIENT_DATA"
    assert any(
        d.get("field") == "floating_rate_share_percent"
        for d in (ei.value.details or [])
        if isinstance(d, dict)
    )


def test_known_zero_debt_and_floating():
    zeros = {
        "debt_amount": 0,
        "floating_rate_share_percent": 0,
        "near_term_payments_90d": 0,
        "fx_purchase_volume": 0,
        "cash_reserve_days": 0,
    }
    ev = _event(
        title="Ключевая ставка",
        attrs={
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
        },
    )
    fin = simulate_financial_scenarios(event=ev, optional_finance=zeros)
    assert fin["status"] == "ok"
    assert fin["scenarios"][0]["extra_annual_cost"] == 0.0


def test_no_automatic_rub_unit_in_display():
    ev = _event(
        title="Ключевая ставка",
        attrs={
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
        },
    )
    fin = simulate_financial_scenarios(event=ev, optional_finance=FULL)
    row = fin["scenarios"][0]
    assert row["debt_amount_unit"] == "unspecified"
    line = format_scenario_metric_line(
        row, assessment_state="finance_ready", source="financial_calculation"
    )
    assert line
    assert "₽" not in line
    assert "единицы введённой суммы долга" in line


def test_no_mixed_fx_in_rate_result():
    ev = _event(
        title="ЦБ сохранил ключевую ставку",
        severity=99.0,
    )
    fin = simulate_financial_scenarios(event=ev, optional_finance=FULL)
    for sc in fin["scenarios"]:
        assert sc.get("near_term_pressure") is None
        assert sc.get("fx_exposure_index") is None
        assert sc.get("near_term_pressure_status") == "unavailable_not_severity_proxy"


def test_scenario_persists_basis(
    client: TestClient, auth_headers: dict, db: Session
):
    from app.models import Company
    from app.services.assistant.tools import compare_scenarios
    from app.services.impact import recompute_company_impact

    company = db.get(Company, "cmp_severprom")
    event = db.get(Event, "evt_rate_hike_001")
    assert company and event
    # Ensure trusted attrs from seed (session may already have them after reseed)
    attrs = dict(event.attributes_json or {})
    attrs.update(
        {
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
        }
    )
    event.attributes_json = attrs
    client.patch(
        "/api/v1/companies/cmp_severprom/finance",
        headers=auth_headers,
        json={"purchase_currencies": ["RUB"], "optional_finance": FULL},
    )
    recompute_company_impact(db, event, company)
    db.commit()

    conv = client.post(
        "/api/v1/events/evt_rate_hike_001/assistant/conversations",
        headers=auth_headers,
        json={"company_id": "cmp_severprom"},
    ).json()
    user_id = client.get("/api/v1/users/me", headers=auth_headers).json()["id"]
    result = compare_scenarios(
        db,
        conversation_id=conv["id"],
        event_id="evt_rate_hike_001",
        company_id="cmp_severprom",
        user_id=user_id,
    )
    db.commit()
    assert result.get("status") == "ok"
    assert result.get("scenarios")
    sc_id = result["scenario_ids"][0]
    row = db.get(Scenario, sc_id)
    assert row is not None
    params = row.parameters_json or {}
    assert "rate_change" in params
    assert params["rate_change"]["basis"] == "observed"
    assert params["rate_change"]["observed_delta_pp"] == 1.0
    assert row.results_json.get("rate_change_basis") == "observed"
    assert "finance-rate-v2" in (row.model_version or "")


def test_legacy_parameters_not_called_observed():
    legacy = legacy_rate_basis_from_parameters({"shock_proxy_pp": 1.375, "debt_amount": 1})
    assert legacy["basis"] == "assumed"
    assert legacy.get("legacy") is True
    assert legacy["observed_delta_pp"] is None

    empty = legacy_rate_basis_from_parameters({})
    assert empty["basis"] == "none"
    assert empty.get("legacy") is True


def test_display_assumed_and_none_framing():
    assumed = {
        "kind": "baseline",
        "label": "What-if",
        "rate_change_basis": "assumed",
        "rate_change_delta_pp": 1.25,
        "annual_rate_sensitivity": 100.0,
        "extra_annual_cost": 100.0,
        "debt_amount_unit": "unspecified",
        "shock_framing": "При допущении изменения ставки на 1.25 п.п.",
    }
    line = format_scenario_metric_line(
        assumed, assessment_state="finance_ready", source="financial_calculation"
    )
    assert line and "Что если ставка изменится на 1.25 п.п." in line
    assert "Допущение сценария" in line

    none_row = {
        "kind": "baseline",
        "label": "Нет данных",
        "rate_change_basis": "none",
    }
    line_n = format_scenario_metric_line(
        none_row, assessment_state="finance_ready", source="financial_calculation"
    )
    assert line_n and (
        "Недостаточно данных" in line_n or "недоступен" in line_n.lower()
    )
