from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models import EventImpact, Scenario, SolutionCandidate, User
from app.schemas.event import SimulateIn, SolutionOut
from app.services.simulator import rank_solutions, simulate

router = APIRouter(tags=["solutions"])


def _ensure_member(company_id: str, db: Session, user: User) -> None:
    from app.core.deps import require_company_member

    require_company_member(company_id, db, user)


@router.get("/events/{event_id}/solutions", response_model=list[SolutionOut])
def list_solutions(
    event_id: str,
    company_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SolutionOut]:
    _ensure_member(company_id, db, user)
    impact = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event_id, EventImpact.company_id == company_id)
        .first()
    )
    if impact is None:
        raise AppError("NOT_FOUND", "Влияние не найдено", 404)
    solutions = (
        db.query(SolutionCandidate)
        .filter(SolutionCandidate.event_impact_id == impact.id)
        .all()
    )
    ranked = rank_solutions(solutions)
    db.commit()
    return [
        SolutionOut(
            id=s.id,
            name=s.name,
            country=s.country,
            cost_delta_percent=s.cost_delta_percent,
            lead_time_days=s.lead_time_days,
            risk_percent=s.risk_percent,
            compatibility=s.compatibility,
            availability_status=s.availability_status,
            sort_score=s.sort_score,
            sort_breakdown=s.sort_breakdown_json or {},
            is_demo=s.is_demo,
            notes=s.notes,
        )
        for s in ranked
    ]


@router.post("/events/{event_id}/simulate")
def run_simulate(
    event_id: str,
    body: SimulateIn,
    company_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _ensure_member(company_id, db, user)
    impact = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event_id, EventImpact.company_id == company_id)
        .first()
    )
    if impact is None:
        raise AppError("NOT_FOUND", "Влияние не найдено", 404)

    solution = None
    if body.solution_id:
        solution = (
            db.query(SolutionCandidate)
            .filter(
                SolutionCandidate.id == body.solution_id,
                SolutionCandidate.event_impact_id == impact.id,
            )
            .first()
        )
        if solution is None:
            raise AppError("NOT_FOUND", "Вариант решения не найден", 404)

    results = simulate(
        output_share_at_risk=impact.exposure_value,
        inventory_days=body.inventory_days,
        delay_days=body.delay_days,
        solution=solution,
    )
    scenario = Scenario(
        id=str(uuid4()),
        company_id=company_id,
        event_id=event_id,
        solution_id=solution.id if solution else None,
        created_by=user.id,
        parameters_json=results["parameters"],
        results_json=results,
        model_version=get_settings().simulator_model_version,
        is_estimate=True,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return {
        "scenario_id": scenario.id,
        **results,
        "disclaimer": "Оценка, не финансовая гарантия. Демонстрационные данные.",
    }


@router.get("/scenarios/{scenario_id}")
def get_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise AppError("NOT_FOUND", "Сценарий не найден", 404)
    _ensure_member(scenario.company_id, db, user)
    params = scenario.parameters_json if isinstance(scenario.parameters_json, dict) else {}
    results = scenario.results_json if isinstance(scenario.results_json, dict) else {}
    presentation = None
    if (
        params.get("kind") == "financial"
        or results.get("track") in {"rate", "fx"}
        or results.get("rate_change_basis") is not None
        or results.get("fx_change_basis") is not None
        or results.get("fx_value_change") is not None
        or "finance" in str(scenario.model_version or "")
    ):
        from app.services.finance_scenario_presentation import build_finance_scenario_presentation

        presentation = build_finance_scenario_presentation(
            results=results,
            parameters=params,
            model_version=scenario.model_version,
            label=results.get("label") if isinstance(results.get("label"), str) else None,
        )
    return {
        "id": scenario.id,
        "company_id": scenario.company_id,
        "event_id": scenario.event_id,
        "solution_id": scenario.solution_id,
        "parameters": scenario.parameters_json,
        "results": scenario.results_json,
        "model_version": scenario.model_version,
        "is_estimate": scenario.is_estimate,
        "created_at": scenario.created_at,
        "presentation": presentation,
    }
