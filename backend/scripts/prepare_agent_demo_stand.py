"""Prepare isolated agent-loop demo stand from e2e462 success DB (stage 4.7).

- SQLite backup() of e2e462 DB (source read-only)
- Copy Policy Rate PDF into stand storage; verify SHA
- Resolve user/company/event/snapshot IDs from DB relationships
- Write manifest WITHOUT secrets / API keys

Does not modify e2e462, root .env, web/.env, or kontur.db.
Does not call live LLM.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DB = (
    ROOT
    / "data/bank_materials/verification/e2e462/assistant_agent_live_recheck.db"
)
SRC_STORAGE = ROOT / "data/bank_materials/verification/e2e462/storage"
RAW_PDF = ROOT / "data/bank_materials/raw/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"
EXPECTED_PDF_SHA = "92a96805f2b720f76bd0c52d2491044812b38401ab62d0f4a9157b4ca81c49bb"
OCR_RUN_ID = "7d64e39e-0ff5-450c-8a01-c44f678da871"
STORAGE_KEY = "bank_import_stage_5v66axai/pdf/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"
SLOT = "competition_default"

STAND_DIR = ROOT / "data/agent_demo"
STAND_DB = STAND_DIR / "agent_demo.db"
STAND_STORAGE = STAND_DIR / "storage"
MANIFEST = STAND_DIR / "stand_manifest.json"
# Process profile for launchers — no HACKATHON_API_KEY here.
STAND_ENV = STAND_DIR / "stand.env"
STAND_WEB_ENV = STAND_DIR / "web.env"

# Explicit stand ports (must not silently steal :8003 / :5173).
API_PORT = 8017
WEB_PORT = 5177

# Demo login (password hashed in DB at seed time of 4.6.2).
DEMO_PASSWORD = "E2eAgent462!"


def _backup_db(src: Path, dst: Path) -> None:
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


def _prepare_storage() -> Path:
    STAND_STORAGE.mkdir(parents=True, exist_ok=True)
    target = STAND_STORAGE / STORAGE_KEY
    target.parent.mkdir(parents=True, exist_ok=True)
    src_pdf = SRC_STORAGE / STORAGE_KEY
    if src_pdf.is_file():
        shutil.copy2(src_pdf, target)
    elif RAW_PDF.is_file():
        shutil.copy2(RAW_PDF, target)
    else:
        raise FileNotFoundError("Policy Rate PDF missing in e2e462 storage and raw/")
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    if sha != EXPECTED_PDF_SHA:
        raise RuntimeError(f"PDF SHA mismatch: {sha}")
    return STAND_STORAGE


def _resolve_ids(db_path: Path) -> dict:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        users = list(conn.execute("select id, email from users"))
        if not users:
            raise RuntimeError("no users in stand DB")
        # Prefer e2e462 synthetic user
        user = next((u for u in users if "e2e462" in (u["email"] or "")), users[0])
        mem = conn.execute(
            "select company_id, role from company_memberships where user_id=?",
            (user["id"],),
        ).fetchone()
        if not mem:
            raise RuntimeError("membership missing")
        company = conn.execute(
            "select id, name from companies where id=?", (mem["company_id"],)
        ).fetchone()
        link = conn.execute(
            "select external_uid, slot_key from case_org_company_links where company_id=?",
            (company["id"],),
        ).fetchone()
        active = conn.execute(
            "select slot_key, active_snapshot_id from case_active_snapshot where slot_key=?",
            (SLOT,),
        ).fetchone()
        snap = None
        if active and active["active_snapshot_id"]:
            snap = conn.execute(
                "select id, status, version_label, slot_key from case_snapshots where id=?",
                (active["active_snapshot_id"],),
            ).fetchone()
        event = conn.execute(
            "select id, title, occurred_at from events where id=?",
            ("evt_synth_e2e462_policy_rate",),
        ).fetchone()
        if event is None:
            event = conn.execute(
                "select id, title, occurred_at from events order by occurred_at desc limit 1"
            ).fetchone()
        impact_n = conn.execute(
            "select count(*) from event_impacts where event_id=? and company_id=?",
            (event["id"], company["id"]),
        ).fetchone()[0]
        conv = conn.execute(
            """
            select c.id as conversation_id, c.event_id, c.company_id
            from assistant_conversations c
            where c.event_id=? and c.company_id=?
            order by c.created_at desc limit 1
            """,
            (event["id"], company["id"]),
        ).fetchone()
        msgs = []
        if conv:
            msgs = [
                dict(r)
                for r in conn.execute(
                    """
                    select id, role, length(content) as content_chars,
                           substr(content, 1, 60) as content_prefix
                    from assistant_messages
                    where conversation_id=?
                    order by created_at
                    """,
                    (conv["conversation_id"],),
                )
            ]
        # OCR run present
        ocr = conn.execute(
            "select id, processing_status from bank_ocr_runs where id=?",
            (OCR_RUN_ID,),
        ).fetchone()
        if ocr is None:
            # Resolve from document file → ocr runs (do not hardcode unknown IDs).
            file_probe = conn.execute(
                "select id from bank_document_files where storage_key=?",
                (STORAGE_KEY,),
            ).fetchone()
            if file_probe:
                ocr = conn.execute(
                    """
                    select id, processing_status from bank_ocr_runs
                    where document_file_id=?
                    order by created_at desc limit 1
                    """,
                    (file_probe["id"],),
                ).fetchone()
        file_row = conn.execute(
            "select id, storage_key, sha256 from bank_document_files where storage_key=?",
            (STORAGE_KEY,),
        ).fetchone()
        resolved_ocr_id = ocr["id"] if ocr else OCR_RUN_ID
        return {
            "user_id": user["id"],
            "email": user["email"],
            "company_id": company["id"],
            "company_name": company["name"],
            "membership_role": mem["role"],
            "external_uid": link["external_uid"] if link else None,
            "slot_key": (link["slot_key"] if link else None) or SLOT,
            "active_snapshot_id": active["active_snapshot_id"] if active else None,
            "snapshot_status": snap["status"] if snap else None,
            "snapshot_label": snap["version_label"] if snap else None,
            "event_id": event["id"],
            "event_title": event["title"],
            "event_occurred_at": event["occurred_at"],
            "event_impact_count": int(impact_n or 0),
            "conversation_id": conv["conversation_id"] if conv else None,
            "message_summaries": msgs,
            "ocr_run_id": resolved_ocr_id,
            "ocr_run_status": ocr["processing_status"] if ocr else None,
            "bank_file_sha256": file_row["sha256"] if file_row else None,
            "storage_key": STORAGE_KEY,
        }
    finally:
        conn.close()


def _mark_synthetic_demo(db_path: Path, event_id: str) -> None:
    """Copy-only: mark synthetic event as is_demo for UI chip (source DB untouched)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("update events set is_demo=1 where id=?", (event_id,))
        conn.commit()
    finally:
        conn.close()


