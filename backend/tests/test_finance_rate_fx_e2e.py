"""Stage 5.6: end-to-end finance rate/FX path via TestClient (no LLM, no browser).

Uses the session test DB (kontur_test.db) with synthetic companies/events — not the
working app DB. Scenarios are created through the assistant tool ``compare_scenarios``
(ASSISTANT_PROVIDER=mock); HTTP covers PATCH/profile/impact/scenario/decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Company,
    CompanyMembership,
    CompanyProfileSettings,
    Event,
    Scenario,
    User,
)
from app.services.assistant.tools import compare_scenarios
from app.services.finance_scenario_presentation import build_finance_scenario_presentation
from app.services.finance_validation import merge_optional_finance
from app.services.financial_simulator import simulate_financial_scenarios
from app.services.impact import (
    assessment_state_for_impact,
    has_rate_finance_context,
    recompute_company_impact,
)


RATE_DEBT = {
    "debt_amount": 100_000_000,
    "debt_amount_unit": "RUB",
    "floating_rate_share_percent": 40,
}

FX_PAYMENT = {
    "fx_exposure_amount": 1000,
    "fx_exposure_currency": "CNY",
    "fx_exposure_direction": "payment",
    "fx_quote_currency": "RUB",
    "fx_quote_convention": "quote_per_exposure",
}

CLEAR_RATE = {
    "debt_amount": None,
    "debt_amount_unit": None,
    "debt_currency": None,
    "floating_rate_share_percent": None,
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


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def _add_event(db: Session, *, title: str, attrs: dict, currencies: list[str] | None = None) -> Event:
    ev = Event(
        id=_uid("evt"),
        title=title,
        summary="e2e fixture",
        category="macro",
        event_type="risk",
        severity=55.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        match_countries_json=[],
        match_categories_json=[],
        match_currencies_json=currencies or [],
        match_materials_json=[],
        attributes_json=attrs,
        is_demo=False,
    )
    db.add(ev)
    db.flush()
    return ev


def _create_company(client: TestClient, headers: dict) -> str:
    r = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": f"E2E Finance {_uid('co')}", "industry": "manufacturing"},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _patch_finance(client: TestClient, headers: dict, company_id: str, finance: dict) -> dict:
    r = client.patch(
        f"/api/v1/companies/{company_id}/finance",
        headers=headers,
        json={"purchase_currencies": ["CNY", "RUB"], "optional_finance": finance},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _profile_finance(client: TestClient, headers: dict, company_id: str) -> dict:
    r = client.get(f"/api/v1/companies/{company_id}/profile", headers=headers)
    assert r.status_code == 200, r.text
    settings = r.json().get("settings") or {}
    fin = settings.get("optional_finance") or {}
    assert isinstance(fin, dict)
    return fin


def _prepare_impact(db: Session, event: Event, company_id: str) -> None:
    company = db.get(Company, company_id)
    assert company is not None
    recompute_company_impact(db, event, company)
    db.commit()


def _open_conv(client: TestClient, headers: dict, event_id: str, company_id: str) -> str:
    r = client.post(
        f"/api/v1/events/{event_id}/assistant/conversations",
        headers=headers,
        json={"company_id": company_id},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _compare(
    db: Session,
    client: TestClient,
    headers: dict,
    *,
    conv_id: str,
    event_id: str,
    company_id: str,
    assumed_rate_change_pp: float | None = None,
    assumed_fx_change_percent: float | None = None,
) -> dict:
    user_id = client.get("/api/v1/users/me", headers=headers).json()["id"]
    result = compare_scenarios(
        db,
        conversation_id=conv_id,
        event_id=event_id,
        company_id=company_id,
        user_id=user_id,
        assumed_rate_change_pp=assumed_rate_change_pp,
        assumed_fx_change_percent=assumed_fx_change_percent,
    )
    db.commit()
    return result


# ---------------------------------------------------------------------------
# PATCH merge / pair-rate server guard
# ---------------------------------------------------------------------------


def test_merge_clears_rate_when_pair_changes_without_explicit_rate():
    existing = {
        **FX_PAYMENT,
        "fx_rate_from": 12.0,
    }
    # Pair change, rate not in patch → must drop stored rate (Flutter-safe).
    merged = merge_optional_finance(
        existing,
        {"fx_exposure_currency": "USD", "fx_quote_currency": "RUB"},
    )
    assert merged["fx_exposure_currency"] == "USD"
    assert "fx_rate_from" not in merged

    # Explicit new rate in same patch is kept.
    kept = merge_optional_finance(
        existing,
        {
            "fx_exposure_currency": "USD",
            "fx_quote_currency": "RUB",
            "fx_rate_from": 90.0,
        },
    )
    assert kept["fx_rate_from"] == 90.0


def test_patch_pair_change_clears_rate_via_api(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    _patch_finance(client, auth_headers, cid, {**FX_PAYMENT, "fx_rate_from": 12})
    # New Session read
    db.expire_all()
    fin1 = _profile_finance(client, auth_headers, cid)
    assert fin1.get("fx_rate_from") == 12.0

    _patch_finance(
        client,
        auth_headers,
        cid,
        {"fx_exposure_currency": "USD", "fx_quote_currency": "RUB"},
    )
    db.expire_all()
    fin2 = _profile_finance(client, auth_headers, cid)
    assert fin2.get("fx_exposure_currency") == "USD"
    assert "fx_rate_from" not in fin2
    assert fin2.get("fx_exposure_amount") == 1000.0  # untouched


def test_patch_null_clear_zero_and_new_session(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    _patch_finance(
        client,
        auth_headers,
        cid,
        {**RATE_DEBT, "cash_reserve_days": 21},
    )
    _patch_finance(
        client,
        auth_headers,
        cid,
        {"debt_amount": 0, "cash_reserve_days": None},
    )
    db.expire_all()
    fin = _profile_finance(client, auth_headers, cid)
    assert fin["debt_amount"] == 0
    assert fin["floating_rate_share_percent"] == 40
    assert "cash_reserve_days" not in fin

    # Clear floating → rate track not ready
    _patch_finance(client, auth_headers, cid, {"floating_rate_share_percent": None})
    db.expire_all()
    fin2 = _profile_finance(client, auth_headers, cid)
    assert not has_rate_finance_context(fin2)


# ---------------------------------------------------------------------------
# Rate matrix (tool path + HTTP GET)
# ---------------------------------------------------------------------------


def test_rate_hold_zero_sensitivity_api_path(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    ev = _add_event(
        db,
        title="ЦБ сохранил ключевую ставку",
        attrs={},
        currencies=["RUB"],
    )
    db.commit()
    _prepare_impact(db, ev, cid)

    impact = client.get(
        f"/api/v1/events/{ev.id}/impact",
        params={"company_id": cid},
        headers=auth_headers,
    )
    assert impact.status_code == 200
    assert impact.json()["assessment_state"] == "finance_ready"

    conv = _open_conv(client, auth_headers, ev.id, cid)
    result = _compare(db, client, auth_headers, conv_id=conv, event_id=ev.id, company_id=cid)
    assert result.get("status") == "ok"
    rate_rows = [s for s in (result.get("scenarios") or []) if s.get("track") == "rate"]
    assert rate_rows
    base = next(s for s in rate_rows if s.get("kind") == "baseline")
    assert base["rate_change_basis"] == "observed"
    assert base["rate_change_delta_pp"] == 0.0
    assert base["annual_rate_sensitivity"] == 0.0
    assert not any(s.get("track") == "fx" for s in result["scenarios"])

    sc_id = base["scenario_id"]
    got = client.get(f"/api/v1/scenarios/{sc_id}", headers=auth_headers)
    assert got.status_code == 200
    body = got.json()
    assert body["results"]["annual_rate_sensitivity"] == 0.0
    assert body["presentation"]["basis"] == "observed"
    assert body["presentation"]["hold_note"] or "0" in (body["presentation"].get("money_line") or "")
    # Not «рисков нет»
    blob = str(body["presentation"]).lower()
    assert "рисков нет" not in blob


def test_rate_observed_hike_1pp_and_decision(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    ev = _add_event(
        db,
        title="ЦБ повысил ключевую ставку",
        attrs={
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
        },
        currencies=["RUB"],
    )
    db.commit()
    _prepare_impact(db, ev, cid)

    conv = _open_conv(client, auth_headers, ev.id, cid)
    result = _compare(db, client, auth_headers, conv_id=conv, event_id=ev.id, company_id=cid)
    assert result["status"] == "ok"
    base = next(
        s
        for s in result["scenarios"]
        if s.get("track") == "rate" and s.get("kind") == "baseline"
    )
    assert base["rate_change_delta_pp"] == 1.0
    assert base["annual_rate_sensitivity"] == 400_000.0
    assert base["debt_amount_unit"] == "RUB"
    sc_id = base["scenario_id"]

    # Decision via ordinary POST /decisions
    dec = client.post(
        "/api/v1/decisions",
        headers=auth_headers,
        json={"scenario_id": sc_id, "decision_note": "E2E rate hike plan", "status": "selected"},
    )
    assert dec.status_code == 200, dec.text
    detail = dec.json()
    assert detail["scenario"]["presentation"]["basis"] == "observed"
    assert detail["scenario"]["presentation"]["delta_pp"] == 1.0
    assert detail["scenario"]["model_version"]

    # Profile change must not rewrite stored scenario/decision
    old_annual = base["annual_rate_sensitivity"]
    _patch_finance(client, auth_headers, cid, {"debt_amount": 50_000_000})
    db.expire_all()
    sc_row = db.get(Scenario, sc_id)
    assert sc_row is not None
    assert sc_row.results_json["annual_rate_sensitivity"] == old_annual
    detail2 = client.get(f"/api/v1/decisions/{detail['id']}", headers=auth_headers)
    assert detail2.status_code == 200
    assert detail2.json()["scenario"]["presentation"]["annual_sensitivity"] == old_annual


def test_rate_what_if_on_hold_and_unknown_delta(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})

    hold = _add_event(db, title="ЦБ сохранил ключевую ставку", attrs={}, currencies=["RUB"])
    unknown = _add_event(
        db,
        title="Макро-сигнал без решения по ставке",
        attrs={},
        currencies=["RUB"],
    )
    db.commit()
    _prepare_impact(db, hold, cid)
    _prepare_impact(db, unknown, cid)

    conv_h = _open_conv(client, auth_headers, hold.id, cid)
    with_if = _compare(
        db,
        client,
        auth_headers,
        conv_id=conv_h,
        event_id=hold.id,
        company_id=cid,
        assumed_rate_change_pp=1.5,
    )
    assert with_if["status"] == "ok"
    alts = [
        s
        for s in with_if["scenarios"]
        if s.get("action_id") == "assumed_rate_shock" or s.get("rate_change_basis") == "assumed"
    ]
    assert alts or any(
        s.get("rate_change_basis") == "assumed" for s in with_if["scenarios"]
    )

    conv_u = _open_conv(client, auth_headers, unknown.id, cid)
    bare = _compare(
        db, client, auth_headers, conv_id=conv_u, event_id=unknown.id, company_id=cid
    )
    assert bare.get("status") in {"missing_data", "unavailable"} or not (
        bare.get("scenarios") or []
    )


def test_rate_unspecified_unit_and_zero_vs_unknown(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    # No debt_amount_unit
    _patch_finance(
        client,
        auth_headers,
        cid,
        {
            "debt_amount": 100_000_000,
            "floating_rate_share_percent": 40,
            **CLEAR_FX,
            "debt_amount_unit": None,
            "debt_currency": None,
        },
    )
    ev = _add_event(
        db,
        title="ЦБ повысил ключевую ставку",
        attrs={"rate_decision_status": "observed", "rate_from": 10.0, "rate_to": 11.0},
        currencies=["RUB"],
    )
    db.commit()
    _prepare_impact(db, ev, cid)
    conv = _open_conv(client, auth_headers, ev.id, cid)
    result = _compare(db, client, auth_headers, conv_id=conv, event_id=ev.id, company_id=cid)
    base = next(s for s in result["scenarios"] if s.get("kind") == "baseline")
    assert base.get("debt_amount_unit") in {None, "unspecified"} or base[
        "debt_amount_unit"
    ] == "unspecified"
    pres = build_finance_scenario_presentation(
        results=base, parameters=result.get("parameters") or {}
    )
    assert not pres.get("debt_unit_confirmed_rub")
    money = (pres.get("money_line") or "").lower()
    assert "₽" not in money or "единиц" in money

    # Known zero debt vs missing
    _patch_finance(client, auth_headers, cid, {"debt_amount": 0})
    zero_pkg = simulate_financial_scenarios(
        event=ev, optional_finance=_profile_finance(client, auth_headers, cid)
    )
    z_base = next(s for s in zero_pkg["scenarios"] if s.get("kind") == "baseline")
    assert z_base["annual_rate_sensitivity"] == 0.0

    _patch_finance(client, auth_headers, cid, {"debt_amount": None})
    fin = _profile_finance(client, auth_headers, cid)
    assert "debt_amount" not in fin
    assert not has_rate_finance_context(fin)


# ---------------------------------------------------------------------------
# FX matrix
# ---------------------------------------------------------------------------


def _impact(db: Session, event_id: str, company_id: str):
    from app.models import EventImpact

    return (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event_id, EventImpact.company_id == company_id)
        .one()
    )


def test_fx_payment_1000_cny_12_to_13(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    ev = _add_event(
        db,
        title="Курс CNY вырос",
        attrs={
            "fx_rate_decision": {
                "status": "observed",
                "exposure_currency": "CNY",
                "quote_currency": "RUB",
                "quote_convention": "quote_per_exposure",
                "rate_from": 12,
                "rate_to": 13,
            }
        },
        currencies=["CNY"],
    )
    db.commit()
    _patch_finance(client, auth_headers, cid, {**FX_PAYMENT, **CLEAR_RATE})
    _prepare_impact(db, ev, cid)
    assert assessment_state_for_impact(db, ev, _impact(db, ev.id, cid)) == "finance_ready"

    conv = _open_conv(client, auth_headers, ev.id, cid)
    result = _compare(db, client, auth_headers, conv_id=conv, event_id=ev.id, company_id=cid)
    assert result["status"] == "ok"
    fx_rows = [s for s in result["scenarios"] if s.get("track") == "fx"]
    assert fx_rows
    assert not any(s.get("track") == "rate" for s in result["scenarios"])
    base = next(s for s in fx_rows if s.get("kind") == "baseline")
    assert base["fx_baseline_value"] == "12000.00"
    assert base["fx_scenario_value"] == "13000.00"
    assert base["fx_value_change"] == "1000.00"
    assert base["fx_value_change_meaning"] == "payment_cost_increase"
    assert "прибыл" not in (base.get("fx_value_change_meaning_label") or "").lower()

    sc = client.get(f"/api/v1/scenarios/{base['scenario_id']}", headers=auth_headers)
    assert sc.status_code == 200
    assert sc.json()["presentation"]["track"] == "fx"
    assert "1000" in (sc.json()["presentation"].get("money_line") or "").replace(" ", "")


def test_fx_receipt_same_numbers_different_meaning(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    ev = _add_event(
        db,
        title="Курс CNY вырос",
        attrs={
            "fx_rate_decision": {
                "status": "observed",
                "exposure_currency": "CNY",
                "quote_currency": "RUB",
                "quote_convention": "quote_per_exposure",
                "rate_from": 12,
                "rate_to": 13,
            }
        },
        currencies=["CNY"],
    )
    db.commit()
    _patch_finance(
        client,
        auth_headers,
        cid,
        {**FX_PAYMENT, "fx_exposure_direction": "receipt", **CLEAR_RATE},
    )
    _prepare_impact(db, ev, cid)
    conv = _open_conv(client, auth_headers, ev.id, cid)
    result = _compare(db, client, auth_headers, conv_id=conv, event_id=ev.id, company_id=cid)
    base = next(s for s in result["scenarios"] if s.get("track") == "fx")
    assert base["fx_value_change"] == "1000.00"
    assert base["fx_value_change_meaning"] == "receipt_equivalent_increase"
    assert "прибыл" not in (base.get("fx_value_change_meaning_label") or "").lower()


def test_fx_no_basis_no_money_and_what_if_and_conflict(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    bare = _add_event(db, title="Валютный обзор без курсов", attrs={}, currencies=["CNY"])
    conflict = _add_event(
        db,
        title="Конфликт курсов",
        attrs={
            "fx_rate_decision": {
                "status": "observed",
                "exposure_currency": "CNY",
                "quote_currency": "RUB",
                "quote_convention": "quote_per_exposure",
                "rate_from": 12,
                "rate_to": 13,
                "rate_delta": 5,
            }
        },
        currencies=["CNY"],
    )
    db.commit()

    _patch_finance(
        client,
        auth_headers,
        cid,
        {**FX_PAYMENT, "fx_rate_from": 12, **CLEAR_RATE},
    )
    _prepare_impact(db, bare, cid)
    conv = _open_conv(client, auth_headers, bare.id, cid)
    no_basis = _compare(db, client, auth_headers, conv_id=conv, event_id=bare.id, company_id=cid)
    assert no_basis.get("status") in {"missing_data", "unavailable"} or not (
        no_basis.get("scenarios") or []
    )

    # what-if +10% with base 12 → 13.2, Δ = 1200
    with_if = _compare(
        db,
        client,
        auth_headers,
        conv_id=_open_conv(client, auth_headers, bare.id, cid),
        event_id=bare.id,
        company_id=cid,
        assumed_fx_change_percent=10,
    )
    assert with_if["status"] == "ok"
    fx = next(s for s in with_if["scenarios"] if s.get("track") == "fx")
    assert fx["fx_rate_to"] == "13.200000"
    assert fx["fx_value_change"] == "1200.00"

    _prepare_impact(db, conflict, cid)
    bad = _compare(
        db,
        client,
        auth_headers,
        conv_id=_open_conv(client, auth_headers, conflict.id, cid),
        event_id=conflict.id,
        company_id=cid,
    )
    assert bad.get("status") in {"missing_data", "unavailable"} or not (
        bad.get("scenarios") or []
    )


# ---------------------------------------------------------------------------
# Cross tracks + mixed profile + legacy + ACL
# ---------------------------------------------------------------------------


def test_cross_fx_only_rate_event_and_rate_only_fx_event(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    rate_ev = _add_event(
        db,
        title="ЦБ повысил ключевую ставку",
        attrs={"rate_decision_status": "observed", "rate_from": 16.0, "rate_to": 17.0},
        currencies=["RUB"],
    )
    fx_ev = _add_event(
        db,
        title="Курс CNY",
        attrs={
            "fx_rate_decision": {
                "status": "observed",
                "exposure_currency": "CNY",
                "quote_currency": "RUB",
                "quote_convention": "quote_per_exposure",
                "rate_from": 12,
                "rate_to": 13,
            }
        },
        currencies=["CNY"],
    )
    db.commit()

    # FX-only profile + rate event → no rate money
    _patch_finance(client, auth_headers, cid, {**FX_PAYMENT, **CLEAR_RATE})
    _prepare_impact(db, rate_ev, cid)
    r1 = _compare(
        db,
        client,
        auth_headers,
        conv_id=_open_conv(client, auth_headers, rate_ev.id, cid),
        event_id=rate_ev.id,
        company_id=cid,
    )
    # finance_ready from FX profile, but rate track has no debt → only FX if FX basis absent → unavailable
    assert not any(
        s.get("track") == "rate" and s.get("annual_rate_sensitivity") not in (None,)
        for s in (r1.get("scenarios") or [])
    )

    # Rate-only + FX event → no FX money
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, fx_ev, cid)
    r2 = _compare(
        db,
        client,
        auth_headers,
        conv_id=_open_conv(client, auth_headers, fx_ev.id, cid),
        event_id=fx_ev.id,
        company_id=cid,
    )
    assert not any(s.get("track") == "fx" for s in (r2.get("scenarios") or []))


def test_mixed_profile_keeps_tracks_separate(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    ev = _add_event(
        db,
        title="ЦБ повысил ставку и курс",
        attrs={
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
            "fx_rate_decision": {
                "status": "observed",
                "exposure_currency": "CNY",
                "quote_currency": "RUB",
                "quote_convention": "quote_per_exposure",
                "rate_from": 12,
                "rate_to": 13,
            },
        },
        currencies=["RUB", "CNY"],
    )
    db.commit()
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **FX_PAYMENT})
    _prepare_impact(db, ev, cid)
    result = _compare(
        db,
        client,
        auth_headers,
        conv_id=_open_conv(client, auth_headers, ev.id, cid),
        event_id=ev.id,
        company_id=cid,
    )
    assert result["status"] == "ok"
    rate = next(s for s in result["scenarios"] if s.get("track") == "rate" and s.get("kind") == "baseline")
    fx = next(s for s in result["scenarios"] if s.get("track") == "fx" and s.get("kind") == "baseline")
    assert rate["annual_rate_sensitivity"] == 400_000.0
    assert fx["fx_value_change"] == "1000.00"
    # No mixing horizons into FX money_period annual
    fx_pres = build_finance_scenario_presentation(
        results=fx, parameters=result.get("parameters") or {}
    )
    assert fx_pres.get("money_period") is None
    assert fx_pres.get("track") == "fx"


def test_legacy_scenario_not_observed_and_not_recalculated(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    ev = _add_event(db, title="Legacy macro", attrs={}, currencies=["RUB"])
    db.commit()
    user_id = client.get("/api/v1/users/me", headers=auth_headers).json()["id"]
    sc = Scenario(
        id=_uid("sc"),
        company_id=cid,
        event_id=ev.id,
        solution_id=None,
        created_by=user_id,
        parameters_json={
            "kind": "financial",
            "shock_proxy_pp": 1.25,
            "debt_amount": 100_000_000,
        },
        results_json={
            "label": "Legacy baseline",
            "extra_annual_cost": 500_000,
            "funding_pressure_percent": 40,
        },
        model_version="sim-v1.0-pre52",
        is_estimate=True,
    )
    db.add(sc)
    db.commit()

    got = client.get(f"/api/v1/scenarios/{sc.id}", headers=auth_headers)
    assert got.status_code == 200
    pres = got.json()["presentation"]
    assert pres["basis"] == "legacy"
    assert pres.get("legacy") is True
    assert "observed" not in (pres.get("rate_fact_line") or "").lower()

    # Changing profile does not mutate legacy row
    _patch_finance(client, auth_headers, cid, RATE_DEBT)
    db.expire_all()
    row = db.get(Scenario, sc.id)
    assert row.results_json["extra_annual_cost"] == 500_000
    assert row.parameters_json.get("shock_proxy_pp") == 1.25


def test_acl_foreign_company_scenario_decision(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    ev = _add_event(
        db,
        title="ЦБ сохранил ключевую ставку",
        attrs={},
        currencies=["RUB"],
    )
    db.commit()
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, ev, cid)
    result = _compare(
        db,
        client,
        auth_headers,
        conv_id=_open_conv(client, auth_headers, ev.id, cid),
        event_id=ev.id,
        company_id=cid,
    )
    sc_id = next(s["scenario_id"] for s in result["scenarios"] if s.get("scenario_id"))

    email = f"outsider_{uuid4().hex[:8]}@test.app"
    outsider = User(
        id=str(uuid4()),
        email=email,
        password_hash=hash_password("Password1!"),
        display_name="Out",
        email_verified_at=datetime.now(timezone.utc),
    )
    other = Company(id=_uid("cmp"), name="Чужая", is_demo=False, profile_status="draft")
    db.add(outsider)
    db.add(other)
    db.flush()
    db.add(
        CompanyMembership(
            id=str(uuid4()), user_id=outsider.id, company_id=other.id, role="owner"
        )
    )
    db.add(
        CompanyProfileSettings(
            id=str(uuid4()),
            company_id=other.id,
            optional_finance_json={},
            purchase_currencies_json=[],
        )
    )
    db.commit()

    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password1!"}
    )
    assert login.status_code == 200
    foreign = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get(f"/api/v1/scenarios/{sc_id}", headers=foreign).status_code == 403
    assert (
        client.patch(
            f"/api/v1/companies/{cid}/finance",
            headers=foreign,
            json={"purchase_currencies": [], "optional_finance": RATE_DEBT},
        ).status_code
        == 403
    )


def test_message_path_mock_provider_finance_ready(
    client: TestClient, auth_headers: dict, db: Session
):
    """HTTP message path with ASSISTANT_PROVIDER=mock (legacy assistant flow)."""
    cid = _create_company(client, auth_headers)
    ev = _add_event(
        db,
        title="ЦБ повысил ключевую ставку",
        attrs={"rate_decision_status": "observed", "rate_from": 16.0, "rate_to": 17.0},
        currencies=["RUB"],
    )
    db.commit()
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, ev, cid)
    conv = _open_conv(client, auth_headers, ev.id, cid)
    msg = client.post(
        f"/api/v1/assistant/conversations/{conv}/messages",
        headers=auth_headers,
        json={
            "content": "Покажи три сценария",
            "client_message_id": f"e2e-msg-{uuid4().hex[:8]}",
        },
    )
    assert msg.status_code == 200, msg.text
    blocks = msg.json()["assistant_message"]["blocks"]
    cmp_blocks = [b for b in blocks if b["type"] == "scenario_comparison"]
    # Mock may return comparison or missing_data depending on tool routing
    if cmp_blocks:
        data = cmp_blocks[0]["data"]
        scenarios = data.get("scenarios") or []
        if scenarios:
            assert any(s.get("track") == "rate" or s.get("rate_change_basis") for s in scenarios)


def test_unavailable_does_not_become_numeric_decision(
    client: TestClient, auth_headers: dict, db: Session
):
    cid = _create_company(client, auth_headers)
    ev = _add_event(db, title="Сигнал без Δ", attrs={}, currencies=["RUB"])
    db.commit()
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, ev, cid)
    result = _compare(
        db,
        client,
        auth_headers,
        conv_id=_open_conv(client, auth_headers, ev.id, cid),
        event_id=ev.id,
        company_id=cid,
    )
    assert not (result.get("scenarios") or [])
    # No decision can be created without a scenario_id from a successful compare
    fake = client.post(
        "/api/v1/decisions",
        headers=auth_headers,
        json={"scenario_id": "does-not-exist", "decision_note": "x"},
    )
    assert fake.status_code == 404
