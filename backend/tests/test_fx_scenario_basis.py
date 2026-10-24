"""Stage 5.4: FX scenarios — currencies, quote convention, no severity proxy."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.models import Event
from app.services.finance_scenario_presentation import build_finance_scenario_presentation
from app.services.finance_validation import validate_optional_finance_fx
from app.services.financial_simulator import simulate_financial_scenarios
from app.services.fx_scenario import (
    compute_fx_value_change,
    resolve_fx_exposure,
    resolve_observed_fx_change,
    simulate_fx_scenarios,
)


def _event(**kwargs) -> Event:
    return Event(
        id=kwargs.get("id", f"evt_fx_{uuid4().hex[:8]}"),
        title=kwargs.get("title", "Курс CNY"),
        summary=kwargs.get("summary", "fx audit"),
        category=kwargs.get("category", "macro"),
        event_type="risk",
        severity=float(kwargs.get("severity", 90.0)),
        urgency_default="watch",
        status="active",
        occurred_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        match_countries_json=[],
        match_categories_json=[],
        match_currencies_json=kwargs.get("match_currencies_json", ["CNY"]),
        match_materials_json=kwargs.get("match_materials_json", []),
        attributes_json=kwargs.get("attributes_json", {}),
        is_demo=True,
    )


def _fx_finance(**overrides):
    base = {
        "fx_exposure_amount": 1000,
        "fx_exposure_currency": "CNY",
        "fx_exposure_direction": "payment",
        "fx_quote_currency": "RUB",
        "fx_quote_convention": "quote_per_exposure",
    }
    base.update(overrides)
    return base


def _trusted_attrs(rate_from=12, rate_to=13, **extra):
    return {
        "fx_rate_decision": {
            "status": "observed",
            "exposure_currency": "CNY",
            "quote_currency": "RUB",
            "quote_convention": "quote_per_exposure",
            "rate_from": rate_from,
            "rate_to": rate_to,
            **extra,
        }
    }


def test_payment_known_rates_value_change():
    exp = resolve_fx_exposure(_fx_finance())
    assert exp is not None
    calc = compute_fx_value_change(
        exposure=exp,
        rate_from=Decimal("12"),
        rate_to=Decimal("13"),
        quote_currency="RUB",
    )
    assert calc["value_change"] == "1000.00"
    assert calc["meaning"] == "payment_cost_increase"
    assert "платежа" in calc["meaning_label"].lower() or "payment" in calc["meaning"]


def test_receipt_same_rates_different_meaning():
    exp = resolve_fx_exposure(_fx_finance(fx_exposure_direction="receipt"))
    assert exp is not None
    calc = compute_fx_value_change(
        exposure=exp,
        rate_from=Decimal("12"),
        rate_to=Decimal("13"),
        quote_currency="RUB",
    )
    assert calc["value_change"] == "1000.00"
    assert calc["meaning"] == "receipt_equivalent_increase"
    assert "прибыл" not in calc["meaning_label"].lower()


def test_rate_up_down_flat():
    exp = resolve_fx_exposure(_fx_finance())
    assert exp is not None
    up = compute_fx_value_change(
        exposure=exp, rate_from=Decimal("12"), rate_to=Decimal("13"), quote_currency="RUB"
    )
    down = compute_fx_value_change(
        exposure=exp, rate_from=Decimal("13"), rate_to=Decimal("12"), quote_currency="RUB"
    )
    flat = compute_fx_value_change(
        exposure=exp, rate_from=Decimal("12"), rate_to=Decimal("12"), quote_currency="RUB"
    )
    assert up["value_change"] == "1000.00"
    assert down["value_change"] == "-1000.00"
    assert flat["value_change"] == "0.00"


def test_what_if_with_base_rate():
    event = _event(attributes_json={})
    pkg = simulate_fx_scenarios(
        event=event,
        optional_finance=_fx_finance(fx_rate_from=12),
        assumed_fx_change_percent=Decimal("10"),
    )
    # Profile rates alone are not observed; with assumed % and profile from → assumed money
    # resolve uses profile_rate_from only inside assumed path when assumed_pct set.
    assert pkg["status"] == "ok"
    assert pkg["scenarios"][0]["fx_change_basis"] == "assumed"
    assert pkg["scenarios"][0]["fx_value_change"] == "1200.00"  # 1000 * (13.2-12)


def test_what_if_without_base_rate_no_rub_effect():
    event = _event(attributes_json={})
    pkg = simulate_fx_scenarios(
        event=event,
        optional_finance=_fx_finance(),
        assumed_fx_change_percent=10,
    )
    assert pkg["status"] == "unavailable"
    assert pkg.get("qualitative") is not None
    assert not pkg.get("scenarios")


def test_volume_without_currency_not_money():
    event = _event(attributes_json=_trusted_attrs())
    pkg = simulate_fx_scenarios(
        event=event,
        optional_finance={"fx_purchase_volume": 25_000_000},
    )
    assert pkg["status"] == "unavailable"
    reasons = (pkg.get("parameters") or {}).get("fx_change", {}).get("unavailable_reasons") or []
    assert any("fx_purchase_volume" in r for r in reasons)


def test_pair_mismatch_conflict():
    event = _event(
        attributes_json=_trusted_attrs(),
    )
    # Force USD exposure vs CNY event pair
    pkg = simulate_fx_scenarios(
        event=event,
        optional_finance=_fx_finance(fx_exposure_currency="USD"),
    )
    assert pkg["status"] == "unavailable"
    assert (pkg.get("parameters") or {}).get("fx_change", {}).get("basis") == "conflict"


def test_contradictory_delta_conflict():
    event = _event(
        attributes_json=_trusted_attrs(rate_from=12, rate_to=13, rate_delta=5),
    )
    obs = resolve_observed_fx_change(event, exposure_currency="CNY", quote_currency="RUB")
    assert obs.basis == "conflict"


def test_invalid_rates_rejected():
    for bad in (0, -1, "NaN", float("inf")):
        event = _event(attributes_json=_trusted_attrs(rate_from=12, rate_to=bad))
        obs = resolve_observed_fx_change(event, exposure_currency="CNY", quote_currency="RUB")
        assert obs.basis in {"conflict", "none"}, bad


def test_zero_exposure_known():
    event = _event(attributes_json=_trusted_attrs())
    pkg = simulate_fx_scenarios(
        event=event,
        optional_finance=_fx_finance(fx_exposure_amount=0),
    )
    assert pkg["status"] == "ok"
    assert pkg["scenarios"][0]["fx_value_change"] == "0.00"


def test_same_currency_no_fx_move():
    event = _event(
        attributes_json={
            "fx_rate_decision": {
                "status": "observed",
                "exposure_currency": "RUB",
                "quote_currency": "RUB",
                "quote_convention": "quote_per_exposure",
                "rate_from": 1,
                "rate_to": 1,
            }
        }
    )
    pkg = simulate_fx_scenarios(
        event=event,
        optional_finance=_fx_finance(
            fx_exposure_currency="RUB",
            fx_quote_currency="RUB",
            fx_exposure_amount=5000,
        ),
    )
    assert pkg["status"] == "ok"
    assert pkg["scenarios"][0]["fx_value_change"] == "0.00"


def test_unknown_period_label():
    event = _event(attributes_json=_trusted_attrs())
    pkg = simulate_fx_scenarios(event=event, optional_finance=_fx_finance())
    assert pkg["scenarios"][0]["fx_period_label"] == "Период не указан"
    pres = build_finance_scenario_presentation(
        results=pkg["scenarios"][0],
        parameters=pkg["parameters"],
        model_version=pkg["model_version"],
    )
    assert "Период не указан" in (pres.get("fx_period_line") or "")


def test_severity_does_not_drive_fx_money():
    event = _event(severity=99.0, attributes_json={})
    pkg = simulate_fx_scenarios(event=event, optional_finance=_fx_finance())
    assert pkg["status"] == "unavailable"
    assert (pkg.get("parameters") or {}).get("severity_used_as_fx_rate") is False


def test_bare_fx_from_to_not_observed():
    event = _event(attributes_json={"fx_from": 90, "fx_to": 100})
    obs = resolve_observed_fx_change(event)
    assert obs.basis == "none"


def test_basis_persisted_in_scenario_row():
    event = _event(attributes_json=_trusted_attrs())
    pkg = simulate_fx_scenarios(event=event, optional_finance=_fx_finance())
    row = pkg["scenarios"][0]
    assert row["fx_change_basis"] == "observed"
    assert row["fx_quote_convention"] == "quote_per_exposure"
    assert "assumptions" in row and row["assumptions"]
    assert "limitations" in row and row["limitations"]
    assert pkg["parameters"]["fx_change"]["basis"] == "observed"


def test_pure_fx_without_debt():
    """FX track does not require debt/floating."""
    event = _event(attributes_json=_trusted_attrs())
    # No FINANCE_REQUIRED_KEYS — only typed FX
    pkg = simulate_financial_scenarios(
        event=event,
        optional_finance=_fx_finance(),
    )
    assert pkg["status"] == "ok"
    assert pkg.get("fx_status") == "ok"
    assert any(s.get("track") == "fx" for s in pkg["scenarios"])
    assert not any(s.get("track") == "rate" and s.get("annual_rate_sensitivity") for s in pkg["scenarios"])


def test_rate_track_regression_unchanged_formula():
    """Rate annual = debt × floating × Δ/100 (5.2) still holds beside FX."""
    event = _event(
        title="ЦБ повысил ставку",
        attributes_json={
            "rate_decision_status": "observed",
            "rate_from": 14.0,
            "rate_to": 15.0,
            **_trusted_attrs(),
        },
    )
    finance = {
        "debt_amount": 100_000_000,
        "floating_rate_share_percent": 40,
        "near_term_payments_90d": 8_000_000,
        "fx_purchase_volume": 25_000_000,
        "cash_reserve_days": 21,
        "debt_amount_unit": "RUB",
        **_fx_finance(),
    }
    pkg = simulate_financial_scenarios(event=event, optional_finance=finance)
    assert pkg["status"] == "ok"
    rate_rows = [s for s in pkg["scenarios"] if s.get("track") == "rate"]
    fx_rows = [s for s in pkg["scenarios"] if s.get("track") == "fx"]
    assert rate_rows
    assert fx_rows
    baseline = next(s for s in rate_rows if s.get("kind") == "baseline")
    # 100e6 * 0.4 * 0.01 = 400_000
    assert baseline["annual_rate_sensitivity"] == 400_000.0
    assert fx_rows[0]["fx_value_change"] == "1000.00"


def test_validate_fx_rejects_nan_and_negative_rate():
    with pytest.raises(AppError):
        validate_optional_finance_fx(_fx_finance(fx_rate_from=float("nan")))
    with pytest.raises(AppError):
        validate_optional_finance_fx(_fx_finance(fx_rate_from=-1))
    with pytest.raises(AppError):
        validate_optional_finance_fx(
            {
                "fx_exposure_amount": 1,
                "fx_exposure_currency": "CNY",
                # missing direction/quote
            }
        )


def test_presentation_fx_not_rate_copy():
    event = _event(attributes_json=_trusted_attrs())
    pkg = simulate_fx_scenarios(event=event, optional_finance=_fx_finance())
    pres = build_finance_scenario_presentation(
        results=pkg["scenarios"][0],
        parameters=pkg["parameters"],
    )
    assert pres["track"] == "fx"
    assert pres["delta_pp"] is None
    assert pres["annual_sensitivity"] is None
    assert "п.п" not in (pres.get("money_line") or "")
    assert "плавающ" not in (pres.get("money_line") or "").lower()
    assert "1 000.00" in (pres.get("money_line") or "") or "1000" in (
        (pres.get("money_line") or "").replace(" ", "")
    )
