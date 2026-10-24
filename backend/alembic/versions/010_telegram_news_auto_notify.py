"""Telegram news auto-notify watermark (TG-4).

Revision ID: 010
Revises: 009
Create Date: 2026-10-24

Adds notification_subscriptions.auto_notify_since — watermark for automatic
news notifications (no archive backfill on connect / re-enable).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(inspector: sa.Inspector, table: str) -> set[str]:
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = _cols(inspector, "notification_subscriptions")
    if not cols:
        return
    if "auto_notify_since" not in cols:
        op.add_column(
            "notification_subscriptions",
            sa.Column("auto_notify_since", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = _cols(inspector, "notification_subscriptions")
    if "auto_notify_since" in cols:
        op.drop_column("notification_subscriptions", "auto_notify_since")
