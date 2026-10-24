"""Safe application tools. LLM must not invent numeric risk/cost estimates."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    ActionItem,
    AssistantToolRun,
    Decision,
    Scenario,
    SolutionCandidate,
)
from app.services.assistant.context_builder import (
    build_conversation_context,
    calculation_unavailable_payload,
    lookup_usable_impact,
)
from app.services.assistant.safety import honesty_labels
from app.services.simulator import simulate


TOOL_NAMES = {
    "get_event_context",
    "get_company_impact",
    "get_impact_paths",
    "list_solution_candidates",
    "simulate_scenario",
    "compare_scenarios",
    "create_decision_draft",
}

_IN_PROGRESS = {
    "type": "operation_in_progress",
    "message": "Сравнение сценариев уже выполняется — повторите через мгновение",
    "status": "running",
}


def _idempotency_key(conversation_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps(
        {"c": conversation_id, "t": tool_name, "a": arguments},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


def _lookup_run(
    db: Session, *, conversation_id: str, tool_name: str, arguments: dict[str, Any]
) -> AssistantToolRun | None:
    key = _idempotency_key(conversation_id, tool_name, arguments)
    return (
        db.query(AssistantToolRun)
        .filter(
            AssistantToolRun.conversation_id == conversation_id,
            AssistantToolRun.idempotency_key == key,
        )
        .one_or_none()
    )


def _store_run(
    db: Session,
    *,
    conversation_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
    status: str = "ok",
    message_id: str | None = None,
) -> dict[str, Any]:
    key = _idempotency_key(conversation_id, tool_name, arguments)
    existing = (
        db.query(AssistantToolRun)
        .filter(
            AssistantToolRun.conversation_id == conversation_id,
            AssistantToolRun.idempotency_key == key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.status == "running" and status != "running":
            existing.result_json = result
            existing.status = status
            if message_id:
                existing.message_id = message_id
            db.flush()
            return result
        if existing.status == "running":
            return dict(_IN_PROGRESS)
        return existing.result_json or {}

    run = AssistantToolRun(
        id=str(uuid4()),
        conversation_id=conversation_id,
        message_id=message_id,
        tool_name=tool_name,
        arguments_json=arguments,
        result_json=result,
        status=status,
        idempotency_key=key,
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        hit = _lookup_run(
            db, conversation_id=conversation_id, tool_name=tool_name, arguments=arguments
        )
        if hit is None:
            raise
        if hit.status == "running":
            return dict(_IN_PROGRESS)
        return hit.result_json or {}
    return result


def _reserve_run(
    db: Session,
    *,
    conversation_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[Literal["done", "in_progress", "reserved"], dict[str, Any] | AssistantToolRun]:
    """Atomically claim an idempotency slot before creating Scenario rows."""
    hit = _lookup_run(
        db, conversation_id=conversation_id, tool_name=tool_name, arguments=arguments
    )
    if hit is not None:
        if hit.status == "running":
            return "in_progress", dict(_IN_PROGRESS)
        return "done", hit.result_json or {}

    key = _idempotency_key(conversation_id, tool_name, arguments)
    run = AssistantToolRun(
        id=str(uuid4()),
        conversation_id=conversation_id,
        message_id=None,
        tool_name=tool_name,
        arguments_json=arguments,
        result_json={},
        status="running",
        idempotency_key=key,
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
        return "reserved", run
    except IntegrityError:
        hit = _lookup_run(
            db, conversation_id=conversation_id, tool_name=tool_name, arguments=arguments
        )
        if hit is None:
            raise
        if hit.status == "running":
            return "in_progress", dict(_IN_PROGRESS)
        return "done", hit.result_json or {}


def _complete_run(run: AssistantToolRun, result: dict[str, Any], *, status: str = "ok") -> dict:
    run.result_json = result
    run.status = status
    return result


def _store_unavailable(
    db: Session,
    *,
    conversation_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result = calculation_unavailable_payload(tool_name=tool_name)
    return _store_run(
        db,
        conversation_id=conversation_id,
        tool_name=tool_name,
        arguments=arguments,
        result=result,
        status="unavailable",
    )


def get_event_context(db: Session, *, conversation_id: str, event_id: str, company_id: str) -> dict:
    args = {"event_id": event_id, "company_id": company_id}
    hit = _lookup_run(
        db, conversation_id=conversation_id, tool_name="get_event_context", arguments=args
    )
    if hit is not None:
        return hit.result_json or {}
    ctx = build_conversation_context(db, event_id=event_id, company_id=company_id)
    from app.services.assistant.provenance import NEWS_SOURCE

    result = {
        "event": ctx["event"],
        "sources": ctx["sources"],
        "company": {"id": ctx["company"]["id"], "name": ctx["company"]["name"]},
        "assessment_state": ctx.get("assessment_state"),
        "has_impact_calculation": bool(ctx.get("has_impact_calculation")),
        "labels": [NEWS_SOURCE],
    }
    return _store_run(
        db,
        conversation_id=conversation_id,
        tool_name="get_event_context",
        arguments=args,
        result=result,
    )


def get_company_impact(db: Session, *, conversation_id: str, event_id: str, company_id: str) -> dict:
    args = {"event_id": event_id, "company_id": company_id}
    hit = _lookup_run(
        db, conversation_id=conversation_id, tool_name="get_company_impact", arguments=args
    )
    if hit is not None:
        return hit.result_json or {}
    if lookup_usable_impact(db, event_id=event_id, company_id=company_id) is None:
        return _store_unavailable(
            db, conversation_id=conversation_id, tool_name="get_company_impact", arguments=args
        )
    ctx = build_conversation_context(db, event_id=event_id, company_id=company_id)
    from app.services.assistant.provenance import COMPANY_CALC

    result = {"impact": ctx["impact"], "available": True, "labels": [COMPANY_CALC]}
    return _store_run(
        db,
        conversation_id=conversation_id,
        tool_name="get_company_impact",
        arguments=args,
        result=result,
    )


def get_impact_paths(db: Session, *, conversation_id: str, event_id: str, company_id: str) -> dict:
    args = {"event_id": event_id, "company_id": company_id}
    hit = _lookup_run(
        db, conversation_id=conversation_id, tool_name="get_impact_paths", arguments=args
    )
    if hit is not None:
        return hit.result_json or {}
    if lookup_usable_impact(db, event_id=event_id, company_id=company_id) is None:
        return _store_unavailable(
            db, conversation_id=conversation_id, tool_name="get_impact_paths", arguments=args
        )
    ctx = build_conversation_context(db, event_id=event_id, company_id=company_id)
    result = {"paths": ctx["paths"], "available": True}
    return _store_run(
        db,
        conversation_id=conversation_id,
        tool_name="get_impact_paths",
        arguments=args,
        result=result,
    )


def list_solution_candidates(
    db: Session, *, conversation_id: str, event_id: str, company_id: str
) -> dict:
    args = {"event_id": event_id, "company_id": company_id}
    hit = _lookup_run(
        db, conversation_id=conversation_id, tool_name="list_solution_candidates", arguments=args
    )
    if hit is not None:
        return hit.result_json or {}
    if lookup_usable_impact(db, event_id=event_id, company_id=company_id) is None:
        return _store_unavailable(
            db,
            conversation_id=conversation_id,
            tool_name="list_solution_candidates",
            arguments=args,
        )
    ctx = build_conversation_context(db, event_id=event_id, company_id=company_id)
    result = {"solutions": ctx["solutions"], "available": True}
    return _store_run(
        db,
        conversation_id=conversation_id,
        tool_name="list_solution_candidates",
        arguments=args,
        result=result,
    )


def simulate_scenario(
    db: Session,
    *,
    conversation_id: str,
    event_id: str,
    company_id: str,
    solution_id: str | None = None,
    inventory_days: int = 14,
    delay_days: int = 45,
) -> dict:
    args = {
        "event_id": event_id,
        "company_id": company_id,
        "solution_id": solution_id,
        "inventory_days": inventory_days,
        "delay_days": delay_days,
    }
    hit = _lookup_run(
        db, conversation_id=conversation_id, tool_name="simulate_scenario", arguments=args
    )
    if hit is not None:
        return hit.result_json or {}

    impact = lookup_usable_impact(db, event_id=event_id, company_id=company_id)
    if impact is None:
        return _store_unavailable(
            db, conversation_id=conversation_id, tool_name="simulate_scenario", arguments=args
        )

    if impact.exposure_value is None:
        return _store_run(
            db,
            conversation_id=conversation_id,
            tool_name="simulate_scenario",
            arguments=args,
            result={
                "type": "missing_data",
                "fields": ["output_share_at_risk"],
                "message": "Недостаточно данных: нет доли выпуска под риском",
                "labels": ["estimate"],
            },
            status="missing_data",
        )

    solution = None
    if solution_id:
        solution = db.get(SolutionCandidate, solution_id)
        if solution is None or solution.event_impact_id != impact.id:
            raise AppError("NOT_FOUND", "Кандидат решения не найден", 404)

    sim = simulate(
        output_share_at_risk=impact.exposure_value,
        inventory_days=inventory_days,
        delay_days=delay_days,
        solution=solution,
    )
    result = {
        "source": "calculation",
        "scenario": sim,
        "labels": honesty_labels(
            is_estimate=True,
            is_demo=bool(solution.is_demo) if solution else True,
        ),
    }
    return _store_run(
        db,
        conversation_id=conversation_id,
        tool_name="simulate_scenario",
        arguments=args,
        result=result,
    )


def compare_scenarios(
    db: Session,
    *,
    conversation_id: str,
    event_id: str,
    company_id: str,
    inventory_days: int = 14,
    delay_days: int = 45,
    user_id: str,
    assumed_rate_change_pp: float | None = None,
    assumed_fx_change_percent: float | None = None,
) -> dict:
    """Simulate baseline + up to 3 alternatives. Idempotent — no duplicate Scenario rows.

    ``assumed_rate_change_pp`` — explicit key-rate what-if (percentage points).
    ``assumed_fx_change_percent`` — explicit FX what-if (%). Never inferred from severity.
    """
    args = {
        "event_id": event_id,
        "company_id": company_id,
        "inventory_days": inventory_days,
        "delay_days": delay_days,
        "assumed_rate_change_pp": assumed_rate_change_pp,
        "assumed_fx_change_percent": assumed_fx_change_percent,
    }
    state, payload = _reserve_run(
        db, conversation_id=conversation_id, tool_name="compare_scenarios", arguments=args
    )
    if state == "done":
        return payload  # type: ignore[return-value]
    if state == "in_progress":
        return payload  # type: ignore[return-value]
    run = payload  # type: ignore[assignment]
    assert isinstance(run, AssistantToolRun)

    from app.models import Event
    from app.services.financial_simulator import simulate_financial_scenarios
    from app.services.impact import (
        FINANCE_REQUIRED_KEYS,
        _optional_finance_for,
        assessment_state_for_impact,
    )

    impact = lookup_usable_impact(db, event_id=event_id, company_id=company_id)
    event = db.get(Event, event_id)
    if impact is None or event is None:
        result = calculation_unavailable_payload(tool_name="compare_scenarios")
        return _complete_run(run, result, status="unavailable")

    state = assessment_state_for_impact(db, event, impact)
    if state == "finance_data_required":
        from app.services.assistant.provenance import (
            COMPANY_CONTEXT,
            FINANCE_MISSING_CTA,
            FINANCE_MISSING_MESSAGE,
        )
        from app.services.impact import missing_finance_track_fields

        finance_preview = _optional_finance_for(db, company_id)
        missing_tracks = missing_finance_track_fields(finance_preview)
        missing_fields = list(
            dict.fromkeys([*missing_tracks.get("rate", []), *missing_tracks.get("fx", [])])
        )

        result = {
            "type": "missing_data",
            "fields": missing_fields or list(FINANCE_REQUIRED_KEYS),
            "missing_by_track": missing_tracks,
            "message": FINANCE_MISSING_MESSAGE,
            "assessment_state": state,
            "cta": dict(FINANCE_MISSING_CTA),
            "labels": [COMPANY_CONTEXT],
        }
        return _complete_run(run, result, status="missing_data")

    if state == "finance_ready":
        finance = _optional_finance_for(db, company_id)
        fin = simulate_financial_scenarios(
            event=event,
            optional_finance=finance,
            assumed_rate_change_pp=assumed_rate_change_pp,
            assumed_fx_change_percent=assumed_fx_change_percent,
        )
        from app.services.assistant.provenance import COMPANY_CALC

        from app.services.finance_scenario_presentation import (
            attach_presentation_to_scenarios,
            build_finance_scenario_presentation,
        )

        package_params = fin.get("parameters") or {}
        model_ver = fin.get("model_version", "sim-v1.0-finance-rate-v2")

        if fin.get("status") == "unavailable" or not (fin.get("scenarios") or []):
            params = package_params if isinstance(package_params, dict) else {}
            fx_change = params.get("fx_change") if isinstance(params.get("fx_change"), dict) else {}
            rc = params.get("rate_change") if isinstance(params.get("rate_change"), dict) else {}
            if fx_change.get("basis") in {"none", "conflict", "assumed", "observed"}:
                unavail_pres = build_finance_scenario_presentation(
                    results={
                        "track": "fx",
                        "fx_change_basis": fx_change.get("basis") or "none",
                    },
                    parameters=params,
                    model_version=str(model_ver) if model_ver else None,
                )
            else:
                basis = rc.get("basis") if isinstance(rc, dict) else "none"
                unavail_pres = build_finance_scenario_presentation(
                    results={"rate_change_basis": basis or "none"},
                    parameters=params,
                    model_version=str(model_ver) if model_ver else None,
                )
            result = {
                "type": "missing_data",
                "source": "financial_calculation",
                "status": "unavailable",
                "fields": list(fin.get("fields") or ["rate_change_observed_or_assumed"]),
                "message": (
                    unavail_pres.get("unavailable_message")
                    or fin.get("message")
                    or "Недостаточно оснований для денежного rate-сценария"
                ),
                "parameters": package_params,
                "presentation": unavail_pres,
                "scenarios": [],
                "scenario_ids": [],
                "assessment_state": state,
                "model_version": model_ver,
                "labels": [COMPANY_CALC],
            }
            return _complete_run(run, result, status="missing_data")

        persisted_ids: list[str] = []
        raw_scenarios: list[dict[str, Any]] = []
        for item in fin.get("scenarios") or []:
            sc = Scenario(
                id=str(uuid4()),
                company_id=company_id,
                event_id=event_id,
                solution_id=None,
                created_by=user_id,
                parameters_json={
                    "kind": "financial",
                    "action_id": item.get("action_id") or item.get("kind"),
                    "assistant_conversation_id": conversation_id,
                    **package_params,
                },
                results_json=item,
                model_version=str(model_ver),
                is_estimate=True,
            )
            db.add(sc)
            persisted_ids.append(sc.id)
            raw_scenarios.append(
                {
                    **item,
                    "scenario_id": sc.id,
                    "solution_id": None,
                    "solution_name": item.get("label"),
                    "labels": ["estimate"],
                    "model_version": str(model_ver),
                }
            )
        db.flush()
        scenarios = attach_presentation_to_scenarios(
            raw_scenarios,
            parameters=package_params if isinstance(package_params, dict) else {},
            model_version=str(model_ver),
        )

        result = {
            "source": "financial_calculation",
            "status": "ok",
            "scenarios": scenarios,
            "scenario_ids": persisted_ids,
            "parameters": package_params,
            "assessment_state": state,
            "model_version": model_ver,
            "labels": [COMPANY_CALC],
        }
        return _complete_run(run, result)

    if state != "supply_chain_ready" or impact.exposure_value is None:
        result = {
            "type": "missing_data",
            "fields": ["output_share_at_risk"],
            "message": "Недостаточно данных для сравнения сценариев поставки",
            "assessment_state": state,
            "labels": ["estimate"],
        }
        return _complete_run(run, result, status="missing_data")

    solutions = (
        db.query(SolutionCandidate)
        .filter(SolutionCandidate.event_impact_id == impact.id)
        .order_by(SolutionCandidate.sort_score.desc())
        .limit(3)
        .all()
    )

    scenarios = []
    baseline = simulate(
        output_share_at_risk=impact.exposure_value,
        inventory_days=inventory_days,
        delay_days=delay_days,
        solution=None,
    )
    scenarios.append({"kind": "baseline", **baseline})

    persisted_ids = []
    for sol in solutions:
        sim = simulate(
            output_share_at_risk=impact.exposure_value,
            inventory_days=inventory_days,
            delay_days=delay_days,
            solution=sol,
        )
        sc = Scenario(
            id=str(uuid4()),
            company_id=company_id,
            event_id=event_id,
            solution_id=sol.id,
            created_by=user_id,
            parameters_json={
                "inventory_days": inventory_days,
                "delay_days": delay_days,
                "solution_id": sol.id,
                "assistant_conversation_id": conversation_id,
            },
            results_json=sim,
            model_version=sim.get("model_version", "sim-v1.0"),
            is_estimate=True,
        )
        db.add(sc)
        persisted_ids.append(sc.id)
        scenarios.append(
            {
                **sim,
                "kind": "alternative",
                "scenario_id": sc.id,
                "solution_id": sol.id,
                "solution_name": sol.name,
                "availability_status": sol.availability_status,
                "labels": honesty_labels(is_demo=sol.is_demo, is_estimate=True),
            }
        )

    db.flush()
    from app.services.assistant.provenance import COMPANY_CALC

    result = {
        "source": "calculation",
        "scenarios": scenarios,
        "scenario_ids": persisted_ids,
        "assessment_state": state,
        "labels": [COMPANY_CALC],
    }
    return _complete_run(run, result)


def create_decision_draft(
    db: Session,
    *,
    conversation_id: str,
    event_id: str,
    company_id: str,
    user_id: str,
    scenario_id: str | None = None,
    solution_id: str | None = None,
    note: str | None = None,
    confirm: bool = False,
    client_request_id: str | None = None,
) -> dict:
    """Draft requires an existing scenario. Confirm creates Decision at most once."""
    args = {
        "event_id": event_id,
        "company_id": company_id,
        "scenario_id": scenario_id,
        "solution_id": solution_id,
        "note": note,
        "confirm": confirm,
        "client_request_id": client_request_id,
    }
    hit = _lookup_run(
        db, conversation_id=conversation_id, tool_name="create_decision_draft", arguments=args
    )
    if hit is not None:
        if hit.status == "running":
            return dict(_IN_PROGRESS)
        return hit.result_json or {}

    # No usable impact → cannot invent scenarios/decisions.
    if lookup_usable_impact(db, event_id=event_id, company_id=company_id) is None:
        return _store_unavailable(
            db,
            conversation_id=conversation_id,
            tool_name="create_decision_draft",
            arguments=args,
        )

    if not scenario_id:
        if solution_id:
            prior = (
                db.query(AssistantToolRun)
                .filter(
                    AssistantToolRun.conversation_id == conversation_id,
                    AssistantToolRun.tool_name == "compare_scenarios",
                    AssistantToolRun.status == "ok",
                )
                .order_by(AssistantToolRun.created_at.desc())
                .first()
            )
            if prior and prior.result_json:
                for sc in prior.result_json.get("scenarios") or []:
                    if sc.get("solution_id") == solution_id and sc.get("scenario_id"):
                        scenario_id = sc["scenario_id"]
                        break
        if not scenario_id:
            return _store_run(
                db,
                conversation_id=conversation_id,
                tool_name="create_decision_draft",
                arguments=args,
                result={
                    "type": "missing_data",
                    "fields": ["scenario_id"],
                    "message": "Сначала сравните сценарии и выберите вариант",
                    "status": "draft",
                    "decision_id": None,
                },
                status="missing_data",
            )

    scenario = db.get(Scenario, scenario_id)
    if scenario is None or scenario.company_id != company_id or scenario.event_id != event_id:
        raise AppError("NOT_FOUND", "Сценарий не найден", 404)

    plan_body = (
        "согласовать альтернативу, проверить совместимость, зафиксировать буфер."
    )
    draft_note = note or f"Черновик плана: {plan_body}"
    confirmed_note = note or f"Решение подтверждено. План: {plan_body}"

    draft = {
        "status": "draft",
        "scenario_id": scenario.id,
        "solution_id": scenario.solution_id,
        "note": draft_note,
        "expected_effect": (scenario.results_json or {}).get("comparison"),
        "calculation_results": scenario.results_json,
        "labels": honesty_labels(is_estimate=True, is_demo=True),
        "decision_id": None,
    }

    if not confirm:
        return _store_run(
            db,
            conversation_id=conversation_id,
            tool_name="create_decision_draft",
            arguments=args,
            result=draft,
        )

    existing_decision = (
        db.query(Decision)
        .filter(Decision.scenario_id == scenario.id)
        .order_by(Decision.created_at.asc())
        .first()
    )
    if existing_decision is not None:
        confirmed = {
            **draft,
            "status": "confirmed",
            "note": confirmed_note,
            "decision_id": existing_decision.id,
        }
        return _store_run(
            db,
            conversation_id=conversation_id,
            tool_name="create_decision_draft",
            arguments=args,
            result=confirmed,
        )

    decision = Decision(
        id=str(uuid4()),
        scenario_id=scenario.id,
        status="selected",
        decision_note=confirmed_note,
        created_by=user_id,
    )
    action_titles = [
        "Запросить коммерческое предложение у альтернативного поставщика",
        "Проверить совместимость компонента с линией №2",
        "Согласовать буферный запас на переходный период",
    ]
    try:
        with db.begin_nested():
            db.add(decision)
            for title in action_titles:
                db.add(
                    ActionItem(
                        id=str(uuid4()),
                        decision_id=decision.id,
                        title=title,
                        status="todo",
                        assignee_user_id=user_id,
                    )
                )
            db.flush()
    except IntegrityError:
        existing_decision = (
            db.query(Decision).filter(Decision.scenario_id == scenario.id).one()
        )
        confirmed = {
            **draft,
            "status": "confirmed",
            "note": confirmed_note,
            "decision_id": existing_decision.id,
        }
        return _store_run(
            db,
            conversation_id=conversation_id,
            tool_name="create_decision_draft",
            arguments=args,
            result=confirmed,
        )

    confirmed = {
        **draft,
        "status": "confirmed",
        "note": confirmed_note,
        "decision_id": decision.id,
    }
    return _store_run(
        db,
        conversation_id=conversation_id,
        tool_name="create_decision_draft",
        arguments=args,
        result=confirmed,
    )


def run_tool(
    db: Session,
    *,
    conversation_id: str,
    tool_name: str,
    event_id: str,
    company_id: str,
    user_id: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tool_name not in TOOL_NAMES:
        raise AppError("VALIDATION_ERROR", f"Неизвестный tool: {tool_name}", 400)
    args = arguments or {}

    if tool_name == "get_event_context":
        return get_event_context(
            db, conversation_id=conversation_id, event_id=event_id, company_id=company_id
        )
    if tool_name == "get_company_impact":
        return get_company_impact(
            db, conversation_id=conversation_id, event_id=event_id, company_id=company_id
        )
    if tool_name == "get_impact_paths":
        return get_impact_paths(
            db, conversation_id=conversation_id, event_id=event_id, company_id=company_id
        )
    if tool_name == "list_solution_candidates":
        return list_solution_candidates(
            db, conversation_id=conversation_id, event_id=event_id, company_id=company_id
        )
    if tool_name == "simulate_scenario":
        return simulate_scenario(
            db,
            conversation_id=conversation_id,
            event_id=event_id,
            company_id=company_id,
            solution_id=args.get("solution_id"),
            inventory_days=int(args.get("inventory_days", 14)),
            delay_days=int(args.get("delay_days", 45)),
        )
    if tool_name == "compare_scenarios":
        assumed_raw = args.get("assumed_rate_change_pp")
        assumed_pp: float | None
        try:
            assumed_pp = float(assumed_raw) if assumed_raw is not None else None
        except (TypeError, ValueError):
            assumed_pp = None
        fx_raw = args.get("assumed_fx_change_percent")
        assumed_fx: float | None
        try:
            assumed_fx = float(fx_raw) if fx_raw is not None else None
        except (TypeError, ValueError):
            assumed_fx = None
        return compare_scenarios(
            db,
            conversation_id=conversation_id,
            event_id=event_id,
            company_id=company_id,
            inventory_days=int(args.get("inventory_days", 14)),
            delay_days=int(args.get("delay_days", 45)),
            user_id=user_id,
            assumed_rate_change_pp=assumed_pp,
            assumed_fx_change_percent=assumed_fx,
        )
    if tool_name == "create_decision_draft":
        return create_decision_draft(
            db,
            conversation_id=conversation_id,
            event_id=event_id,
            company_id=company_id,
            user_id=user_id,
            scenario_id=args.get("scenario_id"),
            solution_id=args.get("solution_id"),
            note=args.get("note"),
            confirm=bool(args.get("confirm", False)),
            client_request_id=args.get("client_request_id"),
        )
    raise AppError("VALIDATION_ERROR", f"Tool не реализован: {tool_name}", 400)
