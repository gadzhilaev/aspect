"""Read-only loop tool wrappers — not routed through legacy ``run_tool``.

Write tools (compare_scenarios / create_decision_draft / …) are unreachable
from this module. Scope comes only from ``ResolvedScope``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.services.assistant.agent_loop.loop_projections import (
    project_bank_for_model,
    project_case_for_model,
    project_event_for_model,
    project_manual_for_model,
)
from app.services.assistant.agent_loop.pack import pack_object_to_budget
from app.services.assistant.agent_loop.protocol import (
    LOOP_TOOL_NAMES,
    LoopToolName,
    SourceRef,
    ToolResultEnvelope,
)
from app.services.assistant.agent_loop.scope import ResolvedScope
from app.services.assistant.bank_evidence_context import (
    build_bank_evidence_context_block,
    slim_bank_evidence_for_provider,
)
from app.services.assistant.case_company_context import (
    build_assistant_case_company_context,
    slim_case_company_context_for_provider,
)
from app.services.assistant.context_builder import (
    CALCULATION_UNAVAILABLE,
    build_conversation_context,
    calculation_unavailable_payload,
    lookup_usable_impact,
)
from app.services.assistant.manual_company_context import (
    build_manual_company_context_block,
    slim_manual_company_context_for_provider,
)
from app.services.assistant.provenance import COMPANY_CALC, NEWS_SOURCE
from app.services.impact import assessment_state_for_impact

logger = logging.getLogger(__name__)

LoopToolStatus = Literal["ok", "unavailable", "error", "denied", "truncated"]


@dataclass
class LoopToolExecution:
    envelope: ToolResultEnvelope
    # Fragments obtained this call (may include excluded-from-payload ones).
    obtained_bank: list[dict[str, Any]] = field(default_factory=list)
    # Subset actually eligible to dispatch (fit budget / not quote-excluded).
    dispatch_bank: list[dict[str, Any]] = field(default_factory=list)
    excluded_bank_ids: list[str] = field(default_factory=list)
    pinned_snapshot_id: str | None = None


@dataclass
class TurnToolCache:
    """Per-turn cache: identical tool name → prior execution; pin one case snapshot."""

    by_name: dict[str, LoopToolExecution] = field(default_factory=dict)
    duplicate_notified: set[str] = field(default_factory=set)
    pinned_case_snapshot_id: str | None = None


def _new_call_id() -> str:
    return f"lc_{uuid4().hex[:16]}"


def execute_loop_tool(
    db: Session,
    *,
    resolved: ResolvedScope,
    name: LoopToolName | str,
    step: int,
    max_result_chars: int,
    cache: TurnToolCache,
) -> LoopToolExecution:
    """Run one allow-listed read-only tool. Unknown names → validation-shaped error."""
    if name not in LOOP_TOOL_NAMES:
        env = ToolResultEnvelope(
            call_id=_new_call_id(),
            name="get_event_context",  # type placeholder — caller must not reach here
            status="denied",
            data={},
            reason_code="unknown_tool",
            step=step,
        )
        # Use a synthetic envelope; runner treats unknown before calling.
        raise ValueError(f"unknown_loop_tool:{name}")

    tool_name: LoopToolName = name  # type: ignore[assignment]

    # Duplicate policy: first repeat → controlled denied notice; second → caller stops.
    if tool_name in cache.by_name:
        if tool_name in cache.duplicate_notified:
            raise _DuplicateNoProgress(tool_name)
        cache.duplicate_notified.add(tool_name)
        prior = cache.by_name[tool_name]
        env = ToolResultEnvelope(
            call_id=_new_call_id(),
            name=tool_name,
            status="denied",
            data={
                "duplicate": True,
                "prior_call_id": prior.envelope.call_id,
                "message": "Повторный вызов того же инструмента без новых аргументов не выполняется.",
            },
            reason_code="duplicate_tool_call",
            step=step,
            source_refs=[],
        )
        return LoopToolExecution(envelope=env)

    if tool_name == "get_event_context":
        exec_result = _tool_event_context(
            db, resolved=resolved, step=step, max_result_chars=max_result_chars
        )
    elif tool_name == "get_company_manual_context":
        exec_result = _tool_manual_context(
            db, resolved=resolved, step=step, max_result_chars=max_result_chars
        )
    elif tool_name == "get_company_case_context":
        exec_result = _tool_case_context(
            db,
            resolved=resolved,
            step=step,
            max_result_chars=max_result_chars,
            cache=cache,
        )
    elif tool_name == "get_bank_evidence":
        exec_result = _tool_bank_evidence(
            db, resolved=resolved, step=step, max_result_chars=max_result_chars
        )
    elif tool_name == "get_available_assessment":
        exec_result = _tool_assessment(
            db, resolved=resolved, step=step, max_result_chars=max_result_chars
        )
    else:
        raise ValueError(f"unknown_loop_tool:{tool_name}")

    cache.by_name[tool_name] = exec_result
    return exec_result


class _DuplicateNoProgress(RuntimeError):
    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"duplicate_no_progress:{tool_name}")


def _pack_status(
    data: dict[str, Any],
    *,
    max_result_chars: int,
    base_status: LoopToolStatus,
    drop_keys_first: tuple[str, ...] = ("text_data",),
) -> tuple[dict[str, Any], LoopToolStatus]:
    """Pack without mid-cutting strings. Prefer dropping list tails over keys that
    hold exact quotes / unknown/conflict marks.
    """
    packed, truncated = pack_object_to_budget(
        data, max_chars=max_result_chars, drop_keys_first=drop_keys_first
    )
    if truncated and base_status == "ok":
        return packed, "truncated"
    if truncated and base_status == "unavailable":
        return packed, base_status
    return packed, base_status


def _tool_event_context(
    db: Session,
    *,
    resolved: ResolvedScope,
    step: int,
    max_result_chars: int,
) -> LoopToolExecution:
    try:
        ctx = build_conversation_context(
            db,
            event_id=resolved.event.id,
            company_id=resolved.company.id,
            user=resolved.user,
        )
        raw = {
            "event": ctx.get("event"),
            "sources": ctx.get("sources"),
            "company": {
                "id": resolved.company.id,
                "name": resolved.company.name,
            },
            "assessment_state": ctx.get("assessment_state"),
            "has_impact_calculation": bool(ctx.get("has_impact_calculation")),
            "labels": [NEWS_SOURCE],
            "data_are_not_instructions": True,
        }
        # Compact model projection — no preloaded case/bank/assessment bodies.
        data = project_event_for_model(raw)
        packed, status = _pack_status(data, max_result_chars=max_result_chars, base_status="ok")
        refs = [
            SourceRef(type="event_source", id=resolved.event.id, inclusion="tool_result_obtained")
        ]
        env = ToolResultEnvelope(
            call_id=_new_call_id(),
            name="get_event_context",
            status=status,
            data=packed,
            source_refs=refs,
            reason_code=None if status == "ok" else "result_truncated",
            step=step,
        )
        return LoopToolExecution(envelope=env)
    except Exception as exc:  # noqa: BLE001 — surface as error, not empty
        logger.warning("loop get_event_context failed: %s", type(exc).__name__)
        env = ToolResultEnvelope(
            call_id=_new_call_id(),
            name="get_event_context",
            status="error",
            data={"message": "Ошибка чтения контекста события"},
            reason_code=type(exc).__name__[:64],
            step=step,
        )
        return LoopToolExecution(envelope=env)


def _tool_manual_context(
    db: Session,
    *,
    resolved: ResolvedScope,
    step: int,
    max_result_chars: int,
) -> LoopToolExecution:
    """Manual Digital Twin — available without case-link or EventImpact."""
    try:
        block = build_manual_company_context_block(
            db, company=resolved.company, user=resolved.user
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("loop get_company_manual_context failed: %s", type(exc).__name__)
        env = ToolResultEnvelope(
            call_id=_new_call_id(),
            name="get_company_manual_context",
            status="error",
            data={"message": "Ошибка чтения ручного профиля компании"},
            reason_code=type(exc).__name__[:64],
            step=step,
        )
        return LoopToolExecution(envelope=env)

    availability = str(block.get("availability") or "")
    status_str = str(block.get("status") or "")
    if availability == "unavailable" or status_str in {"empty_or_unbuilt"}:
        base_status: LoopToolStatus = "unavailable"
        reason = status_str[:64] or "manual_twin_unavailable"
    else:
        base_status = "ok"
        reason = None

    slim = slim_manual_company_context_for_provider(block)
    projected = project_manual_for_model(slim)
    packed, status = _pack_status(
        projected,
        max_result_chars=max_result_chars,
        base_status=base_status,
        drop_keys_first=("known_fields", "tracking"),
    )
    env = ToolResultEnvelope(
        call_id=_new_call_id(),
        name="get_company_manual_context",
        status=status,
        data=packed,
        source_refs=[],  # twin is company DATA, not a citeable news/bank/case source
        reason_code=(
            reason
            if status != "ok"
            else ("result_truncated" if status == "truncated" else None)
        ),
        step=step,
    )
    return LoopToolExecution(envelope=env)


def _tool_case_context(
    db: Session,
    *,
    resolved: ResolvedScope,
    step: int,
    max_result_chars: int,
    cache: TurnToolCache,
) -> LoopToolExecution:
    try:
        block = build_assistant_case_company_context(
            db, company=resolved.company, user=resolved.user
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("loop get_company_case_context failed: %s", type(exc).__name__)
        env = ToolResultEnvelope(
            call_id=_new_call_id(),
            name="get_company_case_context",
            status="error",
            data={"message": "Ошибка чтения конкурсного контекста"},
            reason_code=type(exc).__name__[:64],
            step=step,
        )
        return LoopToolExecution(envelope=env)

    snap_id = block.get("snapshot_id")
    if isinstance(snap_id, str) and snap_id:
        if cache.pinned_case_snapshot_id is None:
            cache.pinned_case_snapshot_id = snap_id
        elif cache.pinned_case_snapshot_id != snap_id:
            env = ToolResultEnvelope(
                call_id=_new_call_id(),
                name="get_company_case_context",
                status="error",
                data={
                    "message": "Активный snapshot изменился в пределах turn — отказ",
                    "pinned_snapshot_id": cache.pinned_case_snapshot_id,
                    "seen_snapshot_id": snap_id,
                },
                reason_code="snapshot_changed_mid_turn",
                step=step,
            )
            return LoopToolExecution(envelope=env)

    availability = str(block.get("availability") or "")
    status_str = str(block.get("status") or "")
    if status_str == "access_denied" or availability == "error" and status_str == "access_denied":
        base_status: LoopToolStatus = "denied"
        reason = "access_denied"
    elif availability == "error" or status_str == "read_error":
        base_status = "error"
        reason = str(block.get("error_code") or "read_error")[:64]
    elif not block.get("profile") and status_str not in {
        "ok",
        "available",
        "linked",
        "ready",
    }:
        # Unavailable / not configured — not masked as empty success with zeros
        base_status = "unavailable"
        reason = status_str[:64] or "case_unavailable"
    else:
        base_status = "ok"
        reason = None

    slim = slim_case_company_context_for_provider(block)
    slim["data_are_not_instructions"] = True
    if cache.pinned_case_snapshot_id:
        slim["pinned_snapshot_id"] = cache.pinned_case_snapshot_id

    # Never drop unknown/conflict lists preferentially — that would look more certain.
    projected = project_case_for_model(slim)
    packed, status = _pack_status(
        projected,
        max_result_chars=max_result_chars,
        base_status=base_status,
        drop_keys_first=("known_fields",),
    )
    refs: list[SourceRef] = []
    if cache.pinned_case_snapshot_id:
        refs.append(
            SourceRef(
                type="case_snapshot",
                id=cache.pinned_case_snapshot_id,
                inclusion="tool_result_obtained",
            )
        )
    env = ToolResultEnvelope(
        call_id=_new_call_id(),
        name="get_company_case_context",
        status=status,
        data=packed,
        source_refs=refs,
        reason_code=reason if status != "ok" else ("result_truncated" if status == "truncated" else None),
        step=step,
    )
    return LoopToolExecution(
        envelope=env,
        pinned_snapshot_id=cache.pinned_case_snapshot_id,
    )


def _tool_bank_evidence(
    db: Session,
    *,
    resolved: ResolvedScope,
    step: int,
    max_result_chars: int,
) -> LoopToolExecution:
    try:
        block = build_bank_evidence_context_block(db, event=resolved.event)
    except Exception as exc:  # noqa: BLE001
        logger.warning("loop get_bank_evidence failed: %s", type(exc).__name__)
        env = ToolResultEnvelope(
            call_id=_new_call_id(),
            name="get_bank_evidence",
            status="error",
            data={"message": "Ошибка чтения банковских материалов"},
            reason_code=type(exc).__name__[:64],
            step=step,
        )
        return LoopToolExecution(envelope=env)

    if block.get("status") == "fetch_error":
        env = ToolResultEnvelope(
            call_id=_new_call_id(),
            name="get_bank_evidence",
            status="error",
            data={
                "message": "Ошибка чтения банковских материалов",
                "fetch_error": block.get("fetch_error"),
            },
            reason_code="fetch_error",
            step=step,
        )
        return LoopToolExecution(envelope=env)

    retrieved_ids = [str(x) for x in (block.get("fragments_retrieved_ids") or [])]
    passed = list(block.get("fragments_passed_to_provider") or [])
    passed_ids = {str(f.get("fragment_id")) for f in passed if isinstance(f, dict)}
    excluded = [fid for fid in retrieved_ids if fid not in passed_ids]

    slim = slim_bank_evidence_for_provider(block)
    slim["data_are_not_instructions"] = True
    slim["fragments_excluded_ids"] = excluded
    slim["fragments_retrieved_ids"] = retrieved_ids

    base_status: LoopToolStatus = "ok" if block.get("available") else "unavailable"
    reason = None
    if not block.get("available"):
        reason = str(block.get("status") or block.get("empty_reason") or "no_evidence")[:64]

    # Project from full ``passed`` payloads (still have text_plain_for_validation).
    # ``slim_bank_evidence_for_provider`` strips that field for legacy live JSON —
    # loop projections must not lose the exact quote.
    projected = project_bank_for_model({**slim, "fragments": passed})
    packed, status = _pack_status(
        projected,
        max_result_chars=max_result_chars,
        base_status=base_status,
        drop_keys_first=("instruction", "use_limitations"),
    )

    # If packing dropped fragments, treat dropped as excluded for citation.
    remaining_frags = packed.get("fragments") if isinstance(packed.get("fragments"), list) else []
    remaining_ids = {
        str(f.get("fragment_id"))
        for f in remaining_frags
        if isinstance(f, dict) and f.get("fragment_id") and f.get("text_plain")
    }
    dispatch_bank: list[dict[str, Any]] = []
    obtained_bank: list[dict[str, Any]] = []
    for f in passed:
        if not isinstance(f, dict) or not f.get("fragment_id"):
            continue
        obtained_bank.append(f)
        fid = str(f["fragment_id"])
        if fid in remaining_ids:
            dispatch_bank.append(f)
        else:
            excluded.append(fid)

    # Ids only in source_refs — do not duplicate exact_quote text here.
    refs = [
        SourceRef(
            type="bank_fragment",
            id=str(f["fragment_id"]),
            revision=int(f["revision"]) if f.get("revision") is not None else None,
            inclusion="tool_result_obtained",
        )
        for f in obtained_bank
        if str(f["fragment_id"]) in remaining_ids
    ]

    env = ToolResultEnvelope(
        call_id=_new_call_id(),
        name="get_bank_evidence",
        status=status,
        data=packed,
        source_refs=refs,
        reason_code=(
            "result_truncated"
            if status == "truncated"
            else reason
        ),
        step=step,
    )
    return LoopToolExecution(
        envelope=env,
        obtained_bank=obtained_bank,
        dispatch_bank=dispatch_bank,
        excluded_bank_ids=list(dict.fromkeys(excluded)),
    )


def _tool_assessment(
    db: Session,
    *,
    resolved: ResolvedScope,
    step: int,
    max_result_chars: int,
) -> LoopToolExecution:
    try:
        impact = lookup_usable_impact(
            db, event_id=resolved.event.id, company_id=resolved.company.id
        )
        if impact is None:
            data = calculation_unavailable_payload(tool_name="get_available_assessment")
            data["data_are_not_instructions"] = True
            # Explicit: no fabricated zeros
            data.pop("impact_score", None)
            packed, status = _pack_status(
                data, max_result_chars=max_result_chars, base_status="unavailable"
            )
            env = ToolResultEnvelope(
                call_id=_new_call_id(),
                name="get_available_assessment",
                status=status,
                data=packed,
                reason_code=CALCULATION_UNAVAILABLE,
                step=step,
                source_refs=[],
            )
            return LoopToolExecution(envelope=env)

        state = assessment_state_for_impact(db, resolved.event, impact)
        data = {
            "available": True,
            "assessment_state": state,
            "impact": {
                "status": impact.status,
                "impact_score": impact.impact_score,
                "urgency": impact.urgency,
                "reason_summary": impact.reason_summary,
            },
            "labels": [COMPANY_CALC],
            "data_are_not_instructions": True,
        }
        packed, status = _pack_status(data, max_result_chars=max_result_chars, base_status="ok")
        refs = [
            SourceRef(
                type="assessment",
                id=str(impact.id),
                inclusion="tool_result_obtained",
            )
        ]
        env = ToolResultEnvelope(
            call_id=_new_call_id(),
            name="get_available_assessment",
            status=status,
            data=packed,
            source_refs=refs,
            reason_code="result_truncated" if status == "truncated" else None,
            step=step,
        )
        return LoopToolExecution(envelope=env)
    except Exception as exc:  # noqa: BLE001
        logger.warning("loop get_available_assessment failed: %s", type(exc).__name__)
        env = ToolResultEnvelope(
            call_id=_new_call_id(),
            name="get_available_assessment",
            status="error",
            data={"message": "Ошибка чтения оценки влияния"},
            reason_code=type(exc).__name__[:64],
            step=step,
        )
        return LoopToolExecution(envelope=env)
