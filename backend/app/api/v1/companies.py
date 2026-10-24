from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_company_member
from app.core.errors import AppError
from app.db.session import get_db
from app.models import (
    Company,
    CompanyEdge,
    CompanyMembership,
    CompanyNode,
    CompanyProfileSettings,
    Event,
    EventImpact,
    User,
)
from app.schemas.common import INDUSTRIES, IndustryOut, MessageOut
from app.schemas.company import (
    CompanyCreateIn,
    CompanyPatchIn,
    CompanySummaryOut,
    EdgeCreateIn,
    EdgeOut,
    FinancePatchIn,
    NodeCreateIn,
    NodeOut,
    NodePatchIn,
    ProfileOut,
)
from app.schemas.company_context import CompanyContextOut
from app.services.company_context import build_company_context

router = APIRouter(tags=["companies"])


def _summary(company: Company, role: str | None = None) -> CompanySummaryOut:
    return CompanySummaryOut(
        id=company.id,
        name=company.name,
        legal_name=company.legal_name,
        tax_id=company.tax_id,
        industry=company.industry,
        size_band=company.size_band,
        hq_region=company.hq_region,
        profile_status=company.profile_status,
        digital_twin_status=company.digital_twin_status,
        digital_twin_coverage=company.digital_twin_coverage,
        is_demo=company.is_demo,
        role=role,
    )


def _completeness(nodes: list[CompanyNode], company: Company) -> dict:
    types = {n.node_type for n in nodes}
    checks = {
        "industry": bool(company.industry),
        "product": "product" in types,
        "supplier": "supplier" in types,
        "component": "component" in types,
        "facility": "facility" in types,
        "production_line": "production_line" in types,
        "market": "market" in types,
    }
    # finance optional
    done = sum(1 for v in checks.values() if v)
    return {
        "checks": checks,
        "required_done": done,
        "required_total": len(checks),
        "percent": round(100 * done / len(checks), 1),
        "finance_optional": True,
    }


def _warnings(nodes: list[CompanyNode], edges: list[CompanyEdge], company: Company) -> list[str]:
    warnings: list[str] = []
    types = {n.node_type for n in nodes}
    if not company.industry:
        warnings.append("Не указана отрасль")
    if "supplier" in types and "component" not in types:
        warnings.append("Есть поставщик, но нет компонента")
    if "production_line" in types and not any(n.output_share_percent for n in nodes):
        warnings.append("У линии не указана доля выпуска")
    if nodes and not edges:
        warnings.append("Узлы есть, но связи ещё не заданы")
    return warnings


@router.get("/industries", response_model=list[IndustryOut])
def list_industries() -> list[IndustryOut]:
    return INDUSTRIES


@router.get("/companies/search", response_model=list[CompanySummaryOut])
def search_companies(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CompanySummaryOut]:
    """Search only the caller's own companies.

    This is NOT a public directory: it must never expose other users' company
    cards by name or INN. For public registry requisites use
    POST /api/v1/company-registry/lookup instead.
    """
    like = f"%{q}%"
    rows = (
        db.query(Company, CompanyMembership.role)
        .join(CompanyMembership, CompanyMembership.company_id == Company.id)
        .filter(
            CompanyMembership.user_id == user.id,
            or_(Company.name.ilike(like), Company.tax_id.ilike(like)),
        )
        .limit(20)
        .all()
    )
    return [_summary(c, role=role) for c, role in rows]


