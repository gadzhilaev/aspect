"""Wire AgentLoopRunner into post_message behind ASSISTANT_AGENT_LOOP (stage 4.5+).

Transaction policy: commit the user message **before** model HTTP, then commit
the assistant (or incomplete notice) in a separate transaction — SQLite write
lock is not held across network waits.

Idempotency limits: at-most-once assistant persistence per client_message_id
within this process+DB; external hackathon API is **not** exactly-once if the
process dies after HTTP success and before the assistant commit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AssistantConversation, AssistantMessage, User
from app.schemas.assistant import PostMessageOut
from app.services.assistant.agent_loop.budget import LoopStopReason, TurnBudget
from app.services.assistant.agent_loop.hackathon_loop import HackathonLoopProvider
from app.services.assistant.agent_loop.outcomes import LoopFinalOutcome, LoopStoppedOutcome
from app.services.assistant.agent_loop.runner import AgentLoopRunner
from app.services.assistant.agent_loop.runtime import ensure_agent_loop_runtime_allowed
from app.services.assistant.agent_loop.scope import ServerScope
from app.services.assistant.agent_loop.sources import SourceLedger
from app.services.assistant.bank_evidence_citations import (
    ValidatedCitation,
    validated_to_public_dicts,
)
from app.services.assistant.case_company_context import case_context_ref_message_block
from app.services.assistant.provenance import BANK_MATERIAL, COMPANY_CONTEXT

logger = logging.getLogger(__name__)

# Whole messages only — never mid-cut content (citations / caveats stay intact or omit).
MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_TOTAL_CHARS = 6000

# Injectable for tests (mocked httpx transport). Production: None → per-request client.
_loop_http_client: httpx.Client | None = None


@dataclass(frozen=True)
class ConversationHistoryPack:
    """Prior turns for the model as DATA, plus honesty flags when anything was dropped."""

    messages: list[dict[str, Any]]
    history_incomplete: bool
    history_omitted_count: int


def normalize_message_text(text: str) -> str:
    """Idempotency text compare: strip edges + unify newlines; keep internal spacing."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def set_loop_http_client_for_tests(client: httpx.Client | None) -> None:
    global _loop_http_client
    _loop_http_client = client


def build_hackathon_loop_provider() -> HackathonLoopProvider:
    from app.services.competition_profile import assert_competition_llm_config

    settings = get_settings()
    assert_competition_llm_config(settings)
    api_key = settings.resolved_hackathon_api_key()
    if not api_key:
        raise AppError(
            "PROVIDER_UNAVAILABLE",
            "Hackathon-провайдер не настроен: задайте HACKATHON_API_KEY в root .env",
            503,
            details=[{"reason": "missing_hackathon_api_key"}],
        )
    return HackathonLoopProvider(
        api_key=api_key,
        model=settings.resolved_hackathon_model(),
        base_url=settings.resolved_hackathon_base_url(),
        http_client=_loop_http_client,
        transport_timeout_s=45.0,
    )


def assert_loop_mode_supported() -> None:
    """Flag on requires hackathon; no silent legacy/mock fallback."""
    settings = get_settings()
    ensure_agent_loop_runtime_allowed(enabled=True)
    provider = settings.normalized_assistant_provider()
    if provider != "hackathon":
        raise AppError(
            "ASSISTANT_AGENT_LOOP_UNSUPPORTED_PROVIDER",
            (
                "Многошаговый цикл (ASSISTANT_AGENT_LOOP) поддерживается только "
                "с ASSISTANT_PROVIDER=hackathon"
            ),
            400,
            details=[{"provider": provider, "required": "hackathon"}],
        )