def _write_stand_env(*, storage: Path, ocr_run_id: str, event_id: str) -> None:
    # Repo-relative paths so the stand is portable across machines (cwd = repo root).
    db_url = "sqlite:///./data/agent_demo/agent_demo.db"
    storage_rel = str(storage.relative_to(ROOT)).replace("\\", "/")
    lines = [
        "# Agent-loop demo stand process profile (stage 4.7+ / 6.2).",
        "# Loaded by scripts/run_agent_demo_backend.ps1 into the process environment.",
        "# HACKATHON_API_KEY is NOT stored here — launcher reads it from root .env.",
        "# Do not copy this file's contents into web/.env.",
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
        f"CASE_CONTEXT_SLOT_KEY={SLOT}",
        f"BANK_MATERIALS_ALLOWED_OCR_RUN_IDS={ocr_run_id}",
        f"BANK_MATERIALS_STORAGE_ROOT={storage_rel}",
        "OPENAI_API_KEY=",
        "GIGACHAT_AUTH_KEY=",
        # Stage 4.8: enable demo entry panel API (not product default).
        "AGENT_DEMO_STAND=true",
        f"AGENT_DEMO_EVENT_ID={event_id}",
        f"AGENT_DEMO_API_PORT={API_PORT}",
        f"AGENT_DEMO_WEB_PORT={WEB_PORT}",
        "",
    ]
    STAND_ENV.write_text("\n".join(lines), encoding="utf-8")
    STAND_WEB_ENV.write_text(
        f"# Frontend pointer for agent demo stand only.\n"
        f"# Launcher sets VITE_API_BASE_URL / VITE_AGENT_DEMO in-process; does not overwrite web/.env.\n"
        f"VITE_API_BASE_URL=http://127.0.0.1:{API_PORT}\n"
        f"VITE_AGENT_DEMO=true\n",
        encoding="utf-8",
    )


