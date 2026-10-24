"""Conversation orchestration: get-or-create, messages, draft decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.deps import require_company_member
from app.core.errors import AppError
from app.models import AssistantConversation, AssistantMessage, Event, EventImpact, User
from app.schemas.assistant import (
    AssistantBlock,
    AssistantConversationListItem,
    AssistantConversationOut,
    AssistantMessageOut,
    ConversationListStatus,
    DraftDecisionOut,
    PostMessageOut,
)
from app.services.assistant.bank_evidence_citations import (
    validate_bank_evidence_citations,
    validated_to_public_dicts,
)
from app.services.assistant.bank_evidence_context import (
    passed_fragment_index,
    slim_bank_evidence_for_provider,
)
from app.services.assistant.case_company_context import case_context_ref_message_block
from app.services.assistant.context_builder import build_conversation_context, slim_live_context
from app.services.assistant.prompts import chips_for_assessment, opening_for_assessment
from app.services.assistant.gigachat import GigaChatProvider
from app.services.assistant.hackathon import HackathonProvider, is_retryable_bad_response
from app.services.assistant.provider import (
    LiveAssistantProvider,
    MockAssistantProvider,
    ProviderMessage,
    get_provider,
)
from app.services.assistant.provenance import (
    BANK_MATERIAL,
    COMPANY_CALC,
    COMPANY_CONTEXT,
    FINANCE_MISSING_CTA,
    FINANCE_MISSING_MESSAGE,
    explanation_basis,
    merge_tool_labels,
    sanitize_labels_for_client,
)
from app.services.assistant.tools import create_decision_draft, run_tool
from app.services.impact import assessment_state_for_impact
from app.services.scenario_display import (
    format_scenario_comparison_lines,
    sanitize_ui_text,
)
from app.core.config import get_settings


def _msg_out(m: AssistantMessage) -> AssistantMessageOut:
    blocks = []
    for b in m.blocks_json or []:
        if not (isinstance(b, dict) and b.get("type")):
            continue
        data = b.get("data")
        # DB-only pairing for loop idempotency — never expose to clients.
        if (
            isinstance(data, dict)
            and data.get("internal_reply_link") is True
        ):
            continue
        raw = dict(b)
        raw["labels"] = sanitize_labels_for_client(list(raw.get("labels") or []))
        blocks.append(AssistantBlock.model_validate(raw))
    return AssistantMessageOut(
        id=m.id,
        role=m.role,
        content=m.content or "",
        blocks=blocks,
        client_message_id=m.client_message_id,
        created_at=m.created_at,
    )


def _answer_basis() -> str:
    return explanation_basis(provider=get_settings().normalized_assistant_provider())


def _answer_model() -> str | None:
    """Actual model id for honest provenance (hackathon only)."""
    settings = get_settings()
    if settings.normalized_assistant_provider() != "hackathon":
        return None
    return settings.resolved_hackathon_model()


def _assessment_for_conversation(db: Session, conv: AssistantConversation) -> str:
    from app.services.assistant.context_builder import (
        CALCULATION_UNAVAILABLE,
        lookup_usable_impact,
    )

    impact = lookup_usable_impact(
        db, event_id=conv.event_id, company_id=conv.company_id
    )
    event = db.get(Event, conv.event_id)
    if impact is None or event is None:
        # Distinct from monitoring_only (which implies an impact row without a path).
        return CALCULATION_UNAVAILABLE
    return assessment_state_for_impact(db, event, impact)


def _conversation_out(
    c: AssistantConversation,
    *,
    suggestion_chips: list[str] | None = None,
    assessment_state: str | None = None,
    has_impact_calculation: bool | None = None,
) -> AssistantConversationOut:
    state = assessment_state
    has_calc = has_impact_calculation
    if state is None:
        state = "supply_chain_ready"
    if has_calc is None:
        has_calc = state != "calculation_unavailable"
    return AssistantConversationOut(
        id=c.id,
        user_id=c.user_id,
        company_id=c.company_id,
        event_id=c.event_id,
        status=c.status,
        created_at=c.created_at,
        updated_at=c.updated_at,
        suggestion_chips=list(suggestion_chips or chips_for_assessment(state)),
        answer_basis=_answer_basis(),  # type: ignore[arg-type]
        answer_model=_answer_model(),
        assessment_state=state,
        has_impact_calculation=bool(has_calc),
    )


def _touch(conv: AssistantConversation) -> None:
    conv.updated_at = datetime.now(timezone.utc)


def get_conversation_for_user(
    db: Session, *, conversation_id: str, user: User
) -> AssistantConversation:
    conv = db.get(AssistantConversation, conversation_id)
    if conv is None:
        raise AppError("NOT_FOUND", "Разговор не найден", 404)
    if conv.user_id != user.id:
        raise AppError("FORBIDDEN", "Нет доступа к этому разговору", 403)
    require_company_member(conv.company_id, db, user)
    return conv


def get_or_create_conversation(
    db: Session,
    *,
    user: User,
    company_id: str,
    event_id: str,
) -> tuple[AssistantConversation, bool]:
    require_company_member(company_id, db, user)
    event = db.get(Event, event_id)
    if event is None:
        raise AppError("NOT_FOUND", "Событие не найдено", 404)

    existing_rows = (
        db.query(AssistantConversation)
        .filter(
            AssistantConversation.user_id == user.id,
            AssistantConversation.company_id == company_id,
            AssistantConversation.event_id == event_id,
            AssistantConversation.status == "active",
        )
        .order_by(AssistantConversation.created_at.asc())
        .all()
    )
    if existing_rows:
        primary = existing_rows[0]
        # Heal accidental duplicates from concurrent creates
        for dup in existing_rows[1:]:
            dup.status = "archived"
        if len(existing_rows) > 1:
            db.commit()
            db.refresh(primary)
        return primary, False

    # Build grounding without creating EventImpact or triggering recompute.
    from app.services.assistant.context_builder import (
        CALCULATION_UNAVAILABLE,
        lookup_usable_impact,
    )

    build_conversation_context(
        db, event_id=event_id, company_id=company_id, user=user
    )

    conv = AssistantConversation(
        id=str(uuid4()),
        user_id=user.id,
        company_id=company_id,
        event_id=event_id,
        status="active",
    )
    db.add(conv)
    db.flush()

    impact_row = lookup_usable_impact(db, event_id=event_id, company_id=company_id)
    state = (
        assessment_state_for_impact(db, event, impact_row)
        if impact_row is not None
        else CALCULATION_UNAVAILABLE
    )
    opening_blocks: list[dict[str, Any]] = []
    if state == "finance_data_required":
        opening_blocks.append(
            {
                "type": "missing_data",
                "title": "Недостаточно данных",
                "data": {
                    "message": FINANCE_MISSING_MESSAGE,
                    "cta": dict(FINANCE_MISSING_CTA),
                    "assessment_state": state,
                },
                "labels": [COMPANY_CONTEXT],
            }
        )
    elif state == CALCULATION_UNAVAILABLE:
        opening_blocks.append(
            {
                "type": "missing_data",
                "title": "Расчётная оценка отсутствует",
                "data": {
                    "message": (
                        "Персональный расчёт влияния для этой компании по событию "
                        "ещё не выполнен. Можно обсудить событие и контекст компании; "
                        "численные сценарии недоступны. Отсутствие расчёта не означает, "
                        "что событие безопасно."
                    ),
                    "assessment_state": CALCULATION_UNAVAILABLE,
                    "has_impact_calculation": False,
                },
                "labels": [COMPANY_CONTEXT],
            }
        )

    opening = AssistantMessage(
        id=str(uuid4()),
        conversation_id=conv.id,
        role="assistant",
        content=opening_for_assessment(state),
        blocks_json=opening_blocks,
        client_message_id=None,
    )
    db.add(opening)
    _touch(conv)
    db.commit()
    db.refresh(conv)
    return conv, True


def list_messages(db: Session, *, conversation_id: str, user: User) -> list[AssistantMessageOut]:
    conv = get_conversation_for_user(db, conversation_id=conversation_id, user=user)
    rows = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conv.id)
        .order_by(AssistantMessage.created_at.asc())
        .all()
    )
    return [_msg_out(m) for m in rows]


def _bank_evidence_message_block(
    *,
    bank_block: dict[str, Any],
    citation_check,
) -> dict[str, Any] | None:
    """Persist bank evidence diagnostics + validated citations (pinned revisions).

    Distinguishes retrieved / passed / cited_by_model / validated.
    Does not auto-attach all retrieved fragments as «used sources».
    """
    status = str(bank_block.get("status") or "integration_not_configured")
    passed = list(bank_block.get("fragments_passed_to_provider") or [])
    retrieved_ids = list(bank_block.get("fragments_retrieved_ids") or [])
    validated = validated_to_public_dicts(list(citation_check.validated))
    rejected = [
        {"fragment_id": r.fragment_id, "reason": r.reason}
        for r in citation_check.rejected
    ]

    # Always emit a compact block when bank integration was consulted this turn,
    # so the client can show unavailability without implying bank analytics were used.
    data: dict[str, Any] = {
        "status": status,
        "available": bool(bank_block.get("available")),
        "event_occurred_at": bank_block.get("event_occurred_at"),
        "as_of_date": bank_block.get("as_of_date"),
        "as_of_date_basis": bank_block.get("as_of_date_basis"),
        "used": validated,
        "diagnostics": {
            "retrieved_count": int(bank_block.get("retrieved_count") or 0),
            "retrieved_ids": retrieved_ids,
            "passed_to_provider_ids": [
                str(f.get("fragment_id"))
                for f in passed
                if isinstance(f, dict) and f.get("fragment_id")
            ],
            "cited_by_model": list(citation_check.cited_by_model),
            "validated_ids": [v.fragment_id for v in citation_check.validated],
            "rejected": rejected,
        },
        "limitations": list(bank_block.get("use_limitations") or [])[:10],
        "provenance_note": (
            "Validated fragment IDs prove link provenance and revision snapshot; "
            "they do not prove that the source supports every model claim."
        ),
    }
    if bank_block.get("fetch_error"):
        data["fetch_error"] = bank_block.get("fetch_error")
        data["available"] = False

    title = "Материалы банка"
    if status == "fetch_error":
        title = "Материалы банка недоступны"
    elif status != "available" or not validated:
        if status in {
            "no_matching_evidence",
            "integration_not_configured",
            "event_date_unavailable",
        }:
            title = "Материалы банка не использованы"

    return {
        "type": "bank_evidence_list",
        "title": title,
        "data": data,
        "labels": [BANK_MATERIAL],
    }


def _dedupe_source_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep a single Источники card with unique publishers/URLs."""
    from app.services.assistant.provenance import NEWS_SOURCE

    sources: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in blocks:
        if block.get("type") != "source_list":
            rest.append(block)
            continue
        data = block.get("data") if isinstance(block.get("data"), dict) else {}
        for src in data.get("sources") or []:
            if not isinstance(src, dict):
                continue
            url = str(src.get("url") or "").strip()
            pub = str(src.get("publisher") or "").strip().lower()
            key = url or f"{pub}|{src.get('published_at') or ''}"
            if not key or key in seen:
                continue
            seen.add(key)
            sources.append(src)
    if not sources:
        return rest
    rest.append(
        {
            "type": "source_list",
            "title": "Источники",
            "data": {"sources": sources},
            "labels": [NEWS_SOURCE],
        }
    )
    return rest