def build_conversation_history_data(
    rows: list[AssistantMessage],
    *,
    exclude_message_id: str | None = None,
) -> ConversationHistoryPack:
    """Limited prior turns as DATA — not citation grounds.

    Keeps **whole** messages only (no character slice of content). Selects the
    newest messages that fit ``MAX_HISTORY_MESSAGES`` and ``MAX_HISTORY_TOTAL_CHARS``.
    Oversized messages are omitted entirely; ``history_incomplete`` /
    ``history_omitted_count`` mark that the model must not invent missing context.
    """
    candidates: list[AssistantMessage] = []
    for m in rows:
        if exclude_message_id and m.id == exclude_message_id:
            continue
        if m.role not in {"user", "assistant"}:
            continue
        # Skip prior incomplete loop notices as noisy history
        blocks = m.blocks_json or []
        if any(
            isinstance(b, dict)
            and b.get("type") == "missing_data"
            and isinstance(b.get("data"), dict)
            and b["data"].get("reason") == "loop_incomplete"
            for b in blocks
        ):
            continue
        candidates.append(m)

    omitted = 0
    # Newest-first pack into budget, then restore chronological order.
    chosen_rev: list[dict[str, Any]] = []
    used_chars = 0
    for m in reversed(candidates):
        text = m.content or ""
        # Preserve original content bytes (no strip mid-message); only skip empties.
        if not text.strip():
            omitted += 1
            continue
        if len(chosen_rev) >= MAX_HISTORY_MESSAGES:
            omitted += 1
            continue
        if len(text) > MAX_HISTORY_TOTAL_CHARS:
            # Cannot fit alone without mid-cutting — omit whole message.
            omitted += 1
            continue
        if used_chars + len(text) > MAX_HISTORY_TOTAL_CHARS:
            omitted += 1
            continue
        chosen_rev.append({"role": m.role, "content": text})
        used_chars += len(text)

    messages = list(reversed(chosen_rev))
    # Also incomplete if we dropped older candidates beyond the window we scanned
    # only via budget/count above (omitted already counts those).
    return ConversationHistoryPack(
        messages=messages,
        history_incomplete=omitted > 0,
        history_omitted_count=omitted,
    )


def analysis_steps_from_trace(safe_trace: dict[str, Any] | None) -> list[str]:
    """Human-readable agent steps for jury / Flutter (no secrets)."""
    if not isinstance(safe_trace, dict):
        return []
    lines: list[str] = []
    for step in safe_trace.get("steps") or []:
        if not isinstance(step, dict):
            continue
        kind = str(step.get("kind") or "step")
        name = str(step.get("name") or step.get("tool") or "").strip()
        status = str(step.get("status") or "").strip()
        line = f"{kind}: {name}" if name else kind
        if status:
            line = f"{line} ({status})"
        lines.append(line[:160])
        if len(lines) >= 20:
            break
    tools = safe_trace.get("tool_calls_used")
    if tools is not None and not lines:
        lines.append(f"tool_calls_used: {tools}")
    return lines


def _safe_trace(outcome: LoopFinalOutcome | LoopStoppedOutcome) -> dict[str, Any]:
    snap = dict(outcome.budget_snapshot or {})
    steps = []
    for t in outcome.trace:
        detail = {
            k: v
            for k, v in (t.detail or {}).items()
            if k
            in {
                "name",
                "status",
                "call_id",
                "reason_code",
                "code",
                "reason",
                "tool",
                "citations",
                "content_chars",
                "repair",
            }
        }
        steps.append({"kind": t.kind, **detail})
    out: dict[str, Any] = {
        "mode": "loop",
        "steps": steps[:40],
        "model_http_used": snap.get("model_http_used"),
        "model_http_reserved": snap.get("model_http_reserved", snap.get("model_http_used")),
        "model_http_transport": snap.get("model_http_transport"),
        "model_http_responses": snap.get("model_http_responses"),
        "tool_calls_used": snap.get("tool_calls_used"),
        "repairs_used": snap.get("repairs_used"),
        "transcript_chars": snap.get("transcript_chars"),
        "peak_payload_chars": snap.get("peak_payload_chars"),
    }
    if isinstance(outcome, LoopStoppedOutcome):
        out["outcome"] = "stopped"
        out["stop_reason"] = outcome.reason.value
        out["detail"] = (outcome.detail or "")[:200]
    else:
        out["outcome"] = "final"
        out["citations_count"] = len(outcome.citations)
    return out


