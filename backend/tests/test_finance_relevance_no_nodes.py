"""Stage 6.10.1 — finance-only feature_match without twin nodes / purchase_currencies."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import Company, Event
from app.services.assessment_explain import SCORE_KIND_COMPANY
from app.services.impact import (
    assessment_state_for_impact,
    event_matches_company,
    recompute_company_impact,
)
from app.services.relevance import analyze_event_company_relevance


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def _company(db: Session) -> Company:
    co = Company(
        id=str(uuid4()),
        name="Finance only Co",
        industry="manufacturing",
        profile_status="draft",
        digital_twin_status="not_built",
        digital_twin_coverage=0.0,
    )
    db.add(co)
    db.commit()
    return co


def _rate_event(**attrs) -> Event:
    return Event(
        id=_uid("evt"),
        title="[ТЕСТ] Ключевая ставка ЦБ",
        summary="Сигнал по ключевой ставке",
        category="macro",
        event_type="risk",
        severity=40.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        match_countries_json=["Россия"],
        match_currencies_json=["RUB"],
        match_materials_json=[],
        match_categories_json=["macro", "rates"],
        attributes_json=attrs or {"rate_decision_status": "observed", "rate_from": 16, "rate_to": 16},
        is_demo=True,
    )


def _fx_event(*, currencies: list[str], **attrs) -> Event:
    return Event(
        id=_uid("evt"),
        title="[ТЕСТ] Движение курса валюты",
        summary="Курс валюты изменился",
        category="macro",
        event_type="risk",
        severity=40.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        match_countries_json=[],
        match_currencies_json=currencies,
        match_materials_json=[],
        match_categories_json=["macro", "fx"],
        attributes_json=attrs
        or {
            "fx_rate_decision": {
                "status": "observed",
                "exposure_currency": currencies[0] if currencies else "CNY",
                "quote_currency": "RUB",
                "quote_convention": "quote_per_exposure",
                "rate_from": 12.0,
                "rate_to": 13.0,
            }
        },
        is_demo=True,
    )


RATE_DEBT = {
    "debt_amount": 50_000_000,
    "debt_amount_unit": "RUB",
    "floating_rate_share_percent": 35,
}

FX_PAYMENT = {
    "fx_exposure_amount": 1000,
    "fx_exposure_currency": "CNY",
    "fx_exposure_direction": "payment",
    "fx_quote_currency": "RUB",
    "fx_quote_convention": "quote_per_exposure",
}

FX_RECEIPT = {
    **FX_PAYMENT,
    "fx_exposure_direction": "receipt",
}


@pytest.mark.parametrize(
    "finance,event_factory,expect",
    [
        (RATE_DEBT, lambda: _rate_event(), True),
        (FX_PAYMENT, lambda: _fx_event(currencies=["CNY"]), True),
        (FX_RECEIPT, lambda: _fx_event(currencies=["CNY"]), True),
        (FX_PAYMENT, lambda: _fx_event(currencies=["USD"]), False),
        ({"debt_amount": 10}, lambda: _rate_event(), False),  # incomplete rate
        ({}, lambda: _rate_event(), False),  # LOA-only analogue: no manual finance
    ],
)
def test_finance_feature_match_matrix(db: Session, finance, event_factory, expect):
    co = _company(db)
    ev = event_factory()
    db.add(ev)
    db.commit()
    rel = analyze_event_company_relevance(
        ev,
        co,
        [],
        purchase_currencies=[],
        optional_finance=finance,
    )
    assert rel.is_relevant is expect
    if expect:
        assert rel.level == "feature_match"
        assert all(m.axis != "supply" for m in rel.matched_features)


def test_rate_debt_without_purchase_currencies_opens_recompute(db: Session):
    co = _company(db)
    ev = _rate_event()
    db.add(ev)
    db.commit()
    assert (
        event_matches_company(
            ev, co, [], purchase_currencies=[], optional_finance=RATE_DEBT
        )
        is True
    )
    # Persist finance on settings for recompute_company_impact
    from app.models import CompanyProfileSettings

    db.add(
        CompanyProfileSettings(
            id=str(uuid4()),
            company_id=co.id,
            purchase_currencies_json=[],
            optional_finance_json=dict(RATE_DEBT),
            preferences_json={},
            warnings_json=[],
        )
    )
    db.commit()
    impact = recompute_company_impact(db, ev, co)
    db.commit()
    state = assessment_state_for_impact(db, ev, impact)
    assert state == "finance_ready"
    kind = (impact.score_breakdown_json or {}).get("score_kind") or (
        (impact.score_breakdown_json or {}).get("assessment_basis") or {}
    ).get("score_kind")
    # Never claim company_calculated for finance-only twin-less card
    assert kind != SCORE_KIND_COMPANY


def test_purchase_currencies_still_work_without_finance_amounts(db: Session):
    co = _company(db)
    ev = _rate_event()
    db.add(ev)
    db.commit()
    rel = analyze_event_company_relevance(
        ev, co, [], purchase_currencies=["RUB"], optional_finance={}
    )
    assert rel.is_relevant is True
    assert rel.level == "feature_match"
    assert rel.matched_features[0].axis == "currency"
