"""Human-facing assessment explanation — matches stored impact values, never invents history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import Event, EventImpact

EXPOSURE_LABEL = "Доля выпуска, связанная с затронутым узлом"
IMPACT_SCORE_LABEL = "Индекс влияния"
EVENT_SEVERITY_SIGNAL_LABEL = "Сигнал события"
CONFIDENCE_LABEL = "Качество данных"
STOP_RISK_LABEL = "Модельная оценка риска остановки"

SCORE_KIND_COMPANY = "company_calculated"
SCORE_KIND_SEVERITY = "event_severity_signal"
SCORE_KIND_UNAVAILABLE = "unavailable"
SCORE_KIND_CASE_PROFILE = "case_profile_match"

SCORE_KIND_LABELS = {
    SCORE_KIND_COMPANY: IMPACT_SCORE_LABEL,
    SCORE_KIND_SEVERITY: EVENT_SEVERITY_SIGNAL_LABEL,
    SCORE_KIND_CASE_PROFILE: "По профилю компании",
    "industry_profile_match": "По вашим продуктам",
    SCORE_KIND_UNAVAILABLE: "Оценка недоступна",
}

IMPACT_SCORE_MEANING = (
    "Внутренний индекс приоритета от 0 до 100: насколько событие важно разобрать "
    "для этой компании относительно других сигналов. Это не процент потерь и не вероятность убытка."
)
EVENT_SEVERITY_SIGNAL_MEANING = (
    "Предварительный ориентир приоритета по серьёзности события (severity), "
    "без расчёта по финансовым параметрам или доле выпуска компании. "
    "Это не персональный индекс влияния на компанию и не рассчитанный финансовый эффект."
)
CONFIDENCE_MEANING = (
    "Эвристическая оценка качества данных: 0.55×среднее source_quality источников "
    "+ 0.45×среднее confidence рёбер пути (0…1). "
    "При отсутствии источников подставляется default 0.4; при отсутствии рёбер — 0.5. "
    "Это не проверенная точность и не вероятность правильности ответа."
)
EXPOSURE_MEANING = (
    "Доля выпуска компании, приходящаяся на конечный узел найденной цепочки зависимостей. "
    "0 означает известную нулевую долю; отсутствие значения (null) — доля неизвестна или неприменима. "
    "Это не прогноз потери выпуска и не доля уже сорванных поставок."
)
STOP_RISK_MEANING = (
    "Модельный индекс из доли выпуска и покрытия задержки запасами (0…100). "
    "Не статистически проверенная вероятность остановки производства."
)


def score_kind_for_state(assessment_state: str) -> str:
    if assessment_state == "supply_chain_ready":
        return SCORE_KIND_COMPANY
    if assessment_state in {
        "finance_data_required",
        "finance_ready",
        "monitoring_only",
    }:
        return SCORE_KIND_SEVERITY
    # calculation_unavailable and unknown → no numeric score kind
    return SCORE_KIND_UNAVAILABLE


def score_kind_label(score_kind: str) -> str:
    return SCORE_KIND_LABELS.get(score_kind, IMPACT_SCORE_LABEL)


def metric_labels(
    *,
    has_exposure: bool,
    assessment_state: str,
    score_kind: str | None = None,
) -> dict[str, str]:
    kind = score_kind or score_kind_for_state(assessment_state)
    labels = {
        "impact_score": score_kind_label(kind),
        "confidence": CONFIDENCE_LABEL,
    }
    if has_exposure and assessment_state == "supply_chain_ready":
        labels["exposure"] = EXPOSURE_LABEL
    return labels


def _confidence_meaning(detail: dict[str, Any] | None) -> str:
    if not detail:
        return CONFIDENCE_MEANING
    parts = [CONFIDENCE_MEANING]
    if detail.get("source_quality_defaulted"):
        parts.append(
            "Источники события отсутствовали при расчёте — использован default source_quality=0.4."
        )
    if detail.get("edge_confidence_defaulted"):
        parts.append(
            "Рёбра пути отсутствовали при расчёте — использован default edge_confidence=0.5; "
            "качество цепочки связей не измерялось."
        )
    return " ".join(parts)


def build_assessment_basis(
    *,
    assessment_state: str,
    event: Event,
    impact_score: float,
    confidence: float,
    exposure_value: float | None,
    exposure_raw_for_score: float | None,
    path_node_names: list[str],
    formula: str | None,
    display_mode: str | None,
    source_count: int,
    missing_finance_keys: list[str],
    model_version: str,
    computed_at: datetime,
    score_kind: str,
    confidence_detail: dict[str, Any] | None = None,
    demo_score_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Snapshot stored with the score so UI can explain the same numbers later."""
    kind = score_kind or score_kind_for_state(assessment_state)
    score_label = score_kind_label(kind)
    score_meaning = (
        IMPACT_SCORE_MEANING
        if kind == SCORE_KIND_COMPANY
        else EVENT_SEVERITY_SIGNAL_MEANING
    )

    used_event: list[str] = [
        f"Событие: {event.title}",
        f"Категория: {event.category}",
        f"Серьёзность события (severity): {event.severity}",
    ]
    if event.is_demo:
        used_event.append("Тип данных события: демонстрационное (is_demo)")
    if source_count:
        used_event.append(f"Источников в карточке: {source_count}")

    used_company: list[str] = []
    dependencies: list[str] = []
    assumptions: list[str] = []
    missing: list[str] = []
    limitations: list[str] = [
        "Числа оценки не являются финансовым прогнозом или гарантией.",
        "Числа действительны на момент расчёта; после изменения профиля компании нужен пересчёт.",
    ]
    calculation: str | None = None
    metrics: list[dict[str, Any]] = [
        {
            "key": "impact_score",
            "label": score_label,
            "value": impact_score,
            "unit": "index_0_100",
            "meaning": score_meaning,
        },
        {
            "key": "confidence",
            "label": CONFIDENCE_LABEL,
            "value": confidence,
            "unit": "ratio_0_1",
            "meaning": _confidence_meaning(confidence_detail),
        },
    ]

    if assessment_state == "supply_chain_ready":
        if path_node_names:
            dependencies.append(" → ".join(path_node_names))
            used_company.append(
                "Цепочка Digital Twin: " + " → ".join(path_node_names)
            )
        if exposure_value is not None:
            used_company.append(f"{EXPOSURE_LABEL}: {exposure_value:g}%")
            metrics.append(
                {
                    "key": "exposure",
                    "label": EXPOSURE_LABEL,
                    "value": exposure_value,
                    "unit": "percent",
                    "meaning": EXPOSURE_MEANING,
                }
            )
        if formula:
            calculation = (
                f"{score_label}: {formula}. "
                "Вклад exposure — доля выпуска узла (percent), ограниченная сверху 100; "
                "в карточке показывается та же доля."
            )
            if exposure_raw_for_score is not None and exposure_value is not None:
                calculation += (
                    f" Для скоринга использована доля {exposure_raw_for_score:g}% "
                    f"(карточка: {exposure_value:g}%)."
                )
        assumptions.extend(
            [
                "Связи профиля компании отражают реальную зависимость выпуска.",
                "Серьёзность события задана в карточке события (severity).",
            ]
        )
        limitations.append(
            "Доля выпуска описывает связанность с узлом, а не ожидаемый процент потерь."
        )
    elif assessment_state == "finance_data_required":
        calculation = (
            f"Показан «{score_label}»: мягкий ориентир от severity события "
            "(placeholder для ранжирования ленты), а не персональный расчёт влияния "
            "на компанию. Числовые финансовые сценарии недоступны без профиля."
        )
        missing.extend(
            missing_finance_keys
            or [
                "debt_amount",
                "floating_rate_share_percent",
                "fx_exposure_amount",
                "fx_exposure_currency",
                "fx_exposure_direction",
                "fx_quote_currency",
            ]
        )
        limitations.append(
            "Нужны параметры долга и/или одной валютной операции; "
            "ликвидность (90д/резервы) не обязательна для независимого FX."
        )
        limitations.append(
            "Поле impact_score здесь сохранено для совместимости и сортировки ленты; "
            "его нельзя трактовать как рассчитанный индекс влияния на компанию."
        )
    elif assessment_state == "finance_ready":
        calculation = (
            f"«{score_label}» — ориентир от severity события, не полный персональный индекс. "
            "Детальные суммы и давление финансирования считаются отдельным симулятором "
            "по профилю компании."
        )
        used_company.append(
            "Финансовый профиль достаточен хотя бы для одного track (rate и/или FX)."
        )
        assumptions.append(
            "Денежный сценарий требует observed/assumed основания в событии "
            "или явного what-if — не severity."
        )
        limitations.append(
            "Профиль готов ≠ расчёт доступен; без основания события scenarios unavailable."
        )
        limitations.append(
            "impact_score в этом режиме — сигнал события для приоритета, не финансовый эффект."
        )
    else:
        calculation = (
            f"Событие релевантно профилю, но цепочка влияния с известной долей выпуска "
            f"не построена. «{score_label}» — мягкий ориентир от severity для сортировки."
        )
        missing.append("подтверждённая цепочка зависимостей с известной долей выпуска")
        limitations.append(
            "Отсутствие найденной цепочки не означает, что риска нет — только что модель его не связала."
        )
        limitations.append(
            "impact_score здесь — triage-сигнал, не персональный расчёт по компании."
        )

    if display_mode and display_mode != "supply_chain_ready":
        assumptions.append(f"Режим отображения: {display_mode}")

    if confidence_detail:
        if confidence_detail.get("source_quality_defaulted") or confidence_detail.get(
            "edge_confidence_defaulted"
        ):
            assumptions.append(
                "В confidence использованы default-значения (см. meaning метрики) — "
                "это не измеренный факт качества цепочки."
            )

    if demo_score_override and demo_score_override.get("applied"):
        assumptions.append(
            f"Применён явный demo score override "
            f"(множитель {demo_score_override.get('multiplier')})."
        )
        limitations.append(
            "Demo override меняет только демонстрационный расчёт и не является обычной формулой."
        )
    else:
        assumptions.append(
            "Demo score override не применялся — единая формула для demo и real."
        )

    summary = {
        "supply_chain_ready": "Оценка построена по цепочке зависимостей и доле выпуска.",
        "finance_data_required": (
            "Нужен финансовый контекст; показан сигнал события, не персональный расчёт."
        ),
        "finance_ready": (
            "Доступны финансовые сценарии; impact_score — сигнал события, не полный индекс."
        ),
        "monitoring_only": (
            "Пока только мониторинг: численная связь с выпуском не построена; "
            "число в ленте — сигнал события."
        ),
    }.get(assessment_state, "Оценка влияния для компании.")

    return {
        "version": 2,
        "basis_available": True,
        "summary": summary,
        "metrics": metrics,
        "used_event_data": used_event,
        "used_company_data": used_company,
        "dependencies": dependencies,
        "calculation": calculation,
        "assumptions": assumptions,
        "missing_data": missing,
        "limitations": limitations,
        "model_version": model_version,
        "computed_at": computed_at.isoformat().replace("+00:00", "Z"),
        "assessment_state": assessment_state,
        "is_demo_event": bool(event.is_demo),
        "score_kind": kind,
        "score_kind_label": score_label,
        "confidence_detail": confidence_detail or {},
        "demo_score_override": demo_score_override
        or {"applied": False, "multiplier": None, "reason": None},
    }


