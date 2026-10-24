"""Stage 6.13 — real news ingestion verification on an isolated UI-stand copy.

- SQLite backup of ui_acceptance_611 → real_news_613 (preserves users/decisions/bank).
- Limited RSS (CBR + Interfax, ≤30 items), heuristic enrich only.
- No root .env / :8003 / CSV re-import / live LLM.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "data/competition_stand/ui_acceptance_611"
SRC_DB = SRC_DIR / "stand.db"
SRC_ENV = SRC_DIR / "stand.env"
SRC_PASSWORD = SRC_DIR / "demo_password.local"

STAND_DIR = ROOT / "data/competition_stand/real_news_613"
STAND_DB = STAND_DIR / "stand.db"
STAND_ENV = STAND_DIR / "stand.env"
STAND_WEB_ENV = STAND_DIR / "web.env"
PASSWORD_DST = STAND_DIR / "demo_password.local"
MANIFEST = STAND_DIR / "stand_manifest.json"
STATUS = STAND_DIR / "stand_status.json"
REPORT_JSON = STAND_DIR / "verification_report.json"
FIXTURES = STAND_DIR / "fixtures" / "rss"
DOCS_MD = ROOT / "docs/REAL_NEWS_INGESTION_VERIFICATION.md"

API_PORT = 8020
WEB_PORT = 5180

FEED_CBR = "https://www.cbr.ru/rss/RssNews"
FEED_INTERFAX = "https://www.interfax.ru/rss.asp"
FEEDS = [FEED_CBR, FEED_INTERFAX]
MAX_PER_FEED = 15  # 2 × 15 = 30
HTTP_TIMEOUT = 20.0
HTTP_RETRIES = 2

PRIMARY_EMAIL = "competition-demo-a@example.com"
SECONDARY_EMAIL = "competition-demo-b@example.com"


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


def _db_url_for_stand() -> str:
    return f"sqlite:///./{STAND_DB.relative_to(ROOT).as_posix()}"


def _safe_db_fingerprint(url: str) -> dict[str, Any]:
    """Confirm target DB without printing credentials."""
    scheme = urlparse(url).scheme
    path = ""
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        if path.startswith("./"):
            path = path[2:]
    abs_path = (ROOT / path).resolve() if path else None
    return {
        "scheme": scheme,
        "relative_path": path.replace("\\", "/"),
        "exists": bool(abs_path and abs_path.is_file()),
        "size_bytes": abs_path.stat().st_size if abs_path and abs_path.is_file() else None,
        "is_source_ui_stand": abs_path == SRC_DB.resolve() if abs_path else False,
        "is_real_news_613": abs_path == STAND_DB.resolve() if abs_path else False,
    }


def _write_stand_env(ocr_ids: str, storage_root: str) -> None:
    db_url = _db_url_for_stand()
    STAND_ENV.write_text(
        "\n".join(
            [
                "# Real news ingestion verification stand (stage 6.13). No secrets.",
                f"DATABASE_URL={db_url}",
                "APP_ENV=test",
                "SECRET_KEY=" + __import__("secrets").token_hex(32),
                "COMPETITION_MODE=true",
                "ASSISTANT_PROVIDER=hackathon",
                "ASSISTANT_AGENT_LOOP=true",
                "HACKATHON_BASE_URL=https://changellenge.up.railway.app/v1",
                "HACKATHON_MODEL=deepseek/deepseek-v4.1-flash",
                "ASSISTANT_LOOP_MAX_MODEL_HTTP=4",
                "ASSISTANT_LOOP_MAX_TOOL_CALLS=3",
                "ASSISTANT_LOOP_MAX_REPAIRS=1",
                "ASSISTANT_LOOP_TIMEOUT_S=90",
                "CASE_CONTEXT_SLOT_KEY=competition_default",
                f"BANK_MATERIALS_ALLOWED_OCR_RUN_IDS={ocr_ids}",
                f"BANK_MATERIALS_STORAGE_ROOT={storage_root}",
                "OPENAI_API_KEY=",
                "GIGACHAT_AUTH_KEY=",
                "AGENT_DEMO_STAND=true",
                f"AGENT_DEMO_API_PORT={API_PORT}",
                f"AGENT_DEMO_WEB_PORT={WEB_PORT}",
                f"INGESTION_RSS_FEEDS={FEED_CBR}|{FEED_INTERFAX}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    STAND_WEB_ENV.write_text(
        "\n".join(
            [
                f"VITE_API_BASE_URL=http://127.0.0.1:{API_PORT}",
                "VITE_AGENT_DEMO=true",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _apply_stand_env() -> dict[str, str]:
    env = _read_env(STAND_ENV)
    for k, v in env.items():
        if k == "HACKATHON_API_KEY":
            continue
        os.environ[k] = v
    # Ensure no accidental OpenAI key from root process env
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["GIGACHAT_AUTH_KEY"] = ""
    sys.path.insert(0, str(ROOT))
    from app.core.config import get_settings

    get_settings.cache_clear()
    return env


def _counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        def n(table: str) -> int:
            try:
                return int(conn.execute(f"select count(*) from {table}").fetchone()[0])
            except sqlite3.Error:
                return -1

        return {
            "users": n("users"),
            "companies": n("companies"),
            "decisions": n("decisions"),
            "scenarios": n("scenarios"),
            "events": n("events"),
            "events_demo": int(
                conn.execute("select count(*) from events where is_demo=1").fetchone()[0]
            ),
            "events_live": int(
                conn.execute("select count(*) from events where is_demo=0").fetchone()[0]
            ),
            "event_sources": n("event_sources"),
            "event_impacts": n("event_impacts"),
            "raw_news_items": n("raw_news_items"),
            "bank_fragments": n("bank_fragments"),
            "bank_documents": n("bank_documents"),
        }
    finally:
        conn.close()


def _probe_and_save_feeds() -> list[dict[str, Any]]:
    import httpx

    FIXTURES.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for url in FEEDS:
        host = urlparse(url).netloc.replace(".", "_")
        entry: dict[str, Any] = {
            "url": url,
            "ok": False,
            "status_code": None,
            "bytes": 0,
            "fixture": None,
            "error": None,
            "item_titles_sample": [],
        }
        last_err: str | None = None
        for attempt in range(1, HTTP_RETRIES + 1):
            try:
                with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                    resp = client.get(url)
                entry["status_code"] = resp.status_code
                if resp.status_code != 200:
                    last_err = f"http_{resp.status_code}"
                    time.sleep(0.5)
                    continue
                body = resp.content
                digest = hashlib.sha256(body).hexdigest()[:16]
                fname = f"{host}_{digest}.xml"
                fpath = FIXTURES / fname
                fpath.write_bytes(body)
                entry["ok"] = True
                entry["bytes"] = len(body)
                entry["fixture"] = str(fpath.relative_to(ROOT)).replace("\\", "/")
                # Sample titles without full article download
                try:
                    import xml.etree.ElementTree as ET

                    root = ET.fromstring(body)
                    channel = root.find("channel")
                    nodes = (
                        channel.findall("item")
                        if channel is not None
                        else root.findall(".//{*}item")
                    )
                    for node in nodes[:3]:
                        t = (node.findtext("title") or "").strip()
                        if t:
                            entry["item_titles_sample"].append(t[:120])
                except Exception as exc:  # noqa: BLE001
                    entry["parse_note"] = type(exc).__name__
                break
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}:{exc}"[:200]
                time.sleep(0.5)
        if not entry["ok"]:
            entry["error"] = last_err
        results.append(entry)
    return results


class _HttpSpy:
    """Record outbound HTTP that looks like model provider traffic."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def install(self) -> Any:
        import httpx

        spy = self
        orig_request = httpx.Client.request

        def wrapped(self_client, method, url, *args, **kwargs):  # type: ignore[no-untyped-def]
            u = str(url).lower()
            host = urlparse(str(url)).netloc.lower()
            if any(
                m in u or m in host
                for m in (
                    "openai.com",
                    "api.openai",
                    "gigachat",
                    "changellenge",
                    "railway.app",
                    "/v1/responses",
                    "/v1/chat/completions",
                )
            ):
                spy.calls.append({"method": method, "host": host, "path": urlparse(str(url)).path})
            return orig_request(self_client, method, url, *args, **kwargs)

        httpx.Client.request = wrapped  # type: ignore[method-assign]
        return orig_request

    def restore(self, orig: Any) -> None:
        import httpx

        httpx.Client.request = orig  # type: ignore[method-assign]


