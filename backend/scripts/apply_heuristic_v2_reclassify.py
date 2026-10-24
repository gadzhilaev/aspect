# -*- coding: utf-8 -*-
"""Apply heuristic_v2 reclassification to the main real_news_613 stand.

Safety:
- SQLite backup API before write
- Only heuristic classification fields (+ match tags derived by heuristic)
- Skip demo events and locked / non-heuristic classifications
- Mark related EventImpact rows as classification-stale (no mass recompute)
- Do not touch messages, scenarios, decisions, Telegram/outbox
- Idempotent: second run is a no-op when already at heuristic_v2 result

Usage:
  python scripts/apply_heuristic_v2_reclassify.py --preview
  python scripts/apply_heuristic_v2_reclassify.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_DB = ROOT / "data/competition_stand/real_news_613/stand.db"
BACKUP_DIR = ROOT / "data/competition_stand/real_news_613/backups"
REPORT_DIR = ROOT / "data/competition_stand/reclassify_applied"
HEURISTIC_VERSION = "heuristic_v2"

# Fields we may rewrite on Event (classification + heuristic match tags only).
CLASSIFICATION_FIELDS = (
    "category",
    "event_type",
    "severity",
    "match_categories_json",
    "match_countries_json",
    "match_currencies_json",
    "match_materials_json",
)


def _sqlite_backup(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    s = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()
    return hashlib.sha256(dst.read_bytes()).hexdigest()


def _alembic_version(db_path: Path) -> str | None:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    finally:
        con.close()


def _severity_nullable(db_path: Path) -> bool:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        cols = con.execute("PRAGMA table_info(events)").fetchall()
        for col in cols:
            # cid, name, type, notnull, dflt, pk
            if col[1] == "severity":
                return col[3] == 0  # notnull == 0 → nullable
        return False
    finally:
        con.close()


def _is_locked_classification(attrs: dict | None) -> bool:
    """Skip human / verified / locked classifications — never overwrite."""
    a = attrs or {}
    if a.get("classification_locked") or a.get("manual_classification"):
        return True
    cls = a.get("classification") or {}
    if not isinstance(cls, dict):
        return False
    if cls.get("locked") or cls.get("verified") or cls.get("manual"):
        return True
    basis = str(cls.get("basis") or "")
    # Allow rewrite of old heuristic / missing / v1; skip other bases (e.g. live LLM if marked).
    if basis and basis not in {
        "heuristic",
        "heuristic_v1",
        "heuristic_v2",
        "fallback_heuristic",
    }:
        return True
    return False


def _norm_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    return []


def _same_sev(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return float(a) == float(b)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="Print plan only")
    parser.add_argument("--apply", action="store_true", help="Write main stand DB")
    parser.add_argument("--limit", type=int, default=2000)
    args = parser.parse_args()
    if not args.preview and not args.apply:
        parser.error("Specify --preview and/or --apply")

    assert MAIN_DB.is_file(), MAIN_DB
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    db_path = MAIN_DB.resolve()
    alembic_rev = _alembic_version(MAIN_DB)
    sev_nullable = _severity_nullable(MAIN_DB)
    print(
        json.dumps(
            {
                "db_path": str(db_path).replace("\\", "/"),
                "db_size_bytes": MAIN_DB.stat().st_size,
                "alembic_version": alembic_rev,
                "severity_nullable": sev_nullable,
                "heuristic_version": HEURISTIC_VERSION,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if alembic_rev != "009":
        print("ERROR: expected alembic 009 before apply", file=sys.stderr)
        return 2
    if not sev_nullable:
        print("ERROR: events.severity must be nullable (migration 009)", file=sys.stderr)
        return 2

    backup_path = None
    backup_sha = None
    if args.apply:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = BACKUP_DIR / f"stand_pre_heuristic_v2_{stamp}.db"
        backup_sha = _sqlite_backup(MAIN_DB, backup_path)
        print(
            json.dumps(
                {
                    "backup": str(backup_path.relative_to(ROOT)).replace("\\", "/"),
                    "backup_sha256": backup_sha,
                },
                ensure_ascii=False,
            )
        )

    # Point app session at main stand (same path API :8020 uses).
    os.environ["DATABASE_URL"] = "sqlite:///./data/competition_stand/real_news_613/stand.db"
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("SECRET_KEY", "reclassify-apply-main")
    os.environ["ASSISTANT_PROVIDER"] = "mock"
    os.environ["COMPETITION_MODE"] = "false"

    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models import Event, EventImpact
    from app.models.raw_news import RawNewsItem
    from app.services.ingestion.enrich import heuristic_enrich

    get_settings.cache_clear()
    engine.dispose()

    db = SessionLocal()
    changes: list[dict] = []
    skipped_locked = 0
    skipped_no_raw = 0
    unchanged = 0
    errors: list[str] = []
    impact_stale_ids: list[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    events = (
        db.query(Event)
        .filter(Event.is_demo.is_(False), Event.status == "active")
        .order_by(Event.occurred_at.desc())
        .limit(args.limit)
        .all()
    )

    for ev in events:
        attrs = dict(ev.attributes_json or {})
        if _is_locked_classification(attrs):
            skipped_locked += 1
            continue

        raws = (
            db.query(RawNewsItem)
            .filter(RawNewsItem.event_id == ev.id, RawNewsItem.processing_status == "processed")
            .all()
        )
        if not raws:
            skipped_no_raw += 1
            continue

        try:
            enr = heuristic_enrich(raws)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{ev.id}:{type(exc).__name__}:{exc}")
            continue

        new_sev = float(enr.severity) if enr.severity is not None else None
        old_sev = float(ev.severity) if ev.severity is not None else None
        new_countries = list(enr.countries)
        new_currencies = list(enr.currencies)
        new_materials = list(enr.materials)
        old_countries = _norm_list(ev.match_countries_json)
        old_currencies = _norm_list(ev.match_currencies_json)
        old_materials = _norm_list(ev.match_materials_json)

        cls_before = (attrs.get("classification") or {}) if isinstance(attrs.get("classification"), dict) else {}
        already_v2 = cls_before.get("basis") == HEURISTIC_VERSION

        class_same = (
            ev.category == enr.category
            and ev.event_type == enr.event_type
            and _same_sev(old_sev, new_sev)
            and old_countries == new_countries
            and old_currencies == new_currencies
            and old_materials == new_materials
        )
        if class_same and already_v2:
            unchanged += 1
            continue
        if class_same and not already_v2:
            # Stamp version only — still a classification-meta update.
            pass

        delta = {
            "event_id": ev.id,
            "title": (ev.title or "")[:140],
            "before": {
                "category": ev.category,
                "event_type": ev.event_type,
                "severity": old_sev,
                "countries": old_countries,
                "currencies": old_currencies,
            },
            "after": {
                "category": enr.category,
                "event_type": enr.event_type,
                "severity": new_sev,
                "countries": new_countries,
                "currencies": new_currencies,
                "matched_rules": list((enr.classification_meta or {}).get("matched_rules") or []),
            },
            "fields_touched": list(CLASSIFICATION_FIELDS) + ["attributes_json.classification"],
        }
        changes.append(delta)

        if not args.apply:
            continue

        # Apply classification fields only — never touch title/summary/sources/dates/is_demo.
        ev.category = enr.category
        ev.event_type = enr.event_type
        ev.severity = new_sev
        ev.match_categories_json = [enr.category]
        ev.match_countries_json = new_countries
        ev.match_currencies_json = new_currencies
        ev.match_materials_json = new_materials
        meta = dict(enr.classification_meta or {})
        meta["basis"] = HEURISTIC_VERSION
        meta["applied_at"] = now_iso
        meta["previous"] = {
            "category": delta["before"]["category"],
            "event_type": delta["before"]["event_type"],
            "severity": delta["before"]["severity"],
            "countries": delta["before"]["countries"],
            "currencies": delta["before"]["currencies"],
        }
        attrs["classification"] = meta
        attrs["reclassified_at"] = now_iso
        attrs["reclassified_version"] = HEURISTIC_VERSION
        ev.attributes_json = attrs

        # Stale-mark existing impacts (no recompute).
        impacts = db.query(EventImpact).filter(EventImpact.event_id == ev.id).all()
        for imp in impacts:
            br = dict(imp.score_breakdown_json or {})
            br["event_classification_stale"] = True
            br["stale_reason"] = "event_reclassified_heuristic_v2"
            br["stale_at"] = now_iso
            br["stale_event_snapshot"] = {
                "category": enr.category,
                "event_type": enr.event_type,
                "severity": new_sev,
            }
            imp.score_breakdown_json = br
            # Keep status as-is so rows remain visible, but annotate claims.
            claims = dict(imp.claims_json or {})
            claims["classification_stale"] = True
            claims["classification_stale_note"] = (
                "Оценка влияния рассчитана до смены классификации события (heuristic_v2); "
                "не считать актуальной без пересчёта."
            )
            imp.claims_json = claims
            impact_stale_ids.append(imp.id)

    if args.apply and changes:
        db.commit()
    elif args.apply:
        db.rollback()
    db.close()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORT_DIR / f"apply_report_{stamp}.json"
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "preview",
        "db_path": str(db_path).replace("\\", "/"),
        "alembic_version": alembic_rev,
        "severity_nullable": sev_nullable,
        "heuristic_version": HEURISTIC_VERSION,
        "backup": (
            str(backup_path.relative_to(ROOT)).replace("\\", "/") if backup_path else None
        ),
        "backup_sha256": backup_sha,
        "scanned": len(events),
        "would_change_or_changed": len(changes),
        "unchanged_already_v2": unchanged,
        "skipped_locked": skipped_locked,
        "skipped_no_raw": skipped_no_raw,
        "errors": errors[:30],
        "impact_stale_marked": len(set(impact_stale_ids)) if args.apply else None,
        "impact_stale_ids_sample": sorted(set(impact_stale_ids))[:40] if args.apply else [],
        "messages_scenarios_decisions_telegram_untouched": True,
        "impact_mass_recompute": False,
        "changes": changes,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Console-safe summary per event
    print(
        json.dumps(
            {
                "summary": {
                    "scanned": len(events),
                    "changes": len(changes),
                    "unchanged": unchanged,
                    "skipped_locked": skipped_locked,
                    "skipped_no_raw": skipped_no_raw,
                    "applied": bool(args.apply),
                    "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
                }
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    for c in changes:
        print(
            f"- {c['event_id']}: "
            f"{c['before']['category']}/{c['before']['event_type']}/{c['before']['severity']} "
            f"{c['before']['countries']}/{c['before']['currencies']} → "
            f"{c['after']['category']}/{c['after']['event_type']}/{c['after']['severity']} "
            f"{c['after']['countries']}/{c['after']['currencies']} "
            f"| {(c['title'] or '')[:80]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
