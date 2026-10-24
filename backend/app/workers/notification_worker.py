"""Process notification_outbox. Safe without Telegram token (marks skipped).

Never logs bot token, Authorization headers, or pairing payloads.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import NotificationOutbox, NotificationSubscription
from app.services.notifications import (
    mark_subscription_blocked,
    sanitize_telegram_error,
    subscription_allows_send,
)
from app.services.telegram_news_policy import quiet_hours_status

logger = logging.getLogger(__name__)


def worker_kind_allowlist(settings=None) -> frozenset[str] | None:
    """Return allowed outbox kinds, or None when the worker may process all kinds."""
    settings = settings or get_settings()
    raw = (getattr(settings, "telegram_outbox_kinds", None) or "").strip()
    if not raw:
        return None
    kinds = frozenset(k.strip() for k in raw.split(",") if k.strip())
    return kinds or None


def process_outbox_once(db: Session | None = None) -> int:
    own = db is None
    session = db or SessionLocal()
    settings = get_settings()
    now = datetime.now(timezone.utc)
    processed = 0
    try:
        q = session.query(NotificationOutbox).filter(
            NotificationOutbox.status.in_(["pending", "retry", "uncertain"]),
        )
        allowed_kinds = worker_kind_allowlist(settings)
        if allowed_kinds is not None:
            q = q.filter(NotificationOutbox.kind.in_(allowed_kinds))
        rows = q.order_by(NotificationOutbox.created_at.asc()).limit(50).all()
        for row in rows:
            next_at = row.next_attempt_at
            if next_at is not None:
                if next_at.tzinfo is None:
                    next_at = next_at.replace(tzinfo=timezone.utc)
                if next_at > now:
                    continue

            allowed, reason = subscription_allows_send(session, outbox=row)
            if not allowed:
                if reason == "quiet_hours" and row.subscription_id:
                    sub = session.get(NotificationSubscription, row.subscription_id)
                    resume = None
                    if sub is not None:
                        q = quiet_hours_status(sub, now=now)
                        resume = q.get("resume_at")
                    row.status = "pending"
                    row.next_attempt_at = resume or (now + timedelta(minutes=30))
                    row.last_error = "deferred_quiet_hours"
                    processed += 1
                    logger.info("outbox_deferred_quiet id=%s", row.id)
                    continue
                row.status = "skipped"
                row.last_error = f"pre_send_denied:{reason}"
                row.attempts += 1
                processed += 1
                logger.info(
                    "outbox_skipped id=%s reason=%s",
                    row.id,
                    reason,
                )
                continue

            if not settings.telegram_bot_token:
                row.attempts += 1
                row.status = "skipped"
                row.last_error = "TELEGRAM_BOT_TOKEN not configured — skipped"
                processed += 1
                continue

            outcome = _send(row, settings.telegram_bot_token)
            row.attempts += 1
            if outcome == "sent":
                row.status = "sent"
                row.sent_at = datetime.now(timezone.utc)
                row.last_error = None
            elif outcome == "blocked":
                row.status = "blocked"
                row.last_error = "telegram_403_blocked"
                mark_subscription_blocked(session, row.subscription_id)
            elif outcome == "rate_limited":
                row.status = "retry"
                retry_after = int((row.payload_json or {}).get("_retry_after") or 30)
                row.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                    seconds=max(5, min(retry_after, 600))
                )
                row.last_error = "telegram_429"
                if "_retry_after" in (row.payload_json or {}):
                    payload = dict(row.payload_json or {})
                    payload.pop("_retry_after", None)
                    row.payload_json = payload
            elif outcome == "uncertain":
                # Timeout after possible accept — do not claim failure or success.
                if row.attempts >= 5:
                    row.status = "uncertain"
                    row.last_error = "timeout_after_possible_accept"
                else:
                    row.status = "uncertain"
                    row.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                        minutes=2 ** min(row.attempts, 4)
                    )
                    row.last_error = "timeout_uncertain"
            else:
                if row.attempts >= 5:
                    row.status = "failed"
                else:
                    row.status = "retry"
                    row.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                        minutes=2 ** row.attempts
                    )
            processed += 1
        session.commit()
    finally:
        if own:
            session.close()
    return processed


def _send(row: NotificationOutbox, token: str) -> str:
    """Return sent|blocked|rate_limited|uncertain|failed."""
    payload = row.payload_json or {}
    text = payload.get("text", "")
    buttons = payload.get("buttons") or []
    reply_markup = None
    if buttons:
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": b["text"], "url": b["url"]}
                    if "url" in b
                    else {
                        "text": b["text"],
                        "callback_data": b.get("callback_data", "noop"),
                    }
                ]
                for b in buttons
            ]
        }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": row.chat_id,
                    "text": text,
                    "reply_markup": reply_markup,
                },
            )
            if resp.status_code == 403:
                row.last_error = sanitize_telegram_error(resp.text)
                return "blocked"
            if resp.status_code == 429:
                retry_after = 30
                try:
                    body = resp.json()
                    retry_after = int(
                        (body.get("parameters") or {}).get("retry_after")
                        or body.get("retry_after")
                        or 30
                    )
                except Exception:  # noqa: BLE001
                    retry_after = 30
                payload = dict(row.payload_json or {})
                payload["_retry_after"] = retry_after
                row.payload_json = payload
                row.last_error = "telegram_429"
                return "rate_limited"
            if resp.status_code >= 400:
                row.last_error = sanitize_telegram_error(resp.text)
                return "failed"
            return "sent"
    except httpx.TimeoutException:
        row.last_error = "http_timeout"
        return "uncertain"
    except Exception as exc:  # noqa: BLE001
        row.last_error = sanitize_telegram_error(str(exc))
        return "failed"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    n = process_outbox_once()
    print(f"processed={n}")
