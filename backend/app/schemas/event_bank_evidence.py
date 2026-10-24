"""Typed response for GET /events/{event_id}/bank-evidence (stage 2.13)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

EventBankEvidenceStatus = Literal[
    "available",
    "no_matching_evidence",
    "integration_not_configured",
    "event_date_unavailable",
]


class EventBankEvidenceItemOut(BaseModel):
    document_id: str
    document_file_id: str
    ocr_run_id: str
    fragment_id: str
    stable_key: str
    revision: int
    document_title: str | None = None
    document_slug: str
    publication_date: date | None = None
    publication_year: int | None = None
    publication_month: int | None = None
    publication_date_precision: str
    publication_date_display: str | None = None
    page_number: int
    text_kind: Literal["exact_quote", "summary"]
    text: str
    content_type: str | None = None
    content_type_status: str
    source_role: str | None = None
    source_role_meaning: str
    qa_method: str | None = None
    match_reasons: list[str] = Field(default_factory=list)
    lexical_match_score: float
    date_gate_reasons: list[str] = Field(default_factory=list)
    document_href: str
    fragment_href: str
    content_href: str


class EventBankEvidenceOut(BaseModel):
    event_id: str
    status: EventBankEvidenceStatus
    event_occurred_at: datetime | None = None
    as_of_date: date | None = None
    as_of_date_basis: str | None = None
    query_preview: str | None = None
    evidence: list[EventBankEvidenceItemOut] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    empty_reason: str | None = None
