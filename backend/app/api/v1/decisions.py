from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_company_member
from app.core.errors import AppError
from app.db.session import get_db
from app.models import (
    ActionItem,
    AssistantConversation,
    Decision,
    Event,
    EventImpact,
    Scenario,
    SolutionCandidate,
    User,
)
from app.schemas.decision import (
    ActionItemOut,
    ActionItemPatchOut,
    DecisionCancelIn,
    DecisionDetailOut,
    DecisionEventOut,
    DecisionProgressOut,
    DecisionScenarioOut,
)
from app.schemas.event import ActionItemIn, ActionItemPatchIn, DecisionIn
from app.services.public_news import category_label

router = APIRouter(tags=["decisions"])

_STATUS_LABEL = {
    "todo": "Запланировано",
    "in_progress": "В работе",
    "done": "Выполнено",
}

_ALLOWED_ACTION_STATUS = {"todo", "in_progress", "done"}

# Product-confirmed Decision rows (draft lives only in assistant blocks until confirm).
# Cancelled plans stay in history but are never returned as the active event decision.
CONFIRMED_DECISION_STATUSES = frozenset({"selected", "confirmed", "accepted", "done"})
CANCELLED_DECISION_STATUS = "cancelled"


def _decision_status_label(status: str) -> str:
    if status == CANCELLED_DECISION_STATUS:
        return "План отменён"
    if status in CONFIRMED_DECISION_STATUSES:
        return "Решение принято"
    return "Решение в работе"


def _require_decision_company(db: Session, decision: Decision, user: User) -> Scenario:
    scenario = db.get(Scenario, decision.scenario_id)
    if scenario is None:
        raise AppError("NOT_FOUND", "Сценарий не найден", 404)
    require_company_member(scenario.company_id, db, user)
    return scenario


def _reject_if_cancelled(decision: Decision) -> None:
    if decision.status == CANCELLED_DECISION_STATUS:
        raise AppError(
            "CONFLICT",
            "План отменён — действия больше нельзя менять",
            409,
            details=[{"reason": "decision_cancelled"}],
        )


def _progress(items: list[ActionItem]) -> DecisionProgressOut:
    total = len(items)
    done = sum(1 for i in items if i.status == "done")
    return DecisionProgressOut(
        done=done,
        total=total,
        label=f"{done} из {total} действий" if total else "Нет действий",
    )


def _normalize_status(raw: str) -> str:
    if raw in ("completed", "done", "done_ok"):
        return "done"
    if raw in ("doing", "in_progress", "progress"):
        return "in_progress"
    return "todo" if raw in ("todo", "planned", "open", "") else (raw if raw in _ALLOWED_ACTION_STATUS else "todo")


def _assignee_name(db: Session, user_id: str | None) -> str | None:
    if not user_id:
        return None
    user = db.get(User, user_id)
    return user.display_name if user else None


def _action_out(db: Session, item: ActionItem) -> ActionItemOut:
    status = _normalize_status(item.status)
    return ActionItemOut(
        id=item.id,
        title=item.title,
        status=status,  # type: ignore[arg-type]
        status_label=_STATUS_LABEL.get(status, "Запланировано"),
        assignee_name=_assignee_name(db, item.assignee_user_id),
        due_at=item.due_at,
    )


def _is_finance_scenario(scenario: Scenario) -> bool:
    params = scenario.parameters_json or {}
    results = scenario.results_json or {}
    if params.get("kind") == "financial":
        return True
    if results.get("track") in {"rate", "fx"}:
        return True
    if results.get("rate_change_basis") is not None:
        return True
    if results.get("fx_change_basis") is not None:
        return True
    if results.get("annual_rate_sensitivity") is not None:
        return True
    if results.get("fx_value_change") is not None:
        return True
    if results.get("funding_pressure_percent") is not None:
        return True
    mv = str(scenario.model_version or "")
    if "finance" in mv:
        return True
    return False


def _finance_presentation(scenario: Scenario) -> dict:
    from app.services.finance_scenario_presentation import build_finance_scenario_presentation

    results = scenario.results_json if isinstance(scenario.results_json, dict) else {}
    params = scenario.parameters_json if isinstance(scenario.parameters_json, dict) else {}
    return build_finance_scenario_presentation(
        results=results,
        parameters=params,
        model_version=scenario.model_version,
        label=results.get("label") if isinstance(results.get("label"), str) else None,
    )


