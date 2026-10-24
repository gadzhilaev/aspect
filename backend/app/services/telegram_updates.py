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

logger = logging.getLogger(__name__)


def reply_send_message(chat_id: int | str, text: str, **extra) -> dict:
    return {"method": "sendMessage", "chat_id": chat_id, "text": text, **extra}


def handle_telegram_update(db: Session, update: dict) -> dict:
    """Process one Bot API Update. Same path for webhook and polling.

    Returns either ``{"ok": True}`` or a Telegram Bot API callback-style
    ``{"method": "sendMessage", ...}`` dict (webhook can return it; polling
    must POST it via sendMessage).
    """
    update_id = update.get("update_id")
    message = update.get("message") or update.get("edited_message") or {}
    callback = update.get("callback_query")
    if callback:
        return _handle_callback(db, callback)

    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    chat_id = chat.get("id")
    chat_type = (chat.get("type") or "").lower()
    if not chat_id:
        return {"ok": True}

    if text.startswith("/start"):
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
                "Команда /unlink отвязывает все компании этого чата.",
            )
        return reply_send_message(
            chat_id,
            "Аспект — уведомления о важных событиях для вашей компании.\n"
            "Подключение начинается из приложения. Команды: /help /status /mute /unmute /unlink",
        )

    if text.startswith("/help"):
        return reply_send_message(
            chat_id,
            "Команды:\n/start — подключение по ссылке из приложения\n"
            "/status — статус этого чата\n"
            "/mute — пауза 24ч\n/unmute — возобновить\n"
            "/unlink — отвязать все компании этого чата\n"
            "/settings — настройки в приложении\n\n"
            "Бот не принимает бизнес-решения.",
        )

    if text.startswith("/settings"):
        return reply_send_message(
            chat_id,
            "Изменить порог и включение уведомлений можно в приложении: Уведомления → Telegram.",
        )

    if text.startswith("/mute"):
        _mute_chat(db, str(chat_id), hours=24)
        return reply_send_message(chat_id, "Уведомления на паузе на 24 часа.")

    if text.startswith("/unmute"):
        _unmute_chat(db, str(chat_id))
        return reply_send_message(chat_id, "Уведомления возобновлены.")

    if text.startswith("/unlink"):
        n = unlink_private_by_chat(db, chat_id=str(chat_id))
        db.commit()
        if n == 0:
            return reply_send_message(chat_id, "Этот чат не был привязан.")
        return reply_send_message(
            chat_id,
            f"Отвязано компаний: {n}. Чтобы снова получать уведомления, "
            "создайте ссылку в приложении для нужной компании.",
        )

    if text.startswith("/status"):
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
