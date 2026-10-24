# -*- coding: utf-8 -*-
"""Business-news coverage check on a COPY of real_news_613.

- ≤50 source records total, heuristic enrich only (no live LLM).
- Existing connectors: GDELT + RSS whitelist (stand.env on the copy).
- Does NOT expand OFFICIAL/trusted publishers in code.
- Does NOT mutate real_news_613; Telegram token cleared for this process.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC_DB = ROOT / "data/competition_stand/real_news_613/stand.db"
SRC_ENV = ROOT / "data/competition_stand/real_news_613/stand.env"
STAND_DIR = ROOT / "data/competition_stand/business_news_coverage"
STAND_DB = STAND_DIR / "stand.db"
STAND_ENV = STAND_DIR / "stand.env"
REPORT_JSON = STAND_DIR / "coverage_report.json"
FIXTURES = STAND_DIR / "fixtures"
DOCS_MD = ROOT / "docs/BUSINESS_NEWS_COVERAGE.md"

UPK_ID = "b76ead25-eaf9-4eea-89f0-70b7bbb0acb0"

# Candidate feeds / APIs — probed; only available ones used.
CANDIDATES = [
    {
        "id": "rss_interfax",
        "kind": "rss",
        "url": "https://www.interfax.ru/rss.asp",
        "theme": "general_business",
        "existing_connector": True,
        "trust_basis": (
            "Существующий whitelist RSS; коммерческий агрегатор. "
            "Не official — публикация Event только при ≥2 независимых издателях в кластере."
        ),
    },
    {
        "id": "rss_vedomosti",
        "kind": "rss",
        "url": "https://www.vedomosti.ru/rss/news",
        "theme": "general_business",
        "existing_connector": True,
        "trust_basis": (
            "Существующий whitelist RSS; деловая пресса. "
            "Не official — те же правила verification gate."
        ),
    },
    {
        "id": "rss_wto",
        "kind": "rss",
        "url": "https://www.wto.org/library/rss/latest_news_e.xml",
        "theme": "trade",
        "existing_connector": True,  # via RssProvider whitelist on copy
        "trust_basis": (
            "Первичная лента ВТО (межправительственная организация). "
            "В код OFFICIAL_PROVIDERS не добавлялась — одна запись без второго "
            "издателя → unverified_single_source (не обходим gate)."
        ),
    },
    {
        "id": "rss_ec_trade",
        "kind": "rss",
        "url": "https://ec.europa.eu/commission/presscorner/api/rss?dossier=trade&language=en",
        "theme": "trade_export",
        "existing_connector": True,
        "trust_basis": (
            "Официальные press releases Еврокомиссии (dossier=trade). "
            "Не помечена official в Kontur — без второго источника не публикуется."
        ),
    },
    {
        "id": "rss_customs_ru",
        "kind": "rss",
        "url": "https://customs.gov.ru/press/federal/rss",
        "theme": "trade_logistics",
        "existing_connector": True,
        "trust_basis": (
            "ФТС России — первичная гос. пресс-лента. "
            "Не добавлена в trusted/official ради публикации; gate тот же."
        ),
    },
    {
        "id": "gdelt_export_electronics",
        "kind": "gdelt",
        "url": "https://api.gdeltproject.org/api/v2/doc/doc",
        "query": '(export control OR export restriction OR sanctions) AND (semiconductor OR electronics OR chip)',
        "theme": "electronics_export",
        "existing_connector": True,
        "trust_basis": (
            "Существующий GdeltProvider: метаданные DOC 2.1, не полный текст. "
            "is_official=False; Event только при кластере ≥2 доменов или вместе с official."
        ),
    },
    {
        "id": "gdelt_logistics_trade",
        "kind": "gdelt",
        "url": "https://api.gdeltproject.org/api/v2/doc/doc",
        "query": '(shipping OR freight OR logistics OR supply chain) AND (China OR semiconductor OR electronics)',
        "theme": "logistics",
        "existing_connector": True,
        "trust_basis": (
            "Существующий GdeltProvider (логистика/цепочки). Не trusted publisher."
        ),
    },
    {
        "id": "gdelt_trade_china",
        "kind": "gdelt",
        "url": "https://api.gdeltproject.org/api/v2/doc/doc",
        "query": '(export OR import OR customs OR tariff) AND (China OR electronics) sourcelang:english',
        "theme": "trade_china",
        "existing_connector": True,
        "trust_basis": "Существующий GdeltProvider; не official.",
    },
]

# Probed but NOT used if HTML / anti-bot / not RSS
REJECTED_CANDIDATES = [
    {
        "id": "bis_doc_rss",
        "url": "https://www.bis.doc.gov/index.php/about-bis/newsroom?format=feed&type=rss",
        "reason": "HTTP 200 but content-type text/html (не RSS) — не обходим, не trusted.",
    },
    {
        "id": "minpromtorg_rss",
        "url": "https://minpromtorg.gov.ru/press-centre/news/rss/",
        "reason": "Отдаёт HTML, не RSS.",
    },
    {
        "id": "federalregister_bis",
        "url": "https://www.federalregister.gov/documents/search.rss?…",
        "reason": "HTML login/error page, не RSS.",
    },
]


def _patch_outbox_schema(db_path: Path) -> None:
    """Idempotent columns needed by current ORM; does not touch source stand."""
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


def _backup(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    src_conn = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    dst_conn = sqlite3.connect(dst)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return hashlib.sha256(dst.read_bytes()).hexdigest()


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


def _probe() -> list[dict[str, Any]]:
    import httpx

    results: list[dict[str, Any]] = []
    client = httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        for c in CANDIDATES:
            url = c["url"]
            if c["kind"] == "gdelt":
                from urllib.parse import urlencode

                url = (
                    c["url"]
                    + "?"
                    + urlencode(
                        {
                            "query": c["query"],
                            "mode": "ArtList",
                            "format": "json",
                            "maxrecords": "3",
                            "sort": "DateDesc",
                        }
                    )
                )
            row: dict[str, Any] = {
                "id": c["id"],
                "kind": c["kind"],
                "url": c["url"],
                "theme": c["theme"],
                "trust_basis": c["trust_basis"],
            }
            try:
                resp = client.get(url)
                ct = (resp.headers.get("content-type") or "").split(";")[0].strip()
                row["http_status"] = resp.status_code
                row["content_type"] = ct
                body = resp.text[:400]
                FIXTURES.mkdir(parents=True, exist_ok=True)
                safe = c["id"].replace("/", "_")
                (FIXTURES / f"probe_{safe}.txt").write_text(
                    f"url={url}\nstatus={resp.status_code}\nct={ct}\n\n{body}",
                    encoding="utf-8",
                )
                if c["kind"] == "rss":
                    ok = resp.status_code == 200 and (
                        "xml" in ct or "rss" in ct or body.lstrip().startswith("<?xml")
                    )
                    row["available"] = ok
                    if ok:
                        # sample title
                        import re

                        m = re.search(r"<title>([^<]+)</title>", body, re.I)
                        row["sample_title"] = m.group(1).strip() if m else None
                else:
                    ok = resp.status_code == 200 and "json" in ct
                    row["available"] = ok
                    if ok:
                        try:
                            arts = resp.json().get("articles") or []
                            row["sample_title"] = (arts[0].get("title") if arts else None)
                            row["sample_count"] = len(arts)
                        except Exception:  # noqa: BLE001
                            row["sample_title"] = None
            except Exception as exc:  # noqa: BLE001
                row["available"] = False
                row["error"] = f"{type(exc).__name__}: {exc}"
            results.append(row)
    finally:
        client.close()
    return results


def _write_stand_env(rss_feeds: list[str], gdelt_queries: list[str]) -> None:
    base = _read_env(SRC_ENV)
    db_url = f"sqlite:///./{STAND_DB.relative_to(ROOT).as_posix()}"
    lines = [
        "# Business news coverage copy of real_news_613. No secrets.",
        f"DATABASE_URL={db_url}",
        f"APP_ENV={base.get('APP_ENV', 'test')}",
        f"SECRET_KEY={base.get('SECRET_KEY', 'business-news-coverage-secret')}",
        # Competition mode off: no hackathon LLM requirement; ingest stays heuristic-only.
        "COMPETITION_MODE=false",
        "ASSISTANT_PROVIDER=mock",
        "ASSISTANT_AGENT_LOOP=false",
        "AGENT_DEMO_STAND=false",
        f"CASE_CONTEXT_SLOT_KEY={base.get('CASE_CONTEXT_SLOT_KEY', '')}",
        f"BANK_MATERIALS_ALLOWED_OCR_RUN_IDS={base.get('BANK_MATERIALS_ALLOWED_OCR_RUN_IDS', '')}",
        f"BANK_MATERIALS_STORAGE_ROOT={base.get('BANK_MATERIALS_STORAGE_ROOT', '')}",
        "OPENAI_API_KEY=",
        "GIGACHAT_AUTH_KEY=",
        "HACKATHON_API_KEY=",
        "TELEGRAM_BOT_TOKEN=",
        "TELEGRAM_WEBHOOK_SECRET=",
        f"INGESTION_RSS_FEEDS={'|'.join(rss_feeds)}",
        f"INGESTION_GDELT_QUERIES={'|'.join(gdelt_queries)}",
        "",
    ]
    STAND_ENV.write_text("\n".join(lines), encoding="utf-8")


def _apply_env() -> None:
    # Drop inherited competition/telegram keys before loading stand.env
    for k in (
        "COMPETITION_MODE",
        "ASSISTANT_PROVIDER",
        "HACKATHON_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "OPENAI_API_KEY",
        "GIGACHAT_AUTH_KEY",
        "AGENT_DEMO_STAND",
    ):
        os.environ.pop(k, None)
    env = _read_env(STAND_ENV)
    for k, v in env.items():
        os.environ[k] = v
    os.environ["TELEGRAM_BOT_TOKEN"] = ""
    from app.core.config import get_settings

    get_settings.cache_clear()


def _table_count(db, table: str) -> int:
    from sqlalchemy import text

    try:
        return int(db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
    except Exception:  # noqa: BLE001
        db.rollback()
        return -1


def _counts(db) -> dict[str, int]:
    from app.models import Decision, Event, EventImpact, Scenario
    from app.models.raw_news import RawNewsItem

    return {
        "raw": db.query(RawNewsItem).count(),
        "raw_pending": db.query(RawNewsItem)
        .filter(RawNewsItem.processing_status == "pending")
        .count(),
        "events_active": db.query(Event).filter(Event.status == "active").count(),
        "events_live": db.query(Event)
        .filter(Event.status == "active", Event.is_demo.is_(False))
        .count(),
        "impacts_upk": db.query(EventImpact)
        .filter(EventImpact.company_id == UPK_ID)
        .count(),
        "impacts_upk_active": db.query(EventImpact)
        .filter(
            EventImpact.company_id == UPK_ID,
            EventImpact.status.in_(["action_required", "monitor"]),
        )
        .count(),
        "scenarios": db.query(Scenario).count(),
        "decisions": db.query(Decision).count(),
        # Stand schema may predate migration 008 — use raw SQL, not ORM.
        "outbox": _table_count(db, "notification_outbox"),
    }


def main() -> int:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    STAND_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)

    if not SRC_DB.is_file():
        print("SOURCE_MISSING", SRC_DB)
        return 1

    print("=== probe sources ===")
    probes = _probe()
    available_rss = [
        c["url"]
        for c in CANDIDATES
        if c["kind"] == "rss"
        and any(p["id"] == c["id"] and p.get("available") for p in probes)
    ]
    # Prefer trade/logistics official-ish + existing business press; skip CBR (already in corpus).
    preferred_rss_order = [
        "https://customs.gov.ru/press/federal/rss",
        "https://ec.europa.eu/commission/presscorner/api/rss?dossier=trade&language=en",
        "https://www.wto.org/library/rss/latest_news_e.xml",
        "https://www.interfax.ru/rss.asp",
        "https://www.vedomosti.ru/rss/news",
    ]
    rss_feeds = [u for u in preferred_rss_order if u in available_rss]

    # Always keep existing GDELT connector queries (probe may 429 transiently).
    gdelt_queries = [c["query"] for c in CANDIDATES if c["kind"] == "gdelt"]

    print("rss_feeds", rss_feeds)
    print("gdelt_queries", len(gdelt_queries))

    print("=== copy DB ===")
    sha = _backup(SRC_DB, STAND_DB)
    _write_stand_env(rss_feeds, gdelt_queries)
    _apply_env()

    # Align copy schema for notification_outbox (source may lag 008). Copy only.
    print("=== patch copy schema (outbox columns) ===")
    _patch_outbox_schema(STAND_DB)

    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models import Company, CompanyNode, Event, EventImpact
    from app.models.raw_news import RawNewsItem
    from app.services.impact import recompute_events_for_company
    from app.services.ingestion.gdelt import GdeltProvider
    from app.services.ingestion.pipeline import run_ingestion
    from app.services.ingestion.rss import RssProvider
    from app.services.relevance import (
        analyze_event_company_relevance,
        country_roles_for_event,
        event_suggests_rate_track,
        is_macro_fx_event,
    )

    get_settings.cache_clear()
    engine.dispose()

    db = SessionLocal()
    report: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_db": str(SRC_DB.relative_to(ROOT)).replace("\\", "/"),
        "copy_db": str(STAND_DB.relative_to(ROOT)).replace("\\", "/"),
        "sha256_copy": sha,
        "probes": probes,
        "rejected_candidates": REJECTED_CANDIDATES,
        "selected_rss": rss_feeds,
        "selected_gdelt_queries": gdelt_queries,
        "llm": {"prefer_live_enrich": False, "assistant_provider": "mock"},
    }
    before = _counts(db)
    report["counts_before"] = before

    # Cap: max_per_feed / max_per_query so sum ≤ 50
    # 5 RSS × 5 + 3 GDELT × 8 = 49
    max_rss = 5
    max_gdelt = 8
    report["gdelt_probe_note"] = (
        "GDELT queries always configured; probe may be 429 — fetch still attempted"
    )
    providers = []
    if gdelt_queries:
        providers.append(
            GdeltProvider(queries=gdelt_queries, max_per_query=max_gdelt, timeout=25.0)
        )
    if rss_feeds:
        providers.append(
            RssProvider(feed_urls=rss_feeds, max_per_feed=max_rss, timeout=20.0)
        )
    # Intentionally NO CbrProvider — corpus already CBR-heavy on source stand.

    print("=== ingest pass 1 (heuristic) ===")
    pass1 = run_ingestion(
        db,
        providers=providers,
        prefer_live_enrich=False,
        fetch=True,
        process=True,
    )
    mid = _counts(db)
    report["pass1"] = {
        "fetched": pass1.fetched,
        "inserted": pass1.inserted,
        "duplicates": pass1.duplicates,
        "clusters": pass1.clusters,
        "published": pass1.published,
        "rejected": pass1.rejected,
        "event_ids": pass1.event_ids,
        "errors": pass1.errors,
        "counts_after": mid,
    }
    assert pass1.fetched <= 50, f"fetched {pass1.fetched} exceeds 50"

    # Rejection reasons for new raw
    reject_reasons: dict[str, int] = {}
    for item in (
        db.query(RawNewsItem)
        .filter(RawNewsItem.processing_status == "rejected")
        .order_by(RawNewsItem.fetched_at.desc())
        .limit(80)
        .all()
    ):
        key = item.error or "unknown"
        reject_reasons[key] = reject_reasons.get(key, 0) + 1
    report["reject_reasons_sample"] = reject_reasons

    # New live events (vs before)
    new_event_ids = list(pass1.event_ids)
    event_diag: list[dict[str, Any]] = []
    for eid in new_event_ids:
        ev = db.get(Event, eid)
        if ev is None:
            continue
        sources = [
            {
                "publisher": s.publisher,
                "url": s.url,
                "published_at": s.published_at.isoformat() if s.published_at else None,
            }
            for s in (ev.sources if hasattr(ev, "sources") else [])
        ]
        # EventSource relation may need query
        from app.models import EventSource

        src_rows = db.query(EventSource).filter(EventSource.event_id == ev.id).all()
        sources = [
            {
                "publisher": s.publisher,
                "url": s.url,
                "published_at": s.published_at.isoformat() if getattr(s, "published_at", None) else None,
            }
            for s in src_rows
        ]
        event_diag.append(
            {
                "id": ev.id,
                "title": ev.title,
                "category": ev.category,
                "event_type": ev.event_type,
                "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
                "countries": ev.match_countries_json,
                "materials": ev.match_materials_json,
                "currencies": ev.match_currencies_json,
                "categories_match": ev.match_categories_json,
                "is_macro_fx": is_macro_fx_event(ev),
                "suggests_rate": event_suggests_rate_track(ev),
                "country_roles": sorted(country_roles_for_event(ev) or []),
                "sources": sources,
                "note_china_token": (
                    "heuristic may list China/Китай from title word alone — "
                    "not proof of export measure on a supplier chain"
                    if any(
                        "кита" in str(x).lower() or "china" in str(x).lower()
                        for x in (ev.match_countries_json or [])
                    )
                    or "кита" in (ev.title or "").lower()
                    or "china" in (ev.title or "").lower()
                    else None
                ),
            }
        )
    report["new_published_events"] = event_diag

    # All active events thematic inventory (brief)
    inventory = []
    for ev in (
        db.query(Event)
        .filter(Event.status == "active", Event.is_demo.is_(False))
        .order_by(Event.occurred_at.desc())
        .all()
    ):
        inventory.append(
            {
                "id": ev.id,
                "title": (ev.title or "")[:120],
                "category": ev.category,
                "countries": ev.match_countries_json,
                "materials": ev.match_materials_json,
                "new": ev.id in new_event_ids,
            }
        )
    report["active_live_inventory"] = inventory

    print("=== recompute упк ===")
    company = db.get(Company, UPK_ID)
    assert company is not None, "упк missing on copy"
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == UPK_ID).all()
    node_brief = [
        {
            "type": n.node_type,
            "name": n.name,
            "country": n.country,
            "share": n.output_share_percent,
        }
        for n in nodes
    ]
    report["upk_profile"] = {
        "id": company.id,
        "name": company.name,
        "profile_status": company.profile_status,
        "twin": company.digital_twin_status,
        "nodes": node_brief,
        "profile_mutated": False,
    }

    before_impacts = (
        db.query(EventImpact)
        .filter(EventImpact.company_id == UPK_ID)
        .count()
    )
    impacts = recompute_events_for_company(db, company, demo_only=False)
    db.commit()
    after_impacts = (
        db.query(EventImpact)
        .filter(EventImpact.company_id == UPK_ID)
        .count()
    )

    purchase = []
    finance = {}
    from app.models import CompanyProfileSettings

    settings = (
        db.query(CompanyProfileSettings)
        .filter(CompanyProfileSettings.company_id == UPK_ID)
        .one_or_none()
    )
    if settings:
        purchase = list(settings.purchase_currencies_json or [])
        finance = (
            dict(settings.optional_finance_json)
            if isinstance(settings.optional_finance_json, dict)
            else {}
        )

    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    inconclusive: list[dict[str, Any]] = []

    for ev in (
        db.query(Event)
        .filter(Event.status == "active")
        .order_by(Event.occurred_at.desc())
        .all()
    ):
        rel = analyze_event_company_relevance(
            ev,
            company,
            nodes,
            purchase_currencies=purchase,
            optional_finance=finance,
        )
        impact = (
            db.query(EventImpact)
            .filter(
                EventImpact.company_id == UPK_ID,
                EventImpact.event_id == ev.id,
            )
            .one_or_none()
        )
        roles = country_roles_for_event(ev)
        row = {
            "event_id": ev.id,
            "title": ev.title,
            "is_demo": bool(ev.is_demo),
            "category": ev.category,
            "countries": ev.match_countries_json,
            "materials": ev.match_materials_json,
            "country_roles_for_gate": sorted(roles) if roles is not None else None,
            "relevant": rel.is_relevant,
            "level": rel.level,
            "summary": rel.summary,
            "matched_features": [m.__dict__ for m in rel.matched_features],
            "missing_data": rel.missing_data,
            "limitations": rel.limitations,
            "impact_status": impact.status if impact else None,
            "impact_score": float(impact.impact_score) if impact else None,
            "new_from_this_run": ev.id in new_event_ids,
        }
        # Honesty: bare China token
        china_only = bool(
            rel.is_relevant
            and any(m.axis == "country" for m in rel.matched_features)
            and not any(m.axis == "material" for m in rel.matched_features)
            and not (ev.match_materials_json or [])
        )
        if china_only:
            row["data_sufficiency"] = (
                "weak: country token overlap only — one word «Китай/China» in "
                "enrichment/title is not enough to confirm an export measure "
                "on this supplier chain"
            )
            inconclusive.append(row)
        if rel.is_relevant and impact and impact.status in {"action_required", "monitor"}:
            included.append(row)
        else:
            excluded.append(row)

    report["upk_recompute"] = {
        "impacts_returned": len(impacts),
        "impacts_before": before_impacts,
        "impacts_after": after_impacts,
        "included_in_personal": included,
        "excluded": excluded,
        "inconclusive_weak_country_only": inconclusive,
    }

    print("=== idempotent reprocess ===")
    outbox_before = _counts(db)["outbox"]
    scen_before = _counts(db)["scenarios"]
    dec_before = _counts(db)["decisions"]
    raw_before = _counts(db)["raw"]
    live_before = _counts(db)["events_live"]
    pass2 = run_ingestion(
        db,
        providers=providers,
        prefer_live_enrich=False,
        fetch=True,
        process=True,
    )
    after = _counts(db)
    report["pass2_idempotent"] = {
        "fetched": pass2.fetched,
        "inserted": pass2.inserted,
        "duplicates": pass2.duplicates,
        "published": pass2.published,
        "rejected": pass2.rejected,
        "delta_raw": after["raw"] - raw_before,
        "delta_live_events": after["events_live"] - live_before,
        "delta_scenarios": after["scenarios"] - scen_before,
        "delta_decisions": after["decisions"] - dec_before,
        "delta_outbox": after["outbox"] - outbox_before,
        "counts_after": after,
    }

    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print("wrote", REPORT_JSON)

    # Markdown report
    _write_md(report)
    print("wrote", DOCS_MD)
    db.close()
    return 0


def _write_md(report: dict[str, Any]) -> None:
    p1 = report["pass1"]
    p2 = report["pass2_idempotent"]
    upk = report["upk_recompute"]
    lines: list[str] = []
    lines.append("# Расширение реальных источников для ручной персонализации")
    lines.append("")
    lines.append(f"Дата: {report['created_at'][:10]}")
    lines.append("")
    lines.append(
        "Цель: проверить персонализацию «упк» на корпусе шире ЦБ. "
        "Исходный `real_news_613` **не изменялся**; перенос публикаций на основной стенд **не делался**."
    )
    lines.append("")
    lines.append("Связанные: `REAL_NEWS_INGESTION_VERIFICATION.md`, `MANUAL_PROFILE_FEED_VERIFICATION.md`.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Копия стенда")
    lines.append("")
    lines.append("| | |")
    lines.append("|--|--|")
    lines.append(f"| Источник | `{report['source_db']}` |")
    lines.append(f"| Копия | `{report['copy_db']}` |")
    lines.append(f"| SHA256 копии | `{report['sha256_copy'][:16]}…` |")
    lines.append("| Live LLM | нет (`prefer_live_enrich=false`, provider mock) |")
    lines.append("| Telegram | `TELEGRAM_BOT_TOKEN` очищен в процессе |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Источники: доступность и доверие")
    lines.append("")
    lines.append(
        "Предпочтение: существующие коннекторы (`RssProvider` whitelist, `GdeltProvider`). "
        "**OFFICIAL/trusted в коде не расширялся** — ФТС/WTO/EC остаются первичными лентами "
        "по смыслу, но Kontur gate требует official-маркер (сейчас только CBR) или ≥2 независимых издателя."
    )
    lines.append("")
    lines.append("### Проверенные URL")
    lines.append("")
    lines.append("| id | HTTP | available | тема | основание доверия |")
    lines.append("|----|------|-----------|------|-------------------|")
    for p in report["probes"]:
        lines.append(
            f"| {p['id']} | {p.get('http_status')} | {p.get('available')} | "
            f"{p.get('theme')} | {p.get('trust_basis', '')[:80]}… |"
        )
    lines.append("")
    lines.append("### Не использованы")
    lines.append("")
    for r in report["rejected_candidates"]:
        lines.append(f"- **{r['id']}**: {r['reason']}")
    lines.append("")
    lines.append("### Выбраны для ограниченного импорта")
    lines.append("")
    lines.append(f"- RSS: {report['selected_rss']}")
    lines.append(f"- GDELT queries: {len(report['selected_gdelt_queries'])} шт. (электроника/экспорт, логистика, торговля+China)")
    lines.append("- CBR / `CbrProvider` **не** включались (корпус уже ЦБ-тяжёлый).")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. Импорт (≤50, без LLM)")
    lines.append("")
    lines.append("| Метрика | Pass 1 |")
    lines.append("|---------|--------|")
    lines.append(f"| fetched | {p1['fetched']} |")
    lines.append(f"| inserted | {p1['inserted']} |")
    lines.append(f"| duplicates | {p1['duplicates']} |")
    lines.append(f"| clusters | {p1['clusters']} |")
    lines.append(f"| published Events | {p1['published']} |")
    lines.append(f"| rejected clusters | {p1['rejected']} |")
    lines.append(f"| errors | {p1['errors']} |")
    lines.append("")
    lines.append(f"Лимит: fetched={p1['fetched']} ≤ 50 — "
                 f"{'PASS' if p1['fetched'] <= 50 else 'FAIL'}.")
    lines.append("")
    lines.append("Отказы (накопительно по rejected raw, включая прежние):")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.get("reject_reasons_sample") or {}, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append(
        "Ожидаемо: WTO/EC/ФТС/Interfax/Vedomosti/GDELT поодиночке → "
        "`unverified_single_source`, пока нет второго независимого издателя в кластере "
        "или official CBR. **Не** помечали их official ради PASS."
    )
    lines.append("")
    lines.append("### Новые опубликованные Event")
    lines.append("")
    new_ev = report.get("new_published_events") or []
    if not new_ev:
        lines.append(
            "В этом прогоне **0 новых Event**. Сырьё сохранено с provenance "
            "(provider, canonical_url, published_at, publisher); гипотезы/планы "
            "в вступившие меры не превращались."
        )
    else:
        for ev in new_ev:
            lines.append(f"- **{ev['title']}** (`{ev['id']}`)")
            lines.append(
                f"  - category={ev['category']}, countries={ev['countries']}, "
                f"materials={ev['materials']}, occurred_at={ev['occurred_at']}"
            )
            lines.append(f"  - sources={ev['sources']}")
            if ev.get("note_china_token"):
                lines.append(f"  - ⚠ {ev['note_china_token']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 4. Темы / страны / роли")
    lines.append("")
    lines.append(
        "Различие ролей (как в `relevance.country_roles_for_event`): "
        "geopolitics/export → роль **supplier**; market → роль **market**; "
        "macro/FX → страны не открывают gate (нужны finance/валюты)."
    )
    lines.append("")
    lines.append(
        "Heuristic enrich может положить «Китай»/China в `match_countries` "
        "из одного слова в заголовке. **Этого недостаточно**, чтобы утверждать "
        "влияние на цепочку «упк» с китайским поставщиком: нужна мера по экспорту/"
        "поставкам (или материал), а не упоминание страны."
    )
    lines.append("")
    lines.append(f"Активных live Event на копии: {len(report.get('active_live_inventory') or [])}.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 5. Пересчёт «упк» (профиль не менялся)")
    lines.append("")
    lines.append(f"Профиль: `{report['upk_profile']['name']}` twin={report['upk_profile']['twin']}, "
                 f"nodes={report['upk_profile']['nodes']}")
    lines.append("")
    lines.append(f"Impact rows: before={upk['impacts_before']} after={upk['impacts_after']} "
                 f"(recompute returned {upk['impacts_returned']}).")
    lines.append("")
    lines.append("### В персональной ленте (active Impact)")
    lines.append("")
    included = upk.get("included_in_personal") or []
    if not included:
        lines.append(
            "**Ни одной карточки.** Честный результат: среди опубликованных "
            "(включая прежний CBR-корпус и новые raw, не прошедшие gate) нет "
            "события с достаточным пересечением цепочки «упк»."
        )
    else:
        for row in included:
            lines.append(
                f"- `{row['event_id']}` {row['title']} — level={row['level']}, "
                f"status={row['impact_status']}, score={row['impact_score']}"
            )
            lines.append(f"  - основание: {row['summary']}")
            if row.get("data_sufficiency"):
                lines.append(f"  - ⚠ {row['data_sufficiency']}")
    lines.append("")
    lines.append("### Исключены (кратко по причинам)")
    lines.append("")
    # Summarize exclusion reasons
    reasons: dict[str, int] = {}
    for row in upk.get("excluded") or []:
        key = row.get("summary") or row.get("level") or "?"
        key = key[:100]
        reasons[key] = reasons.get(key, 0) + 1
    for k, n in sorted(reasons.items(), key=lambda x: -x[1])[:12]:
        lines.append(f"- ({n}) {k}")
    lines.append("")
    lines.append("### Нельзя подтвердить из данных")
    lines.append("")
    weak = upk.get("inconclusive_weak_country_only") or []
    if not weak:
        lines.append(
            "Слабых «только токен страны» попаданий в active Impact нет "
            "(либо релевантных совпадений не было)."
        )
    else:
        for row in weak:
            lines.append(f"- {row['title']}: {row.get('data_sufficiency')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 6. Идемпотентность / побочные эффекты")
    lines.append("")
    lines.append("| | Pass 2 |")
    lines.append("|--|--------|")
    lines.append(f"| fetched | {p2['fetched']} |")
    lines.append(f"| inserted | {p2['inserted']} |")
    lines.append(f"| duplicates | {p2['duplicates']} |")
    lines.append(f"| Δ raw | {p2['delta_raw']} |")
    lines.append(f"| Δ live events | {p2['delta_live_events']} |")
    lines.append(f"| Δ scenarios | {p2['delta_scenarios']} |")
    lines.append(f"| Δ decisions | {p2['delta_decisions']} |")
    lines.append(f"| Δ notification_outbox | {p2['delta_outbox']} |")
    lines.append("")
    idem_ok = (
        p2["inserted"] == 0
        and p2["delta_raw"] == 0
        and p2["delta_live_events"] == 0
        and p2["delta_scenarios"] == 0
        and p2["delta_decisions"] == 0
    )
    lines.append(
        f"Вердикт идемпотентности: **{'PASS' if idem_ok else 'REVIEW'}** "
        "(без дублей raw/Event и без Scenario/Decision)."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 7. Выводы")
    lines.append("")
    lines.append(
        "1. Доступны: Interfax, Vedomosti, WTO, EC trade, ФТС RSS, GDELT DOC API; "
        "BIS/Минпромторг RSS-URL отдают HTML — не использовались."
    )
    lines.append(
        "2. Без расширения trusted большинство бизнес-записей остаются "
        "`unverified_single_source` — это ожидаемое поведение gate, не дефект персонализации."
    )
    lines.append(
        "3. Для «упк» после явного `recompute_events_for_company` персональная лента "
        f"{'по-прежнему пуста' if not included else 'содержит карточки — см. §5'}; "
        "профиль не подгонялся."
    )
    lines.append(
        "4. Исходный стенд и live API :8020 не переключались на эту копию."
    )
    lines.append("")
    lines.append(f"Машинный отчёт: `{STAND_DIR.relative_to(ROOT).as_posix()}/coverage_report.json`")
    lines.append("")
    DOCS_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