def _decision_title(scenario: Scenario, solution: SolutionCandidate | None, note: str | None) -> str:
    if note and note.strip():
        short = note.strip()
        if len(short) <= 80 and not short.lower().startswith("черновик"):
            return short
    results = scenario.results_json or {}
    if _is_finance_scenario(scenario):
        label = results.get("label") or results.get("solution_name")
        if isinstance(label, str) and label.strip():
            return label.strip()
        return "Финансовый сценарий по ставке"
    alt = results.get("alternative") if isinstance(results.get("alternative"), dict) else {}
    label = alt.get("label") or alt.get("name")
    if isinstance(label, str) and label.strip():
        return label.strip()
    if solution is not None and solution.name:
        return solution.name
    comparison = results.get("comparison") if isinstance(results.get("comparison"), dict) else {}
    delta = comparison.get("stop_risk_delta")
    if isinstance(delta, (int, float)) and delta < 0:
        return "Снизить риск остановки производства"
    return "Принятое решение"


def _expected_effect(scenario: Scenario) -> str | None:
    if _is_finance_scenario(scenario):
        return _finance_presentation(scenario).get("expected_effect")
    results = scenario.results_json or {}
    comparison = results.get("comparison") if isinstance(results.get("comparison"), dict) else {}
    delta = comparison.get("stop_risk_delta")
    if isinstance(delta, (int, float)):
        if delta < 0:
            return "Снижение риска остановки"
        if delta > 0:
            return "Рост риска остановки"
    alt = results.get("alternative") if isinstance(results.get("alternative"), dict) else {}
    stop = alt.get("stop_risk_percent")
    base = results.get("baseline") if isinstance(results.get("baseline"), dict) else {}
    base_stop = base.get("stop_risk_percent")
    if isinstance(stop, (int, float)) and isinstance(base_stop, (int, float)) and stop < base_stop:
        return "Снижение риска остановки"
    return None


def _horizon(scenario: Scenario, solution: SolutionCandidate | None) -> str | None:
    if _is_finance_scenario(scenario):
        return _finance_presentation(scenario).get("decision_horizon")
    results = scenario.results_json or {}
    alt = results.get("alternative") if isinstance(results.get("alternative"), dict) else {}
    days = alt.get("lead_time_days")
    if not isinstance(days, int) and solution is not None:
        days = solution.lead_time_days
    if isinstance(days, int) and days > 0:
        if days <= 14:
            return "Ближайшие 14 дней"
        if days <= 30:
            return "Ближайший месяц"
        return f"Около {days} дней"
    return "Ближайшие 14 дней"


def _scenario_reason(scenario: Scenario, solution: SolutionCandidate | None, note: str | None) -> str:
    if _is_finance_scenario(scenario):
        return str(_finance_presentation(scenario).get("decision_reason") or "")
    results = scenario.results_json or {}
    comparison = results.get("comparison") if isinstance(results.get("comparison"), dict) else {}
    tradeoff = comparison.get("tradeoff")
    if isinstance(tradeoff, str) and tradeoff.strip():
        return f"Выбран вариант с лучшим балансом: {tradeoff.strip()}."
    if solution is not None:
        parts = [f"Альтернатива: {solution.name}"]
        if solution.country:
            parts.append(f"страна — {solution.country}")
        return ". ".join(parts) + "."
    if note and note.strip():
        return note.strip()
    return "Сценарий выбран по результатам сравнения вариантов влияния."