def _blocks_from_tool_result(tool_name: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    labels = merge_tool_labels(tool_name, result)

    if result.get("type") == "missing_data":
        data = dict(result)
        if data.get("assessment_state") == "finance_data_required":
            data["message"] = data.get("message") or FINANCE_MISSING_MESSAGE
            data["cta"] = data.get("cta") or dict(FINANCE_MISSING_CTA)
        return [
            {
                "type": "missing_data",
                "title": "Недостаточно данных",
                "data": data,
                "labels": labels,
            }
        ]

    if result.get("type") == "tool_unavailable" or result.get("unavailable_reason") == "calculation_unavailable":
        return [
            {
                "type": "missing_data",
                "title": "Расчёт недоступен",
                "data": dict(result),
                "labels": labels or [COMPANY_CONTEXT],
            }
        ]

    if result.get("type") == "operation_in_progress":
        return [
            {
                "type": "missing_data",
                "title": "Операция выполняется",
                "data": result,
                "labels": [COMPANY_CALC],
            }
        ]

    if tool_name == "compare_scenarios":
        assessment = result.get("assessment_state")
        source = result.get("source")
        if not assessment:
            if source == "financial_calculation":
                assessment = "finance_ready"
            elif source == "calculation":
                assessment = "supply_chain_ready"
        data: dict[str, Any] = {
            "source": source,
            "scenarios": result.get("scenarios"),
            "scenario_ids": result.get("scenario_ids"),
            "assessment_state": assessment,
        }
        if result.get("parameters") is not None:
            data["parameters"] = result.get("parameters")
        if result.get("model_version") is not None:
            data["model_version"] = result.get("model_version")
        if result.get("presentation") is not None:
            data["presentation"] = result.get("presentation")
        if result.get("status") is not None:
            data["status"] = result.get("status")
        if result.get("message") is not None:
            data["message"] = result.get("message")
        return [
            {
                "type": "scenario_comparison",
                "title": "Сравнение сценариев",
                "data": data,
                "labels": labels or [COMPANY_CALC],
            }
        ]

    if tool_name == "create_decision_draft":
        return [
            {
                "type": "action_plan_draft",
                "title": "Черновик решения" if result.get("status") == "draft" else "Решение сохранено",
                "data": result,
                "labels": labels or [COMPANY_CALC],
            }
        ]

    if tool_name == "get_company_impact":
        return [
            {
                "type": "impact_summary",
                "title": "Влияние",
                "data": result.get("impact") or result,
                "labels": labels or [COMPANY_CALC],
            }
        ]

    if tool_name == "get_impact_paths":
        return [
            {
                "type": "claim_list",
                "title": "Цепочки влияния",
                "data": {"paths": result.get("paths") or []},
                "labels": labels or [COMPANY_CONTEXT],
            }
        ]

    if tool_name == "get_event_context":
        from app.services.assistant.provenance import NEWS_SOURCE

        return [
            {
                "type": "source_list",
                "title": "Источники",
                "data": {"sources": result.get("sources") or []},
                "labels": labels or [NEWS_SOURCE],
            }
        ]

    if tool_name == "simulate_scenario":
        return [
            {
                "type": "scenario_comparison",
                "title": "Расчёт сценария",
                "data": result,
                "labels": labels or [COMPANY_CALC],
            }
        ]

    return []


def post_message(
    db: Session,
    *,
    conversation_id: str,
    user: User,
    content: str,
    client_message_id: str | None = None,
) -> PostMessageOut:
    settings = get_settings()
    if settings.assistant_agent_loop:
        from app.services.assistant.agent_loop.api_integration import post_message_agent_loop

        return post_message_agent_loop(
            db,
            conversation_id=conversation_id,
            user=user,
            content=content,
            client_message_id=client_message_id,
        )

    conv = get_conversation_for_user(db, conversation_id=conversation_id, user=user)

    if client_message_id:
        existing = (
            db.query(AssistantMessage)
            .filter(
                AssistantMessage.conversation_id == conv.id,
                AssistantMessage.client_message_id == client_message_id,
            )
            .one_or_none()
        )
        if existing is not None:
            # Return existing user message + following assistant reply if present
            assistant = (
                db.query(AssistantMessage)
                .filter(
                    AssistantMessage.conversation_id == conv.id,
                    AssistantMessage.role == "assistant",
                    AssistantMessage.created_at >= existing.created_at,
                    AssistantMessage.id != existing.id,
                )
                .order_by(AssistantMessage.created_at.asc())
                .first()
            )
            if assistant is None:
                assistant = existing
            return PostMessageOut(
                user_message=_msg_out(existing),
                assistant_message=_msg_out(assistant),
                reused=True,
            )

    user_msg = AssistantMessage(
        id=str(uuid4()),
        conversation_id=conv.id,
        role="user",
        content=content.strip(),
        blocks_json=[],
        client_message_id=client_message_id,
    )
    db.add(user_msg)
    db.flush()

    context = build_conversation_context(
        db, event_id=conv.event_id, company_id=conv.company_id, user=user
    )
    history_rows = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conv.id)
        .order_by(AssistantMessage.created_at.asc())
        .all()
    )
    history = [
        ProviderMessage(role=m.role, content=m.content or "", blocks=list(m.blocks_json or []))
        for m in history_rows
        if m.role in {"user", "assistant"}
    ]

    provider = get_provider()
    is_live = isinstance(
        provider, (LiveAssistantProvider, GigaChatProvider, HackathonProvider)
    )
    provider_context = slim_live_context(context) if is_live else context
    # Shared budget: at most one extra model HTTP per user message
    # (retryable empty/bad completion OR citation fix — not both, not stacked).
    # Provider / transport / budget / auth do not add independent retry loops.
    extra_model_http_used = False
    try:
        result = provider.generate(
            context=provider_context, history=history, user_text=content
        )
    except AppError as first_err:
        if (
            is_live
            and not isinstance(provider, MockAssistantProvider)
            and is_retryable_bad_response(first_err)
            and not extra_model_http_used
        ):
            extra_model_http_used = True
            result = provider.generate(
                context=provider_context, history=history, user_text=content
            )
        else:
            raise

    bank_block = context.get("bank_evidence") if isinstance(context.get("bank_evidence"), dict) else {}
    passed_idx = passed_fragment_index(bank_block)
    citation_check = validate_bank_evidence_citations(
        list(result.bank_evidence_citations or []),
        passed_index=passed_idx,
    )
    # Citation-fix retry shares the same one-extra-HTTP budget.
    # Budget exceeded / unauthorized are never retried (raised inside provider).
    if (
        citation_check.rejected
        and is_live
        and not isinstance(provider, MockAssistantProvider)
        and not extra_model_http_used
    ):
        extra_model_http_used = True
        retry_context = dict(provider_context)
        be = dict(retry_context.get("bank_evidence") or slim_bank_evidence_for_provider(bank_block))
        be["citation_retry_note"] = (
            "Previous bank_evidence_citations were rejected by the server. "
            "Cite only fragment_id values from bank_evidence.fragments; "
            "do not invent IDs, URLs, or alter exact quotes."
        )
        retry_context["bank_evidence"] = be
        result = provider.generate(
            context=retry_context, history=history, user_text=content
        )
        citation_check = validate_bank_evidence_citations(
            list(result.bank_evidence_citations or []),
            passed_index=passed_idx,
        )
        # Still-invalid citations are dropped — never published as confirmed.

    blocks: list[dict[str, Any]] = list(result.blocks or [])
    for call in result.tool_calls or []:
        name = call.get("name")
        if not name:
            continue
        tool_result = run_tool(
            db,
            conversation_id=conv.id,
            tool_name=name,
            event_id=conv.event_id,
            company_id=conv.company_id,
            user_id=user.id,
            arguments=call.get("arguments") or {},
        )
        blocks.extend(_blocks_from_tool_result(name, tool_result))

        # Enrich content with typed metrics (finance vs supply-chain) — never None%
        if name == "compare_scenarios" and tool_result.get("scenarios"):
            lines = format_scenario_comparison_lines(
                list(tool_result.get("scenarios") or []),
                assessment_state=tool_result.get("assessment_state"),
                source=tool_result.get("source"),
                parameters=(
                    tool_result.get("parameters")
                    if isinstance(tool_result.get("parameters"), dict)
                    else None
                ),
                model_version=(
                    str(tool_result["model_version"])
                    if tool_result.get("model_version") is not None
                    else None
                ),
            )
            if lines:
                result.content = (result.content or "") + "\n" + "\n".join(lines)

    blocks = _dedupe_source_blocks(blocks)
    bank_block_out = _bank_evidence_message_block(
        bank_block=bank_block,
        citation_check=citation_check,
    )
    if bank_block_out is not None:
        blocks.append(bank_block_out)

    case_block = (
        context.get("case_company_context")
        if isinstance(context.get("case_company_context"), dict)
        else None
    )
    case_ref = case_context_ref_message_block(case_block)
    if case_ref is not None:
        # Bind only this new answer to the frozen snapshot — never rewrite older messages.
        blocks.append(case_ref)

    assistant_msg = AssistantMessage(
        id=str(uuid4()),
        conversation_id=conv.id,
        role="assistant",
        content=result.content or "",
        blocks_json=blocks,
        client_message_id=None,
    )
    db.add(assistant_msg)
    _touch(conv)
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)

    return PostMessageOut(
        user_message=_msg_out(user_msg),
        assistant_message=_msg_out(assistant_msg),
        reused=False,
    )


