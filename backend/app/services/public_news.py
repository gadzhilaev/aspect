"""Public news projections — never include company-specific impact fields."""

from __future__ import annotations

from datetime import datetime

from app.models import Event, EventSource

CATEGORY_LABELS = {
    "geopolitics": "Геополитика",
    "macro": "Макроэкономика",
    "market": "Рынки",
    "electronics": "Электроника",
    "equipment": "Оборудование",
    "logistics": "Логистика",
    "energy": "Энергетика",
    "other": "Прочее",
}

EVENT_TYPE_LABELS = {
    "risk": "Риск",
    "opportunity": "Возможность",
    "market": "Рынок",
    "neutral": "Нейтрально",
}

# Editorial cover images (public Unsplash) — not company data
CATEGORY_IMAGES = {
    "geopolitics": "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?auto=format&fit=crop&w=1400&q=80",
    "macro": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1400&q=80",
    "market": "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=1400&q=80",
    "default": "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=1400&q=80",
}


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.capitalize())


def event_type_label(event_type: str) -> str:
    return EVENT_TYPE_LABELS.get(event_type, "Событие")


def severity_label(severity: float | None) -> str:
    if severity is None:
        return "Важность не определена"
    if severity >= 80:
        return "Высокая важность"
    if severity >= 55:
        return "Средняя важность"
    return "Обзор"


def image_for(event: Event) -> str:
    attrs = event.attributes_json or {}
    if isinstance(attrs.get("image_url"), str):
        return attrs["image_url"]
    return CATEGORY_IMAGES.get(event.category, CATEGORY_IMAGES["default"])


def reading_time(summary: str) -> int:
    words = max(1, len(summary.split()))
    return max(2, min(12, round(words / 40) + 2))


def pick_primary_source(sources: list[EventSource]) -> EventSource | None:
    if not sources:
        return None
    # Prefer non-stub, then highest quality, then latest published
    def sort_key(s: EventSource) -> tuple:
        pub: datetime | None = s.published_at
        ts = pub.timestamp() if pub is not None else 0.0
        return (0 if s.is_stub else 1, s.source_quality or 0.0, ts)

    return sorted(sources, key=sort_key, reverse=True)[0]


def to_public_card(
    event: Event,
    source_count: int = 0,
    *,
    featured: bool = False,
    primary: EventSource | None = None,
) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "summary": event.summary,
        "category": event.category,
        "category_label": category_label(event.category),
        "event_type": event.event_type,
        "event_type_label": event_type_label(event.event_type),
        "severity_label": severity_label(event.severity),
        "occurred_at": event.occurred_at,
        "image_url": image_for(event),
        "reading_time_min": reading_time(event.summary),
        "is_featured": featured,
        "is_demo": bool(event.is_demo),
        "source_count": source_count,
        "primary_publisher": primary.publisher if primary else None,
        "primary_published_at": primary.published_at if primary else event.occurred_at,
        "primary_source_url": primary.url if primary else None,
    }


def to_public_detail(event: Event, sources: list[EventSource], related: list[dict]) -> dict:
    primary = pick_primary_source(sources)
    if event.is_demo:
        body = (
            f"{event.summary}\n\n"
            "Материал подготовлен редакцией «Аспект» на основе открытых сигналов и "
            "демонстрационных источников. После создания профиля компании вы увидите, "
            "как это событие связано с вашими поставщиками, линиями и рынками."
        )
    else:
        pubs = ", ".join(sorted({s.publisher for s in sources})) or "открытых источников"
        body = (
            f"{event.summary}\n\n"
            f"Сводка по материалам: {pubs}. "
            "Оригинальные публикации доступны в блоке «Источники»."
        )
    return {
        **to_public_card(event, source_count=len(sources), primary=primary),
        "effective_from": event.effective_from,
        "body": body,
        "sources": [
            {
                "publisher": s.publisher,
                "published_at": s.published_at,
                "excerpt": s.excerpt,
                "url": s.url,
                "is_stub": s.is_stub,
            }
            for s in sources
        ],
        "related": related,
    }
