"""Outbox-based notification enqueue — never send Telegram inside request path."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Company,
    CompanyMembership,
    Event,
    EventImpact,
    NotificationOutbox,
    NotificationSubscription,
    TelegramLinkToken,
    User,
)

logger = logging.getLogger(__name__)

TEST_MESSAGE_TEXT = (
    "Тестовое уведомление Аспекта. Telegram подключён.\n"
    "Это проверка доставки, а не предупреждение о новости."
)

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def public_web_base_url() -> str | None:
    """Return https public site base or None (localhost / empty rejected)."""
    settings = get_settings()
    raw = (getattr(settings, "public_web_base_url", None) or "").strip()
    if not raw:
        # Fall back to deep_link_base parent only if it looks like a public https host
        raw = (settings.deep_link_base or "").strip()
        # deep_link_base is often .../e — strip path for site root later in callers
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return None
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local"):
        return None
    if not host:
        return None
    return f"https://{host}".rstrip("/")


def event_open_url(event_id: str) -> str | None:
    base = public_web_base_url()
    if not base:
        return None
    settings = get_settings()
    deep = (settings.deep_link_base or "").strip()
    # Prefer dedicated deep_link_base path when it shares the same public host
    if deep.startswith("https://"):
        p = urlparse(deep)
        if p.hostname and p.hostname.lower() == urlparse(base).hostname:
            return f"{deep.rstrip('/')}/{event_id}"
    return f"{base}/news/{event_id}"


def issue_link_token(
    db: Session, *, user_id: str, company_id: str, purpose: str = "private"
) -> dict[str, str]:
    settings = get_settings()
    raw = secrets.token_urlsafe(24)
    token = TelegramLinkToken(
        id=str(uuid4()),
        user_id=user_id,
        company_id=company_id,
        token_hash=hash_token(raw),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=settings.telegram_link_token_ttl_minutes),
    )
    db.add(token)
    db.flush()
    bot = settings.telegram_bot_username.lstrip("@")
    deep_link = f"https://t.me/{bot}?start={raw}"
    return {
        "token": raw,
        "deep_link": deep_link,
        "expires_at": token.expires_at.isoformat(),
    }


def consume_link_token(db: Session, raw: str) -> TelegramLinkToken | None:
    """Atomically consume a pairing token. Concurrent callers: at most one wins."""
    if not raw or len(raw) > 200:
        return None
    now = datetime.now(timezone.utc)
    digest = hash_token(raw)
    # Atomic claim: UPDATE … WHERE consumed_at IS NULL
    updated = (
        db.query(TelegramLinkToken)
        .filter(
            TelegramLinkToken.token_hash == digest,
            TelegramLinkToken.consumed_at.is_(None),
            TelegramLinkToken.expires_at > now,
        )
        .update({"consumed_at": now}, synchronize_session="fetch")
    )
    if updated != 1:
        return None
    row = (
        db.query(TelegramLinkToken)
        .filter(TelegramLinkToken.token_hash == digest)
        .first()
    )
    return row


def user_is_company_member(db: Session, *, user_id: str, company_id: str) -> bool:
    return (
        db.query(CompanyMembership.id)
        .filter(
            CompanyMembership.user_id == user_id,
            CompanyMembership.company_id == company_id,
        )
        .first()
        is not None
    )


def chat_bound_to_other_user(
    db: Session, *, chat_id: str, user_id: str, channel_type: str = "telegram_private"
) -> bool:
    """True if this chat_id is already linked to a different user (any company)."""
    row = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.chat_id == chat_id,
            NotificationSubscription.channel_type == channel_type,
            NotificationSubscription.status == "connected",
            NotificationSubscription.user_id != user_id,
        )
        .first()
    )
    return row is not None


def bind_private_subscription(
    db: Session,
    *,
    token: TelegramLinkToken,
    chat_id: str,
    chat_title: str | None,
) -> tuple[NotificationSubscription | None, str | None]:
    """Bind private chat after token consume. Returns (sub, error_code)."""
    if not user_is_company_member(
        db, user_id=token.user_id, company_id=token.company_id
    ):
        return None, "membership_revoked"
    if chat_bound_to_other_user(db, chat_id=chat_id, user_id=token.user_id):
        return None, "chat_bound_to_other_user"

    existing = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.user_id == token.user_id,
            NotificationSubscription.company_id == token.company_id,
            NotificationSubscription.channel_type == "telegram_private",
        )
        .first()
    )
    if existing is None:
        existing = NotificationSubscription(
            id=str(uuid4()),
            company_id=token.company_id,
            user_id=token.user_id,
            channel_type="telegram_private",
        )
        db.add(existing)
    existing.chat_id = str(chat_id)
    existing.chat_title = chat_title or "private"
    existing.status = "connected"
    existing.is_active = True
    existing.verified_at = datetime.now(timezone.utc)
    # Connecting / rebinding never backfills the archive into Telegram.
    from app.services.telegram_news_policy import stamp_auto_notify_watermark

    stamp_auto_notify_watermark(existing)
    if not existing.min_severity:
        existing.min_severity = "medium"
    db.flush()
    return existing, None


def unlink_private_by_chat(
    db: Session, *, chat_id: str, user_id: str | None = None
) -> int:
    """Disconnect all private subscriptions for this chat_id.

    Semantics (/unlink): affects every telegram_private row with this chat_id
    (all companies of the linking user). Does not pick an arbitrary "first" row.
    If user_id is set, only that user's rows are unlinked.
    """
    q = db.query(NotificationSubscription).filter(
        NotificationSubscription.chat_id == chat_id,
        NotificationSubscription.channel_type == "telegram_private",
    )
    if user_id is not None:
        q = q.filter(NotificationSubscription.user_id == user_id)
    n = 0
    for sub in q.all():
        sub.is_active = False
        sub.status = "disconnected"
        sub.chat_id = None
        sub.verified_at = None
        n += 1
    db.flush()
    return n


# min_severity label → minimum impact_score (0–100 index of priority).
# Not Event.severity. Do not lower these for tests.
IMPACT_SCORE_THRESHOLDS = {"low": 0, "medium": 40, "high": 70, "critical": 90}


def impact_score_meets_min_severity(score: float, min_severity: str) -> bool:
    """Compare company impact_score to subscription threshold labels."""
    return float(score) >= float(IMPACT_SCORE_THRESHOLDS.get(min_severity, 40))


def impact_meets_threshold(impact: EventImpact, sub: NotificationSubscription) -> bool:
    if not sub.is_active or sub.status != "connected":
        return False
    if sub.muted_until:
        muted = _aware(sub.muted_until)
        if muted > datetime.now(timezone.utc):
            return False
    return impact_score_meets_min_severity(impact.impact_score, sub.min_severity)


def build_telegram_payload(
    event: Event, impact: EventImpact, *, for_group: bool = False
) -> dict[str, Any]:
    """Legacy impact card — kept for existing enqueue; TG-2 test path does not use it."""
    conf_label = (
        "высокая" if impact.confidence >= 0.8 else "средняя" if impact.confidence >= 0.55 else "низкая"
    )
    claims = impact.claims_json or {}
    text = (
        f"Событие для разбора\n\n"
        f"{event.title}\n"
        f"{impact.reason_summary}\n"
        f"Приоритет (индекс): {impact.impact_score:.0f}/100 · "
        f"качество данных: {conf_label} · "
        f"{claims.get('confirmed', 0)} факта, {claims.get('assumptions', 0)} предположение"
    )
    if for_group:
        text = (
            f"Событие для команды\n\n{event.title}\n"
            f"Приоритет: {impact.urgency}\n"
            f"Детали — в приложении Аспект"
        )
    buttons: list[dict[str, str]] = []
    open_url = event_open_url(event.id)
    if open_url:
        buttons.append({"text": "Открыть разбор", "url": open_url})
    buttons.append({"text": "Пауза на 24 часа", "callback_data": "mute_24h"})
    return {
        "text": text,
        "deep_link": open_url,
        "buttons": buttons,
        "is_estimate": True,
    }


def enqueue_impact_notifications(db: Session, impact: EventImpact, event: Event) -> int:
    """TG-4: enqueue news cards after a committed-ready Impact row (same transaction).

    Gated by TELEGRAM_NEWS_NOTIFICATIONS_ENABLED and telegram_news_policy eligibility.
    Idempotent via UniqueConstraint(dedupe_key). Does not call Telegram or models.
    Groups are out of v1 scope.
    """
    from app.services.telegram_news_policy import (
        NEWS_KIND,
        build_news_telegram_payload,
        evaluate_news_eligibility,
        news_dedupe_key,
        news_notifications_enabled,
        quiet_hours_status,
    )

    if not news_notifications_enabled():
        return 0
    if impact.status not in {"action_required", "monitor"}:
        return 0

    subs = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.company_id == impact.company_id,
            NotificationSubscription.channel_type == "telegram_private",
            NotificationSubscription.is_active.is_(True),
            NotificationSubscription.status == "connected",
        )
        .all()
    )
    created = 0
    now = datetime.now(timezone.utc)
    for sub in subs:
        decision = evaluate_news_eligibility(
            db, sub=sub, event=event, impact=impact, check_quiet_hours=False, now=now
        )
        if not decision.allowed:
            logger.info(
                "telegram_news_enqueue_denied subscription_id=%s event_id=%s reason=%s",
                sub.id,
                event.id,
                decision.reason,
            )
            continue
        if not sub.chat_id:
            continue
        dedupe = news_dedupe_key(subscription_id=sub.id, event_id=event.id)
        exists = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.dedupe_key == dedupe)
            .first()
        )
        if exists is not None:
            continue
        payload = build_news_telegram_payload(
            db, event=event, impact=impact, company_id=impact.company_id
        )
        next_at = now
        q = quiet_hours_status(sub, now=now)
        if q["in_quiet_hours"] and q.get("resume_at") is not None:
            next_at = q["resume_at"]
            payload = {**payload, "deferred_quiet_hours": True}
        row = NotificationOutbox(
            id=str(uuid4()),
            company_id=impact.company_id,
            subscription_id=sub.id,
            kind=NEWS_KIND,
            event_impact_id=impact.id,
            channel_type="telegram_private",
            chat_id=sub.chat_id,
            payload_json=payload,
            dedupe_key=dedupe,
            status="pending",
            attempts=0,
            next_attempt_at=next_at,
        )
        db.add(row)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            continue
        created += 1
        logger.info(
            "telegram_news_enqueued subscription_id=%s event_id=%s outbox_id=%s",
            sub.id,
            event.id,
            row.id,
        )
    return created


def enqueue_test_notification(
    db: Session,
    *,
    user: User,
    company_id: str,
    client_request_id: str | None = None,
) -> dict[str, Any]:
    """Queue a fixed test message for the caller's private subscription. No client chat_id/text."""
    settings = get_settings()
    cooldown = int(getattr(settings, "telegram_test_send_cooldown_seconds", 60) or 60)

    if not user_is_company_member(db, user_id=user.id, company_id=company_id):
        return {"ok": False, "error": "forbidden", "http_status": 403}

    sub = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.user_id == user.id,
            NotificationSubscription.company_id == company_id,
            NotificationSubscription.channel_type == "telegram_private",
        )
        .first()
    )
    if (
        sub is None
        or sub.status != "connected"
        or not sub.chat_id
    ):
        return {"ok": False, "error": "not_connected", "http_status": 409}

    now = datetime.now(timezone.utc)
    # Idempotency before rate limit so retries of the same client_request_id succeed.
    req_id = (client_request_id or "").strip()[:64] or str(uuid4())
    dedupe = f"test:{sub.id}:{req_id}"
    existing = (
        db.query(NotificationOutbox)
        .filter(NotificationOutbox.dedupe_key == dedupe)
        .first()
    )
    if existing is not None:
        return {
            "ok": True,
            "queued": False,
            "idempotent_replay": True,
            "outbox_id": existing.id,
            "status": existing.status,
            "delivery": "not_claimed",
            "message": "Повтор того же client_request_id — новая постановка не создана.",
        }

    recent = (
        db.query(NotificationOutbox)
        .filter(
            NotificationOutbox.subscription_id == sub.id,
            NotificationOutbox.kind == "test",
            NotificationOutbox.created_at
            >= now - timedelta(seconds=cooldown),
        )
        .order_by(NotificationOutbox.created_at.desc())
        .first()
    )
    if recent is not None:
        return {
            "ok": False,
            "error": "rate_limited",
            "http_status": 429,
            "retry_after_seconds": cooldown,
            "existing_outbox_id": recent.id,
            "existing_status": recent.status,
        }

    company = db.get(Company, company_id)
    company_name = company.name if company else "компания"
    payload: dict[str, Any] = {
        "text": TEST_MESSAGE_TEXT,
        "buttons": [],
        "kind": "test",
        "company_name": company_name,
    }
    # Optional open button only with public https base (never localhost)
    base = public_web_base_url()
    if base:
        payload["buttons"] = [{"text": "Открыть Аспект", "url": base}]

    row = NotificationOutbox(
        id=str(uuid4()),
        company_id=company_id,
        subscription_id=sub.id,
        kind="test",
        event_impact_id=None,
        channel_type="telegram_private",
        chat_id=sub.chat_id,
        payload_json=payload,
        dedupe_key=dedupe,
        status="pending",
        attempts=0,
        next_attempt_at=now,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        again = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.dedupe_key == dedupe)
            .first()
        )
        if again:
            return {
                "ok": True,
                "queued": False,
                "idempotent_replay": True,
                "outbox_id": again.id,
                "status": again.status,
                "delivery": "not_claimed",
            }
        return {"ok": False, "error": "conflict", "http_status": 409}

    return {
        "ok": True,
        "queued": True,
        "idempotent_replay": False,
        "outbox_id": row.id,
        "status": "pending",
        "delivery": "not_claimed",
        "message": "Сообщение поставлено в очередь. Это не подтверждение доставки.",
    }


