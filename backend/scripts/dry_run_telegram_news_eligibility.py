# -*- coding: utf-8 -*-
"""Dry-run news eligibility for one subscription. No Telegram sends, no outbox writes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument(
        "--assume-watermark-now",
        action="store_true",
        help="Evaluate as if auto_notify_since were stamped to UTC now (no DB write)",
    )
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ["DATABASE_URL"] = "sqlite:///./data/competition_stand/real_news_613/stand.db"
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("SECRET_KEY", "tg-dry-run")
    os.environ["TELEGRAM_NEWS_NOTIFICATIONS_ENABLED"] = "true"
    os.environ.pop("TELEGRAM_NEWS_CONTROLLED_PAIR", None)
    os.environ.setdefault("COMPETITION_MODE", "false")
    os.environ.setdefault("ASSISTANT_PROVIDER", "mock")

    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models import Event, EventImpact, NotificationSubscription
    from app.services.telegram_news_policy import evaluate_news_eligibility

    get_settings.cache_clear()
    engine.dispose()
    db = SessionLocal()
    sub = db.get(NotificationSubscription, args.subscription_id)
    if sub is None:
        print("subscription not found", file=sys.stderr)
        return 2

    assumed_wm = datetime.now(timezone.utc) if args.assume_watermark_now else None
    if assumed_wm is not None:
        # ephemeral — do not commit
        sub.auto_notify_since = assumed_wm

    impacts = (
        db.query(EventImpact)
        .filter(EventImpact.company_id == sub.company_id)
        .order_by(EventImpact.computed_at.desc())
        .limit(args.limit)
        .all()
    )
    # Also scan active risk events without impact
    events_no_impact = (
        db.query(Event)
        .filter(Event.status == "active", Event.is_demo.is_(False), Event.event_type == "risk")
        .limit(args.limit)
        .all()
    )

    rows = []
    eligible = []
    for impact in impacts:
        event = db.get(Event, impact.event_id)
        if event is None:
            continue
        d = evaluate_news_eligibility(db, sub=sub, event=event, impact=impact)
        item = {
            "event_id": event.id,
            "title": (event.title or "")[:100],
            "is_demo": bool(event.is_demo),
            "event_type": event.event_type,
            "severity": float(event.severity) if event.severity is not None else None,
            "impact_score": float(impact.impact_score),
            "impact_status": impact.status,
            "score_kind": (impact.score_breakdown_json or {}).get("score_kind"),
            "allowed": d.allowed,
            "reason": d.reason,
        }
        rows.append(item)
        if d.allowed:
            eligible.append(item)

    report = {
        "subscription_id": sub.id,
        "company_id": sub.company_id,
        "min_severity": sub.min_severity,
        "risks_enabled": sub.risks_enabled,
        "watermark_used": (assumed_wm or sub.auto_notify_since).isoformat()
        if (assumed_wm or sub.auto_notify_since)
        else None,
        "assume_watermark_now": bool(args.assume_watermark_now),
        "controlled_pair": None,
        "impacts_scanned": len(rows),
        "eligible_count": len(eligible),
        "eligible": eligible,
        "denied_sample": [r for r in rows if not r["allowed"]][:20],
        "active_non_demo_risk_events_without_requiring_impact_scan": len(events_no_impact),
        "sends": 0,
        "outbox_writes": 0,
    }
    db.rollback()  # discard ephemeral watermark
    db.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
