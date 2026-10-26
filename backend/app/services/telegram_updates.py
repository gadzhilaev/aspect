"""Shared Telegram update handling for webhook and long-polling.

Never log bot tokens, pairing payloads, or message text.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import NotificationSubscription
from app.services.notifications import (
    bind_private_subscription,
    consume_link_token,
    unlink_private_by_chat,
)
from app.services.support_group_registry import register_chat_id, register_email_alert
from app.services.support_operator import try_handle_operator_telegram

logger = logging.getLogger(__name__)


def reply_send_message(chat_id: int | str, text: str, **extra) -> dict:
    return {"method": "sendMessage", "chat_id": chat_id, "text": text, **extra}


def _cmd_name(text: str) -> str:
    """First token without @bot suffix: '/start@Bot' → '/start'."""
    head = (text or "").split(maxsplit=1)[0]
    return head.split("@", 1)[0].lower()


def handle_telegram_update(db: Session, update: dict) -> dict:
    """Process one Bot API Update. Same path for webhook and polling.

    Returns either ``{"ok": True}`` or a Telegram Bot API callback-style
    ``{"method": "sendMessage", ...}`` dict (webhook can return it; polling
    must POST it via sendMessage).
    """
    update_id = update.get("update_id")
    callback = update.get("callback_query")
    if callback:
        return _handle_callback(db, callback)

    member = update.get("my_chat_member")
    if member:
        return _handle_my_chat_member(member)

    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    chat_id = chat.get("id")
    chat_type = (chat.get("type") or "").lower()
    from_user = message.get("from") or {}
    if not chat_id:
        return {"ok": True}

    cmd = _cmd_name(text) if text.startswith("/") else ""

    # /id — always show chat / user ids
    if cmd == "/id":
        uid = from_user.get("id")
        if chat_type == "private":
            return reply_send_message(
                chat_id,
                f"Ваш Telegram user id: {uid}\n"
                f"chat_id (ЛС): {chat_id}",
            )
        return reply_send_message(
            chat_id,
            f"ID этой группы: {chat_id}\n"
            f"Ваш user id: {uid}\n\n"
            "Чтобы сюда шли обращения поддержки — напишите /support_here",
        )

    # Register this group as support destination
    if cmd == "/support_here":
        if chat_type not in {"group", "supergroup"}:
            return reply_send_message(
                chat_id,
                "Команда /support_here только для группы. "
                "Добавьте бота в группу поддержки и вызовите там.",
            )
        register_chat_id(chat_id)
        return reply_send_message(
            chat_id,
            f"Готово. Группа {chat_id} принимает обращения поддержки Аспект.\n"
            "Когда AI не справится — сюда придёт карточка SUP-…\n"
            "Ответьте reply на карточку — ответ уйдёт пользователю в приложение.",
        )

    # Private: bind this TG chat to an app email for support reply alerts
    if cmd == "/support_alerts":
        if chat_type != "private":
            return reply_send_message(
                chat_id,
                "Команда только в личке с ботом.\n"
                "Формат: /support_alerts ваш@email.ru",
            )
        parts = text.split(maxsplit=1)
        email = parts[1].strip() if len(parts) > 1 else ""
        if "@" not in email:
            return reply_send_message(
                chat_id,
                "Укажите email аккаунта Аспект:\n"
                "/support_alerts info@example.com",
            )
        try:
            register_email_alert(email, chat_id)
        except ValueError:
            return reply_send_message(chat_id, "Некорректный email.")
        return reply_send_message(
            chat_id,
            f"Готово. Уведомления о ответах поддержки для {email.strip().lower()} "
            f"будут приходить сюда (chat_id {chat_id}).",
        )

    # Human support operators — reply / /support before /start pairing.
    if text:
        reply_to = message.get("reply_to_message") or {}
        reply_to_text = (reply_to.get("text") or "") if isinstance(reply_to, dict) else ""
        op_ack = try_handle_operator_telegram(
            db,
            chat_id=chat_id,
            text=text,
            reply_to_text=reply_to_text or None,
        )
        if op_ack is not None:
            return reply_send_message(chat_id, op_ack)

    if cmd == "/start":
        parts = text.split(maxsplit=1)
        payload = parts[1] if len(parts) > 1 else ""
        if payload:
            if chat_type != "private":
                db.commit()
                return reply_send_message(
                    chat_id,
                    "Личное подключение возможно только в личном чате с ботом. "
                    "Откройте ссылку из приложения в личных сообщениях.",
                )
            token = consume_link_token(db, payload)
            if token is None:
                already = (
                    db.query(NotificationSubscription)
                    .filter(
                        NotificationSubscription.chat_id == str(chat_id),
                        NotificationSubscription.channel_type == "telegram_private",
                        NotificationSubscription.status == "connected",
                    )
                    .first()
                )
                db.commit()
                if already is not None:
                    return reply_send_message(
                        chat_id,
                        "Telegram уже подключён к Аспекту для одной или нескольких ваших компаний.",
                    )
                return reply_send_message(
                    chat_id,
                    "Ссылка недействительна или уже использована. Создайте новую в приложении Аспект.",
                )
            if token.purpose != "private":
                db.commit()
                return reply_send_message(
                    chat_id,
                    "Эта ссылка предназначена для группового подключения, не для личного чата.",
                )
            title = chat.get("username") or chat.get("first_name") or "private"
            sub, err = bind_private_subscription(
                db, token=token, chat_id=str(chat_id), chat_title=title
            )
            db.commit()
            if err == "membership_revoked":
                return reply_send_message(
                    chat_id,
                    "Доступ к компании отозван. Обратитесь к администратору и создайте новую ссылку.",
                )
            if err == "chat_bound_to_other_user":
                return reply_send_message(
                    chat_id,
                    "Этот Telegram уже привязан к другому аккаунту Аспекта. "
                    "Отвяжите его там или войдите в тот аккаунт.",
                )
            if sub is None:
                return reply_send_message(
                    chat_id, "Не удалось завершить подключение. Попробуйте новую ссылку."
                )
            logger.info(
                "telegram_private_bound update_id=%s subscription_id=%s",
                update_id,
                sub.id,
            )
            return reply_send_message(
                chat_id,
                "Готово. Личный Telegram подключён к Аспекту.\n"
                "Уведомления настраиваются в приложении: Уведомления → Telegram.\n"
                "Команда /unlink отвязывает все компании этого чата.\n\n"
                f"Ваш user id: {from_user.get('id')}\n"
                f"chat_id: {chat_id}",
            )
        # Bare /start — show ids (private) or group id (group)
        if chat_type == "private":
            return reply_send_message(
                chat_id,
                "Аспект — поддержка и уведомления.\n\n"
                f"Ваш Telegram user id: {from_user.get('id')}\n"
                f"chat_id (ЛС): {chat_id}\n\n"
                "Подключение уведомлений — по ссылке из приложения.\n"
                "Команды: /help /id /support_alerts /status /mute /unmute /unlink",
            )
        return reply_send_message(
            chat_id,
            f"ID этой группы: {chat_id}\n\n"
            "Чтобы принимать обращения поддержки — /support_here",
        )

    if cmd == "/help":
        return reply_send_message(
            chat_id,
            "Команды:\n/start — id пользователя/группы + подключение\n"
            "/id — показать chat_id / user id\n"
            "/support_here — группа-приёмник поддержки\n"
            "/support_alerts email — уведомления о ответах в ЛС\n"
            "/support SUP-XXXXXXXX текст — ответ оператора\n"
            "/history SUP-XXXXXXXX — история обращения\n"
            "Поиск в группе: #SUP_… или #u_email\n"
            "/status /mute /unmute /unlink /settings\n\n"
            "Бот не принимает бизнес-решения.",
        )

    if cmd == "/settings":
        return reply_send_message(
            chat_id,
            "Изменить порог и включение уведомлений можно в приложении: Уведомления → Telegram.",
        )

    if cmd == "/mute":
        _mute_chat(db, str(chat_id), hours=24)
        return reply_send_message(chat_id, "Уведомления на паузе на 24 часа.")

    if cmd == "/unmute":
        _unmute_chat(db, str(chat_id))
        return reply_send_message(chat_id, "Уведомления возобновлены.")

    if cmd == "/unlink":
        n = unlink_private_by_chat(db, chat_id=str(chat_id))
        db.commit()
        if n == 0:
            return reply_send_message(chat_id, "Этот чат не был привязан.")
        return reply_send_message(
            chat_id,
            f"Отвязано компаний: {n}. Чтобы снова получать уведомления, "
            "создайте ссылку в приложении для нужной компании.",
        )

    if cmd == "/status":
        subs = (
            db.query(NotificationSubscription)
            .filter(
                NotificationSubscription.chat_id == str(chat_id),
                NotificationSubscription.channel_type == "telegram_private",
            )
            .all()
        )
        if not subs:
            return reply_send_message(chat_id, "Этот чат ещё не привязан к компании.")
        lines = [f"Привязано компаний: {len(subs)}"]
        for s in subs:
            lines.append(
                f"— status={s.status} active={'да' if s.is_active else 'нет'} "
                f"min={s.min_severity}"
            )
        return reply_send_message(chat_id, "\n".join(lines))

    if chat_type in {"group", "supergroup"} and text:
        token = consume_link_token(db, text.strip())
        if token and token.purpose == "group":
            existing = (
                db.query(NotificationSubscription)
                .filter(
                    NotificationSubscription.company_id == token.company_id,
                    NotificationSubscription.channel_type == "telegram_group",
                )
                .first()
            )
            if existing is None:
                existing = NotificationSubscription(
                    id=str(uuid4()),
                    company_id=token.company_id,
                    user_id=token.user_id,
                    channel_type="telegram_group",
                )
                db.add(existing)
            existing.chat_id = str(chat_id)
            existing.chat_title = chat.get("title")
            existing.status = "connected"
            existing.is_active = True
            existing.verified_at = datetime.now(timezone.utc)
            db.commit()
            return reply_send_message(
                chat_id,
                "Группа подключена к Аспекту. В группу уходят короткие карточки без финансовых деталей.",
            )

    return {"ok": True}


def _handle_callback(db: Session, callback: dict) -> dict:
    data = callback.get("data")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if data == "mute_24h" and chat_id:
        _mute_chat(db, str(chat_id), hours=24)
        return reply_send_message(chat_id, "Ок, пауза на 24 часа.")
    return {"ok": True}


def _handle_my_chat_member(member: dict) -> dict:
    """When bot is added to a group — announce group id."""
    chat = member.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = (chat.get("type") or "").lower()
    new = member.get("new_chat_member") or {}
    status = (new.get("status") or "").lower()
    if not chat_id:
        return {"ok": True}
    if chat_type not in {"group", "supergroup"}:
        return {"ok": True}
    if status not in {"member", "administrator"}:
        return {"ok": True}
    title = chat.get("title") or "группа"
    return reply_send_message(
        chat_id,
        f"Бот добавлен в «{title}».\n"
        f"ID этой группы: {chat_id}\n\n"
        "Чтобы сюда приходили обращения поддержки из приложения — "
        "напишите /support_here\n"
        "Ответ пользователю: reply на карточку SUP-…",
    )


def _mute_chat(db: Session, chat_id: str, hours: int) -> None:
    subs = (
        db.query(NotificationSubscription)
        .filter(NotificationSubscription.chat_id == chat_id)
        .all()
    )
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    for s in subs:
        s.muted_until = until
    db.commit()


def _unmute_chat(db: Session, chat_id: str) -> None:
    subs = (
        db.query(NotificationSubscription)
        .filter(NotificationSubscription.chat_id == chat_id)
        .all()
    )
    for s in subs:
        s.muted_until = None
    db.commit()
