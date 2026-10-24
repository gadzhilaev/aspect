"""Real ingestion ↔ personalization: relevance gate, dashboard, no duplicate impacts."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Company, CompanyNode, Event, EventImpact, EventSource
from app.models.raw_news import RawNewsItem
from app.services.impact import event_matches_company, recompute_event_for_ready_companies
from app.services.ingestion.enrich import EnrichedClaim, EventEnrichment
from app.services.ingestion.normalize import content_hash
from app.services.ingestion.publish import publish_event

COMPANY_ID = "cmp_severprom"


def _make_raw(
    db: Session,
    *,
    publisher: str,
    url: str,
    title: str,
    provider: str = "gdelt",
    official: bool = False,
) -> RawNewsItem:
    item = RawNewsItem(
        id=str(uuid4()),
        provider="cbr" if official else provider,
        external_id=f"ext-{uuid4().hex[:10]}",
        canonical_url=url,
        publisher=publisher,
        title=title,
        excerpt=f"{title} — excerpt",
        published_at=datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc),
        language="en",
        payload_json={"is_official": official},
        content_hash=content_hash(title=title, excerpt=f"{title} — excerpt", canonical_url=url),
        processing_status="pending",
    )
    db.add(item)
    db.flush()
    return item


def _china_enrichment(raw_ids: list[str]) -> EventEnrichment:
    return EventEnrichment(
        title_ru="Китай ужесточает экспорт электроники",
        summary_ru="Новые лицензии на экспорт электронных компонентов из Китая.",
        category="electronics",
        event_type="risk",
        severity=82,
        countries=["Китай", "China"],
        currencies=["CNY"],
        materials=["electronics"],
        effective_from=datetime(2026, 10, 15, tzinfo=timezone.utc),
        claims=[
            EnrichedClaim(text="Источник подтверждает ограничения", claim_type="confirmed_fact", source_id=rid)
            for rid in raw_ids
        ],
    )


def test_event_matches_china_supplier_for_severprom(db: Session):
    company = db.get(Company, COMPANY_ID)
    assert company is not None
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == COMPANY_ID).all()
    event = Event(
        id="evt_tmp_match",
        title="t",
        summary="s",
        category="electronics",
        event_type="risk",
        severity=70,
        urgency_default="watch",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_countries_json=["China"],
        match_categories_json=[],
        match_currencies_json=[],
        match_materials_json=[],
        attributes_json={},
        is_demo=False,
    )
    assert event_matches_company(event, company, nodes, purchase_currencies=["CNY"]) is True

    unrelated = Event(
        id="evt_tmp_br",
        title="t",
        summary="s",
        category="market",
        event_type="risk",
        severity=40,
        urgency_default="info",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_countries_json=["Бразилия", "Brazil"],
        match_categories_json=[],
        match_currencies_json=["BRL"],
        match_materials_json=["soy"],
        attributes_json={},
        is_demo=False,
    )
    assert event_matches_company(unrelated, company, nodes, purchase_currencies=["CNY"]) is False


def test_real_china_event_appears_in_dashboard_and_impact(
    client: TestClient, auth_headers: dict, db: Session
):
    a = _make_raw(
        db,
        publisher="Alpha Wire",
        url="https://alpha.example.com/china-export-live",
        title="China tightens electronics export licenses",
    )
    b = _make_raw(
        db,
        publisher="Beta Desk",
        url="https://beta.example.com/china-export-live",
        title="Electronics export controls expand in China",
    )
    db.commit()

    enrich = _china_enrichment([a.id, b.id])
    event = publish_event(db, items=[a, b], enrichment=enrich, cluster_key="pers_china_1")
    assert event is not None
    assert event.is_demo is False
    impacts = recompute_event_for_ready_companies(db, event)
    db.commit()
    assert impacts, "SeverProm twin must match China export signal"
    # Other tests may leave additional ready companies; require SeverProm, not exclusivity.
    matched_ids = {i.company_id for i in impacts}
    assert COMPANY_ID in matched_ids

    dash = client.get(f"/api/v1/companies/{COMPANY_ID}/dashboard", headers=auth_headers)
    assert dash.status_code == 200
    ids = [c["id"] for c in dash.json()["priority_events"]]
    assert event.id in ids

    card = next(c for c in dash.json()["priority_events"] if c["id"] == event.id)
    assert card["is_demo"] is False

    impact = client.get(
        f"/api/v1/events/{event.id}/impact",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert impact.status_code == 200

    detail = client.get(
        f"/api/v1/events/{event.id}",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["is_demo"] is False
    assert len(body["sources"]) == 2
    assert all(s.get("url") for s in body["sources"])
    assert all(s.get("publisher") for s in body["sources"])


def test_unrelated_real_event_skips_impact_and_dashboard(
    client: TestClient, auth_headers: dict, db: Session
):
    a = _make_raw(
        db,
        publisher="LatAm One",
        url="https://latam.example.com/brazil-soy",
        title="Brazil soy export window",
    )
    b = _make_raw(
        db,
        publisher="LatAm Two",
        url="https://latam2.example.com/brazil-soy",
        title="Soy shipments from Brazil rise",
    )
    db.commit()
    enrich = EventEnrichment(
        title_ru="Рост экспорта сои из Бразилии",
        summary_ru="Окно поставок сои расширяется.",
        category="market",
        event_type="opportunity",
        severity=45,
        countries=["Бразилия", "Brazil"],
        currencies=["BRL"],
        materials=["soy"],
        claims=[
            EnrichedClaim(text="a", claim_type="confirmed_fact", source_id=a.id),
            EnrichedClaim(text="b", claim_type="confirmed_fact", source_id=b.id),
        ],
    )
    event = publish_event(db, items=[a, b], enrichment=enrich, cluster_key="pers_br_1")
    assert event is not None
    impacts = recompute_event_for_ready_companies(db, event)
    db.commit()
    assert impacts == []

    count = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event.id, EventImpact.company_id == COMPANY_ID)
        .count()
    )
    assert count == 0

    dash = client.get(f"/api/v1/companies/{COMPANY_ID}/dashboard", headers=auth_headers)
    assert dash.status_code == 200
    ids = [c["id"] for c in dash.json()["priority_events"]]
    assert event.id not in ids


def test_repeated_personalization_does_not_duplicate_impact(db: Session):
    a = _make_raw(
        db,
        publisher="Wire A",
        url="https://wa.example.com/chip-cn",
        title="Chip export rules China",
    )
    b = _make_raw(
        db,
        publisher="Wire B",
        url="https://wb.example.com/chip-cn",
        title="China chip licensing update",
    )
    db.commit()
    enrich = _china_enrichment([a.id, b.id])
    event = publish_event(db, items=[a, b], enrichment=enrich, cluster_key="pers_dedupe_1")
    assert event is not None

    first = recompute_event_for_ready_companies(db, event)
    db.commit()
    second = recompute_event_for_ready_companies(db, event)
    db.commit()

    assert first and second
    assert first[0].id == second[0].id
    total = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == event.id, EventImpact.company_id == COMPANY_ID)
        .count()
    )
    assert total == 1


def test_assistant_context_exposes_real_source_metadata(
    client: TestClient, auth_headers: dict, db: Session
):
    a = _make_raw(
        db,
        publisher="Reuters Asia",
        url="https://reuters.example.com/cn-elec",
        title="China electronics controls",
    )
    b = _make_raw(
        db,
        publisher="Nikkei",
        url="https://nikkei.example.com/cn-elec",
        title="Export licenses for chips expand",
    )
    db.commit()
    event = publish_event(
        db,
        items=[a, b],
        enrichment=_china_enrichment([a.id, b.id]),
        cluster_key="pers_asst_1",
    )
    assert event is not None
    recompute_event_for_ready_companies(db, event)
    db.commit()

    conv = client.post(
        f"/api/v1/events/{event.id}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    )
    assert conv.status_code == 200, conv.text
    msgs = client.get(
        f"/api/v1/assistant/conversations/{conv.json()['id']}/messages",
        headers=auth_headers,
    )
    assert msgs.status_code == 200

    # Tool/context path: get_event_context via a generic message
    posted = client.post(
        f"/api/v1/assistant/conversations/{conv.json()['id']}/messages",
        headers=auth_headers,
        json={"content": "Какие источники у события?", "client_message_id": "src-meta-1"},
    )
    assert posted.status_code == 200, posted.text
    assistant = posted.json()["assistant_message"]
    # source_list block or content should surface publishers / URLs from backend context
    blob = assistant["content"] + str(assistant.get("blocks") or [])
    assert "Reuters Asia" in blob or "Nikkei" in blob or any(
        b.get("type") == "source_list" for b in (assistant.get("blocks") or [])
    )

    sources = db.query(EventSource).filter(EventSource.event_id == event.id).all()
    assert all(s.url and s.publisher and s.published_at for s in sources)
    assert all(s.is_stub is False for s in sources)
