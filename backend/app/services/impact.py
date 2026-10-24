"""Deterministic, versioned impact scoring — never merge impact and confidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Company,
    CompanyEdge,
    CompanyNode,
    CompanyProfileSettings,
    Event,
    EventImpact,
    EventSource,
    ImpactPath,
)
from app.services.assessment_explain import (
    EXPOSURE_LABEL,
    SCORE_KIND_COMPANY,
    SCORE_KIND_SEVERITY,
    build_assessment_basis,
    score_kind_for_state,
)
from app.services.graph import find_paths, match_event_to_nodes
from app.services.graph_names import path_has_unconfirmed_nodes
from app.services.relevance import (
    analyze_event_company_relevance,
    expand_country_tokens,
    is_macro_fx_event,  # re-exported for API modules
    norm_token,
)

# Re-exports for callers/tests that imported helpers from impact
_norm_token = norm_token
_expand_country_tokens = expand_country_tokens

IMPACT_STATUS_ACTIVE = frozenset({"action_required", "monitor"})
IMPACT_STATUS_NOT_RELEVANT = "not_relevant"

SEVERITY_TO_URGENCY = [
    (85, "watch_now"),
    (60, "this_week"),
    (30, "monitor"),
    (0, "info"),
]

AssessmentState = Literal[
    "supply_chain_ready",
    "finance_data_required",
    "finance_ready",
    "monitoring_only",
    # No usable EventImpact row (absent or not_relevant) — distinct from monitoring_only.
    "calculation_unavailable",
]

# Legacy five keys (liquidity etc.) — still accepted; not all required for finance_ready.
FINANCE_REQUIRED_KEYS = (
    "debt_amount",
    "floating_rate_share_percent",
    "near_term_payments_90d",
    "fx_purchase_volume",
    "cash_reserve_days",
)

RATE_FINANCE_KEYS = (
    "debt_amount",
    "floating_rate_share_percent",
)

FX_FINANCE_KEYS = (
    "fx_exposure_amount",
    "fx_exposure_currency",
    "fx_exposure_direction",
    "fx_quote_currency",
)

FINANCE_DATA_REQUIRED_REASON = (
    "Событие может затронуть стоимость финансирования или валютную экспозицию. "
    "Добавьте параметры долга и/или валютной операции в финансовом профиле"
)

MONITORING_ONLY_REASON = (
    "Сигнал релевантен для компании, но пока недостаточно данных "
    "для моделирования влияния"
)


def event_matches_company(
    event: Event,
    company: Company,
    nodes: list[CompanyNode],
    *,
    purchase_currencies: list[str] | None = None,
    optional_finance: dict[str, Any] | None = None,
) -> bool:
    """Relevance gate — role-aware (supplier vs market); see analyze_event_company_relevance."""
    return analyze_event_company_relevance(
        event,
        company,
        nodes,
        purchase_currencies=purchase_currencies,
        optional_finance=optional_finance,
    ).is_relevant


def _purchase_currencies_for(db: Session, company_id: str) -> list[str]:
    settings = (
        db.query(CompanyProfileSettings)
        .filter(CompanyProfileSettings.company_id == company_id)
        .one_or_none()
    )
    if settings is None:
        return []
    raw = settings.purchase_currencies_json or []
    return [str(c) for c in raw if str(c).strip()]


def _optional_finance_for(db: Session, company_id: str) -> dict[str, Any]:
    settings = (
        db.query(CompanyProfileSettings)
        .filter(CompanyProfileSettings.company_id == company_id)
        .one_or_none()
    )
    if settings is None:
        return {}
    raw = settings.optional_finance_json or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _key_present(data: dict[str, Any], key: str) -> bool:
    """True when the key is present with a known value (including numeric 0)."""
    if key not in data:
        return False
    val = data.get(key)
    return val is not None and val != ""


def has_rate_finance_context(optional_finance: dict[str, Any] | None) -> bool:
    """Profile sufficient for the key-rate track (debt + floating share)."""
    data = optional_finance or {}
    return all(_key_present(data, k) for k in RATE_FINANCE_KEYS)


def has_fx_finance_context(optional_finance: dict[str, Any] | None) -> bool:
    """Profile sufficient for the typed FX track (one exposure)."""
    from app.services.fx_scenario import has_fx_exposure_context

    return has_fx_exposure_context(optional_finance)


def has_finance_context(optional_finance: dict[str, Any] | None) -> bool:
    """True if at least one finance track (rate or FX) has required profile params.

    Does **not** mean a money scenario is available for a given event — that also
    needs observed/assumed basis in the event or explicit what-if.
    """
    return has_rate_finance_context(optional_finance) or has_fx_finance_context(
        optional_finance
    )


def missing_finance_track_fields(
    optional_finance: dict[str, Any] | None,
) -> dict[str, list[str]]:
    """Fields still needed per track for profile readiness (not event basis)."""
    data = optional_finance or {}
    rate_missing = [k for k in RATE_FINANCE_KEYS if not _key_present(data, k)]
    fx_missing = [k for k in FX_FINANCE_KEYS if not _key_present(data, k)]
    return {"rate": rate_missing, "fx": fx_missing}


def resolve_assessment_state(
    event: Event,
    *,
    has_supply_path: bool,
    has_exposure: bool,
    optional_finance: dict[str, Any] | None = None,
) -> AssessmentState:
    """Pick assessment mode.

    ``has_exposure`` means an exposure value is *known* (including ``0.0``).
    Unknown / inapplicable exposure must be passed as ``False`` (API ``null``),
    never coerced from missing data into ``0``.
    """
    # Macro/FX always uses the finance track — do not treat a country/market
    # coincidence as a production supply-chain impact.
    if is_macro_fx_event(event):
        if has_finance_context(optional_finance):
            return "finance_ready"
        return "finance_data_required"
    if has_supply_path and has_exposure:
        return "supply_chain_ready"
    return "monitoring_only"


def assessment_state_for_impact(
    db: Session, event: Event, impact: EventImpact
) -> AssessmentState:
    """Live resolve — picks up finance filled after impact was computed."""
    paths = (
        db.query(ImpactPath)
        .filter(ImpactPath.event_impact_id == impact.id)
        .limit(1)
        .all()
    )
    finance = _optional_finance_for(db, impact.company_id)
    return resolve_assessment_state(
        event,
        has_supply_path=bool(paths) and impact.exposure_value is not None,
        has_exposure=impact.exposure_value is not None,
        optional_finance=finance,
    )


def _urgency_from_score(score: float) -> str:
    for threshold, label in SEVERITY_TO_URGENCY:
        if score >= threshold:
            return label
    return "info"


def compute_impact_score(
    *,
    severity: float | None,
    exposure: float,
    dependency_criticality: float,
    propagation_proximity: float,
) -> tuple[float, dict[str, Any]]:
    settings = get_settings()
    w_s = settings.impact_weight_severity
    w_e = settings.impact_weight_exposure
    w_d = settings.impact_weight_dependency
    w_p = settings.impact_weight_proximity

    # Unknown severity: omit the term (do not invent 0 as a known severity).
    if severity is None:
        rest = w_e + w_d + w_p
        if rest <= 0:
            score = 0.0
            sev_contrib = 0.0
            w_s_eff = 0.0
        else:
            scale = (w_s + rest) / rest
            score = scale * (
                w_e * exposure
                + w_d * dependency_criticality
                + w_p * propagation_proximity
            )
            sev_contrib = 0.0
            w_s_eff = 0.0
        sev_note = "severity unknown — term omitted, not coerced to 0"
    else:
        score = (
            w_s * severity
            + w_e * exposure
            + w_d * dependency_criticality
            + w_p * propagation_proximity
        )
        sev_contrib = round(w_s * severity, 2)
        w_s_eff = w_s
        sev_note = None

    breakdown = {
        "severity": {
            "value": severity,
            "weight": w_s_eff,
            "contribution": sev_contrib,
            **({"note": sev_note} if sev_note else {}),
        },
        "exposure": {
            "value": exposure,
            "weight": w_e,
            "contribution": round(w_e * exposure, 2),
            "note": (
                "output_share_percent capped at 100; "
                "API exposure shows the same raw share (null if unknown)"
            ),
        },
        "dependency_criticality": {
            "value": dependency_criticality,
            "weight": w_d,
            "contribution": round(w_d * dependency_criticality, 2),
        },
        "propagation_proximity": {
            "value": propagation_proximity,
            "weight": w_p,
            "contribution": round(w_p * propagation_proximity, 2),
        },
        "formula": (
            f"{w_s:.2f}×severity + {w_e:.2f}×exposure + "
            f"{w_d:.2f}×dependency + {w_p:.2f}×proximity"
        ),
    }
    return round(min(100.0, max(0.0, score)), 2), breakdown


def compute_confidence_detail(
    sources: list[EventSource], path_edge_confidences: list[float]
) -> tuple[float, dict[str, Any]]:
    """Heuristic data-quality score + provenance of defaults.

    Not measured accuracy and not a probability that the impact is «correct».
    """
    source_defaulted = not sources
    edge_defaulted = not path_edge_confidences
    source_q = (
        0.4
        if source_defaulted
        else sum(s.source_quality for s in sources) / len(sources)
    )
    edge_q = (
        0.5
        if edge_defaulted
        else sum(path_edge_confidences) / len(path_edge_confidences)
    )
    value = round(min(1.0, max(0.0, 0.55 * source_q + 0.45 * edge_q)), 3)
    detail = {
        "is_heuristic": True,
        "formula": "0.55×source_quality + 0.45×edge_confidence",
        "source_quality": round(float(source_q), 3),
        "edge_confidence": round(float(edge_q), 3),
        "source_quality_defaulted": source_defaulted,
        "edge_confidence_defaulted": edge_defaulted,
        "default_source_quality_if_no_sources": 0.4,
        "default_edge_confidence_if_no_edges": 0.5,
    }
    return value, detail


def compute_confidence(sources: list[EventSource], path_edge_confidences: list[float]) -> float:
    value, _ = compute_confidence_detail(sources, path_edge_confidences)
    return value


def recompute_company_impact(db: Session, event: Event, company: Company) -> EventImpact:
    settings = get_settings()
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company.id).all()
    edges = db.query(CompanyEdge).filter(CompanyEdge.company_id == company.id).all()
    sources = db.query(EventSource).filter(EventSource.event_id == event.id).all()
    edge_by_id = {e.id: e for e in edges}
    finance = _optional_finance_for(db, company.id)

    relevance = analyze_event_company_relevance(
        event,
        company,
        nodes,
        purchase_currencies=_purchase_currencies_for(db, company.id),
        optional_finance=finance,
    )
    start_ids = match_event_to_nodes(event.match_countries_json or [], nodes)
    # Prefer supplier entry points so chains stay explainable (country → supplier → …)
    supplier_starts = {
        n.id for n in nodes if n.id in start_ids and n.node_type == "supplier"
    }
    if supplier_starts:
        start_ids = supplier_starts
    elif not is_macro_fx_event(event) and relevance.level == "dependency_ready":
        # Material-only starts only when country role already matched (no invented China chain)
        materials = {m.lower() for m in (event.match_materials_json or [])}
        for node in nodes:
            if node.node_type == "component" and any(
                m in node.name.lower() for m in materials
            ):
                start_ids.add(node.id)

    paths = find_paths(start_ids, nodes, edges)
    # Drop paths whose node names are explicit unknowns («не знаю», n/a, …).
    # Those must not become a confirmed supply-chain reason with an output share.
    paths = [p for p in paths if not path_has_unconfirmed_nodes(p.get("nodes"))]
    best = paths[0] if paths else None
    # Preserve None vs 0.0 — never coerce missing share into zero.
    if best is None:
        exposure_share: float | None = None
    else:
        raw_share = best.get("exposure_value")
        exposure_share = float(raw_share) if raw_share is not None else None

    proximity = 100.0
    if best:
        hops = max(1, len(best["nodes"]) - 1)
        proximity = max(20.0, 100.0 - (hops - 1) * 15)
    dependency = (
        80.0 if best and best["nodes"][-1]["node_type"] == "production_line" else 40.0
    )

    # Unified formula for demo and real — no event-id / company-name overrides.
    exposure_for_score = (
        min(100.0, exposure_share) if exposure_share is not None else 0.0
    )
    score, breakdown = compute_impact_score(
        severity=event.severity,
        exposure=exposure_for_score,
        dependency_criticality=dependency,
        propagation_proximity=proximity,
    )
    demo_score_override: dict[str, Any] = {
        "applied": False,
        "multiplier": None,
        "reason": None,
    }

    path_confidences: list[float] = []
    if best:
        for eid in best["edge_ids"]:
            edge = edge_by_id.get(eid)
            if edge:
                path_confidences.append(edge.confidence)
    confidence, confidence_detail = compute_confidence_detail(sources, path_confidences)

    # Known value (incl. 0.0) vs unknown/missing (None)
    has_known_exposure = exposure_share is not None
    assessment = resolve_assessment_state(
        event,
        has_supply_path=bool(best),
        has_exposure=has_known_exposure,
        optional_finance=finance,
    )

    # Macro/FX / monitoring: do not invent supply-chain exposure/paths
    if assessment in {"finance_data_required", "finance_ready", "monitoring_only"}:
        best = None
        exposure_share = None
        has_known_exposure = False
        path_confidences = []
        confidence, confidence_detail = compute_confidence_detail(sources, [])

    score_kind = score_kind_for_state(assessment)
    claims = {
        "confirmed": sum(1 for s in sources if s.source_quality >= 0.75),
        "inferences": 1 if best else 0,
        "assumptions": 1 if has_known_exposure else 0,
        "estimates": 1,
    }

    display_mode: str | None = None
    if assessment == "supply_chain_ready" and best:
        reason = f"Ограничение связано с цепочкой до узла «{best['nodes'][-1]['name']}»."
        if len(best["nodes"]) >= 3:
            chain = " → ".join(n["name"] for n in best["nodes"][1:4])
            reason = f"Ограничение связано с {chain}."
        display_mode = "supply_chain_ready"
        score_kind = SCORE_KIND_COMPANY
    elif assessment == "finance_data_required":
        reason = FINANCE_DATA_REQUIRED_REASON
        # Severity triage signal only — not a calculated company impact.
        # Unknown severity → keep score from compute_impact_score (severity term omitted).
        display_mode = "finance_data_required"
        score_kind = SCORE_KIND_SEVERITY
        if event.severity is not None:
            score = round(min(100.0, max(0.0, float(event.severity) * 0.5)), 2)
        breakdown = {
            **breakdown,
            "display_mode": display_mode,
            "score_kind": score_kind,
            "note": (
                "impact_score is an event-severity triage signal for feed ranking, "
                "not a calculated company impact"
                if event.severity is not None
                else "event.severity unknown — triage factor omitted, not coerced to 0"
            ),
        }
    elif assessment == "finance_ready":
        reason = (
            "Событие может повлиять на стоимость финансирования и валютные платежи. "
            "Ниже — расчётные финансовые сценарии на основе профиля компании."
        )
        display_mode = "finance_ready"
        score_kind = SCORE_KIND_SEVERITY
        if event.severity is not None:
            score = round(min(100.0, max(0.0, float(event.severity) * 0.55)), 2)
        breakdown = {
            **breakdown,
            "display_mode": display_mode,
            "score_kind": score_kind,
            "note": (
                "impact_score is an event-severity signal; finance effects come from "
                "the separate financial simulator"
                if event.severity is not None
                else "event.severity unknown — finance scenarios still from simulator"
            ),
        }
    else:
        reason = MONITORING_ONLY_REASON
        display_mode = "monitoring_only"
        score_kind = SCORE_KIND_SEVERITY
        if event.severity is not None:
            score = round(min(100.0, max(0.0, float(event.severity) * 0.4)), 2)
        breakdown = {
            **breakdown,
            "display_mode": display_mode,
            "score_kind": score_kind,
            "note": (
                "impact_score is an event-severity triage signal; no company "
                "exposure path was established"
                if event.severity is not None
                else "event.severity unknown — no severity triage invented"
            ),
        }

    missing_tracks = missing_finance_track_fields(finance)
    missing_finance = list(
        dict.fromkeys([*missing_tracks.get("rate", []), *missing_tracks.get("fx", [])])
    )
    path_names = [n["name"] for n in best["nodes"]] if best else []
    computed_at = datetime.now(timezone.utc)
    basis = build_assessment_basis(
        assessment_state=assessment,
        event=event,
        impact_score=score,
        confidence=confidence,
        exposure_value=exposure_share if has_known_exposure else None,
        exposure_raw_for_score=(
            exposure_for_score if assessment == "supply_chain_ready" else None
        ),
        path_node_names=path_names,
        formula=str(breakdown.get("formula") or "") or None,
        display_mode=display_mode,
        source_count=len(sources),
        missing_finance_keys=missing_finance if assessment == "finance_data_required" else [],
        model_version=settings.impact_model_version,
        computed_at=computed_at,
        score_kind=score_kind,
        confidence_detail=confidence_detail,
        demo_score_override=demo_score_override,
    )
    breakdown = {
        **breakdown,
        "assessment_state": assessment,
        "score_kind": score_kind,
        "confidence_detail": confidence_detail,
        "demo_score_override": demo_score_override,
        "relevance": relevance.to_dict(),
        "assessment_basis": basis,
    }
    # Keep relevance snapshot inside basis for «Как рассчитано»
    basis = {**basis, "relevance": relevance.to_dict()}
    breakdown["assessment_basis"] = basis

    existing = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event.id, EventImpact.company_id == company.id)
        .first()
    )
    if existing:
        impact = existing
        db.query(ImpactPath).filter(ImpactPath.event_impact_id == impact.id).delete()
    else:
        impact = EventImpact(id=str(uuid4()), event_id=event.id, company_id=company.id)
        db.add(impact)

    impact.impact_score = score
    impact.urgency = (
        "this_week"
        if assessment == "finance_data_required"
        else _urgency_from_score(score)
    )
    impact.confidence = confidence
    impact.reason_summary = reason
    impact.exposure_value = exposure_share if has_known_exposure else None
    impact.exposure_label = EXPOSURE_LABEL if has_known_exposure else None
    impact.exposure_unit = "percent" if has_known_exposure else None
    impact.score_breakdown_json = breakdown
    impact.claims_json = claims
    if assessment == "finance_data_required":
        impact.status = "monitor"
    elif assessment == "monitoring_only":
        impact.status = "monitor"
    else:
        impact.status = "action_required" if score >= 50 else "monitor"
    impact.model_version = settings.impact_model_version
    impact.computed_at = computed_at

    db.flush()

    if best and assessment == "supply_chain_ready":
        claim_types = ["confirmed_fact", "inference", "assumption", "estimate"]
        for i, node in enumerate(best["nodes"]):
            claim = claim_types[min(i, len(claim_types) - 1)]
            db.add(
                ImpactPath(
                    id=str(uuid4()),
                    event_impact_id=impact.id,
                    path_nodes_json=best["nodes"][: i + 1],
                    path_edges_json=best["edge_ids"][:i],
                    exposure_value=node.get("output_share_percent"),
                    claim_type=claim,
                    explanation=_node_explanation(node, claim),
                    sort_order=i,
                )
            )
        assert exposure_share is not None
        db.add(
            ImpactPath(
                id=str(uuid4()),
                event_impact_id=impact.id,
                path_nodes_json=best["nodes"],
                path_edges_json=best["edge_ids"],
                exposure_value=exposure_share,
                claim_type="estimate",
                explanation=(
                    f"{exposure_share:g}% выпуска компании связано с затронутым узлом "
                    f"по цепочке из {len(best['nodes'])} узлов. "
                    "Это доля выпуска, а не прогноз потерь. "
                    "0% — известная нулевая доля; отсутствие значения означало бы, "
                    "что доля неизвестна."
                ),
                sort_order=100,
            )
        )

    db.flush()
    return impact


def _node_explanation(node: dict[str, Any], claim: str) -> str:
    labels = {
        "confirmed_fact": "Подтверждённый узел профиля",
        "inference": "Вывод по связи Digital Twin",
        "assumption": "Допущение о распространении влияния",
        "estimate": "Оценочный эффект",
    }
    return f"{labels.get(claim, claim)}: {node.get('name')} ({node.get('node_type')})"


def _mark_impact_not_relevant(
    db: Session,
    impact: EventImpact,
    *,
    relevance_dict: dict[str, Any],
    reason: str,
) -> None:
    """Hide from personal feed without deleting history / decisions / chats.

    Does not rewrite historical score numbers — only status, reason, and relevance note.
    """
    breakdown = dict(impact.score_breakdown_json or {})
    breakdown["relevance"] = relevance_dict
    breakdown["active_for_feed"] = False
    breakdown["not_relevant_reason"] = reason
    basis = dict(breakdown.get("assessment_basis") or {})
    if basis:
        basis["relevance"] = relevance_dict
        basis["limitations"] = list(basis.get("limitations") or []) + [
            "Актуальная релевантность снята после изменения профиля; "
            "сохранённые числа — снимок прошлого расчёта, не текущий статус."
        ]
        breakdown["assessment_basis"] = basis
    impact.score_breakdown_json = breakdown
    impact.status = IMPACT_STATUS_NOT_RELEVANT
    impact.reason_summary = reason
    # Drop live paths from the inactive card (history stays in past API responses / chats)
    db.query(ImpactPath).filter(ImpactPath.event_impact_id == impact.id).delete()
    impact.computed_at = datetime.now(timezone.utc)


def recompute_events_for_company(
    db: Session,
    company: Company,
    *,
    demo_only: bool = False,
) -> list[EventImpact]:
    """Build personal feed cards; deactivate impacts that no longer match the profile."""
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company.id).all()
    if not nodes:
        return []

    purchase_ccy = _purchase_currencies_for(db, company.id)
    q = db.query(Event).filter(Event.status == "active")
    if demo_only:
        q = q.filter(Event.is_demo.is_(True))
    events = q.order_by(Event.occurred_at.desc()).all()
    active_event_ids: set[str] = set()
    impacts: list[EventImpact] = []
    finance = _optional_finance_for(db, company.id)
    for event in events:
        assessment = analyze_event_company_relevance(
            event,
            company,
            nodes,
            purchase_currencies=purchase_ccy,
            optional_finance=finance,
        )
        if assessment.is_relevant:
            impact = recompute_company_impact(db, event, company)
            impacts.append(impact)
            active_event_ids.add(event.id)
            from app.services.notifications import enqueue_impact_notifications

            enqueue_impact_notifications(db, impact, event)
        else:
            existing = (
                db.query(EventImpact)
                .filter(
                    EventImpact.event_id == event.id,
                    EventImpact.company_id == company.id,
                )
                .first()
            )
            if existing is not None and existing.status != IMPACT_STATUS_NOT_RELEVANT:
                _mark_impact_not_relevant(
                    db,
                    existing,
                    relevance_dict=assessment.to_dict(),
                    reason=assessment.summary,
                )

    # Any leftover active impacts for inactive/removed events
    leftovers = (
        db.query(EventImpact)
        .filter(EventImpact.company_id == company.id)
        .filter(EventImpact.status.in_(list(IMPACT_STATUS_ACTIVE)))
        .all()
    )
    for impact in leftovers:
        if impact.event_id in active_event_ids:
            continue
        event = db.get(Event, impact.event_id)
        if event is None:
            _mark_impact_not_relevant(
                db,
                impact,
                relevance_dict={"is_relevant": False, "level": "not_relevant"},
                reason="Событие больше недоступно для персональной ленты.",
            )
            continue
        assessment = analyze_event_company_relevance(
            event,
            company,
            nodes,
            purchase_currencies=purchase_ccy,
            optional_finance=finance,
        )
        if not assessment.is_relevant:
            _mark_impact_not_relevant(
                db,
                impact,
                relevance_dict=assessment.to_dict(),
                reason=assessment.summary,
            )

    db.commit()
    return impacts


def recompute_event_for_ready_companies(db: Session, event: Event) -> list[EventImpact]:
    """After publishing a real event — personalize only for matching ready twins."""
    companies = (
        db.query(Company)
        .filter(Company.profile_status == "ready")
        .all()
    )
    impacts: list[EventImpact] = []
    for company in companies:
        nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company.id).all()
        if not nodes:
            continue
        purchase_ccy = _purchase_currencies_for(db, company.id)
        finance = _optional_finance_for(db, company.id)
        assessment = analyze_event_company_relevance(
            event,
            company,
            nodes,
            purchase_currencies=purchase_ccy,
            optional_finance=finance,
        )
        if not assessment.is_relevant:
            existing = (
                db.query(EventImpact)
                .filter(
                    EventImpact.event_id == event.id,
                    EventImpact.company_id == company.id,
                )
                .first()
            )
            if existing is not None and existing.status != IMPACT_STATUS_NOT_RELEVANT:
                _mark_impact_not_relevant(
                    db,
                    existing,
                    relevance_dict=assessment.to_dict(),
                    reason=assessment.summary,
                )
            continue
        impact = recompute_company_impact(db, event, company)
        impacts.append(impact)
        from app.services.notifications import enqueue_impact_notifications

        enqueue_impact_notifications(db, impact, event)
    return impacts
