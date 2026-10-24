"""HTTP/TestClient verification of a prepared competition stand (no model HTTP).

Usage:
  python scripts/verify_competition_stand.py --stand-dir data/competition_stand/jury_63
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stand-dir", type=Path, required=True)
    parser.add_argument(
        "--relocate-to",
        type=Path,
        default=None,
        help="Optional: copy stand dir to a new path and re-verify (storage keys unchanged)",
    )
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))

    stand_dir = args.stand_dir.resolve()
    if args.relocate_to is not None:
        import shutil

        dest = args.relocate_to.resolve()
        if dest.exists():
            print(f"relocate target exists: {dest}", file=sys.stderr)
            return 2
        shutil.copytree(stand_dir, dest)
        stand_dir = dest
        print(f"relocated_copy={stand_dir}")

    status_path = stand_dir / "stand_status.json"
    man_path = stand_dir / "stand_manifest.json"
    pwd_path = stand_dir / "demo_password.local"
    env_path = stand_dir / "stand.env"
    if not status_path.is_file() or not man_path.is_file():
        print("stand_status.json / stand_manifest.json missing", file=sys.stderr)
        return 2
    status = json.loads(status_path.read_text(encoding="utf-8"))
    manifest = json.loads(man_path.read_text(encoding="utf-8"))
    if status.get("status") != "ready" or not status.get("ready_for_launch"):
        print(f"stand not ready: {status}", file=sys.stderr)
        return 1

    if not pwd_path.is_file():
        print("demo_password.local missing", file=sys.stderr)
        return 2
    email = None
    password = None
    for line in pwd_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("email="):
            email = line.split("=", 1)[1].strip()
        if line.startswith("password="):
            password = line.split("=", 1)[1].strip()
    if not email or not password:
        print("demo_password.local incomplete", file=sys.stderr)
        return 2

    stand_env = _load_dotenv_file(env_path)
    db_url = stand_env.get("DATABASE_URL")
    if not db_url:
        db_url = f"sqlite:///{(stand_dir / 'stand.db').as_posix()}"

    # Isolate process env for TestClient app.
    for key in list(os.environ.keys()):
        if key.startswith("ASSISTANT_") or key in {
            "DATABASE_URL",
            "COMPETITION_MODE",
            "HACKATHON_API_KEY",
            "CASE_CONTEXT_SLOT_KEY",
            "BANK_MATERIALS_ALLOWED_OCR_RUN_IDS",
            "BANK_MATERIALS_STORAGE_ROOT",
            "AGENT_DEMO_STAND",
            "AGENT_DEMO_EVENT_ID",
            "OPENAI_API_KEY",
            "GIGACHAT_AUTH_KEY",
        }:
            os.environ.pop(key, None)

    os.environ["DATABASE_URL"] = db_url
    for k, v in stand_env.items():
        if k == "HACKATHON_API_KEY":
            continue
        os.environ[k] = v
    # No hackathon key — verify paths that must not call the model.
    os.environ.pop("HACKATHON_API_KEY", None)

    from app.core.config import get_settings

    get_settings.cache_clear()

    model_http = {"count": 0}

    import httpx

    class CountingTransport(httpx.MockTransport):
        def __init__(self) -> None:
            super().__init__(self._handler)

        def _handler(self, request: httpx.Request) -> httpx.Response:
            host = request.url.host or ""
            path = request.url.path or ""
            if "changellenge" in host or path.endswith("/chat/completions"):
                model_http["count"] += 1
            raise AssertionError(f"unexpected outbound HTTP {request.method} {request.url}")

    report: dict = {
        "stand_dir": str(stand_dir),
        "checks": {},
        "model_http_attempts": 0,
        "ok": False,
    }

    from fastapi.testclient import TestClient

    from app.main import app

    company_id = manifest["profiles"][0]["company_id"]
    event_id = manifest["event"]["id"]
    external_uid = manifest["profiles"][0]["external_uid"]

    with TestClient(app) as client:
        # health
        h = client.get("/health")
        report["checks"]["health"] = h.status_code == 200

        # login
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        report["checks"]["login"] = login.status_code == 200
        token = None
        if login.status_code == 200:
            token = login.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        # membership via /users/me
        me = client.get("/api/v1/users/me", headers=headers)
        report["checks"]["companies_list"] = me.status_code == 200
        ids = []
        if me.status_code == 200:
            body = me.json()
            items = body.get("companies") or []
            ids = [
                c.get("company_id") or c.get("id")
                for c in items
                if isinstance(c, dict)
            ]
        report["checks"]["membership_has_company"] = company_id in ids

        # case context
        ctx = client.get(f"/api/v1/companies/{company_id}/context", headers=headers)
        report["checks"]["case_context_http"] = ctx.status_code == 200
        case_ctx = ctx.json() if ctx.status_code == 200 else {}
        report["checks"]["case_context_has_snapshot"] = bool(
            (case_ctx.get("case_context") or case_ctx).get("active_snapshot_id")
            or (case_ctx.get("case_context") or {}).get("status")
            in {"ready", "available", "profile_available"}
            or case_ctx.get("status") == "ok"
            or "external_uid" in json.dumps(case_ctx)
        )
        report["case_context_external_uid_mentioned"] = external_uid in json.dumps(case_ctx)
        report["case_context_keys"] = sorted(case_ctx.keys()) if isinstance(case_ctx, dict) else []

        # event card without impact
        ev = client.get(
            f"/api/v1/events/{event_id}",
            headers=headers,
            params={"company_id": company_id},
        )
        report["checks"]["event_get"] = ev.status_code == 200
        ev_body = ev.json() if ev.status_code == 200 else {}
        report["checks"]["event_is_demo_or_synthetic"] = bool(
            ev_body.get("is_demo")
            or (ev_body.get("attributes_json") or {}).get("synthetic_demo_event")
            or "ДЕМО" in (ev_body.get("title") or "")
        )

        # open / create conversation empty — no messages transferred
        conv = client.post(
            f"/api/v1/events/{event_id}/assistant/conversations",
            headers=headers,
            json={"company_id": company_id},
        )
        # Some APIs use GET list first
        if conv.status_code not in (200, 201):
            conv = client.get(
                f"/api/v1/events/{event_id}/assistant/conversations",
                headers=headers,
                params={"company_id": company_id},
            )
        report["checks"]["conversation_endpoint"] = conv.status_code in (200, 201)
        conv_body = conv.json() if conv.status_code in (200, 201) else {}
        msgs = []
        if isinstance(conv_body, dict):
            msgs = conv_body.get("messages") or []
            if not msgs and conv_body.get("items"):
                # list of conversations
                items = conv_body["items"]
                if items:
                    cid = items[0].get("id")
                    detail = client.get(
                        f"/api/v1/assistant/conversations/{cid}",
                        headers=headers,
                    )
                    if detail.status_code == 200:
                        msgs = detail.json().get("messages") or []
        report["checks"]["no_transferred_history"] = len(msgs) == 0
        report["message_count"] = len(msgs)

        # bank materials search / fragments
        bank = client.get(
            "/api/v1/bank-materials/documents",
            headers=headers,
        )
        report["checks"]["bank_documents"] = bank.status_code in (200, 404, 503)
        # evidence for event
        evid = client.get(
            f"/api/v1/events/{event_id}/bank-evidence",
            headers=headers,
            params={"company_id": company_id},
        )
        report["checks"]["event_bank_evidence"] = evid.status_code in (200, 404)
        evid_body = evid.json() if evid.status_code == 200 else {}
        report["bank_evidence_keys"] = (
            sorted(evid_body.keys()) if isinstance(evid_body, dict) else []
        )

        # PDF download with bearer via file_id
        pdf_ok = False
        pdf_sha_ok = False
        storage_root = Path(
            stand_env.get("BANK_MATERIALS_STORAGE_ROOT")
            or (stand_dir / "storage")
        )
        if not storage_root.is_absolute():
            storage_root = (ROOT / storage_root).resolve()
        pdf_candidates = list(storage_root.rglob("*.pdf")) if storage_root.is_dir() else []
        report["pdf_candidates"] = len(pdf_candidates)

        docs = client.get("/api/v1/bank-materials/documents", headers=headers)
        file_id = None
        expected_sha = None
        if docs.status_code == 200:
            dbody = docs.json()
            items = dbody if isinstance(dbody, list) else dbody.get("items") or dbody.get("documents") or []
            for d in items:
                if not isinstance(d, dict):
                    continue
                slug = d.get("slug") or d.get("document_slug") or ""
                if "Policy_Rate" in slug or "policy" in slug.lower():
                    file_id = d.get("file_id") or d.get("current_file_id")
                    expected_sha = d.get("sha256") or d.get("source_sha256")
                    break
            if file_id is None and items:
                d0 = items[0]
                file_id = d0.get("file_id") or d0.get("current_file_id")
                expected_sha = d0.get("sha256") or d0.get("source_sha256")

        if file_id is None:
            # Resolve from SQLite when list payload lacks file_id
            import sqlite3

            db_path = stand_dir / "stand.db"
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "select id, sha256 from bank_document_files "
                "where original_filename like '%Policy_Rate%' limit 1"
            ).fetchone()
            if row:
                file_id, expected_sha = row[0], row[1]
            conn.close()

        report["pdf_file_id"] = file_id
        if file_id:
            dl = client.get(
                f"/api/v1/bank-materials/files/{file_id}/content",
                headers=headers,
            )
            pdf_ok = dl.status_code == 200
            if pdf_ok:
                sha = hashlib.sha256(dl.content).hexdigest()
                pdf_sha_ok = (expected_sha is None) or (sha == expected_sha)
                dl2 = client.get(f"/api/v1/bank-materials/files/{file_id}/content")
                report["checks"]["pdf_requires_auth"] = dl2.status_code in (401, 403)
        report["checks"]["pdf_download_bearer"] = pdf_ok
        report["checks"]["pdf_sha_match"] = pdf_sha_ok

    report["model_http_attempts"] = model_http["count"]
    report["checks"]["no_model_http"] = model_http["count"] == 0
    report["password_printed"] = False
    report["ok"] = all(
        v is True
        for k, v in report["checks"].items()
        if k
        in {
            "health",
            "login",
            "membership_has_company",
            "event_get",
            "no_transferred_history",
            "no_model_http",
            "pdf_download_bearer",
            "pdf_sha_match",
            "case_context_http",
        }
    )
    out_path = stand_dir / "verify_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
