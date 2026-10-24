"""case data layer (competition snapshots)

Revision ID: 006
Revises: 005
Create Date: 2026-10-20

Creates case_* tables only. No seed/demo/competition row data.
Does not mutate companies or memberships.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CASE_TABLES = [
    "case_org_company_links",
    "case_person_org_links",
    "case_persons",
    "case_payments",
    "case_org_group_members",
    "case_org_groups",
    "case_org_field_resolution",
    "case_org_product_marks",
    "case_org_catalog_rows",
    "case_org",
    "case_import_files",
    "case_active_snapshot",
    "case_import_runs",
    "case_snapshots",
]


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _has_table(inspector, "case_snapshots"):
        return

    op.create_table(
        "case_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slot_key", sa.String(length=64), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("version_seq", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("import_run_id", sa.String(length=36), nullable=True),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_report_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("slot_key", "version_seq", name="uq_case_snapshots_slot_version_seq"),
        sa.UniqueConstraint(
            "slot_key", "version_label", name="uq_case_snapshots_slot_version_label"
        ),
        sa.UniqueConstraint("id", "slot_key", name="uq_case_snapshots_id_slot"),
        sa.CheckConstraint(
            "status IN ('building', 'ready', 'active', 'retired', 'failed')",
            name="ck_case_snapshots_status",
        ),
        sa.CheckConstraint("version_seq >= 1", name="ck_case_snapshots_version_seq"),
    )
    op.create_index("ix_case_snapshots_slot_status", "case_snapshots", ["slot_key", "status"])
    op.execute(
        "CREATE UNIQUE INDEX uq_case_snapshots_one_active_per_slot "
        "ON case_snapshots (slot_key) WHERE status = 'active'"
    )

    op.create_table(
        "case_import_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_by", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("resume_cursor_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["case_snapshots.id"], name="fk_case_import_runs_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("snapshot_id", name="uq_case_import_runs_snapshot"),
        sa.UniqueConstraint("id", "snapshot_id", name="uq_case_import_runs_id_snapshot"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'identical_skip')",
            name="ck_case_import_runs_status",
        ),
    )
    op.create_index("ix_case_import_runs_status", "case_import_runs", ["status"])

    # SQLite cannot ALTER ADD CONSTRAINT; use batch copy-and-move.
    with op.batch_alter_table("case_snapshots") as batch:
        batch.create_foreign_key(
            "fk_case_snapshots_import_run",
            "case_import_runs",
            ["import_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "case_active_snapshot",
        sa.Column("slot_key", sa.String(length=64), primary_key=True),
        sa.Column("active_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["slot_key", "active_snapshot_id"],
            ["case_snapshots.slot_key", "case_snapshots.id"],
            name="fk_case_active_snapshot_same_slot",
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "case_import_files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("import_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("row_count_declared", sa.Integer(), nullable=True),
        sa.Column("row_count_loaded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_row_number", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["case_import_runs.id"],
            name="fk_case_import_files_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("import_run_id", "source_file", name="uq_case_import_files_run_file"),
        sa.CheckConstraint(
            "status IN ('pending', 'loading', 'completed', 'failed')",
            name="ck_case_import_files_status",
        ),
    )
    op.create_index(
        "ix_case_import_files_content_sha256", "case_import_files", ["content_sha256"]
    )

    op.create_table(
        "case_org",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("external_uid", sa.String(length=64), nullable=False),
        sa.Column("has_catalog_profile", sa.Boolean(), nullable=False),
        sa.Column("profile_resolution", sa.String(length=32), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["case_snapshots.id"], name="fk_case_org_snapshot", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("snapshot_id", "external_uid", name="uq_case_org_snapshot_uid"),
        sa.UniqueConstraint("snapshot_id", "id", name="uq_case_org_snapshot_id"),
        sa.CheckConstraint(
            "profile_resolution IN ('absent', 'single', 'consensus', 'conflict')",
            name="ck_case_org_profile_resolution",
        ),
    )
    op.create_index(
        "ix_case_org_snapshot_has_catalog", "case_org", ["snapshot_id", "has_catalog_profile"]
    )
    op.create_index(
        "ix_case_org_snapshot_resolution", "case_org", ["snapshot_id", "profile_resolution"]
    )

    op.create_table(
        "case_org_catalog_rows",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("import_run_id", sa.String(length=36), nullable=False),
        sa.Column("case_org_id", sa.String(length=36), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("row_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("org_type", sa.String(length=64), nullable=True),
        sa.Column("okfs_name", sa.String(length=255), nullable=True),
        sa.Column("company_age_years_gradation", sa.String(length=32), nullable=True),
        sa.Column("eco_mark_label", sa.String(length=128), nullable=True),
        sa.Column("mainokved_code", sa.String(length=32), nullable=True),
        sa.Column("mainokved_name", sa.String(length=512), nullable=True),
        sa.Column("negative_mark", sa.Boolean(), nullable=True),
        sa.Column("workers_fns_gradation", sa.String(length=64), nullable=True),
        sa.Column("workers_spark_gradation", sa.String(length=64), nullable=True),
        sa.Column("cl_type", sa.String(length=32), nullable=True),
        sa.Column("fts_flag", sa.Boolean(), nullable=True),
        sa.Column("fts_country_name_raw", sa.Text(), nullable=True),
        sa.Column("factoring_mark", sa.Boolean(), nullable=True),
        sa.Column("revenue_raw", sa.String(length=64), nullable=False),
        sa.Column("revenue_amount", sa.Numeric(20, 1), nullable=True),
        sa.Column("revenue_parse_status", sa.String(length=16), nullable=False),
        sa.Column("revenue_parse_error", sa.String(length=255), nullable=True),
        sa.Column("revenue_unit", sa.String(length=32), nullable=True),
        sa.Column("revenue_currency", sa.String(length=3), nullable=True),
        sa.Column("group_external_id", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("region", sa.String(length=255), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["case_snapshots.id"],
            name="fk_case_org_catalog_rows_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "case_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_org_catalog_rows_org_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id", "snapshot_id"],
            ["case_import_runs.id", "case_import_runs.snapshot_id"],
            name="fk_case_org_catalog_rows_run_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_run_id",
            "source_file",
            "source_row_number",
            name="uq_case_org_catalog_rows_source",
        ),
        sa.UniqueConstraint(
            "snapshot_id", "id", name="uq_case_org_catalog_rows_snapshot_id"
        ),
        sa.CheckConstraint(
            "revenue_parse_status IN ('ok', 'error')",
            name="ck_case_org_catalog_rows_revenue_parse",
        ),
    )
    op.create_index(
        "ix_case_org_catalog_rows_org", "case_org_catalog_rows", ["snapshot_id", "case_org_id"]
    )
    op.create_index(
        "ix_case_org_catalog_rows_group", "case_org_catalog_rows", ["group_external_id"]
    )
    op.create_index(
        "ix_case_org_catalog_rows_content_sha", "case_org_catalog_rows", ["row_content_sha256"]
    )

    op.create_table(
        "case_org_product_marks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("catalog_row_id", sa.String(length=36), nullable=False),
        sa.Column("product_code", sa.String(length=32), nullable=False),
        sa.Column("mark", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["case_snapshots.id"],
            name="fk_case_org_product_marks_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "catalog_row_id"],
            ["case_org_catalog_rows.snapshot_id", "case_org_catalog_rows.id"],
            name="fk_case_org_product_marks_row_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "catalog_row_id", "product_code", name="uq_case_org_product_marks_row_code"
        ),
        sa.CheckConstraint(
            "product_code IN ('RKO', 'GAR', 'LOA', 'LEA', 'DEP', 'ZPP')",
            name="ck_case_org_product_marks_code",
        ),
    )
    op.create_index(
        "ix_case_org_product_marks_code_mark",
        "case_org_product_marks",
        ["product_code", "mark"],
    )

    op.create_table(
        "case_org_field_resolution",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("case_org_id", sa.String(length=36), nullable=False),
        sa.Column("import_run_id", sa.String(length=36), nullable=False),
        sa.Column("consensus_json", sa.JSON(), nullable=False),
        sa.Column("conflict_json", sa.JSON(), nullable=False),
        sa.Column("absent_json", sa.JSON(), nullable=False),
        sa.Column("variant_count", sa.Integer(), nullable=False),
        sa.Column("confirmed_field_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["case_snapshots.id"],
            name="fk_case_org_field_resolution_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "case_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_org_field_resolution_org_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id", "snapshot_id"],
            ["case_import_runs.id", "case_import_runs.snapshot_id"],
            name="fk_case_org_field_resolution_run_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("case_org_id", name="uq_case_org_field_resolution_org"),
        sa.UniqueConstraint(
            "snapshot_id", "case_org_id", name="uq_case_org_field_resolution_snap_org"
        ),
    )

    op.create_table(
        "case_org_groups",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("external_group_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["case_snapshots.id"],
            name="fk_case_org_groups_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "snapshot_id", "external_group_id", name="uq_case_org_groups_snapshot_ext"
        ),
        sa.UniqueConstraint("snapshot_id", "id", name="uq_case_org_groups_snapshot_id"),
    )

    op.create_table(
        "case_org_group_members",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("case_org_id", sa.String(length=36), nullable=False),
        sa.Column("catalog_row_id", sa.String(length=36), nullable=True),
        sa.Column("is_conflicted_membership", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["case_snapshots.id"],
            name="fk_case_org_group_members_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "group_id"],
            ["case_org_groups.snapshot_id", "case_org_groups.id"],
            name="fk_case_org_group_members_group_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "case_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_org_group_members_org_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "catalog_row_id"],
            ["case_org_catalog_rows.snapshot_id", "case_org_catalog_rows.id"],
            name="fk_case_org_group_members_catalog_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "group_id",
            "case_org_id",
            "catalog_row_id",
            name="uq_case_org_group_members_triple",
        ),
    )

    op.create_table(
        "case_payments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("import_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("row_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("payer_org_id", sa.String(length=36), nullable=False),
        sa.Column("beneficiary_org_id", sa.String(length=36), nullable=False),
        sa.Column("pay_amt_raw", sa.String(length=64), nullable=False),
        sa.Column("pay_amt", sa.Numeric(20, 1), nullable=True),
        sa.Column("pay_amt_parse_status", sa.String(length=16), nullable=False),
        sa.Column("pay_amt_parse_error", sa.String(length=255), nullable=True),
        sa.Column("pay_cnt_raw", sa.String(length=64), nullable=False),
        sa.Column("pay_cnt", sa.Integer(), nullable=True),
        sa.Column("pay_cnt_parse_status", sa.String(length=16), nullable=False),
        sa.Column("amount_unit", sa.String(length=32), nullable=True),
        sa.Column("amount_currency", sa.String(length=3), nullable=True),
        sa.Column("period_label", sa.String(length=64), nullable=True),
        sa.Column("is_self_pay", sa.Boolean(), nullable=False),
        sa.Column("intra_file_dup_rank", sa.Integer(), nullable=False),
        sa.Column(
            "semantics_note",
            sa.String(length=64),
            nullable=False,
            server_default="payment_aggregate_only",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["case_snapshots.id"],
            name="fk_case_payments_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "payer_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_payments_payer_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "beneficiary_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_payments_beneficiary_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id", "snapshot_id"],
            ["case_import_runs.id", "case_import_runs.snapshot_id"],
            name="fk_case_payments_run_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_run_id",
            "source_file",
            "source_row_number",
            name="uq_case_payments_source_row",
        ),
        sa.CheckConstraint(
            "pay_amt_parse_status IN ('ok', 'error')",
            name="ck_case_payments_pay_amt_parse",
        ),
        sa.CheckConstraint(
            "pay_cnt_parse_status IN ('ok', 'error')",
            name="ck_case_payments_pay_cnt_parse",
        ),
        sa.CheckConstraint("intra_file_dup_rank >= 1", name="ck_case_payments_dup_rank"),
    )
    op.create_index(
        "ix_case_payments_snapshot_payer", "case_payments", ["snapshot_id", "payer_org_id"]
    )
    op.create_index(
        "ix_case_payments_snapshot_beneficiary",
        "case_payments",
        ["snapshot_id", "beneficiary_org_id"],
    )
    op.create_index(
        "ix_case_payments_run_content_sha",
        "case_payments",
        ["import_run_id", "row_content_sha256"],
    )

    op.create_table(
        "case_persons",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("external_fid", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["case_snapshots.id"],
            name="fk_case_persons_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("snapshot_id", "external_fid", name="uq_case_persons_snapshot_fid"),
        sa.UniqueConstraint("snapshot_id", "id", name="uq_case_persons_snapshot_id"),
    )

    op.create_table(
        "case_person_org_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("import_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.Column("case_org_id", sa.String(length=36), nullable=False),
        sa.Column("city_name", sa.String(length=255), nullable=True),
        sa.Column("rc_name", sa.String(length=255), nullable=True),
        sa.Column(
            "relation_kind",
            sa.String(length=32),
            nullable=False,
            server_default="unspecified",
        ),
        sa.Column("org_had_catalog_at_import", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["case_snapshots.id"],
            name="fk_case_person_org_links_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "person_id"],
            ["case_persons.snapshot_id", "case_persons.id"],
            name="fk_case_person_org_links_person_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "case_org_id"],
            ["case_org.snapshot_id", "case_org.id"],
            name="fk_case_person_org_links_org_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id", "snapshot_id"],
            ["case_import_runs.id", "case_import_runs.snapshot_id"],
            name="fk_case_person_org_links_run_same_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_run_id",
            "source_file",
            "source_row_number",
            name="uq_case_person_org_links_source_row",
        ),
    )

    op.create_table(
        "case_org_company_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slot_key", sa.String(length=64), nullable=False),
        sa.Column("external_uid", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("linked_by", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_case_org_company_links_company",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "slot_key", "external_uid", name="uq_case_org_company_links_slot_uid"
        ),
        sa.UniqueConstraint(
            "slot_key", "company_id", name="uq_case_org_company_links_slot_company"
        ),
    )
    op.create_index(
        "ix_case_org_company_links_company", "case_org_company_links", ["company_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if bind.dialect.name == "sqlite":
        # SQLite cannot drop a single FK cleanly; disable checks for teardown.
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    elif "case_snapshots" in existing:
        op.drop_constraint(
            "fk_case_snapshots_import_run", "case_snapshots", type_="foreignkey"
        )

    for name in CASE_TABLES:
        if name in existing:
            op.drop_table(name)
