"""Support chat: AI first, escalate to Telegram operator when unsure."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.support import SupportMessage, SupportThread
from app.models.user import User
from app.schemas.support import SupportMessageOut, SupportThreadOut
from app.services.support_ai import decide_support_reply
from app.services.support_operator import (
    forward_user_to_operators,
    notify_operators,
    ticket_code,
)

_WELCOME = (
    "Здравствуйте! Это поддержка Аспект.\n\n"
    "Сначала отвечу я — AI. Если не смогу помочь, "
    "подключу живого оператора (через Telegram).\n"
    "Спросите про вход, профиль, ленту, финансы, Telegram или материалы банка."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _msg_out(m: SupportMessage) -> SupportMessageOut:
    role = m.role if m.role in ("user", "support", "system", "operator") else "support"
    return SupportMessageOut(
        id=m.id,
        role=role,  # type: ignore[arg-type]
        content=m.content or "",
        client_message_id=m.client_message_id,
        created_at=m.created_at,
    )


def _thread_status(raw: str) -> str:
    if raw in ("open", "closed", "waiting_operator", "with_operator"):
        return raw
    return "open"


def _thread_out(thread: SupportThread, messages: list[SupportMessage]) -> SupportThreadOut:
    handler = getattr(thread, "handler", None) or "ai"
    if handler not in ("ai", "operator"):
        handler = "ai"
    return SupportThreadOut(
        id=thread.id,
        status=_thread_status(thread.status),  # type: ignore[arg-type]
        handler=handler,  # type: ignore[arg-type]
        subject=thread.subject,
        company_id=thread.company_id,
        ticket=ticket_code(thread.id),
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=[_msg_out(m) for m in messages],
    )


def _add_message(
    db: Session,
    *,
    thread: SupportThread,
    role: str,
    content: str,
    client_message_id: str | None = None,
) -> SupportMessage:
    msg = SupportMessage(
        id=str(uuid4()),
        thread_id=thread.id,
        role=role,
        content=content.strip(),
        client_message_id=client_message_id,
        created_at=_utcnow(),
    )
    db.add(msg)
    thread.updated_at = _utcnow()
    return msg


def craft_support_reply(*, user_text: str, thread_id: str) -> str:
    """Backward-compatible helper for unit tests (FAQ or escalate stub)."""
    decision = decide_support_reply(user_text)
    if decision.reply and not decision.escalate:
        return decision.reply
    return "Передал оператору"


def get_or_create_thread(
    db: Session,
    *,
    user: User,
    company_id: str | None = None,
) -> SupportThreadOut:
    thread = (
        db.query(SupportThread)
        .filter(
            SupportThread.user_id == user.id,
            SupportThread.status.in_(("open", "waiting_operator", "with_operator")),
        )
        .order_by(SupportThread.updated_at.desc())
        .first()
    )
    if thread is None:
        thread = SupportThread(
            id=str(uuid4()),
            user_id=user.id,
            company_id=company_id,
            status="open",
            handler="ai",
            subject="Поддержка",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(thread)
        db.flush()
        _add_message(db, thread=thread, role="support", content=_WELCOME)
        db.commit()
        db.refresh(thread)
    elif company_id and not thread.company_id:
        thread.company_id = company_id
        db.commit()
        db.refresh(thread)

    messages = (
        db.query(SupportMessage)
        .filter(SupportMessage.thread_id == thread.id)
        .order_by(SupportMessage.created_at.asc())
        .all()
    )
    return _thread_out(thread, messages)


def list_messages(
    db: Session,
    *,
    user: User,
    after_id: str | None = None,
) -> list[SupportMessageOut]:
    thread = (
        db.query(SupportThread)
        .filter(
            SupportThread.user_id == user.id,
            SupportThread.status.in_(("open", "waiting_operator", "with_operator")),
        )
        .order_by(SupportThread.updated_at.desc())
        .first()
    )
    if thread is None:
        return []
    q = db.query(SupportMessage).filter(SupportMessage.thread_id == thread.id)
    if after_id:
        pivot = db.get(SupportMessage, after_id)
        if pivot is not None and pivot.thread_id == thread.id:
            q = q.filter(SupportMessage.created_at > pivot.created_at)
    rows = q.order_by(SupportMessage.created_at.asc()).all()
    return [_msg_out(m) for m in rows]


def _open_thread(db: Session, user: User, company_id: str | None) -> SupportThread:
    thread = (
        db.query(SupportThread)
        .filter(
            SupportThread.user_id == user.id,
            SupportThread.status.in_(("open", "waiting_operator", "with_operator")),
        )
        .order_by(SupportThread.updated_at.desc())
        .first()
    )
    if thread is None:
        get_or_create_thread(db, user=user, company_id=company_id)
        thread = (
            db.query(SupportThread)
            .filter(
                SupportThread.user_id == user.id,
                SupportThread.status.in_(
                    ("open", "waiting_operator", "with_operator")
                ),
            )
            .order_by(SupportThread.updated_at.desc())
            .first()
        )
    assert thread is not None
    return thread


def post_message(
    db: Session,
    *,
    user: User,
    content: str,
    client_message_id: str | None = None,
    company_id: str | None = None,
) -> tuple[SupportMessageOut, SupportMessageOut | None, bool]:
    text = (content or "").strip()
    if not text:
        raise AppError("VALIDATION_ERROR", "Пустое сообщение", 422)

    thread = _open_thread(db, user, company_id)

    if client_message_id:
        existing = (
            db.query(SupportMessage)
            .filter(
                SupportMessage.thread_id == thread.id,
                SupportMessage.client_message_id == client_message_id,
            )
            .first()
        )
        if existing is not None:
            reply = (
                db.query(SupportMessage)
                .filter(
                    SupportMessage.thread_id == thread.id,
                    SupportMessage.role.in_(("support", "system", "operator")),
                    SupportMessage.created_at > existing.created_at,
                )
                .order_by(SupportMessage.created_at.asc())
                .first()
            )
            return _msg_out(existing), (_msg_out(reply) if reply else None), True

    if company_id and not thread.company_id:
        thread.company_id = company_id

    user_msg = _add_message(
        db,
        thread=thread,
        role="user",
        content=text,
        client_message_id=client_message_id,
    )
    db.flush()

    handler = getattr(thread, "handler", None) or "ai"
    if handler == "operator" or thread.status in ("waiting_operator", "with_operator"):
        # Already with operator — forward quietly, no system spam in the app.
        forward_user_to_operators(db, thread=thread, user=user, user_text=text)
        db.commit()
        db.refresh(user_msg)
        return _msg_out(user_msg), None, False

    decision = decide_support_reply(text)
    if decision.reply and not decision.escalate:
        support_msg = _add_message(
            db, thread=thread, role="support", content=decision.reply
        )
        db.commit()
        db.refresh(user_msg)
        db.refresh(support_msg)
        return _msg_out(user_msg), _msg_out(support_msg), False

    # Escalate to human operator via Telegram bot.
    thread.handler = "operator"
    thread.status = "waiting_operator"
    notify_operators(
        db,
        thread=thread,
        user=user,
        user_text=text,
        reason="ai_uncertain" if decision.source == "llm" else "ai_unavailable",
    )
    support_msg = _add_message(
        db, thread=thread, role="system", content="Передал оператору"
    )
    db.commit()
    db.refresh(user_msg)
    db.refresh(support_msg)
    return _msg_out(user_msg), _msg_out(support_msg), False


def close_thread(db: Session, *, user: User) -> SupportThreadOut:
    thread = (
        db.query(SupportThread)
        .filter(
            SupportThread.user_id == user.id,
            SupportThread.status.in_(("open", "waiting_operator", "with_operator")),
        )
        .order_by(SupportThread.updated_at.desc())
        .first()
    )
    if thread is None:
        raise AppError("NOT_FOUND", "Открытый чат поддержки не найден", 404)
    thread.status = "closed"
    thread.updated_at = _utcnow()
    _add_message(
        db,
        thread=thread,
        role="system",
        content="Обращение закрыто. Чтобы написать снова — откройте поддержку из настроек.",
    )
    db.commit()
    db.refresh(thread)
    messages = (
        db.query(SupportMessage)
        .filter(SupportMessage.thread_id == thread.id)
        .order_by(SupportMessage.created_at.asc())
        .all()
    )
    return _thread_out(thread, messages)