def _bank_block_from_citations(
    citations: list[ValidatedCitation],
    *,
    ledger: SourceLedger,
    provider: HackathonLoopProvider | None,
) -> dict[str, Any] | None:
    if not citations and not ledger.passed_index_for_citations():
        return None
    validated = validated_to_public_dicts(citations)
    passed_ids = list(ledger.passed_index_for_citations().keys())
    data: dict[str, Any] = {
        "status": "available" if validated else "no_matching_evidence",
        "available": bool(validated),
        "used": validated,
        "diagnostics": {
            "retrieved_count": len(passed_ids),
            "retrieved_ids": passed_ids,
            "passed_to_provider_ids": passed_ids,
            "cited_by_model": [c.fragment_id for c in citations],
            "validated_ids": [c.fragment_id for c in citations],
            "rejected": [],
            "http_attempts": getattr(provider, "http_attempts", None),
        },
        "provenance_note": (
            "Validated fragment IDs prove link provenance and revision snapshot; "
            "they do not prove that the source supports every model claim."
        ),
        "loop_mode": True,
    }
    return {
        "type": "bank_evidence_list",
        "title": "Материалы банка" if validated else "Материалы банка не использованы",
        "data": data,
        "labels": [BANK_MATERIAL],
    }


def _incomplete_content(reason: LoopStopReason) -> str:
    mapping = {
        LoopStopReason.budget_exhausted: (
            "Не удалось завершить разбор: исчерпан лимит шагов. "
            "Можно отправить вопрос ещё раз."
        ),
        LoopStopReason.context_limit: (
            "Не удалось завершить разбор: подготовленный контекст не помещается "
            "в лимит запроса к модели. Сократите историю диалога или уточните вопрос; "
            "повтор той же формулировки не гарантирует успех."
        ),
        LoopStopReason.timeout: (
            "Не удалось завершить разбор: истекло время ожидания. "
            "Можно отправить вопрос ещё раз."
        ),
        LoopStopReason.no_progress: (
            "Не удалось завершить разбор: нет прогресса по инструментам. "
            "Попробуйте переформулировать вопрос."
        ),
        LoopStopReason.invalid_action: (
            "Не удалось завершить разбор: получен некорректный ответ модели. "
            "Можно отправить вопрос ещё раз."
        ),
        LoopStopReason.provider_daily_budget: (
            "Не удалось завершить разбор: исчерпан дневной бюджет провайдера модели. "
            "Повторите попытку позже."
        ),
    }
    return mapping.get(
        reason,
        "Не удалось завершить разбор.",
    )


def _incomplete_blocks(
    outcome: LoopStoppedOutcome, *, safe_trace: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        {
            "type": "missing_data",
            "title": "Разбор не завершён",
            "data": {
                "reason": "loop_incomplete",
                "loop_stop_reason": outcome.reason.value,
                "message": _incomplete_content(outcome.reason),
                "not_ai_final": True,
                # Safe compact diagnostics — no prompt/secrets
                "diagnostics": {
                    "detail_code": (outcome.detail or "")[:120],
                    "model_http_used": safe_trace.get("model_http_used"),
                    "model_http_reserved": safe_trace.get("model_http_reserved"),
                    "model_http_transport": safe_trace.get("model_http_transport"),
                    "model_http_responses": safe_trace.get("model_http_responses"),
                    "tool_calls_used": safe_trace.get("tool_calls_used"),
                    "peak_payload_chars": safe_trace.get("peak_payload_chars"),
                },
            },
            "labels": ["system"],
        }
    ]


