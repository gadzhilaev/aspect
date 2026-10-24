from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_company_member
from app.core.errors import AppError
from app.db.session import get_db
from app.models import (
    Company,
    CompanyMembership,
    CompanyNode,
    CompanyProfileSettings,
    Event,
    EventImpact,
    EventSource,
    ImpactPath,
    User,
)
from app.schemas.event import (
    AssessmentExplanationOut,
    DashboardOut,
    EventCardOut,
    EventDetailOut,
    EventSourceOut,
    ExposureOut,
    ImpactOut,
    ImpactPathOut,
    MetricMeaningOut,
    RelevanceMatchOut,
    RelevanceOut,
)
from app.schemas.event_bank_evidence import EventBankEvidenceOut
from app.services.bank_materials.event_evidence import collect_event_bank_evidence
from app.services.assessment_explain import (
    explanation_from_impact,
    metric_labels,
    score_kind_for_state,
    score_kind_label,
)
from app.services.impact import (
    IMPACT_STATUS_ACTIVE,
    IMPACT_STATUS_NOT_RELEVANT,
    assessment_state_for_impact,
    event_matches_company,
    recompute_company_impact,
    _purchase_currencies_for,
)
from app.services.notifications import enqueue_impact_notifications
from app.services.case_profile_feed import (
    FEED_GROUP_NAME,
    FEED_SORT_RULE,
    apply_feed_cursor,
    build_merged_feed_entries,
    describe_personal_feed_empty,
    feed_cursor_of,
    feed_group,
    load_product_snapshot,
    parse_feed_cursor,
)
from app.services.relevance import analyze_event_company_relevance

router = APIRouter(tags=["events"])


