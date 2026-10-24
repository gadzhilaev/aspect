# -*- coding: utf-8 -*-
"""TG-5: prepare ONE controlled news outbox for the bound main-stand subscription.

Does NOT send. Writes preview JSON for human approval.
Uses synthetic demo event (not a real publication). Controlled pair required to pass policy.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MAIN_DB = ROOT / "data/competition_stand/real_news_613/stand.db"
RUNTIME = ROOT / "data/competition_stand/real_news_613/telegram_runtime"
PREVIEW = RUNTIME / "controlled_preview.json"


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ["DATABASE_URL"] = "sqlite:///./data/competition_stand/real_news_613/stand.db"
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("SECRET_KEY", "tg5-controlled")
    os.environ["TELEGRAM_NEWS_NOTIFICATIONS_ENABLED"] = "false"
    os.environ["ASSISTANT_PROVIDER"] = "hackathon"
    os.environ["COMPETITION_MODE"] = "false"  # avoid provider lock for this script
    # No working phone button for localhost stand — do not advertise kontur.app deep link.
    os.environ["PUBLIC_WEB_BASE_URL"] = ""
    os.environ["DEEP_LINK_BASE"] = ""

    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models import Event, EventImpact, EventSource, NotificationOutbox, NotificationSubscription
    from app.services.assessment_explain import SCORE_KIND_COMPANY
    from app.services.telegram_news_policy import (
        NEWS_KIND,
        build_news_telegram_payload,
        evaluate_news_eligibility,
        news_dedupe_key,
    )

    get_settings.cache_clear()
    engine.dispose()
    RUNTIME.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    sub = (
        db.query(NotificationSubscription)
        .filter(
            NotificationSubscription.channel_type == "telegram_private",
            NotificationSubscription.status == "connected",
            NotificationSubscription.is_active.is_(True),
        )
        .order_by(NotificationSubscription.verified_at.desc())
        .first()
    )
    if sub is None or not sub.chat_id:
        print("ERROR: no connected private subscription on main stand", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    # After watermark so novelty passes without bypassing it.
    wm = sub.auto_notify_since
    if wm is not None and wm.tzinfo is None:
        wm = wm.replace(tzinfo=timezone.utc)
    base = max(now, (wm + timedelta(minutes=1)) if wm else now)

    eid = f"evt_tg5_controlled_{uuid4().hex[:10]}"
    event = Event(
        id=eid,
        title="Контролируемая проверка: синтетическое экспортное ограничение (TG-5)",
        summary=(
            "Синтетическая fixture для одной контролируемой Telegram-доставки. "
            "Не является реальной публикацией источника."
        ),
        category="geopolitics",
        event_type="risk",
        severity=75.0,
        status="active",
        occurred_at=base,
        effective_from=base,
        is_demo=True,
        match_countries_json=["Китай"],
        match_categories_json=["geopolitics"],
        match_currencies_json=[],
        match_materials_json=["electronics"],
        attributes_json={
            "synthetic_tg5": True,
            "provenance": "controlled_isolated_fixture",
            "not_real_publication": True,
        },
    )
    db.add(event)
    db.flush()
    event.created_at = base
    db.add(
        EventSource(
            id=str(uuid4()),
            event_id=eid,
            publisher="TG-5 controlled fixture",
            url=None,
            published_at=base,
            source_quality=0.5,
            excerpt="synthetic",
            is_stub=True,
        )
    )
    impact = EventImpact(
        id=str(uuid4()),
        event_id=eid,
        company_id=sub.company_id,
        impact_score=80.0,
        urgency="this_week",
        confidence=0.7,
        reason_summary="Синтетический company_calculated индекс для TG-5 controlled delivery.",
        score_breakdown_json={
            "score_kind": SCORE_KIND_COMPANY,
            "assessment_state": "supply_chain_ready",
            "synthetic_tg5": True,
        },
        claims_json={"confirmed": 0, "assumptions": 1, "synthetic": True},
        status="action_required",
        model_version="tg5-controlled",
        computed_at=now,
    )
    db.add(impact)
    db.flush()

    # Prove ordinary policy rejects this demo without controlled pair.
    os.environ.pop("TELEGRAM_NEWS_CONTROLLED_PAIR", None)
    get_settings.cache_clear()
    denied = evaluate_news_eligibility(db, sub=sub, event=event, impact=impact)
    if denied.allowed or denied.reason not in {"event_demo", "feature_disabled"}:
        # With feature off → feature_disabled; with feature on → event_demo.
        print("WARN unexpected deny reason without pair:", denied.reason)

    # Enable controlled pair for this subscription+event only.
    os.environ["TELEGRAM_NEWS_CONTROLLED_PAIR"] = f"{sub.id}:{eid}"
    get_settings.cache_clear()
    allowed = evaluate_news_eligibility(db, sub=sub, event=event, impact=impact)
    if not allowed.allowed:
        print("ERROR controlled eligibility failed:", allowed.reason, file=sys.stderr)
        db.rollback()
        return 3

    payload = build_news_telegram_payload(
        db, event=event, impact=impact, company_id=sub.company_id, controlled_test=True
    )
    dedupe = news_dedupe_key(subscription_id=sub.id, event_id=eid)
    existing = db.query(NotificationOutbox).filter(NotificationOutbox.dedupe_key == dedupe).first()
    if existing:
        outbox_id = existing.id
        created = False
    else:
        row = NotificationOutbox(
            id=str(uuid4()),
            company_id=sub.company_id,
            subscription_id=sub.id,
            kind=NEWS_KIND,
            event_impact_id=impact.id,
            channel_type="telegram_private",
            chat_id=sub.chat_id,
            payload_json=payload,
            dedupe_key=dedupe,
            status="pending",
            attempts=0,
            next_attempt_at=now,
        )
        db.add(row)
        db.flush()
        outbox_id = row.id
        created = True

    # Persist controlled pair for the one-shot sender (not in Git).
    pair_path = RUNTIME / "controlled_pair.env"
    pair_path.write_text(
        f"TELEGRAM_NEWS_CONTROLLED_PAIR={sub.id}:{eid}\n"
        f"TELEGRAM_NEWS_NOTIFICATIONS_ENABLED=false\n"
        f"CONTROLLED_OUTBOX_ID={outbox_id}\n",
        encoding="utf-8",
    )

    company_name = None
    from app.models import Company

    c = db.get(Company, sub.company_id)
    company_name = c.name if c else sub.company_id

    preview = {
        "prepared_at": now.isoformat(),
        "delivery_kind": "controlled_synthetic_fixture",
        "is_real_publication": False,
        "warning": (
            "Это НЕ доказательство отбора реальной новости в production. "
            "Синтетическая fixture + явный controlled pair."
        ),
        "company_id": sub.company_id,
        "company_name": company_name,
        "subscription_id": sub.id,
        "event_id": eid,
        "event_title": event.title,
        "event_is_demo": True,
        "impact_id": impact.id,
        "impact_score": impact.impact_score,
        "score_kind": SCORE_KIND_COMPANY,
        "outbox_id": outbox_id,
        "outbox_created": created,
        "outbox_status": "pending",
        "has_public_open_button": bool(payload.get("has_public_open_url")),
        "buttons": payload.get("buttons"),
        "text": payload.get("text"),
        "eligibility_without_pair": denied.as_dict(),
        "eligibility_with_pair": allowed.as_dict(),
        "send": "NOT sent — wait for explicit user approval (отправляй)",
    }
    db.commit()
    PREVIEW.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"preview": str(PREVIEW.relative_to(ROOT)).replace("\\", "/"), **{k: preview[k] for k in ("outbox_id", "event_id", "company_name", "is_real_publication", "has_public_open_button")}}, ensure_ascii=False, indent=2))
    print("---TEXT---")
    print(preview["text"])
    print("---END---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
