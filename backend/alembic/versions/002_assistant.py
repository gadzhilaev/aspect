"""assistant conversations, messages, tool runs

Revision ID: 002
Revises: 001
Create Date: 2026-10-14

Compatible with historical 001 that may already have created these tables
via Base.metadata.create_all (models include assistant_* at import time).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_index(inspector: sa.Inspector, table: str, name: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return any(idx.get("name") == name for idx in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_table(inspector, "assistant_conversations"):
        op.create_table(
            "assistant_conversations",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "company_id", sa.String(length=36), sa.ForeignKey("companies.id"), nullable=False
            ),
            sa.Column("event_id", sa.String(length=64), sa.ForeignKey("events.id"), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
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
        inspector = inspect(bind)

    if not _has_index(inspector, "assistant_conversations", "ix_assistant_conv_user_company_event"):
        op.create_index(
            "ix_assistant_conv_user_company_event",
            "assistant_conversations",
            ["user_id", "company_id", "event_id"],
        )
    if not _has_index(inspector, "assistant_conversations", "ix_assistant_conversations_user_id"):
        op.create_index(
            "ix_assistant_conversations_user_id", "assistant_conversations", ["user_id"]
        )
    if not _has_index(inspector, "assistant_conversations", "ix_assistant_conversations_company_id"):
        op.create_index(
            "ix_assistant_conversations_company_id", "assistant_conversations", ["company_id"]
        )
    if not _has_index(inspector, "assistant_conversations", "ix_assistant_conversations_event_id"):
        op.create_index(
            "ix_assistant_conversations_event_id", "assistant_conversations", ["event_id"]
        )

    inspector = inspect(bind)
    if not _has_table(inspector, "assistant_messages"):
        op.create_table(
            "assistant_messages",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "conversation_id",
                sa.String(length=36),
                sa.ForeignKey("assistant_conversations.id"),
                nullable=False,
            ),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("blocks_json", sa.JSON(), nullable=False),
            sa.Column("client_message_id", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "conversation_id", "client_message_id", name="uq_assistant_msg_client_id"
            ),
        )
        inspector = inspect(bind)

    if not _has_index(inspector, "assistant_messages", "ix_assistant_messages_conversation_id"):
        op.create_index(
            "ix_assistant_messages_conversation_id", "assistant_messages", ["conversation_id"]
        )

    inspector = inspect(bind)
    if not _has_table(inspector, "assistant_tool_runs"):
        op.create_table(
            "assistant_tool_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "conversation_id",
                sa.String(length=36),
                sa.ForeignKey("assistant_conversations.id"),
                nullable=False,
            ),
            sa.Column(
                "message_id",
                sa.String(length=36),
                sa.ForeignKey("assistant_messages.id"),
                nullable=True,
            ),
            sa.Column("tool_name", sa.String(length=64), nullable=False),
            sa.Column("arguments_json", sa.JSON(), nullable=False),
            sa.Column("result_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "conversation_id",
                "idempotency_key",
                name="uq_assistant_tool_idempotency",
            ),
        )
        inspector = inspect(bind)

    if not _has_index(inspector, "assistant_tool_runs", "ix_assistant_tool_runs_conversation_id"):
        op.create_index(
            "ix_assistant_tool_runs_conversation_id",
            "assistant_tool_runs",
            ["conversation_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _has_table(inspector, "assistant_tool_runs"):
        op.drop_table("assistant_tool_runs")
    if _has_table(inspector, "assistant_messages"):
        op.drop_table("assistant_messages")
    if _has_table(inspector, "assistant_conversations"):
        op.drop_table("assistant_conversations")
