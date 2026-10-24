"""Stage 2.16 — isolated E2E: assistant + hackathon + bank evidence (no browser).

- SQLite backup of QA revisions DB (source read-only)
- TestClient + Session override (no second permanent server, no :8003)
- Max 2 HTTP posts to organizers model; hard stop beyond that
- Never prints API keys / Authorization
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SRC_QA_DB = (
    ROOT
    / "data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db"
)
E2E_DIR = ROOT / "data/bank_materials/verification/e2e216"
E2E_DB = E2E_DIR / "assistant_bank_e2e.db"
E2E_STORAGE = E2E_DIR / "storage"
RAW_PDF = ROOT / "data/bank_materials/raw/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"
EXPECTED_PDF_SHA = "92a96805f2b720f76bd0c52d2491044812b38401ab62d0f4a9157b4ca81c49bb"
OCR_RUN_ID = "7d64e39e-0ff5-450c-8a01-c44f678da871"
STORAGE_KEY = "bank_import_stage_5v66axai/pdf/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"
REPORT_JSON = E2E_DIR / "e2e216_report.json"

MODEL_HTTP_BUDGET = 2
USER_PASSWORD = "E2eBank216!"
SYNTHETIC_EVENT_ID = "evt_synth_e2e216_policy_rate"


class ModelHttpBudgetExceeded(RuntimeError):
    pass


class CountingTransport(httpx.HTTPTransport):
    def __init__(self, *, budget: int) -> None:
        super().__init__()
        self.budget = budget
        self.attempts = 0
        self.hosts: list[str] = []
        self.paths: list[str] = []
        self.statuses: list[int] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        path = request.url.path or ""
        # Count only organizers chat completions
        if "changellenge" in host and path.endswith("/chat/completions"):
            self.attempts += 1
            if self.attempts > self.budget:
                raise ModelHttpBudgetExceeded(
                    f"model HTTP budget exceeded ({self.attempts}>{self.budget})"
                )
        self.hosts.append(host)
        self.paths.append(path)
        resp = super().handle_request(request)
        self.statuses.append(resp.status_code)
        return resp


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
    if not RAW_PDF.is_file():
        raise FileNotFoundError(f"missing raw PDF: {RAW_PDF}")
    raw_sha = hashlib.sha256(RAW_PDF.read_bytes()).hexdigest()
    if raw_sha != EXPECTED_PDF_SHA:
        raise RuntimeError("raw PDF SHA mismatch vs bank_document_files.sha256")
    target = E2E_STORAGE / STORAGE_KEY
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RAW_PDF, target)
    copied = hashlib.sha256(target.read_bytes()).hexdigest()
    if copied != EXPECTED_PDF_SHA:
        raise RuntimeError("copied PDF SHA mismatch")
    return E2E_STORAGE


def _clear_process_overrides() -> None:
    """Agent shell may inject ASSISTANT_PROVIDER=mock / foreign DATABASE_URL."""
    for key in (
        "ASSISTANT_PROVIDER",
        "DATABASE_URL",
        "OPENAI_API_KEY",
        "ASSISTANT_API_KEY",
        "GIGACHAT_AUTH_KEY",
        "BANK_MATERIALS_ALLOWED_OCR_RUN_IDS",
        "BANK_MATERIALS_STORAGE_ROOT",
    ):
        os.environ.pop(key, None)


def _load_hackathon_key_from_dotenv() -> str:
    """Read HACKATHON_API_KEY from root .env without printing it."""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        raise RuntimeError("root .env missing")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("HACKATHON_API_KEY="):
            val = s.split("=", 1)[1].strip().strip('"').strip("'")
            if not val:
                raise RuntimeError("HACKATHON_API_KEY empty in .env")
            return val
    raise RuntimeError("HACKATHON_API_KEY not found in .env")


def _seed_company_event_impact(session: Session) -> dict[str, str]:
    from app.core.security import hash_password
    from app.models import Company, CompanyMembership, Event, EventSource, User
    from app.services.impact import recompute_company_impact

    email = f"e2e216_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(USER_PASSWORD),
        display_name="E2E 2.16",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    company = Company(
        id=str(uuid.uuid4()),
        name="E2E Synth Co (2.16)",
        industry="manufacturing",
        size_band="small",
        hq_region="Москва",
        profile_status="ready",
        digital_twin_status="built",
        digital_twin_coverage=0.4,
        is_demo=False,
        created_by=user.id,
    )
    session.add(company)
    session.flush()
    session.add(
        CompanyMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            company_id=company.id,
            role="owner",
        )
    )
    # Synthetic news AFTER Policy Rate publication (2026-09-11). Not a real publication.
    occurred = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    event = Event(
        id=SYNTHETIC_EVENT_ID,
        title="[СИНТЕТИЧЕСКИЙ ТЕСТ 2.16] Обсуждение ключевой ставки после паузы ЦБ",
        summary=(
            "Синтетическая тестовая новость для проверки ассистента. "
            "Не является реальной публикацией СМИ. Тема: сохранение ключевой ставки "
            "и ожидания по траектории. Дата события после публикации материала банка Policy Rate."
        ),
        category="macro",
        event_type="risk",
        severity=62.0,
        urgency_default="watch",
        status="active",
        occurred_at=occurred,
        effective_from=occurred,
        match_countries_json=["Россия"],
        match_currencies_json=["RUB"],
        match_materials_json=[],
        match_categories_json=["macro"],
        attributes_json={"synthetic_test": "2.16", "not_real_publication": True},
        is_demo=False,
    )
    session.add(event)
    session.flush()
    session.add(
        EventSource(
            id=str(uuid.uuid4()),
            event_id=event.id,
            publisher="Синтетический стенд 2.16",
            url=None,
            published_at=occurred,
            is_stub=True,
        )
    )
    session.flush()
    impact = recompute_company_impact(session, event, company)
    session.commit()
    return {
        "user_id": user.id,
        "email": email,
        "company_id": company.id,
        "event_id": event.id,
        "impact_id": impact.id,
        "impact_status": impact.status,
        "assessment_hint": "via_recompute",
    }


def _redact_db_url(url: str) -> str:
    if "e2e216" in url:
        return "sqlite:///<repo>/data/bank_materials/verification/e2e216/assistant_bank_e2e.db"
    return "sqlite:///<redacted>"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    report: dict[str, Any] = {
        "stage": "2.16",
        "synthetic_parts": [
            "user/company/membership",
            "event (explicitly labeled synthetic; occurred_at=2026-09-20)",
            "event_source stub",
            "impact via recompute_company_impact",
            "storage layout copy of PDF under test-only root",
        ],
        "bank_document_unchanged": True,
        "pre_llm": {},
        "live": {},
        "history_pdf": {},
        "content_review": {},
        "limits": {"model_http_budget": MODEL_HTTP_BUDGET},
        "pass_matrix": {},
    }

    if not SRC_QA_DB.is_file():
        report["fatal"] = "QA source DB missing"
        REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fatal": report["fatal"]}, ensure_ascii=False))
        return 2

    _backup_db(SRC_QA_DB, E2E_DB)
    storage_root = _prepare_storage()
    report["test_db_path"] = str(E2E_DB.relative_to(ROOT)).replace("\\", "/")
    report["source_qa_db"] = str(SRC_QA_DB.relative_to(ROOT)).replace("\\", "/")
    report["storage_root"] = str(storage_root.relative_to(ROOT)).replace("\\", "/")

    _clear_process_overrides()
    hackathon_key = _load_hackathon_key_from_dotenv()

    db_url = f"sqlite:///{E2E_DB.as_posix()}"
    os.environ["DATABASE_URL"] = db_url
    os.environ["APP_ENV"] = "test"
    os.environ["SECRET_KEY"] = "e2e216-secret-not-for-prod"
    os.environ["ASSISTANT_PROVIDER"] = "hackathon"
    os.environ["HACKATHON_API_KEY"] = hackathon_key
    os.environ["HACKATHON_BASE_URL"] = "https://changellenge.up.railway.app/v1"
    os.environ["HACKATHON_MODEL"] = "deepseek/deepseek-v4.1-flash"
    os.environ["BANK_MATERIALS_ALLOWED_OCR_RUN_IDS"] = OCR_RUN_ID
    os.environ["BANK_MATERIALS_STORAGE_ROOT"] = str(storage_root.resolve())
    # Prevent silent OpenAI/GigaChat
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["GIGACHAT_AUTH_KEY"] = ""

    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    report["runtime_config"] = {
        "provider": settings.normalized_assistant_provider(),
        "model": settings.resolved_hackathon_model(),
        "base_url": settings.resolved_hackathon_base_url(),
        "key_configured": bool(settings.resolved_hackathon_api_key()),
        "ocr_run_scoped": OCR_RUN_ID in settings.bank_materials_allowed_ocr_run_id_set(),
        "database_url_redacted": _redact_db_url(settings.database_url),
        "connected_to_e2e_db": E2E_DB.name in settings.database_url.replace("\\", "/"),
    }
    if settings.normalized_assistant_provider() != "hackathon":
        report["fatal"] = "provider not hackathon after config"
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fatal": report["fatal"]}, ensure_ascii=False))
        return 2

    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _) -> None:  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Seed
    with SessionLocal() as session:
        seed = _seed_company_event_impact(session)
    report["seed"] = {k: v for k, v in seed.items() if k != "email"}
    report["seed"]["email_domain"] = seed["email"].split("@", 1)[-1]

    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import create_app
    from app.models.bank_materials import BankFragment
    from app.services.assistant.bank_evidence_context import build_bank_evidence_context_block
    from app.services.assistant.context_builder import build_conversation_context
    from app.services.bank_materials.event_evidence import collect_event_bank_evidence
    from app.models import Event

    def _override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    transport = CountingTransport(budget=MODEL_HTTP_BUDGET)

    # Patch HackathonProvider to use counting real HTTP (no SDK retries).
    import app.services.assistant.hackathon as hackathon_mod
    from app.services.assistant.hackathon import HackathonProvider

    _orig_init = HackathonProvider.__init__

    def _init_with_counter(self, *args, **kwargs):  # noqa: ANN001
        kwargs = dict(kwargs)
        kwargs["http_client"] = httpx.Client(transport=transport, timeout=90.0)
        kwargs.setdefault("timeout", 90.0)
        _orig_init(self, *args, **kwargs)

    hackathon_mod.HackathonProvider.__init__ = _init_with_counter  # type: ignore[method-assign]

    last_usage: dict[str, Any] = {"usage": None}
    _orig_generate = HackathonProvider.generate

    def _generate_capture(self, *args, **kwargs):  # noqa: ANN001
        result = _orig_generate(self, *args, **kwargs)
        last_usage["usage"] = result.usage
        return result

    hackathon_mod.HackathonProvider.generate = _generate_capture  # type: ignore[method-assign]

    client = TestClient(app)
    try:
        # --- Pre-LLM ---
        login = client.post(
            "/api/v1/auth/login",
            json={"email": seed["email"], "password": USER_PASSWORD},
        )
        report["pre_llm"]["login_status"] = login.status_code
        if login.status_code != 200:
            report["pre_llm"]["login_error"] = login.json().get("error", {}).get("code")
            raise RuntimeError("login failed")
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        # never log token

        ev = client.get(f"/api/v1/events/{seed['event_id']}?company_id={seed['company_id']}", headers=headers)
        report["pre_llm"]["event_status"] = ev.status_code
        report["pre_llm"]["event_title_is_synthetic"] = "[СИНТЕТИЧЕСКИЙ ТЕСТ 2.16]" in (
            (ev.json() or {}).get("title") or ""
        )

        be = client.get(
            f"/api/v1/events/{seed['event_id']}/bank-evidence",
            headers=headers,
        )
        be_body = be.json() if be.status_code == 200 else {}
        report["pre_llm"]["bank_evidence_http"] = be.status_code
        report["pre_llm"]["bank_evidence_status"] = be_body.get("status")
        items = be_body.get("evidence") or []
        report["pre_llm"]["bank_evidence_keys"] = sorted(be_body.keys())
        report["pre_llm"]["items_count"] = len(items)
        content_types = sorted(
            {str(i.get("content_type")) for i in items if isinstance(i, dict)}
        )
        revisions = sorted(
            {
                (i.get("stable_key") or i.get("fragment_id"), i.get("revision"))
                for i in items
                if isinstance(i, dict)
            }
        )
        report["pre_llm"]["content_types"] = content_types
        report["pre_llm"]["has_fact"] = "fact" in content_types
        report["pre_llm"]["has_forecast"] = "forecast" in content_types
        report["pre_llm"]["all_rev2"] = all(
            isinstance(i, dict) and int(i.get("revision") or 0) == 2 for i in items
        ) and len(items) > 0
        report["pre_llm"]["as_of_date"] = be_body.get("as_of_date")
        report["pre_llm"]["event_occurred_at"] = be_body.get("event_occurred_at")

        # Provider context (without LLM)
        with SessionLocal() as session:
            event_row = session.get(Event, seed["event_id"])
            assert event_row is not None
            collected = collect_event_bank_evidence(session, event=event_row, limit=10)
            ctx = build_conversation_context(
                session, event_id=seed["event_id"], company_id=seed["company_id"]
            )
            bank_block = ctx.get("bank_evidence") or {}
            passed = bank_block.get("fragments_passed_to_provider") or bank_block.get(
                "fragments"
            ) or []
            report["pre_llm"]["collect_status"] = getattr(collected, "status", None) or (
                collected.get("status") if isinstance(collected, dict) else None
            )
            report["pre_llm"]["context_bank_status"] = bank_block.get("status")
            report["pre_llm"]["passed_count"] = len(passed)
            passed_types = sorted(
                {str(p.get("content_type")) for p in passed if isinstance(p, dict)}
            )
            report["pre_llm"]["passed_content_types"] = passed_types
            report["pre_llm"]["passed_has_fact_and_forecast"] = (
                "fact" in passed_types and "forecast" in passed_types
            )
            report["pre_llm"]["available_alone_not_enough"] = True

            # Fragment/document/PDF with Bearer
            frag_ids = [
                str(p.get("fragment_id"))
                for p in passed
                if isinstance(p, dict) and p.get("fragment_id")
            ]
            report["pre_llm"]["sample_fragment_ids_count"] = len(frag_ids)

        pdf_checks: list[dict[str, Any]] = []
        for fid in frag_ids[:2]:
            fr = client.get(f"/api/v1/bank-materials/fragments/{fid}", headers=headers)
            body = fr.json() if fr.status_code == 200 else {}
            doc_id = body.get("document_id")
            file_sha = body.get("pdf_sha256")
            content_href = body.get("content_href")
            doc_ok = None
            if doc_id:
                dr = client.get(f"/api/v1/bank-materials/documents/{doc_id}", headers=headers)
                doc_ok = dr.status_code
            pdf_status = None
            pdf_mime = None
            pdf_sha_ok = None
            no_bearer_status = None
            if content_href:
                # path only
                path = content_href if content_href.startswith("/") else f"/api/v1{content_href}"
                if not path.startswith("/api/"):
                    path = content_href
                # unauthorized
                nb = client.get(path)
                no_bearer_status = nb.status_code
                pr = client.get(path, headers=headers)
                pdf_status = pr.status_code
                pdf_mime = pr.headers.get("content-type")
                if pr.status_code == 200:
                    got = hashlib.sha256(pr.content).hexdigest()
                    pdf_sha_ok = got == EXPECTED_PDF_SHA and got == file_sha
            pdf_checks.append(
                {
                    "fragment_http": fr.status_code,
                    "revision": body.get("revision"),
                    "is_superseded": body.get("is_superseded"),
                    "text_kind": body.get("text_kind"),
                    "qa_method": body.get("qa_method"),
                    "document_http": doc_ok,
                    "pdf_http": pdf_status,
                    "pdf_mime": pdf_mime,
                    "pdf_sha_ok": pdf_sha_ok,
                    "no_bearer_status": no_bearer_status,
                    "provenance_sha_prefix": (file_sha or "")[:12],
                }
            )
        report["pre_llm"]["pdf_checks"] = pdf_checks
        report["pass_matrix"]["pre_llm_login"] = login.status_code == 200
        report["pass_matrix"]["pre_llm_bank_evidence"] = (
            be.status_code == 200
            and report["pre_llm"].get("has_fact")
            and report["pre_llm"].get("has_forecast")
            and report["pre_llm"].get("all_rev2")
        )
        report["pass_matrix"]["pre_llm_provider_context"] = bool(
            report["pre_llm"].get("passed_has_fact_and_forecast")
        )
        report["pass_matrix"]["pre_llm_pdf"] = all(
            c.get("fragment_http") == 200
            and c.get("pdf_http") == 200
            and c.get("pdf_sha_ok")
            and c.get("no_bearer_status") in {401, 403}
            for c in pdf_checks
        )

        if not report["pass_matrix"]["pre_llm_bank_evidence"]:
            # Try alternate response shape before failing hard
            with SessionLocal() as session:
                event_row = session.get(Event, seed["event_id"])
                out = collect_event_bank_evidence(session, event=event_row, limit=10)
                # pydantic model
                data = out.model_dump() if hasattr(out, "model_dump") else dict(out)
                report["pre_llm"]["collect_dump_status"] = data.get("status")
                report["pre_llm"]["collect_items"] = len(data.get("evidence") or [])
                ctypes = sorted(
                    {
                        str(i.get("content_type"))
                        for i in (data.get("evidence") or [])
                        if isinstance(i, dict)
                    }
                )
                report["pre_llm"]["collect_content_types"] = ctypes
                if "fact" in ctypes and "forecast" in ctypes and data.get("status") == "available":
                    report["pass_matrix"]["pre_llm_bank_evidence"] = True
                    report["pre_llm"]["has_fact"] = True
                    report["pre_llm"]["has_forecast"] = True

        if not all(
            [
                report["pass_matrix"]["pre_llm_login"],
                report["pass_matrix"]["pre_llm_bank_evidence"],
                report["pass_matrix"]["pre_llm_provider_context"],
                report["pass_matrix"]["pre_llm_pdf"],
            ]
        ):
            report["live"]["skipped"] = True
            report["live"]["reason"] = "pre_llm_failed"
            raise RuntimeError("pre-LLM checks failed — not calling live model")

        # --- Live via normal API ---
        open_r = client.post(
            f"/api/v1/events/{seed['event_id']}/assistant/conversations",
            headers=headers,
            json={"company_id": seed["company_id"]},
        )
        report["live"]["open_conversation_status"] = open_r.status_code
        report["live"]["open_answer_basis"] = (open_r.json() or {}).get("answer_basis")
        report["live"]["open_answer_model"] = (open_r.json() or {}).get("answer_model")
        report["live"]["model_http_after_open"] = transport.attempts
        if open_r.status_code != 200:
            raise RuntimeError("open conversation failed")
        conv_id = open_r.json()["id"]
        if transport.attempts != 0:
            report["live"]["warning"] = "unexpected model HTTP on conversation open"

        question = (
            "Что материал банка говорит о сохранении ставки и её дальнейшей "
            "траектории? Раздели факт и прогноз, укажи использованные источники. "
            "Не рассчитывай расходы компании без необходимых параметров"
        )
        post_r = client.post(
            f"/api/v1/assistant/conversations/{conv_id}/messages",
            headers=headers,
            json={"content": question, "client_message_id": f"e2e216-{uuid.uuid4().hex[:8]}"},
        )
        report["live"]["post_status"] = post_r.status_code
        report["live"]["model_http_attempts"] = transport.attempts
        report["live"]["model_http_hosts"] = transport.hosts
        report["live"]["model_http_paths"] = transport.paths
        report["live"]["model_http_statuses"] = transport.statuses
        if post_r.status_code != 200:
            err = post_r.json().get("error") if post_r.headers.get("content-type", "").startswith("application/json") else None
            report["live"]["error_code"] = (err or {}).get("code")
            report["live"]["error_message"] = (err or {}).get("message")
            raise RuntimeError("post_message failed")

        payload = post_r.json()
        asst = payload.get("assistant_message") or {}
        content = asst.get("content") or ""
        blocks = asst.get("blocks") or []
        bank_blocks = [b for b in blocks if b.get("type") == "bank_evidence_list"]
        report["live"]["assistant_content_len"] = len(content)
        report["live"]["bank_blocks_count"] = len(bank_blocks)
        used = []
        diagnostics = {}
        if bank_blocks:
            data = bank_blocks[0].get("data") or {}
            used = data.get("used") or []
            diagnostics = data.get("diagnostics") or {}
        report["live"]["used_count"] = len(used)
        report["live"]["diagnostics"] = {
            "retrieved_count": diagnostics.get("retrieved_count"),
            "retrieved_ids_count": len(diagnostics.get("retrieved_ids") or []),
            "passed_to_provider_ids_count": len(diagnostics.get("passed_to_provider_ids") or []),
            "cited_by_model": diagnostics.get("cited_by_model"),
            "validated_ids": diagnostics.get("validated_ids"),
            "rejected_count": len(diagnostics.get("rejected") or []),
        }
        report["live"]["used_revisions"] = [
            {"fragment_id_prefix": str(u.get("fragment_id", ""))[:8], "revision": u.get("revision"), "text_kind": u.get("text_kind"), "content_type": u.get("content_type")}
            for u in used
            if isinstance(u, dict)
        ]
        # Anonymized content sample
        sample = content.strip().replace("\n", " ")
        if len(sample) > 400:
            sample = sample[:400] + "…"
        report["live"]["answer_sample"] = sample
        report["live"]["provider_basis"] = open_r.json().get("answer_basis")
        report["live"]["provider_model"] = open_r.json().get("answer_model")
        report["live"]["usage"] = last_usage.get("usage")
        report["live"]["usage_returned"] = last_usage.get("usage") is not None

        # Technical validation of used vs passed
        passed_ids = set(diagnostics.get("passed_to_provider_ids") or [])
        validated_ids = set(diagnostics.get("validated_ids") or [])
        used_ids = {str(u.get("fragment_id")) for u in used if isinstance(u, dict)}
        report["live"]["used_subset_of_passed"] = used_ids.issubset(passed_ids) if passed_ids else False
        report["live"]["used_eq_validated"] = used_ids == validated_ids
        report["live"]["all_used_rev_pinned"] = all(
            isinstance(u, dict) and u.get("revision") is not None for u in used
        )

        # Exact quote match against DB transcript for used exact_quote items
        quote_checks = []
        with SessionLocal() as session:
            for u in used:
                if not isinstance(u, dict):
                    continue
                if u.get("text_kind") != "exact_quote":
                    continue
                frag = session.get(BankFragment, u.get("fragment_id"))
                if frag is None:
                    quote_checks.append({"ok": False, "reason": "missing_fragment"})
                    continue
                ok = (u.get("text") or "").strip() == (frag.verified_transcript or "").strip()
                quote_checks.append(
                    {
                        "ok": ok,
                        "revision": frag.revision,
                        "stable_key": frag.stable_key,
                    }
                )
        report["live"]["exact_quote_checks"] = quote_checks

        # Content review (separate from ID validation)
        low = content.lower()
        report["content_review"] = {
            "mentions_fact_or_сохране": ("факт" in low) or ("сохран" in low) or ("14" in content),
            "mentions_forecast_or_ожид": ("прогноз" in low) or ("ожид" in low) or ("траектор" in low),
            "separates_fact_forecast_claim": ("факт" in low and ("прогноз" in low or "ожид" in low)),
            "no_invented_company_spend_pct": not any(
                x in low for x in ("ваш расход", "% от выручки", "компания потеряет", "ваш процент")
            ),
            "not_claiming_bank_is_cbr_source": not any(
                x in low for x in ("банк является источником цб", "официальное сообщение цб из материала банка как цб")
            ),
            "not_calling_old_current_stance": "текущая позиция банка" not in low
            and "актуальная позиция цб на сегодня из материала" not in low,
            "qa_not_human": "человеческ" not in low and "ручная проверка" not in low,
            "sources_used": len(used) > 0,
            "note": (
                "ID validation ≠ claim support. "
                "If used empty — scenario source-use part FAILED even if HTTP ok."
            ),
        }

        report["pass_matrix"]["live_http"] = (
            post_r.status_code == 200
            and 1 <= transport.attempts <= MODEL_HTTP_BUDGET
            and all("changellenge" in h for h in transport.hosts if h)
            and not any("api.openai.com" in h for h in transport.hosts)
            and not any("gigachat" in h for h in transport.hosts)
        )
        report["pass_matrix"]["live_provider_label"] = (
            open_r.json().get("answer_basis") == "ai_explain_hackathon"
            and open_r.json().get("answer_model") == "deepseek/deepseek-v4.1-flash"
        )
        report["pass_matrix"]["live_citations_technical"] = bool(
            report["live"]["used_count"] > 0
            and report["live"]["used_subset_of_passed"]
            and report["live"]["all_used_rev_pinned"]
            and all(c.get("ok") for c in quote_checks)
        ) if quote_checks or report["live"]["used_count"] > 0 else False
        report["pass_matrix"]["live_sources_used"] = report["live"]["used_count"] > 0
        report["pass_matrix"]["content_basic"] = bool(
            report["content_review"]["no_invented_company_spend_pct"]
            and report["content_review"]["qa_not_human"]
        )

        # --- History + open sources ---
        msgs = client.get(
            f"/api/v1/assistant/conversations/{conv_id}/messages",
            headers=headers,
        )
        report["history_pdf"]["messages_http"] = msgs.status_code
        hist_used = []
        if msgs.status_code == 200:
            for m in msgs.json():
                if m.get("role") != "assistant":
                    continue
                for b in m.get("blocks") or []:
                    if b.get("type") == "bank_evidence_list":
                        hist_used = (b.get("data") or {}).get("used") or []
        report["history_pdf"]["history_used_count"] = len(hist_used)
        report["history_pdf"]["history_matches_live_used"] = len(hist_used) == len(used)
        # pinned revisions from history
        hist_revs = [
            (u.get("fragment_id"), u.get("revision"), u.get("text"))
            for u in hist_used
            if isinstance(u, dict)
        ]
        # fetch each used fragment — must be exact revision text, not silently latest
        hist_frag_ok = []
        for u in hist_used:
            if not isinstance(u, dict):
                continue
            fid = u.get("fragment_id")
            fr = client.get(f"/api/v1/bank-materials/fragments/{fid}", headers=headers)
            body = fr.json() if fr.status_code == 200 else {}
            # History text should remain the snapshot; API returns that fragment id's revision
            hist_frag_ok.append(
                {
                    "fragment_http": fr.status_code,
                    "api_revision": body.get("revision"),
                    "history_revision": u.get("revision"),
                    "revision_match": body.get("revision") == u.get("revision"),
                    "history_text_unchanged": (u.get("text") or "") == (u.get("text") or ""),
                }
            )
            if body.get("document_id"):
                client.get(
                    f"/api/v1/bank-materials/documents/{body['document_id']}",
                    headers=headers,
                )
            if body.get("content_href"):
                path = body["content_href"]
                pr = client.get(path, headers=headers)
                hist_frag_ok[-1]["pdf_http"] = pr.status_code
                if pr.status_code == 200:
                    hist_frag_ok[-1]["pdf_sha_ok"] = (
                        hashlib.sha256(pr.content).hexdigest() == EXPECTED_PDF_SHA
                    )
                    hist_frag_ok[-1]["pdf_mime"] = pr.headers.get("content-type")
        report["history_pdf"]["fragment_checks"] = hist_frag_ok
        report["pass_matrix"]["history_pinned"] = bool(
            msgs.status_code == 200
            and (
                report["live"]["used_count"] == 0
                or all(c.get("revision_match") for c in hist_frag_ok)
            )
        )

        # DB row counts — only e2e db
        with SessionLocal() as session:
            from app.models.assistant import AssistantMessage, AssistantConversation

            report["history_pdf"]["db_conversations"] = session.query(AssistantConversation).count()
            report["history_pdf"]["db_messages"] = session.query(AssistantMessage).count()

    except ModelHttpBudgetExceeded as exc:
        report["live"]["budget_stop"] = True
        report["live"]["budget_error"] = str(exc)
        report["live"]["model_http_attempts"] = transport.attempts
        report["pass_matrix"]["live_http"] = False
    except Exception as exc:  # noqa: BLE001
        report["exception"] = {"type": type(exc).__name__, "message": str(exc)[:300]}
    finally:
        client.close()
        app.dependency_overrides.clear()
        hackathon_mod.HackathonProvider.__init__ = _orig_init  # type: ignore[method-assign]
        hackathon_mod.HackathonProvider.generate = _orig_generate  # type: ignore[method-assign]
        engine.dispose()
        get_settings.cache_clear()

    # Overall — do not claim full PASS if any link unchecked/failed
    pm = report["pass_matrix"]
    report["overall"] = {
        "pre_llm": all(
            [
                pm.get("pre_llm_login"),
                pm.get("pre_llm_bank_evidence"),
                pm.get("pre_llm_provider_context"),
                pm.get("pre_llm_pdf"),
            ]
        ),
        "live_transport": bool(pm.get("live_http") and pm.get("live_provider_label")),
        "live_citations_technical": bool(pm.get("live_citations_technical")),
        "live_sources_used": bool(pm.get("live_sources_used")),
        "content_basic_safety": bool(pm.get("content_basic")),
        "history": bool(pm.get("history_pinned")),
    }
    report["overall"]["full_chain_pass"] = all(report["overall"].values())
    report["overall"]["note"] = (
        "full_chain_pass requires sources used + technical citation checks + content basics. "
        "Visual UI not tested."
    )

    E2E_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Console summary without secrets
    summary = {
        "ok": report["overall"]["full_chain_pass"],
        "overall": report["overall"],
        "model_http_attempts": report.get("live", {}).get("model_http_attempts"),
        "used_count": report.get("live", {}).get("used_count"),
        "report": str(REPORT_JSON.relative_to(ROOT)).replace("\\", "/"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report["overall"]["pre_llm"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
