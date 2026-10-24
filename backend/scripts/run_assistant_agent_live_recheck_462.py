"""Stage 4.6.2 — live recheck after context fix (4.6.1), isolated SQLite stand.

- NEW test DB under e2e462 (does NOT overwrite e2e46 / its stopped result)
- Same model, question, synthetic seed shape, and TurnBudget defaults as 4.6
- TestClient + Session override (not :8003 / not root kontur.db)
- ASSISTANT_AGENT_LOOP=true + hackathon only for this process
- Max 4 model HTTP / 3 tools / 1 repair; one live turn only
- Never prints API keys / Authorization / full prompts / reasoning_content
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, event as sa_event, func, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SRC_QA_DB = (
    ROOT
    / "data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db"
)
E2E46_DIR = ROOT / "data/bank_materials/verification/e2e46"
E2E_DIR = ROOT / "data/bank_materials/verification/e2e462"
E2E_DB = E2E_DIR / "assistant_agent_live_recheck.db"
E2E_STORAGE = E2E_DIR / "storage"
RAW_PDF = ROOT / "data/bank_materials/raw/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"
EXPECTED_PDF_SHA = "92a96805f2b720f76bd0c52d2491044812b38401ab62d0f4a9157b4ca81c49bb"
OCR_RUN_ID = "7d64e39e-0ff5-450c-8a01-c44f678da871"
STORAGE_KEY = "bank_import_stage_5v66axai/pdf/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"
REPORT_JSON = E2E_DIR / "e2e462_report.json"
REPORT_MD = ROOT / "docs/ASSISTANT_AGENT_LIVE_RECHECK.md"
# Preserve original 4.6 artefacts (read-only reference in report).
E2E46_REPORT = E2E46_DIR / "e2e46_report.json"

MODEL_HTTP_BUDGET = 4
SLOT = "competition_default"
CATALOG_FILE = "df_Uid_data_hack.csv"
USER_PASSWORD = "E2eAgent462!"
SYNTHETIC_EVENT_ID = "evt_synth_e2e462_policy_rate"
PRODUCT_CODES = ("RKO", "GAR", "LOA", "LEA", "DEP", "ZPP")

# Exact same user question as stage 4.6 — do not tune for the model.
QUESTION = (
    "Разбери эту новость для нашей компании. Сначала проверь факты "
    "события, данные компании и подходящие материалы банка. "
    "Отдели факт от прогноза, объясни, что стоит проверить. "
    "Не рассчитывай денежный эффект без исходных параметров. "
    "Укажи использованные банковские источники"
)

CLIENT_MSG_ID = f"e2e462-live-{uuid.uuid4().hex[:10]}"


class ModelHttpBudgetExceeded(RuntimeError):
    pass


class RecordingTransport(httpx.HTTPTransport):
    """Real HTTPS + hard budget; records safe step summaries (no secrets/prompts)."""

    def __init__(self, *, budget: int) -> None:
        super().__init__()
        self.budget = budget
        self.attempts = 0
        self.steps: list[dict[str, Any]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        path = request.url.path or ""
        is_model = "changellenge" in host and path.endswith("/chat/completions")
        if is_model:
            self.attempts += 1
            if self.attempts > self.budget:
                raise ModelHttpBudgetExceeded(
                    f"model HTTP budget exceeded ({self.attempts}>{self.budget})"
                )
            step = _summarize_request(self.attempts, request)
            resp = super().handle_request(request)
            # Buffer decompressed body once. Rebuild without Content-Encoding so the
            # provider can read JSON without a second decode pass (DecodingError).
            try:
                raw = bytes(resp.content or b"")
            except Exception:  # noqa: BLE001
                raw = resp.read() if hasattr(resp, "read") else b""
            hdrs = {
                k: v
                for k, v in resp.headers.items()
                if k.lower() not in {"content-encoding", "content-length"}
            }
            buffered = httpx.Response(
                status_code=resp.status_code,
                headers=hdrs,
                content=raw,
                request=request,
                extensions=dict(resp.extensions or {}),
            )
            step.update(_summarize_response(buffered))
            self.steps.append(step)
            return buffered
        return super().handle_request(request)

    def merge_provider_diagnostics(self, diagnostics: dict[str, Any] | None) -> None:
        """Prefer adapter-parsed safe diagnostics over re-parsing raw body."""
        if not diagnostics or not self.steps:
            return
        last = self.steps[-1]
        if diagnostics.get("usage") and not last.get("usage"):
            last["usage"] = diagnostics["usage"]
        if diagnostics.get("finish_reason") and not last.get("finish_reason"):
            last["finish_reason"] = diagnostics["finish_reason"]
        if diagnostics.get("action_kind") and (
            last.get("action_kind") in {None, "unparsed"} or last.get("parse") == "non_json"
        ):
            last["action_kind"] = diagnostics["action_kind"]
            last.pop("parse", None)
        if diagnostics.get("tool_name") and not last.get("tool_name"):
            last["tool_name"] = diagnostics["tool_name"]
        if diagnostics.get("content_length") is not None and "content_chars" not in last:
            last["content_chars"] = diagnostics["content_length"]


def _uid() -> str:
    return str(uuid.uuid4())


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
    if hashlib.sha256(target.read_bytes()).hexdigest() != EXPECTED_PDF_SHA:
        raise RuntimeError("copied PDF SHA mismatch")
    return E2E_STORAGE


def _clear_process_overrides() -> None:
    for key in (
        "ASSISTANT_PROVIDER",
        "ASSISTANT_AGENT_LOOP",
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


def _extract_data_json(user_content: str) -> dict[str, Any] | None:
    marker = "BEGIN_UNTRUSTED_APPLICATION_DATA"
    end = "END_UNTRUSTED_APPLICATION_DATA"
    i0 = user_content.find(marker)
    i1 = user_content.find(end)
    if i0 < 0 or i1 <= i0:
        return None
    blob = user_content[i0 + len(marker) : i1]
    start = blob.find("{")
    if start < 0:
        return None
    try:
        return json.loads(blob[start:])
    except json.JSONDecodeError:
        return None


def _obs_summary(observations: list[Any]) -> dict[str, Any]:
    tools: list[str] = []
    statuses: list[str] = []
    source_refs = 0
    fragment_ids: list[str] = []
    text_markers: list[str] = []
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        name = obs.get("name") or obs.get("tool") or (obs.get("data") or {}).get("tool")
        if isinstance(name, str):
            tools.append(name)
        st = obs.get("status") or (obs.get("data") or {}).get("status")
        if isinstance(st, str):
            statuses.append(st)
        data = obs.get("data") if isinstance(obs.get("data"), dict) else {}
        for ref in data.get("source_refs") or obs.get("source_refs") or []:
            if isinstance(ref, dict):
                source_refs += 1
        for f in data.get("fragments") or []:
            if isinstance(f, dict) and f.get("fragment_id"):
                fragment_ids.append(str(f["fragment_id"])[:12])
            plain = ""
            if isinstance(f, dict):
                plain = str(f.get("text_plain") or f.get("text") or "")
            if "14" in plain:
                text_markers.append("has_14")
            if "прогноз" in plain.lower() or "ожид" in plain.lower():
                text_markers.append("has_forecast_lex")
            if "ставк" in plain.lower():
                text_markers.append("has_rate_lex")
    return {
        "observation_count": len(observations),
        "tools_in_observations": tools,
        "statuses": statuses,
        "source_refs_count": source_refs,
        "fragment_id_prefixes": fragment_ids[:8],
        "text_markers": sorted(set(text_markers)),
    }


def _summarize_request(n: int, request: httpx.Request) -> dict[str, Any]:
    # Never log Authorization
    body: dict[str, Any] = {}
    try:
        raw = request.content.decode("utf-8") if request.content else "{}"
        body = json.loads(raw)
    except Exception:  # noqa: BLE001
        body = {}
    messages = body.get("messages") if isinstance(body.get("messages"), list) else []
    user_content = ""
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user":
            user_content = str(m.get("content") or "")
    data = _extract_data_json(user_content) or {}
    obs = data.get("observations") if isinstance(data.get("observations"), list) else []
    hist = data.get("conversation_history") if isinstance(data.get("conversation_history"), list) else []
    uq = str(data.get("user_question") or "")
    # Prove current question present without dumping full prompt
    q_present = "Разбери эту новость" in uq or "новост" in uq.lower()
    # Prepared DATA size (serialized) — not the full HTTP envelope / system prompt.
    data_chars = 0
    if data:
        try:
            data_chars = len(
                json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
        except Exception:  # noqa: BLE001
            data_chars = len(user_content)
    budget_meta = data.get("budget") if isinstance(data.get("budget"), dict) else {}
    summary = {
        "model_http": n,
        "host": request.url.host,
        "path": request.url.path,
        "has_authorization_header": "authorization" in {k.lower() for k in request.headers.keys()},
        "user_question_present": q_present,
        "history_len": len(hist),
        "history_incomplete": bool(data.get("history_incomplete")),
        "final_only": bool(data.get("final_only") or budget_meta.get("final_only")),
        "repair_kind": data.get("repair_kind"),
        "context_incomplete": bool(data.get("context_incomplete")),
        "prepared_data_chars": data_chars,
        "user_content_chars": len(user_content),
        **_obs_summary(obs),
        # Preload guard: full assessment/case dumps must not appear on step 1
        "payload_keys": sorted(data.keys()) if data else [],
        "mentions_full_case_dump": "org_catalog_rows" in user_content.lower()
        or "full_profile" in user_content.lower(),
        "mentions_impact_score_block": '"impact_score"' in user_content
        and "get_available_assessment" not in json.dumps(obs, ensure_ascii=False),
    }
    return summary


def _summarize_response(resp: httpx.Response) -> dict[str, Any]:
    out: dict[str, Any] = {"http_status": resp.status_code}
    body: Any = None
    try:
        body = json.loads(resp.content.decode("utf-8"))
    except Exception:  # noqa: BLE001
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            out["parse"] = "non_json"
            out["content_bytes"] = len(resp.content or b"")
            return out
    usage = body.get("usage") if isinstance(body, dict) else None
    if isinstance(usage, dict):
        out["usage"] = {
            k: usage.get(k)
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            if k in usage
        }
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices:
        out["action_kind"] = None
        return out
    ch0 = choices[0] if isinstance(choices[0], dict) else {}
    out["finish_reason"] = ch0.get("finish_reason")
    msg = ch0.get("message") if isinstance(ch0.get("message"), dict) else {}
    # Never store reasoning_content
    content = str(msg.get("content") or "")
    out["content_chars"] = len(content)
    kind = None
    tool_name = None
    try:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            kind = parsed.get("kind")
            action = parsed.get("action") if isinstance(parsed.get("action"), dict) else {}
            tool_name = action.get("name")
    except Exception:  # noqa: BLE001
        kind = "unparsed"
    out["action_kind"] = kind
    out["tool_name"] = tool_name
    return out


def _product_marks(*, loa: bool, dep: bool) -> dict[str, bool | None]:
    marks = {c: False for c in PRODUCT_CODES}
    marks["RKO"] = True
    marks["LOA"] = loa
    marks["DEP"] = dep
    return marks


def _seed_ready_snapshot(session: Session, *, slot: str, label: str, seq: int):
    from app.models import CaseImportFile, CaseImportRun, CaseSnapshot

    snap_id, run_id = _uid(), _uid()
    snap = CaseSnapshot(
        id=snap_id,
        slot_key=slot,
        version_label=label,
        version_seq=seq,
        status="building",
        import_run_id=None,
    )
    session.add(snap)
    session.flush()
    run = CaseImportRun(
        id=run_id,
        snapshot_id=snap_id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    snap.import_run_id = run_id
    for name in (CATALOG_FILE, "payments.csv", "links.csv"):
        session.add(
            CaseImportFile(
                id=_uid(),
                import_run_id=run_id,
                source_file=name,
                content_sha256="b" * 64,
                byte_size=10,
                row_count_loaded=0,
                status="completed",
            )
        )
    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    snap.status = "ready"
    snap.built_at = datetime.now(timezone.utc)
    snap.validation_report_json = {
        "ready_at": datetime.now(timezone.utc).isoformat(),
        "final_checks": {
            "companies": {"catalog_rows": 0},
            "payments": {"rows": 0},
            "person_links": {"rows": 0},
        },
        "manifest": [
            {"role": "companies", "source_file": CATALOG_FILE, "record_count": 0},
            {"role": "payments", "source_file": "payments.csv", "record_count": 0},
            {"role": "person_links", "source_file": "links.csv", "record_count": 0},
        ],
        "synthetic_e2e": "4.6.2",
    }
    session.flush()
    return snap


def _add_profiled_org(session: Session, snap, *, external_uid: str, product_marks: dict):
    """Reuse 3.3 catalog/product seeding shape (no CSV import)."""
    from app.models import (
        CaseOrg,
        CaseOrgCatalogRow,
        CaseOrgFieldResolution,
        CaseOrgGroup,
        CaseOrgGroupMember,
        CaseOrgProductMark,
    )
    from app.services.case_data.resolution import resolve_catalog_variants

    assert snap.import_run_id
    org = CaseOrg(
        id=_uid(),
        snapshot_id=snap.id,
        external_uid=external_uid,
        has_catalog_profile=True,
        profile_resolution="single",
    )
    session.add(org)
    session.flush()
    defaults = {
        "org_type": "ООО",
        "okfs_name": None,
        "company_age_years_gradation": "5-10",
        "eco_mark_label": None,
        "mainokved_code": "25.11",
        "mainokved_name": "Производство металлоконструкций",
        "negative_mark": False,
        "workers_fns_gradation": "15-100",
        "workers_spark_gradation": None,
        "cl_type": None,
        "fts_flag": True,
        "fts_country_name_raw": "Китай",
        "factoring_mark": False,
        "revenue_raw": "1000.0",
        "group_external_id": "G_E2E462",
        "city": "Москва",
        "region": "Москва",
    }
    marks_data = [product_marks]
    rows_data = [defaults]
    max_row = (
        session.scalar(
            select(func.max(CaseOrgCatalogRow.source_row_number)).where(
                CaseOrgCatalogRow.import_run_id == snap.import_run_id,
                CaseOrgCatalogRow.source_file == CATALOG_FILE,
            )
        )
        or 0
    )
    cid = _uid()
    session.add(
        CaseOrgCatalogRow(
            id=cid,
            snapshot_id=snap.id,
            import_run_id=snap.import_run_id,
            case_org_id=org.id,
            source_file=CATALOG_FILE,
            source_row_number=max_row + 1,
            row_content_sha256=f"{external_uid.encode().hex():0<64}"[:64],
            org_type=defaults["org_type"],
            okfs_name=None,
            company_age_years_gradation=defaults["company_age_years_gradation"],
            eco_mark_label=None,
            mainokved_code=defaults["mainokved_code"],
            mainokved_name=defaults["mainokved_name"],
            negative_mark=False,
            workers_fns_gradation=defaults["workers_fns_gradation"],
            workers_spark_gradation=None,
            cl_type=None,
            fts_flag=True,
            fts_country_name_raw=defaults["fts_country_name_raw"],
            factoring_mark=False,
            revenue_raw=defaults["revenue_raw"],
            revenue_amount=None,
            revenue_parse_status="ok",
            revenue_parse_error=None,
            revenue_unit=None,
            revenue_currency=None,
            group_external_id=defaults["group_external_id"],
            city=defaults["city"],
            region=defaults["region"],
            raw_json={"synthetic_e2e": "4.6"},
        )
    )
    session.flush()
    for code, mark in product_marks.items():
        session.add(
            CaseOrgProductMark(
                id=_uid(),
                snapshot_id=snap.id,
                catalog_row_id=cid,
                product_code=code,
                mark=mark,
            )
        )
    resolved = resolve_catalog_variants(rows_data, product_marks_by_row=marks_data)
    org.profile_resolution = resolved["profile_resolution"]
    session.add(
        CaseOrgFieldResolution(
            id=_uid(),
            snapshot_id=snap.id,
            case_org_id=org.id,
            import_run_id=snap.import_run_id,
            consensus_json=resolved["consensus_json"],
            conflict_json=resolved["conflict_json"],
            absent_json=resolved["absent_json"],
            variant_count=resolved["variant_count"],
            confirmed_field_count=resolved["confirmed_field_count"],
        )
    )
    gid = resolved["consensus_json"].get("group_external_id")
    if gid and "group_external_id" not in resolved["conflict_json"]:
        group = session.scalars(
            select(CaseOrgGroup).where(
                CaseOrgGroup.snapshot_id == snap.id,
                CaseOrgGroup.external_group_id == str(gid),
            )
        ).first()
        if group is None:
            group = CaseOrgGroup(
                id=_uid(), snapshot_id=snap.id, external_group_id=str(gid)
            )
            session.add(group)
            session.flush()
        session.add(
            CaseOrgGroupMember(
                id=_uid(),
                snapshot_id=snap.id,
                group_id=group.id,
                case_org_id=org.id,
                catalog_row_id=cid,
                is_conflicted_membership=False,
            )
        )
    session.flush()
    return org


def _user_company(session: Session, *, name: str, email_prefix: str):
    from app.core.security import hash_password
    from app.models import Company, CompanyMembership, User

    user = User(
        id=_uid(),
        email=f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password(USER_PASSWORD),
        display_name="E2E46",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    company = Company(
        id=_uid(),
        name=name,
        industry="manufacturing",
        size_band="medium",
        hq_region="Москва",
        profile_status="ready",
        digital_twin_status="built",
        digital_twin_coverage=0.5,
        is_demo=False,
        created_by=user.id,
    )
    session.add(company)
    session.flush()
    session.add(
        CompanyMembership(
            id=_uid(), user_id=user.id, company_id=company.id, role="owner"
        )
    )
    session.flush()
    return user, company


def _seed_event(session: Session):
    from app.models import Event, EventSource

    occurred = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    event = Event(
        id=SYNTHETIC_EVENT_ID,
        title="[СИНТЕТИЧЕСКИЙ ТЕСТ 4.6.2] Сохранение ключевой ставки ЦБ",
        summary=(
            "Синтетическая тестовая новость для live agent loop recheck. "
            "Не является реальной публикацией СМИ. Тема: Банк России сохранил ключевую "
            "ставку без изменений. Дата события после публикации материала банка Policy Rate."
        ),
        category="macro",
        event_type="risk",
        severity=55.0,
        urgency_default="watch",
        status="active",
        occurred_at=occurred,
        effective_from=occurred,
        match_countries_json=["Россия"],
        match_currencies_json=["RUB"],
        match_materials_json=[],
        match_categories_json=["macro", "rates"],
        attributes_json={
            "synthetic_test": "4.6.2",
            "not_real_publication": True,
            "no_event_impact": True,
        },
        is_demo=False,
    )
    session.add(event)
    session.flush()
    session.add(
        EventSource(
            id=_uid(),
            event_id=event.id,
            publisher="Синтетический стенд 4.6.2",
            url=None,
            published_at=occurred,
            is_stub=True,
            excerpt="ЦБ сохранил ключевую ставку (синтетический stub).",
            source_quality=0.7,
        )
    )
    session.flush()
    return event


def _content_review(content: str) -> dict[str, Any]:
    low = content.lower()
    invented = any(
        x in low
        for x in (
            "расходы выросли на",
            "потери составят",
            "компания потеряет",
            "% от выручки",
            "млн ₽ эффекта",
            "вероятность дефолта",
        )
    )
    treats_safe = any(
        x in low
        for x in (
            "событие безопасно",
            "риска нет потому что нет расчёта",
            "нет влияния потому что нет impact",
        )
    )
    bank_as_news = any(
        x in low
        for x in (
            "банк прокомментировал именно эту новость",
            "официальный комментарий банка к этой новости",
        )
    )
    fact_forecast = (("факт" in low) or ("сохран" in low) or ("14" in content)) and (
        ("прогноз" in low) or ("ожид" in low) or ("интерпретац" in low) or ("материал" in low)
    )
    profile = any(
        x in low
        for x in ("производств", "manufactur", "кредит", "loa", "москв", "компани")
    )
    check = any(
        x in low for x in ("проверить", "уточнить", "стоит", "нельзя рассчитать", "недостаточно")
    )
    return {
        "fact_forecast_separated_heuristic": fact_forecast,
        "profile_signals_mentioned": profile,
        "check_questions_present": check,
        "no_invented_money_or_probs": not invented,
        "no_missing_impact_as_safe": not treats_safe,
        "bank_not_claimed_as_news_comment": not bank_as_news,
        "sample": (content.strip().replace("\n", " ")[:500] + ("…" if len(content) > 500 else "")),
    }


def _write_md(report: dict[str, Any]) -> None:
    """Write human report; content is refined after scoring in main when needed."""
    scores = report.get("scores") or {}
    seq = report.get("sequence") or []
    live = report.get("live") or {}
    success = bool(report.get("ok")) and live.get("outcome") == "final"
    headline = (
        "Повтор после исправления 4.6.1 прошёл."
        if success
        else "Повтор после исправления 4.6.1 не завершился успешно (один live turn)."
    )
    lines = [
        "# Agent loop — live recheck (Этап 4.6.2)",
        "",
        f"Дата: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        f"**{headline}**",
        "",
        "Один live-прогон на **новой** изолированной БД после фикса контекста (4.6.1).",
        "Исходный этап 4.6 остаётся **stopped** (`docs/ASSISTANT_AGENT_LIVE_E2E.md`, `e2e46_report.json`).",
        "Root `.env` / рабочая БД / backend `:8003` **не** менялись. Флаг loop в root `.env` не включался.",
        "",
        "**Один успешный прогон не доказывает стабильность.**",
        "",
        "## Стенд",
        "",
        f"- Тестовая БД: `{report.get('test_db_path')}` (новая копия; e2e46 не перезаписывалась)",
        f"- Источник QA: `{report.get('source_qa_db')}`",
        f"- Storage: `{report.get('storage_root')}`",
        f"- Модель: `{((report.get('runtime_config') or {}).get('model'))}`",
        f"- Синтетика: {', '.join(report.get('synthetic_parts') or [])}",
        f"- EventImpact: отсутствует по дизайну (`no_event_impact_by_design={report.get('no_event_impact_by_design')}`)",
        f"- Вопрос: тот же, что в 4.6 (без подстройки под модель)",
        "",
        "## Лимиты",
        "",
        f"- model HTTP ≤ {MODEL_HTTP_BUDGET}; tool calls ≤ 3; repairs ≤ 1; timeout_s=90",
        f"- Фактически transport HTTP: `{live.get('model_http_used')}`; "
        f"reserved=`{live.get('model_http_reserved')}`; "
        f"responses=`{live.get('model_http_responses')}`; "
        f"tools≈{live.get('tool_calls_observed')}; repairs={live.get('repairs_used')}",
        "",
        "## Preflight (без LLM)",
        "",
        f"- ok: `{((report.get('preflight') or {}).get('ok'))}`",
        f"- offline packed payload fits ≤12000: "
        f"`{((report.get('preflight') or {}).get('offline_pack_fits'))}` "
        f"(chars=`{((report.get('preflight') or {}).get('offline_pack_chars'))}`)",
        f"- open conversation spent model HTTP: "
        f"`{((report.get('preflight') or {}).get('open_conversation_spent_model_http'))}`",
        "",
        "## Последовательность model HTTP",
        "",
    ]
    for step in seq:
        lines.append(
            f"- **HTTP #{step.get('model_http')}**: kind=`{step.get('action_kind')}` "
            f"tool=`{step.get('tool_name')}` finish=`{step.get('finish_reason')}` "
            f"final_only=`{step.get('final_only')}` "
            f"prepared_data_chars=`{step.get('prepared_data_chars')}` "
            f"obs_count=`{step.get('observation_count')}` "
            f"obs_tools={step.get('tools_in_observations')} "
            f"source_refs={step.get('source_refs_count')} "
            f"usage={step.get('usage')}"
        )
    lines.extend(
        [
            "",
            "### Обратная связь tool → следующий HTTP",
            "",
            f"- proven: `{live.get('tool_feedback_proven')}`",
            "",
            "## Оценки A–E",
            "",
            f"- **A механика:** {scores.get('A_mechanics')}",
            f"- **B полнота:** {scores.get('B_completeness')} "
            f"(missing={scores.get('B_missing_tools')}; "
            f"early_final={scores.get('early_final_without_tools')})",
            f"- **C источники:** {scores.get('C_sources')}",
            f"- **D содержание:** {scores.get('D_content')}",
            f"- **E история/идемпотентность:** {scores.get('E_idempotency')}",
            "",
            "## Финал / остановка",
            "",
            f"- outcome: `{live.get('outcome')}` status=`{live.get('http_status')}`",
            f"- error: `{live.get('error_code')}`",
            f"- stop_message: `{live.get('stop_message')}`",
            f"- content sample: {((report.get('content_review') or {}).get('sample') or '')[:800]}",
            "",
            "### Примеры содержания (ручная выдержка)",
            "",
            f"- {((report.get('content_review') or {}).get('manual_notes') or '—')}",
            "",
            "## Идемпотентность",
            "",
            f"- replay: `{json.dumps(report.get('idempotency') or {}, ensure_ascii=False)}`",
            "",
            "## Ограничения",
            "",
            "- Один live turn; не доказательство стабильности и не полное соответствие конкурсному ТЗ.",
            "- Ключи / Authorization / reasoning_content / полный prompt в отчёт не включались.",
            "- Второй live turn при неудаче **не** запускался.",
            "",
        ]
    )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    report: dict[str, Any] = {
        "stage": "4.6.2",
        "prior_stage_4_6": {
            "status": "stopped_preserved",
            "report": str(E2E46_REPORT.relative_to(ROOT)).replace("\\", "/")
            if E2E46_REPORT.is_file()
            else None,
            "stand_dir": str(E2E46_DIR.relative_to(ROOT)).replace("\\", "/"),
        },
        "synthetic_parts": [
            "user/company/membership (synthetic)",
            "case snapshot + catalog U_460 + product marks LOA=true DEP=false",
            "event labeled synthetic; occurred_at=2026-09-20; NO EventImpact",
            "Policy Rate bank QA fragments unchanged from QA DB backup",
            "storage layout copy of PDF under test-only root",
            "same user question as stage 4.6",
        ],
        "bank_document_unchanged": True,
        "no_event_impact_by_design": True,
        "preflight": {},
        "live": {},
        "sequence": [],
        "scores": {},
        "limits": {
            "model_http_budget": MODEL_HTTP_BUDGET,
            "max_tool_calls": 3,
            "max_repairs": 1,
            "timeout_s": 90,
            "max_transcript_chars": 12_000,
            "max_result_chars": 4000,
        },
    }

    if not SRC_QA_DB.is_file():
        report["fatal"] = "QA source DB missing"
        E2E_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_md(report)
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
    os.environ["SECRET_KEY"] = __import__("secrets").token_hex(32)
    os.environ["ASSISTANT_PROVIDER"] = "hackathon"
    os.environ["ASSISTANT_AGENT_LOOP"] = "true"
    os.environ["HACKATHON_API_KEY"] = hackathon_key
    os.environ["HACKATHON_BASE_URL"] = "https://changellenge.up.railway.app/v1"
    os.environ["HACKATHON_MODEL"] = "deepseek/deepseek-v4.1-flash"
    os.environ["BANK_MATERIALS_ALLOWED_OCR_RUN_IDS"] = OCR_RUN_ID
    os.environ["BANK_MATERIALS_STORAGE_ROOT"] = str(storage_root.resolve())
    os.environ["CASE_CONTEXT_SLOT_KEY"] = SLOT
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["GIGACHAT_AUTH_KEY"] = ""

    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    report["runtime_config"] = {
        "provider": settings.normalized_assistant_provider(),
        "agent_loop": bool(settings.assistant_agent_loop),
        "model": settings.resolved_hackathon_model(),
        "base_url": settings.resolved_hackathon_base_url(),
        "key_configured": bool(settings.resolved_hackathon_api_key()),
        "ocr_run_scoped": OCR_RUN_ID in settings.bank_materials_allowed_ocr_run_id_set(),
        "case_slot": settings.case_context_slot_key,
        "connected_to_e2e_db": E2E_DB.name in settings.database_url.replace("\\", "/"),
        "budget": {
            "max_model_http": settings.assistant_loop_max_model_http,
            "max_tool_calls": settings.assistant_loop_max_tool_calls,
            "max_repairs": settings.assistant_loop_max_repairs,
            "timeout_s": settings.assistant_loop_timeout_s,
        },
    }
    if (
        settings.normalized_assistant_provider() != "hackathon"
        or not settings.assistant_agent_loop
        or not report["runtime_config"]["connected_to_e2e_db"]
    ):
        report["fatal"] = "runtime not on isolated loop+hackathon+e2e db"
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_md(report)
        print(json.dumps({"ok": False, "fatal": report["fatal"]}, ensure_ascii=False))
        return 2

    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _) -> None:  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        snap = _seed_ready_snapshot(session, slot=SLOT, label="e2e462-synth-v1", seq=1)
        _add_profiled_org(
            session, snap, external_uid="U_460", product_marks=_product_marks(loa=True, dep=False)
        )
        from app.models import CaseImportFile as _CaseImportFile

        cat_file = session.scalars(
            select(_CaseImportFile).where(
                _CaseImportFile.import_run_id == snap.import_run_id,
                _CaseImportFile.source_file == CATALOG_FILE,
            )
        ).one()
        cat_file.row_count_loaded = 1
        snap.validation_report_json = {
            **(snap.validation_report_json or {}),
            "final_checks": {
                "companies": {"catalog_rows": 1},
                "payments": {"rows": 0},
                "person_links": {"rows": 0},
            },
            "manifest": [
                {"role": "companies", "source_file": CATALOG_FILE, "record_count": 1},
                {"role": "payments", "source_file": "payments.csv", "record_count": 0},
                {"role": "person_links", "source_file": "links.csv", "record_count": 0},
            ],
        }
        user, company = _user_company(
            session, name="Синтетика Агент Loop 4.6.2", email_prefix="e2e462"
        )
        event = _seed_event(session)
        session.commit()
        seed = {
            "snap_id": snap.id,
            "event_id": event.id,
            "user_id": user.id,
            "email": user.email,
            "company_id": company.id,
            "company_name": company.name,
        }

    from app.services.case_data.activate_snapshot import run_activation
    from app.services.case_data.link_org_company import run_link

    act = run_activation(
        database_url=db_url,
        slot_key=SLOT,
        snapshot_id=seed["snap_id"],
        expect_no_active=True,
    )
    run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_460",
        company_id=seed["company_id"],
        linked_by="e2e462",
    )
    report["seed"] = {
        "activation": getattr(act, "outcome", str(act)),
        "snap_id": seed["snap_id"],
        "event_id": seed["event_id"],
        "company_id": seed["company_id"],
        "uid": "U_460",
        "email_domain": "example.com",
    }

    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import create_app
    from app.models import Decision, EventImpact, Scenario, User
    from app.models.assistant import AssistantConversation, AssistantMessage
    from app.models.bank_materials import BankFragment
    from app.services.assistant.agent_loop.api_integration import set_loop_http_client_for_tests
    from app.services.assistant.agent_loop.provider_iface import ScriptedLoopProvider
    from app.services.assistant.agent_loop.runner import AgentLoopRunner
    from app.services.assistant.agent_loop.scope import ServerScope
    from app.services.assistant.agent_loop.sources import SourceLedger
    from app.services.assistant.agent_loop.budget import TurnBudget
    from app.services.bank_materials.event_evidence import collect_event_bank_evidence

    def _override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    transport = RecordingTransport(budget=MODEL_HTTP_BUDGET)
    loop_client = httpx.Client(transport=transport, timeout=90.0)
    set_loop_http_client_for_tests(loop_client)

    client = TestClient(app)
    try:
        # ---------- Preflight (no paid model HTTP) ----------
        pf: dict[str, Any] = {"model_http_before": transport.attempts}
        login = client.post(
            "/api/v1/auth/login",
            json={"email": seed["email"], "password": USER_PASSWORD},
        )
        pf["login_status"] = login.status_code
        if login.status_code != 200:
            raise RuntimeError("login failed")
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/v1/auth/me", headers=headers)
        pf["me_status"] = me.status_code

        with SessionLocal() as session:
            impact_n = session.scalar(
                select(func.count())
                .select_from(EventImpact)
                .where(
                    EventImpact.event_id == seed["event_id"],
                    EventImpact.company_id == seed["company_id"],
                )
            )
            pf["event_impact_count"] = int(impact_n or 0)
            user_row = session.get(User, seed["user_id"])
            assert user_row is not None

            # Wrappers / eligibility without LLM
            from app.services.assistant.agent_loop.loop_tools import (
                TurnToolCache,
                execute_loop_tool,
            )
            from app.services.assistant.agent_loop.scope import resolve_server_scope

            scope = ServerScope(
                user_id=seed["user_id"],
                company_id=seed["company_id"],
                event_id=seed["event_id"],
                conversation_id="preflight",
            )
            resolved = resolve_server_scope(session, scope)
            cache = TurnToolCache()

            def _run_tool(name: str, step: int):
                return execute_loop_tool(
                    session,
                    resolved=resolved,
                    name=name,
                    step=step,
                    max_result_chars=4000,
                    cache=cache,
                )

            ev = _run_tool("get_event_context", 1)
            cs = _run_tool("get_company_case_context", 2)
            bk = _run_tool("get_bank_evidence", 3)
            asmt = _run_tool("get_available_assessment", 4)
            pf["wrappers"] = {
                "event_status": ev.envelope.status,
                "case_status": cs.envelope.status,
                "bank_status": bk.envelope.status,
                "assessment_status": asmt.envelope.status,
            }
            bank_data = bk.envelope.data if isinstance(bk.envelope.data, dict) else {}
            frags = list(
                bk.dispatch_bank or bk.obtained_bank or bank_data.get("fragments") or []
            )
            pf["bank_tool_fragment_count"] = len(frags)
            pf["bank_tool_status"] = bk.envelope.status
            from app.models import Event as _Event

            ev_row = session.get(_Event, seed["event_id"])
            assert ev_row is not None
            collected = collect_event_bank_evidence(session, event=ev_row)
            pf["collector_status"] = collected.status
            pf["collector_evidence_count"] = len(collected.evidence or [])
            pf["collector_ok"] = collected.status == "available" and len(collected.evidence or []) > 0
            ctypes = {
                str(e.content_type)
                for e in (collected.evidence or [])
                if e.content_type
            }
            pf["has_fact"] = "fact" in ctypes
            pf["has_forecast"] = "forecast" in ctypes
            # Authorized fragment + PDF href smoke from collector
            sample_ev = (collected.evidence or [None])[0]
            if sample_ev is not None:
                pf["sample_fragment_id"] = sample_ev.fragment_id
                pf["sample_document_href"] = bool(sample_ev.document_href)
                pf["sample_fragment_href"] = bool(sample_ev.fragment_href)
                pf["sample_content_href"] = bool(sample_ev.content_href)

            # Offline first-payload shape (ScriptedLoopProvider — zero network)
            captured: list[dict[str, Any]] = []

            def _capture(req):  # noqa: ANN001
                captured.append(
                    {
                        "keys": sorted((req.payload or {}).keys()),
                        "obs": list((req.payload or {}).get("observations") or []),
                        "has_user_question": bool((req.payload or {}).get("user_question")),
                    }
                )
                return json.dumps(
                    {"kind": "final", "content": "dry", "bank_evidence_citations": []},
                    ensure_ascii=False,
                )

            dry = AgentLoopRunner(
                db=session,
                scope=ServerScope(
                    user_id=seed["user_id"],
                    company_id=seed["company_id"],
                    event_id=seed["event_id"],
                    conversation_id="dry",
                ),
                provider=ScriptedLoopProvider(steps=[_capture]),
                budget=TurnBudget(config=settings.agent_loop_budget_config()),
                ledger=SourceLedger(),
            )
            dry.run(user_question=QUESTION, conversation_history=[])
            pf["first_payload_offline"] = captured[0] if captured else None
            pf["first_payload_observations_empty"] = bool(
                captured and captured[0]["obs"] == []
            )
            pf["first_payload_no_preloaded_bank_frags"] = not any(
                "fragments" in json.dumps(captured[0].get("obs") or []) for _ in [0]
            )

            # Offline: event+bank+case packed payload must fit transcript limit
            # (does not prescribe live tool order to the real model).
            from app.services.assistant.agent_loop.context_pack import prepare_turn_payload
            from app.services.assistant.agent_loop.loop_projections import (
                slim_source_refs_for_model,
            )
            from app.services.assistant.agent_loop.budget import (
                DEFAULT_MAX_TRANSCRIPT_CHARS,
            )

            pack_obs: list[dict[str, Any]] = []
            for ex in (ev, bk, cs):
                dump = ex.envelope.model_dump(mode="json")
                dump["role"] = "tool_result_data"
                dump["source_refs"] = slim_source_refs_for_model(
                    dump.get("source_refs") or []
                )
                pack_obs.append(dump)
            packed = prepare_turn_payload(
                user_question=QUESTION,
                task={
                    "constraints": [
                        "read_only_tools_only",
                        "cite_only_dispatched_bank_fragments",
                    ],
                    "available_tools": [
                        {"name": "get_event_context"},
                        {"name": "get_bank_evidence"},
                        {"name": "get_company_case_context"},
                        {"name": "get_available_assessment"},
                    ],
                    "note": "offline pack fit check",
                },
                observations=pack_obs,
                conversation_history=[],
                history_incomplete=False,
                history_omitted_count=0,
                budget_meta={"final_only": False, "attempt_index": 4},
                repair_note=None,
                revision_conflicts=[],
                max_chars=DEFAULT_MAX_TRANSCRIPT_CHARS,
            )
            pf["offline_pack_fits"] = bool(packed.fits)
            pf["offline_pack_chars"] = packed.payload_chars
            pf["offline_pack_limit"] = DEFAULT_MAX_TRANSCRIPT_CHARS
            pf["offline_pack_obs_names"] = [
                o.get("name") for o in packed.payload.get("observations") or []
            ]
            pf["offline_pack_incomplete"] = bool(packed.context_incomplete)

        # Create conversation via API — must not spend model HTTP
        http_before_conv = transport.attempts
        conv = client.post(
            f"/api/v1/events/{seed['event_id']}/assistant/conversations",
            headers=headers,
            json={"company_id": seed["company_id"]},
        )
        pf["create_conversation_status"] = conv.status_code
        if conv.status_code != 200:
            raise RuntimeError(f"create conversation failed: {conv.text[:200]}")
        conversation_id = conv.json().get("id") or conv.json().get("conversation_id")
        if not conversation_id:
            raise RuntimeError(f"conversation id missing: {list(conv.json().keys())}")
        pf["conversation_id"] = conversation_id
        pf["model_http_after_open"] = transport.attempts
        pf["open_conversation_spent_model_http"] = (
            transport.attempts > http_before_conv
        )

        # Fragment / PDF link smoke (auth) using collector sample
        fid = pf.get("sample_fragment_id")
        if fid:
            fr = client.get(f"/api/v1/bank-materials/fragments/{fid}", headers=headers)
            pf["fragment_http"] = fr.status_code
            href = None
            if fr.status_code == 200:
                href = (fr.json() or {}).get("content_href")
            if href:
                no_bearer = client.get(href).status_code
                with_bearer = client.get(href, headers=headers)
                pf["pdf"] = {
                    "content_http": with_bearer.status_code,
                    "no_bearer": no_bearer,
                    "content_type": with_bearer.headers.get("content-type"),
                    "sha_ok": (
                        hashlib.sha256(with_bearer.content).hexdigest() == EXPECTED_PDF_SHA
                        if with_bearer.status_code == 200
                        else False
                    ),
                }
            else:
                pf["pdf"] = {"content_http": None}
        else:
            pf["fragment_http"] = None

        pf["model_http_total_preflight"] = transport.attempts
        report["preflight"] = pf

        # case/bank may be truncated under max_result_chars — still proves wrappers run.
        case_ok = pf["wrappers"]["case_status"] in {"ok", "truncated"}
        bank_ok = pf["wrappers"]["bank_status"] in {"ok", "truncated", "unavailable"}
        # assessment unavailable expected without EventImpact
        asmt_ok = pf["wrappers"]["assessment_status"] in {"ok", "unavailable", "truncated"}
        pdf_ok = bool((pf.get("pdf") or {}).get("sha_ok")) or (
            (pf.get("pdf") or {}).get("content_http") == 200
        )

        preflight_ok = (
            pf["login_status"] == 200
            and pf["event_impact_count"] == 0
            and pf["wrappers"]["event_status"] == "ok"
            and case_ok
            and bank_ok
            and asmt_ok
            and pf.get("has_fact")
            and pf.get("has_forecast")
            and pf.get("collector_ok")
            and pf["first_payload_observations_empty"]
            and not pf["open_conversation_spent_model_http"]
            and pf["model_http_total_preflight"] == 0
            and pf.get("fragment_http") == 200
            and pdf_ok
            and pf.get("offline_pack_fits") is True
            and report["runtime_config"]["connected_to_e2e_db"]
            and E2E_DB.name in settings.database_url.replace("\\", "/")
        )
        pf["ok"] = bool(preflight_ok)
        report["preflight"] = pf
        if not preflight_ok:
            report["fatal"] = "preflight failed — no live LLM call"
            REPORT_JSON.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _write_md(report)
            print(json.dumps({"ok": False, "fatal": report["fatal"], "preflight": pf}, ensure_ascii=False))
            return 2

        # ---------- One live turn ----------
        before_sc = {"impact": 0, "scenario": 0, "decision": 0}
        with SessionLocal() as session:
            before_sc["impact"] = session.scalar(select(func.count()).select_from(EventImpact)) or 0
            before_sc["scenario"] = session.scalar(select(func.count()).select_from(Scenario)) or 0
            before_sc["decision"] = session.scalar(select(func.count()).select_from(Decision)) or 0

        live_resp = client.post(
            f"/api/v1/assistant/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": QUESTION, "client_message_id": CLIENT_MSG_ID},
        )
        report["sequence"] = list(transport.steps)
        report["live"]["http_status"] = live_resp.status_code
        report["live"]["model_http_used"] = transport.attempts
        report["live"]["client_message_id"] = CLIENT_MSG_ID

        body = live_resp.json()
        content = ""
        blocks: list[Any] = []
        if live_resp.status_code == 200:
            content = body.get("assistant_message", {}).get("content") or ""
            blocks = body.get("assistant_message", {}).get("blocks") or []
            report["live"]["outcome"] = "final"
        else:
            err = (body.get("error") or {}) if isinstance(body, dict) else {}
            report["live"]["outcome"] = "stopped"
            report["live"]["error_code"] = err.get("code")
            report["live"]["stop_message"] = err.get("message")
            # Load persisted incomplete notice
            msgs = client.get(
                f"/api/v1/assistant/conversations/{conversation_id}/messages",
                headers=headers,
            )
            if msgs.status_code == 200:
                for m in msgs.json():
                    if m.get("role") == "assistant":
                        content = m.get("content") or content
                        blocks = m.get("blocks") or blocks

        # Trace from blocks
        loop_trace = None
        used = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            data = b.get("data") if isinstance(b.get("data"), dict) else {}
            if b.get("type") == "bank_evidence_list":
                used = data.get("used") or []
                loop_trace = (data.get("diagnostics") or {}).get("loop_trace") or loop_trace
            if data.get("loop_trace"):
                loop_trace = data.get("loop_trace")
        report["live"]["loop_trace"] = loop_trace
        report["live"]["repairs_used"] = (loop_trace or {}).get("repairs_used")
        report["live"]["model_http_reserved"] = (loop_trace or {}).get(
            "model_http_reserved", (loop_trace or {}).get("model_http_used")
        )
        report["live"]["model_http_transport_trace"] = (loop_trace or {}).get(
            "model_http_transport"
        )
        report["live"]["model_http_responses"] = (loop_trace or {}).get(
            "model_http_responses"
        )
        report["live"]["peak_payload_chars"] = (loop_trace or {}).get("peak_payload_chars")
        report["live"]["tool_calls_used_budget"] = (loop_trace or {}).get("tool_calls_used")
        report["live"]["stop_reason"] = (loop_trace or {}).get("stop_reason")
        report["live"]["detail"] = (loop_trace or {}).get("detail")
        report["live"]["bank_used_count"] = len(used)
        report["live"]["bank_used"] = [
            {
                "fragment_id_prefix": str(u.get("fragment_id", ""))[:8],
                "revision": u.get("revision"),
                "text_kind": u.get("text_kind"),
                "content_type": u.get("content_type"),
            }
            for u in used
            if isinstance(u, dict)
        ]

        # Tools + feedback: prefer loop_trace; also prove obs growth in next HTTP body.
        tools_seen: list[str] = []
        for st in (loop_trace or {}).get("steps") or []:
            if isinstance(st, dict) and st.get("kind") == "tool_result" and st.get("name"):
                tools_seen.append(str(st["name"]))
        if not tools_seen:
            for step in transport.steps:
                if step.get("tool_name"):
                    tools_seen.append(str(step["tool_name"]))
        feedback = False
        for i, step in enumerate(transport.steps):
            if i == 0:
                continue
            prev = transport.steps[i - 1]
            grew = (step.get("observation_count") or 0) > (prev.get("observation_count") or 0)
            named = bool(step.get("tools_in_observations"))
            if grew and named:
                feedback = True
                break
            if prev.get("action_kind") == "tool_request" and (step.get("observation_count") or 0) > 0:
                feedback = True
                break
        report["live"]["tools_requested"] = tools_seen
        report["live"]["tool_calls_observed"] = len(tools_seen)
        report["live"]["tool_feedback_proven"] = feedback

        # Citation checks: DB revision + fragment/PDF with Bearer; IDs must appear
        # in the last model request that produced final (stateless cite scope).
        cite_ok = True
        cite_details = []
        last_step = transport.steps[-1] if transport.steps else {}
        final_request_frag_prefixes = set(last_step.get("fragment_id_prefixes") or [])
        # Prefer final HTTP step where action was final — find last request before final response
        final_req_frags: set[str] = set()
        for step in transport.steps:
            # Observations in the request body that led to this response
            for pref in step.get("fragment_id_prefixes") or []:
                if step.get("action_kind") == "final" or (
                    live_resp.status_code == 200 and step is last_step
                ):
                    final_req_frags.add(str(pref))
        # Fallback: fragments present on the last HTTP request (the one that returned final)
        if not final_req_frags:
            final_req_frags = {str(x) for x in final_request_frag_prefixes}

        with SessionLocal() as session:
            for u in used:
                if not isinstance(u, dict):
                    continue
                fid = u.get("fragment_id")
                rev = u.get("revision")
                detail: dict[str, Any] = {
                    "fragment_id_prefix": str(fid or "")[:12],
                    "revision": rev,
                    "text_kind": u.get("text_kind"),
                }
                frag = session.get(BankFragment, fid) if fid else None
                if frag is None:
                    cite_ok = False
                    detail.update({"ok": False, "reason": "missing"})
                    cite_details.append(detail)
                    continue
                if rev is not None and int(frag.revision) != int(rev):
                    cite_ok = False
                    detail.update({"ok": False, "reason": "revision_mismatch"})
                    cite_details.append(detail)
                    continue
                # Must have been in some request body (prefer final-request prefixes)
                pref = str(fid)[:12]
                in_final_body = any(
                    str(fid).startswith(p) or p.startswith(str(fid)[:8])
                    for p in final_req_frags
                ) or any(
                    str(fid).startswith(p) or p.startswith(str(fid)[:8])
                    for p in final_request_frag_prefixes
                )
                detail["in_final_request_body_heuristic"] = in_final_body
                if live_resp.status_code == 200 and used and not in_final_body:
                    # Soft signal — prefixes are truncated; still require fragment HTTP
                    detail["prefix_match_uncertain"] = True
                fr = client.get(f"/api/v1/bank-materials/fragments/{fid}", headers=headers)
                detail["fragment_http"] = fr.status_code
                pdf_http = None
                if fr.status_code == 200:
                    href = (fr.json() or {}).get("content_href")
                    if href:
                        pdf_http = client.get(href, headers=headers).status_code
                        detail["pdf_http"] = pdf_http
                        no_bearer = client.get(href).status_code
                        detail["pdf_no_bearer"] = no_bearer
                        if no_bearer == 200:
                            cite_ok = False
                            detail["reason"] = "pdf_without_bearer_allowed"
                if fr.status_code != 200 or (pdf_http is not None and pdf_http != 200):
                    cite_ok = False
                    detail["ok"] = False
                else:
                    detail["ok"] = True
                cite_details.append(detail)
        report["live"]["citation_checks"] = cite_details

        cr = _content_review(content)
        # Short manual notes for D (ID checks alone do not prove claim support).
        notes: list[str] = []
        if content:
            low = content.lower()
            if "факт" in low:
                notes.append("упоминает «факт»")
            if "прогноз" in low or "ожид" in low:
                notes.append("упоминает прогноз/ожидание")
            if "14" in content:
                notes.append("есть «14» (ставка из материалов)")
            if any(x in low for x in ("кредит", "loa", "производств", "компани")):
                notes.append("есть отсылка к профилю/продуктам компании")
            if any(x in low for x in ("проверить", "уточнить", "недостаточно")):
                notes.append("есть оговорка о проверке/недостаточности данных")
        cr["manual_notes"] = "; ".join(notes) if notes else "финальный текст пуст или без маркеров"
        cr["content_chars"] = len(content or "")
        report["content_review"] = cr

        # Idempotency replay
        replay = client.post(
            f"/api/v1/assistant/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": QUESTION, "client_message_id": CLIENT_MSG_ID},
        )
        report["idempotency"] = {
            "replay_status": replay.status_code,
            "model_http_after_replay": transport.attempts,
            "extra_http": transport.attempts - report["live"]["model_http_used"],
        }
        if live_resp.status_code == 200:
            report["idempotency"]["replay_reused"] = bool(replay.json().get("reused"))
            report["idempotency"]["ok"] = (
                replay.status_code == 200
                and replay.json().get("reused") is True
                and report["idempotency"]["extra_http"] == 0
            )
        else:
            err2 = (replay.json().get("error") or {}) if replay.status_code != 200 else {}
            report["idempotency"]["replay_error_code"] = err2.get("code")
            report["idempotency"]["ok"] = (
                replay.status_code == live_resp.status_code
                and err2.get("code") == report["live"].get("error_code")
                and (err2.get("details") or [{}])[0].get("reused") is True
                and report["idempotency"]["extra_http"] == 0
            )

        with SessionLocal() as session:
            after_impact = session.scalar(select(func.count()).select_from(EventImpact)) or 0
            after_sc = session.scalar(select(func.count()).select_from(Scenario)) or 0
            after_dec = session.scalar(select(func.count()).select_from(Decision)) or 0
            report["live"]["no_new_impact"] = after_impact == before_sc["impact"]
            report["live"]["no_new_scenario"] = after_sc == before_sc["scenario"]
            report["live"]["no_new_decision"] = after_dec == before_sc["decision"]
            # incomplete notice shape
            msgs = (
                session.query(AssistantMessage)
                .filter(AssistantMessage.conversation_id == conversation_id)
                .order_by(AssistantMessage.created_at.asc())
                .all()
            )
            report["live"]["message_count"] = len(msgs)

        # Scores A–E
        a_ok = feedback and any(
            s.get("action_kind") == "tool_request" for s in transport.steps
        )
        tools_set = set(tools_seen)
        b_parts = {
            "event": "get_event_context" in tools_set,
            "case": "get_company_case_context" in tools_set,
            "bank": "get_bank_evidence" in tools_set,
            "assessment": "get_available_assessment" in tools_set,
        }
        b_note = [k for k, v in b_parts.items() if not v]
        early_final = (
            live_resp.status_code == 200
            and transport.attempts == 1
            and not tools_seen
        )
        b_ok = (
            live_resp.status_code == 200
            and b_parts["event"]
            and b_parts["case"]
            and b_parts["bank"]
            and not early_final
        )
        c_ok = (
            live_resp.status_code == 200
            and len(used) > 0
            and cite_ok
            and all(
                (u.get("text_kind") == "exact_quote")
                for u in used
                if isinstance(u, dict)
            )
        )
        cr = report["content_review"]
        d_ok = (
            live_resp.status_code == 200
            and cr.get("fact_forecast_separated_heuristic")
            and cr.get("no_invented_money_or_probs")
            and cr.get("no_missing_impact_as_safe")
            and cr.get("bank_not_claimed_as_news_comment")
            and cr.get("profile_signals_mentioned")
        )
        e_ok = bool(report["idempotency"].get("ok")) and report["live"].get("no_new_impact")

        report["scores"] = {
            "A_mechanics": "PASS" if a_ok else "FAIL",
            "B_completeness": "PASS" if b_ok else ("PARTIAL" if a_ok and not early_final else "FAIL"),
            "B_missing_tools": b_note,
            "C_sources": "PASS" if c_ok else ("N/A_STOP" if live_resp.status_code != 200 else "FAIL"),
            "D_content": "PASS" if d_ok else ("N/A_STOP" if live_resp.status_code != 200 else "FAIL"),
            "E_idempotency": "PASS" if e_ok else "FAIL",
            "early_final_without_tools": early_final,
        }

        # 4.6.2 success: final with A+B+C+D+E (assessment optional).
        report["ok"] = (
            live_resp.status_code == 200
            and report["scores"]["A_mechanics"] == "PASS"
            and report["scores"]["B_completeness"] == "PASS"
            and report["scores"]["C_sources"] == "PASS"
            and report["scores"]["D_content"] == "PASS"
            and report["scores"]["E_idempotency"] == "PASS"
            and report["live"].get("no_new_impact")
            and report["live"].get("no_new_scenario")
            and report["live"].get("no_new_decision")
            and transport.attempts <= MODEL_HTTP_BUDGET
        )
        report["headline"] = (
            "Повтор после исправления 4.6.1 прошёл"
            if report["ok"]
            else "Повтор после исправления 4.6.1 не прошёл"
        )

    except ModelHttpBudgetExceeded as exc:
        report["fatal"] = str(exc)
        report["sequence"] = list(transport.steps)
        report["live"]["model_http_used"] = transport.attempts
        report["ok"] = False
    except Exception as exc:  # noqa: BLE001
        report["fatal"] = f"{type(exc).__name__}: {exc}"
        report["sequence"] = list(getattr(transport, "steps", []))
        report["ok"] = False
    finally:
        set_loop_http_client_for_tests(None)
        loop_client.close()
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()
        # Do not leave ASSISTANT_AGENT_LOOP in process env for other tools
        os.environ.pop("ASSISTANT_AGENT_LOOP", None)

    E2E_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(report)
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "fatal": report.get("fatal"),
                "scores": report.get("scores"),
                "model_http": report.get("live", {}).get("model_http_used"),
                "report": str(REPORT_JSON.relative_to(ROOT)).replace("\\", "/"),
                "md": str(REPORT_MD.relative_to(ROOT)).replace("\\", "/"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
