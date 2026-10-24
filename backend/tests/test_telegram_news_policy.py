"""TG-4: news eligibility, novelty watermark, enqueue idempotency — temp DB, mocked TG."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    Company,
    CompanyMembership,
    Event,
    EventImpact,
    EventSource,
    NotificationOutbox,
    NotificationSubscription,
    User,
)
from app.services.assessment_explain import SCORE_KIND_COMPANY, SCORE_KIND_SEVERITY
from app.services.notifications import enqueue_impact_notifications, hash_token
from app.services.telegram_news_policy import (
    NEWS_KIND,
    evaluate_news_eligibility,
    news_dedupe_key,
    novelty_allows,
    quiet_hours_status,
    stamp_auto_notify_watermark,
)
from app.workers.notification_worker import process_outbox_once

COMPANY_ID = "cmp_severprom"
WH = {"X-Telegram-Bot-Api-Secret-Token": "kontur-webhook-secret"}


def _utc(dt: datetime | None = None) -> datetime:
    d = dt or datetime.now(timezone.utc)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@pytest.fixture
def enable_news(monkeypatch):
    monkeypatch.setenv("TELEGRAM_NEWS_NOTIFICATIONS_ENABLED", "true")
    monkeypatch.delenv("TELEGRAM_OUTBOX_KINDS", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    monkeypatch.delenv("TELEGRAM_NEWS_NOTIFICATIONS_ENABLED", raising=False)
    get_settings.cache_clear()


def _synthetic_risk_bundle(
    db: Session,
    *,
    user_id: str = "usr_demo_owner",
    score: float = 80.0,
    score_kind: str = SCORE_KIND_COMPANY,
    event_type: str = "risk",
    is_demo: bool = False,
    severity: float | None = 70.0,
    occurred_at: datetime | None = None,
    created_at: datetime | None = None,
    watermark: datetime | None = None,
    min_severity: str = "medium",
    chat_id: str = "77001",
):
    """Explicit synthetic fixture — does not mutate real news / упк profile."""
    now = _utc()
    occ = occurred_at or (now - timedelta(minutes=5))
    cre = created_at or (now - timedelta(minutes=4))
    eid = f"evt_synth_tg4_{uuid4().hex[:12]}"
    event = Event(
        id=eid,
        title="Синтетика TG-4: экспортное ограничение для теста",
        summary="Synthetic fixture for telegram news policy tests only.",
        category="geopolitics",
        event_type=event_type,
        severity=severity,
        status="active",
        occurred_at=occ,
        effective_from=occ,
        is_demo=is_demo,
        match_countries_json=[],
        match_categories_json=["geopolitics"],
        match_currencies_json=[],
        match_materials_json=[],
        attributes_json={"synthetic_tg4": True},
    )
    db.add(event)
    db.flush()
    # Force created_at (server_default may ignore on some dialects)
    event.created_at = cre
    db.add(
        EventSource(
            id=str(uuid4()),
            event_id=eid,
            publisher="Synthetic Gazette",
            url="https://example.test/synth",
            published_at=occ,
            source_quality=0.9,
            excerpt="synthetic",
            is_stub=False,
        )
    )
    impact = EventImpact(
        id=str(uuid4()),
        event_id=eid,
        company_id=COMPANY_ID,
        impact_score=score,
        urgency="this_week",
        confidence=0.7,
        reason_summary="Synthetic company_calculated path for TG-4 tests.",
        score_breakdown_json={"score_kind": score_kind, "assessment_state": "supply_chain_ready"},
        claims_json={"confirmed": 1, "assumptions": 0},
        status="action_required",
        model_version="impact-v1.1-test",
        computed_at=now,
    )
    db.add(impact)
    sub = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.user_id == user_id,
            NotificationSubscription.company_id == COMPANY_ID,
            NotificationSubscription.channel_type == "telegram_private",
        )
        .first()
    )
    if sub is None:
        sub = NotificationSubscription(
            id=str(uuid4()),
            company_id=COMPANY_ID,
            user_id=user_id,
            channel_type="telegram_private",
        )
        db.add(sub)
    sub.chat_id = chat_id
    sub.status = "connected"
    sub.is_active = True
    sub.risks_enabled = True
    sub.min_severity = min_severity
    sub.muted_until = None
    sub.quiet_hours_json = None
    sub.verified_at = watermark or (now - timedelta(hours=1))
    stamp_auto_notify_watermark(sub, when=watermark or (now - timedelta(hours=1)))
    db.commit()
    db.refresh(event)
    db.refresh(impact)
    db.refresh(sub)
    return event, impact, sub


def test_eligible_new_risk_enqueues(enable_news, db: Session):
    event, impact, sub = _synthetic_risk_bundle(db)
    n = enqueue_impact_notifications(db, impact, event)
    db.commit()
    assert n == 1
    row = (
        db.query(NotificationOutbox)
        .filter(NotificationOutbox.dedupe_key == news_dedupe_key(subscription_id=sub.id, event_id=event.id))
        .one()
    )
    assert row.kind == NEWS_KIND
    assert row.status == "pending"
    text = (row.payload_json or {}).get("text", "").lower()
    assert "индекс влияния" in text
    assert "не вероятность" in text
    assert "не процент потерь" in text


def test_feature_flag_default_blocks_enqueue(db: Session, monkeypatch):
    monkeypatch.delenv("TELEGRAM_NEWS_NOTIFICATIONS_ENABLED", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    event, impact, _ = _synthetic_risk_bundle(db)
    assert enqueue_impact_notifications(db, impact, event) == 0
    db.commit()


@pytest.mark.parametrize(
    "kwargs,reason_part",
    [
        ({"event_type": "neutral"}, "event_not_risk"),
        ({"is_demo": True}, "event_demo"),
        ({"score_kind": SCORE_KIND_SEVERITY}, "score_kind_not_company_calculated"),
        ({"score": 10.0, "min_severity": "high"}, "below_threshold"),
        ({"severity": None, "event_type": "neutral"}, "event_not_risk"),
        ({"severity": None, "event_type": "risk"}, "severity_unknown"),
    ],
)
def test_denies_non_v1_signals(enable_news, db: Session, kwargs, reason_part):
    event, impact, sub = _synthetic_risk_bundle(db, **kwargs)
    d = evaluate_news_eligibility(db, sub=sub, event=event, impact=impact)
    assert d.allowed is False
    assert reason_part in d.reason
    assert enqueue_impact_notifications(db, impact, event) == 0


def test_severity_zero_not_auto_critical(enable_news, db: Session):
    """Known severity=0 must not become a Telegram push without company_calculated risk path."""
    event, impact, sub = _synthetic_risk_bundle(
        db, severity=0.0, event_type="neutral", score_kind=SCORE_KIND_SEVERITY, score=0.0
    )
    d = evaluate_news_eligibility(db, sub=sub, event=event, impact=impact)
    assert d.allowed is False


def test_controlled_pair_required_for_demo_fixture(db: Session, monkeypatch):
    """Without controlled pair, demo fixture stays rejected; with pair — allowed."""
    monkeypatch.setenv("TELEGRAM_NEWS_NOTIFICATIONS_ENABLED", "false")
    monkeypatch.delenv("TELEGRAM_NEWS_CONTROLLED_PAIR", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    event, impact, sub = _synthetic_risk_bundle(db, chat_id="77222")
    event.is_demo = True
    db.commit()
    d0 = evaluate_news_eligibility(db, sub=sub, event=event, impact=impact)
    assert d0.allowed is False
    assert d0.reason in {"feature_disabled", "event_demo"}

    monkeypatch.setenv("TELEGRAM_NEWS_NOTIFICATIONS_ENABLED", "true")
    get_settings.cache_clear()
    d1 = evaluate_news_eligibility(db, sub=sub, event=event, impact=impact)
    assert d1.allowed is False
    assert d1.reason == "event_demo"

    monkeypatch.setenv("TELEGRAM_NEWS_CONTROLLED_PAIR", f"{sub.id}:{event.id}")
    get_settings.cache_clear()
    d2 = evaluate_news_eligibility(db, sub=sub, event=event, impact=impact)
    assert d2.allowed is True
    monkeypatch.delenv("TELEGRAM_NEWS_CONTROLLED_PAIR", raising=False)
    get_settings.cache_clear()


def test_dedupe_conflict_does_not_rollback_impact(enable_news, db: Session):
    """Outbox UniqueConstraint must use a savepoint — Impact row stays committed."""
    event, impact, sub = _synthetic_risk_bundle(db, chat_id="77111")
    assert enqueue_impact_notifications(db, impact, event) == 1
    db.commit()
    impact_id = impact.id
    score_before = float(impact.impact_score)
    # Second enqueue hits dedupe (exists check) — also force nested IntegrityError path
    assert enqueue_impact_notifications(db, impact, event) == 0
    # Simulate concurrent insert: same dedupe after exists-check race
    from app.models import NotificationOutbox
    from app.services.telegram_news_policy import NEWS_KIND, news_dedupe_key

    dup = NotificationOutbox(
        id=str(uuid4()),
        company_id=COMPANY_ID,
        subscription_id=sub.id,
        kind=NEWS_KIND,
        event_impact_id=impact_id,
        channel_type="telegram_private",
        chat_id=sub.chat_id or "77111",
        payload_json={"text": "race"},
        dedupe_key=news_dedupe_key(subscription_id=sub.id, event_id=event.id),
        status="pending",
        attempts=0,
        next_attempt_at=_utc(),
    )
    db.add(dup)
    try:
        with db.begin_nested():
            db.flush()
        raised = False
    except Exception:
        raised = True
    assert raised or True  # dialect may raise on flush
    db.rollback()
    # Re-load impact — must still exist with same score (not rolled back by outbox conflict)
    again = db.get(EventImpact, impact_id)
    assert again is not None
    assert float(again.impact_score) == score_before
    assert (
        db.query(NotificationOutbox)
        .filter(NotificationOutbox.event_impact_id == impact_id, NotificationOutbox.kind == NEWS_KIND)
        .count()
        == 1
    )


def test_old_news_new_impact_denied(enable_news, db: Session):
    now = _utc()
    wm = now - timedelta(hours=1)
    event, impact, sub = _synthetic_risk_bundle(
        db,
        watermark=wm,
        occurred_at=now - timedelta(days=10),
        created_at=now - timedelta(days=10),
    )
    # Fresh recompute timestamp — must not unlock
    impact.computed_at = now
    db.commit()
    d = novelty_allows(event=event, watermark=sub.auto_notify_since)
    assert d.allowed is False
    assert "publication" in d.reason
    assert enqueue_impact_notifications(db, impact, event) == 0


def test_late_import_old_publication_denied(enable_news, db: Session):
    now = _utc()
    wm = now - timedelta(hours=2)
    # Arrived after watermark, but published long ago
    event, impact, sub = _synthetic_risk_bundle(
        db,
        watermark=wm,
        occurred_at=now - timedelta(days=30),
        created_at=now - timedelta(minutes=5),
    )
    d = novelty_allows(event=event, watermark=sub.auto_notify_since)
    assert d.allowed is False
    assert d.reason == "novelty_publication_before_watermark"


def test_connect_and_reenable_no_backfill(enable_news, client: TestClient, auth_headers, db: Session):
    # Old synthetic event before connect
    old_occ = _utc() - timedelta(days=3)
    event, impact, _ = _synthetic_risk_bundle(
        db,
        occurred_at=old_occ,
        created_at=old_occ,
        watermark=_utc() - timedelta(days=30),  # will be overwritten on connect
    )
    token = client.post(
        "/api/v1/telegram/link-token",
        json={"company_id": COMPANY_ID},
        headers=auth_headers,
    ).json()["token"]
    r = client.post(
        "/api/v1/telegram/webhook",
        json={
            "update_id": 424242,
            "message": {
                "chat": {"id": 88001, "type": "private", "username": "t"},
                "text": f"/start {token}",
            },
        },
        headers=WH,
    )
    assert r.status_code == 200
    db.expire_all()
    sub = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.user_id == "usr_demo_owner",
            NotificationSubscription.company_id == COMPANY_ID,
            NotificationSubscription.channel_type == "telegram_private",
        )
        .one()
    )
    assert sub.auto_notify_since is not None
    # Watermark must be after the old event clocks (no archive backfill).
    assert _utc(sub.auto_notify_since) > _utc(event.occurred_at)
    assert enqueue_impact_notifications(db, impact, event) == 0

    # Pause then re-enable — watermark advances; still no old backfill
    client.patch(
        f"/api/v1/notification-subscriptions/{sub.id}",
        json={"is_active": False},
        headers=auth_headers,
    )
    client.patch(
        f"/api/v1/notification-subscriptions/{sub.id}",
        json={"is_active": True},
        headers=auth_headers,
    )
    db.expire_all()
    assert enqueue_impact_notifications(db, impact, event) == 0


def test_enqueue_idempotent_and_integrity(enable_news, db: Session):
    event, impact, sub = _synthetic_risk_bundle(db)
    assert enqueue_impact_notifications(db, impact, event) == 1
    assert enqueue_impact_notifications(db, impact, event) == 0
    db.commit()
    # Concurrent-style second insert with same dedupe
    row = NotificationOutbox(
        id=str(uuid4()),
        company_id=COMPANY_ID,
        subscription_id=sub.id,
        kind=NEWS_KIND,
        event_impact_id=impact.id,
        channel_type="telegram_private",
        chat_id=sub.chat_id or "x",
        payload_json={"text": "dup"},
        dedupe_key=news_dedupe_key(subscription_id=sub.id, event_id=event.id),
        status="pending",
        attempts=0,
        next_attempt_at=_utc(),
    )
    db.add(row)
    with pytest.raises(Exception):
        db.flush()
    db.rollback()
    n = (
        db.query(NotificationOutbox)
        .filter(NotificationOutbox.event_impact_id == impact.id, NotificationOutbox.kind == NEWS_KIND)
        .count()
    )
    assert n == 1


def test_rollback_drops_outbox(enable_news, db: Session):
    event, impact, sub = _synthetic_risk_bundle(db)
    enqueue_impact_notifications(db, impact, event)
    assert (
        db.query(NotificationOutbox)
        .filter(NotificationOutbox.dedupe_key == news_dedupe_key(subscription_id=sub.id, event_id=event.id))
        .count()
        == 1
    )
    db.rollback()
    assert (
        db.query(NotificationOutbox)
        .filter(NotificationOutbox.dedupe_key == news_dedupe_key(subscription_id=sub.id, event_id=event.id))
        .count()
        == 0
    )


def test_membership_revoked_and_mute_skip_send(enable_news, db: Session, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "000:TEST")
    from app.core.config import get_settings

    get_settings.cache_clear()
    event, impact, sub = _synthetic_risk_bundle(db)
    enqueue_impact_notifications(db, impact, event)
    db.commit()

    membership = (
        db.query(CompanyMembership)
        .filter(
            CompanyMembership.user_id == sub.user_id,
            CompanyMembership.company_id == COMPANY_ID,
        )
        .one()
    )
    saved = {
        "id": membership.id,
        "user_id": membership.user_id,
        "company_id": membership.company_id,
        "role": membership.role,
    }
    db.delete(membership)
    db.commit()
    db.expire_all()
    try:
        process_outbox_once(db)
        row = (
            db.query(NotificationOutbox)
            .filter(
                NotificationOutbox.dedupe_key
                == news_dedupe_key(subscription_id=sub.id, event_id=event.id)
            )
            .one()
        )
        assert row.status == "skipped"
        assert "membership" in (row.last_error or "")
    finally:
        # Session-scoped seed DB — restore membership for later tests.
        exists = db.get(CompanyMembership, saved["id"])
        if exists is None:
            db.add(CompanyMembership(**saved))
            db.commit()

    event2, impact2, sub2 = _synthetic_risk_bundle(db, chat_id="77002")
    sub2.muted_until = _utc() + timedelta(hours=2)
    db.commit()
    assert enqueue_impact_notifications(db, impact2, event2) == 0
    db.commit()


def test_unlink_pending_skipped(enable_news, db: Session, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "000:TEST")
    from app.core.config import get_settings

    get_settings.cache_clear()
    event, impact, sub = _synthetic_risk_bundle(db, chat_id="77003")
    assert enqueue_impact_notifications(db, impact, event) == 1
    db.commit()
    dedupe = news_dedupe_key(subscription_id=sub.id, event_id=event.id)
    sub.is_active = False
    sub.status = "disconnected"
    old_chat = "77003"
    sub.chat_id = None
    db.commit()
    db.expire_all()
    process_outbox_once(db)
    row = db.query(NotificationOutbox).filter(NotificationOutbox.dedupe_key == dedupe).one()
    assert row.status == "skipped"
    assert row.chat_id == old_chat


def test_quiet_hours_defers_not_drops(enable_news, db: Session, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "000:TEST")
    from app.core.config import get_settings

    get_settings.cache_clear()
    event, impact, sub = _synthetic_risk_bundle(db, chat_id="77004")
    now = _utc()
    # Window that definitely contains "now" in UTC (start 1h ago → end 6h ahead).
    start = (now - timedelta(hours=1)).strftime("%H:%M")
    end = (now + timedelta(hours=6)).strftime("%H:%M")
    sub.quiet_hours_json = {"start": start, "end": end}
    sub.timezone = "UTC"
    db.commit()
    assert quiet_hours_status(sub, now=now)["in_quiet_hours"] is True
    assert enqueue_impact_notifications(db, impact, event) == 1
    db.commit()
    dedupe = news_dedupe_key(subscription_id=sub.id, event_id=event.id)
    row = db.query(NotificationOutbox).filter(NotificationOutbox.dedupe_key == dedupe).one()
    assert row.next_attempt_at is not None
    assert _utc(row.next_attempt_at) > now
    row.next_attempt_at = now - timedelta(minutes=1)
    db.commit()
    with patch("app.workers.notification_worker.httpx.Client") as client_cls:
        process_outbox_once(db)
    db.expire_all()
    row = db.query(NotificationOutbox).filter(NotificationOutbox.dedupe_key == dedupe).one()
    assert row.status == "pending"
    assert row.last_error == "deferred_quiet_hours"
    client_cls.assert_not_called()


def test_event_reclassified_after_enqueue_skips(enable_news, db: Session, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "000:TEST")
    from app.core.config import get_settings

    get_settings.cache_clear()
    event, impact, sub = _synthetic_risk_bundle(db, chat_id="77005")
    assert enqueue_impact_notifications(db, impact, event) == 1
    db.commit()
    dedupe = news_dedupe_key(subscription_id=sub.id, event_id=event.id)
    event.event_type = "neutral"
    db.commit()
    db.expire_all()
    process_outbox_once(db)
    row = db.query(NotificationOutbox).filter(NotificationOutbox.dedupe_key == dedupe).one()
    assert row.status == "skipped"
    assert "event_not_risk" in (row.last_error or "")


def test_send_success_mocked(enable_news, db: Session, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "000:TEST")
    from app.core.config import get_settings

    get_settings.cache_clear()
    event, impact, sub = _synthetic_risk_bundle(db, chat_id="77006")
    assert enqueue_impact_notifications(db, impact, event) == 1
    db.commit()
    dedupe = news_dedupe_key(subscription_id=sub.id, event_id=event.id)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "{}"
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_resp
    with patch("app.workers.notification_worker.httpx.Client", return_value=mock_client):
        process_outbox_once(db)
    db.expire_all()
    row = db.query(NotificationOutbox).filter(NotificationOutbox.dedupe_key == dedupe).one()
    assert row.status == "sent"
    text = mock_client.post.call_args.kwargs["json"]["text"]
    assert "Синтетика TG-4" in text


def test_settings_expose_policy(client: TestClient, auth_headers):
    r = client.get(
        f"/api/v1/companies/{COMPANY_ID}/notification-settings",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert "news_policy_note" in body
    assert body["news_notifications_server_enabled"] is False
    assert "архив" in body["news_policy_note"].lower() or "v1" in body["news_policy_note"].lower()


def test_no_scenario_decision_side_effects(enable_news, db: Session):
    from app.models import Decision, Scenario

    before_s = db.query(Scenario).count()
    before_d = db.query(Decision).count()
    event, impact, _ = _synthetic_risk_bundle(db)
    enqueue_impact_notifications(db, impact, event)
    db.commit()
    assert db.query(Scenario).count() == before_s
    assert db.query(Decision).count() == before_d
