from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Event, EventSource
from app.schemas.public import (
    PublicCategory,
    PublicIngestionStatus,
    PublicNewsDetail,
    PublicNewsPage,
    PublicTrending,
)
from app.services.ingestion.scheduler_status import SchedulerStatusStore, resolve_status_path
from app.services.public_news import (
    category_label,
    pick_primary_source,
    to_public_card,
    to_public_detail,
)


def _public_ingestion_status() -> PublicIngestionStatus | None:
    settings = get_settings()
    raw_dir = (getattr(settings, "news_scheduler_state_dir", None) or "").strip()
    if not raw_dir:
        return None
    path = resolve_status_path(Path(raw_dir), settings.database_url)
    view = SchedulerStatusStore(path).public_view()
    if not view.get("status") and not view.get("sources_checked_at"):
        return PublicIngestionStatus()
    return PublicIngestionStatus(
        status=view.get("status"),
        sources_checked_at=view.get("sources_checked_at"),
        sources_check_ok=view.get("sources_check_ok"),
        last_success_at=view.get("last_success_at"),
        next_run_at=view.get("next_run_at"),
        interval_seconds=view.get("interval_seconds"),
        counts=view.get("counts"),
        source_errors=list(view.get("source_errors") or [])[:20],
    )

router = APIRouter(prefix="/public", tags=["public"])


def _sources_by_event(db: Session, event_ids: list[str]) -> dict[str, list[EventSource]]:
    if not event_ids:
        return {}
    rows = db.query(EventSource).filter(EventSource.event_id.in_(event_ids)).all()
    out: dict[str, list[EventSource]] = {eid: [] for eid in event_ids}
    for row in rows:
        out.setdefault(row.event_id, []).append(row)
    return out


def _source_counts(db: Session, event_ids: list[str]) -> dict[str, int]:
    grouped = _sources_by_event(db, event_ids)
    return {eid: len(srcs) for eid, srcs in grouped.items()}


@router.get("/news", response_model=PublicNewsPage)
def public_news(
    category: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> PublicNewsPage:
    q = db.query(Event).filter(Event.status == "active")
    if category:
        q = q.filter(Event.category == category)
    if event_type:
        q = q.filter(Event.event_type == event_type)
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AppError("VALIDATION_ERROR", "Некорректный cursor", 422) from exc
        q = q.filter(Event.occurred_at < cursor_dt)
    rows = q.order_by(Event.occurred_at.desc(), Event.severity.desc()).limit(limit + 1).all()
    page = rows[:limit]
    by_event = _sources_by_event(db, [e.id for e in page])
    items = [
        to_public_card(
            e,
            len(by_event.get(e.id, [])),
            featured=(i == 0 and not category and not cursor),
            primary=pick_primary_source(by_event.get(e.id, [])),
        )
        for i, e in enumerate(page)
    ]
    next_cursor = None
    if len(rows) > limit and page:
        next_cursor = page[-1].occurred_at.isoformat()
    return PublicNewsPage(
        items=items,
        next_cursor=next_cursor,
        limit=limit,
        ingestion=_public_ingestion_status(),
    )


@router.get("/ingestion-status", response_model=PublicIngestionStatus)
def public_ingestion_status() -> PublicIngestionStatus:
    """Read-only scheduler status for the news feed. No secrets / DB paths."""
    return _public_ingestion_status() or PublicIngestionStatus()


@router.get("/news/{event_id}", response_model=PublicNewsDetail)
def public_news_detail(event_id: str, db: Session = Depends(get_db)) -> PublicNewsDetail:
    event = db.get(Event, event_id)
    if event is None or event.status != "active":
        raise AppError("NOT_FOUND", "Новость не найдена", 404)
    sources = db.query(EventSource).filter(EventSource.event_id == event_id).all()
    related_rows = (
        db.query(Event)
        .filter(Event.status == "active", Event.id != event_id, Event.category == event.category)
        .order_by(Event.occurred_at.desc())
        .limit(3)
        .all()
    )
    if len(related_rows) < 3:
        extra = (
            db.query(Event)
            .filter(
                Event.status == "active",
                Event.id != event_id,
                ~Event.id.in_([r.id for r in related_rows] or ["__none__"]),
            )
            .order_by(Event.severity.desc())
            .limit(3 - len(related_rows))
            .all()
        )
        related_rows = [*related_rows, *extra]
    related_by = _sources_by_event(db, [e.id for e in related_rows])
    related = [
        to_public_card(
            e,
            len(related_by.get(e.id, [])),
            primary=pick_primary_source(related_by.get(e.id, [])),
        )
        for e in related_rows
    ]
    return PublicNewsDetail.model_validate(to_public_detail(event, sources, related))


@router.get("/categories", response_model=list[PublicCategory])
def public_categories(db: Session = Depends(get_db)) -> list[PublicCategory]:
    rows = db.query(Event).filter(Event.status == "active").all()
    counts: dict[str, int] = {}
    for e in rows:
        counts[e.category] = counts.get(e.category, 0) + 1
    descriptions = {
        "geopolitics": "Регуляторные и экспортные сигналы",
        "macro": "Ставки, валюта и стоимость денег",
        "market": "Спрос, импорт и окна роста",
    }
    return [
        PublicCategory(
            id=cat,
            label=category_label(cat),
            description=descriptions.get(cat, "Отраслевая лента"),
            count=count,
        )
        for cat, count in sorted(counts.items(), key=lambda x: -x[1])
    ]


@router.get("/trending", response_model=PublicTrending)
def public_trending(db: Session = Depends(get_db)) -> PublicTrending:
    rows = (
        db.query(Event)
        .filter(Event.status == "active")
        .order_by(Event.severity.desc(), Event.occurred_at.desc())
        .all()
    )
    by_event = _sources_by_event(db, [e.id for e in rows])
    cards = [
        to_public_card(
            e,
            len(by_event.get(e.id, [])),
            primary=pick_primary_source(by_event.get(e.id, [])),
        )
        for e in rows
    ]
    featured = None
    if cards:
        featured = {**cards[0], "is_featured": True}
    risks = [c for c in cards if c["event_type"] == "risk"][:4]
    opportunities = [c for c in cards if c["event_type"] == "opportunity"][:4]
    markets = [c for c in cards if c["category"] in {"market", "macro"}][:4]
    now_important = cards[:4]
    by_industry: dict[str, list] = {}
    for c in cards:
        by_industry.setdefault(c["category_label"], []).append(c)
    for key in list(by_industry):
        by_industry[key] = by_industry[key][:3]
    return PublicTrending(
        featured=featured,
        now_important=now_important,
        risks=risks,
        opportunities=opportunities,
        markets=markets,
        by_industry=by_industry,
    )
