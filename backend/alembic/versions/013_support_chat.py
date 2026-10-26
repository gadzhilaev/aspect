"""Support chat threads and messages.

Revision ID: 013
Revises: 012
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "support_threads" not in tables:
        op.create_table(
            "support_threads",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "company_id",
                sa.String(length=36),
                sa.ForeignKey("companies.id"),
                nullable=True,
            ),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column("subject", sa.String(length=255), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_support_threads_user_id", "support_threads", ["user_id"])
        op.create_index("ix_support_threads_company_id", "support_threads", ["company_id"])
        op.create_index(
            "ix_support_threads_user_status",
            "support_threads",
            ["user_id", "status"],
        )

    if "support_messages" not in tables:
        op.create_table(
            "support_messages",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "thread_id",
                sa.String(length=36),
                sa.ForeignKey("support_threads.id"),
                nullable=False,
            ),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("client_message_id", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "thread_id",
                "client_message_id",
                name="uq_support_msg_client_id",
            ),
        )
        op.create_index("ix_support_messages_thread_id", "support_messages", ["thread_id"])
        op.create_index(
            "ix_support_messages_thread_created",
            "support_messages",
            ["thread_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "support_messages" in tables:
        op.drop_table("support_messages")
    if "support_threads" in tables:
        op.drop_table("support_threads")
