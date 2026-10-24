"""Ensure idempotent СеверПром demo data without wiping other users.

Safe to re-run: upserts demo user/company/events/solutions only.
Does not delete unrelated companies, decisions, or conversations.

Usage:
  python -m scripts.ensure_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.core.config import get_settings
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


def _ensure_sqlite_mobile_columns() -> None:
    """Additive DX migration for existing kontur.db (prefs for mobile settings)."""
    settings = get_settings()
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
        }
        if "preferences_json" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN preferences_json "
                    "JSON NOT NULL DEFAULT '{}'"
                )
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
    _ensure_sqlite_mobile_columns()
    seed_main()
    _verify()


if __name__ == "__main__":
    main()
