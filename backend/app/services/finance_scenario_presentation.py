"""Unified presentation contract for finance scenarios (stages 5.3–5.4).

Single adapter for basis → copy. Do not infer basis from scenario labels or magnitudes.
Rate formulas: financial_simulator (5.2). FX formulas: fx_scenario (5.4).
"""

from __future__ import annotations

from typing import Any, Literal

from app.services.financial_simulator import legacy_rate_basis_from_parameters
from app.services.fx_scenario import legacy_fx_basis_from_parameters

RatePresentBasis = Literal["observed", "assumed", "none", "conflict", "legacy"]
PresentTrack = Literal["rate", "fx"]

_ACTION_MODEL_NOTE = (
    "Коэффициенты альтернатив (хедж / рефинансирование) — допущения модели, "
    "не гарантия снижения расходов"
)


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == value and value not in (float("inf"), float("-inf"))
    return False


def _fmt_pp(delta: float) -> str:
    text = f"{delta:g}"
    return text


def format_debt_amount_display(value: Any, unit: str | None) -> str | None:
    if not _is_finite_number(value):
        return None
    n = float(value)
    u = (unit or "unspecified").strip().upper()
    if abs(n) >= 1_000_000:
        body = f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + " млн"
    elif abs(n) >= 1_000:
        body = f"{n / 1_000:.1f}".rstrip("0").rstrip(".") + " тыс."
    else:
        body = f"{int(round(n))}"
    if u in {"", "UNSPECIFIED", "UNKNOWN"}:
        return f"{body} (единицы введённой суммы долга)"
    if u in {"RUB", "RUR", "₽"}:
        return f"{body} ₽"
    return f"{body} {u}"


def resolve_present_basis(
    results: dict[str, Any] | None,
    parameters: dict[str, Any] | None,
) -> tuple[RatePresentBasis, dict[str, Any]]:
    """Resolve display basis from stored fields only (never from label/title)."""
    results = results or {}
    parameters = parameters or {}

    raw = results.get("rate_change_basis")
    if isinstance(raw, str) and raw.strip() in {"observed", "assumed", "none", "conflict"}:
        meta = {}
        rc = parameters.get("rate_change")
        if isinstance(rc, dict):
            meta = dict(rc)
        return raw.strip(), meta  # type: ignore[return-value]

    rc = parameters.get("rate_change")
    if isinstance(rc, dict) and rc.get("basis") in {
        "observed",
        "assumed",
        "none",
        "conflict",
    }:
        return str(rc["basis"]), dict(rc)  # type: ignore[return-value]

    legacy = legacy_rate_basis_from_parameters(parameters)
    if legacy.get("legacy"):
        if parameters.get("shock_proxy_pp") is not None:
            return "legacy", {
                **legacy,
                "shock_proxy_pp": parameters.get("shock_proxy_pp"),
            }
        return "legacy", legacy

    # Finance-looking payload without typed basis
    if (
        results.get("extra_annual_cost") is not None
        or results.get("annual_rate_sensitivity") is not None
        or results.get("funding_pressure_percent") is not None
        or parameters.get("kind") == "financial"
    ):
        return "legacy", {"source": "untyped_finance_payload", "legacy": True}

    return "none", {"unavailable_reasons": ["Основание rate-сценария не сохранено"]}


def _delta_pp(results: dict[str, Any], meta: dict[str, Any]) -> float | None:
    for bag in (results, meta):
        for key in ("rate_change_delta_pp", "used_delta_pp", "delta_pp", "observed_delta_pp"):
            if _is_finite_number(bag.get(key)):
                return float(bag[key])
    return None


def _annual(results: dict[str, Any]) -> float | None:
    for key in ("annual_rate_sensitivity", "extra_annual_cost"):
        if _is_finite_number(results.get(key)):
            return float(results[key])
    return None


def _debt_unit(results: dict[str, Any], parameters: dict[str, Any]) -> str:
    for bag in (results, parameters):
        raw = bag.get("debt_amount_unit") or bag.get("debt_currency")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "unspecified"


def _is_fx_row(results: dict[str, Any], parameters: dict[str, Any]) -> bool:
    if results.get("track") == "fx" or parameters.get("track") == "fx":
        return True
    if results.get("fx_change_basis") is not None:
        return True
    if results.get("fx_value_change") is not None:
        return True
    return False