def draft_decision(
    db: Session,
    *,
    conversation_id: str,
    user: User,
    scenario_id: str | None = None,
    solution_id: str | None = None,
    note: str | None = None,
    confirm: bool = False,
    client_request_id: str | None = None,
) -> DraftDecisionOut:
    from app.services.assistant.context_builder import lookup_usable_impact

    conv = get_conversation_for_user(db, conversation_id=conversation_id, user=user)

    if lookup_usable_impact(db, event_id=conv.event_id, company_id=conv.company_id) is None:
        raise AppError(
            "CALCULATION_UNAVAILABLE",
            "Расчётная оценка влияния отсутствует — черновик решения и сценарии недоступны",
            409,
        )

    if not scenario_id and not solution_id:
        raise AppError(
            "VALIDATION_ERROR",
            "Выберите сценарий после сравнения — без этого черновик не подготовить",
            400,
        )

    result = create_decision_draft(
        db,
        conversation_id=conv.id,
        event_id=conv.event_id,
        company_id=conv.company_id,
        user_id=user.id,
        scenario_id=scenario_id,
        solution_id=solution_id,
        note=note,
        confirm=confirm,
        client_request_id=client_request_id,
    )

    status = "confirmed" if result.get("status") == "confirmed" else "draft"
    client_msg_id = f"draft:{client_request_id}" if client_request_id else None

    if client_msg_id:
        existing = (
            db.query(AssistantMessage)
            .filter(
                AssistantMessage.conversation_id == conv.id,
                AssistantMessage.client_message_id == client_msg_id,
            )
            .one_or_none()
        )
        if existing is not None:
            return DraftDecisionOut(
                status=status,  # type: ignore[arg-type]
                decision_id=result.get("decision_id"),
                draft=result,
                message=_msg_out(existing),
                disclaimer="Оценки демонстрационные. Подтверждённое решение создаётся только явно.",
            )

    assistant_msg = AssistantMessage(
        id=str(uuid4()),
        conversation_id=conv.id,
        role="assistant",
        content=(
            "Черновик решения подготовлен. Нажмите «Подтвердить и сохранить», чтобы зафиксировать план."
            if status == "draft"
            else "Решение подтверждено и сохранено."
        ),
        blocks_json=_blocks_from_tool_result("create_decision_draft", result),
        client_message_id=client_msg_id,
    )
    db.add(assistant_msg)
    _touch(conv)
    db.commit()
    db.refresh(assistant_msg)

    return DraftDecisionOut(
        status=status,  # type: ignore[arg-type]
        decision_id=result.get("decision_id"),
        draft=result,
        message=_msg_out(assistant_msg),
        disclaimer="Оценки демонстрационные. Подтверждённое решение создаётся только явно.",
    )


