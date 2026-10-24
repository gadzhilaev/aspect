"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-10-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # For hackathon DX tables are also created via Base.metadata.create_all.
    # This revision documents the intended baseline for Postgres deploys.
    bind = op.get_bind()
    from app.db.base import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    from app.db.base import Base
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=bind)