def resolve_fx_present_basis(
    results: dict[str, Any],
    parameters: dict[str, Any],
) -> tuple[RatePresentBasis, dict[str, Any]]:
    raw = results.get("fx_change_basis")
    if isinstance(raw, str) and raw.strip() in {"observed", "assumed", "none", "conflict"}:
        meta: dict[str, Any] = {}
        fc = parameters.get("fx_change")
        if isinstance(fc, dict):
            meta = dict(fc)
        return raw.strip(), meta  # type: ignore[return-value]
    fc = parameters.get("fx_change")
    if isinstance(fc, dict) and fc.get("basis") in {
        "observed",
        "assumed",
        "none",
        "conflict",
    }:
        return str(fc["basis"]), dict(fc)  # type: ignore[return-value]
    legacy = legacy_fx_basis_from_parameters(parameters)
    if legacy.get("legacy"):
        return "legacy", legacy
    return "none", {"unavailable_reasons": ["Основание FX-сценария не сохранено"]}


def _fmt_money_ccy(value: Any, ccy: str | None) -> str | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    body = f"{n:,.2f}".replace(",", " ")
    u = (ccy or "").strip().upper()
    if not u or u in {"UNSPECIFIED", "UNKNOWN"}:
        return body
    if u in {"RUB", "RUR", "₽"}:
        return f"{body} ₽"
    return f"{body} {u}"


def build_fx_scenario_presentation(
    *,
    results: dict[str, Any],
    parameters: dict[str, Any],
    model_version: str | None,
    label: str | None,
) -> dict[str, Any]:
    """FX branch — never reuse rate annual / п.п. copy for FX money."""
    basis, meta = resolve_fx_present_basis(results, parameters)
    version = model_version or parameters.get("model_version")
    version_s = version if isinstance(version, str) else None

    exp_ccy = results.get("fx_exposure_currency") or (parameters.get("fx_exposure") or {}).get(
        "currency"
    )
    quote_ccy = results.get("fx_quote_currency") or results.get("fx_result_currency")
    amount = results.get("fx_exposure_amount")
    direction = results.get("fx_exposure_direction")
    rate_from = results.get("fx_rate_from")
    rate_to = results.get("fx_rate_to")
    value_change = results.get("fx_value_change")
    meaning_label = results.get("fx_value_change_meaning_label")
    period_label = results.get("fx_period_label") or (
        results.get("fx_period") if results.get("fx_period") else "Период не указан"
    )
    if not isinstance(period_label, str) or not period_label.strip():
        period_label = "Период не указан"

    pair_line: str | None = None
    if isinstance(exp_ccy, str) and isinstance(quote_ccy, str):
        pair_line = (
            f"Пара {quote_ccy}/{exp_ccy}: единиц {quote_ccy} за 1 {exp_ccy} "
            "(quote_per_exposure)"
        )

    rate_fact_line: str | None = None
    what_if_line: str | None = None
    assumption_badge: str | None = None
    money_line: str | None = None
    unavailable_message: str | None = None
    historical_note: str | None = None
    hold_note: str | None = None
    limitations_line: str | None = None

    lim = results.get("limitations")
    if isinstance(lim, list) and lim:
        limitations_line = "; ".join(str(x) for x in lim[:3])

    if basis == "conflict":
        unavailable_message = "Исходные данные о курсе противоречат друг другу"
        value_change = None
    elif basis == "none":
        unavailable_message = "Недостаточно данных для FX-расчёта"
        value_change = None
    elif basis == "legacy":
        historical_note = (
            "Историческая FX/severity-оценка; не является observed курсом"
        )
        assumption_badge = "Допущение прежней модели"
        value_change = None
    elif basis == "assumed":
        assumption_badge = "Допущение сценария"
        pct = meta.get("assumed_change_percent") or results.get("assumed_fx_change_percent")
        if pct is not None:
            what_if_line = f"Что если курс изменится на {pct}%"
        else:
            what_if_line = "What-if изменения курса (допущение сценария)"
        if rate_from is not None and rate_to is not None:
            what_if_line = (
                f"{what_if_line}: {rate_from} → {rate_to} "
                f"{quote_ccy or ''}/{exp_ccy or ''}".strip()
            )
    elif basis == "observed":
        if rate_from is not None and rate_to is not None:
            rate_fact_line = (
                f"Курс {quote_ccy or '?'}/{exp_ccy or '?'}: {rate_from} → {rate_to}"
            )
        else:
            rate_fact_line = "Observed изменение курса учтено"

    amount_line: str | None = None
    if amount is not None and isinstance(exp_ccy, str):
        dir_ru = (
            "платёж"
            if direction == "payment"
            else ("поступление" if direction == "receipt" else "экспозиция")
        )
        amount_line = f"Сумма ({dir_ru}): {amount} {exp_ccy}"

    if basis in {"observed", "assumed"} and value_change is not None:
        money = _fmt_money_ccy(value_change, quote_ccy if isinstance(quote_ccy, str) else None)
        if money is not None:
            label_m = (
                meaning_label
                if isinstance(meaning_label, str) and meaning_label.strip()
                else "Изменение эквивалента"
            )
            money_line = f"{label_m}: {money}"

    period_line = f"Период: {period_label}"

    suffix_parts = [
        assumption_badge,
        pair_line,
        rate_fact_line,
        what_if_line,
        amount_line,
        money_line,
        period_line if money_line or unavailable_message else None,
        unavailable_message,
        historical_note if basis == "legacy" else None,
    ]
    suffix = " · ".join(p for p in suffix_parts if isinstance(p, str) and p.strip()) or None

    decision_parts: list[str] = []
    head = f"Выбран вариант «{label}». " if isinstance(label, str) and label.strip() else ""
    for part in (pair_line, rate_fact_line, what_if_line, amount_line, money_line, period_line):
        if part:
            decision_parts.append(part)
    if unavailable_message:
        decision_parts = [unavailable_message]
    if limitations_line and money_line:
        decision_parts.append(limitations_line)

    return {
        "track": "fx",
        "basis": basis,
        "legacy": basis == "legacy",
        "delta_pp": None,
        "annual_sensitivity": None,
        "money_period": None,
        "debt_amount_unit": "n/a",
        "debt_unit_confirmed_rub": False,
        "fx_pair_line": pair_line,
        "fx_amount_line": amount_line,
        "fx_period_line": period_line,
        "fx_limitations_line": limitations_line,
        "fx_value_change": str(value_change) if value_change is not None else None,
        "fx_result_currency": quote_ccy if isinstance(quote_ccy, str) else None,
        "rate_fact_line": rate_fact_line,
        "what_if_line": what_if_line,
        "assumption_badge": assumption_badge,
        "money_line": money_line,
        "hold_note": hold_note,
        "unavailable_message": unavailable_message,
        "historical_note": historical_note,
        "model_version": version_s,
        "metric_suffix": suffix,
        "decision_reason": head + (" ".join(decision_parts) if decision_parts else "FX-сценарий."),
        "decision_horizon": period_line if money_line else None,
        "expected_effect": money_line or unavailable_message or historical_note,
        "action_model_note": None,
        "credit_transfer_disclaimer": (
            "Observed рыночный курс не является доказанным курсом исполнения договора"
            if basis == "observed" and money_line
            else None
        ),
    }


