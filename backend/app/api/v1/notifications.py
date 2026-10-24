from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_company_member
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Company, CompanyMembership, NotificationOutbox, NotificationSubscription, User
from app.services.notifications import enqueue_test_notification, issue_link_token
from app.services.telegram_news_policy import (
    POLICY_SCOPE_NOTE,
    news_notifications_enabled,
    stamp_auto_notify_watermark,
)

router = APIRouter(tags=["notifications"])


class SubscriptionPatchIn(BaseModel):
    min_severity: str | None = None
    risks_enabled: bool | None = None
    opportunities_enabled: bool | None = None
    digest_enabled: bool | None = None
    quiet_hours_json: dict | None = None
    timezone: str | None = None
    is_active: bool | None = None
    event_categories_json: list | None = None


class LinkTokenIn(BaseModel):
    company_id: str = Field(...)


class TestSendIn(BaseModel):
    company_id: str = Field(...)
    client_request_id: str | None = Field(default=None, max_length=64)


def _company_name(db: Session, company_id: str) -> str | None:
    c = db.get(Company, company_id)
    return c.name if c else None


def _sub_out(db: Session, s: NotificationSubscription) -> dict:
    status_map = {
        "pending": "Ожидаем подтверждения",
        "connected": "Подключён",
        "disconnected": "Не подключён",
        "blocked": "Бот заблокирован",
    }
    linked = s.status == "connected" and bool(s.chat_id)
    return {
        "id": s.id,
        "company_id": s.company_id,
        "company_name": _company_name(db, s.company_id),
        "channel_type": s.channel_type,
        "status": s.status,
        "status_label": status_map.get(s.status, s.status),
        "linked": linked,
        "notifications_enabled": bool(linked and s.is_active and s.status == "connected"),
        # Never expose raw chat_id to clients that don't need it — keep for owner debug optional
        "chat_bound": bool(s.chat_id),
        "chat_title": s.chat_title if linked else None,
        "min_severity": s.min_severity,
        "risks_enabled": s.risks_enabled,
        "opportunities_enabled": s.opportunities_enabled,
        "digest_enabled": s.digest_enabled,
        "quiet_hours_json": s.quiet_hours_json,
        "timezone": s.timezone,
        "is_active": s.is_active,
        "muted_until": s.muted_until,
        "verified_at": s.verified_at,
    }


def _disconnected_stub(company_id: str | None = None) -> dict:
    return {
        "id": None,
        "company_id": company_id,
        "company_name": None,
        "channel_type": "telegram_private",
        "status": "disconnected",
        "status_label": "Не подключён",
        "linked": False,
        "notifications_enabled": False,
        "chat_bound": False,
        "chat_title": None,
    }


@router.get("/companies/{company_id}/notification-settings")
def notification_settings(
    company_id: str,
    db: Session = Depends(get_db),
    membership: CompanyMembership = Depends(require_company_member),
    user: User = Depends(get_current_user),
) -> dict:
    _ = membership
    # Scope to current user — do not leak other members' telegram bindings
    subs = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.company_id == company_id,
            NotificationSubscription.user_id == user.id,
        )
        .all()
    )
    private = next((s for s in subs if s.channel_type == "telegram_private"), None)
    group = next((s for s in subs if s.channel_type == "telegram_group"), None)
    company = db.get(Company, company_id)
    return {
        "company_id": company_id,
        "company_name": company.name if company else None,
        "scope_note": "Настройки Telegram действуют только для выбранной компании и вашего аккаунта.",
        "news_policy_note": POLICY_SCOPE_NOTE,
        "news_notifications_server_enabled": news_notifications_enabled(),
        "telegram_private": _sub_out(db, private) if private else _disconnected_stub(company_id),
        "telegram_group": _sub_out(db, group) if group else {
            **_disconnected_stub(company_id),
            "channel_type": "telegram_group",
        },
        "channels": [_sub_out(db, s) for s in subs],
    }


