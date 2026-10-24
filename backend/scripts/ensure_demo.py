"""Ensure idempotent СеверПром demo data without wiping other users.

Safe to re-run: upserts demo user/company/events/solutions only.
Does not delete unrelated companies, decisions, or conversations.

Requires schema at Alembic head (incl. 012 preferences_json). Run first:
  alembic upgrade head

Usage:
  python -m scripts.ensure_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect

from app.db.session import SessionLocal, engine
from app.models import Event, EventImpact
from app.services.impact import assessment_state_for_impact
from scripts.seed_demo import (
    COMPANY_ID,
    DEMO_PASSWORD,
    DEMO_USER_EMAIL,
    EVENT_EXPORT,
    main as seed_main,
)


def _require_preferences_column() -> None:
    """Fail fast if mobile migration 012 was not applied (no silent ALTER)."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        raise SystemExit(
            "FAIL: table users missing — run `alembic upgrade head` (or start API once "
            "on empty SQLite so metadata create_all runs, then alembic stamp/upgrade)."
        )
    cols = {c["name"] for c in insp.get_columns("users")}
    if "preferences_json" not in cols:
        raise SystemExit(
            "FAIL: users.preferences_json missing — apply Alembic revision 012:\n"
            "  alembic upgrade head"
        )


def _verify() -> None:
    db = SessionLocal()
    try:
        event = db.get(Event, EVENT_EXPORT)
        if event is None:
            raise SystemExit(f"FAIL: missing event {EVENT_EXPORT}")
        impact = (
            db.query(EventImpact)
            .filter(
                EventImpact.event_id == EVENT_EXPORT,
                EventImpact.company_id == COMPANY_ID,
            )
            .first()
        )
        if impact is None:
            raise SystemExit("FAIL: missing China impact for СеверПром")
        state = assessment_state_for_impact(db, event, impact)
        print("OK Demo ready")
        print(f"  login:   {DEMO_USER_EMAIL} / {DEMO_PASSWORD}")
        print(f"  company: {COMPANY_ID}")
        print(f"  event:   {EVENT_EXPORT} ({event.title})")
        print(f"  impact:  assessment_state={state}")
        if state != "supply_chain_ready":
            raise SystemExit(
                f"FAIL: expected supply_chain_ready for China event, got {state}"
            )
        print("  path:    /login -> /news/for-you -> news -> impact -> assistant -> decision")
    finally:
        db.close()


def main() -> None:
    _require_preferences_column()
    seed_main()
    _verify()


if __name__ == "__main__":
    main()
