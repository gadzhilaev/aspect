"""Read-only bank materials API schemas (stage 2.12)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

TextKind = Literal["exact_quote", "summary", "restricted"]


class BankRegionOut(BaseModel):
    page_number: int
    sort_order: int
    region_type: str
    bbox_left: int | None = None
    bbox_top: int | None = None
    bbox_width: int | None = None
    bbox_height: int | None = None
    note: str | None = None


class BankOcrRunRefOut(BaseModel):
    ocr_run_id: str
    fingerprint_hash: str
    processing_status: str
    schema_version: int
    created_at: datetime | None = None


class BankFileRefOut(BaseModel):
    file_id: str
    original_filename: str
    page_count: int
    byte_size: int
    pdf_sha256: str
    revision_label: str | None = None
    supersedes_file_id: str | None = None
    content_href: str
    ocr_runs: list[BankOcrRunRefOut] = Field(default_factory=list)


class BankDocumentOut(BaseModel):
    document_id: str
    slug: str
    title: str | None
    title_status: str
    publication_date: date | None
    publication_year: int | None
    publication_month: int | None
    publication_date_precision: str
    publication_date_display: str | None
    period_covered: str | None
    period_covered_status: str
    topics: list[str] = Field(default_factory=list)
    topics_status: str
    staleness_note: str | None
    is_current_stance: bool
    document_visual_status: str
    files: list[BankFileRefOut] = Field(default_factory=list)


class BankFragmentOut(BaseModel):
    fragment_id: str
    document_id: str
    document_file_id: str
    ocr_run_id: str
    stable_key: str
    revision: int
    is_latest_revision: bool
    is_superseded: bool
    supersedes_fragment_id: str | None = None
    latest_revision: int
    kind: str
    content_type: str | None
    content_type_status: str
    page_number: int
    regions: list[BankRegionOut] = Field(default_factory=list)
    verification_status: str
    primary_region_type: str
    eligible_search: bool
    eligible_ai_evidence: bool
    eligible_exact_quote: bool
    evidence_as_summary_only: bool
    eligibility_reasons: list[str] = Field(default_factory=list)
    text_kind: TextKind
    text: str | None = None
    text_restricted: bool
    restriction_reasons: list[str] = Field(default_factory=list)
    source_role: str | None = None
    source_role_meaning: str
    qa_method: str | None = None
    qa_performed_by: str | None = None
    qa_performed_at: str | None = None
    pdf_sha256: str
    ocr_fingerprint_hash: str
    document_slug: str
    document_title: str | None = None
    content_href: str
