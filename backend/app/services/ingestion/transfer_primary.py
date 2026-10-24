"""Controlled transfer of verified primary raw articles between stand DBs.

Uses store_article (dedupe by URL/hash/external_id) + process_pending.
Does not copy users/companies/decisions. Does not invent random raw IDs by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.models.raw_news import RawNewsItem
from app.services.ingestion.base import FetchedArticle
from app.services.ingestion.official_sources import classify_official_primary
from app.services.ingestion.pipeline import IngestResult, process_pending, store_article


PRIMARY_HOSTS = frozenset({"wto.org", "customs.gov.ru", "ec.europa.eu"})


@dataclass
class TransferPlanItem:
    source_raw_id: str
    title: str
    canonical_url: str
    publisher: str
    feed_url: str | None
    published_at: datetime | None
    official_source_id: str | None
    action: str  # insert | duplicate | skip_not_primary


@dataclass
class TransferPlan:
    dry_run: bool
    items: list[TransferPlanItem] = field(default_factory=list)
    would_insert: int = 0
    would_duplicate: int = 0
    skipped: int = 0


def _host(url: str) -> str:
    from urllib.parse import urlparse

    h = urlparse(url or "").netloc.lower()
    return h[4:] if h.startswith("www.") else h


def iter_verified_primary_raws(source_db: Session) -> list[RawNewsItem]:
    """Published (or classifiable) primary raws from the coverage copy."""
    rows = (
        source_db.query(RawNewsItem)
        .filter(RawNewsItem.processing_status.in_(["processed", "rejected", "pending"]))
        .order_by(RawNewsItem.published_at.asc())
        .all()
    )
    out: list[RawNewsItem] = []
    for item in rows:
        host = _host(item.canonical_url or "")
        if host not in PRIMARY_HOSTS:
            continue
        cls = classify_official_primary(item)
        if not cls.is_official_primary:
            continue
        out.append(item)
    return out


def raw_to_fetched(item: RawNewsItem) -> FetchedArticle:
    payload = dict(item.payload_json) if isinstance(item.payload_json, dict) else {}
    payload.pop("is_official", None)
    # Preserve provenance; mark transfer origin without trusting official flag.
    payload["transferred_from_raw_id"] = item.id
    payload["transfer_source"] = "business_news_coverage"
    if item.event_id:
        payload["source_stand_event_id"] = item.event_id
    return FetchedArticle(
        provider=item.provider or "rss",
        external_id=item.external_id,
        canonical_url=item.canonical_url,
        publisher=item.publisher,
        title=item.title,
        excerpt=item.excerpt,
        published_at=item.published_at,
        language=item.language,
        is_official=False,
        payload=payload,
    )


def plan_transfer(
    source_db: Session,
    target_db: Session,
    *,
    dry_run: bool = True,
    limit: int = 50,
) -> TransferPlan:
    plan = TransferPlan(dry_run=dry_run)
    sources = iter_verified_primary_raws(source_db)[:limit]
    for item in sources:
        cls = classify_official_primary(item)
        payload = item.payload_json if isinstance(item.payload_json, dict) else {}
        feed = payload.get("feed_url") if isinstance(payload.get("feed_url"), str) else None
        # Probe dedupe without writing when dry_run: check existing URL/hash
        from app.services.ingestion.normalize import canonicalize_url, content_hash

        url = canonicalize_url(item.canonical_url)
        digest = content_hash(
            title=item.title, excerpt=item.excerpt, canonical_url=url
        )
        existing = (
            target_db.query(RawNewsItem)
            .filter(
                (RawNewsItem.canonical_url == url)
                | (
                    (RawNewsItem.provider == (item.provider or "rss"))
                    & (RawNewsItem.external_id == item.external_id)
                )
                | (RawNewsItem.content_hash == digest)
            )
            .first()
        )
        action = "duplicate" if existing is not None else "insert"
        if action == "insert":
            plan.would_insert += 1
        else:
            plan.would_duplicate += 1
        plan.items.append(
            TransferPlanItem(
                source_raw_id=item.id,
                title=item.title,
                canonical_url=item.canonical_url,
                publisher=item.publisher,
                feed_url=feed,
                published_at=item.published_at,
                official_source_id=cls.source_id,
                action=action,
            )
        )
    return plan


def apply_transfer(
    source_db: Session,
    target_db: Session,
    *,
    prefer_live_enrich: bool = False,
    personalize: bool = False,
    limit: int = 50,
) -> tuple[TransferPlan, IngestResult, IngestResult]:
    """Insert missing primaries via store_article, then process_pending (no company recompute)."""
    plan = plan_transfer(source_db, target_db, dry_run=False, limit=limit)
    store_result = IngestResult()
    for item in iter_verified_primary_raws(source_db)[:limit]:
        article = raw_to_fetched(item)
        _, status = store_article(target_db, article)
        store_result.fetched += 1
        if status == "inserted":
            store_result.inserted += 1
        elif status == "duplicate":
            store_result.duplicates += 1
    target_db.commit()

    # Re-queue any previously rejected duplicates that are now official under policy
    from app.services.ingestion.reprocess import reprocess_rejected

    # First: process newly pending inserts without personalize
    proc1 = process_pending(
        target_db,
        prefer_live_enrich=prefer_live_enrich,
        personalize=personalize,
    )
    # Second: reprocess rejected primaries that already existed as unverified
    _plan_r, proc2 = reprocess_rejected(
        target_db,
        dry_run=False,
        prefer_live_enrich=prefer_live_enrich,
        personalize=personalize,
        article_hosts=list(PRIMARY_HOSTS),
        feed_hosts=list(PRIMARY_HOSTS),
        errors=["unverified_single_source"],
        only_would_be_official=True,
        limit=100,
    )
    combined = IngestResult(
        fetched=store_result.fetched,
        inserted=store_result.inserted,
        duplicates=store_result.duplicates,
        clusters=proc1.clusters + (proc2.clusters if proc2 else 0),
        published=proc1.published + (proc2.published if proc2 else 0),
        rejected=proc1.rejected + (proc2.rejected if proc2 else 0),
        errors=list(proc1.errors) + list(proc2.errors if proc2 else []),
        event_ids=list(proc1.event_ids) + list(proc2.event_ids if proc2 else []),
    )
    return plan, store_result, combined