def conversation_to_out(db: Session, conv: AssistantConversation) -> AssistantConversationOut:
    state = _assessment_for_conversation(db, conv)
    chips = chips_for_assessment(state)
    return _conversation_out(
        conv,
        suggestion_chips=chips,
        assessment_state=state,
        has_impact_calculation=state != "calculation_unavailable",
    )


_PREVIEW_MAX = 160


def _preview_text(content: str) -> str:
    text = sanitize_ui_text(" ".join((content or "").split()))
    if len(text) <= _PREVIEW_MAX:
        return text
    return text[: _PREVIEW_MAX - 1].rstrip() + "…"


def _derive_list_status(
    messages: list[AssistantMessage],
) -> tuple[ConversationListStatus, str | None, bool]:
    has_scenarios = False
    has_draft = False
    decision_id: str | None = None
    for msg in messages:
        for block in msg.blocks_json or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            data = block.get("data") if isinstance(block.get("data"), dict) else {}
            if btype == "scenario_comparison":
                has_scenarios = True
            if btype == "action_plan_draft":
                status = data.get("status")
                if status == "confirmed" and data.get("decision_id"):
                    decision_id = str(data["decision_id"])
                    return "decision_saved", decision_id, True
                if status == "draft":
                    has_draft = True
                    if data.get("decision_id"):
                        decision_id = str(data["decision_id"])
    if has_draft:
        return "draft_ready", decision_id, True
    if has_scenarios:
        return "scenarios_ready", None, True
    return "active", None, False