def _priority(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _sort_active_impacts(
    db: Session, impacts: list[EventImpact]
) -> list[tuple[EventImpact, str, str]]:
    """Return (impact, assessment_state, score_kind) sorted for personal feed."""
    enriched: list[tuple[EventImpact, str, str]] = []
    for impact in impacts:
        if impact.status == IMPACT_STATUS_NOT_RELEVANT:
            continue
        if impact.status not in IMPACT_STATUS_ACTIVE:
            continue
        event = db.get(Event, impact.event_id)
        if event is None:
            continue
        state = assessment_state_for_impact(db, event, impact)
        kind = _score_kind_of(impact, state)
        enriched.append((impact, state, kind))
    enriched.sort(
        key=lambda row: (
            feed_group(row[2]),
            -float(row[0].impact_score),
            row[0].event_id,
        )
    )
    return enriched


def _relevance_out(
    db: Session,
    event: Event,
    company: Company,
    nodes: list[CompanyNode],
    *,
    purchase_currencies: list[str],
    impact: EventImpact | None,
) -> RelevanceOut:
    finance: dict = {}
    settings_row = (
        db.query(CompanyProfileSettings)
        .filter(CompanyProfileSettings.company_id == company.id)
        .one_or_none()
    )
    if settings_row and isinstance(settings_row.optional_finance_json, dict):
        finance = dict(settings_row.optional_finance_json)
    assessment = analyze_event_company_relevance(
        event,
        company,
        nodes,
        purchase_currencies=purchase_currencies,
        optional_finance=finance,
    )
    active = impact is not None and impact.status in IMPACT_STATUS_ACTIVE
    state = None
    kind = None
    if impact is not None and active:
        state = assessment_state_for_impact(db, event, impact)
        kind = _score_kind_of(impact, state)
    return RelevanceOut(
        event_id=event.id,
        company_id=company.id,
        is_relevant=assessment.is_relevant,
        level=assessment.level,
        summary=assessment.summary,
        matched_features=[
            RelevanceMatchOut(**m) for m in (assessment.to_dict()["matched_features"] or [])
        ],
        missing_data=list(assessment.missing_data),
        limitations=list(assessment.limitations),
        country_roles_considered=list(assessment.country_roles_considered),
        has_active_impact=active,
        assessment_state=state,
        score_kind=kind,
        feed_group=FEED_GROUP_NAME.get(feed_group(kind)) if kind else None,
        profile_fingerprint=assessment.profile_fingerprint,
    )


def _score_kind_of(impact: EventImpact, state: str) -> str:
    breakdown = impact.score_breakdown_json or {}
    basis = breakdown.get("assessment_basis") if isinstance(breakdown, dict) else None
    if isinstance(basis, dict) and basis.get("score_kind"):
        return str(basis["score_kind"])
    if isinstance(breakdown, dict) and breakdown.get("score_kind"):
        return str(breakdown["score_kind"])
    return score_kind_for_state(state)


def _card(
    event: Event,
    impact: EventImpact,
    source_count: int,
    *,
    assessment_state: str | None = None,
) -> EventCardOut:
    exposure = None
    # exposure_value may be 0.0 (known zero) — only None means missing
    if impact.exposure_value is not None:
        exposure = ExposureOut(
            label=impact.exposure_label or "Доля выпуска, связанная с затронутым узлом",
            value=impact.exposure_value,
            unit=impact.exposure_unit or "percent",
        )
    state = str(
        assessment_state
        or (impact.score_breakdown_json or {}).get("assessment_state", "monitoring_only")
    )
    kind = _score_kind_of(impact, state)
    labels = metric_labels(
        has_exposure=exposure is not None,
        assessment_state=state,
        score_kind=kind,
    )
    bases: list[str] = []
    if kind == "company_calculated":
        bases.append("calculated_impact")
    elif kind == "event_severity_signal":
        bases.append("event_severity_signal")
    elif kind == "case_profile_match":
        bases.append("case_profile")
    return EventCardOut(
        id=event.id,
        title=event.title,
        category=event.category,
        priority=_priority(impact.impact_score),
        impact_score=float(impact.impact_score),
        impact_score_available=True,
        urgency=impact.urgency,
        confidence=impact.confidence,
        reason_summary=impact.reason_summary,
        exposure=exposure,
        claims=impact.claims_json or {},
        source_count=source_count,
        updated_at=impact.computed_at,
        status=impact.status,
        is_demo=event.is_demo,
        assessment_state=state,
        metric_labels=labels,
        score_kind=kind,
        score_kind_label=labels.get("impact_score") or score_kind_label(kind),
        inclusion_bases=bases,
        profile_relevance=None,
    )


def _explanation_out(impact: EventImpact, event: Event | None) -> AssessmentExplanationOut:
    raw = explanation_from_impact(impact, event)
    return AssessmentExplanationOut(
        basis_available=bool(raw.get("basis_available")),
        summary=str(raw.get("summary") or ""),
        metrics=[MetricMeaningOut(**m) for m in (raw.get("metrics") or [])],
        used_event_data=list(raw.get("used_event_data") or []),
        used_company_data=list(raw.get("used_company_data") or []),
        dependencies=list(raw.get("dependencies") or []),
        calculation=raw.get("calculation"),
        assumptions=list(raw.get("assumptions") or []),
        missing_data=list(raw.get("missing_data") or []),
        limitations=list(raw.get("limitations") or []),
        model_version=raw.get("model_version"),
        computed_at=raw.get("computed_at"),
        assessment_state=str(raw.get("assessment_state") or "monitoring_only"),
        is_demo_event=bool(raw.get("is_demo_event")),
        metric_labels=dict(raw.get("metric_labels") or {}),
        score_kind=raw.get("score_kind"),
        score_kind_label=raw.get("score_kind_label"),
        confidence_detail=dict(raw.get("confidence_detail") or {}),
        demo_score_override=raw.get("demo_score_override"),
    )


@router.get("/companies/{company_id}/dashboard", response_model=DashboardOut)
def dashboard(
    company_id: str,
    db: Session = Depends(get_db),
    _: CompanyMembership = Depends(require_company_member),
    user: User = Depends(get_current_user),
) -> DashboardOut:
    company = db.get(Company, company_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)
    impacts = (
        db.query(EventImpact).filter(EventImpact.company_id == company_id).all()
    )
    # Read-only: no lazy twin recompute on GET (use POST digital-twin/build
    # or POST .../recompute-impact for explicit recalculation).
    active_rows = _sort_active_impacts(db, impacts)

    products = load_product_snapshot(db, company=company, user=user)
    entries = build_merged_feed_entries(
        db,
        company_id=company_id,
        impact_rows=active_rows,
        products=products,
        score_kind_of=_score_kind_of,
    )
    cards = [e.card for e in entries[:10]]
    active_only = [i for i, _, _ in active_rows]
    profile_only = sum(1 for e in entries if e.score_kind == "case_profile_match")
    counters = {
        "action_required": sum(1 for i in active_only if i.status == "action_required"),
        "monitor": sum(1 for i in active_only if i.status == "monitor"),
        "total": len(active_only),
        "high_priority": sum(1 for i in active_only if i.impact_score >= 80),
        "not_relevant": sum(1 for i in impacts if i.status == IMPACT_STATUS_NOT_RELEVANT),
        "profile_match": profile_only,
    }
    node_count = (
        db.query(CompanyNode).filter(CompanyNode.company_id == company_id).count()
    )
    feed_empty = describe_personal_feed_empty(
        db,
        company=company,
        node_count=node_count,
        feed_card_count=len(entries),
    )
    return DashboardOut(
        counters=counters,
        priority_events=cards,
        digital_twin={
            "status": company.digital_twin_status,
            "coverage_percent": company.digital_twin_coverage,
        },
        company_name=company.name,
        feed_sort_rule=FEED_SORT_RULE,
        feed_empty=feed_empty,
    )


@router.get("/companies/{company_id}/events", response_model=dict)
def list_events(
    company_id: str,
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: CompanyMembership = Depends(require_company_member),
    user: User = Depends(get_current_user),
) -> dict:
    company = db.get(Company, company_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)

    q = db.query(EventImpact).filter(EventImpact.company_id == company_id)
    if status:
        q = q.filter(EventImpact.status == status)
    else:
        q = q.filter(EventImpact.status.in_(list(IMPACT_STATUS_ACTIVE)))
    impacts = q.all()

    # Default (no status filter): merge active impacts with case-profile matches.
    if status is None:
        sorted_rows = _sort_active_impacts(db, impacts)
        products = load_product_snapshot(db, company=company, user=user)
        entries = build_merged_feed_entries(
            db,
            company_id=company_id,
            impact_rows=sorted_rows,
            products=products,
            score_kind_of=_score_kind_of,
        )
        entries = apply_feed_cursor(entries, cursor)
        page_entries = entries[:limit]
        items = [e.card for e in page_entries]
        next_cursor = None
        if len(entries) > limit and page_entries:
            last = page_entries[-1]
            next_cursor = feed_cursor_of(
                last.score_kind, last.sort_key, last.event_id
            )
        return {
            "items": items,
            "next_cursor": next_cursor,
            "limit": limit,
            "feed_sort_rule": FEED_SORT_RULE,
        }

    # Explicit status filter — impact rows only (no profile injection).
    if status == IMPACT_STATUS_NOT_RELEVANT:
        sorted_rows = []
        for i in impacts:
            st = str((i.score_breakdown_json or {}).get("assessment_state") or "monitoring_only")
            sorted_rows.append((i, st, _score_kind_of(i, st)))
        sorted_rows.sort(
            key=lambda row: (-float(row[0].impact_score), row[0].event_id)
        )
    else:
        sorted_rows = _sort_active_impacts(db, impacts)

    cur = parse_feed_cursor(cursor)
    if cur is not None:
        filtered: list[tuple[EventImpact, str, str]] = []
        for row in sorted_rows:
            impact, _st, kind = row
            # Reuse same after-cursor semantics via a tiny FeedEntry-like check
            g = feed_group(kind)
            score = float(impact.impact_score)
            eid = impact.event_id
            if g > cur.group:
                filtered.append(row)
            elif g < cur.group:
                continue
            elif score < cur.sort_key:
                filtered.append(row)
            elif score > cur.sort_key:
                continue
            elif cur.event_id is None:
                continue
            elif eid > cur.event_id:
                filtered.append(row)
        sorted_rows = filtered

    page = sorted_rows[:limit]
    items = []
    for impact, state, kind in page:
        event = db.get(Event, impact.event_id)
        if event is None:
            continue
        src = db.query(EventSource).filter(EventSource.event_id == event.id).count()
        items.append(_card(event, impact, src, assessment_state=state))
    next_cursor = None
    if len(sorted_rows) > limit and page:
        _imp, _st, kind = page[-1]
        next_cursor = feed_cursor_of(kind, float(_imp.impact_score), _imp.event_id)
    return {
        "items": items,
        "next_cursor": next_cursor,
        "limit": limit,
        "feed_sort_rule": FEED_SORT_RULE,
    }


@router.get(
    "/events/{event_id}/bank-evidence",
    response_model=EventBankEvidenceOut,
    summary="Bank research evidence for an event (thematic, read-only)",
)
def event_bank_evidence(
    event_id: str,
    company_id: str | None = Query(
        default=None,
        description="Optional; if set, requires company membership. Not used for thematic matching.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EventBankEvidenceOut:
    """Return verified bank fragments thematically related to the event.

    Auth required (bank corpus is not public). EventImpact is not required.
    Does not create impact/chat/links or change scores. Client cannot set OCR scope.
    """
    if company_id is not None:
        require_company_member(company_id, db, user)
    event = db.get(Event, event_id)
    if event is None:
        raise AppError("NOT_FOUND", "Событие не найдено", 404)
    return collect_event_bank_evidence(db, event=event)


@router.get("/events/{event_id}/relevance", response_model=RelevanceOut)
def event_relevance(
    event_id: str,
    company_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RelevanceOut:
    """Explain relevance for the company without creating EventImpact (GET is side-effect free)."""
    require_company_member(company_id, db, user)
    event = db.get(Event, event_id)
    company = db.get(Company, company_id)
    if event is None or company is None:
        raise AppError("NOT_FOUND", "Событие или компания не найдены", 404)
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company_id).all()
    impact = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event_id, EventImpact.company_id == company_id)
        .first()
    )
    return _relevance_out(
        db,
        event,
        company,
        nodes,
        purchase_currencies=_purchase_currencies_for(db, company_id),
        impact=impact,
    )


@router.get("/events/{event_id}", response_model=EventDetailOut)
def event_detail(
    event_id: str,
    company_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EventDetailOut:
    require_company_member(company_id, db, user)
    event = db.get(Event, event_id)
    company = db.get(Company, company_id)
    if event is None:
        raise AppError("NOT_FOUND", "Событие не найдено", 404)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)
    impact = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event_id, EventImpact.company_id == company_id)
        .first()
    )
    sources = db.query(EventSource).filter(EventSource.event_id == event_id).all()
    card = None
    claims = {}
    if impact is not None and impact.status in IMPACT_STATUS_ACTIVE:
        card = _card(
            event,
            impact,
            len(sources),
            assessment_state=assessment_state_for_impact(db, event, impact),
        )
        claims = impact.claims_json or {}
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company_id).all()
    relevance = _relevance_out(
        db,
        event,
        company,
        nodes,
        purchase_currencies=_purchase_currencies_for(db, company_id),
        impact=impact,
    )
    return EventDetailOut(
        id=event.id,
        title=event.title,
        summary=event.summary,
        category=event.category,
        event_type=event.event_type,
        severity=event.severity,
        status=event.status,
        occurred_at=event.occurred_at,
        effective_from=event.effective_from,
        impact=card,
        sources=[EventSourceOut.model_validate(s) for s in sources],
        claims=claims,
        is_demo=event.is_demo,
        relevance=relevance,
    )


