"""bank materials corpus tables

Revision ID: 007
Revises: 006
Create Date: 2026-10-21

Creates bank_* tables only. No PDF/OCR import, no seed data.
Does not mutate companies, case_*, news, or assistant tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BANK_TABLES = [
    "bank_fragment_regions",
    "bank_fragments",
    "bank_ocr_pages",
    "bank_ocr_runs",
    "bank_document_files",
    "bank_documents",
]

REGION_TYPES = (
    "'prose', 'table', 'chart', 'contacts_disclaimer', 'mixed', 'unverified'"
)


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _has_table(inspector, "bank_documents"):
        return

    op.create_table(
        "bank_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("title_status", sa.String(length=32), nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("publication_year", sa.SmallInteger(), nullable=True),
        sa.Column("publication_month", sa.SmallInteger(), nullable=True),
        sa.Column("publication_date_precision", sa.String(length=16), nullable=False),
        sa.Column("publication_date_display", sa.String(length=255), nullable=True),
        sa.Column("period_covered", sa.Text(), nullable=True),
        sa.Column("period_covered_status", sa.String(length=32), nullable=False),
        sa.Column("topics_json", sa.JSON(), nullable=False),
        sa.Column("topics_status", sa.String(length=32), nullable=False),
        sa.Column("staleness_note", sa.Text(), nullable=True),
        sa.Column("is_current_stance", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("document_visual_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("slug", name="uq_bank_documents_slug"),
        sa.CheckConstraint(
            "title_status IN ('confirmed', 'unknown', 'filename_hint')",
            name="ck_bank_documents_title_status",
        ),
        sa.CheckConstraint(
            "publication_date_precision IN ('day', 'month', 'unknown')",
            name="ck_bank_documents_pub_precision",
        ),
        sa.CheckConstraint(
            "period_covered_status IN ('confirmed', 'unknown')",
            name="ck_bank_documents_period_status",
        ),
        sa.CheckConstraint(
            "topics_status IN ('confirmed', 'unknown')",
            name="ck_bank_documents_topics_status",
        ),
        sa.CheckConstraint(
            "document_visual_status IN ("
            "'unverified', 'partial_spot_check', 'verified_spot_check', 'verified'"
            ")",
            name="ck_bank_documents_visual_status",
        ),
        sa.CheckConstraint(
            "publication_month IS NULL OR (publication_month >= 1 AND publication_month <= 12)",
            name="ck_bank_documents_pub_month_range",
        ),
        sa.CheckConstraint(
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
    )
    op.create_index(
        "ix_bank_documents_pub_ym",
        "bank_documents",
        ["publication_year", "publication_month"],
    )
    op.create_index(
        "ix_bank_documents_visual_status",
        "bank_documents",
        ["document_visual_status"],
    )

    op.create_table(
        "bank_document_files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("pdf_producer", sa.String(length=255), nullable=True),
        sa.Column("pdf_creation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision_label", sa.String(length=128), nullable=True),
        sa.Column("supersedes_file_id", sa.String(length=36), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["bank_documents.id"],
            name="fk_bank_document_files_document",
            ondelete="RESTRICT",
        ),
        # Inline CREATE TABLE FK — SQLite cannot ALTER ADD CONSTRAINT.
        sa.ForeignKeyConstraint(
            ["document_id", "supersedes_file_id"],
            ["bank_document_files.document_id", "bank_document_files.id"],
            name="fk_bank_document_files_supersedes_same_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("sha256", name="uq_bank_document_files_sha256"),
        sa.UniqueConstraint("id", "document_id", name="uq_bank_document_files_id_document"),
        sa.CheckConstraint("page_count >= 1", name="ck_bank_document_files_page_count"),
        sa.CheckConstraint("byte_size >= 0", name="ck_bank_document_files_byte_size"),
        sa.CheckConstraint(
            "supersedes_file_id IS NULL OR supersedes_file_id != id",
            name="ck_bank_document_files_supersedes_not_self",
        ),
    )
    op.create_index(
        "ix_bank_document_files_document_id",
        "bank_document_files",
        ["document_id"],
    )
    op.create_index(
        "ix_bank_document_files_supersedes_file_id",
        "bank_document_files",
        ["supersedes_file_id"],
    )

    op.create_table(
        "bank_ocr_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_file_id", sa.String(length=36), nullable=False),
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("tesseract_version_line", sa.String(length=128), nullable=False),
        sa.Column("lang", sa.String(length=32), nullable=False),
        sa.Column("psm_default", sa.SmallInteger(), nullable=False),
        sa.Column("preserve_interword_spaces", sa.Boolean(), nullable=False),
        sa.Column("eng_traineddata_sha256", sa.String(length=64), nullable=False),
        sa.Column("rus_traineddata_sha256", sa.String(length=64), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("pages_ok_json", sa.JSON(), nullable=False),
        sa.Column("pages_failed_json", sa.JSON(), nullable=False),
        sa.Column("artifact_root_key", sa.String(length=1024), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_file_id"],
            ["bank_document_files.id"],
            name="fk_bank_ocr_runs_file",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "document_file_id",
            "fingerprint_hash",
            name="uq_bank_ocr_runs_file_fingerprint",
        ),
        sa.UniqueConstraint("id", "document_file_id", name="uq_bank_ocr_runs_id_file"),
        sa.CheckConstraint(
            "processing_status IN ('complete', 'incomplete')",
            name="ck_bank_ocr_runs_processing_status",
        ),
        sa.CheckConstraint("schema_version >= 1", name="ck_bank_ocr_runs_schema_version"),
        sa.CheckConstraint("psm_default >= 0", name="ck_bank_ocr_runs_psm_default"),
    )
    op.create_index(
        "ix_bank_ocr_runs_processing_status",
        "bank_ocr_runs",
        ["processing_status"],
    )

    op.create_table(
        "bank_ocr_pages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("ocr_run_id", sa.String(length=36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("image_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("raw_text_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("cleaned_text_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("tsv_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("words_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("mean_confidence", sa.Float(), nullable=True),
        sa.Column("median_confidence", sa.Float(), nullable=True),
        sa.Column("psm_used", sa.SmallInteger(), nullable=True),
        sa.Column("visual_verification_status", sa.String(length=32), nullable=False),
        sa.Column("content_regions_json", sa.JSON(), nullable=False),
        sa.Column("visual_checks_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["ocr_run_id"],
            ["bank_ocr_runs.id"],
            name="fk_bank_ocr_pages_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("ocr_run_id", "page_number", name="uq_bank_ocr_pages_run_page"),
        sa.UniqueConstraint("id", "ocr_run_id", name="uq_bank_ocr_pages_id_run"),
        sa.CheckConstraint("page_number >= 1", name="ck_bank_ocr_pages_page_number"),
        sa.CheckConstraint("width IS NULL OR width > 0", name="ck_bank_ocr_pages_width_positive"),
        sa.CheckConstraint(
            "height IS NULL OR height > 0",
            name="ck_bank_ocr_pages_height_positive",
        ),
        sa.CheckConstraint(
            "processing_status IN ('ok', 'failed', 'incomplete')",
            name="ck_bank_ocr_pages_processing_status",
        ),
        sa.CheckConstraint(
            "visual_verification_status IN ("
            "'unverified', 'verified_spot_check', 'verified_partial', 'verified'"
            ")",
            name="ck_bank_ocr_pages_visual_status",
        ),
    )
    op.create_index(
        "ix_bank_ocr_pages_visual_status",
        "bank_ocr_pages",
        ["visual_verification_status"],
    )
    op.create_index(
        "ix_bank_ocr_pages_processing_status",
        "bank_ocr_pages",
        ["processing_status"],
    )

    op.create_table(
        "bank_fragments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("ocr_run_id", sa.String(length=36), nullable=False),
        sa.Column("document_file_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("stable_key", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("primary_region_type", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=True),
        sa.Column("content_type_status", sa.String(length=32), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("cleaned_text", sa.Text(), nullable=True),
        sa.Column("verified_transcript", sa.Text(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("ocr_correction_json", sa.JSON(), nullable=True),
        sa.Column("source_role", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("supersedes_fragment_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ocr_run_id", "document_file_id"],
            ["bank_ocr_runs.id", "bank_ocr_runs.document_file_id"],
            name="fk_bank_fragments_run_file",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_file_id", "document_id"],
            ["bank_document_files.id", "bank_document_files.document_id"],
            name="fk_bank_fragments_file_document",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ocr_run_id", "page_number"],
            ["bank_ocr_pages.ocr_run_id", "bank_ocr_pages.page_number"],
            name="fk_bank_fragments_run_page",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_fragment_id", "ocr_run_id", "stable_key"],
            [
                "bank_fragments.id",
                "bank_fragments.ocr_run_id",
                "bank_fragments.stable_key",
            ],
            name="fk_bank_fragments_supersedes_same_key",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "ocr_run_id",
            "stable_key",
            "revision",
            name="uq_bank_fragments_run_key_revision",
        ),
        sa.UniqueConstraint(
            "id",
            "ocr_run_id",
            "stable_key",
            name="uq_bank_fragments_id_run_key",
        ),
        sa.UniqueConstraint("id", "ocr_run_id", name="uq_bank_fragments_id_run"),
        sa.CheckConstraint("revision >= 1", name="ck_bank_fragments_revision"),
        sa.CheckConstraint("page_number >= 1", name="ck_bank_fragments_page_number"),
        sa.CheckConstraint(
            "kind IN ('exact_quote', 'summary')",
            name="ck_bank_fragments_kind",
        ),
        sa.CheckConstraint(
            f"primary_region_type IN ({REGION_TYPES})",
            name="ck_bank_fragments_primary_region_type",
        ),
        sa.CheckConstraint(
            "content_type IS NULL OR content_type IN ('fact', 'forecast', 'interpretation')",
            name="ck_bank_fragments_content_type",
        ),
        sa.CheckConstraint(
            "content_type_status IN ('confirmed', 'unconfirmed', 'unknown')",
            name="ck_bank_fragments_content_type_status",
        ),
        sa.CheckConstraint(
            "verification_status IN ('verified', 'unverified', 'needs_reverification')",
            name="ck_bank_fragments_verification_status",
        ),
        sa.CheckConstraint(
            "supersedes_fragment_id IS NULL OR supersedes_fragment_id != id",
            name="ck_bank_fragments_supersedes_not_self",
        ),
    )
    op.create_index("ix_bank_fragments_document_id", "bank_fragments", ["document_id"])
    op.create_index(
        "ix_bank_fragments_verification_status",
        "bank_fragments",
        ["verification_status"],
    )
    op.create_index(
        "ix_bank_fragments_file_page",
        "bank_fragments",
        ["document_file_id", "page_number"],
    )
    op.create_index(
        "ix_bank_fragments_run_stable_key",
        "bank_fragments",
        ["ocr_run_id", "stable_key"],
    )

    op.create_table(
        "bank_fragment_regions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("fragment_id", sa.String(length=36), nullable=False),
        sa.Column("ocr_run_id", sa.String(length=36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("region_type", sa.String(length=32), nullable=False),
        sa.Column("bbox_left", sa.Integer(), nullable=True),
        sa.Column("bbox_top", sa.Integer(), nullable=True),
        sa.Column("bbox_width", sa.Integer(), nullable=True),
        sa.Column("bbox_height", sa.Integer(), nullable=True),
        sa.Column(
            "coord_space",
            sa.String(length=32),
            nullable=False,
            server_default="page_image_px",
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["fragment_id", "ocr_run_id"],
            ["bank_fragments.id", "bank_fragments.ocr_run_id"],
            name="fk_bank_fragment_regions_fragment_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ocr_run_id", "page_number"],
            ["bank_ocr_pages.ocr_run_id", "bank_ocr_pages.page_number"],
            name="fk_bank_fragment_regions_run_page",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "fragment_id",
            "sort_order",
            name="uq_bank_fragment_regions_fragment_sort",
        ),
        sa.CheckConstraint("page_number >= 1", name="ck_bank_fragment_regions_page_number"),
        sa.CheckConstraint("sort_order >= 0", name="ck_bank_fragment_regions_sort_order"),
        sa.CheckConstraint(
            f"region_type IN ({REGION_TYPES})",
            name="ck_bank_fragment_regions_region_type",
        ),
        sa.CheckConstraint(
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
    )
    op.create_index(
        "ix_bank_fragment_regions_fragment_id",
        "bank_fragment_regions",
        ["fragment_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for name in BANK_TABLES:
        if _has_table(inspector, name):
            op.drop_table(name)
            inspector = inspect(bind)
