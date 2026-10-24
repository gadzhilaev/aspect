"""Safe runtime probe for NEW_USER_RUNTIME_VERIFICATION — no secrets printed."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def summarize_db(db_path: Path, label: str) -> dict:
    out: dict = {
        "label": label,
        "exists": db_path.exists(),
        "path": db_path.as_posix(),
    }
    if not db_path.exists():
        return out
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    def scalar(sql: str):
        try:
            row = con.execute(sql).fetchone()
            return row[0] if row else None
        except sqlite3.Error as exc:
            return f"ERR:{type(exc).__name__}"

    out["users"] = scalar("select count(*) from users")
    out["companies"] = scalar("select count(*) from companies")
    out["events"] = scalar("select count(*) from events")
    cols = {r[1] for r in con.execute("pragma table_info(events)")}
    if "lifecycle_status" in cols:
        out["events_by_lifecycle"] = dict(
            con.execute(
                "select coalesce(lifecycle_status,'null'), count(*) "
                "from events group by 1"
            ).fetchall()
        )
    if "published_at" in cols:
        out["events_with_published_at"] = scalar(
            "select count(*) from events where published_at is not null"
        )
    try:
        rows = con.execute(
            "select id, substr(coalesce(title,''),1,70) as title "
            "from events order by created_at desc limit 8"
        ).fetchall()
        out["recent_event_titles"] = [dict(r) for r in rows]
    except sqlite3.Error as exc:
        out["recent_event_titles_err"] = str(exc)[:120]
    out["bank_fragments"] = scalar("select count(*) from bank_fragments")
    out["memberships"] = scalar("select count(*) from company_memberships")
    try:
        out["alembic"] = con.execute(
            "select version_num from alembic_version"
        ).fetchone()[0]
    except sqlite3.Error:
        out["alembic"] = None
    # assistant messages sample provenance
    try:
        msgs = con.execute(
            "select answer_basis, count(*) from assistant_messages "
            "where role='assistant' group by 1"
        ).fetchall()
        out["assistant_basis_counts"] = {r[0] or "null": r[1] for r in msgs}
    except sqlite3.Error:
        out["assistant_basis_counts"] = "n/a"
    con.close()
    return out


def stand_env_flags(path: Path) -> dict:
    flags = {}
    if not path.is_file():
        return {"exists": False}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k in {
            "DATABASE_URL",
            "ASSISTANT_PROVIDER",
            "ASSISTANT_AGENT_LOOP",
            "COMPETITION_MODE",
            "HACKATHON_BASE_URL",
            "HACKATHON_MODEL",
            "APP_ENV",
            "TELEGRAM_LIVE_STAND",
            "AGENT_DEMO_STAND",
            "AGENT_DEMO_API_PORT",
            "AGENT_DEMO_WEB_PORT",
            "TELEGRAM_LIVE_API_PORT",
            "TELEGRAM_LIVE_WEB_PORT",
            "CASE_CONTEXT_SLOT_KEY",
            "BANK_MATERIALS_STORAGE_ROOT",
        }:
            if k == "DATABASE_URL":
                # path only, no credentials
                flags[k] = v.split(":///")[-1] if "sqlite" in v else "non-sqlite"
            elif k.endswith("KEY") or "SECRET" in k or "TOKEN" in k:
                flags[k] = "SET" if v else "EMPTY"
            else:
                flags[k] = v
        if k in {"OPENAI_API_KEY", "GIGACHAT_AUTH_KEY", "HACKATHON_API_KEY"}:
            flags[k + "_present"] = bool(v)
    flags["exists"] = True
    return flags


def api_probe(base: str) -> dict:
    out = {"base": base}
    try:
        with httpx.Client(timeout=8.0, trust_env=False) as client:
            h = client.get(f"{base}/health")
            out["health_status"] = h.status_code
            out["health"] = h.json() if h.status_code == 200 else h.text[:80]
            # public events if any
            for path in (
                "/api/v1/events",
                "/api/v1/public/events",
                "/api/v1/feed",
            ):
                r = client.get(f"{base}{path}")
                out[f"GET {path}"] = r.status_code
    except Exception as exc:  # noqa: BLE001
        out["error"] = type(exc).__name__
    return out


def main() -> int:
    report = {
        "telegram_live_stand_env": stand_env_flags(
            ROOT / "data/telegram_live/stand.env"
        ),
        "real_news_613_stand_env": stand_env_flags(
            ROOT / "data/competition_stand/real_news_613/stand.env"
        ),
        "db_telegram_live": summarize_db(
            ROOT / "data/telegram_live/telegram_live.db", "telegram_live"
        ),
        "db_real_news_613": summarize_db(
            ROOT / "data/competition_stand/real_news_613/stand.db", "real_news_613"
        ),
        "api_8027": api_probe("http://127.0.0.1:8027"),
        "api_8020": api_probe("http://127.0.0.1:8020"),
        "web_5187": None,
        "web_5180": None,
    }
    with httpx.Client(timeout=5.0, trust_env=False) as client:
        for port, key in ((5187, "web_5187"), (5180, "web_5180")):
            try:
                r = client.get(f"http://127.0.0.1:{port}/")
                report[key] = {"status": r.status_code, "bytes": len(r.content)}
                # vite transformed client
                c = client.get(f"http://127.0.0.1:{port}/src/api/client.ts")
                if c.status_code == 200:
                    report[key]["client_has_8027"] = "8027" in c.text
                    report[key]["client_has_8020"] = "8020" in c.text
                    report[key]["client_has_8003"] = "8003" in c.text
            except Exception as exc:  # noqa: BLE001
                report[key] = {"error": type(exc).__name__}

    out_path = ROOT / "data/telegram_live/new_user_runtime_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
