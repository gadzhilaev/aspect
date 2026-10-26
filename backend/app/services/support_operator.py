"""Escalate support threads to Telegram operators and ingest replies."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.company import Company
from app.models.notification import NotificationSubscription
from app.models.support import SupportMessage, SupportThread
from app.models.user import User
from app.services.support_group_registry import (
    load_email_alert_chats,
    load_registered_chat_ids,
)
from app.services.telegram_send import send_telegram_text

logger = logging.getLogger(__name__)

_TICKET_RE = re.compile(r"SUP-([A-F0-9]{8})", re.IGNORECASE)
_REPLY_CMD_RE = re.compile(
    r"^/support(?:_reply)?\s+(SUP-[A-F0-9]{8})\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def ticket_code(thread_id: str) -> str:
    return "SUP-" + (thread_id or "").replace("-", "")[:8].upper()


def operator_chat_ids() -> list[str]:
    """Env SUPPORT_OPERATOR_CHAT_IDS + groups registered via /support_here."""
    settings = get_settings()
    raw = (getattr(settings, "support_operator_chat_ids", None) or "").strip()
    from_env = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    from_file = load_registered_chat_ids()
    seen: set[str] = set()
    out: list[str] = []
    for cid in from_env + from_file:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def is_operator_chat(chat_id: str | int | None) -> bool:
    if chat_id is None:
        return False
    cid = str(chat_id).strip()
    return cid in set(operator_chat_ids())


def _company_block(db: Session, thread: SupportThread) -> str:
    if not thread.company_id:
        return ""
    company = db.get(Company, thread.company_id)
    if company is None:
        return ""
    parts: list[str] = []
    name = (company.legal_name or company.name or "").strip()
    if name:
        parts.append(name)
    if company.industry and str(company.industry).strip():
        parts.append(str(company.industry).strip())
    if company.tax_id and str(company.tax_id).strip():
        parts.append(f"ИНН {company.tax_id.strip()}")
    if company.size_band and str(company.size_band).strip():
        parts.append(str(company.size_band).strip())
    if company.hq_region and str(company.hq_region).strip():
        parts.append(str(company.hq_region).strip())
    return "\n".join(parts)


def _quote(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return "«»"
    # Telegram-friendly blockquote-ish lines
    lines = body.splitlines() or [body]
    return "\n".join(f"«{line}»" if len(lines) == 1 else f"> {line}" for line in lines)


def _tg_tag(raw: str) -> str:
    """Telegram hashtag token: letters/digits/underscore only."""
    s = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_]+", "_", (raw or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:48] or "x"


def user_search_tag(*, email: str, user_id: str) -> str:
    local = (email or "").split("@", 1)[0].strip().lower()
    if local:
        return f"#u_{_tg_tag(local)}"
    return f"#u_{_tg_tag((user_id or '')[:8])}"


def ticket_search_tag(ticket: str) -> str:
    code = (ticket or "").replace("-", "_").upper()
    return f"#{_tg_tag(code)}"


def _user_header(db: Session, *, thread: SupportThread, user: User) -> list[str]:
    email = (user.email or "").strip() or "—"
    name = (user.display_name or "").strip()
    ticket = ticket_code(thread.id)
    lines = [
        f"Пользователь: {name}" if name else "Пользователь:",
        f"Email: {email}",
    ]
    company = _company_block(db, thread)
    if company:
        lines.append(company)
    else:
        lines.append("Компания: не привязана")
    lines.append(
        f"{ticket_search_tag(ticket)} {user_search_tag(email=email, user_id=user.id)} #aspect_support"
    )
    return lines


def find_thread_by_ticket(db: Session, ticket: str) -> SupportThread | None:
    code = (ticket or "").strip().upper()
    m = _TICKET_RE.search(code)
    if not m:
        if code.startswith("SUP-"):
            prefix = code[4:12]
        else:
            return None
    else:
        prefix = m.group(1).upper()
    if len(prefix) < 8:
        return None
    rows = (
        db.query(SupportThread)
        .filter(SupportThread.status.in_(("open", "waiting_operator", "with_operator")))
        .order_by(SupportThread.updated_at.desc())
        .limit(200)
        .all()
    )
    for t in rows:
        if (t.id or "").replace("-", "").upper().startswith(prefix):
            return t
    rows2 = (
        db.query(SupportThread)
        .filter(SupportThread.status == "closed")
        .order_by(SupportThread.updated_at.desc())
        .limit(50)
        .all()
    )
    for t in rows2:
        if (t.id or "").replace("-", "").upper().startswith(prefix):
            return t
    return None


def notify_operators(
    db: Session,
    *,
    thread: SupportThread,
    user: User,
    user_text: str,
    reason: str,
) -> bool:
    """Push escalation card to all operator chats. Returns True if any sent."""
    del reason  # not shown to operators (keep signature stable)
    ids = operator_chat_ids()
    ticket = ticket_code(thread.id)
    quoted = _quote(user_text)
    lines = [
        f"🆘 Поддержка Аспект · {ticket}",
        *_user_header(db, thread=thread, user=user),
        "Сообщение:",
        quoted,
        "",
        "➡️ Reply на это сообщение — ответ уйдёт в приложение.",
        f"История: /history {ticket}",
    ]
    text = "\n".join(lines)
    if not ids:
        logger.info("support_escalate_no_operators ticket=%s", ticket)
        return False
    ok_any = False
    for cid in ids:
        if send_telegram_text(cid, text, bot="support"):
            ok_any = True
    logger.info(
        "support_escalate ticket=%s operators=%s sent=%s",
        ticket,
        len(ids),
        ok_any,
    )
    return ok_any


def forward_user_to_operators(
    db: Session,
    *,
    thread: SupportThread,
    user: User,
    user_text: str,
) -> None:
    ids = operator_chat_ids()
    if not ids:
        return
    ticket = ticket_code(thread.id)
    lines = [
        f"💬 Новое сообщение · {ticket}",
        *_user_header(db, thread=thread, user=user),
        "Сообщение:",
        _quote(user_text),
        "",
        "➡️ Reply на это сообщение",
        f"История: /history {ticket}",
    ]
    text = "\n".join(lines)
    for cid in ids:
        send_telegram_text(cid, text, bot="support")


def format_thread_history(
    db: Session,
    *,
    thread: SupportThread,
    limit: int = 30,
) -> str:
    """Compact transcript for Telegram operators."""
    user = db.get(User, thread.user_id)
    ticket = ticket_code(thread.id)
    rows = (
        db.query(SupportMessage)
        .filter(SupportMessage.thread_id == thread.id)
        .order_by(SupportMessage.created_at.asc())
        .all()
    )
    if len(rows) > limit:
        rows = rows[-limit:]
    role_label = {
        "user": "Клиент",
        "support": "AI",
        "operator": "Оператор",
        "system": "Система",
    }
    lines: list[str] = [f"🗂 История · {ticket}"]
    if user is not None:
        lines.extend(_user_header(db, thread=thread, user=user))
    lines.append("")
    if not rows:
        lines.append("(пусто)")
    else:
        for m in rows:
            label = role_label.get(m.role, m.role)
            body = (m.content or "").strip().replace("\n", " ")
            if len(body) > 220:
                body = body[:217] + "…"
            lines.append(f"• {label}: {body}")
    lines.append("")
    lines.append(f"➡️ Reply на карточку с {ticket} или /support {ticket} текст")
    return "\n".join(lines)


def notify_user_operator_reply(
    db: Session,
    *,
    thread: SupportThread,
    content: str,
) -> None:
    """Push a short Telegram DM when operator answers (linked TG or /support_alerts)."""
    preview = (content or "").strip()
    if len(preview) > 280:
        preview = preview[:277] + "…"
    text = (
        "💬 Ответ поддержки Аспект\n\n"
        f"{preview}\n\n"
        "Откройте чат поддержки в приложении."
    )
    chat_ids: set[str] = set()
    subs = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.user_id == thread.user_id,
            NotificationSubscription.channel_type == "telegram_private",
            NotificationSubscription.status == "connected",
            NotificationSubscription.is_active.is_(True),
        )
        .all()
    )
    for sub in subs:
        cid = (sub.chat_id or "").strip()
        if cid:
            chat_ids.add(cid)

    user = db.get(User, thread.user_id)
    email = ((user.email if user else None) or "").strip().lower()
    if email:
        mapped = load_email_alert_chats().get(email)
        if mapped:
            chat_ids.add(mapped)

    sent = False
    for cid in chat_ids:
        if send_telegram_text(cid, text, bot="support"):
            sent = True
    if not sent:
        logger.info(
            "support_user_notify_skipped thread=%s reason=no_linked_telegram",
            thread.id,
        )


def add_operator_reply(
    db: Session,
    *,
    thread: SupportThread,
    content: str,
) -> SupportMessage:
    now = datetime.now(timezone.utc)
    msg = SupportMessage(
        id=str(uuid4()),
        thread_id=thread.id,
        role="operator",
        content=(content or "").strip(),
        client_message_id=None,
        created_at=now,
    )
    db.add(msg)
    thread.handler = "operator"
    if thread.status in ("open", "waiting_operator"):
        thread.status = "with_operator"
    thread.updated_at = now
    return msg


def try_handle_operator_telegram(
    db: Session,
    *,
    chat_id: str | int,
    text: str,
    reply_to_text: str | None = None,
) -> str | None:
    """If this is an operator chat command/reply, ingest and return ack text."""
    if not is_operator_chat(chat_id):
        return None
    raw = (text or "").strip()
    if not raw:
        return None

    # /history SUP-XXXXXXXX  (or reply to a card)
    head = raw.split(maxsplit=1)[0].split("@", 1)[0].lower()
    if head in {"/history", "/support_hist"}:
        ticket = None
        parts = raw.split(maxsplit=1)
        if len(parts) > 1:
            m = _TICKET_RE.search(parts[1].upper())
            if m:
                ticket = f"SUP-{m.group(1).upper()}"
        if not ticket and reply_to_text:
            tm = _TICKET_RE.search(reply_to_text)
            if tm:
                ticket = f"SUP-{tm.group(1).upper()}"
        if not ticket:
            return "Формат: /history SUP-XXXXXXXX\nИли reply на карточку + /history"
        thread = find_thread_by_ticket(db, ticket)
        if thread is None:
            return f"Обращение {ticket} не найдено."
        return format_thread_history(db, thread=thread)

    ticket = None
    body = None
    m = _REPLY_CMD_RE.match(raw)
    if m:
        ticket = m.group(1).upper()
        body = m.group(2).strip()
    elif reply_to_text:
        tm = _TICKET_RE.search(reply_to_text)
        if tm:
            ticket = f"SUP-{tm.group(1).upper()}"
            body = raw

    if not ticket or not body:
        if raw.startswith("/support"):
            return (
                "Формат: /support SUP-XXXXXXXX текст ответа\n"
                "Или reply на карточку обращения.\n"
                "История: /history SUP-XXXXXXXX"
            )
        return None

    thread = find_thread_by_ticket(db, ticket)
    if thread is None:
        return f"Обращение {ticket} не найдено."
    if not body:
        return "Пустой ответ."
    add_operator_reply(db, thread=thread, content=body)
    notify_user_operator_reply(db, thread=thread, content=body)
    db.commit()
    return f"✓ Ответ отправлен в приложение ({ticket})."
