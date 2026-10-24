"""Human-readable scenario metric lines — never emit None/null/NaN into UI text."""

from __future__ import annotations

from typing import Any

from app.services.finance_scenario_presentation import (
    format_debt_amount_display,
    format_presentation_metric_line,
    present_scenario_dict,
)


def is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == value and value not in (float("inf"), float("-inf"))
    return False


def format_percent(value: Any, *, digits: int = 1) -> str | None:
    if not is_finite_number(value):
        return None
    n = float(value)
    if digits == 0:
        return f"{int(round(n))}%"
    text = f"{n:.{digits}f}".rstrip("0").rstrip(".")
    return f"{text}%"


def format_money_rub(value: Any) -> str | None:
    """Only when caller already confirmed RUB — prefer format_debt_amount_display."""
    return format_debt_amount_display(value, "RUB")


def format_debt_amount(value: Any, unit: str | None) -> str | None:
    return format_debt_amount_display(value, unit)


def scenario_label(sc: dict[str, Any], index: int = 0) -> str:
    alt = sc.get("alternative") if isinstance(sc.get("alternative"), dict) else {}
    base = sc.get("baseline") if isinstance(sc.get("baseline"), dict) else {}
    for key in ("solution_name", "label"):
        raw = sc.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    for bag in (alt, base):
        raw = bag.get("label") or bag.get("name")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    kind = sc.get("kind")
    if kind == "baseline":
        return "Без действий"
    return f"Сценарий {index + 1}"


def is_finance_scenario_payload(
    sc: dict[str, Any], *, assessment_state: str | None = None, source: str | None = None
) -> bool:
    if assessment_state == "finance_ready":
        return True
    if source == "financial_calculation":
        return True
    if sc.get("rate_change_basis") is not None:
        return True
    if isinstance(sc.get("presentation"), dict) and sc["presentation"].get("basis"):
        return True
    if sc.get("annual_rate_sensitivity") is not None:
        return True
    if sc.get("funding_pressure_percent") is not None:
        return True
    alt = sc.get("alternative") if isinstance(sc.get("alternative"), dict) else {}
    if alt.get("funding_pressure_percent") is not None:
        return True
    return False


def stop_risk_percent(sc: dict[str, Any]) -> float | None:
    alt = sc.get("alternative") if isinstance(sc.get("alternative"), dict) else {}
    base = sc.get("baseline") if isinstance(sc.get("baseline"), dict) else {}
    for bag in (alt, sc, base):
        val = bag.get("stop_risk_percent")
        if is_finite_number(val):
            return float(val)
    return None


def funding_pressure_percent(sc: dict[str, Any]) -> float | None:
    """Do not resurrect disabled pressure from defaults — only explicit finite values."""
    if sc.get("funding_pressure_status") in {
        "unavailable_severity_proxy_removed",
        "unavailable",
    }:
        return None
    alt = sc.get("alternative") if isinstance(sc.get("alternative"), dict) else {}
    for bag in (sc, alt):
        val = bag.get("funding_pressure_percent")
        if is_finite_number(val):
            return float(val)
    return None


def format_scenario_metric_line(
    sc: dict[str, Any],
    *,
    index: int = 0,
    assessment_state: str | None = None,
    source: str | None = None,
    parameters: dict[str, Any] | None = None,
    model_version: str | None = None,
) -> str | None:
    """One bullet for chat enrichment / list UI."""
    if is_finance_scenario_payload(sc, assessment_state=assessment_state, source=source):
        return format_presentation_metric_line(
            sc,
            index=index,
            parameters=parameters,
            model_version=model_version,
        )

    label = scenario_label(sc, index)
    stop = format_percent(stop_risk_percent(sc))
    if stop:
        return f"• {label}: модельная оценка риска остановки {stop}"
    lead = sc.get("lead_time_days")
    alt = sc.get("alternative") if isinstance(sc.get("alternative"), dict) else {}
    if not is_finite_number(lead):
        lead = alt.get("lead_time_days")
    if is_finite_number(lead) and int(lead) > 0:
        return f"• {label}: срок поставки ~{int(lead)} дн."
    return f"• {label}"


def format_scenario_comparison_lines(
    scenarios: list[dict[str, Any]],
    *,
    assessment_state: str | None = None,
    source: str | None = None,
    parameters: dict[str, Any] | None = None,
    model_version: str | None = None,
    limit: int = 8,
) -> list[str]:
    lines: list[str] = []
    for i, sc in enumerate(scenarios[:limit]):
        if not isinstance(sc, dict):
            continue
        # Ensure presentation attached for consistent copy
        row = sc
        if is_finance_scenario_payload(sc, assessment_state=assessment_state, source=source):
            if not isinstance(sc.get("presentation"), dict):
                row = {
                    **sc,
                    "presentation": present_scenario_dict(
                        sc, parameters=parameters, model_version=model_version
                    ),
                }
        line = format_scenario_metric_line(
            row,
            index=i,
            assessment_state=assessment_state,
            source=source,
            parameters=parameters,
            model_version=model_version,
        )
        if line:
            lines.append(line)
    return lines


def sanitize_ui_text(text: str) -> str:
    """Strip technical empty tokens from stored previews / assistant leftovers."""
    if not text:
        return text
    import re

    out = text
    out = re.sub(
        r"риск остановки\s*(None|null|undefined|NaN)\s*%?",
        "финансовый сценарий без риска остановки",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"\b(None|null|undefined|NaN)\s*%", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\b(None|null|undefined|NaN)\b", "", out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    return out.strip()
