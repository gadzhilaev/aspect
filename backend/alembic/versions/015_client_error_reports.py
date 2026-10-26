"""Client error reports from mobile/web.

Revision ID: 015
Revises: 014
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "client_error_reports" in set(inspector.get_table_names()):
        return
    op.create_table(
        "client_error_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("screen", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("exception_type", sa.String(length=255), nullable=True),
        sa.Column("stack", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("http_code", sa.String(length=64), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("app_version", sa.String(length=64), nullable=True),
        sa.Column("platform", sa.String(length=64), nullable=True),
        sa.Column("device_info", sa.String(length=512), nullable=True),
        sa.Column("email_attempted", sa.String(length=320), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_client_error_reports_created_at",
        "client_error_reports",
        ["created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "client_error_reports" not in set(inspector.get_table_names()):
        return
    op.drop_index("ix_client_error_reports_created_at", table_name="client_error_reports")
    op.drop_table("client_error_reports")
