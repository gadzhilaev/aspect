"""Re-queue previously rejected raw items after a policy change.

Does not delete rows or change IDs. Dedup store_article is unrelated — rejected
items already exist; we only reset status so process_pending can publish.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.raw_news import RawNewsItem
from app.services.ingestion.official_sources import classify_official_primary
from app.services.ingestion.pipeline import IngestResult, process_pending


def _host(url: str) -> str:
    h = urlparse(url or "").netloc.lower()
    return h[4:] if h.startswith("www.") else h


@dataclass
class ReprocessPlan:
    dry_run: bool
    candidate_ids: list[str] = field(default_factory=list)
    would_be_official: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


def select_rejected_for_reprocess(
    db: Session,
    *,
    raw_ids: Sequence[str] | None = None,
    feed_hosts: Sequence[str] | None = None,
    article_hosts: Sequence[str] | None = None,
    errors: Sequence[str] | None = None,
    only_would_be_official: bool = False,
    limit: int = 200,
) -> list[RawNewsItem]:
    q = db.query(RawNewsItem).filter(RawNewsItem.processing_status == "rejected")
    if raw_ids:
        q = q.filter(RawNewsItem.id.in_(list(raw_ids)))
    if errors:
        q = q.filter(RawNewsItem.error.in_(list(errors)))
    items = q.order_by(RawNewsItem.fetched_at.asc()).limit(max(1, min(limit, 500))).all()

    def _norm_host(h: str) -> str:
        x = (h or "").lower().strip()
        return x[4:] if x.startswith("www.") else x

    feed_allow = {_norm_host(h) for h in (feed_hosts or []) if h}
    article_allow = {_norm_host(h) for h in (article_hosts or []) if h}

    selected: list[RawNewsItem] = []
    for item in items:
        payload = item.payload_json if isinstance(item.payload_json, dict) else {}
        feed = str(payload.get("feed_url") or "")
        fh = _host(feed)
        ah = _host(item.canonical_url or "")
        if feed_allow and fh not in feed_allow:
            continue
        if article_allow and ah not in article_allow:
            continue
        if only_would_be_official and not classify_official_primary(item).is_official_primary:
            continue
        selected.append(item)
    return selected


def plan_reprocess(
    db: Session,
    *,
    dry_run: bool = True,
    raw_ids: Sequence[str] | None = None,
    feed_hosts: Sequence[str] | None = None,
    article_hosts: Sequence[str] | None = None,
    errors: Sequence[str] | None = None,
    only_would_be_official: bool = True,
    limit: int = 200,
) -> ReprocessPlan:
    items = select_rejected_for_reprocess(
        db,
        raw_ids=raw_ids,
        feed_hosts=feed_hosts,
        article_hosts=article_hosts,
        errors=errors or ["unverified_single_source"],
        only_would_be_official=only_would_be_official,
        limit=limit,
    )
    plan = ReprocessPlan(dry_run=dry_run)
    for item in items:
        plan.candidate_ids.append(item.id)
        cls = classify_official_primary(item)
        if cls.is_official_primary:
            plan.would_be_official.append(item.id)
        else:
            plan.skipped.append({"id": item.id, "reason": cls.reason})
    return plan


def requeue_rejected(
    db: Session,
    items: Iterable[RawNewsItem],
) -> int:
    """Reset rejected → pending without changing primary keys."""
    n = 0
    for item in items:
        if item.processing_status != "rejected":
            continue
        item.processing_status = "pending"
        item.error = None
        # Keep event_id None; do not invent links
        item.event_id = None
        n += 1
    return n


def reprocess_rejected(
    db: Session,
    *,
    dry_run: bool = True,
    prefer_live_enrich: bool = False,
    personalize: bool = True,
    raw_ids: Sequence[str] | None = None,
    feed_hosts: Sequence[str] | None = None,
    article_hosts: Sequence[str] | None = None,
    errors: Sequence[str] | None = None,
    only_would_be_official: bool = True,
    limit: int = 200,
) -> tuple[ReprocessPlan, IngestResult | None]:
    plan = plan_reprocess(
        db,
        dry_run=dry_run,
        raw_ids=raw_ids,
        feed_hosts=feed_hosts,
        article_hosts=article_hosts,
        errors=errors,
        only_would_be_official=only_would_be_official,
        limit=limit,
    )
    if dry_run:
        return plan, None

    items = (
        db.query(RawNewsItem)
        .filter(RawNewsItem.id.in_(plan.candidate_ids))
        .all()
        if plan.candidate_ids
        else []
    )
    requeue_rejected(db, items)
    db.commit()
    result = process_pending(
        db,
        prefer_live_enrich=prefer_live_enrich,
        personalize=personalize,
    )
    return plan, result
