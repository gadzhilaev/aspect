"""Official primary source policy — host/path rules, no payload trust."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Decision, Event, EventSource, Scenario
from app.models.notification import NotificationOutbox
from app.models.raw_news import RawNewsItem
from app.services.ingestion.enrich import EnrichedClaim, EventEnrichment, enrich_cluster
from app.services.ingestion.normalize import content_hash
from app.services.ingestion.official_sources import classify_official_primary
from app.services.ingestion.publish import can_publish, publish_event
from app.services.ingestion.reprocess import plan_reprocess, reprocess_rejected


def _raw(
    *,
    url: str,
    feed_url: str | None,
    publisher: str = "Someone",
    provider: str = "rss",
    title: str = "Primary notice",
    payload_extra: dict | None = None,
    status: str = "pending",
    error: str | None = None,
) -> RawNewsItem:
    payload = dict(payload_extra or {})
    if feed_url:
        payload["feed_url"] = feed_url
    return RawNewsItem(
        id=str(uuid4()),
        provider=provider,
        external_id=f"ext-{uuid4().hex[:8]}",
        canonical_url=url,
        publisher=publisher,
        title=title,
        excerpt=title,
        published_at=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        language="en",
        payload_json=payload,
        content_hash=content_hash(title=title, excerpt=title, canonical_url=url),
        processing_status=status,
        error=error,
    )


def test_wto_primary_allowed():
    item = _raw(
        url="https://wto.org/english/news_e/news26_e/fac_21oct26_522_e.htm",
        feed_url="https://www.wto.org/library/rss/latest_news_e.xml",
        publisher="World Trade Organization — Latest news",
    )
    cls = classify_official_primary(item)
    assert cls.is_official_primary is True
    assert cls.source_id == "wto"
    assert can_publish([item]).allowed is True
    assert can_publish([item]).reason == "official_source"


def test_fts_primary_allowed():
    item = _raw(
        url="https://customs.gov.ru/press/federal/document/714058",
        feed_url="https://customs.gov.ru/press/federal/rss",
        publisher="Федеральная таможенная служба",
        title="Пресс-релиз ФТС",
    )
    assert classify_official_primary(item).source_id == "fts_ru"
    assert can_publish([item]).allowed is True


def test_ec_presscorner_allowed_but_not_trade_filtered():
    item = _raw(
        url="https://ec.europa.eu/commission/presscorner/detail/en/ip_26_2248",
        feed_url=(
            "https://ec.europa.eu/commission/presscorner/api/rss"
            "?dossier=trade&language=en"
        ),
        publisher="Press releases - RSS",
        title="EU Civil Protection Mechanism turns 25",
    )
    cls = classify_official_primary(item)
    assert cls.is_official_primary is True
    assert cls.source_id == "ec_presscorner"
    assert "dossier=trade" in cls.limitations or "торгов" in cls.limitations.lower()


def test_payload_is_official_ignored_on_wrong_host():
    item = _raw(
        url="https://evil.example.com/fake-cbr",
        feed_url="https://evil.example.com/rss",
        publisher="Банк России",
        payload_extra={"is_official": True},
    )
    assert classify_official_primary(item).is_official_primary is False
    assert can_publish([item]).allowed is False
    assert can_publish([item]).reason == "unverified_single_source"


def test_lookalike_domain_not_official():
    item = _raw(
        url="https://wto.org.evil.example/english/news_e/x.htm",
        feed_url="https://wto.org.evil.example/library/rss/x.xml",
        publisher="World Trade Organization — Latest news",
    )
    assert classify_official_primary(item).is_official_primary is False


def test_wrong_path_on_wto_host_not_official():
    item = _raw(
        url="https://wto.org/english/res_e/statis_e/something.htm",
        feed_url="https://www.wto.org/library/rss/latest_news_e.xml",
    )
    assert classify_official_primary(item).is_official_primary is False


def test_interfax_still_unverified_alone():
    item = _raw(
        url="https://www.interfax.ru/business/999",
        feed_url="https://www.interfax.ru/rss.asp",
        publisher="Интерфакс",
    )
    assert can_publish([item]).reason == "unverified_single_source"


def test_cbr_provider_without_feed_url_still_official():
    item = _raw(
        url="https://cbr.ru/press/event/?id=1",
        feed_url=None,
        provider="cbr",
        publisher="Банк России",
        title="Ключевая ставка",
    )
    assert classify_official_primary(item).is_official_primary is True


def test_publish_preserves_dates_and_urls(db: Session):
    item = _raw(
        url="https://customs.gov.ru/press/federal/document/714999",
        feed_url="https://customs.gov.ru/press/federal/rss",
        publisher="Федеральная таможенная служба",
        title="Официальное сообщение ФТС",
    )
    db.add(item)
    db.commit()
    enrich = EventEnrichment(
        title_ru=item.title,
        summary_ru=item.excerpt or item.title,
        category="logistics",
        event_type="risk",
        severity=40,
        claims=[
            EnrichedClaim(
                text=item.title, claim_type="confirmed_fact", source_id=item.id
            )
        ],
    )
    event = publish_event(db, items=[item], enrichment=enrich, cluster_key="fts_t1")
    db.commit()
    assert event is not None
    assert event.occurred_at == item.published_at
    src = db.query(EventSource).filter(EventSource.event_id == event.id).one()
    assert src.url == item.canonical_url
    assert src.published_at == item.published_at


def test_reprocess_rejected_dry_run_and_apply(db: Session):
    item = _raw(
        url="https://wto.org/english/news_e/news26_e/safe_phl_21oct26_520_e.htm",
        feed_url="https://www.wto.org/library/rss/latest_news_e.xml",
        publisher="World Trade Organization — Latest news",
        title="The Philippines launches safeguard investigation on pork",
        status="rejected",
        error="unverified_single_source",
    )
    rid = item.id
    db.add(item)
    db.commit()

    plan = plan_reprocess(
        db,
        dry_run=True,
        article_hosts=["wto.org"],
        only_would_be_official=True,
    )
    assert rid in plan.candidate_ids
    assert plan.dry_run is True
    db.refresh(item)
    assert item.processing_status == "rejected"

    before_events = db.query(Event).filter(Event.is_demo.is_(False)).count()
    before_scen = db.query(Scenario).count()
    before_dec = db.query(Decision).count()
    before_out = db.query(NotificationOutbox).count()

    plan2, result = reprocess_rejected(
        db,
        dry_run=False,
        prefer_live_enrich=False,
        article_hosts=["wto.org"],
        only_would_be_official=True,
    )
    assert rid in plan2.candidate_ids
    assert result is not None
    assert result.published >= 1
    db.refresh(item)
    assert item.processing_status == "processed"
    assert item.event_id is not None
    assert item.id == rid  # ID unchanged

    # Second apply: already processed — not selected as rejected
    plan3, result3 = reprocess_rejected(
        db,
        dry_run=False,
        prefer_live_enrich=False,
        article_hosts=["wto.org"],
        only_would_be_official=True,
    )
    assert rid not in plan3.candidate_ids
    assert result3 is not None
    assert result3.published == 0

    assert db.query(Event).filter(Event.is_demo.is_(False)).count() == before_events + 1
    assert db.query(Scenario).count() == before_scen
    assert db.query(Decision).count() == before_dec
    assert db.query(NotificationOutbox).count() == before_out

    # Investigation wording stays in title; we do not rewrite as entered measure
    ev = db.get(Event, item.event_id)
    assert ev is not None
    assert "investigation" in (ev.title or "").lower()


def test_heuristic_enrich_with_competition_mode(monkeypatch):
    """prefer_live=False must use heuristic even when COMPETITION_MODE requires hackathon."""
    monkeypatch.setenv("COMPETITION_MODE", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_API_KEY", "test-key-not-used")
    get_settings.cache_clear()
    try:
        item = _raw(
            url="https://wto.org/english/news_e/news26_e/x.htm",
            feed_url="https://www.wto.org/library/rss/latest_news_e.xml",
            title="Trade Facilitation Committee advances TFA review",
        )
        enrich = enrich_cluster([item], prefer_live=False)
        assert enrich.title_ru
        assert enrich.claims
    finally:
        monkeypatch.delenv("COMPETITION_MODE", raising=False)
        monkeypatch.delenv("ASSISTANT_PROVIDER", raising=False)
        monkeypatch.delenv("HACKATHON_API_KEY", raising=False)
        get_settings.cache_clear()