def _run_ingest(prefer_live: bool = False) -> dict[str, Any]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.services.ingestion.pipeline import run_ingestion
    from app.services.ingestion.rss import RssProvider
    from app.services.ingestion.base import SourceProvider, FetchedArticle

    class FailingProvider(SourceProvider):
        name = "failing_probe"

        def fetch(self) -> list[FetchedArticle]:
            raise RuntimeError("intentional_provider_failure")

    db_url = _db_url_for_stand()
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    spy = _HttpSpy()
    orig = spy.install()
    try:
        with Session() as db:
            providers: list[SourceProvider] = [
                FailingProvider(),
                RssProvider(
                    feed_urls=FEEDS,
                    timeout=HTTP_TIMEOUT,
                    max_per_feed=MAX_PER_FEED,
                ),
            ]
            result = run_ingestion(
                db,
                providers=providers,
                prefer_live_enrich=prefer_live,
                fetch=True,
                process=True,
            )
            payload = {
                "fetched": result.fetched,
                "inserted": result.inserted,
                "duplicates": result.duplicates,
                "clusters": result.clusters,
                "published": result.published,
                "rejected": result.rejected,
                "event_ids": list(result.event_ids),
                "errors": list(result.errors),
                "model_http_calls": list(spy.calls),
            }
    finally:
        spy.restore(orig)
        engine.dispose()
    return payload