@router.post("/telegram/link-token")
def create_private_link_token(
    body: LinkTokenIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    require_company_member(body.company_id, db, user)
    result = issue_link_token(db, user_id=user.id, company_id=body.company_id, purpose="private")
    db.commit()
    return {
        **result,
        "company_id": body.company_id,
        "instructions": (
            "Откройте ссылку на телефоне и нажмите Start в личном чате с ботом. "
            "Токен одноразовый и действует ограниченное время. "
            "Открытие ссылки само по себе не подтверждает подключение — дождитесь статуса в приложении."
        ),
    }


@router.post("/telegram/groups/link-token")
def create_group_link_token(
    body: LinkTokenIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    membership = require_company_member(body.company_id, db, user)
    if membership.role not in {"owner", "admin"}:
        raise AppError("FORBIDDEN", "Только владелец или админ может привязать группу", 403)
    result = issue_link_token(db, user_id=user.id, company_id=body.company_id, purpose="group")
    db.commit()
    return {
        **result,
        "instructions": "Добавьте бота в группу и отправьте код подтверждения из deep_link.",
    }


@router.post("/telegram/test-send")
def telegram_test_send(
    body: TestSendIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Queue a fixed test message via outbox. Does not claim delivery."""
    require_company_member(body.company_id, db, user)
    result = enqueue_test_notification(
        db,
        user=user,
        company_id=body.company_id,
        client_request_id=body.client_request_id,
    )
    if not result.get("ok"):
        err = result.get("error")
        status = int(result.get("http_status") or 400)
        messages = {
            "forbidden": "Нет доступа к компании",
            "not_connected": "Сначала подключите Telegram для этой компании",
            "rate_limited": "Слишком частые тестовые отправки. Подождите и повторите.",
            "conflict": "Конфликт постановки в очередь",
        }
        raise AppError(
            err.upper() if isinstance(err, str) else "TEST_SEND_FAILED",
            messages.get(str(err), "Не удалось поставить тестовое сообщение в очередь"),
            status,
            details=[{k: v for k, v in result.items() if k not in {"ok"}}],
        )
    db.commit()
    return result


@router.get("/telegram/outbox/{outbox_id}")
def telegram_outbox_status(
    outbox_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = db.get(NotificationOutbox, outbox_id)
    if row is None:
        raise AppError("NOT_FOUND", "Запись очереди не найдена", 404)
    require_company_member(row.company_id, db, user)
    if row.subscription_id:
        sub = db.get(NotificationSubscription, row.subscription_id)
        if sub is not None and sub.user_id != user.id:
            raise AppError("FORBIDDEN", "Нет доступа к этой записи", 403)
    return {
        "outbox_id": row.id,
        "status": row.status,
        "kind": row.kind,
        "attempts": row.attempts,
        "sent_at": row.sent_at,
        "delivery": "not_claimed" if row.status != "sent" else "send_accepted_unconfirmed_read",
        "message": (
            "Статус sendMessage у Telegram не означает, что сообщение прочитано."
            if row.status == "sent"
            else "Ожидание обработки воркером или повтор."
        ),
    }


@router.patch("/notification-subscriptions/{subscription_id}")
def patch_subscription(
    subscription_id: str,
    body: SubscriptionPatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    sub = db.get(NotificationSubscription, subscription_id)
    if sub is None:
        raise AppError("NOT_FOUND", "Подписка не найдена", 404)
    if sub.user_id != user.id:
        raise AppError("FORBIDDEN", "Это не ваша подписка", 403)
    require_company_member(sub.company_id, db, user)
    was_active = bool(sub.is_active)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(sub, field, value)
    # Pausing notifications must not clear chat binding
    if body.is_active is False and sub.status == "connected":
        sub.is_active = False
    # Re-enable: advance watermark so archive is not backfilled.
    if body.is_active is True and not was_active and sub.status == "connected":
        stamp_auto_notify_watermark(sub)
    db.commit()
    db.refresh(sub)
    return _sub_out(db, sub)


@router.delete("/notification-subscriptions/{subscription_id}")
def delete_subscription(
    subscription_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Unlink: clear chat binding. Distinct from pausing notifications (PATCH is_active)."""
    sub = db.get(NotificationSubscription, subscription_id)
    if sub is None:
        raise AppError("NOT_FOUND", "Подписка не найдена", 404)
    if sub.user_id != user.id:
        raise AppError("FORBIDDEN", "Это не ваша подписка", 403)
    require_company_member(sub.company_id, db, user)
    sub.is_active = False
    sub.status = "disconnected"
    sub.chat_id = None
    sub.verified_at = None
    db.commit()
    return {
        "message": "Telegram отвязан для этой компании",
        "id": subscription_id,
        "operation": "unlink",
    }
