"""unique decision per scenario

Revision ID: 003
Revises: 002
Create Date: 2026-10-14

One Decision per Scenario — closes concurrent confirm race.
Compatible with DBs that already have the unique index via create_all.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "uq_decisions_scenario_id"


def _has_unique_on_scenario(inspector: sa.Inspector) -> bool:
    if "decisions" not in inspector.get_table_names():
        return False
    for uq in inspector.get_unique_constraints("decisions"):
        if uq.get("name") == CONSTRAINT_NAME:
            return True
        cols = uq.get("column_names") or []
        if cols == ["scenario_id"]:
            return True
    # SQLite may expose unique indexes instead of constraints
    for idx in inspector.get_indexes("decisions"):
        if idx.get("unique") and (idx.get("column_names") or []) == ["scenario_id"]:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "decisions" not in inspector.get_table_names():
        return
    if _has_unique_on_scenario(inspector):
        return

    # Keep oldest decision per scenario if duplicates somehow exist
    bind.execute(
        text(
            """
            DELETE FROM action_items
            WHERE decision_id IN (
                SELECT d.id FROM decisions d
                WHERE d.id NOT IN (
                    SELECT MIN(d2.id) FROM decisions d2 GROUP BY d2.scenario_id
                )
            )
            """
        )
    )
    bind.execute(
        text(
            """
            DELETE FROM decisions
            WHERE id NOT IN (
                SELECT MIN(id) FROM decisions GROUP BY scenario_id
            )
            """
        )
    )

    with op.batch_alter_table("decisions") as batch:
        batch.create_unique_constraint(CONSTRAINT_NAME, ["scenario_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not _has_unique_on_scenario(inspector):
        return
    with op.batch_alter_table("decisions") as batch:
        batch.drop_constraint(CONSTRAINT_NAME, type_="unique")
