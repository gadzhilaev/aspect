"""Stage 3.3.2 — limited company-B recheck after response diagnostics fix.

- SQLite backup of e2e33 DB (source read-only; history unchanged)
- Pre-LLM verify B products / snapshot / event / bank / no orphan user msg
- Live POST only for B (same question); max 2 model HTTP total
- Reuse saved A_full_content from e2e33_report.json (do not regenerate A)
- Never prints API keys / Authorization / full prompt / reasoning_content
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SRC_E2E33_DB = (
    ROOT / "data/bank_materials/verification/e2e33/assistant_personalization_e2e.db"
)
SRC_REPORT = ROOT / "data/bank_materials/verification/e2e33/e2e33_report.json"
RECHECK_DIR = ROOT / "data/bank_materials/verification/e2e332"
RECHECK_DB = RECHECK_DIR / "assistant_personalization_recheck_b.db"
RECHECK_REPORT = RECHECK_DIR / "e2e332_report.json"
E2E_STORAGE = ROOT / "data/bank_materials/verification/e2e33/storage"
EXPECTED_PDF_SHA = "92a96805f2b720f76bd0c52d2491044812b38401ab62d0f4a9157b4ca81c49bb"
OCR_RUN_ID = "7d64e39e-0ff5-450c-8a01-c44f678da871"
USER_PASSWORD = "E2ePers33!"
MODEL_HTTP_BUDGET = 2  # primary + one shared fix retry
SYNTHETIC_EVENT_ID = "evt_synth_e2e33_policy_rate"
EXPECTED_FRAG_IDS = (
    "7255d02b-6a75-4aaa-91da-58e6e090abec",
    "f9faa1a6-fc16-418c-9a82-7ecfc46ecfb8",
    "f0e4170c-bde3-41c9-b060-90acb3d75759",
)
QUESTION = (
    "Что эта новость означает для нашей компании? Используй доступные "
    "данные компании и материалы банка. Отдели подтверждённое от "
    "предположений, объясни, что стоит проверить и чего пока нельзя "
    "рассчитать. Укажи использованные банковские источники"
)

# Prompt/config deltas after 3.3 that affect this recheck (documented, not changed here).
POST_33_CHANGES = [
    "inspect_chat_completions_body + structured PROVIDER_BAD_RESPONSE details (3.3.1)",
    "orchestrator shared ≤1 extra model HTTP for retryable bad response OR citation fix",
    "usage retained on parse failure",
]


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


def _clear_process_overrides() -> None:
    for key in (
        "ASSISTANT_PROVIDER",
        "DATABASE_URL",
        "OPENAI_API_KEY",
        "ASSISTANT_API_KEY",
        "GIGACHAT_AUTH_KEY",
        "BANK_MATERIALS_ALLOWED_OCR_RUN_IDS",
        "BANK_MATERIALS_STORAGE_ROOT",
        "CASE_CONTEXT_SLOT_KEY",
        "HACKATHON_API_KEY",
        "HACKATHON_MODEL",
        "HACKATHON_BASE_URL",
    ):
        os.environ.pop(key, None)


def _load_hackathon_key_from_dotenv() -> str:
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


def _product_map(case_block: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in case_block.get("products") or []:
        if isinstance(p, dict) and p.get("code"):
            out[str(p["code"])] = str(p.get("status"))
    return out


def _review_b(content: str) -> dict[str, Any]:
    low = (content or "").lower()
    deposit_hits = [
        m
        for m in ("депозит", "вклад", "dep=true", "dep = true", "dep: true", "ликвидн", "пролонгац")
        if m in low
    ]
    loan_hits = [m for m in ("кредит", "loa=true", "долг", "плавающ") if m in low]
    # Overclaim: LOA=false → «нет долгов вообще»
    overclaim_no_debt = any(
        p in low
        for p in (
            "нет долгов",
            "отсутствуют кредиты во всех",
            "вообще нет кредитов",
            "кредитов нет ни в одном",
        )
    )
    rate_hike_claim = any(
        p in low
        for p in (
            "повысил ставку",
            "повышение ключевой",
            "ставка повышена",
            "поднял ставку",
        )
    )
    invented_money = any(
        p in low
        for p in (
            "потеряете",
            "сэкономите",
            "млн руб",
            "миллион",
            "доходность вырастет на",
            "процентные расходы вырастут на",
        )
    )
    fact_forecast = ("forecast" in low or "прогноз" in low) and (
        "fact" in low or "факт" in low or "оставлена неизменной" in low or "сохранил" in low
    )
    check_qs = any(
        p in low
        for p in ("стоит проверить", "что стоит проверить", "проверить:", "пролонгац", "срок")
    )
    dep_attention = bool(deposit_hits) and (
        "dep" in low or "депозит" in low or "вклад" in low
    )
    return {
        "deposit_marker_hits": deposit_hits,
        "loan_marker_hits": loan_hits,
        "deposit_product_attended": dep_attention,
        "check_questions_present": check_qs,
        "no_overclaim_loa_false_as_no_debts": not overclaim_no_debt,
        "no_rate_hike_misread": not rate_hike_claim,
        "fact_forecast_separated_heuristic": fact_forecast,
        "no_invented_money_effect": not invented_money,
        "sample": (content or "")[:400],
    }


def main() -> int:
    if not SRC_E2E33_DB.is_file():
        print(json.dumps({"error": "e2e33 db missing", "path": str(SRC_E2E33_DB)}))
        return 2
    if not SRC_REPORT.is_file():
        print(json.dumps({"error": "e2e33 report missing — cannot reuse A"}))
        return 2

    src_report = json.loads(SRC_REPORT.read_text(encoding="utf-8"))
    a_content = src_report.get("live", {}).get("A_full_content")
    if not a_content:
        print(
            json.dumps(
                {
                    "error": "saved answer A missing in e2e33_report.json — will not regenerate A",
                },
                ensure_ascii=False,
            )
        )
        return 2

    seed = src_report.get("seed") or {}
    company_b_id = seed.get("company_b_id")
    snap_id = seed.get("snap_id")
    event_id = seed.get("event_id") or SYNTHETIC_EVENT_ID
    if not company_b_id or not snap_id:
        print(json.dumps({"error": "seed ids missing in e2e33 report"}))
        return 2

    RECHECK_DIR.mkdir(parents=True, exist_ok=True)
    _backup_db(SRC_E2E33_DB, RECHECK_DB)

    report: dict[str, Any] = {
        "stage": "3.3.2",
        "source_e2e33_db": str(SRC_E2E33_DB.relative_to(ROOT)).replace("\\", "/"),
        "recheck_db": str(RECHECK_DB.relative_to(ROOT)).replace("\\", "/"),
        "source_report": str(SRC_REPORT.relative_to(ROOT)).replace("\\", "/"),
        "reused_from_33": [
            "test DB snapshot (backup)",
            "company B / U_302 / synthetic event",
            "bank fragments rev2 + storage PDF",
            "A_full_content (not regenerated)",
            "same QUESTION string",
            "same HACKATHON model id",
        ],
        "post_33_code_changes_affecting_run": POST_33_CHANGES,
        "original_33_verdicts_preserved": src_report.get("verdicts"),
        "prep": {},
        "live_b": {},
        "content_compare": {},
        "verdicts_332": {},
    }

    # Resolve B user email from DB (not in report seed)
    conn = sqlite3.connect(f"file:{RECHECK_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    mem = conn.execute(
        "select user_id from company_memberships where company_id=?",
        (company_b_id,),
    ).fetchone()
    if not mem:
        print(json.dumps({"error": "company B membership missing"}))
        return 2
    user_b_row = conn.execute(
        "select id,email from users where id=?", (mem["user_id"],)
    ).fetchone()
    email_b = user_b_row["email"]
    user_b_id = user_b_row["id"]

    conv_row = conn.execute(
        "select id,status from assistant_conversations "
        "where company_id=? and event_id=? and user_id=? and status='active'",
        (company_b_id, event_id, user_b_id),
    ).fetchone()
    msgs = []
    if conv_row:
        msgs = [
            dict(r)
            for r in conn.execute(
                "select id,role,client_message_id,length(content) as len "
                "from assistant_messages where conversation_id=? order by created_at",
                (conv_row["id"],),
            )
        ]
    frag_revs = {
        r["id"]: r["revision"]
        for r in conn.execute(
            "select id,revision from bank_fragments where id in (?,?,?)",
            EXPECTED_FRAG_IDS,
        )
    }
    impact_n = conn.execute("select count(*) c from event_impacts").fetchone()["c"]
    scen_n = conn.execute("select count(*) c from scenarios").fetchone()["c"]
    dec_n = conn.execute("select count(*) c from decisions").fetchone()["c"]
    conn.close()

    user_msgs = [m for m in msgs if m["role"] == "user"]
    asst_msgs = [m for m in msgs if m["role"] == "assistant"]
    report["prep"]["history_b"] = {
        "conversation_id": conv_row["id"] if conv_row else None,
        "message_count": len(msgs),
        "user_messages": len(user_msgs),
        "assistant_messages": len(asst_msgs),
        "roles": [m["role"] for m in msgs],
        "orphan_user_without_assistant_answer": bool(user_msgs)
        and len(user_msgs) >= len(asst_msgs),
        # After 3.3 fail: opening assistant only — no user msg (rolled back).
        "safe_to_repost_same_question": len(user_msgs) == 0 and len(asst_msgs) >= 1,
    }
    report["prep"]["fragment_revisions"] = frag_revs
    report["prep"]["all_frags_rev2"] = all(frag_revs.get(i) == 2 for i in EXPECTED_FRAG_IDS)
    report["prep"]["counts_before"] = {
        "event_impact": impact_n,
        "scenario": scen_n,
        "decision": dec_n,
    }

    _clear_process_overrides()
    from app.core.config import get_settings

    get_settings.cache_clear()
    hk = _load_hackathon_key_from_dotenv()
    os.environ["DATABASE_URL"] = f"sqlite:///{RECHECK_DB.as_posix()}"
    os.environ["ASSISTANT_PROVIDER"] = "hackathon"
    os.environ["HACKATHON_API_KEY"] = hk
    os.environ["HACKATHON_BASE_URL"] = "https://changellenge.up.railway.app/v1"
    os.environ["HACKATHON_MODEL"] = "deepseek/deepseek-v4.1-flash"
    os.environ["BANK_MATERIALS_ALLOWED_OCR_RUN_IDS"] = OCR_RUN_ID
    os.environ["BANK_MATERIALS_STORAGE_ROOT"] = str(E2E_STORAGE)
    os.environ["CASE_CONTEXT_SLOT_KEY"] = "competition_default"
    os.environ["SECRET_KEY"] = "e2e332-recheck-secret"
    os.environ["APP_ENV"] = "test"
    get_settings.cache_clear()

    db_url = f"sqlite:///{RECHECK_DB.as_posix()}"
    engine = create_engine(db_url)

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import create_app
    from app.models import Decision, EventImpact, Scenario, User
    from app.models.assistant import AssistantMessage
    from app.models.bank_materials import BankFragment
    from app.services.assistant.context_builder import (
        CALCULATION_UNAVAILABLE,
        build_conversation_context,
        slim_live_context,
    )

    def _override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    transport = CountingTransport(budget=MODEL_HTTP_BUDGET)

    import app.services.assistant.hackathon as hackathon_mod
    from app.services.assistant.hackathon import HackathonProvider

    _orig_init = HackathonProvider.__init__
    _orig_generate = HackathonProvider.generate
    captured_contexts: list[dict[str, Any]] = []
    last_usage: dict[str, Any] = {"items": []}
    last_diag: dict[str, Any] = {"items": []}

    def _init_with_counter(self, *args, **kwargs):  # noqa: ANN001
        kwargs = dict(kwargs)
        kwargs["http_client"] = httpx.Client(transport=transport, timeout=90.0)
        kwargs.setdefault("timeout", 90.0)
        _orig_init(self, *args, **kwargs)

    def _generate_capture(self, *args, **kwargs):  # noqa: ANN001
        ctx = kwargs.get("context")
        if isinstance(ctx, dict):
            captured_contexts.append(
                {
                    "assessment_state": ctx.get("assessment_state"),
                    "has_impact_calculation": ctx.get("has_impact_calculation"),
                    "impact": ctx.get("impact"),
                    "products": _product_map(ctx.get("case_company_context") or {}),
                    "snapshot_id": (ctx.get("case_company_context") or {}).get(
                        "snapshot_id"
                    ),
                    "external_uid": (ctx.get("case_company_context") or {}).get(
                        "external_uid"
                    ),
                }
            )
        try:
            result = _orig_generate(self, *args, **kwargs)
            last_usage["items"].append(result.usage)
            return result
        except Exception as exc:  # noqa: BLE001
            # Capture safe AppError details without secrets
            from app.core.errors import AppError

            if isinstance(exc, AppError):
                safe = []
                for d in exc.details or []:
                    if not isinstance(d, dict):
                        continue
                    safe.append(
                        {
                            k: d.get(k)
                            for k in (
                                "reason",
                                "http_status",
                                "request_id",
                                "choices_count",
                                "finish_reason",
                                "content_type",
                                "content_length",
                                "has_refusal",
                                "has_tool_calls",
                                "has_reasoning_content",
                                "error_code",
                                "usage",
                            )
                            if k in d or d.get(k) is not None
                        }
                    )
                last_diag["items"].append(
                    {"code": exc.code, "details": safe, "http_attempt": transport.attempts}
                )
            raise

    hackathon_mod.HackathonProvider.__init__ = _init_with_counter  # type: ignore[method-assign]
    hackathon_mod.HackathonProvider.generate = _generate_capture  # type: ignore[method-assign]

    client = TestClient(app)
    try:
        with SessionLocal() as session:
            user_b = session.get(User, user_b_id)
            ctx_b = build_conversation_context(
                session,
                event_id=event_id,
                company_id=company_b_id,
                user=user_b,
            )
        pb = _product_map(ctx_b.get("case_company_context") or {})
        bank = ctx_b.get("bank_evidence") or {}
        passed = bank.get("fragments_passed_to_provider") or []
        passed_ids = sorted(
            str(p.get("fragment_id")) for p in passed if isinstance(p, dict)
        )
        passed_revs = {
            str(p.get("fragment_id")): p.get("revision")
            for p in passed
            if isinstance(p, dict)
        }
        slim = slim_live_context(ctx_b)
        report["prep"]["case_b"] = {
            "status": (ctx_b.get("case_company_context") or {}).get("status"),
            "snapshot_id": (ctx_b.get("case_company_context") or {}).get("snapshot_id"),
            "external_uid": (ctx_b.get("case_company_context") or {}).get("external_uid"),
            "products": pb,
            "assessment_state": ctx_b.get("assessment_state"),
            "impact_is_null": ctx_b.get("impact") is None,
            "event_id": (ctx_b.get("event") or {}).get("id"),
        }
        report["prep"]["bank"] = {
            "status": bank.get("status"),
            "passed_ids": passed_ids,
            "passed_revisions": passed_revs,
            "passed_ids_match_33": passed_ids == sorted(EXPECTED_FRAG_IDS),
            "all_passed_rev2": all(passed_revs.get(i) == 2 for i in EXPECTED_FRAG_IDS),
        }
        report["prep"]["slim"] = {
            "impact_null": slim.get("impact") is None,
            "products": _product_map(slim.get("case_company_context") or {}),
            "display_label": (slim.get("company") or {}).get("display_label"),
        }
        report["prep"]["comparable_to_33"] = {
            "loa_false_dep_true": pb.get("LOA") == "false" and pb.get("DEP") == "true",
            "same_snapshot": report["prep"]["case_b"]["snapshot_id"] == snap_id,
            "same_event": report["prep"]["case_b"]["event_id"] == event_id,
            "impact_null": report["prep"]["case_b"]["impact_is_null"],
            "assessment": report["prep"]["case_b"]["assessment_state"]
            == CALCULATION_UNAVAILABLE,
            "bank_ok": report["prep"]["bank"]["passed_ids_match_33"]
            and report["prep"]["bank"]["all_passed_rev2"],
            "no_orphan_user_msg": report["prep"]["history_b"][
                "safe_to_repost_same_question"
            ],
            "counts_clean": impact_n == 0 and scen_n == 0 and dec_n == 0,
        }
        report["prep"]["pass"] = all(report["prep"]["comparable_to_33"].values())

        if not report["prep"]["pass"]:
            report["live_b"]["skipped"] = True
            report["live_b"]["reason"] = "prep_failed"
            raise RuntimeError("prep checks failed — not calling live model")

        login = client.post(
            "/api/v1/auth/login",
            json={"email": email_b, "password": USER_PASSWORD},
        )
        report["prep"]["login_b"] = login.status_code
        if login.status_code != 200:
            raise RuntimeError("login B failed")
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # Reuse existing conversation via normal open (idempotent get-or-create).
        # Reason: same active conv from 3.3 with opening only — no hidden user msg.
        # New conversation not required.
        open_b = client.post(
            f"/api/v1/events/{event_id}/assistant/conversations",
            headers=headers,
            json={"company_id": company_b_id},
        )
        report["prep"]["open_b"] = {
            "status": open_b.status_code,
            "assessment_state": (open_b.json() or {}).get("assessment_state"),
            "has_impact_calculation": (open_b.json() or {}).get("has_impact_calculation"),
            "conversation_id": (open_b.json() or {}).get("id"),
            "reused_existing": (open_b.json() or {}).get("id")
            == report["prep"]["history_b"]["conversation_id"],
        }
        if open_b.status_code != 200:
            raise RuntimeError("open B failed")
        conv_id = open_b.json()["id"]
        report["prep"]["model_http_after_open"] = transport.attempts
        assert transport.attempts == 0

        # PDF + fragment API (Bearer) — one passed fragment
        frag_id = passed_ids[0]
        fr = client.get(f"/api/v1/bank-materials/fragments/{frag_id}", headers=headers)
        body = fr.json() if fr.status_code == 200 else {}
        doc_href = body.get("document_href")
        content_href = body.get("content_href")
        no_bearer = client.get(content_href).status_code if content_href else None
        with_bearer = (
            client.get(content_href, headers=headers) if content_href else None
        )
        doc_http = (
            client.get(doc_href, headers=headers).status_code if doc_href else None
        )
        report["prep"]["links"] = {
            "fragment_http": fr.status_code,
            "document_http": doc_http,
            "pdf_http": with_bearer.status_code if with_bearer else None,
            "no_bearer": no_bearer,
            "sha_ok": (
                hashlib.sha256(with_bearer.content).hexdigest() == EXPECTED_PDF_SHA
                if with_bearer and with_bearer.status_code == 200
                else False
            ),
        }

        # -------- LIVE B only --------
        before = transport.attempts
        post = client.post(
            f"/api/v1/assistant/conversations/{conv_id}/messages",
            headers=headers,
            json={
                "content": QUESTION,
                "client_message_id": f"e2e332-B-{uuid.uuid4().hex[:8]}",
            },
        )
        after = transport.attempts
        live: dict[str, Any] = {
            "post_status": post.status_code,
            "model_http_delta": after - before,
            "model_http_total": after,
            "model_http_hosts": list(transport.hosts),
            "model_http_paths": list(transport.paths),
            "model_http_statuses": list(transport.statuses),
            "usage_items": list(last_usage["items"]),
            "safe_diagnostics": list(last_diag["items"]),
            "retry_count": max(0, after - before - 1),
            "captured_provider_context": captured_contexts[-1]
            if captured_contexts
            else None,
            "question": QUESTION,
        }

        if post.status_code != 200:
            err = None
            if post.headers.get("content-type", "").startswith("application/json"):
                err = post.json().get("error")
            live["error_code"] = (err or {}).get("code")
            live["error_message"] = (err or {}).get("message")
            # Safe details only (already filtered codes from provider)
            details = (err or {}).get("details") or []
            live["error_details_safe"] = []
            for d in details:
                if not isinstance(d, dict):
                    continue
                live["error_details_safe"].append(
                    {
                        k: d.get(k)
                        for k in (
                            "reason",
                            "http_status",
                            "request_id",
                            "choices_count",
                            "finish_reason",
                            "content_type",
                            "content_length",
                            "has_refusal",
                            "has_tool_calls",
                            "has_reasoning_content",
                            "error_code",
                            "usage",
                        )
                        if d.get(k) is not None
                    }
                )
            report["live_b"] = live
            report["verdicts_332"] = {
                "prep": "PASS",
                "technical_b": "FAIL",
                "content_b": "FAIL",
                "note": "B failed again; stopped. Original 3.3 FAIL preserved.",
            }
        else:
            payload = post.json()
            asst = payload.get("assistant_message") or {}
            content = asst.get("content") or ""
            blocks = asst.get("blocks") or []
            bank_blocks = [b for b in blocks if b.get("type") == "bank_evidence_list"]
            case_refs = [b for b in blocks if b.get("type") == "case_context_ref"]
            used = []
            diagnostics = {}
            if bank_blocks:
                data = bank_blocks[0].get("data") or {}
                used = data.get("used") or []
                diagnostics = data.get("diagnostics") or {}
            live["content_len"] = len(content)
            live["B_full_content"] = content
            live["content_sample"] = content[:500]
            live["used_count"] = len(used)
            live["diagnostics"] = {
                "retrieved_count": diagnostics.get("retrieved_count"),
                "passed_to_provider_ids": diagnostics.get("passed_to_provider_ids"),
                "cited_by_model": diagnostics.get("cited_by_model"),
                "validated_ids": diagnostics.get("validated_ids"),
                "rejected": diagnostics.get("rejected"),
            }
            passed_set = set(diagnostics.get("passed_to_provider_ids") or [])
            validated_ids = set(diagnostics.get("validated_ids") or [])
            used_ids = {str(u.get("fragment_id")) for u in used if isinstance(u, dict)}
            live["used_subset_of_passed"] = (
                used_ids.issubset(passed_set) if passed_set else False
            )
            live["used_eq_validated"] = used_ids == validated_ids
            live["all_used_rev_pinned"] = all(
                isinstance(u, dict) and u.get("revision") is not None for u in used
            )
            quote_checks = []
            with SessionLocal() as session:
                for u in used:
                    if not isinstance(u, dict) or u.get("text_kind") != "exact_quote":
                        continue
                    frag = session.get(BankFragment, u.get("fragment_id"))
                    if frag is None:
                        quote_checks.append({"ok": False, "reason": "missing"})
                        continue
                    ok = (u.get("text") or "").strip() == (
                        frag.verified_transcript or ""
                    ).strip()
                    quote_checks.append({"ok": ok, "revision": frag.revision})
            live["exact_quote_ok"] = (
                all(c.get("ok") for c in quote_checks) if quote_checks else True
            )
            live["exact_quote_checks"] = quote_checks
            if case_refs:
                cref = case_refs[0].get("data") or {}
                live["case_context_ref"] = {
                    "status": cref.get("status"),
                    "snapshot_id": cref.get("snapshot_id"),
                    "source_file": cref.get("source_file"),
                }
            else:
                live["case_context_ref"] = None

            hist = client.get(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                headers=headers,
            )
            live["history_http"] = hist.status_code
            live["history_message_count"] = (
                len(hist.json()) if hist.status_code == 200 else 0
            )

            with SessionLocal() as session:
                live["impact_rows_after"] = session.query(EventImpact).count()
                live["scenario_count"] = session.query(Scenario).count()
                live["decision_count"] = session.query(Decision).count()
                live["assistant_msgs_in_conv"] = (
                    session.query(AssistantMessage)
                    .filter(
                        AssistantMessage.conversation_id == conv_id,
                        AssistantMessage.role == "assistant",
                    )
                    .count()
                )

            tech_ok = bool(
                live["post_status"] == 200
                and live.get("case_context_ref")
                and live["case_context_ref"].get("snapshot_id") == snap_id
                and live.get("used_subset_of_passed")
                and live.get("all_used_rev_pinned")
                and live.get("exact_quote_ok")
                and live.get("history_http") == 200
                and live.get("history_message_count", 0) >= 3
                and live.get("impact_rows_after") == 0
                and live.get("scenario_count") == 0
                and live.get("decision_count") == 0
                and 1 <= live["model_http_total"] <= MODEL_HTTP_BUDGET
                and all("changellenge" in h for h in live["model_http_hosts"] if h)
                and not any("openai.com" in h for h in live["model_http_hosts"])
                and report["prep"]["links"].get("sha_ok")
            )
            live["technical_pass"] = tech_ok
            report["live_b"] = live

            rev_b = _review_b(content)
            # A markers from saved text (reuse, do not call model)
            a_low = a_content.lower()
            a_loan = any(m in a_low for m in ("loa=true", "кредит", "плавающ", "пересмотр"))
            a_dep = any(m in a_low for m in ("депозит", "вклад", "dep=true"))
            report["content_compare"] = {
                "A_reused_from_33": True,
                "A_loan_attention": a_loan,
                "A_deposit_attention": a_dep,
                "B_review": rev_b,
                "answers_identical": a_content.strip() == content.strip(),
                "contrast_loan_vs_deposit": a_loan
                and rev_b["deposit_product_attended"]
                and a_content.strip() != content.strip(),
                "differences_basis": {
                    "A_product_signal": "LOA=true → кредитный портфель / плавающая ставка / объём долга (из 3.3)",
                    "B_product_signal": "DEP=true → депозит/вклад/ликвидность/пролонгация (этот прогон)",
                    "note": "Различие формулировок само по себе не персонализация; смотрим product-linked checks.",
                },
            }
            content_ok = bool(
                rev_b["deposit_product_attended"]
                and rev_b["check_questions_present"]
                and rev_b["no_overclaim_loa_false_as_no_debts"]
                and rev_b["no_rate_hike_misread"]
                and rev_b["fact_forecast_separated_heuristic"]
                and rev_b["no_invented_money_effect"]
            )
            report["verdicts_332"] = {
                "prep": "PASS",
                "technical_b": "PASS" if tech_ok else "FAIL",
                "content_b": "PASS" if content_ok else "FAIL",
                "headline": (
                    "Повтор B после 3.3.1 прошёл"
                    if tech_ok and content_ok
                    else "Повтор B после 3.3.1 не прошёл"
                ),
                "note": (
                    "Один успешный повтор не доказывает стабильность модели. "
                    "Прежний FAIL этапа 3.3 сохранён."
                ),
            }

    except ModelHttpBudgetExceeded as exc:
        report["live_b"]["budget_stop"] = True
        report["live_b"]["budget_error"] = str(exc)
        report["live_b"]["model_http_total"] = transport.attempts
        report["live_b"]["safe_diagnostics"] = list(last_diag["items"])
        report["verdicts_332"] = {
            "prep": "PASS" if report.get("prep", {}).get("pass") else "FAIL",
            "technical_b": "FAIL",
            "content_b": "FAIL",
            "headline": "Повтор B после 3.3.1 не прошёл",
            "note": "Stopped by model HTTP budget (max 2)",
        }
    except Exception as exc:  # noqa: BLE001
        report["exception"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
        report.setdefault(
            "verdicts_332",
            {
                "prep": "FAIL",
                "technical_b": "FAIL",
                "content_b": "FAIL",
                "headline": "Повтор B после 3.3.1 не прошёл",
            },
        )
    finally:
        client.close()
        app.dependency_overrides.clear()
        hackathon_mod.HackathonProvider.__init__ = _orig_init  # type: ignore[method-assign]
        hackathon_mod.HackathonProvider.generate = _orig_generate  # type: ignore[method-assign]
        engine.dispose()
        get_settings.cache_clear()
        _clear_process_overrides()
        get_settings.cache_clear()

    RECHECK_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {
        "stage": "3.3.2",
        "recheck_db": report["recheck_db"],
        "prep_pass": report.get("prep", {}).get("pass"),
        "verdicts_332": report.get("verdicts_332"),
        "model_http": report.get("live_b", {}).get("model_http_total"),
        "report": str(RECHECK_REPORT.relative_to(ROOT)).replace("\\", "/"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
