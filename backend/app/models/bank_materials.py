"""Bank research materials corpus (OCR-backed). No importer/search/API in this module."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

REGION_TYPES = (
    "prose",
    "table",
    "chart",
    "contacts_disclaimer",
    "mixed",
    "unverified",
)
REGION_TYPE_SQL = ", ".join(f"'{t}'" for t in REGION_TYPES)


class BankDocument(Base):
    __tablename__ = "bank_documents"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_bank_documents_slug"),
        CheckConstraint(
            "title_status IN ('confirmed', 'unknown', 'filename_hint')",
            name="ck_bank_documents_title_status",
        ),
        CheckConstraint(
            "publication_date_precision IN ('day', 'month', 'unknown')",
            name="ck_bank_documents_pub_precision",
        ),
        CheckConstraint(
            "period_covered_status IN ('confirmed', 'unknown')",
            name="ck_bank_documents_period_status",
        ),
        CheckConstraint(
            "topics_status IN ('confirmed', 'unknown')",
            name="ck_bank_documents_topics_status",
        ),
        CheckConstraint(
            "document_visual_status IN ("
            "'unverified', 'partial_spot_check', 'verified_spot_check', 'verified'"
            ")",
            name="ck_bank_documents_visual_status",
        ),
        CheckConstraint(
            "publication_month IS NULL OR (publication_month >= 1 AND publication_month <= 12)",
            name="ck_bank_documents_pub_month_range",
        ),
        # Precision ↔ nullability. Year/month vs calendar day match is importer-validated
        # (portable across SQLite/PostgreSQL without dialect-specific EXTRACT in CHECK).
        CheckConstraint(
            "("
            "publication_date_precision = 'day' "
            "AND publication_date IS NOT NULL "
            "AND publication_year IS NOT NULL "
            "AND publication_month IS NOT NULL"
            ") OR ("
            "publication_date_precision = 'month' "
            "AND publication_date IS NULL "
            "AND publication_year IS NOT NULL "
            "AND publication_month IS NOT NULL"
            ") OR ("
            "publication_date_precision = 'unknown' "
            "AND publication_date IS NULL "
            "AND publication_year IS NULL "
            "AND publication_month IS NULL"
            ")",
            name="ck_bank_documents_pub_date_shape",
        ),
        Index("ix_bank_documents_pub_ym", "publication_year", "publication_month"),
        Index("ix_bank_documents_visual_status", "document_visual_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title_status: Mapped[str] = mapped_column(String(32), nullable=False)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    publication_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    publication_month: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    publication_date_precision: Mapped[str] = mapped_column(String(16), nullable=False)
    publication_date_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period_covered: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_covered_status: Mapped[str] = mapped_column(String(32), nullable=False)
    topics_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    topics_status: Mapped[str] = mapped_column(String(32), nullable=False)
    staleness_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_current_stance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    document_visual_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BankDocumentFile(Base):
    __tablename__ = "bank_document_files"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_bank_document_files_sha256"),
        UniqueConstraint("id", "document_id", name="uq_bank_document_files_id_document"),
        ForeignKeyConstraint(
            ["document_id"],
            ["bank_documents.id"],
            name="fk_bank_document_files_document",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_id", "supersedes_file_id"],
            ["bank_document_files.document_id", "bank_document_files.id"],
            name="fk_bank_document_files_supersedes_same_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint("page_count >= 1", name="ck_bank_document_files_page_count"),
        CheckConstraint("byte_size >= 0", name="ck_bank_document_files_byte_size"),
        CheckConstraint(
            "supersedes_file_id IS NULL OR supersedes_file_id != id",
            name="ck_bank_document_files_supersedes_not_self",
        ),
        Index("ix_bank_document_files_document_id", "document_id"),
        Index("ix_bank_document_files_supersedes_file_id", "supersedes_file_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    pdf_producer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # PDF metadata only — never used as publication_date.
    pdf_creation_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revision_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supersedes_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BankOcrRun(Base):
    __tablename__ = "bank_ocr_runs"
    __table_args__ = (
        UniqueConstraint(
            "document_file_id",
            "fingerprint_hash",
            name="uq_bank_ocr_runs_file_fingerprint",
        ),
        UniqueConstraint("id", "document_file_id", name="uq_bank_ocr_runs_id_file"),
        ForeignKeyConstraint(
            ["document_file_id"],
            ["bank_document_files.id"],
            name="fk_bank_ocr_runs_file",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "processing_status IN ('complete', 'incomplete')",
            name="ck_bank_ocr_runs_processing_status",
        ),
        CheckConstraint("schema_version >= 1", name="ck_bank_ocr_runs_schema_version"),
        CheckConstraint("psm_default >= 0", name="ck_bank_ocr_runs_psm_default"),
        Index("ix_bank_ocr_runs_processing_status", "processing_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    tesseract_version_line: Mapped[str] = mapped_column(String(128), nullable=False)
    lang: Mapped[str] = mapped_column(String(32), nullable=False)
    psm_default: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    preserve_interword_spaces: Mapped[bool] = mapped_column(Boolean, nullable=False)
    eng_traineddata_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rus_traineddata_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    params_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    pages_ok_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    pages_failed_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    artifact_root_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BankOcrPage(Base):
    __tablename__ = "bank_ocr_pages"
    __table_args__ = (
        UniqueConstraint("ocr_run_id", "page_number", name="uq_bank_ocr_pages_run_page"),
        UniqueConstraint("id", "ocr_run_id", name="uq_bank_ocr_pages_id_run"),
        ForeignKeyConstraint(
            ["ocr_run_id"],
            ["bank_ocr_runs.id"],
            name="fk_bank_ocr_pages_run",
            ondelete="RESTRICT",
        ),
        CheckConstraint("page_number >= 1", name="ck_bank_ocr_pages_page_number"),
        CheckConstraint(
            "width IS NULL OR width > 0",
            name="ck_bank_ocr_pages_width_positive",
        ),
        CheckConstraint(
            "height IS NULL OR height > 0",
            name="ck_bank_ocr_pages_height_positive",
        ),
        CheckConstraint(
            "processing_status IN ('ok', 'failed', 'incomplete')",
            name="ck_bank_ocr_pages_processing_status",
        ),
        CheckConstraint(
            "visual_verification_status IN ("
            "'unverified', 'verified_spot_check', 'verified_partial', 'verified'"
            ")",
            name="ck_bank_ocr_pages_visual_status",
        ),
        Index("ix_bank_ocr_pages_visual_status", "visual_verification_status"),
        Index("ix_bank_ocr_pages_processing_status", "processing_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ocr_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_text_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cleaned_text_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tsv_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    words_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mean_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    psm_used: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    visual_verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    content_regions_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    visual_checks_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class BankFragment(Base):
    """One revision of a logical fragment inside an OCR run.

    Eligibility is computed by ``compute_fragment_eligibility`` — not stored columns.
    """

    __tablename__ = "bank_fragments"
    __table_args__ = (
        UniqueConstraint(
            "ocr_run_id",
            "stable_key",
            "revision",
            name="uq_bank_fragments_run_key_revision",
        ),
        UniqueConstraint(
            "id",
            "ocr_run_id",
            "stable_key",
            name="uq_bank_fragments_id_run_key",
        ),
        UniqueConstraint("id", "ocr_run_id", name="uq_bank_fragments_id_run"),
        ForeignKeyConstraint(
            ["ocr_run_id", "document_file_id"],
            ["bank_ocr_runs.id", "bank_ocr_runs.document_file_id"],
            name="fk_bank_fragments_run_file",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_file_id", "document_id"],
            ["bank_document_files.id", "bank_document_files.document_id"],
            name="fk_bank_fragments_file_document",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["ocr_run_id", "page_number"],
            ["bank_ocr_pages.ocr_run_id", "bank_ocr_pages.page_number"],
            name="fk_bank_fragments_run_page",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supersedes_fragment_id", "ocr_run_id", "stable_key"],
            [
                "bank_fragments.id",
                "bank_fragments.ocr_run_id",
                "bank_fragments.stable_key",
            ],
            name="fk_bank_fragments_supersedes_same_key",
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision >= 1", name="ck_bank_fragments_revision"),
        CheckConstraint("page_number >= 1", name="ck_bank_fragments_page_number"),
        CheckConstraint(
            "kind IN ('exact_quote', 'summary')",
            name="ck_bank_fragments_kind",
        ),
        CheckConstraint(
            f"primary_region_type IN ({REGION_TYPE_SQL})",
            name="ck_bank_fragments_primary_region_type",
        ),
        CheckConstraint(
            "content_type IS NULL OR content_type IN ('fact', 'forecast', 'interpretation')",
            name="ck_bank_fragments_content_type",
        ),
        CheckConstraint(
            "content_type_status IN ('confirmed', 'unconfirmed', 'unknown')",
            name="ck_bank_fragments_content_type_status",
        ),
        CheckConstraint(
            "verification_status IN ('verified', 'unverified', 'needs_reverification')",
            name="ck_bank_fragments_verification_status",
        ),
        CheckConstraint(
            "supersedes_fragment_id IS NULL OR supersedes_fragment_id != id",
            name="ck_bank_fragments_supersedes_not_self",
        ),
        Index("ix_bank_fragments_document_id", "document_id"),
        Index("ix_bank_fragments_verification_status", "verification_status"),
        Index("ix_bank_fragments_file_page", "document_file_id", "page_number"),
        Index("ix_bank_fragments_run_stable_key", "ocr_run_id", "stable_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ocr_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    document_file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    stable_key: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_region_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_type_status: Mapped[str] = mapped_column(String(32), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleaned_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    ocr_correction_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_fragment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BankFragmentRegion(Base):
    __tablename__ = "bank_fragment_regions"
    __table_args__ = (
        UniqueConstraint(
            "fragment_id",
            "sort_order",
            name="uq_bank_fragment_regions_fragment_sort",
        ),
        ForeignKeyConstraint(
            ["fragment_id", "ocr_run_id"],
            ["bank_fragments.id", "bank_fragments.ocr_run_id"],
            name="fk_bank_fragment_regions_fragment_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["ocr_run_id", "page_number"],
            ["bank_ocr_pages.ocr_run_id", "bank_ocr_pages.page_number"],
            name="fk_bank_fragment_regions_run_page",
            ondelete="RESTRICT",
        ),
        CheckConstraint("page_number >= 1", name="ck_bank_fragment_regions_page_number"),
        CheckConstraint("sort_order >= 0", name="ck_bank_fragment_regions_sort_order"),
        CheckConstraint(
            f"region_type IN ({REGION_TYPE_SQL})",
            name="ck_bank_fragment_regions_region_type",
        ),
        # All-or-nothing bbox; containment in page size is importer-validated.
        CheckConstraint(
            "("
            "bbox_left IS NULL AND bbox_top IS NULL "
            "AND bbox_width IS NULL AND bbox_height IS NULL"
            ") OR ("
            "bbox_left IS NOT NULL AND bbox_top IS NOT NULL "
            "AND bbox_width IS NOT NULL AND bbox_height IS NOT NULL "
            "AND bbox_left >= 0 AND bbox_top >= 0 "
            "AND bbox_width > 0 AND bbox_height > 0"
            ")",
            name="ck_bank_fragment_regions_bbox_shape",
        ),
        Index("ix_bank_fragment_regions_fragment_id", "fragment_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fragment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ocr_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    region_type: Mapped[str] = mapped_column(String(32), nullable=False)
    bbox_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox_top: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coord_space: Mapped[str] = mapped_column(
        String(32), default="page_image_px", nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
