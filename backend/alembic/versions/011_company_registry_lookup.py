"""Company registry lookup cache (external INN lookup confirmation).

Revision ID: 011
Revises: 010
Create Date: 2026-10-24

Adds company_registry_lookups — short-lived, user-bound store of normalized
public candidates so confirmation can trust provenance server-side.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "company_registry_lookups" in inspector.get_table_names():
        return
    op.create_table(
        "company_registry_lookups",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("inn", sa.String(length=32), nullable=False),
        sa.Column("candidates_json", sa.JSON(), nullable=False),
        sa.Column("source_actuality_date", sa.String(length=32), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_company_registry_lookups_user", "company_registry_lookups", ["user_id"]
    )
    op.create_index(
        "ix_company_registry_lookups_inn", "company_registry_lookups", ["inn"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "company_registry_lookups" not in inspector.get_table_names():
        return
    existing = {ix["name"] for ix in inspector.get_indexes("company_registry_lookups")}
    if "ix_company_registry_lookups_inn" in existing:
        op.drop_index("ix_company_registry_lookups_inn", table_name="company_registry_lookups")
    if "ix_company_registry_lookups_user" in existing:
        op.drop_index("ix_company_registry_lookups_user", table_name="company_registry_lookups")
    op.drop_table("company_registry_lookups")
