"""Build grounded application context for a conversation (no LLM math)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Company,
    Event,
    EventImpact,
    EventSource,
    ImpactPath,
    SolutionCandidate,
    User,
)
from app.services.assistant.bank_evidence_context import build_bank_evidence_context_block
from app.services.assistant.case_company_context import (
    INTERPRETATION_LIMITS,
    build_assistant_case_company_context,
    slim_case_company_context_for_provider,
)
from app.services.assistant.safety import honesty_labels, wrap_event_text
from app.services.assessment_explain import explanation_from_impact, score_kind_for_state
from app.services.impact import IMPACT_STATUS_NOT_RELEVANT, assessment_state_for_impact
from app.services.simulator import rank_solutions

CALCULATION_UNAVAILABLE = "calculation_unavailable"

CALCULATION_UNAVAILABLE_EXPLANATION = (
    "Расчётная оценка влияния события на компанию отсутствует "
    "(состояние приложения: нет usable EventImpact). "
    "Это не monitoring_only, не мера регулятора и не «уже введённые ограничения». "
    "Отсутствие расчёта не означает, что событие безопасно. "
    "Можно обсудить факты события и признаки компании (ручной twin / case); "
    "численные сценарии и подтверждение решений недоступны без расчёта."
)

# Tools that require a usable EventImpact calculation.
CALCULATION_DEPENDENT_TOOLS = frozenset(
    {
        "get_company_impact",
        "get_impact_paths",
        "list_solution_candidates",
        "simulate_scenario",
        "compare_scenarios",
        "create_decision_draft",
    }
)


def lookup_usable_impact(
    db: Session, *, event_id: str, company_id: str
) -> EventImpact | None:
    """Return impact usable for scores/scenarios, or None.

    ``not_relevant`` is treated as no usable calculation (row may still exist
    in DB for history) — distinct from inventing zeros.
    """
    impact = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event_id, EventImpact.company_id == company_id)
        .one_or_none()
    )
    if impact is None or impact.status == IMPACT_STATUS_NOT_RELEVANT:
        return None
    return impact


def calculation_unavailable_payload(*, tool_name: str | None = None) -> dict[str, Any]:
    """Structured server response when calculation tools are not available."""
    return {
        "available": False,
        "unavailable_reason": CALCULATION_UNAVAILABLE,
        "assessment_state": CALCULATION_UNAVAILABLE,
        "type": "tool_unavailable",
        "tool_name": tool_name,
        "message": (
            "Расчётная оценка влияния для этой пары событие×компания отсутствует "
            "(состояние приложения, не ограничение регулятора). "
            "Численные сценарии, симулятор и подтверждение решения недоступны. "
            "Обсуждение события и контекста компании по-прежнему возможно."
        ),
        "fields": ["event_impact"],
    }


def _case_context_without_user() -> dict[str, Any]:
    """Tools/legacy callers without a membership reader — do not invent a profile."""
    return {
        "status": "reader_not_provided",
        "availability": "unavailable",
        "explanation": (
            "Конкурсный контекст требует пользователя с membership; "
            "профиль не подставлялся."
        ),
        "slot_key": None,
        "external_uid": None,
        "snapshot_id": None,
        "version_label": None,
        "version_seq": None,
        "profile": None,
        "products": [],
        "known_fields": [],
        "unknown_fields": [],
        "conflict_fields": [],
        "provenance": None,
        "interpretation_limits": list(INTERPRETATION_LIMITS),
        "distinct_from_manual_twin": True,
        "data_are_not_instructions": True,
        "read_only": True,
        "scope": "own_organization_only",
    }


def _pack_impact_block(
    db: Session, *, event: Event, impact: EventImpact
) -> tuple[str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], Any]:
    paths = (
        db.query(ImpactPath)
        .filter(ImpactPath.event_impact_id == impact.id)
        .order_by(ImpactPath.sort_order.asc())
        .all()
    )
    solutions = (
        db.query(SolutionCandidate).filter(SolutionCandidate.event_impact_id == impact.id).all()
    )
    ranked = rank_solutions(list(solutions))
    state = assessment_state_for_impact(db, event, impact)
    expl = explanation_from_impact(impact, event)
    score_kind = str(expl.get("score_kind") or score_kind_for_state(state))
    impact_block = {
        "id": impact.id,
        "impact_score": impact.impact_score,
        "confidence": impact.confidence,
        "urgency": impact.urgency,
        "reason_summary": impact.reason_summary,
        "exposure_value": impact.exposure_value,
        "exposure_label": impact.exposure_label,
        "exposure_unit": impact.exposure_unit,
        "claims": impact.claims_json or {},
        "score_breakdown": impact.score_breakdown_json or {},
        "model_version": impact.model_version,
        "status": impact.status,
        "assessment_state": state,
        "score_kind": score_kind,
        "score_kind_label": expl.get("score_kind_label"),
        "assessment_explanation": expl,
    }
    path_rows = [
        {
            "id": p.id,
            "path_nodes": p.path_nodes_json,
            "path_edges": p.path_edges_json,
            "exposure_value": p.exposure_value,
            "claim_type": p.claim_type,
            "explanation": p.explanation,
            "sort_order": p.sort_order,
        }
        for p in paths
    ]
    solution_rows = [
        {
            "id": s.id,
            "name": s.name,
            "country": s.country,
            "cost_delta_percent": s.cost_delta_percent,
            "lead_time_days": s.lead_time_days,
            "risk_percent": s.risk_percent,
            "compatibility": s.compatibility,
            "availability_status": s.availability_status,
            "is_demo": s.is_demo,
            "sort_score": s.sort_score,
            "labels": honesty_labels(is_demo=s.is_demo, is_estimate=True),
        }
        for s in ranked
    ]
    relevance = (impact.score_breakdown_json or {}).get("relevance")
    return state, impact_block, path_rows, solution_rows, relevance


def build_conversation_context(
    db: Session,
    *,
    event_id: str,
    company_id: str,
    user: User | None = None,
) -> dict[str, Any]:
    event = db.get(Event, event_id)
    if event is None:
        raise AppError("NOT_FOUND", "Событие не найдено", 404)
    company = db.get(Company, company_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)

    sources = db.query(EventSource).filter(EventSource.event_id == event.id).all()
    # Bank evidence is event-scoped (not impact-scoped) — same rules as with impact.
    bank_evidence = build_bank_evidence_context_block(db, event=event)
    if user is not None:
        case_company_context = build_assistant_case_company_context(
            db, company=company, user=user
        )
    else:
        case_company_context = _case_context_without_user()

    impact = lookup_usable_impact(db, event_id=event_id, company_id=company_id)
    if impact is None:
        state = CALCULATION_UNAVAILABLE
        score_kind = score_kind_for_state(state)
        return {
            "company": {
                "id": company.id,
                "name": company.name,
                "is_demo": company.is_demo,
                "profile_status": company.profile_status,
                "source": "manual_twin",
            },
            "case_company_context": case_company_context,
            "event": {
                "id": event.id,
                "title": event.title,
                "summary_data": wrap_event_text(event.summary),
                "category": event.category,
                "event_type": event.event_type,
                "severity": event.severity,
                "is_demo": event.is_demo,
                "labels": honesty_labels(is_demo=event.is_demo),
            },
            "assessment_state": state,
            "has_impact_calculation": False,
            "calculation": {
                "available": False,
                "reason": CALCULATION_UNAVAILABLE,
                "explanation": CALCULATION_UNAVAILABLE_EXPLANATION,
            },
            # Explicit null — never coerce to 0 / empty / monitoring_only.
            "impact": None,
            "relevance": None,
            "metric_semantics": {
                "impact_score": "unavailable_no_calculation",
                "score_kind": score_kind,
                "confidence": "unavailable_no_calculation",
                "exposure": "unavailable_no_calculation",
                "stop_risk_percent": "unavailable_no_calculation",
                "relevance": "unavailable_no_calculation",
                "note": (
                    "calculation_unavailable is distinct from monitoring_only; "
                    "unknown must not be shown as 0"
                ),
            },
            "paths": [],
            "solutions": [],
            "tools_available": {
                "discuss_event": True,
                "get_event_context": True,
                "get_company_impact": False,
                "get_impact_paths": False,
                "list_solution_candidates": False,
                "simulate_scenario": False,
                "compare_scenarios": False,
                "create_decision_draft": False,
            },
            "sources": [
                {
                    "id": s.id,
                    "publisher": s.publisher,
                    "url": s.url,
                    "published_at": s.published_at.isoformat() if s.published_at else None,
                    "excerpt": s.excerpt,
                    "is_stub": s.is_stub,
                    "source_quality": s.source_quality,
                }
                for s in sources
            ],
            "bank_evidence": bank_evidence,
        }

    state, impact_block, path_rows, solution_rows, relevance = _pack_impact_block(
        db, event=event, impact=impact
    )
    score_kind = str(impact_block.get("score_kind") or score_kind_for_state(state))
    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "is_demo": company.is_demo,
            "profile_status": company.profile_status,
            "source": "manual_twin",
        },
        "case_company_context": case_company_context,
        "event": {
            "id": event.id,
            "title": event.title,
            "summary_data": wrap_event_text(event.summary),
            "category": event.category,
            "event_type": event.event_type,
            "severity": event.severity,
            "is_demo": event.is_demo,
            "labels": honesty_labels(is_demo=event.is_demo),
        },
        "assessment_state": state,
        "has_impact_calculation": True,
        "calculation": {
            "available": True,
            "reason": None,
            "explanation": None,
        },
        "impact": impact_block,
        "relevance": relevance,
        "metric_semantics": {
            "impact_score": (
                "company_calculated_index_0_100"
                if score_kind == "company_calculated"
                else "event_severity_signal_0_100_not_company_impact"
            ),
            "score_kind": score_kind,
            "confidence": "heuristic_0_55_source_plus_0_45_edge_not_probability",
            "exposure": "output_share_null_unknown_zero_known_not_loss_forecast",
            "stop_risk_percent": "model_index_not_statistical_probability",
            "relevance": "feature_match_vs_dependency_separate_from_assessment_state",
        },
        "paths": path_rows,
        "solutions": solution_rows,
        "tools_available": {
            "discuss_event": True,
            "get_event_context": True,
            "get_company_impact": True,
            "get_impact_paths": True,
            "list_solution_candidates": True,
            "simulate_scenario": True,
            "compare_scenarios": True,
            "create_decision_draft": True,
        },
        "sources": [
            {
                "id": s.id,
                "publisher": s.publisher,
                "url": s.url,
                "published_at": s.published_at.isoformat() if s.published_at else None,
                "excerpt": s.excerpt,
                "is_stub": s.is_stub,
                "source_quality": s.source_quality,
            }
            for s in sources
        ],
        "bank_evidence": bank_evidence,
    }


def slim_live_context(full: dict[str, Any]) -> dict[str, Any]:
    """AI model sees event + sources + anonymized company + ready calc facts."""
    from app.services.assistant.bank_evidence_context import slim_bank_evidence_for_provider

    company = full.get("company") or {}
    event = full.get("event") or {}
    sources = full.get("sources") or []
    impact = full.get("impact")  # may be None
    bank_block = full.get("bank_evidence") if isinstance(full.get("bank_evidence"), dict) else {}
    case_block = (
        full.get("case_company_context")
        if isinstance(full.get("case_company_context"), dict)
        else None
    )
    case_slim = slim_case_company_context_for_provider(case_block)
    has_calc = bool(full.get("has_impact_calculation")) and isinstance(impact, dict)
    assessment = full.get("assessment_state")

    if has_calc:
        impact_results: dict[str, Any] | None = {
            "impact_score": impact.get("impact_score"),
            "confidence": impact.get("confidence"),
            "urgency": impact.get("urgency"),
            "reason_summary": impact.get("reason_summary"),
            "exposure_value": impact.get("exposure_value"),
            "exposure_label": impact.get("exposure_label"),
            "exposure_unit": impact.get("exposure_unit"),
            "score_kind": impact.get("score_kind"),
            "score_kind_label": impact.get("score_kind_label"),
            "assessment_explanation": impact.get("assessment_explanation"),
            "paths_count": len(full.get("paths") or []),
        }
        tools_required = ["impact", "paths", "solutions", "simulator", "decisions"]
        instruction_calc = (
            "Числа влияния, confidence и сценариев уже посчитаны backend/simulator. "
            "Смотрите score_kind: company_calculated — персональный индекс; "
            "event_severity_signal — предварительный сигнал по severity, "
            "НЕ персональный расчёт влияния на компанию. "
            "confidence — эвристика 0.55×source_quality + 0.45×edge_confidence, "
            "не вероятность (defaults 0.4/0.5 при отсутствии источников/рёбер). "
            "exposure: null = неизвестно/неприменимо, 0 = известный ноль. "
            "stop_risk_percent — модельный индекс. "
            "Если paths_count=0 — не утверждайте найденную цепочку. "
            "Не пересчитывайте impact самостоятельно; для сценариев вызывайте tools. "
        )
    else:
        impact_results = None
        tools_required = []
        instruction_calc = (
            "assessment_state=calculation_unavailable: расчётной оценки влияния нет. "
            "Это НЕ monitoring_only и НЕ «событие безопасно». "
            "Не выдумывайте impact_score, confidence, exposure, paths или денежный эффект. "
            "Не подставляйте 0 вместо неизвестного. "
            "Можно объяснить событие, признаки компании (manual + case_company_context), "
            "bank_evidence и что стоит проверить. "
            "Численные сценарии / симулятор / решения недоступны — tools вернут "
            "tool_unavailable. "
        )

    return {
        "company": {
            "profile_status": company.get("profile_status"),
            "has_company": True,
            "is_demo": company.get("is_demo"),
            "display_label": "ваша компания",
            "source": "manual_twin",
        },
        "case_company_context": case_slim,
        "assessment_state": assessment,
        "has_impact_calculation": has_calc,
        "calculation": full.get("calculation")
        or {
            "available": has_calc,
            "reason": None if has_calc else CALCULATION_UNAVAILABLE,
            "explanation": None if has_calc else CALCULATION_UNAVAILABLE_EXPLANATION,
        },
        "event": {
            "id": event.get("id"),
            "title": event.get("title"),
            "summary_data": event.get("summary_data"),
            "category": event.get("category"),
            "event_type": event.get("event_type"),
            "severity": event.get("severity"),
            "is_demo": event.get("is_demo"),
            "labels": event.get("labels") or [],
        },
        "sources": [
            {
                "id": s.get("id"),
                "publisher": s.get("publisher"),
                "url": s.get("url"),
                "published_at": s.get("published_at"),
                "excerpt": s.get("excerpt"),
                "is_stub": s.get("is_stub"),
                "source_quality": s.get("source_quality"),
            }
            for s in sources
            if isinstance(s, dict)
        ],
        "impact": impact if has_calc else None,
        "impact_results": impact_results,
        "metric_semantics": full.get("metric_semantics")
        or {
            "impact_score": "check_score_kind",
            "confidence": "heuristic_0_55_source_plus_0_45_edge_not_probability",
            "exposure": "output_share_null_unknown_zero_known_not_loss_forecast",
            "stop_risk_percent": "model_index_not_statistical_probability",
        },
        "tools_available": full.get("tools_available")
        or {
            "discuss_event": True,
            "get_event_context": True,
            "get_company_impact": has_calc,
            "get_impact_paths": has_calc,
            "list_solution_candidates": has_calc,
            "simulate_scenario": has_calc,
            "compare_scenarios": has_calc,
            "create_decision_draft": has_calc,
        },
        "tools_required_for": tools_required,
        "bank_evidence": slim_bank_evidence_for_provider(bank_block),
        "instruction": (
            instruction_calc
            + "bank_evidence — отдельные данные банка (не новость и не расчёт компании); "
            "цитируйте только fragment_id из переданного набора. "
            "case_company_context — конкурсные данные выбранной компании (отдельно от "
            "ручного twin); product true/false/unknown/conflict — разные состояния; "
            "не подменяйте конфликтные значения ручным профилем; не выводите сумму долга "
            "и денежный эффект из одной отметки кредита; материалы банка и case — "
            "разные основания."
        ),
    }