def _build_detail(db: Session, decision: Decision, user: User) -> DecisionDetailOut:
    scenario = _require_decision_company(db, decision, user)

    event = db.get(Event, scenario.event_id)
    if event is None:
        raise AppError("NOT_FOUND", "Событие не найдено", 404)

    solution = db.get(SolutionCandidate, scenario.solution_id) if scenario.solution_id else None
    items = (
        db.query(ActionItem)
        .filter(ActionItem.decision_id == decision.id)
        .order_by(ActionItem.created_at.asc())
        .all()
    )
    impact = (
        db.query(EventImpact)
        .filter(
            EventImpact.event_id == scenario.event_id,
            EventImpact.company_id == scenario.company_id,
        )
        .first()
    )
    conversation = (
        db.query(AssistantConversation)
        .filter(
            AssistantConversation.user_id == user.id,
            AssistantConversation.company_id == scenario.company_id,
            AssistantConversation.event_id == scenario.event_id,
            AssistantConversation.status == "active",
        )
        .order_by(AssistantConversation.updated_at.desc())
        .first()
    )

    title = _decision_title(scenario, solution, decision.decision_note)
    # Reason should stay explanatory; do not reuse a short title-note.
    note_for_reason = decision.decision_note
    if note_for_reason and note_for_reason.strip() == title:
        note_for_reason = None
    reason = _scenario_reason(scenario, solution, note_for_reason)
    summary = reason
    progress = _progress(items)
    cancelled = decision.status == CANCELLED_DECISION_STATUS
    disclaimer = (
        "План отменён и сохранён в истории. Он больше не считается активным решением."
        if cancelled
        else "План действий сохранён. Числовые оценки — расчётные и не являются финансовой гарантией."
    )

    return DecisionDetailOut(
        id=decision.id,
        status=decision.status,
        status_label=_decision_status_label(decision.status),
        title=title,
        summary=summary,
        expected_effect=_expected_effect(scenario),
        horizon=_horizon(scenario, solution),
        confidence=float(impact.confidence) if impact is not None else None,
        progress=progress,
        event=DecisionEventOut(
            id=event.id,
            title=event.title,
            category=event.category,
            category_label=category_label(event.category),
            occurred_at=event.occurred_at,
            is_demo=bool(event.is_demo),
        ),
        scenario=DecisionScenarioOut(
            id=scenario.id,
            title=_decision_title(scenario, solution, None),
            reason=reason,
            is_estimate=bool(scenario.is_estimate),
            presentation=(
                _finance_presentation(scenario) if _is_finance_scenario(scenario) else None
            ),
            model_version=scenario.model_version,
        ),
        action_items=[_action_out(db, i) for i in items],
        conversation_href=f"/events/{event.id}/assistant",
        news_href=f"/news/{event.id}",
        created_at=decision.created_at,
        disclaimer=disclaimer,
        cancelled_at=decision.cancelled_at,
        cancel_reason=decision.cancel_reason,
        actions_locked=cancelled,
    )