def _in_reply_to_meta(user_message_id: str) -> dict[str, Any]:
    """Stable link user→assistant; avoids SQLite same-second created_at races.

    Stored as missing_data so JSON stays schema-shaped in DB; stripped from
    public API output (see ``_msg_out_local``).
    """
    return {
        "type": "missing_data",
        "title": None,
        "data": {
            "in_reply_to_message_id": user_message_id,
            "internal_reply_link": True,
        },
        "labels": ["system"],
    }


def _is_internal_reply_link_block(b: dict[str, Any]) -> bool:
    data = b.get("data")
    return (
        b.get("type") == "missing_data"
        and isinstance(data, dict)
        and data.get("internal_reply_link") is True
    )


def _message_replies_to(m: AssistantMessage, user_message_id: str) -> bool:
    for b in m.blocks_json or []:
        if not isinstance(b, dict):
            continue
        data = b.get("data")
        if isinstance(data, dict) and data.get("in_reply_to_message_id") == user_message_id:
            return True
    return False


def _find_reply_after_user(
    db: Session, *, conversation_id: str, user_msg: AssistantMessage
) -> AssistantMessage | None:
    """Assistant/system reply paired to this user message (not merely later by clock)."""
    rows = (
        db.query(AssistantMessage)
        .filter(
            AssistantMessage.conversation_id == conversation_id,
            AssistantMessage.role.in_(("assistant", "system")),
            AssistantMessage.id != user_msg.id,
        )
        .order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc())
        .all()
    )
    for m in rows:
        if _message_replies_to(m, user_msg.id):
            return m
    # Legacy fallback: first assistant strictly after this user in wall-clock order.
    # Only used if meta is missing (should not happen on the loop path).
    seen_user = False
    all_rows = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conversation_id)
        .order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc())
        .all()
    )
    for m in all_rows:
        if m.id == user_msg.id:
            seen_user = True
            continue
        if not seen_user:
            continue
        if m.role in {"assistant", "system"} and m.created_at > user_msg.created_at:
            return m
    return None


def _msg_out_local(m: AssistantMessage):
    from app.services.assistant.orchestrator import _msg_out

    raw_blocks = list(m.blocks_json or [])
    public = [b for b in raw_blocks if not (isinstance(b, dict) and _is_internal_reply_link_block(b))]
    if public == raw_blocks:
        return _msg_out(m)
    # Validate against public blocks only (internal reply link is DB-only).
    prev = m.blocks_json
    try:
        m.blocks_json = public
        return _msg_out(m)
    finally:
        m.blocks_json = prev


def _incomplete_block_data(m: AssistantMessage) -> dict[str, Any] | None:
    for b in m.blocks_json or []:
        if not isinstance(b, dict) or b.get("type") != "missing_data":
            continue
        data = b.get("data")
        if isinstance(data, dict) and data.get("reason") == "loop_incomplete":
            return data
    return None


def _is_incomplete_loop_reply(m: AssistantMessage) -> bool:
    return _incomplete_block_data(m) is not None


def _raise_incomplete_replay(
    *,
    user_msg: AssistantMessage,
    reply: AssistantMessage,
    client_message_id: str | None,
) -> None:
    """Re-raise the original structured stop error — not a successful final."""
    data = _incomplete_block_data(reply) or {}
    reason_raw = str(data.get("loop_stop_reason") or "invalid_action")
    try:
        reason = LoopStopReason(reason_raw)
    except ValueError:
        reason = LoopStopReason.invalid_action
    diag = data.get("diagnostics") if isinstance(data.get("diagnostics"), dict) else {}
    detail = ""
    if isinstance(data.get("loop_trace"), dict):
        detail = str(data["loop_trace"].get("detail") or "")[:120]
    if not detail and isinstance(diag, dict):
        detail = str(diag.get("detail_code") or "")[:120]
    raise AppError(
        _stop_error_code(reason),
        _incomplete_content(reason),
        _stop_http_status(reason),
        details=[
            {
                "loop_stop_reason": reason.value,
                "detail": detail,
                "user_message_id": user_msg.id,
                "assistant_message_id": reply.id,
                "not_ai_final": True,
                "reused": True,
                "client_message_id": client_message_id,
            }
        ],
    )


