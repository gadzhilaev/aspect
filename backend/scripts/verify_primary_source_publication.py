# -*- coding: utf-8 -*-
"""Reprocess rejected primary-source raw on business_news_coverage copy only."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAND_DIR = ROOT / "data/competition_stand/business_news_coverage"
STAND_DB = STAND_DIR / "stand.db"
STAND_ENV = STAND_DIR / "stand.env"
REPORT = STAND_DIR / "primary_publication_report.json"
DOCS = ROOT / "docs/PRIMARY_SOURCE_PUBLICATION.md"

HOSTS = ["wto.org", "customs.gov.ru", "ec.europa.eu"]


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


def _apply() -> None:
    for k in (
        "COMPETITION_MODE",
        "ASSISTANT_PROVIDER",
        "HACKATHON_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "OPENAI_API_KEY",
    ):
        os.environ.pop(k, None)
    env = _read_env(STAND_ENV)
    env["DATABASE_URL"] = f"sqlite:///./{STAND_DB.relative_to(ROOT).as_posix()}"
    # Competition + heuristic: no LLM; do not weaken provider guard.
    env["COMPETITION_MODE"] = "true"
    env["ASSISTANT_PROVIDER"] = "hackathon"
    env["HACKATHON_API_KEY"] = "unused-for-heuristic-ingest"
    env["TELEGRAM_BOT_TOKEN"] = ""
    env["OPENAI_API_KEY"] = ""
    env["GIGACHAT_AUTH_KEY"] = ""
    for k, v in env.items():
        os.environ[k] = v
    from app.core.config import get_settings

    get_settings.cache_clear()


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    if not STAND_DB.is_file():
        print("COPY_MISSING", STAND_DB)
        return 1
    _apply()

    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models import Decision, Event, EventImpact, EventSource, Scenario
    from app.models.notification import NotificationOutbox
    from app.models.raw_news import RawNewsItem
    from app.services.ingestion.official_sources import classify_official_primary
    from app.services.ingestion.reprocess import plan_reprocess, reprocess_rejected
    from app.services.impact import recompute_events_for_company
    from app.models import Company

    get_settings.cache_clear()
    engine.dispose()
    settings = get_settings()
    assert settings.competition_mode is True
    assert settings.normalized_assistant_provider() == "hackathon"

    db = SessionLocal()
    before = {
        "events_live": db.query(Event)
        .filter(Event.status == "active", Event.is_demo.is_(False))
        .count(),
        "scenarios": db.query(Scenario).count(),
        "decisions": db.query(Decision).count(),
        "outbox": db.query(NotificationOutbox).count(),
        "raw_rejected": db.query(RawNewsItem)
        .filter(RawNewsItem.processing_status == "rejected")
        .count(),
        "raw_processed": db.query(RawNewsItem)
        .filter(RawNewsItem.processing_status == "processed")
        .count(),
    }

    dry = plan_reprocess(
        db,
        dry_run=True,
        article_hosts=HOSTS,
        feed_hosts=HOSTS,
        errors=["unverified_single_source"],
        only_would_be_official=True,
        limit=100,
    )
    print("dry_run candidates", len(dry.candidate_ids))

    plan, result = reprocess_rejected(
        db,
        dry_run=False,
        prefer_live_enrich=False,  # heuristic — no live LLM
        article_hosts=HOSTS,
        feed_hosts=HOSTS,
        errors=["unverified_single_source"],
        only_would_be_official=True,
        limit=100,
    )

    published = []
    for eid in result.event_ids if result else []:
        ev = db.get(Event, eid)
        if ev is None:
            continue
        sources = db.query(EventSource).filter(EventSource.event_id == ev.id).all()
        raws = (
            db.query(RawNewsItem).filter(RawNewsItem.event_id == ev.id).all()
        )
        classifications = []
        for r in raws:
            c = classify_official_primary(r)
            classifications.append(
                {
                    "raw_id": r.id,
                    "is_official_primary": c.is_official_primary,
                    "source_id": c.source_id,
                    "reason": c.reason,
                    "limitations": c.limitations,
                }
            )
        published.append(
            {
                "event_id": ev.id,
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
                    for s in sources
                ],
                "raw_ids": [r.id for r in raws],
                "classifications": classifications,
            }
        )

    still_rejected = []
    for item in (
        db.query(RawNewsItem)
        .filter(RawNewsItem.processing_status == "rejected")
        .order_by(RawNewsItem.fetched_at.desc())
        .limit(40)
        .all()
    ):
        payload = item.payload_json if isinstance(item.payload_json, dict) else {}
        feed = str(payload.get("feed_url") or "")
        if not any(h in feed or h in (item.canonical_url or "") for h in HOSTS):
            # keep commercial rejects briefly
            if "interfax" in feed or "vedomosti" in feed:
                still_rejected.append(
                    {
                        "id": item.id,
                        "title": (item.title or "")[:100],
                        "error": item.error,
                        "feed_url": feed,
                        "why": "commercial_single_source_gate",
                    }
                )
        else:
            still_rejected.append(
                {
                    "id": item.id,
                    "title": (item.title or "")[:100],
                    "error": item.error,
                    "feed_url": feed,
                    "classification": classify_official_primary(item).reason,
                }
            )

    # Idempotent second pass
    plan2, result2 = reprocess_rejected(
        db,
        dry_run=False,
        prefer_live_enrich=False,
        article_hosts=HOSTS,
        feed_hosts=HOSTS,
        only_would_be_official=True,
        limit=100,
    )

    after = {
        "events_live": db.query(Event)
        .filter(Event.status == "active", Event.is_demo.is_(False))
        .count(),
        "scenarios": db.query(Scenario).count(),
        "decisions": db.query(Decision).count(),
        "outbox": db.query(NotificationOutbox).count(),
        "raw_rejected": db.query(RawNewsItem)
        .filter(RawNewsItem.processing_status == "rejected")
        .count(),
        "raw_processed": db.query(RawNewsItem)
        .filter(RawNewsItem.processing_status == "processed")
        .count(),
    }

    # Optional упк check (not success criterion)
    upk = None
    company = db.get(Company, "b76ead25-eaf9-4eea-89f0-70b7bbb0acb0")
    if company is not None:
        impacts = recompute_events_for_company(db, company, demo_only=False)
        db.commit()
        upk = {
            "impacts_returned": len(impacts),
            "active": db.query(EventImpact)
            .filter(
                EventImpact.company_id == company.id,
                EventImpact.status.in_(["action_required", "monitor"]),
            )
            .count(),
        }

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stand_db": str(STAND_DB.relative_to(ROOT)).replace("\\", "/"),
        "competition_mode": True,
        "assistant_provider": "hackathon",
        "prefer_live_enrich": False,
        "ec_dossier_trade_effective": False,
        "before": before,
        "dry_run_candidates": len(dry.candidate_ids),
        "pass1": {
            "candidates": plan.candidate_ids,
            "published": result.published if result else 0,
            "rejected": result.rejected if result else 0,
            "event_ids": result.event_ids if result else [],
            "errors": result.errors if result else [],
        },
        "published_events": published,
        "still_rejected_sample": still_rejected[:25],
        "pass2_idempotent": {
            "candidates": plan2.candidate_ids,
            "published": result2.published if result2 else 0,
            "delta_live_events": after["events_live"] - (
                before["events_live"] + (result.published if result else 0)
            ),
        },
        "after": after,
        "deltas": {
            "live_events": after["events_live"] - before["events_live"],
            "scenarios": after["scenarios"] - before["scenarios"],
            "decisions": after["decisions"] - before["decisions"],
            "outbox": after["outbox"] - before["outbox"],
        },
        "upk_optional": upk,
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    _write_md(report)
    print("wrote", REPORT, DOCS)
    print(
        "published",
        report["pass1"]["published"],
        "delta_events",
        report["deltas"]["live_events"],
        "delta_scen/dec/out",
        report["deltas"]["scenarios"],
        report["deltas"]["decisions"],
        report["deltas"]["outbox"],
    )
    db.close()
    return 0


def _write_md(report: dict) -> None:
    lines = []
    lines.append("# Официальные первичные источники: публикация")
    lines.append("")
    lines.append(f"Дата: {report['created_at'][:10]}")
    lines.append("")
    lines.append(
        "Цель: корректная классификация первичных источников в gate "
        "`can_publish`, а не отключение проверки. "
        "Работа только на копии `business_news_coverage`. "
        "Основной стенд / root `.env` / профиль пользователя не менялись."
    )
    lines.append("")
    lines.append(
        "Связанные: `BUSINESS_NEWS_COVERAGE.md`. "
        "Код: `app/services/ingestion/official_sources.py`, "
        "`publish.py`, `reprocess.py`."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Аудит сохранённых WTO / ФТС / EC")
    lines.append("")
    lines.append(
        "На копии 15 raw с feed на `wto.org` / `customs.gov.ru` / `ec.europa.eu`. "
        "У всех проверенных записей: host статьи = host организации после redirects; "
        "feed URL принадлежит тому же сайту; организация — первоисточник **своей** "
        "пресс-страницы. HTTP 200 и строка publisher сами по себе доверия не давали "
        "(`payload.is_official` был false; gate отклонял как `unverified_single_source`)."
    )
    lines.append("")
    lines.append("### EC `dossier=trade`")
    lines.append("")
    lines.append(
        f"**Фильтр не работает.** Сравнение первых заголовков RSS с `dossier=trade` "
        f"и без параметра: полное совпадение "
        f"(`ec_dossier_trade_effective={report['ec_dossier_trade_effective']}`). "
        "Ленту **нельзя** называть торговой — это общая presscorner-выдача "
        "(heritage, speeches, civil protection и т.п. рядом с trade remarks)."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Изменения политики")
    lines.append("")
    lines.append(
        "Добавлен allow-list первичных источников с ограничениями host/path "
        "для **статьи и feed**:"
    )
    lines.append("")
    lines.append("| source_id | hosts | path | основание |")
    lines.append("|-----------|-------|------|-----------|")
    lines.append(
        "| `cbr` | cbr.ru | — | Банк России, первичная публикация |"
    )
    lines.append(
        "| `wto` | wto.org | article `/english/news_e/…`, feed `/library/rss/` | "
        "ВТО, первичная news RSS |"
    )
    lines.append(
        "| `fts_ru` | customs.gov.ru | `/press/` | ФТС, первичная пресс-лента |"
    )
    lines.append(
        "| `ec_presscorner` | ec.europa.eu | `/commission/presscorner/` | "
        "Еврокомиссия presscorner; **не** «trade feed» |"
    )
    lines.append("")
    lines.append("Явно **не** доверяем:")
    lines.append("")
    lines.append("- `payload.is_official` / RSS connector hint;")
    lines.append("- совпадению publisher («Банк России», «WTO…») на чужом хосте;")
    lines.append("- lookalike-доменам (`wto.org.evil…`);")
    lines.append("- пометке всего `RssProvider` как official.")
    lines.append("")
    lines.append(
        "Gate для одиночных неподтверждённых источников сохранён "
        "(`unverified_single_source`). "
        "Публикация официального сообщения подтверждает **происхождение**, "
        "не прогноз и не ущерб компании."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. Reprocess на копии")
    lines.append("")
    lines.append(
        f"COMPETITION_MODE={report['competition_mode']}, "
        f"ASSISTANT_PROVIDER={report['assistant_provider']}, "
        f"prefer_live_enrich={report['prefer_live_enrich']} "
        "(heuristic; live LLM не вызывался)."
    )
    lines.append("")
    lines.append(
        "Ранее rejected → `pending` без смены ID / удаления raw "
        "(`reprocess_rejected`). Dedup `store_article` публикации не блокирует."
    )
    lines.append("")
    lines.append("| | |")
    lines.append("|--|--|")
    lines.append(f"| dry-run candidates | {report['dry_run_candidates']} |")
    lines.append(f"| published (pass 1) | {report['pass1']['published']} |")
    lines.append(f"| Δ live events | {report['deltas']['live_events']} |")
    lines.append(f"| Δ scenarios | {report['deltas']['scenarios']} |")
    lines.append(f"| Δ decisions | {report['deltas']['decisions']} |")
    lines.append(f"| Δ outbox | {report['deltas']['outbox']} |")
    lines.append(
        f"| pass 2 candidates | {len(report['pass2_idempotent']['candidates'])} "
        f"(ожидаемо 0) |"
    )
    lines.append("")
    lines.append("### Опубликовано (примеры)")
    lines.append("")
    for ev in report.get("published_events") or []:
        lines.append(f"- **{ev['title']}** (`{ev['event_id']}`)")
        lines.append(
            f"  - reason=`{ev.get('publish_reason')}`, "
            f"official=`{ev.get('official_source_ids')}`, "
            f"occurred_at=`{ev.get('occurred_at')}`"
        )
        for s in ev.get("sources") or []:
            lines.append(
                f"  - source: {s.get('publisher')} · {s.get('url')} · "
                f"published_at={s.get('published_at')}"
            )
        for c in ev.get("classifications") or []:
            if c.get("limitations"):
                lines.append(f"  - limitation: {c['limitations'][:160]}…")
    if not report.get("published_events"):
        lines.append("_Нет опубликованных событий._")
    lines.append("")
    lines.append("### Остаются отклонёнными")
    lines.append("")
    lines.append(
        "Interfax / Vedomosti (и прочие одиночные коммерческие) — по-прежнему "
        "`unverified_single_source`. Примеры:"
    )
    lines.append("")
    for row in (report.get("still_rejected_sample") or [])[:8]:
        lines.append(
            f"- {(row.get('title') or '')[:80]} — `{row.get('error')}` "
            f"({row.get('why') or row.get('classification') or ''})"
        )
    lines.append("")
    lines.append(
        "Расследование / предложение / вступившая мера не смешиваются в статусе Event: "
        "заголовок источника сохраняется (напр. WTO «safeguard **investigation**» "
        "не переписывается во «вступившую меру»)."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 4. Конкурсный режим + heuristic")
    lines.append("")
    lines.append(
        "Отключать `COMPETITION_MODE` для heuristic **не нужно**: "
        "`enrich_cluster(..., prefer_live=False)` сразу вызывает `heuristic_enrich` "
        "и не заходит в `live_enrich` / hackathon HTTP. "
        "Guard провайдера не ослаблялся. В прогоне COMPETITION_MODE=true + "
        "`--heuristic-enrich` / `prefer_live_enrich=False`."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 5. Регрессии")
    lines.append("")
    lines.append(
        "`tests/test_official_primary_sources.py` + `tests/test_ingestion.py` — "
        "21 passed (в т.ч. fake publisher, lookalike domain, payload ignore, "
        "reprocess idempotent, competition+heuristic)."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 6. Ограничения")
    lines.append("")
    lines.append(
        "- EC presscorner официален как первоисточник EC, но лента с "
        "`dossier=trade` тематически не отфильтрована API."
    )
    lines.append(
        "- Официальная публикация ≠ релевантность для «упк» "
        f"(optional recompute: {report.get('upk_optional')})."
    )
    lines.append("- Основной стенд и `real_news_613` не обновлялись этим прогоном.")
    lines.append("")
    lines.append(
        f"Машинный отчёт: `{STAND_DIR.relative_to(ROOT).as_posix()}/primary_publication_report.json`"
    )
    lines.append("")
    DOCS.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
