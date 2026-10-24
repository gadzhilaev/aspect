"""Deterministic financial scenarios for macro / FX events — no supplier SolutionCandidate.

Stage 5.2: key-rate monetary sensitivity uses observed or *explicit* assumed Δ (п.п.),
never severity as a hidden rate shock.
Stage 5.4: FX money uses typed currencies/rates (fx_scenario); no severity FX proxy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Event
RateBasis = Literal["observed", "assumed", "none", "conflict"]

# Nested or flat structured decision — only with an explicit trusted status.
_TRUSTED_DECISION_STATUS = frozenset(
    {
        "observed",
        "cb_decision",
        "decision_observed",
        "observed_cb_decision",
    }
)

# Explicitly untrusted as observed Δ (may still appear in attrs for other uses).
_UNTRUSTED_DELTA_KEYS = frozenset(
    {
        "claimed_delta_pp",
        "bank_forecast_end_2027",
        "bank_forecast",
        "demo_story",
        "severity",
    }
)

FINANCE_RATE_MODEL_SUFFIX = "finance-rate-v2"

_EXPECTATION_MARKERS = re.compile(
    r"(ожида\w+|прогноз\w*|вероятн\w*|может\s+сохран|"
    r"мы\s+жд[её]м|банк\s+жд|ожидается\s+сохран)",
    re.IGNORECASE,
)
_PAST_NARRATION = re.compile(
    r"(ранее\s+сохран|в\s+прошлом\s+сохран|прошл\w+\s+решени\w*\s+сохран)",
    re.IGNORECASE,
)
_NEGATED_HOLD = re.compile(
    r"(не\s+сохранил|не\s+оставил|не\s+оставлен|не\s+сохранен)",
    re.IGNORECASE,
)
# Completed-decision holds (verbs / explicit «неизменн*» after leave/keep).
_HOLD_DECISION = re.compile(
    r"("
    r"сохранил[аи]?\s+(?:ключевую\s+)?ставку"
    r"|оставил[аи]?\s+(?:ключевую\s+)?ставку\s+неизменн\w*"
    r"|оставить\s+(?:ключевую\s+)?ставку\s+неизменн\w*"
    r"|ставк[ауие]\s+сохранен[аоы]\w*"
    r"|ставк[ауие]\s+без\s+изменени\w*"
    r"|ключевая\s+ставка\s+сохранен\w*"
    r"|решени\w*\s+оставить\s+ставку\s+неизменн\w*"
    r")",
    re.IGNORECASE,
)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _finance_float(data: dict[str, Any], key: str) -> float | None:
    """Return known float including 0.0; None if key absent/blank/unparseable."""
    if key not in data:
        return None
    return _optional_float(data.get(key))


def _debt_amount_unit(optional_finance: dict[str, Any]) -> str:
    for key in ("debt_amount_unit", "debt_currency", "currency"):
        raw = optional_finance.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip().upper()
    return "unspecified"


@dataclass
class RateChangeResolution:
    basis: RateBasis
    delta_pp: float | None = None
    observed_delta_pp: float | None = None
    assumed_delta_pp: float | None = None
    used_delta_pp: float | None = None
    source: str = ""
    assumptions: list[str] = field(default_factory=list)
    unavailable_reasons: list[str] = field(default_factory=list)
    conflict_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "delta_pp": self.delta_pp,
            "observed_delta_pp": self.observed_delta_pp,
            "assumed_delta_pp": self.assumed_delta_pp,
            "used_delta_pp": self.used_delta_pp,
            "source": self.source,
            "assumptions": list(self.assumptions),
            "unavailable_reasons": list(self.unavailable_reasons),
            "conflict_reasons": list(self.conflict_reasons),
        }


def _structured_rate_block(attrs: dict[str, Any]) -> dict[str, Any] | None:
    nested = attrs.get("key_rate_decision")
    if isinstance(nested, dict):
        return nested
    # Flat trusted keys only when status is present on the event attrs.
    status = attrs.get("rate_decision_status")
    if status in _TRUSTED_DECISION_STATUS:
        return {
            "status": status,
            "rate_from": attrs.get("rate_from"),
            "rate_to": attrs.get("rate_to"),
            "delta_pp": attrs.get("rate_delta_pp"),
        }
    return None


def resolve_observed_rate_change(event: Event) -> RateChangeResolution:
    """Resolve observed key-rate Δ (п.п.) from trusted event structure or hold decision text.

    Does **not** use severity, bank forecasts, or ``claimed_delta_pp``.
    """
    attrs = event.attributes_json if isinstance(event.attributes_json, dict) else {}
    title = (event.title or "").strip()
    summary = (event.summary or "").strip()

    block = _structured_rate_block(attrs)
    if block is not None:
        status = str(block.get("status") or block.get("rate_decision_status") or "").strip()
        if status not in _TRUSTED_DECISION_STATUS:
            return RateChangeResolution(
                basis="none",
                source="attributes_untrusted_status",
                unavailable_reasons=[
                    "Структура ставки без доверенного rate_decision_status "
                    f"(получено {status!r}; claimed_delta_pp и прогнозы не используются)"
                ],
            )
        rate_from = _optional_float(block.get("rate_from"))
        rate_to = _optional_float(block.get("rate_to"))
        delta_given = _optional_float(
            block.get("delta_pp")
            if block.get("delta_pp") is not None
            else block.get("rate_delta_pp")
        )
        # claimed_delta_pp on event attrs is never read here.
        if "claimed_delta_pp" in attrs or "claimed_delta_pp" in block:
            # Ignore; do not treat as observed.
            pass

        if rate_from is not None and rate_to is not None:
            computed = round(rate_to - rate_from, 6)
            if delta_given is not None and abs(computed - delta_given) > 1e-6:
                return RateChangeResolution(
                    basis="conflict",
                    source="rate_from_to_vs_delta",
                    observed_delta_pp=None,
                    conflict_reasons=[
                        f"rate_to - rate_from = {computed}, но rate_delta_pp = {delta_given}"
                    ],
                    unavailable_reasons=["Конфликт структурированных полей ставки"],
                )
            return RateChangeResolution(
                basis="observed",
                delta_pp=computed,
                observed_delta_pp=computed,
                source="attributes.key_rate_decision",
                assumptions=[
                    "observed delta — изменение ключевой ставки (п.п.), "
                    "не наблюдаемое изменение расходов компании",
                ],
            )
        if delta_given is not None and rate_from is None and rate_to is None:
            # Explicit trusted delta without from/to pair.
            return RateChangeResolution(
                basis="observed",
                delta_pp=delta_given,
                observed_delta_pp=delta_given,
                source="attributes.rate_delta_pp",
                assumptions=[
                    "observed delta из доверенного rate_delta_pp при status=observed",
                    "не является фактом изменения расходов компании",
                ],
            )
        if rate_from is not None or rate_to is not None:
            return RateChangeResolution(
                basis="none",
                source="attributes_incomplete_pair",
                unavailable_reasons=[
                    "Нужны оба rate_from и rate_to (или только согласованный rate_delta_pp)"
                ],
            )

    # Numbers without trusted status are not observed.
    if any(k in attrs for k in ("rate_from", "rate_to", "rate_delta_pp")) and (
        attrs.get("rate_decision_status") not in _TRUSTED_DECISION_STATUS
    ):
        if not isinstance(attrs.get("key_rate_decision"), dict):
            return RateChangeResolution(
                basis="none",
                source="attributes_numbers_without_status",
                unavailable_reasons=[
                    "rate_from/rate_to/rate_delta_pp без rate_decision_status "
                    "не считаются observed"
                ],
            )

    hold = _text_indicates_hold_decision(title, summary)
    if hold is True:
        return RateChangeResolution(
            basis="observed",
            delta_pp=0.0,
            observed_delta_pp=0.0,
            source="event_text_hold_decision",
            assumptions=[
                "По тексту зафиксировано решение о сохранении ставки (Δ = 0 п.п.)",
                "Это не означает отсутствие прочих финансовых рисков",
            ],
        )
    if hold is False:
        # Explicitly rejected as hold (expectation / negation) — still no observed Δ.
        return RateChangeResolution(
            basis="none",
            source="event_text_not_reliable_hold",
            unavailable_reasons=[
                "Текст похож на ожидание/отрицание/пересказ, а не на надёжный факт решения"
            ],
        )

    return RateChangeResolution(
        basis="none",
        source="no_trusted_rate_decision",
        unavailable_reasons=[
            "Нет доверенного observed изменения ключевой ставки "
            "(severity и прогноз банка не используются как Δ)"
        ],
    )


def _text_indicates_hold_decision(title: str, summary: str) -> bool | None:
    """True = observed hold, False = explicitly unreliable, None = no signal."""
    # Prefer title; fall back to summary first sentence only (not whole blob search).
    primary = title
    first_summary = summary.split(".")[0].strip() if summary else ""
    candidates = [t for t in (primary, first_summary) if t]
    if not candidates:
        return None

    saw_hold_pattern = False
    for text in candidates:
        if _NEGATED_HOLD.search(text):
            return False
        if _EXPECTATION_MARKERS.search(text):
            # Expectation in the same short window → not observed decision.
            if _HOLD_DECISION.search(text) or re.search(
                r"сохранен\w*\s+(?:ключевой\s+)?ставк", text, re.IGNORECASE
            ):
                return False
            continue
        if _PAST_NARRATION.search(text):
            return False
        if _HOLD_DECISION.search(text):
            saw_hold_pattern = True
            continue
        # Noun-phrase title «Сохранение ключевой ставки» — only if no expectation markers.
        if re.search(r"сохранение\s+ключевой\s+ставки", text, re.IGNORECASE):
            if _EXPECTATION_MARKERS.search(text):
                return False
            saw_hold_pattern = True
    if saw_hold_pattern:
        return True
    return None


def resolve_rate_change_for_scenario(
    event: Event,
    *,
    assumed_rate_change_pp: float | None = None,
) -> RateChangeResolution:
    """Combine observed resolution with an optional explicit what-if assumed Δ."""
    observed = resolve_observed_rate_change(event)
    assumed = (
        float(assumed_rate_change_pp)
        if assumed_rate_change_pp is not None
        else None
    )

    if observed.basis == "conflict":
        out = RateChangeResolution(
            basis="conflict",
            observed_delta_pp=observed.observed_delta_pp,
            assumed_delta_pp=assumed,
            source=observed.source,
            conflict_reasons=list(observed.conflict_reasons),
            unavailable_reasons=list(observed.unavailable_reasons),
            assumptions=list(observed.assumptions),
        )
        return out

    if observed.basis == "observed":
        if assumed is not None:
            # Keep both; caller chooses used_delta per scenario row.
            return RateChangeResolution(
                basis="observed",
                delta_pp=observed.delta_pp,
                observed_delta_pp=observed.observed_delta_pp,
                assumed_delta_pp=assumed,
                used_delta_pp=observed.delta_pp,
                source=observed.source,
                assumptions=[
                    *observed.assumptions,
                    f"Отдельно задан what-if assumed_rate_change_pp={assumed}",
                    "Факт observed не перезаписывается допущением",
                ],
                unavailable_reasons=list(observed.unavailable_reasons),
            )
        return RateChangeResolution(
            basis="observed",
            delta_pp=observed.delta_pp,
            observed_delta_pp=observed.observed_delta_pp,
            assumed_delta_pp=None,
            used_delta_pp=observed.delta_pp,
            source=observed.source,
            assumptions=list(observed.assumptions),
        )

    # observed none
    if assumed is not None:
        return RateChangeResolution(
            basis="assumed",
            delta_pp=assumed,
            observed_delta_pp=None,
            assumed_delta_pp=assumed,
            used_delta_pp=assumed,
            source="explicit_assumed_rate_change_pp",
            assumptions=[
                f"What-if: изменение ключевой ставки на {assumed} п.п. задано явно",
                "Это допущение сценария, не факт новости и не прогноз банка",
            ],
            unavailable_reasons=list(observed.unavailable_reasons),
        )

    return RateChangeResolution(
        basis="none",
        source=observed.source or "no_rate_delta",
        unavailable_reasons=[
            *observed.unavailable_reasons,
            "Нет observed Δ и не задан явный assumed_rate_change_pp",
        ],
    )


def _annual_rate_sensitivity(
    *,
    debt: float,
    floating_share: float,
    delta_pp: float,
) -> float:
    """Conditional annual interest sensitivity: debt × floating × (Δп.п. / 100)."""
    return round(debt * floating_share * (delta_pp / 100.0), 2)


def _scenario_row(
    *,
    kind: str,
    label: str,
    action_id: str | None,
    used_basis: RateBasis,
    used_delta_pp: float,
    annual: float | None,
    debt_unit: str,
    assumptions: list[str],
    funding_pressure_percent: float | None = None,
) -> dict[str, Any]:
    # Negative Δ → relief (negative sensitivity), not «дополнительная нагрузка»
    row: dict[str, Any] = {
        "kind": kind,
        "label": label,
        "rate_change_basis": used_basis,
        "rate_change_delta_pp": used_delta_pp,
        "annual_rate_sensitivity": annual,
        "extra_annual_cost": annual,  # compat; interpret via basis + sign
        "annual_metric_kind": "annual_rate_sensitivity",
        "debt_amount_unit": debt_unit,
        "track": "rate",
        "near_term_pressure": None,
        "near_term_pressure_status": "unavailable_not_severity_proxy",
        "fx_exposure_index": None,
        "fx_exposure_status": "see_fx_track",
        "funding_pressure_percent": funding_pressure_percent,
        "funding_pressure_status": (
            "unavailable_severity_proxy_removed"
            if funding_pressure_percent is None
            else "model_index_optional"
        ),
        "assumptions": assumptions,
        "labels": ["estimate"],
        "is_estimate": True,
    }
    if action_id:
        row["action_id"] = action_id
    if used_basis == "assumed":
        row["shock_framing"] = (
            f"При допущении изменения ставки на {used_delta_pp:g} п.п."
        )
    elif used_basis == "observed":
        row["shock_framing"] = (
            f"Факт изменения ключевой ставки: {used_delta_pp:g} п.п.; "
            "денежная метрика — условная годовая чувствительность при допущении "
            "переноса на плавающую долю долга (без дат пересмотра)"
        )
    return row


def _simulate_rate_scenarios(
    *,
    event: Event,
    optional_finance: dict[str, Any],
    assumed_rate_change_pp: float | None = None,
) -> dict[str, Any]:
    """Key-rate track only (stage 5.2 formulas unchanged)."""
    settings = get_settings()
    model_version = f"{settings.simulator_model_version}-{FINANCE_RATE_MODEL_SUFFIX}"
    computed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    debt = _finance_float(optional_finance, "debt_amount")
    floating = _finance_float(optional_finance, "floating_rate_share_percent")
    if debt is None or floating is None:
        rate = resolve_rate_change_for_scenario(
            event, assumed_rate_change_pp=assumed_rate_change_pp
        )
        return {
            "source": "financial_calculation",
            "track": "rate",
            "status": "unavailable",
            "type": "missing_data",
            "model_version": model_version,
            "computed_at": computed_at,
            "is_estimate": True,
            "labels": ["estimate"],
            "message": "Неизвестны сумма долга или доля плавающей ставки — денежный эффект недоступен",
            "fields": [
                k
                for k, v in (
                    ("debt_amount", debt),
                    ("floating_rate_share_percent", floating),
                )
                if v is None
            ],
            "parameters": {
                "debt_amount": debt,
                "debt_amount_unit": _debt_amount_unit(optional_finance),
                "floating_rate_share_percent": floating,
                "rate_change": rate.to_dict(),
                "model_version": model_version,
            },
            "scenarios": [],
        }

    debt_f = float(debt)
    floating_f = float(floating)
    floating_share = max(0.0, min(100.0, floating_f)) / 100.0
    debt_unit = _debt_amount_unit(optional_finance)

    rate = resolve_rate_change_for_scenario(
        event, assumed_rate_change_pp=assumed_rate_change_pp
    )

    base_params: dict[str, Any] = {
        "debt_amount": debt_f,
        "debt_amount_unit": debt_unit,
        "floating_rate_share_percent": floating_f,
        "near_term_payments_90d": _finance_float(
            optional_finance, "near_term_payments_90d"
        ),
        "fx_purchase_volume": _finance_float(optional_finance, "fx_purchase_volume"),
        "cash_reserve_days": _finance_float(optional_finance, "cash_reserve_days"),
        "rate_change": rate.to_dict(),
        "model_version": model_version,
        "shock_proxy_pp": None,
        "severity_used_as_rate_shock": False,
    }

    if rate.basis == "conflict":
        return {
            "source": "financial_calculation",
            "track": "rate",
            "status": "unavailable",
            "type": "missing_data",
            "model_version": model_version,
            "computed_at": computed_at,
            "is_estimate": True,
            "labels": ["estimate"],
            "message": "Конфликт данных об изменении ключевой ставки",
            "fields": ["rate_change"],
            "parameters": base_params,
            "scenarios": [],
            "assessment_hint": "finance_ready",
        }

    if rate.basis == "none" or rate.used_delta_pp is None:
        return {
            "source": "financial_calculation",
            "track": "rate",
            "status": "unavailable",
            "type": "missing_data",
            "model_version": model_version,
            "computed_at": computed_at,
            "is_estimate": True,
            "labels": ["estimate"],
            "message": (
                "Изменение ключевой ставки неизвестно: нет observed Δ и не задан "
                "явный what-if (assumed_rate_change_pp). Severity не заменяет Δ."
            ),
            "fields": ["rate_change_observed_or_assumed"],
            "parameters": base_params,
            "scenarios": [],
            "assessment_hint": "finance_ready",
        }

    baseline_delta = (
        float(rate.observed_delta_pp)
        if rate.observed_delta_pp is not None and rate.basis == "observed"
        else float(rate.used_delta_pp)
    )
    baseline_basis: RateBasis = (
        "observed" if rate.observed_delta_pp is not None and rate.basis == "observed" else "assumed"
    )
    baseline_annual = _annual_rate_sensitivity(
        debt=debt_f, floating_share=floating_share, delta_pp=baseline_delta
    )

    common_assumptions = [
        "Денежная метрика — условная годовая чувствительность процентных расходов "
        "при допущении переноса Δ ставки на плавающую долю долга",
        "Без дат пересмотра кредита не утверждается немедленный эффект или факт расхода за 90 дней",
        "Оценка, не финансовая гарантия",
        "Смешанные near-term деньги от severity отключены; FX — отдельный track (5.4)",
    ]
    if debt_unit == "unspecified":
        common_assumptions.append(
            "Единица debt_amount не подтверждена как ₽ — суммы в единицах введённого долга"
        )

    baseline = _scenario_row(
        kind="baseline",
        label="Без действий",
        action_id=None,
        used_basis=baseline_basis,
        used_delta_pp=baseline_delta,
        annual=baseline_annual,
        debt_unit=debt_unit,
        assumptions=[
            *rate.assumptions,
            *common_assumptions,
            "Коэффициенты альтернатив — условия модели, не доказанная эффективность действия",
        ],
        funding_pressure_percent=None,
    )

    scenarios: list[dict[str, Any]] = [baseline]

    if (
        rate.assumed_delta_pp is not None
        and rate.observed_delta_pp is not None
        and abs(float(rate.assumed_delta_pp) - float(rate.observed_delta_pp)) > 1e-9
    ):
        assumed_annual = _annual_rate_sensitivity(
            debt=debt_f,
            floating_share=floating_share,
            delta_pp=float(rate.assumed_delta_pp),
        )
        scenarios.append(
            _scenario_row(
                kind="alternative",
                label=f"What-if: ставка {float(rate.assumed_delta_pp):+g} п.п.",
                action_id="assumed_rate_shock",
                used_basis="assumed",
                used_delta_pp=float(rate.assumed_delta_pp),
                annual=assumed_annual,
                debt_unit=debt_unit,
                assumptions=[
                    f"Явное допущение assumed_rate_change_pp={rate.assumed_delta_pp}",
                    f"Observed Δ={rate.observed_delta_pp} п.п. сохранена отдельно",
                    *common_assumptions,
                ],
            )
        )

    # FX-reduction is a personal action only with confirmed typed FX exposure.
    # Without it, keep a package-level hypothesis note — never a selectable Scenario.
    from app.services.fx_scenario import has_fx_exposure_context

    include_reduce_fx = has_fx_exposure_context(optional_finance)
    if include_reduce_fx:
        reduce_fx = _scenario_row(
            kind="alternative",
            label="Снизить валютную экспозицию",
            action_id="reduce_fx_exposure",
            used_basis=baseline_basis,
            used_delta_pp=baseline_delta,
            annual=baseline_annual,
            debt_unit=debt_unit,
            assumptions=[
                "Действие: снижение валютной экспозиции — условие модели (эффективность не доказана)",
                "Rate-sensitivity без изменения; денежный FX — в track=fx при наличии оснований",
                *common_assumptions,
            ],
        )
        reduce_fx["cost_delta_percent"] = 1.5
        scenarios.append(reduce_fx)

    refinance_annual = round(baseline_annual * 0.45, 2)
    refinance = _scenario_row(
        kind="alternative",
        label="Пересмотреть финансирование",
        action_id="review_financing",
        used_basis=baseline_basis,
        used_delta_pp=baseline_delta,
        annual=refinance_annual,
        debt_unit=debt_unit,
        assumptions=[
            "Действие: доля плавающей ставки снижается (коэффициент модели 0.45) — не гарантия рынка",
            *common_assumptions,
        ],
    )
    refinance["cost_delta_percent"] = 0.8
    scenarios.append(refinance)

    params = {
        **base_params,
        "rate_change": {
            **rate.to_dict(),
            "used_delta_pp": baseline_delta,
            "baseline_basis": baseline_basis,
        },
    }
    if not include_reduce_fx:
        params["omitted_action_hypotheses"] = [
            {
                "action_id": "reduce_fx_exposure",
                "label": "Снизить валютную экспозицию",
                "kind": "general_model_hypothesis",
                "reason": "no_confirmed_fx_exposure",
                "note": (
                    "Общая гипотеза модели, не персональный расчётный сценарий: "
                    "в профиле нет подтверждённой валютной экспозиции."
                ),
            }
        ]

    return {
        "source": "financial_calculation",
        "track": "rate",
        "status": "ok",
        "model_version": model_version,
        "computed_at": computed_at,
        "is_estimate": True,
        "labels": ["estimate"],
        "parameters": params,
        "scenarios": scenarios,
    }


def simulate_financial_scenarios(
    *,
    event: Event,
    optional_finance: dict[str, Any],
    assumed_rate_change_pp: float | None = None,
    assumed_fx_change_percent: float | None = None,
) -> dict[str, Any]:
    """Package rate (5.2) and FX (5.4) tracks. Severity never drives money Δ.

    Pure FX does not require debt/floating. Rate track still needs debt + floating.
    Assessment ``has_finance_context`` means rate-or-FX profile readiness (5.5).
    """
    from app.services.fx_scenario import has_fx_exposure_context, simulate_fx_scenarios

    settings = get_settings()
    has_rate_keys = (
        _finance_float(optional_finance, "debt_amount") is not None
        and _finance_float(optional_finance, "floating_rate_share_percent") is not None
    )
    has_fx = has_fx_exposure_context(optional_finance)

    if not has_rate_keys and not has_fx:
        missing = [
            k
            for k in (
                "debt_amount",
                "floating_rate_share_percent",
                "fx_exposure_amount",
                "fx_exposure_currency",
                "fx_exposure_direction",
                "fx_quote_currency",
            )
            if optional_finance.get(k) in (None, "")
        ]
        raise AppError(
            "INSUFFICIENT_DATA",
            "Недостаточно финансовых данных для расчёта",
            422,
            details=[{"field": f, "reason": "required"} for f in missing],
        )

    rate_pkg = (
        _simulate_rate_scenarios(
            event=event,
            optional_finance=optional_finance,
            assumed_rate_change_pp=assumed_rate_change_pp,
        )
        if has_rate_keys
        else {
            "source": "financial_calculation",
            "track": "rate",
            "status": "unavailable",
            "type": "missing_data",
            "message": "Rate-track недоступен без долга и плавающей доли",
            "fields": ["debt_amount", "floating_rate_share_percent"],
            "parameters": {},
            "scenarios": [],
            "model_version": f"{settings.simulator_model_version}-{FINANCE_RATE_MODEL_SUFFIX}",
        }
    )

    fx_pkg = simulate_fx_scenarios(
        event=event,
        optional_finance=optional_finance,
        assumed_fx_change_percent=assumed_fx_change_percent,
    )

    rate_ok = rate_pkg.get("status") == "ok" and bool(rate_pkg.get("scenarios"))
    fx_ok = fx_pkg.get("status") == "ok" and bool(fx_pkg.get("scenarios"))

    merged_params: dict[str, Any] = {}
    if isinstance(rate_pkg.get("parameters"), dict):
        merged_params.update(rate_pkg["parameters"])
    if isinstance(fx_pkg.get("parameters"), dict):
        merged_params["fx"] = fx_pkg["parameters"]
        fc = fx_pkg["parameters"].get("fx_change")
        if isinstance(fc, dict):
            merged_params["fx_change"] = fc
        fe = fx_pkg["parameters"].get("fx_exposure")
        if isinstance(fe, dict):
            merged_params["fx_exposure"] = fe

    scenarios: list[dict[str, Any]] = []
    if rate_ok:
        scenarios.extend(list(rate_pkg.get("scenarios") or []))
    if fx_ok:
        scenarios.extend(list(fx_pkg.get("scenarios") or []))

    model_version = (
        f"{settings.simulator_model_version}-finance-rate-v2+fx-v1"
        if rate_ok and fx_ok
        else (
            str(fx_pkg.get("model_version"))
            if fx_ok
            else str(rate_pkg.get("model_version") or settings.simulator_model_version)
        )
    )
    computed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if not scenarios:
        # Prefer FX message when only FX was attempted with typed fields; else rate.
        msg = None
        fields: list[Any] = []
        if has_fx and not fx_ok:
            msg = fx_pkg.get("message")
            fields = list(fx_pkg.get("fields") or [])
        if has_rate_keys and not rate_ok:
            msg = msg or rate_pkg.get("message")
            fields = fields or list(rate_pkg.get("fields") or [])
        return {
            "source": "financial_calculation",
            "status": "unavailable",
            "type": "missing_data",
            "model_version": model_version,
            "computed_at": computed_at,
            "is_estimate": True,
            "labels": ["estimate"],
            "message": msg or "Недостаточно оснований для денежного сценария",
            "fields": fields or ["rate_or_fx_basis"],
            "parameters": merged_params,
            "rate_status": rate_pkg.get("status"),
            "fx_status": fx_pkg.get("status"),
            "scenarios": [],
            "assessment_hint": "finance_ready",
        }

    return {
        "source": "financial_calculation",
        "status": "ok",
        "model_version": model_version,
        "computed_at": computed_at,
        "is_estimate": True,
        "labels": ["estimate"],
        "parameters": merged_params,
        "rate_status": rate_pkg.get("status"),
        "fx_status": fx_pkg.get("status"),
        "scenarios": scenarios,
    }


def legacy_rate_basis_from_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    """Safe read for old Scenario.parameters_json — never invent observed."""
    params = parameters or {}
    if isinstance(params.get("rate_change"), dict):
        return dict(params["rate_change"])
    # Pre-5.2 rows may have shock_proxy_pp from severity — treat as legacy assumed unknown.
    if params.get("shock_proxy_pp") is not None:
        return {
            "basis": "assumed",
            "delta_pp": None,
            "observed_delta_pp": None,
            "assumed_delta_pp": None,
            "used_delta_pp": None,
            "source": "legacy_shock_proxy_pp",
            "assumptions": [
                "Legacy сценарий: shock_proxy_pp от severity; не интерпретировать как observed"
            ],
            "unavailable_reasons": ["Основание до этапа 5.2 не типизировано"],
            "conflict_reasons": [],
            "legacy": True,
        }
    return {
        "basis": "none",
        "delta_pp": None,
        "observed_delta_pp": None,
        "assumed_delta_pp": None,
        "used_delta_pp": None,
        "source": "legacy_missing",
        "assumptions": [],
        "unavailable_reasons": ["Нет полей rate_change в сохранённом сценарии"],
        "conflict_reasons": [],
        "legacy": True,
    }