def _assert_client_message_text_compatible(
    existing: AssistantMessage, *, content: str, client_message_id: str
) -> None:
    if normalize_message_text(existing.content or "") == normalize_message_text(content):
        return
    raise AppError(
        "ASSISTANT_MESSAGE_ID_CONFLICT",
        "Тот же идентификатор сообщения уже использован с другим текстом",
        409,
        details=[
            {
                "client_message_id": client_message_id,
                "reason": "text_mismatch",
            }
        ],
    )


def _replay_existing_pair(
    *,
    existing: AssistantMessage,
    reply: AssistantMessage,
    content: str,
    client_message_id: str,
) -> PostMessageOut:
    _assert_client_message_text_compatible(
        existing, content=content, client_message_id=client_message_id
    )
    if _is_incomplete_loop_reply(reply):
        _raise_incomplete_replay(
            user_msg=existing, reply=reply, client_message_id=client_message_id
        )
    return PostMessageOut(
        user_message=_msg_out_local(existing),
        assistant_message=_msg_out_local(reply),
        reused=True,
        analysis_steps=_steps_from_message_blocks(reply.blocks_json),
    )


def post_message_agent_loop(
    db: Session,
    *,
    conversation_id: str,
    user: User,
    content: str,
    client_message_id: str | None = None,
) -> PostMessageOut:
    """Loop path for ASSISTANT_AGENT_LOOP=true + hackathon."""
    from app.services.assistant.orchestrator import get_conversation_for_user, _touch

    assert_loop_mode_supported()
    conv = get_conversation_for_user(db, conversation_id=conversation_id, user=user)
    normalized_content = normalize_message_text(content)

    # --- idempotent replay / conflict ---
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
            _assert_client_message_text_compatible(
                existing, content=content, client_message_id=client_message_id
            )
            reply = _find_reply_after_user(db, conversation_id=conv.id, user_msg=existing)
            if reply is not None:
                return _replay_existing_pair(
                    existing=existing,
                    reply=reply,
                    content=content,
                    client_message_id=client_message_id,
                )
            raise AppError(
                "ASSISTANT_MESSAGE_IN_PROGRESS",
                "Сообщение с этим идентификатором ещё обрабатывается",
                409,
                details=[{"client_message_id": client_message_id}],
            )

    # --- persist user first, release write lock before HTTP ---
    user_msg = AssistantMessage(
        id=str(uuid4()),
        conversation_id=conv.id,
        role="user",
        content=normalized_content,
        blocks_json=[],
        client_message_id=client_message_id,
    )
    db.add(user_msg)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not client_message_id:
            raise
        existing = (
            db.query(AssistantMessage)
            .filter(
                AssistantMessage.conversation_id == conv.id,
                AssistantMessage.client_message_id == client_message_id,
            )
            .one_or_none()
        )
        if existing is None:
            raise AppError(
                "CONFLICT",
                "Конфликт идемпотентности сообщения",
                409,
            )
        _assert_client_message_text_compatible(
            existing, content=content, client_message_id=client_message_id
        )
        reply = _find_reply_after_user(db, conversation_id=conv.id, user_msg=existing)
        if reply is not None:
            return _replay_existing_pair(
                existing=existing,
                reply=reply,
                content=content,
                client_message_id=client_message_id,
            )
        raise AppError(
            "ASSISTANT_MESSAGE_IN_PROGRESS",
            "Сообщение с этим идентификатором ещё обрабатывается",
            409,
            details=[{"client_message_id": client_message_id}],
        )

    db.refresh(user_msg)

    history_rows = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.conversation_id == conv.id)
        .order_by(AssistantMessage.created_at.asc())
        .all()
    )
    history_pack = build_conversation_history_data(
        history_rows, exclude_message_id=user_msg.id
    )

    settings = get_settings()
    budget = TurnBudget(config=settings.agent_loop_budget_config())
    ledger = SourceLedger()
    provider = build_hackathon_loop_provider()
    scope = ServerScope(
        user_id=user.id,
        company_id=conv.company_id,
        event_id=conv.event_id,
        conversation_id=conv.id,
    )
    runner = AgentLoopRunner(
        db=db,
        scope=scope,
        provider=provider,
        budget=budget,
        ledger=ledger,
    )

    try:
        outcome = runner.run(
            user_question=normalized_content,
            conversation_history=history_pack.messages,
            history_incomplete=history_pack.history_incomplete,
            history_omitted_count=history_pack.history_omitted_count,
        )
    except AppError:
        # Unexpected provider error outside runner mapping — leave IN_PROGRESS
        # only if no reply; save incomplete so retry is defined.
        _persist_crash_incomplete(
            db,
            conv=conv,
            user_msg=user_msg,
            detail="provider_crash",
        )
        raise

    # Re-check winner before writing assistant (concurrent duplicate)
    db.refresh(user_msg)
    existing_reply = _find_reply_after_user(db, conversation_id=conv.id, user_msg=user_msg)
    if existing_reply is not None:
        reused_steps = _steps_from_message_blocks(existing_reply.blocks_json)
        return PostMessageOut(
            user_message=_msg_out_local(user_msg),
            assistant_message=_msg_out_local(existing_reply),
            reused=True,
            analysis_steps=reused_steps,
        )

    safe_trace = _safe_trace(outcome)
    analysis_steps = analysis_steps_from_trace(safe_trace)

    if isinstance(outcome, LoopStoppedOutcome):
        blocks = _incomplete_blocks(outcome, safe_trace=safe_trace)
        blocks = [blocks[0]]
        blocks[0]["data"]["loop_trace"] = safe_trace
        blocks.insert(0, _in_reply_to_meta(user_msg.id))
        assistant_msg = AssistantMessage(
            id=str(uuid4()),
            conversation_id=conv.id,
            role="assistant",
            content=_incomplete_content(outcome.reason),
            blocks_json=blocks,
            client_message_id=None,
        )
        db.add(assistant_msg)
        _touch(conv)
        db.commit()
        db.refresh(user_msg)
        db.refresh(assistant_msg)
        # Explicit error for API consumers; message is also persisted for replay.
        raise AppError(
            _stop_error_code(outcome.reason),
            _incomplete_content(outcome.reason),
            _stop_http_status(outcome.reason),
            details=[
                {
                    "loop_stop_reason": outcome.reason.value,
                    "detail": (outcome.detail or "")[:120],
                    "user_message_id": user_msg.id,
                    "assistant_message_id": assistant_msg.id,
                    "not_ai_final": True,
                }
            ],
        )

    assert isinstance(outcome, LoopFinalOutcome)
    blocks: list[dict[str, Any]] = [_in_reply_to_meta(user_msg.id)]
    bank_block = _bank_block_from_citations(
        outcome.citations, ledger=ledger, provider=provider
    )
    if bank_block is not None:
        bank_block.setdefault("data", {}).setdefault("diagnostics", {})["loop_trace"] = {
            "mode": "loop",
            "outcome": "final",
            "model_http_used": safe_trace.get("model_http_used"),
            "model_http_reserved": safe_trace.get("model_http_reserved"),
            "model_http_transport": safe_trace.get("model_http_transport"),
            "model_http_responses": safe_trace.get("model_http_responses"),
            "tool_calls_used": safe_trace.get("tool_calls_used"),
            "repairs_used": safe_trace.get("repairs_used"),
            "peak_payload_chars": safe_trace.get("peak_payload_chars"),
            "steps": safe_trace.get("steps"),
        }
        blocks.append(bank_block)

    case_ref = _case_ref_from_sent(ledger)
    if case_ref is not None:
        blocks.append(case_ref)

    assistant_msg = AssistantMessage(
        id=str(uuid4()),
        conversation_id=conv.id,
        role="assistant",
        content=outcome.content or "",
        blocks_json=blocks,
        client_message_id=None,
    )
    db.add(assistant_msg)
    _touch(conv)
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)

    return PostMessageOut(
        user_message=_msg_out_local(user_msg),
        assistant_message=_msg_out_local(assistant_msg),
        reused=False,
        analysis_steps=analysis_steps,
    )


