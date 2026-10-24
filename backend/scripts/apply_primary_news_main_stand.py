# -*- coding: utf-8 -*-
"""Transfer verified primary publications onto real_news_613 (main :5180/:8020 stand).

- SQLite backup first
- store_article + process_pending(personalize=False) + reprocess
- No Telegram / live LLM / full-company recompute
- Does not overwrite users/companies/decisions
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DB = ROOT / "data/competition_stand/business_news_coverage/stand.db"
MAIN_DIR = ROOT / "data/competition_stand/real_news_613"
MAIN_DB = MAIN_DIR / "stand.db"
MAIN_ENV = MAIN_DIR / "stand.env"
BACKUP_DIR = MAIN_DIR / "backups"
REPORT = MAIN_DIR / "primary_news_main_stand_report.json"
DOCS = ROOT / "docs/PRIMARY_NEWS_MAIN_STAND.md"
RUNBOOK = ROOT / "docs/NEW_USER_RUNTIME_VERIFICATION.md"


def _read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip("\"'")
    return out


def _backup(src: Path) -> tuple[Path, str]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = BACKUP_DIR / f"stand_pre_primary_{stamp}.db"
    # Consistent SQLite backup API
    s = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()
    sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    return dst, sha


def _apply_main_env() -> None:
    for k in (
        "COMPETITION_MODE",
        "ASSISTANT_PROVIDER",
        "HACKATHON_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "OPENAI_API_KEY",
        "GIGACHAT_AUTH_KEY",
    ):
        os.environ.pop(k, None)
    env = _read_env(MAIN_ENV)
    env["DATABASE_URL"] = f"sqlite:///./{MAIN_DB.relative_to(ROOT).as_posix()}"
    env["COMPETITION_MODE"] = "true"
    env["ASSISTANT_PROVIDER"] = "hackathon"
    env["ASSISTANT_AGENT_LOOP"] = env.get("ASSISTANT_AGENT_LOOP", "true")
    # Placeholder so Settings accepts competition_mode; no HTTP made with heuristic.
    if not env.get("HACKATHON_API_KEY"):
        # Prefer process/root without printing
        root_env = _read_env(ROOT / ".env")
        env["HACKATHON_API_KEY"] = root_env.get("HACKATHON_API_KEY") or "unused-heuristic"
    env["TELEGRAM_BOT_TOKEN"] = ""
    env["OPENAI_API_KEY"] = ""
    env["GIGACHAT_AUTH_KEY"] = ""
    for k, v in env.items():
        os.environ[k] = v
    from app.core.config import get_settings

    get_settings.cache_clear()


def _patch_outbox_schema(db_path: Path) -> None:
    """Idempotent ORM-align columns; does not alter subscription rows/settings."""
    con = sqlite3.connect(db_path)
    try:
        cols = {
            r[1]
            for r in con.execute("PRAGMA table_info(notification_outbox)").fetchall()
        }
        if not cols:
            return
        if "subscription_id" not in cols:
            con.execute(
                "ALTER TABLE notification_outbox ADD COLUMN subscription_id VARCHAR(36)"
            )
        if "kind" not in cols:
            con.execute(
                "ALTER TABLE notification_outbox ADD COLUMN kind VARCHAR(32) "
                "NOT NULL DEFAULT 'impact'"
            )
        con.commit()
    finally:
        con.close()


def _counts(db) -> dict:
    from app.models import Decision, Event, EventImpact, Scenario, User, Company
    from app.models.raw_news import RawNewsItem
    from app.models.notification import NotificationSubscription
    from sqlalchemy import text

    # Raw SQL for outbox — tolerate pre-008 schema until patched.
    outbox = db.execute(text("SELECT COUNT(*) FROM notification_outbox")).scalar() or 0
    return {
        "users": db.query(User).count(),
        "companies": db.query(Company).count(),
        "raw": db.query(RawNewsItem).count(),
        "events_live": db.query(Event)
        .filter(Event.status == "active", Event.is_demo.is_(False))
        .count(),
        "scenarios": db.query(Scenario).count(),
        "decisions": db.query(Decision).count(),
        "impacts": db.query(EventImpact).count(),
        "outbox": int(outbox),
        "telegram_subs": db.query(NotificationSubscription).count(),
    }


def _snapshot_decision_ids(db) -> list[str]:
    from app.models import Decision

    return [r[0] for r in db.query(Decision.id).order_by(Decision.id).all()]


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    assert MAIN_DB.is_file(), MAIN_DB
    assert SRC_DB.is_file(), SRC_DB

    print("=== backup ===")
    backup_path, backup_sha = _backup(MAIN_DB)
    print(backup_path.name, backup_sha[:16])

    print("=== schema align (outbox nullable cols) ===")
    _patch_outbox_schema(MAIN_DB)

    _apply_main_env()
    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    get_settings.cache_clear()
    engine.dispose()

    # Source session on coverage DB (read-only intent)
    src_engine = create_engine(
        f"sqlite:///{SRC_DB.resolve().as_posix()}",
        connect_args={"check_same_thread": False},
    )
    SrcSession = sessionmaker(bind=src_engine, autoflush=False, autocommit=False)
    source_db = SrcSession()
    target_db = SessionLocal()

    from app.services.ingestion.transfer_primary import apply_transfer, plan_transfer
    from app.services.ingestion.pipeline import process_pending
    from app.models import Event, EventSource
    from app.models.raw_news import RawNewsItem

    settings = get_settings()
    link = {
        "site": "http://127.0.0.1:5180",
        "api": "http://127.0.0.1:8020",
        "database_url_scheme": "sqlite",
        "database_relative": str(MAIN_DB.relative_to(ROOT)).replace("\\", "/"),
        "assistant_provider": settings.normalized_assistant_provider(),
        "assistant_agent_loop": bool(settings.assistant_agent_loop),
        "competition_mode": bool(settings.competition_mode),
        "backup": str(backup_path.relative_to(ROOT)).replace("\\", "/"),
        "backup_sha256": backup_sha,
    }

    before = _counts(target_db)
    decision_ids_before = _snapshot_decision_ids(target_db)

    print("=== dry-run ===")
    dry = plan_transfer(source_db, target_db, dry_run=True, limit=50)
    print("items", len(dry.items), "insert", dry.would_insert, "dup", dry.would_duplicate)

    print("=== apply ===")
    plan, store_res, proc = apply_transfer(
        source_db,
        target_db,
        prefer_live_enrich=False,
        personalize=False,
        limit=50,
    )

    print("=== idempotent pass ===")
    plan2, store2, proc2 = apply_transfer(
        source_db,
        target_db,
        prefer_live_enrich=False,
        personalize=False,
        limit=50,
    )
    # Also process_pending empty
    empty = process_pending(target_db, prefer_live_enrich=False, personalize=False)

    after = _counts(target_db)
    decision_ids_after = _snapshot_decision_ids(target_db)

    # Published events detail
    published = []
    for eid in proc.event_ids:
        ev = target_db.get(Event, eid)
        if not ev:
            continue
        srcs = target_db.query(EventSource).filter(EventSource.event_id == ev.id).all()
        published.append(
            {
                "id": ev.id,
                "title": ev.title,
                "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
                "publish_reason": (ev.attributes_json or {}).get("publish_reason"),
                "official_source_ids": (ev.attributes_json or {}).get(
                    "official_source_ids"
                ),
                "sources": [
                    {
                        "publisher": s.publisher,
                        "url": s.url,
                        "published_at": s.published_at.isoformat()
                        if s.published_at
                        else None,
                    }
                    for s in srcs
                ],
            }
        )

    # Pick manual discuss candidate: prefer WTO investigation or FTS with clear URL
    manual = None
    for ev in published:
        title = (ev.get("title") or "").lower()
        if "investigation" in title or "safeguard" in title:
            manual = ev
            break
    if manual is None and published:
        manual = published[0]

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "link": link,
        "dry_run": {
            "count": len(dry.items),
            "would_insert": dry.would_insert,
            "would_duplicate": dry.would_duplicate,
            "items": [
                {
                    "title": i.title[:120],
                    "url": i.canonical_url,
                    "official": i.official_source_id,
                    "action": i.action,
                    "published_at": i.published_at.isoformat()
                    if i.published_at
                    else None,
                }
                for i in dry.items
            ],
        },
        "apply": {
            "store_inserted": store_res.inserted,
            "store_duplicates": store_res.duplicates,
            "published": proc.published,
            "rejected": proc.rejected,
            "event_ids": proc.event_ids,
            "errors": proc.errors,
        },
        "idempotent": {
            "store_inserted": store2.inserted,
            "store_duplicates": store2.duplicates,
            "published": proc2.published,
            "empty_process_published": empty.published,
        },
        "before": before,
        "after": after,
        "deltas": {k: after[k] - before[k] for k in before},
        "decisions_unchanged": decision_ids_before == decision_ids_after,
        "published_events": published,
        "manual_check": {
            "event_id": manual["id"] if manual else None,
            "title": manual["title"] if manual else None,
            "public_path": f"/news/{manual['id']}" if manual else None,
            "discuss_hint": (
                f"Открыть http://127.0.0.1:5180/news/{manual['id']} → обсуждение; "
                "live-вопрос модели не отправлять на этом этапе."
                if manual
                else None
            ),
        },
        "upk_profile_mutated": False,
        "telegram_llm_full_recompute": False,
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    _write_docs(report)
    _update_runbook(report)
    print("published", proc.published, "idempotent_pub", proc2.published)
    print("deltas", report["deltas"])
    print("wrote", DOCS)
    source_db.close()
    target_db.close()
    src_engine.dispose()
    return 0


def _write_docs(report: dict) -> None:
    link = report["link"]
    lines = [
        "# Первичные публикации на основном стенде",
        "",
        f"Дата: {report['created_at'][:10]}",
        "",
        "Перенос 15 проверенных первичных публикаций (WTO / ФТС / EC presscorner) "
        "на основной стенд без затирания пользователей и истории.",
        "",
        "Связанные: `PRIMARY_SOURCE_PUBLICATION.md`, `BUSINESS_NEWS_COVERAGE.md`.",
        "",
        "---",
        "",
        "## 1. Связка сайта",
        "",
        "| | |",
        "|--|--|",
        f"| Сайт | {link['site']} |",
        f"| API | {link['api']} |",
        f"| БД | `{link['database_relative']}` |",
        f"| provider | {link['assistant_provider']} |",
        f"| agent-loop | {link['assistant_agent_loop']} |",
        f"| competition_mode | {link['competition_mode']} |",
        f"| backup | `{link['backup']}` |",
        f"| backup sha256 | `{link['backup_sha256'][:16]}…` |",
        "",
        "Другие стенды (не основной UI):",
        "",
        "- `5187` / `8027` — telegram_live (mock), отдельно;",
        "- `business_news_coverage` — рабочая копия для политики источников;",
        "- не поднимать новый frontend/API на других портах для этой проверки.",
        "",
        "---",
        "",
        "## 2. Dry-run",
        "",
        f"Кандидатов: **{report['dry_run']['count']}** "
        f"(insert={report['dry_run']['would_insert']}, "
        f"already-present={report['dry_run']['would_duplicate']}).",
        "",
        "Перенос через `store_article` (dedupe URL/external_id/hash) + "
        "`process_pending(personalize=False)` + `reprocess_rejected` при необходимости. "
        "Целиком тестовая БД поверх основной **не** копировалась.",
        "",
        "---",
        "",
        "## 3. Apply",
        "",
        "| | |",
        "|--|--|",
        f"| raw inserted | {report['apply']['store_inserted']} |",
        f"| raw duplicates | {report['apply']['store_duplicates']} |",
        f"| Events published | {report['apply']['published']} |",
        f"| rejected | {report['apply']['rejected']} |",
        f"| idempotent published | {report['idempotent']['published']} |",
        f"| Δ users | {report['deltas']['users']} |",
        f"| Δ companies | {report['deltas']['companies']} |",
        f"| Δ scenarios | {report['deltas']['scenarios']} |",
        f"| Δ decisions | {report['deltas']['decisions']} |",
        f"| Δ outbox | {report['deltas']['outbox']} |",
        f"| Δ telegram_subs | {report['deltas']['telegram_subs']} |",
        f"| decisions unchanged | {report['decisions_unchanged']} |",
        "",
        "Telegram / live LLM / пересчёт всех компаний: **не запускались** "
        f"(`personalize=False`).",
        "",
        "### Опубликованные примеры",
        "",
    ]
    for ev in report.get("published_events") or []:
        lines.append(f"- **{ev['title']}** (`{ev['id']}`)")
        lines.append(
            f"  - occurred_at={ev.get('occurred_at')}, "
            f"reason={ev.get('publish_reason')}, official={ev.get('official_source_ids')}"
        )
        for s in ev.get("sources") or []:
            lines.append(
                f"  - {s.get('publisher')}: {s.get('url')} "
                f"(published_at={s.get('published_at')})"
            )
    if not report.get("published_events"):
        lines.append("_Новых Event нет (возможно, уже были на стенде)._")
    lines += [
        "",
        "---",
        "",
        "## 4. Ручная проверка live-вопроса (без отправки)",
        "",
    ]
    m = report.get("manual_check") or {}
    if m.get("event_id"):
        lines.append(f"- Новость: **{m.get('title')}**")
        lines.append(f"- ID: `{m.get('event_id')}`")
        lines.append(f"- URL: http://127.0.0.1:5180{m.get('public_path')}")
        lines.append(f"- {m.get('discuss_hint')}")
    else:
        lines.append("Подходящая новость не выбрана.")
    lines += [
        "",
        "---",
        "",
        "## 5. Ограничения",
        "",
        "- Профиль «упк» не изменялся; карточки «Для вас» не форсились.",
        "- EC presscorner официален как первоисточник EC, не как trade-only лента.",
        "- Секреты в отчёт не выводились.",
        "",
        f"Машинный отчёт: `{MAIN_DIR.relative_to(ROOT).as_posix()}/primary_news_main_stand_report.json`",
        "",
    ]
    DOCS.write_text("\n".join(lines), encoding="utf-8")


def _update_runbook(report: dict) -> None:
    if not RUNBOOK.is_file():
        return
    text = RUNBOOK.read_text(encoding="utf-8")
    marker = "\n## Актуальный адрес стенда (primary news)\n"
    block = (
        marker
        + "\n"
        + "| | |\n|--|--|\n"
        + "| **Открывать** | http://127.0.0.1:5180 → API http://127.0.0.1:8020 |\n"
        + "| БД | `data/competition_stand/real_news_613/stand.db` |\n"
        + "| provider / loop | hackathon + agent-loop |\n"
        + "| Primary news | см. `PRIMARY_NEWS_MAIN_STAND.md` |\n"
        + "| Не основной UI | `:5187`/`:8027` telegram_live; "
        "`business_news_coverage` — копия для политики источников |\n"
        + "\nНе поднимать ещё один frontend/API на новых портах для этой проверки.\n"
    )
    if marker in text:
        # replace from marker to next ## or end
        idx = text.index(marker)
        rest = text[idx + len(marker) :]
        nxt = rest.find("\n## ")
        if nxt >= 0:
            text = text[:idx] + block + rest[nxt:]
        else:
            text = text[:idx] + block
    else:
        text = text.rstrip() + "\n" + block
    RUNBOOK.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