def subscription_allows_send(
    db: Session, *, outbox: NotificationOutbox
) -> tuple[bool, str]:
    """Re-validate before worker send. Stale chat after unlink/rebind → deny.

    For kind=news also re-checks TG-4 eligibility (event/Impact may have changed).
    Quiet hours return reason ``quiet_hours`` — worker must defer, not skip.
    """
    if not outbox.subscription_id:
        return False, "missing_subscription_id"
    sub = db.get(NotificationSubscription, outbox.subscription_id)
    if sub is None:
        return False, "subscription_missing"
    if sub.status == "blocked":
        return False, "subscription_blocked"
    if sub.status != "connected" or not sub.is_active:
        return False, "subscription_inactive"
    if not sub.chat_id or sub.chat_id != outbox.chat_id:
        return False, "chat_mismatch"
    if sub.channel_type != outbox.channel_type:
        return False, "channel_mismatch"
    if sub.company_id != outbox.company_id:
        return False, "company_mismatch"
    if not user_is_company_member(db, user_id=sub.user_id, company_id=sub.company_id):
        return False, "membership_missing"
    if sub.muted_until and _aware(sub.muted_until) > datetime.now(timezone.utc):
        return False, "muted"

    if outbox.kind == "news":
        from app.services.telegram_news_policy import (
            evaluate_news_eligibility,
            news_notifications_enabled,
            quiet_hours_status,
        )

        if not outbox.event_impact_id:
            return False, "news_missing_impact"
        impact = db.get(EventImpact, outbox.event_impact_id)
        if impact is None:
            return False, "impact_missing"
        event = db.get(Event, impact.event_id)
        if event is None:
            return False, "event_missing"
        # Quiet hours: defer (worker), do not permanent-skip.
        q = quiet_hours_status(sub)
        if q["in_quiet_hours"]:
            return False, "quiet_hours"
        # evaluate_news_eligibility itself gates feature flag / controlled pair.
        decision = evaluate_news_eligibility(
            db, sub=sub, event=event, impact=impact, check_quiet_hours=False
        )
        if not decision.allowed:
            return False, f"news_ineligible:{decision.reason}"
    return True, "ok"


def sanitize_telegram_error(text: str) -> str:
    """Strip secrets from Telegram/http error bodies before persistence/logs."""
    s = (text or "")[:400]
    # Never persist bot tokens if somehow echoed
    if "bot" in s.lower() and ":" in s:
        s = "telegram_api_error"
    return s.replace("\n", " ")


def mark_subscription_blocked(db: Session, subscription_id: str | None) -> None:
    if not subscription_id:
        return
    sub = db.get(NotificationSubscription, subscription_id)
    if sub is None:
        return
    sub.status = "blocked"
    sub.is_active = False
    db.flush()
