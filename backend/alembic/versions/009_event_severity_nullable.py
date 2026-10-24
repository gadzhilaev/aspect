"""Allow nullable event.severity (unknown significance).

Revision ID: 009
Revises: 008
Create Date: 2026-10-24

Does not rewrite row values; existing floats remain. None means
significance not established — consumers must not coerce to 0.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.alter_column(
            "severity",
            existing_type=sa.Float(),
            nullable=True,
        )


def downgrade() -> None:
    # Fill nulls before tightening — unknown → leave as null only if dialect allows;
    # SQLite batch recreate may need a sentinel. Prefer soft downgrade no-op on SQLite.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(sa.text("UPDATE events SET severity = 50 WHERE severity IS NULL"))
    with op.batch_alter_table("events") as batch:
        batch.alter_column(
            "severity",
            existing_type=sa.Float(),
            nullable=False,
        )
