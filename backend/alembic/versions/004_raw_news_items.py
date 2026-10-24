"""raw_news_items for signal ingestion

Revision ID: 004
Revises: 003
Create Date: 2026-10-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _has_table(inspector, "raw_news_items"):
        return

    op.create_table(
        "raw_news_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("canonical_url", sa.String(length=1024), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("event_id", sa.String(length=64), sa.ForeignKey("events.id"), nullable=True),
        sa.Column("cluster_key", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("provider", "external_id", name="uq_raw_news_provider_external"),
        sa.UniqueConstraint("canonical_url", name="uq_raw_news_canonical_url"),
    )
    op.create_index("ix_raw_news_items_provider", "raw_news_items", ["provider"])
    op.create_index("ix_raw_news_items_content_hash", "raw_news_items", ["content_hash"])
    op.create_index("ix_raw_news_items_processing_status", "raw_news_items", ["processing_status"])
    op.create_index("ix_raw_news_items_event_id", "raw_news_items", ["event_id"])
    op.create_index("ix_raw_news_items_cluster_key", "raw_news_items", ["cluster_key"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not _has_table(inspector, "raw_news_items"):
        return
    op.drop_table("raw_news_items")
