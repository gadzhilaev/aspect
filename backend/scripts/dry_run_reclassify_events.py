# -*- coding: utf-8 -*-
"""Dry-run / optional apply of heuristic_v2 reclassification on a SQLite copy.

Does not touch assistant messages, decisions, or Telegram outbox.
Does not run impact recompute. Main stand DB is never written unless
--apply-on-copy is used on an explicit copy path (never the live path).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_DB = ROOT / "data/competition_stand/real_news_613/stand.db"
COPY_DIR = ROOT / "data/competition_stand/reclassify_dry_run"
REPORT = COPY_DIR / "reclassify_dry_run_report.json"


def _backup_copy(src: Path, dst: Path) -> str:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply-on-copy",
        action="store_true",
        help="Write classification updates onto the copy DB only",
    )
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    os_chdir = ROOT
    import os

    os.chdir(os_chdir)

    assert MAIN_DB.is_file(), MAIN_DB
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    copy_path = COPY_DIR / f"stand_reclassify_{stamp}.db"
    sha = _backup_copy(MAIN_DB, copy_path)
    print("copy", copy_path.name, sha[:16])

    os.environ["DATABASE_URL"] = f"sqlite:///./{copy_path.relative_to(ROOT).as_posix()}"
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("SECRET_KEY", "reclassify-dry-run")
    os.environ["ASSISTANT_PROVIDER"] = "mock"
    os.environ["COMPETITION_MODE"] = "false"

    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models import Event
    from app.models.raw_news import RawNewsItem
    from app.services.ingestion.enrich import heuristic_enrich

    get_settings.cache_clear()
    engine.dispose()

    # Bring copy schema to head (nullable severity) without touching main DB file.
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")

    db = SessionLocal()
    changes: list[dict] = []
    unchanged = 0
    errors: list[str] = []

    events = (
        db.query(Event)
        .filter(Event.is_demo.is_(False), Event.status == "active")
        .order_by(Event.occurred_at.desc())
        .limit(args.limit)
        .all()
    )
    for ev in events:
        raws = (
            db.query(RawNewsItem)
            .filter(RawNewsItem.event_id == ev.id, RawNewsItem.processing_status == "processed")
            .all()
        )
        if not raws:
            unchanged += 1
            continue
        try:
            enr = heuristic_enrich(raws)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{ev.id}:{type(exc).__name__}")
            continue
        new_sev = float(enr.severity) if enr.severity is not None else None
        old_sev = float(ev.severity) if ev.severity is not None else None
        delta = {
            "event_id": ev.id,
            "title": (ev.title or "")[:120],
            "before": {
                "category": ev.category,
                "event_type": ev.event_type,
                "severity": old_sev,
            },
            "after": {
                "category": enr.category,
                "event_type": enr.event_type,
                "severity": new_sev,
                "matched_rules": list((enr.classification_meta or {}).get("matched_rules") or []),
            },
        }
        if (
            delta["before"]["category"] == delta["after"]["category"]
            and delta["before"]["event_type"] == delta["after"]["event_type"]
            and delta["before"]["severity"] == delta["after"]["severity"]
        ):
            unchanged += 1
            continue
        changes.append(delta)
        if args.apply_on_copy:
            ev.category = enr.category
            ev.event_type = enr.event_type
            try:
                ev.severity = new_sev
            except Exception:  # noqa: BLE001
                # SQLite NOT NULL legacy: skip null write
                if new_sev is not None:
                    ev.severity = new_sev
            ev.match_categories_json = [enr.category]
            ev.match_countries_json = list(enr.countries)
            ev.match_currencies_json = list(enr.currencies)
            ev.match_materials_json = list(enr.materials)
            attrs = dict(ev.attributes_json or {})
            attrs["classification"] = dict(enr.classification_meta or {})
            attrs["reclassified_at"] = datetime.now(timezone.utc).isoformat()
            ev.attributes_json = attrs

    if args.apply_on_copy:
        db.commit()
    db.close()

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_db": str(MAIN_DB.relative_to(ROOT)).replace("\\", "/"),
        "copy_db": str(copy_path.relative_to(ROOT)).replace("\\", "/"),
        "copy_sha256": sha,
        "apply_on_copy": bool(args.apply_on_copy),
        "scanned": len(events),
        "would_change": len(changes),
        "unchanged": unchanged,
        "errors": errors[:20],
        "sample_changes": changes[:40],
        "messages_decisions_telegram_untouched": True,
        "impact_recompute": False,
    }
    COPY_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "would_change": len(changes),
                "unchanged": unchanged,
                "apply_on_copy": args.apply_on_copy,
                "report": str(REPORT.relative_to(ROOT)).replace("\\", "/"),
            },
            ensure_ascii=False,
        )
    )
    # Highlight exhibition if present
    for c in changes:
        if "экспозиц" in (c["title"] or "").lower() or "выставк" in (c["title"] or "").lower():
            print("exhibition_sample", json.dumps(c, ensure_ascii=False))
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
