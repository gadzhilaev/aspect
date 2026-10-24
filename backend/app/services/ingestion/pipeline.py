"""Fetch → store (dedupe) → cluster → enrich → publish."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.raw_news import RawNewsItem
from app.services.ingestion.base import FetchedArticle, SourceProvider
from app.services.ingestion.cbr import CbrProvider
from app.services.ingestion.cluster import assign_clusters
from app.services.ingestion.enrich import enrich_cluster
from app.services.ingestion.gdelt import GdeltProvider
from app.services.ingestion.normalize import canonicalize_url, content_hash
from app.services.impact import recompute_event_for_ready_companies
from app.services.ingestion.publish import can_publish, publish_event
from app.services.ingestion.rss import RssProvider


@dataclass
class IngestResult:
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    clusters: int = 0
    published: int = 0
    rejected: int = 0
    errors: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)


def _rss_feeds_without_cbr_news_overlap() -> list[str]:
    """Drop CBR news RSS from whitelist — CbrProvider already polls CBR_NEWS_RSS."""
    from app.core.config import get_settings
    from app.services.ingestion.cbr import CBR_NEWS_RSS

    feeds = get_settings().rss_feed_list()
    skip = {
        CBR_NEWS_RSS.rstrip("/").lower(),
        "https://www.cbr.ru/rss/rssnews",
        "https://cbr.ru/rss/rssnews",
    }
    out: list[str] = []
    for url in feeds:
        key = url.rstrip("/").lower()
        if key in skip or "cbr.ru/rss/" in key:
            continue
        out.append(url)
    return out


def default_providers() -> list[SourceProvider]:
    # CBR connector owns FX + key rate + CBR news RSS — do not also hit that feed via RssProvider.
    return [
        CbrProvider(),
        GdeltProvider(),
        RssProvider(feed_urls=_rss_feeds_without_cbr_news_overlap()),
    ]


def store_article(db: Session, article: FetchedArticle) -> tuple[RawNewsItem | None, str]:
    """Insert raw item or skip duplicate. Returns (item|None, status)."""
    url = canonicalize_url(article.canonical_url)
    if not url:
        return None, "invalid_url"
    digest = content_hash(title=article.title, excerpt=article.excerpt, canonical_url=url)

    existing = (
        db.query(RawNewsItem)
        .filter(
            (RawNewsItem.canonical_url == url)
            | (
                (RawNewsItem.provider == article.provider)
                & (RawNewsItem.external_id == article.external_id)
            )
            | (RawNewsItem.content_hash == digest)
        )
        .first()
    )
    if existing is not None:
        return None, "duplicate"

    payload = dict(article.payload or {})
    # Never treat connector/RSS/user is_official as publish trust — classification
    # uses verified host/path rules at can_publish time. Keep a non-authoritative hint.
    payload.pop("is_official", None)
    if article.is_official:
        payload["connector_official_hint"] = True

    item = RawNewsItem(
        id=str(uuid4()),
        provider=article.provider,
        external_id=article.external_id,
        canonical_url=url,
        publisher=article.publisher,
        title=article.title[:1024],
        excerpt=article.excerpt,
        published_at=article.published_at,
        fetched_at=datetime.now(timezone.utc),
        language=article.language,
        payload_json=payload,
        content_hash=digest,
        processing_status="pending",
    )
    try:
        with db.begin_nested():
            db.add(item)
            db.flush()
    except IntegrityError:
        return None, "duplicate"
    return item, "inserted"


def process_pending(
    db: Session,
    *,
    prefer_live_enrich: bool = True,
    personalize: bool = True,
    pending_limit: int = 200,
) -> IngestResult:
    result = IngestResult()
    limit = max(1, min(int(pending_limit), 500))
    pending = (
        db.query(RawNewsItem)
        .filter(RawNewsItem.processing_status == "pending")
        .order_by(RawNewsItem.fetched_at.asc())
        .limit(limit)
        .all()
    )
    if not pending:
        return result

    clusters = assign_clusters(pending)
    result.clusters = len(clusters)
    for cluster in clusters:
        decision = can_publish(cluster.items)
        if not decision.allowed:
            for item in cluster.items:
                item.processing_status = "rejected"
                item.error = decision.reason
            result.rejected += 1
            continue
        try:
            enrichment = enrich_cluster(cluster.items, prefer_live=prefer_live_enrich)
            event = publish_event(
                db,
                items=cluster.items,
                enrichment=enrichment,
                cluster_key=cluster.key,
            )
            if event is None:
                result.rejected += 1
            else:
                result.published += 1
                result.event_ids.append(event.id)
                # Optional: personalize ready twins (skip for controlled main-stand import).
                if personalize:
                    recompute_event_for_ready_companies(db, event)
        except Exception as exc:  # noqa: BLE001
            for item in cluster.items:
                item.processing_status = "error"
                item.error = type(exc).__name__
            result.errors.append(f"{cluster.key}:{type(exc).__name__}")
    db.commit()
    return result


def run_ingestion(
    db: Session,
    *,
    providers: Sequence[SourceProvider] | None = None,
    prefer_live_enrich: bool = True,
    fetch: bool = True,
    process: bool = True,
    personalize: bool = True,
    pending_limit: int = 200,
) -> IngestResult:
    result = IngestResult()
    providers = list(providers) if providers is not None else default_providers()

    if fetch:
        for provider in providers:
            try:
                articles = provider.fetch()
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{provider.name}:fetch:{type(exc).__name__}")
                continue
            # Soft per-source errors reported by providers (e.g. http_429)
            fetch_errors = getattr(provider, "last_fetch_errors", None)
            if fetch_errors:
                for err in fetch_errors:
                    result.errors.append(f"{provider.name}:{err}")
            result.fetched += len(articles)
            for article in articles:
                try:
                    item, status = store_article(db, article)
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"store:{type(exc).__name__}")
                    continue
                if status == "inserted" and item is not None:
                    result.inserted += 1
                elif status == "duplicate":
                    result.duplicates += 1
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

    if process:
        processed = process_pending(
            db,
            prefer_live_enrich=prefer_live_enrich,
            personalize=personalize,
            pending_limit=pending_limit,
        )
        result.clusters += processed.clusters
        result.published += processed.published
        result.rejected += processed.rejected
        result.errors.extend(processed.errors)
        result.event_ids.extend(processed.event_ids)

    return result
