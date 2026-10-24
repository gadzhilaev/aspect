"""Competition case data layer (immutable snapshots). No parallel Company entity."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Money: storage type only. CSV range/scale validation is the importer's job.
CASE_MONEY = Numeric(20, 1)


class CaseSnapshot(Base):
    __tablename__ = "case_snapshots"
    __table_args__ = (
        UniqueConstraint("slot_key", "version_seq", name="uq_case_snapshots_slot_version_seq"),
        UniqueConstraint("slot_key", "version_label", name="uq_case_snapshots_slot_version_label"),
        # Enables composite FKs that pin the same slot_key / snapshot identity.
        UniqueConstraint("id", "slot_key", name="uq_case_snapshots_id_slot"),
        CheckConstraint(
            "status IN ('building', 'ready', 'active', 'retired', 'failed')",
            name="ck_case_snapshots_status",
        ),
        CheckConstraint("version_seq >= 1", name="ck_case_snapshots_version_seq"),
        Index("ix_case_snapshots_slot_status", "slot_key", "status"),
        # At most one active snapshot per slot (PostgreSQL + SQLite partial unique).
        Index(
            "uq_case_snapshots_one_active_per_slot",
            "slot_key",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slot_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    version_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # Nullable only to break circular insert with case_import_runs; set in same txn.
    import_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "case_import_runs.id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_case_snapshots_import_run",
        ),
        nullable=True,
    )
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CaseActiveSnapshot(Base):
    """Mandatory pointer: which snapshot is visible for a slot."""

    __tablename__ = "case_active_snapshot"
    __table_args__ = (
        ForeignKeyConstraint(
            ["slot_key", "active_snapshot_id"],
            ["case_snapshots.slot_key", "case_snapshots.id"],
            name="fk_case_active_snapshot_same_slot",
            ondelete="RESTRICT",
        ),
    )

    slot_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    active_snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CaseImportRun(Base):
    __tablename__ = "case_import_runs"
    __table_args__ = (
        UniqueConstraint("snapshot_id", name="uq_case_import_runs_snapshot"),
        UniqueConstraint("id", "snapshot_id", name="uq_case_import_runs_id_snapshot"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'identical_skip')",
            name="ck_case_import_runs_status",
        ),
        Index("ix_case_import_runs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_cursor_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class CaseImportFile(Base):
    __tablename__ = "case_import_files"
    __table_args__ = (
        UniqueConstraint("import_run_id", "source_file", name="uq_case_import_files_run_file"),
        CheckConstraint(
            "status IN ('pending', 'loading', 'completed', 'failed')",
            name="ck_case_import_files_status",
        ),
        Index("ix_case_import_files_content_sha256", "content_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_import_runs.id", ondelete="RESTRICT"), nullable=False
    )
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_count_declared: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count_loaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    last_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CaseOrg(Base):
    __tablename__ = "case_org"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "external_uid", name="uq_case_org_snapshot_uid"),
        UniqueConstraint("snapshot_id", "id", name="uq_case_org_snapshot_id"),
        CheckConstraint(
            "profile_resolution IN ('absent', 'single', 'consensus', 'conflict')",
            name="ck_case_org_profile_resolution",
        ),
        Index("ix_case_org_snapshot_has_catalog", "snapshot_id", "has_catalog_profile"),
        Index("ix_case_org_snapshot_resolution", "snapshot_id", "profile_resolution"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    external_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    has_catalog_profile: Mapped[bool] = mapped_column(Boolean, nullable=False)
    profile_resolution: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CaseOrgCatalogRow(Base):
    __tablename__ = "case_org_catalog_rows"
    __table_args__ = (
        UniqueConstraint(
            "import_run_id",
            "source_file",
            "source_row_number",
            name="uq_case_org_catalog_rows_source",
        ),
        UniqueConstraint("snapshot_id", "id", name="uq_case_org_catalog_rows_snapshot_id"),
        ForeignKeyConstraint(
            ["snapshot_id", "case_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_org_catalog_rows_org_same_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["import_run_id", "snapshot_id"],
            ["case_import_runs.id", "case_import_runs.snapshot_id"],
            name="fk_case_org_catalog_rows_run_same_snapshot",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "revenue_parse_status IN ('ok', 'error')",
            name="ck_case_org_catalog_rows_revenue_parse",
        ),
        Index("ix_case_org_catalog_rows_org", "snapshot_id", "case_org_id"),
        Index("ix_case_org_catalog_rows_group", "group_external_id"),
        Index("ix_case_org_catalog_rows_content_sha", "row_content_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    import_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    case_org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    org_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    okfs_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_age_years_gradation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    eco_mark_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mainokved_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mainokved_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    negative_mark: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    workers_fns_gradation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workers_spark_gradation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cl_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fts_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fts_country_name_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    factoring_mark: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    revenue_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    revenue_amount: Mapped[Decimal | None] = mapped_column(CASE_MONEY, nullable=True)
    revenue_parse_status: Mapped[str] = mapped_column(String(16), nullable=False)
    revenue_parse_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revenue_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    revenue_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    group_external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class CaseOrgProductMark(Base):
    __tablename__ = "case_org_product_marks"
    __table_args__ = (
        UniqueConstraint("catalog_row_id", "product_code", name="uq_case_org_product_marks_row_code"),
        ForeignKeyConstraint(
            ["snapshot_id", "catalog_row_id"],
            ["case_org_catalog_rows.snapshot_id", "case_org_catalog_rows.id"],
            name="fk_case_org_product_marks_row_same_snapshot",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "product_code IN ('RKO', 'GAR', 'LOA', 'LEA', 'DEP', 'ZPP')",
            name="ck_case_org_product_marks_code",
        ),
        Index("ix_case_org_product_marks_code_mark", "product_code", "mark"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    catalog_row_id: Mapped[str] = mapped_column(String(36), nullable=False)
    product_code: Mapped[str] = mapped_column(String(32), nullable=False)
    mark: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class CaseOrgFieldResolution(Base):
    __tablename__ = "case_org_field_resolution"
    __table_args__ = (
        UniqueConstraint("case_org_id", name="uq_case_org_field_resolution_org"),
        UniqueConstraint("snapshot_id", "case_org_id", name="uq_case_org_field_resolution_snap_org"),
        ForeignKeyConstraint(
            ["snapshot_id", "case_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_org_field_resolution_org_same_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["import_run_id", "snapshot_id"],
            ["case_import_runs.id", "case_import_runs.snapshot_id"],
            name="fk_case_org_field_resolution_run_same_snapshot",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    case_org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    import_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    consensus_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    conflict_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    absent_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    variant_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_field_count: Mapped[int] = mapped_column(Integer, nullable=False)


class CaseOrgGroup(Base):
    __tablename__ = "case_org_groups"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "external_group_id", name="uq_case_org_groups_snapshot_ext"
        ),
        UniqueConstraint("snapshot_id", "id", name="uq_case_org_groups_snapshot_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    external_group_id: Mapped[str] = mapped_column(String(64), nullable=False)


class CaseOrgGroupMember(Base):
    __tablename__ = "case_org_group_members"
    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "case_org_id",
            "catalog_row_id",
            name="uq_case_org_group_members_triple",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "group_id"],
            ["case_org_groups.snapshot_id", "case_org_groups.id"],
            name="fk_case_org_group_members_group_same_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "case_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_org_group_members_org_same_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "catalog_row_id"],
            ["case_org_catalog_rows.snapshot_id", "case_org_catalog_rows.id"],
            name="fk_case_org_group_members_catalog_same_snapshot",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    group_id: Mapped[str] = mapped_column(String(36), nullable=False)
    case_org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    catalog_row_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_conflicted_membership: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CasePayment(Base):
    __tablename__ = "case_payments"
    __table_args__ = (
        UniqueConstraint(
            "import_run_id",
            "source_file",
            "source_row_number",
            name="uq_case_payments_source_row",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "payer_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_payments_payer_same_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "beneficiary_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_payments_beneficiary_same_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["import_run_id", "snapshot_id"],
            ["case_import_runs.id", "case_import_runs.snapshot_id"],
            name="fk_case_payments_run_same_snapshot",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "pay_amt_parse_status IN ('ok', 'error')",
            name="ck_case_payments_pay_amt_parse",
        ),
        CheckConstraint(
            "pay_cnt_parse_status IN ('ok', 'error')",
            name="ck_case_payments_pay_cnt_parse",
        ),
        CheckConstraint("intra_file_dup_rank >= 1", name="ck_case_payments_dup_rank"),
        Index("ix_case_payments_snapshot_payer", "snapshot_id", "payer_org_id"),
        Index("ix_case_payments_snapshot_beneficiary", "snapshot_id", "beneficiary_org_id"),
        Index("ix_case_payments_run_content_sha", "import_run_id", "row_content_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    import_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payer_org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    beneficiary_org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    pay_amt_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    pay_amt: Mapped[Decimal | None] = mapped_column(CASE_MONEY, nullable=True)
    pay_amt_parse_status: Mapped[str] = mapped_column(String(16), nullable=False)
    pay_amt_parse_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pay_cnt_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    pay_cnt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pay_cnt_parse_status: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    amount_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    period_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_self_pay: Mapped[bool] = mapped_column(Boolean, nullable=False)
    intra_file_dup_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    semantics_note: Mapped[str] = mapped_column(
        String(64), nullable=False, default="payment_aggregate_only"
    )


class CasePerson(Base):
    __tablename__ = "case_persons"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "external_fid", name="uq_case_persons_snapshot_fid"),
        UniqueConstraint("snapshot_id", "id", name="uq_case_persons_snapshot_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    external_fid: Mapped[str] = mapped_column(String(64), nullable=False)


class CasePersonOrgLink(Base):
    __tablename__ = "case_person_org_links"
    __table_args__ = (
        UniqueConstraint(
            "import_run_id",
            "source_file",
            "source_row_number",
            name="uq_case_person_org_links_source_row",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "person_id"],
            ["case_persons.snapshot_id", "case_persons.id"],
            name="fk_case_person_org_links_person_same_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "case_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_person_org_links_org_same_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["import_run_id", "snapshot_id"],
            ["case_import_runs.id", "case_import_runs.snapshot_id"],
            name="fk_case_person_org_links_run_same_snapshot",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("case_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    import_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    person_id: Mapped[str] = mapped_column(String(36), nullable=False)
    case_org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    city_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rc_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relation_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="unspecified")
    org_had_catalog_at_import: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CaseOrgCompanyLink(Base):
    """Persistent U_* ↔ Company identity per slot. Does not grant membership."""

    __tablename__ = "case_org_company_links"
    __table_args__ = (
        UniqueConstraint("slot_key", "external_uid", name="uq_case_org_company_links_slot_uid"),
        UniqueConstraint("slot_key", "company_id", name="uq_case_org_company_links_slot_company"),
        Index("ix_case_org_company_links_company", "company_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slot_key: Mapped[str] = mapped_column(String(64), nullable=False)
    external_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    linked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
