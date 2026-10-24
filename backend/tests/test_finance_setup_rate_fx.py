"""Stage 5.5: finance setup gates, PATCH merge/clear, rate/FX track readiness."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Company, CompanyProfileSettings, Event
from app.services.finance_validation import merge_optional_finance, validate_optional_finance_fx
from app.services.financial_simulator import simulate_financial_scenarios
from app.services.impact import (
    assessment_state_for_impact,
    has_finance_context,
    has_fx_finance_context,
    has_rate_finance_context,
    recompute_company_impact,
    resolve_assessment_state,
)

COMPANY_ID = "cmp_severprom"
EVENT_RATE = "evt_rate_hike_001"

FX_ONLY = {
    "fx_exposure_amount": 1000,
    "fx_exposure_currency": "CNY",
    "fx_exposure_direction": "payment",
    "fx_quote_currency": "RUB",
    "fx_quote_convention": "quote_per_exposure",
    "fx_rate_from": 12,
}

RATE_ONLY = {
    "debt_amount": 100_000_000,
    "debt_amount_unit": "RUB",
    "floating_rate_share_percent": 40,
}

CLEAR_FX = {
    "fx_exposure_amount": None,
    "fx_exposure_currency": None,
    "fx_exposure_direction": None,
    "fx_quote_currency": None,
    "fx_quote_convention": None,
    "fx_rate_from": None,
    "fx_rate_to": None,
    "fx_exposure_period": None,
}


def _macro_event(**attrs) -> Event:
    return Event(
        id=f"tmp_{uuid4().hex[:8]}",
        title="Курс CNY",
        summary="s",
        category="macro",
        event_type="risk",
        severity=55,
        urgency_default="watch",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_countries_json=[],
        match_categories_json=[],
        match_currencies_json=["CNY"],
        match_materials_json=[],
        attributes_json=attrs,
        is_demo=True,
    )


def test_gates_rate_and_fx_independent():
    assert not has_finance_context({})
    assert has_rate_finance_context(RATE_ONLY)
    assert not has_fx_finance_context(RATE_ONLY)
    assert has_finance_context(RATE_ONLY)

    assert has_fx_finance_context(FX_ONLY)
    assert not has_rate_finance_context(FX_ONLY)
    assert has_finance_context(FX_ONLY)

    assert has_rate_finance_context(
        {"debt_amount": 0, "floating_rate_share_percent": 0}
    )


def test_assessment_fx_only_is_finance_ready():
    event = _macro_event()
    assert (
        resolve_assessment_state(
            event, has_supply_path=False, has_exposure=False, optional_finance=FX_ONLY
        )
        == "finance_ready"
    )
    assert (
        resolve_assessment_state(
            event, has_supply_path=False, has_exposure=False, optional_finance=RATE_ONLY
        )
        == "finance_ready"
    )


def test_merge_preserves_untouched_and_clear_vs_zero():
    existing = {
        "debt_amount": 10,
        "floating_rate_share_percent": 40,
        "cash_reserve_days": 21,
        "fx_purchase_volume": 5,
    }
    merged = merge_optional_finance(
        existing,
        {"debt_amount": 0, "cash_reserve_days": None},
    )
    assert merged["debt_amount"] == 0
    assert "cash_reserve_days" not in merged
    assert merged["floating_rate_share_percent"] == 40
    assert merged["fx_purchase_volume"] == 5

    cleared = merge_optional_finance(merged, {"debt_amount": ""})
    assert "debt_amount" not in cleared


def test_validate_rejects_bad_percent_and_rate():
    with pytest.raises(AppError):
        validate_optional_finance_fx({**RATE_ONLY, "floating_rate_share_percent": 150})
    with pytest.raises(AppError):
        validate_optional_finance_fx({**FX_ONLY, "fx_rate_from": -1})


def test_patch_merge_via_api(client: TestClient, auth_headers: dict, db: Session):
    company = db.get(Company, COMPANY_ID)
    assert company and company.settings
    company.settings.optional_finance_json = {
        "debt_amount": 50,
        "floating_rate_share_percent": 10,
        "cash_reserve_days": 30,
    }
    db.commit()

    r = client.patch(
        f"/api/v1/companies/{COMPANY_ID}/finance",
        headers=auth_headers,
        json={
            "purchase_currencies": ["CNY"],
            "optional_finance": {
                "debt_amount": 0,
                "cash_reserve_days": None,
                "fx_exposure_amount": 1000,
                "fx_exposure_currency": "CNY",
                "fx_exposure_direction": "payment",
                "fx_quote_currency": "RUB",
            },
        },
    )
    assert r.status_code == 200, r.text
    db.refresh(company.settings)
    fin = company.settings.optional_finance_json
    assert fin["debt_amount"] == 0
    assert fin["floating_rate_share_percent"] == 10
    assert "cash_reserve_days" not in fin
    assert fin["fx_exposure_amount"] == 1000.0
    assert has_fx_finance_context(fin)


def test_fx_only_profile_reaches_simulator_with_basis(
    client: TestClient, auth_headers: dict, db: Session
):
    """Ordinary API: PATCH FX-only → finance_ready → simulator FX track (no debt)."""
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_RATE)
    assert company and event
    prev_fin = dict(company.settings.optional_finance_json or {})
    prev_attrs = dict(event.attributes_json or {})

    try:
        # Replace profile with FX-only (clear rate keys explicitly)
        r = client.patch(
            f"/api/v1/companies/{COMPANY_ID}/finance",
            headers=auth_headers,
            json={
                "purchase_currencies": ["CNY"],
                "optional_finance": {
                    **FX_ONLY,
                    "debt_amount": None,
                    "floating_rate_share_percent": None,
                    "debt_amount_unit": None,
                    "debt_currency": None,
                    **{k: None for k in ("near_term_payments_90d", "fx_purchase_volume", "cash_reserve_days")},
                },
            },
        )
        assert r.status_code == 200, r.text
        db.refresh(company.settings)
        fin = company.settings.optional_finance_json
        assert has_fx_finance_context(fin)
        assert not has_rate_finance_context(fin)

        impact = recompute_company_impact(db, event, company)
        db.commit()
        assert assessment_state_for_impact(db, event, impact) == "finance_ready"

        # Event basis for FX
        ev = _macro_event(
            fx_rate_decision={
                "status": "observed",
                "exposure_currency": "CNY",
                "quote_currency": "RUB",
                "quote_convention": "quote_per_exposure",
                "rate_from": 12,
                "rate_to": 13,
            }
        )
        pkg = simulate_financial_scenarios(event=ev, optional_finance=fin)
        assert pkg["status"] == "ok"
        assert pkg.get("fx_status") == "ok"
        assert any(s.get("track") == "fx" for s in pkg["scenarios"])
        assert not any(s.get("track") == "rate" for s in pkg["scenarios"])
        assert any(s.get("fx_value_change") == "1000.00" for s in pkg["scenarios"])
    finally:
        company.settings.optional_finance_json = prev_fin
        event.attributes_json = prev_attrs
        db.commit()


def test_rate_only_no_fake_fx_required(
    client: TestClient, auth_headers: dict, db: Session
):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_RATE)
    assert company and event
    prev_fin = dict(company.settings.optional_finance_json or {})
    prev_attrs = dict(event.attributes_json or {})

    try:
        r = client.patch(
            f"/api/v1/companies/{COMPANY_ID}/finance",
            headers=auth_headers,
            json={
                "purchase_currencies": ["RUB"],
                "optional_finance": {**RATE_ONLY, **CLEAR_FX},
            },
        )
        assert r.status_code == 200, r.text
        db.refresh(company.settings)
        fin = company.settings.optional_finance_json
        assert has_rate_finance_context(fin)
        assert not has_fx_finance_context(fin)

        impact = recompute_company_impact(db, event, company)
        db.commit()
        assert assessment_state_for_impact(db, event, impact) == "finance_ready"

        ev = _macro_event()
        ev.title = "ЦБ сохранил ключевую ставку"
        ev.attributes_json = {
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
        }
        pkg = simulate_financial_scenarios(event=ev, optional_finance=fin)
        assert pkg["status"] == "ok"
        assert any(s.get("track") == "rate" for s in pkg["scenarios"])
        assert not any(s.get("track") == "fx" for s in pkg["scenarios"])
    finally:
        company.settings.optional_finance_json = prev_fin
        event.attributes_json = prev_attrs
        db.commit()


def test_ready_profile_without_event_basis_unavailable_money():
    ev = _macro_event()  # no trusted rate/fx decision
    ev.title = "Макро-сигнал без решения"
    pkg = simulate_financial_scenarios(event=ev, optional_finance=RATE_ONLY)
    assert pkg["status"] == "unavailable"
    assert not (pkg.get("scenarios") or [])


def test_finance_acl_other_company(client: TestClient, auth_headers: dict, db: Session):
    other = Company(
        id=f"cmp_acl_{uuid4().hex[:6]}",
        name="Other",
        profile_status="draft",
        digital_twin_status="not_built",
        digital_twin_coverage=0.0,
        is_demo=False,
    )
    db.add(other)
    db.add(
        CompanyProfileSettings(
            id=str(uuid4()),
            company_id=other.id,
            optional_finance_json={},
            purchase_currencies_json=[],
        )
    )
    db.commit()
    r = client.patch(
        f"/api/v1/companies/{other.id}/finance",
        headers=auth_headers,
        json={"purchase_currencies": [], "optional_finance": RATE_ONLY},
    )
    assert r.status_code in {403, 404}