def _steps_from_message_blocks(blocks: Any) -> list[str]:
    if not isinstance(blocks, list):
        return []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        data = b.get("data") if isinstance(b.get("data"), dict) else {}
        diag = data.get("diagnostics") if isinstance(data.get("diagnostics"), dict) else {}
        trace = data.get("loop_trace") or diag.get("loop_trace")
        steps = analysis_steps_from_trace(trace if isinstance(trace, dict) else None)
        if steps:
            return steps
    return []


def _case_ref_from_sent(ledger: SourceLedger) -> dict[str, Any] | None:
    for ref in ledger.citable_refs():
        if ref.type != "case_snapshot":
            continue
        block = {
            "status": "profile_available",
            "availability": "available",
            "snapshot_id": ref.id,
            "provenance": {"snapshot_id": ref.id},
        }
        return case_context_ref_message_block(block)
    # Case may have been dispatched via observation source_refs without citable_refs
    # if inclusion was sent_to_model for case_snapshot
    for ref in ledger.list_by_inclusion("sent_to_model"):
        if ref.type == "case_snapshot":
            block = {
                "status": "profile_available",
                "availability": "available",
                "snapshot_id": ref.id,
                "provenance": {"snapshot_id": ref.id},
            }
            return case_context_ref_message_block(block)
    return None