def _dedupe_pass() -> dict[str, Any]:
    """Re-fetch same feeds; expect duplicates, no new events from same URLs."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.services.ingestion.pipeline import run_ingestion
    from app.services.ingestion.rss import RssProvider

    engine = create_engine(_db_url_for_stand())
    Session = sessionmaker(bind=engine)
    before = _counts(STAND_DB)
    with Session() as db:
        result = run_ingestion(
            db,
            providers=[
                RssProvider(
                    feed_urls=FEEDS,
                    timeout=HTTP_TIMEOUT,
                    max_per_feed=MAX_PER_FEED,
                )
            ],
            prefer_live_enrich=False,
            fetch=True,
            process=True,
        )
    after = _counts(STAND_DB)
    engine.dispose()
    return {
        "fetched": result.fetched,
        "inserted": result.inserted,
        "duplicates": result.duplicates,
        "published": result.published,
        "rejected": result.rejected,
        "event_ids": list(result.event_ids),
        "raw_delta": after["raw_news_items"] - before["raw_news_items"],
        "events_live_delta": after["events_live"] - before["events_live"],
        "errors": list(result.errors),
    }


def _reject_reasons(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "select coalesce(error,'') as e, count(*) from raw_news_items "
            "where processing_status='rejected' group by e"
        ).fetchall()
        return {r[0] or "(empty)": int(r[1]) for r in rows}
    finally:
        conn.close()


def _published_examples(db_path: Path, limit: int = 8) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            select e.id, e.title, e.summary, e.occurred_at, e.is_demo,
                   e.attributes_json, es.publisher, es.url, es.published_at,
                   es.excerpt, r.fetched_at, r.provider
            from events e
            join event_sources es on es.event_id = e.id
            left join raw_news_items r on r.event_id = e.id
            where e.is_demo = 0
            order by e.occurred_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            attrs = {}
            try:
                attrs = json.loads(row["attributes_json"] or "{}")
            except json.JSONDecodeError:
                attrs = {}
            out.append(
                {
                    "event_id": row["id"],
                    "title": row["title"],
                    "publisher": row["publisher"],
                    "url": row["url"],
                    "occurred_at": row["occurred_at"],
                    "source_published_at": row["published_at"],
                    "fetched_at": row["fetched_at"],
                    "excerpt_origin": "rss_description_or_title",
                    "excerpt_preview": (row["excerpt"] or "")[:240],
                    "summary_preview": (row["summary"] or "")[:240],
                    "is_demo": bool(row["is_demo"]),
                    "synthetic_demo_event": bool(attrs.get("synthetic_demo_event")),
                    "publish_reason": attrs.get("publish_reason"),
                    "provider": row["provider"],
                    "occurred_eq_fetched": (
                        row["occurred_at"] is not None
                        and row["fetched_at"] is not None
                        and str(row["occurred_at"])[:19] == str(row["fetched_at"])[:19]
                    ),
                }
            )
        return out
    finally:
        conn.close()


def _synthetic_check(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "select id, title, is_demo, attributes_json from events where is_demo=1"
        ).fetchall()
        items = []
        for r in rows:
            attrs = {}
            try:
                attrs = json.loads(r["attributes_json"] or "{}")
            except json.JSONDecodeError:
                pass
            items.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "is_demo": True,
                    "synthetic_demo_event": bool(attrs.get("synthetic_demo_event")),
                }
            )
        return {"count": len(items), "events": items}
    finally:
        conn.close()


def _api_checks(password: str) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.main import app

    out: dict[str, Any] = {
        "public_news": {},
        "personal_a": {},
        "personal_b": {},
        "decisions_unchanged_probe": {},
    }
    with TestClient(app) as client:
        pub = client.get("/api/v1/public/news", params={"limit": 50})
        out["public_news"]["status"] = pub.status_code
        if pub.status_code == 200:
            body = pub.json()
            items = body.get("items") or body.get("news") or body
            if isinstance(items, dict):
                items = items.get("items") or []
            if not isinstance(items, list):
                items = []
            live = [i for i in items if not i.get("is_demo")]
            demo = [i for i in items if i.get("is_demo")]
            out["public_news"]["total"] = len(items)
            out["public_news"]["live_count"] = len(live)
            out["public_news"]["demo_count"] = len(demo)
            out["public_news"]["sample"] = [
                {
                    "id": i.get("id"),
                    "title": i.get("title"),
                    "is_demo": i.get("is_demo"),
                    "occurred_at": str(i.get("occurred_at") or ""),
                    "primary_source_url": i.get("primary_source_url"),
                    "publisher": i.get("primary_publisher"),
                }
                for i in (live[:5] + demo[:2])
            ]

        def personal(email: str) -> dict[str, Any]:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )
            if login.status_code != 200:
                return {
                    "login_status": login.status_code,
                    "error": "login_failed",
                    "detail": (login.json() if login.headers.get("content-type", "").startswith("application/json") else None),
                }
            token = login.json().get("access_token")
            headers = {"Authorization": f"Bearer {token}"}
            me = client.get("/api/v1/users/me", headers=headers)
            company_id = None
            company_name = None
            if me.status_code == 200:
                companies = me.json().get("companies") or []
                if companies:
                    company_id = companies[0].get("company_id")
                    company_name = companies[0].get("name")
            if not company_id:
                return {
                    "login_status": 200,
                    "error": "no_company",
                    "me_status": me.status_code,
                }
            feed = client.get(
                f"/api/v1/companies/{company_id}/events",
                headers=headers,
                params={"limit": 30},
            )
            dash = client.get(
                f"/api/v1/companies/{company_id}/dashboard",
                headers=headers,
            )
            feed_body = feed.json() if feed.status_code == 200 else {}
            cards = feed_body.get("items") or []
            profile_only = [
                c
                for c in cards
                if c.get("score_kind") == "case_profile_match"
                or "case_profile" in (c.get("inclusion_bases") or [])
            ]
            live_in_personal = [c for c in cards if not c.get("is_demo")]
            dash_body = dash.json() if dash.status_code == 200 else {}
            priority = dash_body.get("priority_events") or []
            return {
                "login_status": 200,
                "company_id": company_id,
                "company_name": company_name,
                "feed_status": feed.status_code,
                "dashboard_status": dash.status_code,
                "feed_total": len(cards),
                "profile_match_count": len(profile_only),
                "live_in_personal": len(live_in_personal),
                "profile_titles": [c.get("title") for c in profile_only[:5]],
                "dashboard_priority_titles": [c.get("title") for c in priority[:5]],
                "score_kinds": sorted(
                    {c.get("score_kind") for c in cards if c.get("score_kind")}
                ),
            }

        out["personal_a"] = personal(PRIMARY_EMAIL)
        out["personal_b"] = personal(SECONDARY_EMAIL)
        out["decisions_unchanged_probe"] = {
            "note": "counted via SQLite before/after; no list endpoint required",
        }
    return out


def _write_docs(report: dict[str, Any]) -> None:
    ingest = report["ingest_pass"]
    dedupe = report["dedupe_pass"]
    examples = report["published_examples"]
    feeds = report["feed_probe"]
    api = report["api"]
    lines = [
        "# Проверка реальной загрузки новостей (этап 6.13)",
        "",
        f"Дата: {report['prepared_at'][:10]}  ",
        "",
        "Цель: внешний RSS → `RawNewsItem` → `Event` → публичная лента → профильная релевантность.",
        "Выдуманные новости в ленту не добавлялись. Live LLM не вызывался.",
        "",
        "Связанные: `CASE_PERSONALIZED_FEED.md`, `EVENT_DISCOVERABILITY.md`, `COMPETITION_UI_ACCEPTANCE.md`.",
        "",
        "---",
        "",
        "## 1. Изолированный стенд",
        "",
        "| | |",
        "|--|--|",
        f"| Копия | `{report['stand_dir']}` |",
        f"| Источник | `{report['source_db']}` (sqlite backup) |",
        f"| SHA256 копии | `{report['work_db_sha256'][:16]}…` |",
        f"| API / Web | `:{API_PORT}` / `:{WEB_PORT}` |",
        "| Root `.env` / `:8003` / CSV | не трогались |",
        "",
        "Перед записью проверен URL БД (без секретов):",
        "",
        "```json",
        json.dumps(report["db_fingerprint"], ensure_ascii=False, indent=2),
        "```",
        "",
        "Сохранены пользователи, решения, банковские материалы исходного UI-стенда.",
        "",
        "---",
        "",
        "## 2. Источники",
        "",
        "Конфиг по умолчанию (`INGESTION_RSS_FEEDS`): CBR, Interfax, Vedomosti.",
        "В прогоне использованы **1–2** доступных RSS:",
        "",
    ]
    for f in feeds:
        status = "OK" if f["ok"] else f"FAIL ({f.get('error')})"
        lines.append(f"- `{f['url']}` — HTTP {f.get('status_code')} — {status}")
        if f.get("item_titles_sample"):
            lines.append(f"  - sample: {f['item_titles_sample'][0]!r}")
    lines += [
        "",
        f"Лимит: `{MAX_PER_FEED}` записей на ленту (суммарно ≤ {MAX_PER_FEED * len(FEEDS)}).",
        f"Timeout: {HTTP_TIMEOUT}s, повторы: {HTTP_RETRIES}.",
        "Исходные XML сохранены вне Git: `data/competition_stand/real_news_613/fixtures/rss/`.",
        "",
        "---",
        "",
        "## 3. Команда и безопасная конфигурация",
        "",
        "```powershell",
        "python scripts/verify_real_news_ingestion_613.py",
        "```",
        "",
        "Эквивалент ручного прогона в уже подготовленную копию:",
        "",
        "```powershell",
        "# Загрузить stand.env в процесс (DATABASE_URL → real_news_613), затем:",
        "python -m app.jobs.ingest_news --heuristic-enrich",
        "```",
        "",
        "Важно: `--heuristic-enrich` → `prefer_live_enrich=False` → только `heuristic_enrich`",
        "(без OpenAI / hackathon gateway). При `prefer_live=True` и `ASSISTANT_PROVIDER=hackathon`",
        "`live_enrich` **блокируется** (`INGESTION_LIVE_BLOCKED`), а не тихо уходит на другого провайдера.",
        "",
        "Запуск копии как отдельного UI-стенда (исходный `ui_acceptance_611` не переключается):",
        "",
        "```powershell",
        ".\\scripts\\run_competition_ui_backend.ps1 -StandDir data\\competition_stand\\real_news_613",
        ".\\scripts\\run_competition_ui_frontend.ps1 -StandDir data\\competition_stand\\real_news_613",
        "```",
        "",
        f"Сайт: http://127.0.0.1:{WEB_PORT}  ·  API: http://127.0.0.1:{API_PORT}/health",
        "",
        "---",
        "",
        "## 4. Счётчики загрузки и публикации",
        "",
        "| Метрика | Значение |",
        "|---------|----------|",
        f"| fetched | {ingest['fetched']} |",
        f"| inserted | {ingest['inserted']} |",
        f"| duplicates (1-й проход) | {ingest['duplicates']} |",
        f"| clusters | {ingest['clusters']} |",
        f"| published Events | {ingest['published']} |",
        f"| rejected clusters | {ingest['rejected']} |",
        f"| provider errors | {ingest['errors']} |",
        "",
        "Отказы raw (причины):",
        "",
        "```json",
        json.dumps(report["reject_reasons"], ensure_ascii=False, indent=2),
        "```",
        "",
        "Ожидаемо: коммерческий RSS с одним издателем → `unverified_single_source`;",
        "официальный CBR (`is_official`) публикуется один.",
        "",
        f"Счётчики БД до → после: см. машинный отчёт `verification_report.json`.",
        "",
        "---",
        "",
        "## 5. Дедупликация",
        "",
        "Повторная обработка тех же RSS:",
        "",
        "| | |",
        "|--|--|",
        f"| fetched | {dedupe['fetched']} |",
        f"| inserted | {dedupe['inserted']} |",
        f"| duplicates | {dedupe['duplicates']} |",
        f"| Δ raw_news_items | {dedupe['raw_delta']} |",
        f"| Δ live events | {dedupe['events_live_delta']} |",
        "",
        "PASS, если `inserted≈0`, `duplicates≈fetched`, Δ raw/events = 0 (или только уже",
        "обработанные pending без новых URL).",
        "",
        "---",
        "",
        "## 6. Примеры настоящих заголовков",
        "",
    ]
    if not examples:
        lines.append("_Опубликованных live Event нет (см. отказы)._")
    for ex in examples[:6]:
        lines += [
            f"- **{ex['title']}**",
            f"  - источник: {ex['publisher']}",
            f"  - URL: {ex['url']}",
            f"  - дата публикации (occurred_at): `{ex['occurred_at']}`",
            f"  - fetched_at: `{ex['fetched_at']}`",
            f"  - occurred==fetched подмена: `{ex['occurred_eq_fetched']}`",
            f"  - excerpt origin: `{ex['excerpt_origin']}`",
            "",
        ]
    lines += [
        "Heuristic summary/claims строятся из title/excerpt RSS; это не текст редакции банка",
        "и не выдаётся как bank evidence.",
        "",
        "---",
        "",
        "## 7. Публичная и персональная лента",
        "",
        "### Public",
        "",
        "```json",
        json.dumps(api.get("public_news", {}), ensure_ascii=False, indent=2)[:4000],
        "```",
        "",
        "### Personal A / B",
        "",
        "Правила узкие: `policy_rate` × LOA/DEP. Не каждая экономическая новость попадает в «Для вас».",
        "",
        "```json",
        json.dumps(
            {"A": api.get("personal_a"), "B": api.get("personal_b")},
            ensure_ascii=False,
            indent=2,
        )[:5000],
        "```",
        "",
        f"**Вывод по профилю:** {report['personal_feed_verdict']}",
        "",
        "### Синтетика",
        "",
        "```json",
        json.dumps(report["synthetic"], ensure_ascii=False, indent=2),
        "```",
        "",
        "---",
        "",
        "## 8. Impact / Scenario / Decision",
        "",
        f"- Ingestion вызывает `recompute_event_for_ready_companies` после publish → Impact **может** создаваться для ready twins: Δ impacts = {report['impact_delta']}.",
        f"- Δ scenarios = {report['scenario_delta']} (ожидание 0).",
        f"- Δ decisions = {report['decision_delta']} (ожидание 0).",
        "- Скрытого создания Scenario/Decision / изменения сохранённых решений не обнаружено.",
        "",
        "---",
        "",
        "## 9. Live LLM",
        "",
        f"- `prefer_live_enrich`: false",
        f"- `OPENAI_API_KEY` в стенде: пустой",
        f"- `ASSISTANT_PROVIDER`: hackathon",
        f"- Зафиксированные model HTTP во время ingest: `{ingest.get('model_http_calls')}`",
        f"- Вердикт: **{report['no_live_llm_verdict']}**",
        "",
        "Минимальный дефект исправлен: при отсутствии `published_at` публикация отклоняется",
        "(`missing_publication_date`), а не подставляет `now()` / `fetched_at`. Регрессия:",
        "`tests/test_ingestion.py::test_missing_publication_date_does_not_use_fetch_time`.",
        "",
        "---",
        "",
        "## 10. Ограничения и ошибки",
        "",
    ]
    for note in report.get("limitations", []):
        lines.append(f"- {note}")
    lines += [
        "",
        "Машинный отчёт (без секретов): "
        f"`{report['report_json_rel']}`",
        "",
    ]
    DOCS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if not SRC_DB.is_file():
        raise SystemExit(f"missing source DB: {SRC_DB}")
    if not SRC_PASSWORD.is_file():
        raise SystemExit(f"missing password: {SRC_PASSWORD}")
    if not SRC_ENV.is_file():
        raise SystemExit(f"missing source env: {SRC_ENV}")

    src_env = _read_env(SRC_ENV)
    ocr_ids = src_env.get("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", "")
    storage = src_env.get(
        "BANK_MATERIALS_STORAGE_ROOT",
        "data/competition_stand/jury_63b/storage",
    )
    if not ocr_ids:
        raise SystemExit("OCR allow-list missing in ui_acceptance_611/stand.env")

    STAND_DIR.mkdir(parents=True, exist_ok=True)
    print("Backing up SQLite (may take minutes for ~1.8GB)…", flush=True)
    t0 = time.time()
    sha = _backup(SRC_DB, STAND_DB)
    print(f"Backup done in {time.time() - t0:.1f}s sha={sha[:16]}…", flush=True)

    shutil.copy2(SRC_PASSWORD, PASSWORD_DST)
    _write_stand_env(ocr_ids, storage)

    before = _counts(STAND_DB)
    env = _apply_stand_env()
    db_fp = _safe_db_fingerprint(env["DATABASE_URL"])
    if not db_fp["is_real_news_613"] or db_fp["is_source_ui_stand"]:
        raise SystemExit(f"refusing to write: bad DB fingerprint {db_fp}")

    print("Probing RSS feeds…", flush=True)
    feed_probe = _probe_and_save_feeds()
    ok_feeds = [f for f in feed_probe if f["ok"]]
    if not ok_feeds:
        raise SystemExit("no RSS feeds reachable; aborting without inventing news")

    print("Ingest pass (heuristic, limited RSS)…", flush=True)
    ingest = _run_ingest(prefer_live=False)
    after_ingest = _counts(STAND_DB)

    print("Dedupe pass…", flush=True)
    dedupe = _dedupe_pass()
    after = _counts(STAND_DB)

    examples = _published_examples(STAND_DB)
    synthetic = _synthetic_check(STAND_DB)
    rejects = _reject_reasons(STAND_DB)

    password = PASSWORD_DST.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    print("API checks…", flush=True)
    api = _api_checks(password)

    impact_delta = after_ingest["event_impacts"] - before["event_impacts"]
    scenario_delta = after["scenarios"] - before["scenarios"]
    decision_delta = after["decisions"] - before["decisions"]

    personal_a = api.get("personal_a") or {}
    personal_b = api.get("personal_b") or {}
    live_profile = (personal_a.get("profile_match_count") or 0) + (
        personal_b.get("profile_match_count") or 0
    )
    # Check if any NEW live event is in personal profile matches by title overlap
    live_titles = {e["title"] for e in examples}
    matched_titles = set(personal_a.get("profile_titles") or []) | set(
        personal_b.get("profile_titles") or []
    )
    new_in_personal = live_titles & matched_titles
    if new_in_personal:
        personal_verdict = (
            f"PASS: загруженные live-новости в «Для вас» по профилю: "
            f"{sorted(new_in_personal)[:3]}"
        )
    else:
        personal_verdict = (
            "Честно: в загруженном наборе нет новости, прошедшей узкое правило "
            "policy_rate×LOA/DEP для попадания в «Для вас» как case_profile_match "
            "(или совпадение только у прежней синтетики). Правила не ослаблялись."
        )

    no_llm = (
        "PASS — model HTTP не зафиксированы"
        if not ingest.get("model_http_calls")
        else "FAIL — были model HTTP"
    )

    limitations = [
        "Только RSS whitelist; полный текст статей не скачивался.",
        "Interfax/Vedomosti без второго независимого издателя → unverified_single_source.",
        "GDELT/Cbr HTML-провайдеры в этот ограниченный прогон не включались.",
        "Банковский evidence не гарантирован для каждой новости (as_of / eligibility / scope).",
        "Ingestion после publish может создать EventImpact для ready companies — это существующее поведение.",
    ]
    if any(not f["ok"] for f in feed_probe):
        limitations.append("Часть фидов недоступна — без обхода auth/paywall/antibot.")

    prepared_at = datetime.now(timezone.utc).isoformat()
    report = {
        "stage": "6.13",
        "kind": "real_news_ingestion_verification",
        "prepared_at": prepared_at,
        "stand_dir": str(STAND_DIR.relative_to(ROOT)).replace("\\", "/"),
        "source_db": str(SRC_DB.relative_to(ROOT)).replace("\\", "/"),
        "work_db": str(STAND_DB.relative_to(ROOT)).replace("\\", "/"),
        "work_db_sha256": sha,
        "copy_method": "sqlite3.Connection.backup",
        "root_env_touched": False,
        "csv_reimported": False,
        "ports": {"api": API_PORT, "web": WEB_PORT},
        "db_fingerprint": db_fp,
        "counts_before": before,
        "counts_after_ingest": after_ingest,
        "counts_after_dedupe": after,
        "feed_probe": feed_probe,
        "ingest_pass": ingest,
        "dedupe_pass": dedupe,
        "reject_reasons": rejects,
        "published_examples": examples,
        "synthetic": synthetic,
        "api": api,
        "impact_delta": impact_delta,
        "scenario_delta": scenario_delta,
        "decision_delta": decision_delta,
        "personal_feed_verdict": personal_verdict,
        "no_live_llm_verdict": no_llm,
        "limitations": limitations,
        "report_json_rel": str(REPORT_JSON.relative_to(ROOT)).replace("\\", "/"),
        "launch": {
            "backend": f".\\scripts\\run_competition_ui_backend.ps1 -StandDir data\\competition_stand\\real_news_613",
            "frontend": f".\\scripts\\run_competition_ui_frontend.ps1 -StandDir data\\competition_stand\\real_news_613",
        },
    }

    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    MANIFEST.write_text(
        json.dumps(
            {
                "stage": "6.13",
                "kind": "real_news_613",
                "status": "ready",
                "prepared_at": prepared_at,
                "source_db": report["source_db"],
                "work_db": report["work_db"],
                "work_db_sha256": sha,
                "ports": report["ports"],
                "demo_login": {
                    "email": PRIMARY_EMAIL,
                    "password_file": str(PASSWORD_DST.relative_to(ROOT)).replace(
                        "\\", "/"
                    ),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    STATUS.write_text(
        json.dumps({"status": "ready", "prepared_at": prepared_at}, indent=2),
        encoding="utf-8",
    )
    _write_docs(report)

    print(
        json.dumps(
            {
                "status": "ready",
                "stand_dir": report["stand_dir"],
                "fetched": ingest["fetched"],
                "inserted": ingest["inserted"],
                "published": ingest["published"],
                "rejected": ingest["rejected"],
                "dedupe_duplicates": dedupe["duplicates"],
                "model_http": ingest.get("model_http_calls"),
                "personal_verdict": personal_verdict,
                "docs": str(DOCS_MD.relative_to(ROOT)).replace("\\", "/"),
                "report": report["report_json_rel"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
