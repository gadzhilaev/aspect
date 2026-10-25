#!/usr/bin/env python3
"""Read-only quality metrics snapshot from a stand SQLite DB (K12).

Usage:
  python scripts/quality_metrics_snapshot.py --db /path/to/stand.db
  python scripts/quality_metrics_snapshot.py --db stand.db --json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> int:
    try:
        row = conn.execute(sql, args).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0


def snapshot(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        companies = _count(conn, "SELECT COUNT(*) FROM companies") if _table_exists(conn, "companies") else 0
        events = _count(conn, "SELECT COUNT(*) FROM events") if _table_exists(conn, "events") else 0
        impacts = (
            _count(conn, "SELECT COUNT(*) FROM event_impacts")
            if _table_exists(conn, "event_impacts")
            else 0
        )
        bank_docs = (
            _count(conn, "SELECT COUNT(*) FROM bank_documents")
            if _table_exists(conn, "bank_documents")
            else 0
        )
        bank_frags = (
            _count(conn, "SELECT COUNT(*) FROM bank_fragments")
            if _table_exists(conn, "bank_fragments")
            else 0
        )
        # Heuristic: fragments marked eligible for AI evidence if column exists.
        ai_eligible = 0
        if _table_exists(conn, "bank_fragments"):
            cols = {r[1] for r in conn.execute("PRAGMA table_info(bank_fragments)").fetchall()}
            if "eligibility_json" in cols:
                ai_eligible = _count(
                    conn,
                    "SELECT COUNT(*) FROM bank_fragments WHERE eligibility_json LIKE '%ai_evidence%'"
                    " OR eligibility_json LIKE '%eligible_ai%'",
                )
            elif "eligible_ai_evidence" in cols:
                ai_eligible = _count(
                    conn,
                    "SELECT COUNT(*) FROM bank_fragments WHERE eligible_ai_evidence = 1",
                )

        tool_runs = (
            _count(conn, "SELECT COUNT(*) FROM assistant_tool_runs")
            if _table_exists(conn, "assistant_tool_runs")
            else 0
        )
        messages = (
            _count(conn, "SELECT COUNT(*) FROM assistant_messages")
            if _table_exists(conn, "assistant_messages")
            else 0
        )
        memberships = (
            _count(conn, "SELECT COUNT(*) FROM company_memberships")
            if _table_exists(conn, "company_memberships")
            else 0
        )

        impact_coverage = round(impacts / events, 4) if events else None
        bank_per_doc = round(bank_frags / bank_docs, 4) if bank_docs else None

        return {
            "db": str(db_path),
            "counts": {
                "companies": companies,
                "memberships": memberships,
                "events": events,
                "event_impacts": impacts,
                "bank_documents": bank_docs,
                "bank_fragments": bank_frags,
                "bank_fragments_ai_eligible_heuristic": ai_eligible,
                "assistant_messages": messages,
                "assistant_tool_runs": tool_runs,
            },
            "derived": {
                "M1_impact_rows_per_event": impact_coverage,
                "M2_fragments_per_document": bank_per_doc,
                "M3_tool_runs_present": tool_runs > 0,
                "M4_events_present_for_feed": events > 0,
                "note": (
                    "Feed inclusion_bases and bank citation labels need API/export; "
                    "this snapshot is DB-level proxies for K12 ops."
                ),
            },
        }
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True, type=Path, help="Path to stand.db / kontur.db")
    p.add_argument("--json", action="store_true", help="Print JSON only")
    args = p.parse_args()
    if not args.db.is_file():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 2
    data = snapshot(args.db)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print("quality_metrics_snapshot")
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
