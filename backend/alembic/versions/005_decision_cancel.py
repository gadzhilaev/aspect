"""decision cancel fields

Revision ID: 005
Revises: 004
Create Date: 2026-10-19

Adds cancelled_at, cancelled_by_user_id, cancel_reason.
Does not delete or rewrite existing decisions.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = _columns(inspector, "decisions")
    if not cols:
        return

    # SQLite batch: add nullable columns without inline FK (ORM still declares FK).
    with op.batch_alter_table("decisions") as batch:
        if "cancelled_at" not in cols:
            batch.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        if "cancelled_by_user_id" not in cols:
            batch.add_column(sa.Column("cancelled_by_user_id", sa.String(length=36), nullable=True))
        if "cancel_reason" not in cols:
            batch.add_column(sa.Column("cancel_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = _columns(inspector, "decisions")
    if not cols:
        return
    with op.batch_alter_table("decisions") as batch:
        if "cancel_reason" in cols:
            batch.drop_column("cancel_reason")
        if "cancelled_by_user_id" in cols:
            batch.drop_column("cancelled_by_user_id")
        if "cancelled_at" in cols:
            batch.drop_column("cancelled_at")
