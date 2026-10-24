"""Publish cluster → Event + EventSources with verification gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Event, EventSource
from app.models.raw_news import RawNewsItem
from app.services.ingestion.enrich import EventEnrichment, strip_invented_numbers
from app.services.ingestion.official_sources import (
    classify_official_primary,
    is_official_primary_item,
)


@dataclass
class PublishDecision:
    allowed: bool
    reason: str
    has_official: bool
    independent_publishers: int
    official_source_ids: tuple[str, ...] = ()


def _is_official_item(item: RawNewsItem) -> bool:
    """Verified primary only — ignores publisher labels and payload is_official."""
    return is_official_primary_item(item)


def _publisher_key(item: RawNewsItem) -> str:
    host = urlparse(item.canonical_url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host:
        return host
    return (item.publisher or "").strip().lower()


def can_publish(items: list[RawNewsItem]) -> PublishDecision:
    """Official primary alone OR ≥2 independent publishers (by article host)."""
    if not items:
        return PublishDecision(False, "empty_cluster", False, 0)
    official_ids: list[str] = []
    for i in items:
        cls = classify_official_primary(i)
        if cls.is_official_primary and cls.source_id:
            official_ids.append(cls.source_id)
    independents = {_publisher_key(i) for i in items if _publisher_key(i)}
    n = len(independents)
    if official_ids:
        return PublishDecision(
            True,
            "official_source",
            True,
            n,
            official_source_ids=tuple(sorted(set(official_ids))),
        )
    if n >= 2:
        return PublishDecision(True, "two_independent_sources", False, n)
    return PublishDecision(False, "unverified_single_source", False, n)


def publish_event(
    db: Session,
    *,
    items: list[RawNewsItem],
    enrichment: EventEnrichment,
    cluster_key: str,
) -> Event | None:
    decision = can_publish(items)
    if not decision.allowed:
        for item in items:
            item.processing_status = "rejected"
            item.error = decision.reason
        return None

    allowed_ids = {i.id for i in items}
    claims = [c for c in enrichment.claims if c.source_id in allowed_ids]
    source_texts = [f"{i.title}\n{i.excerpt or ''}" for i in items]
    summary = strip_invented_numbers(enrichment.summary_ru, source_texts)

    # Map temporary raw ids → stable event_source ids for citation
    source_id_map: dict[str, str] = {item.id: str(uuid4()) for item in items}
    remapped_claims = []
    for c in claims:
        remapped_claims.append(
            {
                "text": c.text,
                "claim_type": c.claim_type,
                "source_id": source_id_map[c.source_id],
            }
        )

    dated = [i.published_at for i in items if i.published_at is not None]
    if not dated:
        # Never substitute fetched_at / now() as the event publication date.
        for item in items:
            item.processing_status = "rejected"
            item.error = "missing_publication_date"
        return None
    occurred = max(dated)
    event_id = f"evt_live_{cluster_key}"

    existing = db.get(Event, event_id)
    if existing is not None:
        # Attach new sources if missing; do not flip demo events
        if existing.is_demo:
            for item in items:
                item.processing_status = "rejected"
                item.error = "cluster_collides_with_demo"
            return None
        event = existing
        event.title = enrichment.title_ru[:512]
        event.summary = summary
        event.category = enrichment.category
        event.event_type = enrichment.event_type
        event.severity = (
            float(enrichment.severity) if enrichment.severity is not None else None
        )
        event.occurred_at = occurred
        event.effective_from = enrichment.effective_from or occurred
        event.match_countries_json = list(enrichment.countries)
        event.match_currencies_json = list(enrichment.currencies)
        event.match_materials_json = list(enrichment.materials)
        event.match_categories_json = [enrichment.category]
        attrs = dict(event.attributes_json or {})
        attrs["claims"] = remapped_claims
        attrs["publish_reason"] = decision.reason
        attrs["official_source_ids"] = list(decision.official_source_ids)
        if enrichment.classification_meta:
            attrs["classification"] = dict(enrichment.classification_meta)
        event.attributes_json = attrs
    else:
        attrs_new: dict = {
            "claims": remapped_claims,
            "publish_reason": decision.reason,
            "official_source_ids": list(decision.official_source_ids),
            "cluster_key": cluster_key,
        }
        if enrichment.classification_meta:
            attrs_new["classification"] = dict(enrichment.classification_meta)
        event = Event(
            id=event_id,
            title=enrichment.title_ru[:512],
            summary=summary,
            category=enrichment.category,
            event_type=enrichment.event_type,
            severity=(
                float(enrichment.severity) if enrichment.severity is not None else None
            ),
            urgency_default="watch",
            status="active",
            occurred_at=occurred,
            effective_from=enrichment.effective_from or occurred,
            match_countries_json=list(enrichment.countries),
            match_categories_json=[enrichment.category],
            match_currencies_json=list(enrichment.currencies),
            match_materials_json=list(enrichment.materials),
            attributes_json=attrs_new,
            is_demo=False,
        )
        db.add(event)
        db.flush()

    for item in items:
        src_id = source_id_map[item.id]
        existing_src = (
            db.query(EventSource)
            .filter(EventSource.event_id == event.id, EventSource.url == item.canonical_url)
            .one_or_none()
        )
        if existing_src is None:
            db.add(
                EventSource(
                    id=src_id,
                    event_id=event.id,
                    publisher=item.publisher,
                    url=item.canonical_url,
                    published_at=item.published_at,
                    source_quality=0.95 if _is_official_item(item) else 0.7,
                    excerpt=(item.excerpt or item.title)[:2000],
                    is_stub=False,
                )
            )
        item.processing_status = "processed"
        item.event_id = event.id
        item.error = None

    db.flush()
    return event


def claims_cite_event_sources(event: Event, sources: list[EventSource]) -> bool:
    """Validate that every claim.source_id exists among event sources."""
    attrs: dict[str, Any] = event.attributes_json or {}
    claims = attrs.get("claims") or []
    ids = {s.id for s in sources}
    if not claims:
        return True
    for claim in claims:
        if not isinstance(claim, dict):
            return False
        if claim.get("source_id") not in ids:
            return False
    return True