def build_finance_scenario_presentation(
    *,
    results: dict[str, Any] | None = None,
    parameters: dict[str, Any] | None = None,
    model_version: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Canonical presentation object for API / UI / assistant enrichment."""
    results = dict(results or {})
    parameters = dict(parameters or {})
    if _is_fx_row(results, parameters):
        out = build_fx_scenario_presentation(
            results=results,
            parameters=parameters,
            model_version=model_version,
            label=label,
        )
        return out
    basis, meta = resolve_present_basis(results, parameters)
    delta = _delta_pp(results, meta)
    annual = _annual(results)
    unit = _debt_unit(results, parameters)
    rub_confirmed = unit.strip().upper() in {"RUB", "RUR", "₽"}
    version = model_version or parameters.get("model_version")
    if isinstance(version, str):
        version_s: str | None = version
    else:
        version_s = None

    rate_fact_line: str | None = None
    what_if_line: str | None = None
    assumption_badge: str | None = None
    money_line: str | None = None
    unavailable_message: str | None = None
    historical_note: str | None = None
    hold_note: str | None = None

    if basis == "conflict":
        unavailable_message = "Исходные данные о ставке противоречат друг другу"
        # Never show a silently chosen number
        annual = None
        money_line = None
    elif basis == "none":
        unavailable_message = "Недостаточно данных для расчёта изменения расходов"
        annual = None
        money_line = None
    elif basis == "legacy":
        historical_note = "Историческая оценка: основание расчёта не сохранено"
        if meta.get("shock_proxy_pp") is not None:
            historical_note = (
                "Историческая оценка прежней модели (shock_proxy_pp); "
                "не является observed изменением ставки"
            )
            assumption_badge = "Допущение прежней модели"
        # Show money only as historical estimate without inventing RUB
        if _is_finite_number(annual):
            money = format_debt_amount_display(annual, "unspecified")
            if money:
                money_line = f"Историческая условная оценка ~{money}"
    elif basis == "assumed":
        assumption_badge = "Допущение сценария"
        if delta is not None:
            what_if_line = f"Что если ставка изменится на {_fmt_pp(delta)} п.п."
        else:
            what_if_line = "Что если ставка изменится (величина не сохранена)"
        if _is_finite_number(annual):
            money = format_debt_amount_display(annual, unit)
            if money is not None:
                n = float(annual)
                if n < 0:
                    money_line = f"Снижение условной годовой нагрузки ~{money}"
                elif n == 0:
                    money_line = (
                        f"Условная годовая чувствительность 0 ({money}) — "
                        "нет эффекта от изменения ставки в этой модели"
                    )
                else:
                    money_line = (
                        "Условная годовая чувствительность при переносе изменения "
                        f"на плавающую часть долга ~{money}"
                    )
    elif basis == "observed":
        if delta is not None and abs(float(delta)) < 1e-12:
            rate_fact_line = "Ключевая ставка не изменилась"
            hold_note = (
                "Нулевой rate-результат означает отсутствие эффекта именно от изменения "
                "ставки в этой модели, а не отсутствие всех финансовых рисков"
            )
        elif delta is not None:
            rate_fact_line = f"Ключевая ставка изменилась на {_fmt_pp(float(delta))} п.п."
        else:
            rate_fact_line = "Ключевая ставка: observed-изменение учтено"
        if _is_finite_number(annual):
            money = format_debt_amount_display(annual, unit)
            if money is not None:
                n = float(annual)
                if n < 0:
                    money_line = f"Снижение условной годовой нагрузки ~{money}"
                elif n == 0:
                    money_line = (
                        f"Условная годовая чувствительность 0 ({money}) — "
                        "нет эффекта от изменения ставки в этой модели"
                    )
                else:
                    money_line = (
                        "Условная годовая чувствительность при переносе изменения "
                        f"на плавающую часть долга ~{money}"
                    )

    # Compact suffix for lists
    suffix_parts: list[str] = []
    if assumption_badge:
        suffix_parts.append(assumption_badge)
    if rate_fact_line:
        suffix_parts.append(rate_fact_line)
    if what_if_line:
        suffix_parts.append(what_if_line)
    if money_line:
        suffix_parts.append(money_line)
    if unavailable_message:
        suffix_parts.append(unavailable_message)
    if historical_note and basis == "legacy" and not money_line:
        suffix_parts.append(historical_note)

    # Decision / assistant prose
    action_id = results.get("action_id")
    is_action_alt = action_id in {"reduce_fx_exposure", "review_financing"}
    decision_reason = _decision_reason(
        basis=basis,
        label=label or results.get("label"),
        rate_fact_line=rate_fact_line,
        what_if_line=what_if_line,
        money_line=money_line,
        unavailable_message=unavailable_message,
        historical_note=historical_note,
        is_action_alt=is_action_alt,
    )
    expected_effect = _expected_effect(
        basis=basis,
        annual=annual,
        is_action_alt=is_action_alt,
        action_id=str(action_id) if action_id else None,
        unavailable_message=unavailable_message,
    )
    horizon = _horizon(basis=basis)

    return {
        "track": "rate",
        "basis": basis,
        "legacy": basis == "legacy",
        "delta_pp": delta,
        "annual_sensitivity": annual,
        "money_period": "annual" if money_line else None,
        "debt_amount_unit": unit,
        "debt_unit_confirmed_rub": rub_confirmed,
        "fx_pair_line": None,
        "fx_amount_line": None,
        "fx_period_line": None,
        "fx_limitations_line": None,
        "fx_value_change": None,
        "fx_result_currency": None,
        "rate_fact_line": rate_fact_line,
        "what_if_line": what_if_line,
        "assumption_badge": assumption_badge,
        "money_line": money_line,
        "hold_note": hold_note,
        "unavailable_message": unavailable_message,
        "historical_note": historical_note,
        "model_version": version_s,
        "metric_suffix": " · ".join(suffix_parts) if suffix_parts else None,
        "decision_reason": decision_reason,
        "decision_horizon": horizon,
        "expected_effect": expected_effect,
        "action_model_note": _ACTION_MODEL_NOTE if is_action_alt else None,
        "credit_transfer_disclaimer": (
            "Наличие observed изменения ключевой ставки не делает расчёт фактическим "
            "изменением условий конкретного кредита"
            if basis == "observed" and money_line
            else None
        ),
    }


def _decision_reason(
    *,
    basis: RatePresentBasis,
    label: Any,
    rate_fact_line: str | None,
    what_if_line: str | None,
    money_line: str | None,
    unavailable_message: str | None,
    historical_note: str | None,
    is_action_alt: bool,
) -> str:
    label_s = label.strip() if isinstance(label, str) and label.strip() else None
    head = f"Выбран вариант «{label_s}». " if label_s else ""
    if basis == "conflict":
        return head + (unavailable_message or "Данные о ставке противоречивы.")
    if basis == "none":
        return head + (unavailable_message or "Недостаточно данных для расчёта.")
    if basis == "legacy":
        return head + (historical_note or "Историческая оценка без сохранённого основания.")
    parts: list[str] = []
    if rate_fact_line:
        parts.append(rate_fact_line)
    if what_if_line:
        parts.append(what_if_line + " (допущение сценария, не факт и не прогноз банка)")
    if money_line:
        parts.append(money_line)
    if is_action_alt:
        parts.append(_ACTION_MODEL_NOTE)
    if not parts:
        return head + "Финансовый сценарий по ставке."
    return head + " ".join(parts)


def _expected_effect(
    *,
    basis: RatePresentBasis,
    annual: float | None,
    is_action_alt: bool,
    action_id: str | None,
    unavailable_message: str | None,
) -> str | None:
    if basis in {"none", "conflict"}:
        return unavailable_message
    if basis == "legacy":
        return "Историческая оценка (основание не типизировано)"
    if action_id == "reduce_fx_exposure":
        return "Допущение модели: снижение валютной экспозиции (эффект не гарантирован)"
    if action_id == "review_financing":
        return "Допущение модели: пересмотр финансирования (снижение расходов не гарантировано)"
    if action_id == "assumed_rate_shock":
        return "What-if по изменению ставки (допущение сценария)"
    if _is_finite_number(annual):
        n = float(annual)
        if n < 0:
            return "Снижение условной годовой нагрузки (чувствительность модели)"
        if n == 0:
            return "Нет rate-driven эффекта в этой модели"
        return "Условная годовая чувствительность к изменению ставки"
    return None


def _horizon(*, basis: RatePresentBasis) -> str | None:
    if basis in {"none", "conflict"}:
        return None
    # Annual sensitivity — never label as 90-day effect
    return "Условный годовой горизонт чувствительности (не эффект за 90 дней)"


def present_scenario_dict(
    sc: dict[str, Any],
    *,
    parameters: dict[str, Any] | None = None,
    model_version: str | None = None,
) -> dict[str, Any]:
    """Build presentation for a scenario row (results-shaped dict)."""
    params = parameters
    if params is None and isinstance(sc.get("parameters"), dict):
        params = sc["parameters"]
    return build_finance_scenario_presentation(
        results=sc,
        parameters=params,
        model_version=model_version or (
            str(sc["model_version"]) if isinstance(sc.get("model_version"), str) else None
        ),
        label=sc.get("label") if isinstance(sc.get("label"), str) else None,
    )


def attach_presentation_to_scenarios(
    scenarios: list[dict[str, Any]],
    *,
    parameters: dict[str, Any] | None,
    model_version: str | None = None,
) -> list[dict[str, Any]]:
    """Copy scenarios with additive ``presentation`` (does not mutate formulas)."""
    out: list[dict[str, Any]] = []
    for sc in scenarios:
        if not isinstance(sc, dict):
            continue
        row = dict(sc)
        # Ensure unit from package parameters if row omitted it
        if parameters and row.get("debt_amount_unit") is None:
            unit = parameters.get("debt_amount_unit")
            if isinstance(unit, str):
                row["debt_amount_unit"] = unit
        if parameters and isinstance(parameters.get("rate_change"), dict):
            row.setdefault("parameters", parameters)
        pres = present_scenario_dict(
            row, parameters=parameters, model_version=model_version
        )
        row["presentation"] = pres
        out.append(row)
    return out


def format_presentation_metric_line(
    sc: dict[str, Any],
    *,
    index: int = 0,
    parameters: dict[str, Any] | None = None,
    model_version: str | None = None,
) -> str:
    from app.services.scenario_display import scenario_label

    label = scenario_label(sc, index)
    pres = sc.get("presentation")
    if not isinstance(pres, dict):
        pres = present_scenario_dict(
            sc, parameters=parameters, model_version=model_version
        )
    suffix = pres.get("metric_suffix")
    if isinstance(suffix, str) and suffix.strip():
        return f"• {label}: {suffix}"
    return f"• {label}"
