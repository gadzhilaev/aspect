"""telegram outbox subscription binding + kind (TG-2)

Revision ID: 008
Revises: 007
Create Date: 2026-10-24

Adds subscription_id and kind on notification_outbox for safe re-check
before send. Does not drop legacy rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(inspector: sa.Inspector, table: str) -> set[str]:
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = _cols(inspector, "notification_outbox")
    if not cols:
        return
    if "subscription_id" not in cols:
        op.add_column(
            "notification_outbox",
            sa.Column("subscription_id", sa.String(length=36), nullable=True),
        )
        # Soft FK — table may exist without constraint in older create_all DBs
        try:
            op.create_foreign_key(
                "fk_outbox_subscription_id",
                "notification_outbox",
                "notification_subscriptions",
                ["subscription_id"],
                ["id"],
            )
        except Exception:  # noqa: BLE001
            pass
        op.create_index(
            "ix_notification_outbox_subscription_id",
            "notification_outbox",
            ["subscription_id"],
        )
    if "kind" not in cols:
        op.add_column(
            "notification_outbox",
            sa.Column(
                "kind",
                sa.String(length=32),
                nullable=False,
                server_default="impact",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = _cols(inspector, "notification_outbox")
    if not cols:
        return

    # SQLite: plain DROP COLUMN fails when FK still names the column; batch
    # recreate must drop FK/index that reference subscription_id first.
    if bind.dialect.name == "sqlite":
        fk_names = {
            fk.get("name")
            for fk in inspector.get_foreign_keys("notification_outbox")
            if fk.get("name")
        }
        idx_names = {
            idx.get("name")
            for idx in inspector.get_indexes("notification_outbox")
            if idx.get("name")
        }
        with op.batch_alter_table("notification_outbox") as batch:
            if "subscription_id" in cols:
                if "fk_outbox_subscription_id" in fk_names:
                    batch.drop_constraint(
                        "fk_outbox_subscription_id", type_="foreignkey"
                    )
                if "ix_notification_outbox_subscription_id" in idx_names:
                    batch.drop_index("ix_notification_outbox_subscription_id")
                batch.drop_column("subscription_id")
            if "kind" in cols:
                batch.drop_column("kind")
        return

    if "kind" in cols:
        op.drop_column("notification_outbox", "kind")
    if "subscription_id" in cols:
        try:
            op.drop_constraint(
                "fk_outbox_subscription_id", "notification_outbox", type_="foreignkey"
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            op.drop_index(
                "ix_notification_outbox_subscription_id",
                table_name="notification_outbox",
            )
        except Exception:  # noqa: BLE001
            pass
        op.drop_column("notification_outbox", "subscription_id")