@router.post("/companies", response_model=CompanySummaryOut)
def create_company(
    body: CompanyCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompanySummaryOut:
    company = Company(
        id=str(uuid4()),
        name=body.name,
        legal_name=body.legal_name,
        tax_id=body.tax_id,
        industry=body.industry,
        size_band=body.size_band,
        hq_region=body.hq_region,
        created_by=user.id,
        profile_status="draft",
    )
    db.add(company)
    db.add(
        CompanyMembership(
            id=str(uuid4()), user_id=user.id, company_id=company.id, role="owner"
        )
    )
    db.add(
        CompanyProfileSettings(
            id=str(uuid4()),
            company_id=company.id,
            purchase_currencies_json=[],
            optional_finance_json={},
            preferences_json={},
            warnings_json=[],
        )
    )
    db.commit()
    db.refresh(company)
    return _summary(company, role="owner")


@router.get("/companies/{company_id}/profile", response_model=ProfileOut)
def get_profile(
    company_id: str,
    db: Session = Depends(get_db),
    membership: CompanyMembership = Depends(require_company_member),
) -> ProfileOut:
    company = db.get(Company, company_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company_id).all()
    edges = db.query(CompanyEdge).filter(CompanyEdge.company_id == company_id).all()
    settings = company.settings
    warnings = _warnings(nodes, edges, company)
    return ProfileOut(
        company=_summary(company, role=membership.role),
        nodes=[NodeOut.model_validate(n) for n in nodes],
        edges=[EdgeOut.model_validate(e) for e in edges],
        settings={
            "purchase_currencies": (settings.purchase_currencies_json if settings else []),
            "optional_finance": (settings.optional_finance_json if settings else {}),
            "preferences": (settings.preferences_json if settings else {}),
        },
        warnings=warnings,
        completeness=_completeness(nodes, company),
    )


@router.get(
    "/companies/{company_id}/context",
    response_model=CompanyContextOut,
    summary="Business context for company page",
    description=(
        "Read-only business-context projection for the /company page. "
        "Requires company membership. Returns human-readable labels only — "
        "no internal IDs in display fields, no raw twin graph."
    ),
)
def get_company_context(
    company_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _: CompanyMembership = Depends(require_company_member),
) -> CompanyContextOut:
    company = db.get(Company, company_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)
    return build_company_context(db, company=company, user=user)


@router.patch("/companies/{company_id}", response_model=CompanySummaryOut)
def patch_company(
    company_id: str,
    body: CompanyPatchIn,
    db: Session = Depends(get_db),
    membership: CompanyMembership = Depends(require_company_member),
) -> CompanySummaryOut:
    company = db.get(Company, company_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(company, field, value)
    # Editing a registry-sourced field drops its registry provenance (becomes manual).
    if changes:
        from app.services.company_registry.provenance import (
            REGISTRY_PROVENANCE_KEY,
            note_manual_overrides,
        )

        settings = company.settings
        if settings is not None and isinstance(settings.preferences_json, dict):
            prefs = dict(settings.preferences_json)
            if REGISTRY_PROVENANCE_KEY in prefs:
                settings.preferences_json = note_manual_overrides(prefs, changes)
    db.commit()
    db.refresh(company)
    return _summary(company, role=membership.role)


@router.post("/companies/{company_id}/nodes", response_model=NodeOut)
def add_node(
    company_id: str,
    body: NodeCreateIn,
    db: Session = Depends(get_db),
    _: CompanyMembership = Depends(require_company_member),
) -> NodeOut:
    from app.services.graph_names import is_unconfirmed_node_name

    if is_unconfirmed_node_name(body.name):
        raise AppError(
            "VALIDATION_ERROR",
            "Укажите реальное название узла цепочки. «Не знаю» и пустые ответы "
            "нельзя сохранять как подтверждённый узел.",
            422,
        )
    node = CompanyNode(id=str(uuid4()), company_id=company_id, **body.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    return NodeOut.model_validate(node)


@router.patch("/companies/{company_id}/nodes/{node_id}", response_model=NodeOut)
def patch_node(
    company_id: str,
    node_id: str,
    body: NodePatchIn,
    db: Session = Depends(get_db),
    _: CompanyMembership = Depends(require_company_member),
) -> NodeOut:
    from app.services.graph_names import is_unconfirmed_node_name

    node = (
        db.query(CompanyNode)
        .filter(CompanyNode.id == node_id, CompanyNode.company_id == company_id)
        .first()
    )
    if node is None:
        raise AppError("NOT_FOUND", "Узел не найден", 404)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and is_unconfirmed_node_name(data.get("name")):
        raise AppError(
            "VALIDATION_ERROR",
            "Укажите реальное название узла цепочки. «Не знаю» и пустые ответы "
            "нельзя сохранять как подтверждённый узел.",
            422,
        )
    for field, value in data.items():
        setattr(node, field, value)
    db.commit()
    db.refresh(node)
    return NodeOut.model_validate(node)


@router.post("/companies/{company_id}/edges", response_model=EdgeOut)
def add_edge(
    company_id: str,
    body: EdgeCreateIn,
    db: Session = Depends(get_db),
    _: CompanyMembership = Depends(require_company_member),
) -> EdgeOut:
    for nid in (body.from_node_id, body.to_node_id):
        node = (
            db.query(CompanyNode)
            .filter(CompanyNode.id == nid, CompanyNode.company_id == company_id)
            .first()
        )
        if node is None:
            raise AppError("NOT_FOUND", f"Узел {nid} не найден в компании", 404)
    edge = CompanyEdge(id=str(uuid4()), company_id=company_id, **body.model_dump())
    db.add(edge)
    db.commit()
    db.refresh(edge)
    return EdgeOut.model_validate(edge)


@router.patch("/companies/{company_id}/finance", response_model=MessageOut)
def patch_finance(
    company_id: str,
    body: FinancePatchIn,
    db: Session = Depends(get_db),
    _: CompanyMembership = Depends(require_company_member),
) -> MessageOut:
    from app.services.impact import is_macro_fx_event, recompute_company_impact

    company = db.get(Company, company_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)
    settings = (
        db.query(CompanyProfileSettings)
        .filter(CompanyProfileSettings.company_id == company_id)
        .first()
    )
    if settings is None:
        settings = CompanyProfileSettings(id=str(uuid4()), company_id=company_id)
        db.add(settings)
    from app.services.finance_validation import (
        merge_optional_finance,
        validate_optional_finance_fx,
    )

    # purchase_currencies: full replace when provided (list may be empty = clear list).
    settings.purchase_currencies_json = list(body.purchase_currencies)
    existing = (
        dict(settings.optional_finance_json)
        if isinstance(settings.optional_finance_json, dict)
        else {}
    )
    merged = merge_optional_finance(existing, body.optional_finance)
    settings.optional_finance_json = validate_optional_finance_fx(merged)
    db.flush()

    # Refresh *existing* personal cards for macro/FX so assessment_state can flip
    # to finance_ready. Does **not** create Impact for new events and does **not**
    # scan the whole news corpus — usable Impact for a current event is created by
    # explicit POST …/recompute-impact (UI path when setup includes ?event=).
    from app.services.notifications import enqueue_impact_notifications

    impacts = db.query(EventImpact).filter(EventImpact.company_id == company_id).all()
    for impact in impacts:
        event = db.get(Event, impact.event_id)
        if event is not None and is_macro_fx_event(event):
            updated = recompute_company_impact(db, event, company)
            enqueue_impact_notifications(db, updated, event)
    db.commit()
    return MessageOut(message="Финансовые параметры сохранены (необязательный шаг)")


@router.post("/companies/{company_id}/profile/complete", response_model=ProfileOut)
def complete_profile(
    company_id: str,
    db: Session = Depends(get_db),
    membership: CompanyMembership = Depends(require_company_member),
) -> ProfileOut:
    company = db.get(Company, company_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company_id).all()
    completeness = _completeness(nodes, company)
    required = completeness["checks"]
    # finance is NOT required
    blocking = [k for k, v in required.items() if not v]
    if blocking:
        raise AppError(
            "PROFILE_INCOMPLETE",
            "Заполните обязательные поля профиля",
            422,
            details=[{"field": f, "reason": "required"} for f in blocking],
        )
    company.profile_status = "ready"
    db.commit()
    return get_profile(company_id, db, membership)


@router.post("/companies/{company_id}/digital-twin/build")
def build_digital_twin(
    company_id: str,
    db: Session = Depends(get_db),
    _: CompanyMembership = Depends(require_company_member),
) -> dict:
    from app.services.impact import recompute_events_for_company

    company = db.get(Company, company_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company_id).count()
    edges = db.query(CompanyEdge).filter(CompanyEdge.company_id == company_id).count()
    coverage = 0.0 if nodes == 0 else min(100.0, round(100 * edges / max(nodes, 1), 1))
    company.digital_twin_status = "ready" if edges > 0 else "partial"
    company.digital_twin_coverage = coverage
    db.commit()

    impacts: list = []
    if nodes > 0:
        # Demo + real events; relevance gate inside recompute_events_for_company
        impacts = recompute_events_for_company(db, company, demo_only=False)

    return {
        "status": company.digital_twin_status,
        "nodes": nodes,
        "edges": edges,
        "coverage_percent": coverage,
        "impacts_computed": len(impacts),
        "message": "Модель Digital Twin пересчитана",
    }