@router.get("/events/{event_id}/impact", response_model=ImpactOut)
def event_impact(
    event_id: str,
    company_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ImpactOut:
    require_company_member(company_id, db, user)
    impact = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event_id, EventImpact.company_id == company_id)
        .first()
    )
    if impact is None or impact.status == IMPACT_STATUS_NOT_RELEVANT:
        raise AppError(
            "NOT_FOUND",
            "Актуальное влияние события на компанию не рассчитано",
            404,
        )
    paths = (
        db.query(ImpactPath)
        .filter(ImpactPath.event_impact_id == impact.id)
        .order_by(ImpactPath.sort_order.asc())
        .all()
    )
    exposure = None
    if impact.exposure_value is not None:
        exposure = ExposureOut(
            label=impact.exposure_label or "Доля выпуска, связанная с затронутым узлом",
            value=impact.exposure_value,
            unit=impact.exposure_unit or "percent",
        )
    event = db.get(Event, event_id)
    state = (
        assessment_state_for_impact(db, event, impact)
        if event is not None
        else str((impact.score_breakdown_json or {}).get("assessment_state") or "monitoring_only")
    )
    kind = _score_kind_of(impact, state)
    expl = _explanation_out(impact, event)
    labels = expl.metric_labels or metric_labels(
        has_exposure=exposure is not None,
        assessment_state=state,
        score_kind=kind,
    )
    return ImpactOut(
        event_id=event_id,
        company_id=company_id,
        impact_score=impact.impact_score,
        urgency=impact.urgency,
        confidence=impact.confidence,
        reason_summary=impact.reason_summary,
        exposure=exposure,
        score_breakdown=impact.score_breakdown_json or {},
        claims=impact.claims_json or {},
        paths=[
            ImpactPathOut(
                id=p.id,
                path_nodes=p.path_nodes_json or [],
                path_edges=p.path_edges_json or [],
                exposure_value=p.exposure_value,
                claim_type=p.claim_type,
                explanation=p.explanation,
                sort_order=p.sort_order,
            )
            for p in paths
        ],
        model_version=impact.model_version,
        computed_at=impact.computed_at,
        assessment_state=state,
        finance_setup_href=(
            "/company/setup?step=finance" if state == "finance_data_required" else None
        ),
        assessment_explanation=expl,
        metric_labels=labels,
        score_kind=kind,
        score_kind_label=labels.get("impact_score")
        or expl.score_kind_label
        or score_kind_label(kind),
    )


@router.post("/events/{event_id}/recompute-impact", response_model=ImpactOut)
def recompute(
    event_id: str,
    company_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ImpactOut:
    require_company_member(company_id, db, user)
    event = db.get(Event, event_id)
    company = db.get(Company, company_id)
    if event is None or company is None:
        raise AppError("NOT_FOUND", "Событие или компания не найдены", 404)
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company_id).all()
    settings = (
        db.query(CompanyProfileSettings)
        .filter(CompanyProfileSettings.company_id == company_id)
        .one_or_none()
    )
    purchase = list(settings.purchase_currencies_json or []) if settings else []
    finance = (
        dict(settings.optional_finance_json)
        if settings and isinstance(settings.optional_finance_json, dict)
        else {}
    )
    if not event_matches_company(
        event,
        company,
        nodes,
        purchase_currencies=purchase,
        optional_finance=finance,
    ):
        raise AppError(
            "NOT_RELEVANT",
            "Событие не пересекается с профилем компании",
            422,
        )
    impact = recompute_company_impact(db, event, company)
    enqueue_impact_notifications(db, impact, event)
    db.commit()
    return event_impact(event_id, company_id, db, user)