def _stop_error_code(reason: LoopStopReason) -> str:
    return {
        LoopStopReason.budget_exhausted: "ASSISTANT_LOOP_BUDGET_EXHAUSTED",
        LoopStopReason.context_limit: "ASSISTANT_LOOP_CONTEXT_LIMIT",
        LoopStopReason.timeout: "ASSISTANT_LOOP_TIMEOUT",
        LoopStopReason.no_progress: "ASSISTANT_LOOP_NO_PROGRESS",
        LoopStopReason.invalid_action: "ASSISTANT_LOOP_INVALID_ACTION",
        LoopStopReason.provider_daily_budget: "ASSISTANT_LOOP_PROVIDER_DAILY_BUDGET",
    }.get(reason, "ASSISTANT_LOOP_INCOMPLETE")


def _stop_http_status(reason: LoopStopReason) -> int:
    if reason == LoopStopReason.timeout:
        return 504
    if reason in {
        LoopStopReason.budget_exhausted,
        LoopStopReason.provider_daily_budget,
        LoopStopReason.context_limit,
    }:
        return 429
    return 409


def _persist_crash_incomplete(
    db: Session,
    *,
    conv: AssistantConversation,
    user_msg: AssistantMessage,
    detail: str,
) -> None:
    try:
        if _find_reply_after_user(db, conversation_id=conv.id, user_msg=user_msg):
            return
        from app.services.assistant.orchestrator import _touch

        crash_blocks = _incomplete_blocks(
            LoopStoppedOutcome(
                reason=LoopStopReason.invalid_action, detail=detail
            ),
            safe_trace={"mode": "loop", "outcome": "stopped"},
        )
        crash_blocks.insert(0, _in_reply_to_meta(user_msg.id))
        msg = AssistantMessage(
            id=str(uuid4()),
            conversation_id=conv.id,
            role="assistant",
            content=_incomplete_content(LoopStopReason.invalid_action),
            blocks_json=crash_blocks,
            client_message_id=None,
        )
        db.add(msg)
        _touch(conv)
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("failed to persist loop crash incomplete notice")
        db.rollback()
