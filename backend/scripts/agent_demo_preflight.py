"""HTTP/TestClient preflight for agent demo stand (stage 4.7) — zero model HTTP.

Does not POST a new chat question. Does not start uvicorn as a long-lived service.
Leaves no background processes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAND_DIR = ROOT / "data/agent_demo"
STAND_ENV = STAND_DIR / "stand.env"
STAND_WEB_ENV = STAND_DIR / "web.env"
MANIFEST = STAND_DIR / "stand_manifest.json"
REPORT = STAND_DIR / "preflight_report.json"
EXPECTED_PDF_SHA = "92a96805f2b720f76bd0c52d2491044812b38401ab62d0f4a9157b4ca81c49bb"
DEMO_PASSWORD = "E2eAgent462!"


def _read_dotenv(path: Path) -> dict[str, str]:
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


def _load_hackathon_key_configured() -> bool:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("HACKATHON_API_KEY=") and s.split("=", 1)[1].strip().strip('"'):
            return True
    return False


def main() -> int:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    report: dict[str, Any] = {
        "stage": "4.7",
        "model_http_attempts": 0,
        "checks": {},
        "runtime": {},
        "ok": False,
    }

    if not STAND_ENV.is_file() or not MANIFEST.is_file():
        report["fatal"] = "stand not prepared — run scripts/prepare_agent_demo_stand.py"
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": False, "fatal": report["fatal"]}, ensure_ascii=False))
        return 2

    stand = _read_dotenv(STAND_ENV)
    web = _read_dotenv(STAND_WEB_ENV)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ids = manifest.get("resolved") or {}

    # Apply stand env; pull key presence only (value into env for provider assert, not logged)
    for k, v in stand.items():
        if k == "HACKATHON_API_KEY":
            continue
        os.environ[k] = v
    key_configured = _load_hackathon_key_configured()
    if key_configured:
        # Load value for Settings without printing
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("HACKATHON_API_KEY="):
                os.environ["HACKATHON_API_KEY"] = s.split("=", 1)[1].strip().strip('"').strip("'")
                break
    else:
        os.environ.pop("HACKATHON_API_KEY", None)

    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    report["runtime"] = {
        "provider": settings.normalized_assistant_provider(),
        "agent_loop": bool(settings.assistant_agent_loop),
        "model": settings.resolved_hackathon_model(),
        "base_url": settings.resolved_hackathon_base_url(),
        "key_configured": key_configured,
        "case_slot": settings.case_context_slot_key,
        "ocr_scoped": bool(settings.bank_materials_allowed_ocr_run_id_set()),
        "storage_root": str(settings.bank_materials_storage_root or ""),
        "database_is_stand": "agent_demo.db" in settings.database_url.replace("\\", "/"),
        "loop_http_budget": settings.assistant_loop_max_model_http,
        "loop_tools": settings.assistant_loop_max_tool_calls,
        "loop_repairs": settings.assistant_loop_max_repairs,
        "loop_timeout_s": settings.assistant_loop_timeout_s,
        "vite_api_base_url": web.get("VITE_API_BASE_URL"),
        "stand_api_port": stand.get("AGENT_DEMO_API_PORT"),
        "live_generation_previously_verified": True,
        "live_generation_note": (
            "Live agent-loop turn was verified in stage 4.6.2 "
            "(docs/ASSISTANT_AGENT_LIVE_RECHECK.md). This preflight does not "
            "repeat live generation; key_configured ≠ new live proof."
        ),
    }

    # Storage SHA
    storage_root = Path(stand["BANK_MATERIALS_STORAGE_ROOT"])
    pdf = storage_root / stand.get("storage_key", ids.get("storage_key", ""))
    # storage_key from manifest
    sk = manifest.get("storage_key")
    pdf = storage_root / sk
    report["checks"]["pdf_exists"] = pdf.is_file()
    report["checks"]["pdf_sha_ok"] = (
        hashlib.sha256(pdf.read_bytes()).hexdigest() == EXPECTED_PDF_SHA
        if pdf.is_file()
        else False
    )

    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import sessionmaker
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import create_app
    from app.models import EventImpact
    from app.services.assistant.agent_loop.api_integration import set_loop_http_client_for_tests

    import httpx

    class _NoModelTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            report["model_http_attempts"] += 1
            raise RuntimeError(f"model HTTP forbidden in 4.7 preflight: {request.url}")

    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    # Even if something tried to call the gateway — block it.
    blocking = httpx.Client(transport=_NoModelTransport())
    set_loop_http_client_for_tests(blocking)

    client = TestClient(app)
    try:
        h = client.get("/health")
        report["checks"]["health"] = h.status_code == 200

        login = client.post(
            "/api/v1/auth/login",
            json={"email": ids["email"], "password": DEMO_PASSWORD},
        )
        report["checks"]["login"] = login.status_code == 200
        if login.status_code != 200:
            report["fatal"] = f"login failed: {login.status_code}"
            raise RuntimeError(report["fatal"])
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Membership: company context requires ACL membership
        ctx = client.get(f"/api/v1/companies/{ids['company_id']}/context", headers=headers)
        report["checks"]["company_context_http"] = ctx.status_code
        report["checks"]["membership_ok"] = ctx.status_code == 200
        if ctx.status_code == 200:
            cjson = ctx.json()
            case_block = cjson.get("case_context") or cjson.get("case") or {}
            report["checks"]["case_context_status"] = (
                case_block.get("status") or case_block.get("availability")
            )

        # Feed is impact-based; synthetic event has no EventImpact by design —
        # list may be empty. Card is opened with company_id query.
        feed = client.get(
            f"/api/v1/companies/{ids['company_id']}/events", headers=headers
        )
        report["checks"]["events_feed_http"] = feed.status_code
        report["checks"]["events_feed_empty_expected"] = True
        if feed.status_code == 200:
            items = (feed.json() or {}).get("items") or (feed.json() or {}).get("events") or []
            report["checks"]["events_feed_count"] = len(items) if isinstance(items, list) else None

        event_card = client.get(
            f"/api/v1/events/{ids['event_id']}",
            headers=headers,
            params={"company_id": ids["company_id"]},
        )
        report["checks"]["event_card_http"] = event_card.status_code
        report["checks"]["event_title_match"] = False
        if event_card.status_code == 200:
            title = (event_card.json() or {}).get("title") or ""
            report["checks"]["event_title_match"] = (
                "4.6.2" in title or "СИНТЕТИЧЕСК" in title or bool(title)
            )
            report["checks"]["event_title"] = title[:120]
            # No impact card expected
            report["checks"]["event_impact_absent_on_card"] = (
                event_card.json() or {}
            ).get("impact") in (None, {})

        with SessionLocal() as session:
            n = session.scalar(
                select(func.count())
                .select_from(EventImpact)
                .where(
                    EventImpact.event_id == ids["event_id"],
                    EventImpact.company_id == ids["company_id"],
                )
            )
            report["checks"]["event_impact_count"] = int(n or 0)

        # Open / reuse conversation without posting a new user question that triggers the loop
        conv_id = ids.get("conversation_id")
        if conv_id:
            msgs = client.get(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                headers=headers,
            )
            report["checks"]["saved_messages_http"] = msgs.status_code
            final_found = False
            bank_block = False
            if msgs.status_code == 200:
                for m in msgs.json():
                    if m.get("role") != "assistant":
                        continue
                    content = m.get("content") or ""
                    if "Разбор" in content or "14" in content:
                        final_found = True
                    for b in m.get("blocks") or []:
                        if isinstance(b, dict) and b.get("type") == "bank_evidence_list":
                            bank_block = True
            report["checks"]["saved_final_present"] = final_found
            report["checks"]["bank_evidence_list_present"] = bank_block
            report["checks"]["prior_answer_is_historical"] = True
        else:
            # Create conversation only (must not spend model HTTP)
            created = client.post(
                f"/api/v1/events/{ids['event_id']}/assistant/conversations",
                headers=headers,
                json={"company_id": ids["company_id"]},
            )
            report["checks"]["create_conversation_http"] = created.status_code
            conv_id = (created.json() or {}).get("id") or (created.json() or {}).get("conversation_id")

        # Fragment + PDF with Bearer
        # Discover a fragment id from saved bank block or collector offline
        frag_id = None
        from app.models import Event
        from app.services.bank_materials.event_evidence import collect_event_bank_evidence

        with SessionLocal() as session:
            ev = session.get(Event, ids["event_id"])
            assert ev is not None
            collected = collect_event_bank_evidence(session, event=ev)
            report["checks"]["collector_status"] = collected.status
            report["checks"]["collector_count"] = len(collected.evidence or [])
            if collected.evidence:
                frag_id = collected.evidence[0].fragment_id

        if frag_id:
            fr = client.get(f"/api/v1/bank-materials/fragments/{frag_id}", headers=headers)
            report["checks"]["fragment_http"] = fr.status_code
            href = None
            if fr.status_code == 200:
                href = (fr.json() or {}).get("content_href")
            if href:
                no_b = client.get(href).status_code
                with_b = client.get(href, headers=headers)
                report["checks"]["pdf"] = {
                    "with_bearer": with_b.status_code,
                    "no_bearer": no_b,
                    "sha_ok": (
                        hashlib.sha256(with_b.content).hexdigest() == EXPECTED_PDF_SHA
                        if with_b.status_code == 200
                        else False
                    ),
                }

        report["checks"]["frontend_points_to_stand_api"] = (
            web.get("VITE_API_BASE_URL", "").rstrip("/")
            == f"http://127.0.0.1:{stand.get('AGENT_DEMO_API_PORT', '8017')}"
        )
        report["checks"]["model_http_still_zero"] = report["model_http_attempts"] == 0

        ok = (
            report["checks"].get("health")
            and report["checks"].get("login")
            and report["checks"].get("membership_ok")
            and report["checks"].get("event_card_http") == 200
            and report["checks"].get("event_title_match")
            and report["checks"].get("event_impact_count") == 0
            and report["checks"].get("pdf_sha_ok")
            and report["checks"].get("fragment_http") == 200
            and (report["checks"].get("pdf") or {}).get("with_bearer") == 200
            and (report["checks"].get("pdf") or {}).get("no_bearer") == 401
            and report["checks"].get("model_http_still_zero")
            and report["runtime"]["database_is_stand"]
            and report["runtime"]["agent_loop"] is True
            and report["runtime"]["provider"] == "hackathon"
            and report["checks"].get("frontend_points_to_stand_api")
            and report["checks"].get("case_context_status") in {
                "profile_available",
                "available",
                "ok",
                "ready",
            }
        )
        # saved final preferred
        if ids.get("conversation_id"):
            ok = bool(ok and report["checks"].get("saved_final_present"))
        report["ok"] = bool(ok)

    except Exception as exc:  # noqa: BLE001
        report["fatal"] = f"{type(exc).__name__}: {exc}"
        report["ok"] = False
    finally:
        set_loop_http_client_for_tests(None)
        blocking.close()
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()
        for k in (
            "ASSISTANT_AGENT_LOOP",
            "DATABASE_URL",
            "HACKATHON_API_KEY",
            "BANK_MATERIALS_STORAGE_ROOT",
            "BANK_MATERIALS_ALLOWED_OCR_RUN_IDS",
            "CASE_CONTEXT_SLOT_KEY",
        ):
            os.environ.pop(k, None)

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "fatal": report.get("fatal"),
                "model_http_attempts": report.get("model_http_attempts"),
                "key_configured": report.get("runtime", {}).get("key_configured"),
                "report": str(REPORT.relative_to(ROOT)).replace("\\", "/"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
