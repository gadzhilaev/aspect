"""Prepare isolated competition UI acceptance stand (stage 6.11).

SQLite backup of evidence_expansion_stand_copy (7 AI-eligible fragments).
Clears leftover assistant threads so the primary demo user starts without
Impact / Scenario / Decision / finance / chat history.
Does not touch jury_63b, evidence_expansion source, root .env, or :8003.
Does not re-import CSV. Does not call live LLM.
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
SRC_DB = ROOT / "data/bank_materials/verification/evidence_expansion_stand_copy.db"
JURY_DIR = ROOT / "data/competition_stand/jury_63b"
PASSWORD_SRC = JURY_DIR / "demo_password.local"
STORAGE_ROOT = JURY_DIR / "storage"

STAND_DIR = ROOT / "data/competition_stand/ui_acceptance_611"
STAND_DB = STAND_DIR / "stand.db"
STAND_ENV = STAND_DIR / "stand.env"
STAND_WEB_ENV = STAND_DIR / "web.env"
MANIFEST = STAND_DIR / "stand_manifest.json"
PASSWORD_DST = STAND_DIR / "demo_password.local"
STATUS = STAND_DIR / "stand_status.json"

API_PORT = 8018
WEB_PORT = 5178
PRIMARY_EMAIL = "competition-demo-a@example.com"


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


def _count_ai_eligible(db_path: Path) -> int:
    sys.path.insert(0, str(ROOT))
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker
    from app.models.bank_materials import BankFragment, BankFragmentRegion
    from app.services.bank_materials.eligibility import compute_fragment_eligibility

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Session = sessionmaker(bind=engine)
    n = 0
    with Session() as s:
        for f in s.query(BankFragment).all():
            rc = (
                s.query(func.count(BankFragmentRegion.id))
                .filter(BankFragmentRegion.fragment_id == f.id)
                .scalar()
                or 0
            )
            el = compute_fragment_eligibility(
                verification_status=f.verification_status,
                kind=f.kind,
                primary_region_type=f.primary_region_type,
                content_type=f.content_type,
                content_type_status=f.content_type_status,
                verified_transcript=f.verified_transcript,
                summary_text=f.summary_text,
                region_count=int(rc),
            )
            if el.eligible_ai_evidence:
                n += 1
    engine.dispose()
    return n


def _reset_to_clean_start(db_path: Path) -> dict:
    """Remove chat / impact / finance artifacts so UI path starts clean.

    Keeps users, companies, case links, bank materials, synthetic event.
    """
    conn = sqlite3.connect(db_path)
    try:
        before = {
            "assistant_messages": conn.execute(
                "select count(*) from assistant_messages"
            ).fetchone()[0],
            "assistant_conversations": conn.execute(
                "select count(*) from assistant_conversations"
            ).fetchone()[0],
            "assistant_tool_runs": conn.execute(
                "select count(*) from assistant_tool_runs"
            ).fetchone()[0],
            "event_impacts": conn.execute(
                "select count(*) from event_impacts"
            ).fetchone()[0],
            "scenarios": conn.execute("select count(*) from scenarios").fetchone()[0],
            "decisions": conn.execute("select count(*) from decisions").fetchone()[0],
            "company_profile_settings": conn.execute(
                "select count(*) from company_profile_settings"
            ).fetchone()[0],
        }
        # Order: dependents first
        for table in (
            "assistant_messages",
            "assistant_tool_runs",
            "assistant_conversations",
            "action_items",
            "decisions",
            "scenarios",
            "impact_paths",
            "event_impacts",
            "company_profile_settings",
        ):
            conn.execute(f"delete from {table}")
        conn.commit()
        row = conn.execute(
            """
            select u.email, c.id, c.name, e.id, e.title
            from users u
            join company_memberships m on m.user_id = u.id
            join companies c on c.id = m.company_id
            join case_org_company_links l on l.company_id = c.id
            cross join events e
            where u.email = ? and l.external_uid = 'U_264'
            limit 1
            """,
            (PRIMARY_EMAIL,),
        ).fetchone()
        if row is None:
            raise RuntimeError("primary UI user / U_264 company / event missing")
        after = {
            "assistant_messages": conn.execute(
                "select count(*) from assistant_messages"
            ).fetchone()[0],
            "assistant_conversations": conn.execute(
                "select count(*) from assistant_conversations"
            ).fetchone()[0],
            "event_impacts": conn.execute(
                "select count(*) from event_impacts"
            ).fetchone()[0],
            "scenarios": conn.execute("select count(*) from scenarios").fetchone()[0],
            "decisions": conn.execute("select count(*) from decisions").fetchone()[0],
            "company_profile_settings": conn.execute(
                "select count(*) from company_profile_settings"
            ).fetchone()[0],
        }
        return {
            "cleared_before": before,
            "cleared_after": after,
            "primary_email": row[0],
            "company_id": row[1],
            "company_name": row[2],
            "event_id": row[3],
            "event_title": row[4],
        }
    finally:
        conn.close()


def _resolve_password(password_file: Path, db_path: Path) -> str:
    """Pick the hash-matching token from a possibly annotated password file."""
    from app.core.security import verify_password

    raw = password_file.read_text(encoding="utf-8")
    candidates: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        candidates.append(s)
        for sep in ("=", ":"):
            if sep in s:
                right = s.split(sep, 1)[1].strip().strip("\"'")
                if right:
                    candidates.append(right)
    candidates.append(raw.strip())
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "select password_hash from users where email=?",
            (PRIMARY_EMAIL,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise RuntimeError("primary user missing")
    ph = row[0]
    for c in candidates:
        if verify_password(c, ph):
            return c
    raise RuntimeError("demo password file does not match primary user hash")


def _read_jury_ocr_ids() -> str:
    env = (JURY_DIR / "stand.env").read_text(encoding="utf-8")
    for line in env.splitlines():
        if line.startswith("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("OCR allow-list missing in jury_63b/stand.env")


def _write_env(ocr_ids: str) -> None:
    db_url = f"sqlite:///./{STAND_DB.relative_to(ROOT).as_posix()}"
    storage = STORAGE_ROOT.relative_to(ROOT).as_posix()
    STAND_ENV.write_text(
        "\n".join(
            [
                "# Competition UI acceptance stand (stage 6.11). No secrets.",
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
                f"BANK_MATERIALS_STORAGE_ROOT={storage}",
                "OPENAI_API_KEY=",
                "GIGACHAT_AUTH_KEY=",
                "AGENT_DEMO_STAND=true",
                f"AGENT_DEMO_API_PORT={API_PORT}",
                f"AGENT_DEMO_WEB_PORT={WEB_PORT}",
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


def main() -> int:
    if not SRC_DB.is_file():
        raise SystemExit(f"missing source DB: {SRC_DB}")
    if not PASSWORD_SRC.is_file():
        raise SystemExit(f"missing password file: {PASSWORD_SRC}")
    if not STORAGE_ROOT.is_dir():
        raise SystemExit(f"missing storage: {STORAGE_ROOT}")

    STAND_DIR.mkdir(parents=True, exist_ok=True)
    sha = _backup(SRC_DB, STAND_DB)
    ai_n = _count_ai_eligible(STAND_DB)
    if ai_n != 7:
        raise SystemExit(f"expected 7 AI-eligible fragments, got {ai_n}")
    fixtures = _reset_to_clean_start(STAND_DB)
    # Single-line password file for unambiguous UI login (never printed).
    pwd = _resolve_password(PASSWORD_SRC, STAND_DB)
    PASSWORD_DST.write_text(pwd + "\n", encoding="utf-8")
    ocr_ids = _read_jury_ocr_ids()
    _write_env(ocr_ids)

    manifest = {
        "stage": "6.11",
        "kind": "competition_ui_acceptance",
        "status": "ready",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "source_db": str(SRC_DB.relative_to(ROOT)).replace("\\", "/"),
        "work_db": str(STAND_DB.relative_to(ROOT)).replace("\\", "/"),
        "work_db_sha256": sha,
        "copy_method": "sqlite3.Connection.backup",
        "ai_eligible_fragments": ai_n,
        "storage_root": str(STORAGE_ROOT.relative_to(ROOT)).replace("\\", "/"),
        "csv_reimported": False,
        "root_env_touched": False,
        "ports": {"api": API_PORT, "web": WEB_PORT},
        "demo_login": {
            "email": fixtures["primary_email"],
            "password_file": str(PASSWORD_DST.relative_to(ROOT)).replace("\\", "/"),
        },
        "primary_company": {
            "id": fixtures["company_id"],
            "name": fixtures["company_name"],
            "external_uid": "U_264",
        },
        "primary_event": {
            "id": fixtures["event_id"],
            "title": fixtures["event_title"],
            "note": "Discover via personal feed (case_profile_match); do not hardcode ID in UI checks",
        },
        "clean_start": fixtures["cleared_after"],
        "cleared_before": fixtures["cleared_before"],
        "not_from_e2e610_finished_state": True,
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    STATUS.write_text(
        json.dumps(
            {"status": "ready", "prepared_at": manifest["prepared_at"]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "ready",
                "stand_dir": str(STAND_DIR.relative_to(ROOT)).replace("\\", "/"),
                "api_port": API_PORT,
                "web_port": WEB_PORT,
                "email": fixtures["primary_email"],
                "password_file": str(PASSWORD_DST.relative_to(ROOT)).replace("\\", "/"),
                "event_id": fixtures["event_id"],
                "ai_eligible": ai_n,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
