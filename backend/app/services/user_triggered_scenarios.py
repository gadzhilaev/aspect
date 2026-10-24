"""User-triggered scenario comparison without LLM (stage 6.6).

Calls ``compare_scenarios`` directly after ACL checks. Does not add write-tools
to the agent-loop allow-list and does not invoke providers.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import AssistantMessage, AssistantToolRun, User
from app.services.assistant.orchestrator import (
    _blocks_from_tool_result,
    _msg_out,
    _touch,
    get_conversation_for_user,
)
from app.services.assistant.tools import compare_scenarios

USER_COMPARE_TOOL = "user_compare_scenarios"
SYSTEM_CALC_CONTENT = "Расчёт по вашему запросу"

# Sanity bounds only — do not change 5.2/5.4 formulas.
MAX_ABS_RATE_CHANGE_PP = 20.0
MAX_ABS_FX_CHANGE_PERCENT = 100.0


def _request_idempotency_key(conversation_id: str, client_request_id: str) -> str:
    payload = json.dumps(
        {"c": conversation_id, "t": USER_COMPARE_TOOL, "rid": client_request_id},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


def _param_fingerprint(args: dict[str, Any]) -> str:
    relevant = {
        "assumed_rate_change_pp": args.get("assumed_rate_change_pp"),
        "assumed_fx_change_percent": args.get("assumed_fx_change_percent"),
        "inventory_days": args.get("inventory_days"),
        "delay_days": args.get("delay_days"),
        "event_id": args.get("event_id"),
        "company_id": args.get("company_id"),
    }
    raw = json.dumps(relevant, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_what_if(
    *,
    assumed_rate_change_pp: float | None,
    assumed_fx_change_percent: float | None,
) -> None:
    if assumed_rate_change_pp is not None:
        if abs(float(assumed_rate_change_pp)) > MAX_ABS_RATE_CHANGE_PP:
            raise AppError(
                "VALIDATION_ERROR",
                f"Допущение по ставке: не больше ±{MAX_ABS_RATE_CHANGE_PP:g} п.п.",
                400,
                details=[{"field": "assumed_rate_change_pp", "unit": "percentage_points"}],
            )
    if assumed_fx_change_percent is not None:
        if abs(float(assumed_fx_change_percent)) > MAX_ABS_FX_CHANGE_PERCENT:
            raise AppError(
                "VALIDATION_ERROR",
                f"Допущение по курсу: не больше ±{MAX_ABS_FX_CHANGE_PERCENT:g} %",
                400,
                details=[{"field": "assumed_fx_change_percent", "unit": "percent"}],
            )


def run_user_compare_scenarios(
    db: Session,
    *,
    conversation_id: str,
    user: User,
    client_request_id: str,
    assumed_rate_change_pp: float | None = None,
    assumed_fx_change_percent: float | None = None,
    inventory_days: int = 14,
    delay_days: int = 45,
) -> dict[str, Any]:
    """POST handler body: ACL → idempotent compare → system transcript block."""
    client_request_id = (client_request_id or "").strip()
    if not client_request_id:
        raise AppError(
            "VALIDATION_ERROR",
            "client_request_id обязателен для пользовательского расчёта сценариев",
            400,
        )

    _validate_what_if(
        assumed_rate_change_pp=assumed_rate_change_pp,
        assumed_fx_change_percent=assumed_fx_change_percent,
    )

    conv = get_conversation_for_user(db, conversation_id=conversation_id, user=user)

    full_args: dict[str, Any] = {
        "client_request_id": client_request_id,
        "event_id": conv.event_id,
        "company_id": conv.company_id,
        "inventory_days": int(inventory_days),
        "delay_days": int(delay_days),
        "assumed_rate_change_pp": assumed_rate_change_pp,
        "assumed_fx_change_percent": assumed_fx_change_percent,
        "param_fingerprint": None,
    }
    full_args["param_fingerprint"] = _param_fingerprint(full_args)

    key = _request_idempotency_key(conv.id, client_request_id)
    existing = (
        db.query(AssistantToolRun)
        .filter(
            AssistantToolRun.conversation_id == conv.id,
            AssistantToolRun.tool_name == USER_COMPARE_TOOL,
            AssistantToolRun.idempotency_key == key,
        )
        .one_or_none()
    )

    if existing is not None:
        stored = dict(existing.arguments_json or {})
        if stored.get("param_fingerprint") != full_args["param_fingerprint"]:
            raise AppError(
                "USER_COMPARE_REQUEST_CONFLICT",
                "Тот же client_request_id уже использован с другими параметрами расчёта",
                409,
                details=[
                    {
                        "client_request_id": client_request_id,
                        "reason": "param_mismatch",
                    }
                ],
            )
        if existing.status == "running":
            return {
                "status": "running",
                "reused": False,
                "result": {
                    "type": "operation_in_progress",
                    "message": "Расчёт сценариев уже выполняется — повторите через мгновение",
                    "status": "running",
                },
                "message": None,
                "decision_created": False,
            }
        result = dict(existing.result_json or {})
        msg = None
        mid = existing.message_id
        if mid:
            msg_row = db.get(AssistantMessage, mid)
            if msg_row is not None:
                msg = _msg_out(msg_row)
        return {
            "status": existing.status,
            "reused": True,
            "result": result,
            "message": msg,
            "decision_created": False,
            "scenario_ids": list(result.get("scenario_ids") or []),
        }

    run = AssistantToolRun(
        id=str(uuid4()),
        conversation_id=conv.id,
        message_id=None,
        tool_name=USER_COMPARE_TOOL,
        arguments_json=full_args,
        result_json={},
        status="running",
        idempotency_key=key,
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        # Concurrent double-click — re-enter via lookup path.
        return run_user_compare_scenarios(
            db,
            conversation_id=conversation_id,
            user=user,
            client_request_id=client_request_id,
            assumed_rate_change_pp=assumed_rate_change_pp,
            assumed_fx_change_percent=assumed_fx_change_percent,
            inventory_days=inventory_days,
            delay_days=delay_days,
        )

    # Direct server calculation — no provider / agent-loop tools.
    calc = compare_scenarios(
        db,
        conversation_id=conv.id,
        event_id=conv.event_id,
        company_id=conv.company_id,
        inventory_days=inventory_days,
        delay_days=delay_days,
        user_id=user.id,
        assumed_rate_change_pp=assumed_rate_change_pp,
        assumed_fx_change_percent=assumed_fx_change_percent,
    )

    if calc.get("type") == "operation_in_progress":
        # Do not leave a stuck "running" user request; client may retry shortly.
        db.delete(run)
        db.commit()
        return {
            "status": "running",
            "reused": False,
            "result": calc,
            "message": None,
            "decision_created": False,
            "scenario_ids": [],
        }

    status = "ok"
    if calc.get("type") == "missing_data":
        status = "missing_data"
    elif calc.get("type") == "tool_unavailable" or calc.get("unavailable_reason"):
        status = "unavailable"
    elif calc.get("status") == "unavailable":
        status = "missing_data"

    blocks = _blocks_from_tool_result("compare_scenarios", calc)
    # Mark block title for finance/system presentation.
    for b in blocks:
        if b.get("type") == "scenario_comparison":
            b["title"] = "Расчёт по вашему запросу"
            data = dict(b.get("data") or {})
            data["user_triggered"] = True
            data["not_ai_message"] = True
            b["data"] = data
        elif b.get("type") == "missing_data":
            data = dict(b.get("data") or {})
            data["user_triggered"] = True
            data["not_ai_message"] = True
            b["data"] = data

    assistant_msg = AssistantMessage(
        id=str(uuid4()),
        conversation_id=conv.id,
        role="system",
        content=SYSTEM_CALC_CONTENT,
        blocks_json=blocks,
        client_message_id=f"user-compare:{client_request_id}",
    )
    db.add(assistant_msg)
    db.flush()

    run.result_json = calc
    run.status = status
    run.message_id = assistant_msg.id
    _touch(conv)
    db.commit()
    db.refresh(assistant_msg)

    return {
        "status": status,
        "reused": False,
        "result": calc,
        "message": _msg_out(assistant_msg),
        "decision_created": False,
        "scenario_ids": list(calc.get("scenario_ids") or []),
        "next_step": _next_step(calc, status),
    }


def _next_step(calc: dict[str, Any], status: str) -> str | None:
    if status == "ok" and calc.get("scenarios"):
        return "select_scenario_then_draft_decision"
    if calc.get("assessment_state") == "finance_data_required" or (
        calc.get("type") == "missing_data" and calc.get("cta")
    ):
        return "open_finance_setup"
    if status in {"missing_data", "unavailable"}:
        return "resolve_missing_basis_or_profile"
    return None
