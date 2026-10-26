"""Support thread handler (ai | operator).

Revision ID: 014
Revises: 013
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "support_threads" not in set(inspector.get_table_names()):
        return
    cols = {c["name"] for c in inspector.get_columns("support_threads")}
    if "handler" in cols:
        return
    with op.batch_alter_table("support_threads") as batch:
        batch.add_column(
            sa.Column(
                "handler",
                sa.String(length=32),
                nullable=False,
                server_default="ai",
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "support_threads" not in set(inspector.get_table_names()):
        return
    cols = {c["name"] for c in inspector.get_columns("support_threads")}
    if "handler" not in cols:
        return
    with op.batch_alter_table("support_threads") as batch:
        batch.drop_column("handler")