@router.post("/decisions")
def create_decision(
    body: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    scenario = db.get(Scenario, body.scenario_id)
    if scenario is None:
        raise AppError("NOT_FOUND", "Сценарий не найден", 404)
    require_company_member(scenario.company_id, db, user)

    decision = Decision(
        id=str(uuid4()),
        scenario_id=scenario.id,
        status=body.status,
        decision_note=body.decision_note,
        created_by=user.id,
    )
    db.add(decision)
    defaults = [
        "Запросить коммерческое предложение у альтернативного поставщика",
        "Проверить совместимость компонента с линией №2",
        "Согласовать буферный запас на переходный период",
    ]
    for title in defaults:
        db.add(
            ActionItem(
                id=str(uuid4()),
                decision_id=decision.id,
                title=title,
                status="todo",
                assignee_user_id=user.id,
            )
        )
    db.commit()
    db.refresh(decision)
    return _build_detail(db, decision, user).model_dump(mode="json")


@router.get("/decisions/{decision_id}", response_model=DecisionDetailOut)
def get_decision(
    decision_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DecisionDetailOut:
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise AppError("NOT_FOUND", "Решение не найдено", 404)
    return _build_detail(db, decision, user)


@router.get(
    "/events/{event_id}/decision",
    response_model=DecisionDetailOut,
    summary="Confirmed decision for event",
    description=(
        "Returns the latest **confirmed** decision for the event and company. "
        "Confirmed statuses: selected, confirmed, accepted, done. "
        "Cancelled plans are excluded. "
        "Ordering: created_at DESC, id DESC. "
        "Draft / incomplete plans are not returned — clients must not treat a missing "
        "decision as an actionable plan. Use 404 when no confirmed decision exists."
    ),
)
def get_decision_for_event(
    event_id: str,
    company_id: str = Query(..., description="Company the caller belongs to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DecisionDetailOut:
    require_company_member(company_id, db, user)
    scenario_ids = [
        s.id
        for s in db.query(Scenario.id)
        .filter(Scenario.company_id == company_id, Scenario.event_id == event_id)
        .all()
    ]
    if not scenario_ids:
        raise AppError("NOT_FOUND", "Решение по событию не найдено", 404)

    # Active confirmed only — drafts and cancelled plans must not deep-link from event cards.
    decision = (
        db.query(Decision)
        .filter(
            Decision.scenario_id.in_(scenario_ids),
            Decision.status.in_(tuple(CONFIRMED_DECISION_STATUSES)),
        )
        .order_by(Decision.created_at.desc(), Decision.id.desc())
        .first()
    )
    if decision is None:
        raise AppError("NOT_FOUND", "Подтверждённое решение по событию не найдено", 404)
    return _build_detail(db, decision, user)


@router.post(
    "/decisions/{decision_id}/cancel",
    response_model=DecisionDetailOut,
    summary="Cancel confirmed decision",
)
def cancel_decision(
    decision_id: str,
    body: DecisionCancelIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DecisionDetailOut:
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise AppError("NOT_FOUND", "Решение не найдено", 404)
    _require_decision_company(db, decision, user)

    # Idempotent: already cancelled → return current detail, do not rewrite fields.
    if decision.status == CANCELLED_DECISION_STATUS:
        return _build_detail(db, decision, user)

    if decision.status not in CONFIRMED_DECISION_STATUSES:
        raise AppError(
            "CONFLICT",
            "Отменить можно только активный подтверждённый план",
            409,
            details=[{"reason": "not_active_confirmed"}],
        )

    payload = body or DecisionCancelIn()
    reason = (payload.reason or "").strip() or None
    if reason and len(reason) > 1000:
        raise AppError("VALIDATION_ERROR", "Слишком длинная причина отмены", 400)

    decision.status = CANCELLED_DECISION_STATUS
    decision.cancelled_at = datetime.now(timezone.utc)
    decision.cancelled_by_user_id = user.id
    decision.cancel_reason = reason
    db.commit()
    db.refresh(decision)
    return _build_detail(db, decision, user)


@router.post("/decisions/{decision_id}/action-items")
def add_action_item(
    decision_id: str,
    body: ActionItemIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise AppError("NOT_FOUND", "Решение не найдено", 404)
    _require_decision_company(db, decision, user)
    _reject_if_cancelled(decision)
    item = ActionItem(
        id=str(uuid4()),
        decision_id=decision_id,
        title=body.title,
        status="todo",
        assignee_user_id=body.assignee_user_id or user.id,
        due_at=body.due_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _action_out(db, item).model_dump(mode="json")


@router.patch("/action-items/{action_item_id}", response_model=ActionItemPatchOut)
def patch_action_item(
    action_item_id: str,
    body: ActionItemPatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ActionItemPatchOut:
    item = db.get(ActionItem, action_item_id)
    if item is None:
        raise AppError("NOT_FOUND", "Шаг не найден", 404)
    decision = db.get(Decision, item.decision_id)
    if decision is None:
        raise AppError("NOT_FOUND", "Решение не найдено", 404)
    _require_decision_company(db, decision, user)
    _reject_if_cancelled(decision)

    payload = body.model_dump(exclude_unset=True)
    if "status" in payload and payload["status"] is not None:
        status = _normalize_status(str(payload["status"]))
        if status not in _ALLOWED_ACTION_STATUS:
            raise AppError("VALIDATION_ERROR", "Недопустимый статус действия", 400)
        payload["status"] = status
    for field, value in payload.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)

    items = (
        db.query(ActionItem)
        .filter(ActionItem.decision_id == item.decision_id)
        .order_by(ActionItem.created_at.asc())
        .all()
    )
    out = _action_out(db, item)
    return ActionItemPatchOut(
        id=out.id,
        title=out.title,
        status=out.status,
        status_label=out.status_label,
        assignee_name=out.assignee_name,
        due_at=out.due_at,
        progress=_progress(items),
    )
