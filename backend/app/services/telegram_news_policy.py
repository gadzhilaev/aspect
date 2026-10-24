"""TG-4: eligibility, novelty watermark, quiet hours, news outbox payload.

v1 policy is intentionally narrow: private subscription + risk + usable
company_calculated Impact above configured threshold + novelty watermark.
Does not cover profile-only / severity-only / financial-feature signals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Company, Event, EventImpact, EventSource, NotificationSubscription
from app.services.assessment_explain import SCORE_KIND_COMPANY
from app.services.impact import IMPACT_STATUS_ACTIVE
from app.services.notifications import (
    event_open_url,
    impact_score_meets_min_severity,
    public_web_base_url,
    user_is_company_member,
)

logger = logging.getLogger(__name__)

NEWS_KIND = "news"
NEWS_DEDUPE_PREFIX = "news:v1"
POLICY_VERSION = "telegram_news_v1"

# Human-facing scope (API / UI). Do not promise broader coverage.
POLICY_SCOPE_NOTE = (
    "Автоуведомления v1 (если включены сервером): только риск-события с актуальным "
    "расчётом влияния по компании (индекс влияния) выше вашего порога. "
    "Нейтральные/прочие новости, сигналы только по важности события, совпадения по "
    "профилю без расчёта и финансовые what-if в Telegram не уходят. "
    "При подключении архив не рассылается."
)


@dataclass(frozen=True)
class EligibilityDecision:
    allowed: bool
    reason: str
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "detail": self.detail,
            "policy": POLICY_VERSION,
        }


def news_notifications_enabled() -> bool:
    return bool(getattr(get_settings(), "telegram_news_notifications_enabled", False))


def controlled_test_pair() -> tuple[str, str] | None:
    """Return (subscription_id, event_id) when TG-5 isolated allowlist is set."""
    raw = (getattr(get_settings(), "telegram_news_controlled_pair", None) or "").strip()
    if not raw or ":" not in raw:
        return None
    sub_id, event_id = raw.split(":", 1)
    sub_id, event_id = sub_id.strip(), event_id.strip()
    if not sub_id or not event_id:
        return None
    return sub_id, event_id


def is_controlled_test_pair(*, subscription_id: str, event_id: str) -> bool:
    pair = controlled_test_pair()
    return pair is not None and pair == (subscription_id, event_id)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def stamp_auto_notify_watermark(
    sub: NotificationSubscription, *, when: datetime | None = None
) -> datetime:
    """Set watermark so archive / delayed old pubs are not backfilled."""
    ts = _aware(when) or datetime.now(timezone.utc)
    sub.auto_notify_since = ts
    return ts


def impact_score_kind(impact: EventImpact) -> str | None:
    br = impact.score_breakdown_json or {}
    kind = br.get("score_kind")
    if isinstance(kind, str) and kind:
        return kind
    basis = br.get("assessment_basis") or {}
    if isinstance(basis, dict):
        k2 = basis.get("score_kind")
        if isinstance(k2, str) and k2:
            return k2
    return None


def event_publication_at(event: Event) -> datetime | None:
    """Editorial/publication clock (occurred_at). Not Impact.computed_at."""
    return _aware(event.occurred_at) or _aware(event.effective_from)


def event_arrival_at(event: Event) -> datetime | None:
    """First time the event existed in our DB (system arrival)."""
    return _aware(event.created_at)


def novelty_allows(
    *,
    event: Event,
    watermark: datetime | None,
) -> EligibilityDecision:
    """Novelty: both publication and system-arrival must be at/after watermark.

    Delayed import of an old article: occurred_at is old → deny even if created_at
    is recent. Fresh Impact.computed_at alone never makes an old event new.
    """
    if watermark is None:
        return EligibilityDecision(False, "watermark_missing")
    wm = _aware(watermark)
    assert wm is not None
    pub = event_publication_at(event)
    arr = event_arrival_at(event)
    if pub is None:
        return EligibilityDecision(False, "publication_time_unknown")
    if arr is None:
        return EligibilityDecision(False, "arrival_time_unknown")
    if pub < wm:
        return EligibilityDecision(
            False,
            "novelty_publication_before_watermark",
            detail="Published/occurred before auto-notify watermark",
        )
    if arr < wm:
        return EligibilityDecision(
            False,
            "novelty_arrival_before_watermark",
            detail="Event arrived in system before auto-notify watermark",
        )
    return EligibilityDecision(True, "novelty_ok")


def evaluate_news_eligibility(
    db: Session,
    *,
    sub: NotificationSubscription,
    event: Event,
    impact: EventImpact,
    check_quiet_hours: bool = False,
    now: datetime | None = None,
) -> EligibilityDecision:
    """Single allow/deny gate with machine-readable reason."""
    controlled = is_controlled_test_pair(subscription_id=sub.id, event_id=event.id)
    if not news_notifications_enabled() and not controlled:
        return EligibilityDecision(False, "feature_disabled")

    if sub.channel_type != "telegram_private":
        return EligibilityDecision(False, "not_private_channel")
    if sub.status != "connected" or not sub.is_active:
        return EligibilityDecision(False, "subscription_inactive")
    if not sub.chat_id:
        return EligibilityDecision(False, "chat_missing")
    if not sub.risks_enabled:
        return EligibilityDecision(False, "risks_disabled")
    if not user_is_company_member(db, user_id=sub.user_id, company_id=sub.company_id):
        return EligibilityDecision(False, "membership_missing")
    if sub.company_id != impact.company_id:
        return EligibilityDecision(False, "company_mismatch")

    now_utc = _aware(now) or datetime.now(timezone.utc)
    if sub.muted_until and _aware(sub.muted_until) and _aware(sub.muted_until) > now_utc:
        return EligibilityDecision(False, "muted")

    if event.id != impact.event_id:
        return EligibilityDecision(False, "event_impact_mismatch")
    if bool(event.is_demo) and not controlled:
        return EligibilityDecision(False, "event_demo")
    if event.status != "active":
        return EligibilityDecision(False, "event_inactive")
    if event.event_type != "risk":
        return EligibilityDecision(False, "event_not_risk")
    # Unknown significance must not ride into Telegram as an implied critical risk.
    if event.severity is None:
        return EligibilityDecision(False, "severity_unknown")

    if impact.status not in IMPACT_STATUS_ACTIVE:
        return EligibilityDecision(False, "impact_not_usable")
    kind = impact_score_kind(impact)
    if kind != SCORE_KIND_COMPANY:
        return EligibilityDecision(
            False,
            "score_kind_not_company_calculated",
            detail=kind or "missing",
        )

    # Threshold: existing min_severity → impact_score (not Event.severity / not scaled down).
    if not impact_score_meets_min_severity(impact.impact_score, sub.min_severity):
        return EligibilityDecision(False, "below_threshold")

    nov = novelty_allows(event=event, watermark=sub.auto_notify_since)
    if not nov.allowed:
        return nov

    if check_quiet_hours:
        q = quiet_hours_status(sub, now=now_utc)
        if q["in_quiet_hours"]:
            return EligibilityDecision(
                False,
                "quiet_hours",
                detail=q.get("resume_at_iso"),
            )

    return EligibilityDecision(True, "eligible")


def quiet_hours_status(
    sub: NotificationSubscription, *, now: datetime | None = None
) -> dict[str, Any]:
    """Parse quiet_hours_json: {\"start\": \"HH:MM\", \"end\": \"HH:MM\"} in sub.timezone.

    Overnight windows (22:00–08:00) supported. Missing/invalid config → not quiet.
    """
    now_utc = _aware(now) or datetime.now(timezone.utc)
    raw = sub.quiet_hours_json
    if not isinstance(raw, dict):
        return {"in_quiet_hours": False, "resume_at": None, "resume_at_iso": None}
    start_s = str(raw.get("start") or "").strip()
    end_s = str(raw.get("end") or "").strip()
    if not start_s or not end_s:
        return {"in_quiet_hours": False, "resume_at": None, "resume_at_iso": None}
    try:
        sh, sm = (int(x) for x in start_s.split(":")[:2])
        eh, em = (int(x) for x in end_s.split(":")[:2])
        start_t = time(sh, sm)
        end_t = time(eh, em)
    except (TypeError, ValueError):
        return {"in_quiet_hours": False, "resume_at": None, "resume_at_iso": None}

    tz_name = (sub.timezone or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    local = now_utc.astimezone(tz)
    local_t = local.time().replace(second=0, microsecond=0)

    if start_t == end_t:
        return {"in_quiet_hours": False, "resume_at": None, "resume_at_iso": None}

    if start_t < end_t:
        in_quiet = start_t <= local_t < end_t
        resume_local = datetime.combine(local.date(), end_t, tzinfo=tz)
        if in_quiet and resume_local <= local:
            resume_local = resume_local + timedelta(days=1)
    else:
        # Overnight: e.g. 22:00–08:00
        in_quiet = local_t >= start_t or local_t < end_t
        if local_t >= start_t:
            resume_local = datetime.combine(local.date() + timedelta(days=1), end_t, tzinfo=tz)
        else:
            resume_local = datetime.combine(local.date(), end_t, tzinfo=tz)

    if not in_quiet:
        return {"in_quiet_hours": False, "resume_at": None, "resume_at_iso": None}
    resume_utc = resume_local.astimezone(timezone.utc)
    return {
        "in_quiet_hours": True,
        "resume_at": resume_utc,
        "resume_at_iso": resume_utc.isoformat(),
    }


def primary_publisher(db: Session, event_id: str) -> str | None:
    src = (
        db.query(EventSource)
        .filter(EventSource.event_id == event_id)
        .order_by(EventSource.source_quality.desc())
        .first()
    )
    return src.publisher if src else None


def build_news_telegram_payload(
    db: Session,
    *,
    event: Event,
    impact: EventImpact,
    company_id: str,
    controlled_test: bool = False,
) -> dict[str, Any]:
    """Safe card: company, title, priority basis, source; optional public HTTPS button."""
    company = db.get(Company, company_id)
    company_name = company.name if company else "компания"
    publisher = primary_publisher(db, event.id) or "открытый источник"
    score = float(impact.impact_score)
    prefix = "ТЕСТ — не реальная новость\n\n" if controlled_test or bool(event.is_demo) else ""
    text = (
        f"{prefix}"
        f"Новость для «{company_name}»\n\n"
        f"{event.title}\n\n"
        f"Почему в приоритете: по данным профиля компании рассчитан индекс влияния "
        f"{score:.0f}/100 — это приоритет разбора, не вероятность и не процент потерь.\n"
        f"Источник: {publisher}"
    )
    buttons: list[dict[str, str]] = []
    open_url = event_open_url(event.id)
    if open_url and public_web_base_url():
        buttons.append({"text": "Открыть разбор", "url": open_url})
    buttons.append({"text": "Пауза на 24 часа", "callback_data": "mute_24h"})
    return {
        "text": text,
        "buttons": buttons,
        "kind": NEWS_KIND,
        "policy": POLICY_VERSION,
        "company_name": company_name,
        "event_id": event.id,
        "impact_score": score,
        "score_kind": SCORE_KIND_COMPANY,
        "deep_link": open_url,
        "has_public_open_url": bool(open_url),
    }


def news_dedupe_key(*, subscription_id: str, event_id: str) -> str:
    return f"{NEWS_DEDUPE_PREFIX}:{subscription_id}:{event_id}"