def list_conversations_for_company(
    db: Session, *, user: User, company_id: str
) -> list[AssistantConversationListItem]:
    require_company_member(company_id, db, user)

    rows = (
        db.query(AssistantConversation)
        .filter(
            AssistantConversation.user_id == user.id,
            AssistantConversation.company_id == company_id,
            AssistantConversation.status == "active",
        )
        .order_by(AssistantConversation.updated_at.desc())
        .all()
    )
    if not rows:
        return []

    # One visible chat per event: keep newest, archive accidental duplicates
    seen_events: set[str] = set()
    unique_rows: list[AssistantConversation] = []
    archived = False
    for conv in rows:
        if conv.event_id in seen_events:
            conv.status = "archived"
            archived = True
            continue
        seen_events.add(conv.event_id)
        unique_rows.append(conv)
    if archived:
        db.commit()
    rows = unique_rows

    event_ids = {c.event_id for c in rows}
    events = {
        e.id: e
        for e in db.query(Event).filter(Event.id.in_(event_ids)).all()
    }
    impacts = {
        (i.event_id, i.company_id): i
        for i in db.query(EventImpact)
        .filter(
            EventImpact.company_id == company_id,
            EventImpact.event_id.in_(event_ids),
        )
        .all()
    }
    conv_ids = [c.id for c in rows]
    messages = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id.in_(conv_ids))
        .order_by(AssistantMessage.created_at.asc())
        .all()
    )
    by_conv: dict[str, list[AssistantMessage]] = {cid: [] for cid in conv_ids}
    for m in messages:
        by_conv.setdefault(m.conversation_id, []).append(m)

    # Resolve cancelled decisions so scenarios history stays accurate without rewriting chat blocks.
    derived: dict[str, tuple[ConversationListStatus, str | None, bool]] = {}
    need_decision_ids: set[str] = set()
    for conv in rows:
        st, did, hs = _derive_list_status(by_conv.get(conv.id, []))
        derived[conv.id] = (st, did, hs)
        if did:
            need_decision_ids.add(did)

    cancelled_ids: set[str] = set()
    if need_decision_ids:
        from app.models import Decision

        for row in (
            db.query(Decision.id, Decision.status)
            .filter(Decision.id.in_(need_decision_ids))
            .all()
        ):
            if row.status == "cancelled":
                cancelled_ids.add(row.id)

    items: list[AssistantConversationListItem] = []
    for conv in rows:
        status, decision_id, has_scenarios = derived[conv.id]
        if decision_id and decision_id in cancelled_ids:
            status = "decision_cancelled"
        preview = ""
        for m in reversed(by_conv.get(conv.id, [])):
            if m.role in ("user", "assistant") and (m.content or "").strip():
                preview = _preview_text(m.content)
                break
        event = events.get(conv.event_id)
        impact = impacts.get((conv.event_id, company_id))
        from app.services.impact import IMPACT_STATUS_NOT_RELEVANT

        usable = (
            impact is not None and impact.status != IMPACT_STATUS_NOT_RELEVANT
        )
        # Absent / not_relevant → null scores (never coerce unknown to 0).
        items.append(
            AssistantConversationListItem(
                id=conv.id,
                event_id=conv.event_id,
                event_title=event.title if event else conv.event_id,
                event_category=event.category if event else "",
                updated_at=conv.updated_at,
                last_message_preview=preview,
                status=status,
                decision_id=decision_id,
                impact_score=float(impact.impact_score) if usable else None,
                confidence=float(impact.confidence) if usable else None,
                has_impact_calculation=usable,
                assessment_state=(
                    assessment_state_for_impact(db, event, impact)
                    if usable and event is not None
                    else "calculation_unavailable"
                ),
                has_scenarios=has_scenarios,
                is_demo=bool(event.is_demo) if event is not None else False,
            )
        )
    return items
