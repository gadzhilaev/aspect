from datetime import datetime

from pydantic import BaseModel, Field


class PublicNewsCard(BaseModel):
    id: str
    title: str
    summary: str
    category: str
    category_label: str
    event_type: str
    event_type_label: str
    severity_label: str
    occurred_at: datetime
    image_url: str
    reading_time_min: int = Field(ge=1)
    is_featured: bool = False
    is_demo: bool = False
    source_count: int = 0
    primary_publisher: str | None = None
    primary_published_at: datetime | None = None
    primary_source_url: str | None = None


class PublicNewsSource(BaseModel):
    publisher: str
    published_at: datetime | None
    excerpt: str | None
    url: str | None = None
    is_stub: bool = True


class PublicNewsDetail(BaseModel):
    id: str
    title: str
    summary: str
    category: str
    category_label: str
    event_type: str
    event_type_label: str
    severity_label: str
    occurred_at: datetime
    effective_from: datetime | None
    image_url: str
    reading_time_min: int
    is_featured: bool = False
    is_demo: bool = False
    body: str
    sources: list[PublicNewsSource]
    related: list[PublicNewsCard] = []
    primary_publisher: str | None = None
    primary_published_at: datetime | None = None
    primary_source_url: str | None = None
    source_count: int = 0


class PublicCategory(BaseModel):
    id: str
    label: str
    description: str
    count: int


class PublicTrending(BaseModel):
    featured: PublicNewsCard | None
    now_important: list[PublicNewsCard]
    risks: list[PublicNewsCard]
    opportunities: list[PublicNewsCard]
    markets: list[PublicNewsCard]
    by_industry: dict[str, list[PublicNewsCard]]


class PublicIngestionStatus(BaseModel):
    """Safe scheduler snapshot for the news feed (no paths / secrets)."""

    status: str | None = None
    sources_checked_at: str | None = None
    sources_check_ok: bool | None = None
    last_success_at: str | None = None
    next_run_at: str | None = None
    interval_seconds: int | None = None
    counts: dict[str, int] | None = None
    source_errors: list[str] = Field(default_factory=list)


class PublicNewsPage(BaseModel):
    items: list[PublicNewsCard]
    next_cursor: str | None = None
    limit: int = 20
    ingestion: PublicIngestionStatus | None = None