def main() -> int:
    if not SRC_DB.is_file():
        print(json.dumps({"ok": False, "fatal": f"missing source DB: {SRC_DB}"}))
        return 2
    STAND_DIR.mkdir(parents=True, exist_ok=True)
    _backup_db(SRC_DB, STAND_DB)
    storage = _prepare_storage()
    ids = _resolve_ids(STAND_DB)
    if ids["event_impact_count"] != 0:
        print(json.dumps({"ok": False, "fatal": "EventImpact unexpectedly present"}))
        return 2
    if ids["bank_file_sha256"] and ids["bank_file_sha256"] != EXPECTED_PDF_SHA:
        print(json.dumps({"ok": False, "fatal": "DB file SHA != expected PDF"}))
        return 2
    pdf_sha = hashlib.sha256((storage / STORAGE_KEY).read_bytes()).hexdigest()
    _mark_synthetic_demo(STAND_DB, str(ids["event_id"]))
    _write_stand_env(
        storage=storage,
        ocr_run_id=str(ids["ocr_run_id"] or OCR_RUN_ID),
        event_id=str(ids["event_id"]),
    )

    manifest = {
        "stage": "4.8",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "source_db": str(SRC_DB.relative_to(ROOT)).replace("\\", "/"),
        "stand_db": str(STAND_DB.relative_to(ROOT)).replace("\\", "/"),
        "storage_root": str(storage.relative_to(ROOT)).replace("\\", "/"),
        "storage_key": STORAGE_KEY,
        "pdf_sha256_ok": pdf_sha == EXPECTED_PDF_SHA,
        "ports": {"api": API_PORT, "web": WEB_PORT},
        "synthetic_notice": (
            "Company, event, and chat history are synthetic test fixtures from "
            "stage 4.6.2 — not real competition submissions."
        ),
        "prior_answer_notice": (
            "Assistant history in this DB includes a previously obtained 4.6.2 "
            "live answer — not a new generation in stage 4.7."
        ),
        "demo_login": {
            "email": ids["email"],
            "password_hint": "same as e2e462 seed (see runbook)",
        },
        "resolved": {
            k: v
            for k, v in ids.items()
            if k not in {"message_summaries"}
        },
        "message_count": len(ids.get("message_summaries") or []),
        "message_roles": [m.get("role") for m in (ids.get("message_summaries") or [])],
        "runtime_profile_file": str(STAND_ENV.relative_to(ROOT)).replace("\\", "/"),
        "web_env_file": str(STAND_WEB_ENV.relative_to(ROOT)).replace("\\", "/"),
        "secrets_in_manifest": False,
        "hackathon_key_in_stand_files": False,
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"ok": True, "manifest": str(MANIFEST.relative_to(ROOT)).replace("\\", "/"), "email": ids["email"], "event_id": ids["event_id"], "api_port": API_PORT, "web_port": WEB_PORT}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
