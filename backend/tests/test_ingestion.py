"""Real signal layer — dedupe, publish gate, citations, mocked OpenAI transport."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Event, EventSource
from app.models.raw_news import RawNewsItem
from app.services.ingestion.base import FetchedArticle
from app.services.ingestion.enrich import EventEnrichment, EnrichedClaim, live_enrich
from app.services.ingestion.normalize import canonicalize_url, content_hash
from app.services.ingestion.pipeline import process_pending, run_ingestion, store_article
from app.services.ingestion.publish import can_publish, claims_cite_event_sources, publish_event


def _article(**overrides) -> FetchedArticle:
    base = dict(
        provider="gdelt",
        external_id=f"ext-{uuid4().hex[:8]}",
        canonical_url=f"https://news.example.com/a/{uuid4().hex[:8]}",
        publisher="Example News",
        title="Export controls tighten for electronics",
        excerpt="Authorities announced new export controls affecting electronics supply chains.",
        published_at=datetime.now(timezone.utc),
        language="en",
        is_official=False,
        payload={},
    )
    base.update(overrides)
    return FetchedArticle(**base)


def test_canonicalize_strips_tracking():
    a = canonicalize_url("https://WWW.Example.com/path/?utm_source=x&id=1")
    b = canonicalize_url("https://example.com/path?id=1")
    assert a == b


def test_dedupe_by_canonical_url_and_external_id(db: Session):
    a1 = _article(
        provider="gdelt",
        external_id="same-ext",
        canonical_url="https://wire.example.com/story/1?utm_campaign=x",
        title="Rate hike expected",
    )
    a2 = _article(
        provider="gdelt",
        external_id="same-ext",
        canonical_url="https://wire.example.com/story/1",
        title="Rate hike expected",
    )
    a3 = _article(
        provider="rss",
        external_id="other",
        canonical_url="https://wire.example.com/story/1",
        title="Rate hike expected — mirror",
    )

    before = db.query(RawNewsItem).count()
    i1, s1 = store_article(db, a1)
    i2, s2 = store_article(db, a2)
    i3, s3 = store_article(db, a3)
    db.commit()

    assert s1 == "inserted" and i1 is not None
    assert s2 == "duplicate" and i2 is None
    assert s3 == "duplicate" and i3 is None
    assert db.query(RawNewsItem).count() == before + 1
    assert (
        db.query(RawNewsItem)
        .filter(RawNewsItem.canonical_url == canonicalize_url(a1.canonical_url))
        .count()
        == 1
    )


def test_dedupe_by_content_hash(db: Session):
    title = "Semiconductor shortage widens"
    excerpt = "Fab delays continue across Asia."
    url_a = "https://a.example.com/1"
    url_b = "https://b.example.com/2"
    # Force identical hash by using same title/excerpt/url in hash inputs for second
    # via storing first, then second with same hash fields but different provider ids
    # content_hash includes url — so same url different ids already covered.
    # Here: identical title+excerpt+canonical after canonicalize.
    a = _article(
        provider="gdelt",
        external_id="h1",
        canonical_url=url_a,
        title=title,
        excerpt=excerpt,
    )
    b = _article(
        provider="rss",
        external_id="h2",
        canonical_url=url_a + "?utm_medium=email",
        title=title,
        excerpt=excerpt,
    )
    assert content_hash(title=title, excerpt=excerpt, canonical_url=canonicalize_url(url_a)) == content_hash(
        title=title, excerpt=excerpt, canonical_url=canonicalize_url(url_a + "?utm_medium=email")
    )
    _, s1 = store_article(db, a)
    _, s2 = store_article(db, b)
    db.commit()
    assert s1 == "inserted"
    assert s2 == "duplicate"


def test_reject_unverified_single_source(db: Session):
    item = RawNewsItem(
        id=str(uuid4()),
        provider="gdelt",
        external_id="solo-1",
        canonical_url="https://solo.example.com/x",
        publisher="Solo Wire",
        title="Unconfirmed market rumor",
        excerpt="Single outlet rumor",
        published_at=datetime.now(timezone.utc),
        language="en",
        payload_json={"is_official": False},
        content_hash=content_hash(
            title="Unconfirmed market rumor",
            excerpt="Single outlet rumor",
            canonical_url="https://solo.example.com/x",
        ),
        processing_status="pending",
    )
    db.add(item)
    db.commit()

    decision = can_publish([item])
    assert decision.allowed is False
    assert decision.reason == "unverified_single_source"

    real_before = db.query(Event).filter(Event.is_demo.is_(False)).count()
    result = process_pending(db, prefer_live_enrich=False)
    db.refresh(item)
    assert item.processing_status == "rejected"
    assert item.error == "unverified_single_source"
    assert result.published == 0
    assert db.query(Event).filter(Event.is_demo.is_(False)).count() == real_before
    assert item.event_id is None


def test_official_single_source_can_publish(db: Session):
    item = RawNewsItem(
        id=str(uuid4()),
        provider="cbr",
        external_id="cbr-1",
        canonical_url="https://cbr.ru/press/1",
        publisher="Банк России",
        title="Ключевая ставка сохранена",
        excerpt="Совет директоров принял решение.",
        published_at=datetime.now(timezone.utc),
        language="ru",
        payload_json={"is_official": True},
        content_hash="abc123",
        processing_status="pending",
    )
    db.add(item)
    db.commit()

    enrich = EventEnrichment(
        title_ru="Ключевая ставка сохранена",
        summary_ru="Совет директоров принял решение.",
        category="macro",
        event_type="risk",
        severity=55,
        claims=[
            EnrichedClaim(text="Решение ЦБ", claim_type="confirmed_fact", source_id=item.id)
        ],
    )
    event = publish_event(db, items=[item], enrichment=enrich, cluster_key="official1")
    db.commit()
    assert event is not None
    assert event.is_demo is False
    sources = db.query(EventSource).filter(EventSource.event_id == event.id).all()
    assert len(sources) == 1
    assert sources[0].is_stub is False
    assert sources[0].url == "https://cbr.ru/press/1"
    assert claims_cite_event_sources(event, sources)


def test_missing_publication_date_does_not_use_fetch_time(db: Session):
    """Fetched_at / now() must not become Event.occurred_at."""
    item = RawNewsItem(
        id=str(uuid4()),
        provider="cbr",
        external_id="cbr-no-date",
        canonical_url="https://cbr.ru/press/no-date",
        publisher="Банк России",
        title="Сообщение без даты публикации",
        excerpt="Текст.",
        published_at=None,
        fetched_at=datetime.now(timezone.utc),
        language="ru",
        payload_json={"is_official": True},
        content_hash="nodate123",
        processing_status="pending",
    )
    db.add(item)
    db.commit()
    enrich = EventEnrichment(
        title_ru=item.title,
        summary_ru=item.excerpt or item.title,
        category="macro",
        event_type="risk",
        severity=50,
        claims=[
            EnrichedClaim(text=item.title, claim_type="confirmed_fact", source_id=item.id)
        ],
    )
    before = db.query(Event).count()
    event = publish_event(db, items=[item], enrichment=enrich, cluster_key="nodate1")
    db.commit()
    assert event is None
    assert item.processing_status == "rejected"
    assert item.error == "missing_publication_date"
    assert db.query(Event).count() == before


def test_two_independent_sources_publish_with_citations(db: Session):
    a = RawNewsItem(
        id=str(uuid4()),
        provider="gdelt",
        external_id="t1",
        canonical_url="https://alpha.example.com/1",
        publisher="Alpha",
        title="New export license rules for chips",
        excerpt="Licensing expanded.",
        published_at=datetime.now(timezone.utc),
        language="en",
        payload_json={},
        content_hash="h-a",
        processing_status="pending",
    )
    b = RawNewsItem(
        id=str(uuid4()),
        provider="rss",
        external_id="t2",
        canonical_url="https://beta.example.com/2",
        publisher="Beta",
        title="Chip export licenses tightened",
        excerpt="Rules affect suppliers.",
        published_at=datetime.now(timezone.utc),
        language="en",
        payload_json={},
        content_hash="h-b",
        processing_status="pending",
    )
    db.add_all([a, b])
    db.commit()

    enrich = EventEnrichment(
        title_ru="Ужесточение лицензий на экспорт чипов",
        summary_ru="Лицензирование расширено.",
        category="electronics",
        event_type="risk",
        severity=70,
        claims=[
            EnrichedClaim(text="Alpha: licensing", claim_type="confirmed_fact", source_id=a.id),
            EnrichedClaim(text="Beta: suppliers", claim_type="confirmed_fact", source_id=b.id),
            EnrichedClaim(text="Invented", claim_type="inference", source_id="not-a-real-id"),
        ],
    )
    event = publish_event(db, items=[a, b], enrichment=enrich, cluster_key="pair1")
    db.commit()
    assert event is not None
    sources = db.query(EventSource).filter(EventSource.event_id == event.id).all()
    assert len(sources) == 2
    assert claims_cite_event_sources(event, sources)
    claim_ids = {c["source_id"] for c in (event.attributes_json or {}).get("claims", [])}
    assert "not-a-real-id" not in claim_ids
    assert claim_ids <= {s.id for s in sources}


def test_live_enrich_uses_responses_api_mock():
    item = RawNewsItem(
        id="raw-1",
        provider="cbr",
        external_id="x",
        canonical_url="https://cbr.ru/n/1",
        publisher="Банк России",
        title="Курс USD",
        excerpt="Официальный курс",
        published_at=datetime.now(timezone.utc),
        language="ru",
        payload_json={"is_official": True},
        content_hash="z",
        processing_status="pending",
    )
    fake = {
        "output_text": (
            '{"title_ru":"Курс доллара","summary_ru":"Официальный курс",'
            '"category":"macro","event_type":"market","severity":40,'
            '"countries":["Россия"],"currencies":["USD"],"materials":[],'
            '"effective_from":null,'
            '"claims":[{"text":"Курс","claim_type":"confirmed_fact","source_id":"raw-1"}]}'
        )
    }
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = fake
    client = MagicMock()
    client.post.return_value = response

    with patch("app.services.ingestion.enrich.get_settings") as gs:
        settings = MagicMock()
        settings.resolved_openai_api_key.return_value = "sk-test"
        settings.resolved_openai_model.return_value = "gpt-test"
        settings.assistant_base_url = "https://api.openai.com/v1"
        gs.return_value = settings
        result = live_enrich([item], http_client=client)

    assert result.title_ru == "Курс доллара"
    assert result.claims[0].source_id == "raw-1"
    assert client.post.call_args.args[0].endswith("/responses")
    assert client.post.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-test"


def test_internal_ingestion_requires_token(client: TestClient, monkeypatch):
    monkeypatch.setenv("INGESTION_RUN_TOKEN", "secret-demo")
    from app.core.config import get_settings

    get_settings.cache_clear()
    denied = client.post("/api/v1/internal/ingestion/run")
    assert denied.status_code == 403

    with patch("app.api.v1.internal.run_ingestion") as mocked:
        mocked.return_value = MagicMock(
            fetched=0,
            inserted=0,
            duplicates=0,
            clusters=0,
            published=0,
            rejected=0,
            event_ids=[],
            errors=[],
        )
        ok = client.post(
            "/api/v1/internal/ingestion/run",
            headers={"X-Ingestion-Token": "secret-demo"},
        )
    assert ok.status_code == 200
    get_settings.cache_clear()


def test_run_ingestion_with_fake_provider_does_not_break_demo(db: Session):
    before_demo = db.query(Event).filter(Event.is_demo.is_(True)).count()

    class FakeProvider:
        name = "fake"
        is_official = False

        def fetch(self):
            return [
                _article(
                    provider="gdelt",
                    publisher="OneDesk",
                    canonical_url="https://onedesk.example/only",
                    title="Lonely rumor",
                )
            ]

    result = run_ingestion(
        db,
        providers=[FakeProvider()],  # type: ignore[arg-type]
        prefer_live_enrich=False,
    )
    assert result.inserted >= 1
    assert result.published == 0
    assert db.query(Event).filter(Event.is_demo.is_(True)).count() == before_demo
