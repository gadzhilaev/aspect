"""Stage 5.3: unified finance scenario presentation contract."""

from __future__ import annotations

from app.services.finance_scenario_presentation import (
    attach_presentation_to_scenarios,
    build_finance_scenario_presentation,
    format_debt_amount_display,
    present_scenario_dict,
    resolve_present_basis,
)
from app.services.scenario_display import format_scenario_metric_line


def test_observed_hike_copy():
    results = {
        "label": "Без действий",
        "rate_change_basis": "observed",
        "rate_change_delta_pp": 1.0,
        "annual_rate_sensitivity": 400_000.0,
        "extra_annual_cost": 400_000.0,
        "debt_amount_unit": "unspecified",
        "near_term_pressure": None,
        "funding_pressure_percent": None,
    }
    params = {
        "kind": "financial",
        "debt_amount_unit": "unspecified",
        "rate_change": {"basis": "observed", "observed_delta_pp": 1.0, "used_delta_pp": 1.0},
        "model_version": "sim-v1.0-finance-rate-v2",
    }
    pres = build_finance_scenario_presentation(
        results=results, parameters=params, model_version="sim-v1.0-finance-rate-v2"
    )
    assert pres["basis"] == "observed"
    assert "Ключевая ставка изменилась на 1 п.п." in (pres["rate_fact_line"] or "")
    assert "Условная годовая чувствительность" in (pres["money_line"] or "")
    assert "₽" not in (pres["money_line"] or "")
    assert "единицы введённой суммы долга" in (pres["money_line"] or "")
    assert "не эффект за 90 дней" in (pres["decision_horizon"] or "")
    assert "Горизонт около 90" not in (pres["decision_horizon"] or "")
    assert "кредит" in (pres["credit_transfer_disclaimer"] or "").lower()


def test_observed_hold_zero():
    results = {
        "rate_change_basis": "observed",
        "rate_change_delta_pp": 0.0,
        "annual_rate_sensitivity": 0.0,
        "extra_annual_cost": 0.0,
        "debt_amount_unit": "unspecified",
    }
    pres = build_finance_scenario_presentation(results=results, parameters={"kind": "financial"})
    assert "не изменилась" in (pres["rate_fact_line"] or "").lower()
    assert "0" in (pres["money_line"] or "")
    assert "всех финансовых рисков" in (pres["hold_note"] or "")


def test_rate_cut_negative_money_label():
    results = {
        "rate_change_basis": "observed",
        "rate_change_delta_pp": -1.0,
        "annual_rate_sensitivity": -400_000.0,
        "extra_annual_cost": -400_000.0,
        "debt_amount_unit": "RUB",
    }
    pres = build_finance_scenario_presentation(results=results, parameters={})
    assert "Снижение условной годовой нагрузки" in (pres["money_line"] or "")
    assert "дополнительн" not in (pres["money_line"] or "").lower()
    assert "₽" in (pres["money_line"] or "")
    assert pres["debt_unit_confirmed_rub"] is True


def test_assumed_what_if_badge():
    results = {
        "rate_change_basis": "assumed",
        "rate_change_delta_pp": 1.5,
        "annual_rate_sensitivity": 600_000.0,
        "action_id": "assumed_rate_shock",
        "debt_amount_unit": "unspecified",
    }
    pres = build_finance_scenario_presentation(results=results, parameters={})
    assert pres["basis"] == "assumed"
    assert pres["assumption_badge"] == "Допущение сценария"
    assert "Что если ставка изменится на 1.5 п.п." in (pres["what_if_line"] or "")
    assert "банк" not in (pres["what_if_line"] or "").lower()


def test_none_and_conflict_no_number():
    none_p = build_finance_scenario_presentation(
        results={"rate_change_basis": "none", "extra_annual_cost": 999},
        parameters={},
    )
    assert none_p["unavailable_message"] == "Недостаточно данных для расчёта изменения расходов"
    assert none_p["money_line"] is None
    assert none_p["annual_sensitivity"] is None

    conflict_p = build_finance_scenario_presentation(
        results={"rate_change_basis": "conflict", "extra_annual_cost": 999},
        parameters={},
    )
    assert "противореч" in (conflict_p["unavailable_message"] or "")
    assert conflict_p["money_line"] is None


def test_unknown_unit_vs_rub():
    assert "₽" not in (format_debt_amount_display(1_000_000, "unspecified") or "")
    assert "единицы введённой суммы долга" in (format_debt_amount_display(1_000_000, None) or "")
    assert (format_debt_amount_display(1_000_000, "RUB") or "").endswith("₽")


def test_legacy_proxy_and_missing():
    legacy = build_finance_scenario_presentation(
        results={"extra_annual_cost": 100.0, "label": "Без действий"},
        parameters={"shock_proxy_pp": 1.375, "kind": "financial"},
    )
    assert legacy["basis"] == "legacy"
    assert legacy["legacy"] is True
    assert "observed" not in (legacy["historical_note"] or "").lower() or "не является observed" in (
        legacy["historical_note"] or ""
    )
    assert legacy["assumption_badge"] == "Допущение прежней модели"

    empty = resolve_present_basis({}, {})
    assert empty[0] in {"none", "legacy"}


def test_observed_plus_what_if_visually_distinct():
    params = {
        "kind": "financial",
        "debt_amount_unit": "unspecified",
        "rate_change": {
            "basis": "observed",
            "observed_delta_pp": 0.0,
            "assumed_delta_pp": 1.5,
        },
    }
    rows = attach_presentation_to_scenarios(
        [
            {
                "label": "Без действий",
                "rate_change_basis": "observed",
                "rate_change_delta_pp": 0.0,
                "annual_rate_sensitivity": 0.0,
                "debt_amount_unit": "unspecified",
            },
            {
                "label": "What-if: ставка +1.5 п.п.",
                "action_id": "assumed_rate_shock",
                "rate_change_basis": "assumed",
                "rate_change_delta_pp": 1.5,
                "annual_rate_sensitivity": 600_000.0,
                "debt_amount_unit": "unspecified",
            },
        ],
        parameters=params,
        model_version="sim-v1.0-finance-rate-v2",
    )
    assert rows[0]["presentation"]["basis"] == "observed"
    assert rows[1]["presentation"]["basis"] == "assumed"
    assert rows[1]["presentation"]["assumption_badge"] == "Допущение сценария"
    assert rows[0]["presentation"]["rate_fact_line"] != rows[1]["presentation"]["what_if_line"]


def test_disabled_null_metrics_not_in_suffix():
    results = {
        "rate_change_basis": "observed",
        "rate_change_delta_pp": 1.0,
        "annual_rate_sensitivity": 10.0,
        "near_term_pressure": None,
        "near_term_pressure_status": "unavailable_not_severity_proxy",
        "fx_exposure_index": None,
        "funding_pressure_percent": None,
        "funding_pressure_status": "unavailable_severity_proxy_removed",
        "debt_amount_unit": "unspecified",
    }
    line = format_scenario_metric_line(
        {**results, "presentation": present_scenario_dict(results, parameters={})},
        assessment_state="finance_ready",
        source="financial_calculation",
    )
    assert line
    assert "90" not in line
    assert "давление финансирования" not in line
    assert "None" not in line


def test_basis_not_inferred_from_label():
    # Label says hike but fields say assumed — trust fields
    results = {
        "label": "Ключевая ставка повышена факт",
        "rate_change_basis": "assumed",
        "rate_change_delta_pp": 2.0,
        "annual_rate_sensitivity": 1.0,
    }
    basis, _ = resolve_present_basis(results, {})
    assert basis == "assumed"
