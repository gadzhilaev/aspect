"""Assist provenance + new-user checks on a DB copy. No secrets printed."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/competition_stand/real_news_613/stand.db"
COPY_DIR = ROOT / "data/competition_stand/new_user_runtime_verify"
COPY_DB = COPY_DIR / "stand.db"
TG_DB = ROOT / "data/telegram_live/telegram_live.db"
OUT = COPY_DIR / "verification.json"


def dump_assistant(db_path: Path) -> dict:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    tables = [
        r[0]
        for r in con.execute(
            "select name from sqlite_master where type='table'"
        ).fetchall()
    ]
    assist = [t for t in tables if "assist" in t.lower()]
    out: dict = {"tables": assist}
    if "assistant_messages" in tables:
        cols = [r[1] for r in con.execute("pragma table_info(assistant_messages)")]
        out["message_cols"] = cols
        basis_col = "answer_basis" if "answer_basis" in cols else None
        if basis_col:
            out["basis_counts"] = {
                (r[0] or "null"): r[1]
                for r in con.execute(
                    f"select {basis_col}, count(*) from assistant_messages "
                    "where role='assistant' group by 1"
                )
            }
            rows = con.execute(
                f"select id, conversation_id, {basis_col}, "
                "substr(coalesce(content,''),1,80) as preview, created_at "
                "from assistant_messages where role='assistant' "
                "order by created_at desc limit 8"
            ).fetchall()
            out["recent_assistant"] = [dict(r) for r in rows]
        # conversation-level basis
    if "assistant_conversations" in tables:
        ccols = [r[1] for r in con.execute("pragma table_info(assistant_conversations)")]
        out["conversation_cols"] = ccols
        if "answer_basis" in ccols:
            out["conversation_basis_counts"] = {
                (r[0] or "null"): r[1]
                for r in con.execute(
                    "select answer_basis, count(*) from assistant_conversations group by 1"
                )
            }
    con.close()
    return out


def prepare_copy() -> Path:
    COPY_DIR.mkdir(parents=True, exist_ok=True)
    if not SRC.exists():
        raise SystemExit(f"missing source {SRC}")
    if COPY_DB.exists():
        COPY_DB.unlink()
    src = sqlite3.connect(f"file:{SRC.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(COPY_DB)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return COPY_DB


def run_new_user_api(db_path: Path) -> dict:
    """Register new user against isolated copy via TestClient — no live LLM."""
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.resolve().as_posix()}"
    os.environ["APP_ENV"] = "test"
    os.environ["SECRET_KEY"] = "new-user-runtime-verify-secret"
    os.environ["ASSISTANT_PROVIDER"] = "hackathon"
    os.environ["ASSISTANT_AGENT_LOOP"] = "true"
    os.environ["COMPETITION_MODE"] = "true"
    os.environ["HACKATHON_BASE_URL"] = "https://changellenge.up.railway.app/v1"
    os.environ["HACKATHON_MODEL"] = "deepseek/deepseek-v4.1-flash"
    # Empty key — must not call live LLM; only routing/config checks
    os.environ["HACKATHON_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["GIGACHAT_AUTH_KEY"] = ""
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    # Clear settings cache / engine
    sys.path.insert(0, str(ROOT))
    from app.core.config import get_settings
    from app.db import session as db_session
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    get_settings.cache_clear()
    engine = create_engine(
        os.environ["DATABASE_URL"], connect_args={"check_same_thread": False}
    )
    db_session.engine = engine
    db_session.SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )

    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app()
    settings = get_settings()
    report: dict = {
        "db": db_path.as_posix(),
        "provider": settings.normalized_assistant_provider(),
        "agent_loop": bool(settings.assistant_agent_loop),
        "competition_mode": bool(settings.competition_mode),
        "hackathon_key_present": bool(settings.hackathon_api_key),
    }

    email = f"newuser_{uuid.uuid4().hex[:10]}@example.com"
    password = "NewUserVerify1!"

    with TestClient(app) as client:
        # Register
        reg = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "display_name": "New Verify"},
        )
        report["register_status"] = reg.status_code
        reg_body = reg.json() if reg.content else {}
        demo_code = None
        if isinstance(reg_body.get("details"), dict):
            demo_code = reg_body["details"].get("demo_code")
        # MessageOut shape
        if demo_code is None and isinstance(reg_body.get("details"), list):
            pass
        # try nested
        if demo_code is None:
            demo_code = (reg_body.get("details") or {}).get("demo_code") if isinstance(reg_body.get("details"), dict) else None
        # from register response in this codebase
        if demo_code is None and reg.status_code == 200:
            demo_code = (reg_body.get("details") or {}).get("demo_code")

        # Fallback: read verification from DB
        if not demo_code:
            con = sqlite3.connect(db_path)
            row = con.execute(
                "select code from email_verification_codes where email=? order by created_at desc limit 1",
                (email,),
            ).fetchone()
            if not row:
                # alternate schema
                try:
                    row = con.execute(
                        "select code from email_verifications order by created_at desc limit 1"
                    ).fetchone()
                except sqlite3.Error:
                    row = None
            con.close()
            demo_code = row[0] if row else "123456"

        ver = client.post(
            "/api/v1/auth/verify-email",
            json={"email": email, "code": str(demo_code)},
        )
        report["verify_status"] = ver.status_code

        login = client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        report["login_status"] = login.status_code
        if login.status_code != 200:
            report["login_body"] = str(login.text)[:200]
            return report
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/v1/users/me", headers=headers)
        report["me_status"] = me.status_code
        me_body = me.json() if me.status_code == 200 else {}
        companies = me_body.get("companies") or []
        report["new_user_companies_count"] = len(companies)
        report["new_user_has_severprom"] = any(
            (c.get("company_id") == "cmp_severprom")
            or ("северпром" in (c.get("name") or "").lower())
            for c in companies
        )
        report["new_user_auto_synthetic"] = any(
            "SYNTHETIC" in (c.get("name") or "").upper()
            or "U_" in (c.get("name") or "")
            for c in companies
        )

        # Public news (shared feed)
        news = client.get("/api/v1/public/news?limit=50")
        report["public_news_status"] = news.status_code
        if news.status_code == 200:
            items = news.json().get("items") or []
            report["public_news_count"] = len(items)
            report["public_has_live_prefix"] = any(
                str(it.get("id") or "").startswith("evt_live_") for it in items
            )
            report["public_has_demo_china"] = any(
                str(it.get("id") or "") == "evt_china_export_001" for it in items
            )
            report["public_title_samples"] = [
                (it.get("title") or "")[:70] for it in items[:5]
            ]

        # Create own company
        created = client.post(
            "/api/v1/companies",
            headers=headers,
            json={
                "name": f"Verify Co {uuid.uuid4().hex[:6]}",
                "tax_id": None,
                "hq_region": "Москва",
                "size_band": "small",
                "industry": "manufacturing",
            },
        )
        report["create_company_status"] = created.status_code
        if created.status_code != 200:
            report["create_company_body"] = created.text[:240]
            return report
        cid = created.json()["id"]
        report["created_company_id"] = cid
        report["created_is_severprom"] = cid == "cmp_severprom"

        # For-you uses dashboard + public news
        dash = client.get(f"/api/v1/companies/{cid}/dashboard", headers=headers)
        report["dashboard_status"] = dash.status_code
        if dash.status_code == 200:
            dbody = dash.json()
            evs = dbody.get("events") or dbody.get("items") or []
            report["dashboard_events_count"] = len(evs)
            report["for_you_empty_or_matched"] = (
                "empty" if len(evs) == 0 else "has_items"
            )
            report["dashboard_event_ids"] = [
                str(e.get("id") or e.get("event_id") or "")[:40] for e in evs[:8]
            ]

        company_events = client.get(
            f"/api/v1/companies/{cid}/events", headers=headers
        )
        report["company_events_status"] = company_events.status_code

        # Assistant conversation without requiring Impact (routing check, no live LLM)
        con = sqlite3.connect(db_path)
        ev = con.execute(
            "select id from events where id like 'evt_live_%' limit 1"
        ).fetchone()
        con.close()
        if ev:
            eid = ev[0]
            start = client.post(
                f"/api/v1/events/{eid}/assistant/conversations",
                headers=headers,
                json={"company_id": cid},
            )
            report["assistant_start_status"] = start.status_code
            if start.status_code == 200:
                conv = start.json()
                report["assistant_answer_basis"] = conv.get("answer_basis")
                report["assistant_is_demo_explain"] = (
                    conv.get("answer_basis") == "demo_explain"
                )
                report["assistant_is_hackathon_basis"] = (
                    conv.get("answer_basis") == "ai_explain_hackathon"
                )
                # Do NOT send a message (would hit live LLM). Provenance of empty/new conv is enough.
            else:
                report["assistant_start_body"] = start.text[:240]

        ctx = client.get(f"/api/v1/companies/{cid}/context", headers=headers)
        report["context_status"] = ctx.status_code
        if ctx.status_code == 200:
            cjson = ctx.json()
            blob = json.dumps(cjson, ensure_ascii=False).lower()
            report["context_mentions_severprom"] = "северпром" in blob
            report["context_has_case_link"] = bool(
                cjson.get("case_link")
                or cjson.get("case_context")
                or (cjson.get("case") if isinstance(cjson.get("case"), dict) else None)
            )

    return report


def main() -> int:
    COPY_DIR.mkdir(parents=True, exist_ok=True)
    assist_tg = dump_assistant(TG_DB) if TG_DB.exists() else {}
    assist_rn = dump_assistant(SRC) if SRC.exists() else {}
    db = prepare_copy()
    api_report = run_new_user_api(db)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assistant_telegram_live": assist_tg,
        "assistant_real_news_613": assist_rn,
        "new_user_api": api_report,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