def explanation_from_impact(
    impact: EventImpact,
    event: Event | None,
) -> dict[str, Any]:
    """Build API explanation from stored basis, or a honest limited fallback for legacy rows."""
    breakdown = impact.score_breakdown_json or {}
    basis = breakdown.get("assessment_basis")
    state = str(
        breakdown.get("assessment_state")
        or (basis or {}).get("assessment_state")
        or "monitoring_only"
    )
    has_exposure = impact.exposure_value is not None
    stored_kind = None
    if isinstance(basis, dict) and basis.get("score_kind"):
        stored_kind = str(basis["score_kind"])
    elif breakdown.get("score_kind"):
        stored_kind = str(breakdown["score_kind"])
    kind = stored_kind or score_kind_for_state(state)

    if isinstance(basis, dict) and basis.get("basis_available") is True:
        return {
            "basis_available": True,
            "summary": basis.get("summary") or "",
            "metrics": basis.get("metrics") or [],
            "used_event_data": basis.get("used_event_data") or [],
            "used_company_data": basis.get("used_company_data") or [],
            "dependencies": basis.get("dependencies") or [],
            "calculation": basis.get("calculation"),
            "assumptions": basis.get("assumptions") or [],
            "missing_data": basis.get("missing_data") or [],
            "limitations": basis.get("limitations") or [],
            "model_version": basis.get("model_version") or impact.model_version,
            "computed_at": basis.get("computed_at")
            or (
                impact.computed_at.isoformat().replace("+00:00", "Z")
                if impact.computed_at
                else None
            ),
            "assessment_state": state,
            "is_demo_event": bool(event.is_demo)
            if event is not None
            else bool(basis.get("is_demo_event")),
            "metric_labels": metric_labels(
                has_exposure=has_exposure,
                assessment_state=state,
                score_kind=kind,
            ),
            "score_kind": kind,
            "score_kind_label": basis.get("score_kind_label") or score_kind_label(kind),
            "confidence_detail": basis.get("confidence_detail") or {},
            "demo_score_override": basis.get("demo_score_override"),
        }

    # Legacy row: do not invent arithmetic history — only definitions + stored values
    score_meaning = (
        IMPACT_SCORE_MEANING
        if kind == SCORE_KIND_COMPANY
        else EVENT_SEVERITY_SIGNAL_MEANING
    )
    metrics = [
        {
            "key": "impact_score",
            "label": score_kind_label(kind),
            "value": impact.impact_score,
            "unit": "index_0_100",
            "meaning": score_meaning,
        },
        {
            "key": "confidence",
            "label": CONFIDENCE_LABEL,
            "value": impact.confidence,
            "unit": "ratio_0_1",
            "meaning": CONFIDENCE_MEANING,
        },
    ]
    if impact.exposure_value is not None:
        metrics.append(
            {
                "key": "exposure",
                "label": impact.exposure_label or EXPOSURE_LABEL,
                "value": impact.exposure_value,
                "unit": impact.exposure_unit or "percent",
                "meaning": EXPOSURE_MEANING,
            }
        )
    return {
        "basis_available": False,
        "summary": (
            "Сохранены числа оценки, но полное основание расчёта для этой записи "
            "не зафиксировано. Ниже — определения метрик и текущие значения; "
            "для актуального объяснения выполните пересчёт влияния."
        ),
        "metrics": metrics,
        "used_event_data": (
            [f"Событие: {event.title}", f"is_demo={event.is_demo}"]
            if event is not None
            else []
        ),
        "used_company_data": [],
        "dependencies": [],
        "calculation": None,
        "assumptions": [],
        "missing_data": ["сохранённое основание расчёта (assessment_basis)"],
        "limitations": [
            "Нельзя утверждать, что объяснение соответствует исходным данным профиля "
            "на момент прошлого расчёта — снимок основания отсутствует.",
            score_meaning,
            CONFIDENCE_MEANING,
        ],
        "model_version": impact.model_version,
        "computed_at": (
            impact.computed_at.isoformat().replace("+00:00", "Z")
            if impact.computed_at
            else None
        ),
        "assessment_state": state,
        "is_demo_event": bool(event.is_demo) if event is not None else False,
        "metric_labels": metric_labels(
            has_exposure=has_exposure,
            assessment_state=state,
            score_kind=kind,
        ),
        "score_kind": kind,
        "score_kind_label": score_kind_label(kind),
        "confidence_detail": {},
        "demo_score_override": None,
    }
