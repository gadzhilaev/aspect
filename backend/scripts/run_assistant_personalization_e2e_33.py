"""Stage 3.3 — A/B personalization E2E without EventImpact (HackathonProvider).

- SQLite backup of QA revisions DB (source read-only)
- Synthetic case snapshot + two companies (LOA/DEP contrast)
- Same synthetic rate news; no EventImpact / no recompute
- TestClient + Session override (not :8003)
- Max 4 HTTP posts to organizers model; hard stop beyond that
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
from sqlalchemy import create_engine, event as sa_event, func, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SRC_QA_DB = (
    ROOT
    / "data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db"
)
E2E_DIR = ROOT / "data/bank_materials/verification/e2e33"
E2E_DB = E2E_DIR / "assistant_personalization_e2e.db"
E2E_STORAGE = E2E_DIR / "storage"
RAW_PDF = ROOT / "data/bank_materials/raw/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"
EXPECTED_PDF_SHA = "92a96805f2b720f76bd0c52d2491044812b38401ab62d0f4a9157b4ca81c49bb"
OCR_RUN_ID = "7d64e39e-0ff5-450c-8a01-c44f678da871"
STORAGE_KEY = "bank_import_stage_5v66axai/pdf/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"
REPORT_JSON = E2E_DIR / "e2e33_report.json"

MODEL_HTTP_BUDGET = 4  # 1 primary + 1 citation retry per company
SLOT = "competition_default"
CATALOG_FILE = "df_Uid_data_hack.csv"
USER_PASSWORD = "E2ePers33!"
SYNTHETIC_EVENT_ID = "evt_synth_e2e33_policy_rate"
PRODUCT_CODES = ("RKO", "GAR", "LOA", "LEA", "DEP", "ZPP")

QUESTION = (
    "Что эта новость означает для нашей компании? Используй доступные "
    "данные компании и материалы банка. Отдели подтверждённое от "
    "предположений, объясни, что стоит проверить и чего пока нельзя "
    "рассчитать. Укажи использованные банковские источники"
)


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


def _product_marks(*, loa: bool, dep: bool) -> dict[str, bool | None]:
    marks = {c: False for c in PRODUCT_CODES}
    marks["RKO"] = True
    marks["LOA"] = loa
    marks["DEP"] = dep
    return marks


def _seed_ready_snapshot(session: Session, *, slot: str, label: str, seq: int):
    from app.models import (
        CaseImportFile,
        CaseImportRun,
        CaseSnapshot,
    )

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
    # row_count_loaded must match activation checks; orgs are added after seed.
    # Use placeholder 0 here and bump catalog file count after both orgs are inserted.
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
        "synthetic_e2e": "3.3",
    }
    session.flush()
    return snap


def _add_profiled_org(
    session: Session,
    snap,
    *,
    external_uid: str,
    product_marks: dict[str, bool | None],
):
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

    # Identical known catalog fields for A and B — only products differ.
    defaults = {
        "org_type": "ООО",
        "okfs_name": None,
        "company_age_years_gradation": "5-10",
        "eco_mark_label": None,
        "mainokved_code": "46.90",
        "mainokved_name": "Торговля",
        "negative_mark": False,
        "workers_fns_gradation": "15-100",
        "workers_spark_gradation": None,
        "cl_type": None,
        "fts_flag": True,
        "fts_country_name_raw": "Китай",
        "factoring_mark": False,
        "revenue_raw": "1000.0",
        "group_external_id": "G_E2E33",
        "city": "Москва",
        "region": "Москва",
    }
    marks_data = [product_marks]
    rows_data = [defaults]

    max_row = session.scalar(
        select(func.max(CaseOrgCatalogRow.source_row_number)).where(
            CaseOrgCatalogRow.import_run_id == snap.import_run_id,
            CaseOrgCatalogRow.source_file == CATALOG_FILE,
        )
    ) or 0

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
            raw_json={"synthetic_e2e": "3.3", "secret": "must-not-leak"},
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
        email=f"{email_prefix}_{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password(USER_PASSWORD),
        display_name=f"E2E 3.3 {email_prefix}",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    # Identical manual twin fields — only display name differs (anonymized in slim).
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
            id=_uid(),
            user_id=user.id,
            company_id=company.id,
            role="owner",
        )
    )
    session.flush()
    return user, company


def _seed_shared_event(session: Session):
    from app.models import Event, EventSource

    occurred = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    event = Event(
        id=SYNTHETIC_EVENT_ID,
        title="[СИНТЕТИЧЕСКИЙ ТЕСТ 3.3] Сохранение ключевой ставки ЦБ",
        summary=(
            "Синтетическая тестовая новость для проверки персонализации ассистента. "
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
            "synthetic_test": "3.3",
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
            publisher="Синтетический стенд 3.3",
            url=None,
            published_at=occurred,
            is_stub=True,
            excerpt="ЦБ сохранил ключевую ставку (синтетический stub).",
            source_quality=0.7,
        )
    )
    session.flush()
    return event


def _product_map(case_block: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in case_block.get("products") or []:
        if isinstance(p, dict) and p.get("code"):
            out[str(p["code"])] = str(p.get("status"))
    return out


def _review_content(label: str, content: str, *, expect_loan: bool, expect_deposit: bool) -> dict[str, Any]:
    low = content.lower()
    loan_markers = (
        "кредит",
        "заём",
        "заем",
        "loa",
        "рефинанс",
        "пересмотр",
        "плавающ",
        "ставк",
        "процентн",
        "обслуживан",
    )
    deposit_markers = (
        "депозит",
        "вклад",
        "dep",
        "пролонгац",
        "ликвидн",
        "размещен",
    )
    invented_money = any(
        x in low
        for x in (
            "расходы выросли",
            "потери составят",
            "компания потеряет",
            "% от выручки",
            "доходность составит",
            "экономия составит",
            "рублей в месяц",
            "млн ₽ эффекта",
        )
    )
    treats_no_impact_as_safe = any(
        x in low
        for x in (
            "событие безопасно",
            "риска нет потому что нет расчёта",
            "нет влияния потому что нет impact",
            "не влияет, так как расчёт отсутствует",
        )
    )
    bank_as_cbr = any(
        x in low
        for x in (
            "банк прокомментировал именно эту новость",
            "официальный комментарий банка к этой новости",
            "банк является источником цб",
        )
    )
    loan_hits = [m for m in loan_markers if m in low]
    deposit_hits = [m for m in deposit_markers if m in low]
    check_questions = any(
        x in low for x in ("проверить", "уточнить", "стоит", "неизвестно", "нельзя рассчитать", "недостаточно")
    )
    fact_forecast = ("факт" in low or "сохран" in low) and (
        "прогноз" in low or "ожид" in low or "интерпретац" in low or "материал банка" in low
    )

    attention_ok = False
    if expect_loan and not expect_deposit:
        # A: loan-oriented checks, not claiming deposit income
        attention_ok = bool(loan_hits) and check_questions and not invented_money
    elif expect_deposit and not expect_loan:
        attention_ok = bool(deposit_hits) and check_questions and not invented_money
    else:
        attention_ok = False

    # Credit=false must not be overclaimed as "no debts anywhere"
    overclaim_no_debt = expect_deposit and any(
        x in low
        for x in (
            "нет кредитов ни в одном банке",
            "отсутствуют любые долги",
            "компания без заёмных средств во всех банках",
        )
    )

    return {
        "label": label,
        "loan_marker_hits": loan_hits,
        "deposit_marker_hits": deposit_hits,
        "check_questions_present": check_questions,
        "fact_forecast_separated_heuristic": fact_forecast,
        "no_invented_money_effect": not invented_money,
        "no_treat_missing_impact_as_safe": not treats_no_impact_as_safe,
        "bank_not_claimed_as_news_comment": not bank_as_cbr,
        "no_overclaim_no_debts_everywhere": not overclaim_no_debt,
        "product_attention_heuristic_pass": attention_ok and not overclaim_no_debt,
        "sample": (content.strip().replace("\n", " ")[:450] + ("…" if len(content) > 450 else "")),
    }


def main() -> int:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    report: dict[str, Any] = {
        "stage": "3.3",
        "synthetic_parts": [
            "user/company/membership A and B (identical manual twin except display name)",
            "case snapshot + catalog rows U_301 / U_302 (explicitly synthetic)",
            "product marks A: LOA=true DEP=false; B: LOA=false DEP=true",
            "event (explicitly labeled synthetic; occurred_at=2026-09-20; NO EventImpact)",
            "event_source stub",
            "storage layout copy of PDF under test-only root",
        ],
        "bank_document_unchanged": True,
        "no_event_impact_by_design": True,
        "pre_llm": {},
        "live": {"A": {}, "B": {}},
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
    os.environ["SECRET_KEY"] = "e2e33-secret-not-for-prod"
    os.environ["ASSISTANT_PROVIDER"] = "hackathon"
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
        "model": settings.resolved_hackathon_model(),
        "base_url": settings.resolved_hackathon_base_url(),
        "key_configured": bool(settings.resolved_hackathon_api_key()),
        "ocr_run_scoped": OCR_RUN_ID in settings.bank_materials_allowed_ocr_run_id_set(),
        "case_slot": settings.case_context_slot_key,
        "connected_to_e2e_db": E2E_DB.name in settings.database_url.replace("\\", "/"),
    }
    if settings.normalized_assistant_provider() != "hackathon":
        report["fatal"] = "provider not hackathon after config"
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fatal": report["fatal"]}, ensure_ascii=False))
        return 2

    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _) -> None:  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # --- Seed synthetic case + companies (no impact) ---
    with SessionLocal() as session:
        snap = _seed_ready_snapshot(session, slot=SLOT, label="e2e33-synth-v1", seq=1)
        _add_profiled_org(
            session, snap, external_uid="U_301", product_marks=_product_marks(loa=True, dep=False)
        )
        _add_profiled_org(
            session, snap, external_uid="U_302", product_marks=_product_marks(loa=False, dep=True)
        )
        # Align import file counters with activation preconditions (2 catalog rows).
        from app.models import CaseImportFile as _CaseImportFile

        cat_file = session.scalars(
            select(_CaseImportFile).where(
                _CaseImportFile.import_run_id == snap.import_run_id,
                _CaseImportFile.source_file == CATALOG_FILE,
            )
        ).one()
        cat_file.row_count_loaded = 2
        snap.validation_report_json = {
            **(snap.validation_report_json or {}),
            "final_checks": {
                "companies": {"catalog_rows": 2},
                "payments": {"rows": 0},
                "person_links": {"rows": 0},
            },
            "manifest": [
                {"role": "companies", "source_file": CATALOG_FILE, "record_count": 2},
                {"role": "payments", "source_file": "payments.csv", "record_count": 0},
                {"role": "person_links", "source_file": "links.csv", "record_count": 0},
            ],
        }
        user_a, company_a = _user_company(
            session, name="Синтетика Альфа стенд 3.3", email_prefix="e2e33a"
        )
        user_b, company_b = _user_company(
            session, name="Синтетика Бета стенд 3.3", email_prefix="e2e33b"
        )
        event = _seed_shared_event(session)
        session.commit()
        seed = {
            "snap_id": snap.id,
            "event_id": event.id,
            "user_a_id": user_a.id,
            "user_b_id": user_b.id,
            "email_a": user_a.email,
            "email_b": user_b.email,
            "company_a_id": company_a.id,
            "company_b_id": company_b.id,
            "name_a": company_a.name,
            "name_b": company_b.name,
        }

    from app.services.case_data.activate_snapshot import run_activation
    from app.services.case_data.link_org_company import run_link

    act = run_activation(
        database_url=db_url,
        slot_key=SLOT,
        snapshot_id=seed["snap_id"],
        expect_no_active=True,
    )
    report["seed"] = {
        "activation": getattr(act, "outcome", str(act)),
        "snap_id": seed["snap_id"],
        "event_id": seed["event_id"],
        "company_a_id": seed["company_a_id"],
        "company_b_id": seed["company_b_id"],
        "uid_a": "U_301",
        "uid_b": "U_302",
        "email_domain": "example.com",
    }
    run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_301",
        company_id=seed["company_a_id"],
        linked_by="e2e33",
    )
    run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_302",
        company_id=seed["company_b_id"],
        linked_by="e2e33",
    )

    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import create_app
    from app.models import Event, EventImpact, Scenario, Decision, User
    from app.models.assistant import AssistantConversation, AssistantMessage
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
    captured_contexts: list[dict[str, Any]] = []
    last_usage: dict[str, Any] = {"items": []}

    def _init_with_counter(self, *args, **kwargs):  # noqa: ANN001
        kwargs = dict(kwargs)
        kwargs["http_client"] = httpx.Client(transport=transport, timeout=90.0)
        kwargs.setdefault("timeout", 90.0)
        _orig_init(self, *args, **kwargs)

    _orig_generate = HackathonProvider.generate

    def _generate_capture(self, *args, **kwargs):  # noqa: ANN001
        # HackathonProvider.generate uses keyword-only ``context=``.
        ctx = kwargs.get("context")
        if isinstance(ctx, dict):
            captured_contexts.append(
                {
                    "assessment_state": ctx.get("assessment_state"),
                    "has_impact_calculation": ctx.get("has_impact_calculation"),
                    "impact": ctx.get("impact"),
                    "products": _product_map(ctx.get("case_company_context") or {}),
                    "snapshot_id": (ctx.get("case_company_context") or {}).get("snapshot_id"),
                    "external_uid": (ctx.get("case_company_context") or {}).get("external_uid"),
                }
            )
        result = _orig_generate(self, *args, **kwargs)
        last_usage["items"].append(result.usage)
        return result

    hackathon_mod.HackathonProvider.__init__ = _init_with_counter  # type: ignore[method-assign]
    hackathon_mod.HackathonProvider.generate = _generate_capture  # type: ignore[method-assign]

    client = TestClient(app)
    try:
        # ========== PRE-LLM ==========
        with SessionLocal() as session:
            impact_count = (
                session.query(EventImpact)
                .filter(EventImpact.event_id == seed["event_id"])
                .count()
            )
            report["pre_llm"]["event_impact_rows"] = impact_count
            assert impact_count == 0

            user_a = session.get(User, seed["user_a_id"])
            user_b = session.get(User, seed["user_b_id"])
            ctx_a = build_conversation_context(
                session,
                event_id=seed["event_id"],
                company_id=seed["company_a_id"],
                user=user_a,
            )
            ctx_b = build_conversation_context(
                session,
                event_id=seed["event_id"],
                company_id=seed["company_b_id"],
                user=user_b,
            )
            # Cross isolation
            ctx_cross = build_conversation_context(
                session,
                event_id=seed["event_id"],
                company_id=seed["company_b_id"],
                user=user_a,
            )

        pa = _product_map(ctx_a.get("case_company_context") or {})
        pb = _product_map(ctx_b.get("case_company_context") or {})
        report["pre_llm"]["case_a"] = {
            "status": (ctx_a.get("case_company_context") or {}).get("status"),
            "snapshot_id": (ctx_a.get("case_company_context") or {}).get("snapshot_id"),
            "external_uid": (ctx_a.get("case_company_context") or {}).get("external_uid"),
            "products": pa,
            "assessment_state": ctx_a.get("assessment_state"),
            "impact_is_null": ctx_a.get("impact") is None,
            "paths_empty": ctx_a.get("paths") == [],
        }
        report["pre_llm"]["case_b"] = {
            "status": (ctx_b.get("case_company_context") or {}).get("status"),
            "snapshot_id": (ctx_b.get("case_company_context") or {}).get("snapshot_id"),
            "external_uid": (ctx_b.get("case_company_context") or {}).get("external_uid"),
            "products": pb,
            "assessment_state": ctx_b.get("assessment_state"),
            "impact_is_null": ctx_b.get("impact") is None,
            "paths_empty": ctx_b.get("paths") == [],
        }
        report["pre_llm"]["same_snapshot"] = (
            report["pre_llm"]["case_a"]["snapshot_id"]
            == report["pre_llm"]["case_b"]["snapshot_id"]
            == seed["snap_id"]
        )
        report["pre_llm"]["products_differ"] = pa != pb
        report["pre_llm"]["a_loa_dep"] = {"LOA": pa.get("LOA"), "DEP": pa.get("DEP")}
        report["pre_llm"]["b_loa_dep"] = {"LOA": pb.get("LOA"), "DEP": pb.get("DEP")}
        report["pre_llm"]["cross_access_denied"] = (
            (ctx_cross.get("case_company_context") or {}).get("status")
            in {"access_denied", "read_error"}
        )
        report["pre_llm"]["same_event"] = ctx_a["event"]["id"] == ctx_b["event"]["id"]
        report["pre_llm"]["same_bank_status"] = (ctx_a.get("bank_evidence") or {}).get(
            "status"
        ) == (ctx_b.get("bank_evidence") or {}).get("status")
        bank_a = ctx_a.get("bank_evidence") or {}
        bank_b = ctx_b.get("bank_evidence") or {}
        passed_a = bank_a.get("fragments_passed_to_provider") or []
        passed_b = bank_b.get("fragments_passed_to_provider") or []
        ids_a = sorted(
            str(p.get("fragment_id")) for p in passed_a if isinstance(p, dict)
        )
        ids_b = sorted(
            str(p.get("fragment_id")) for p in passed_b if isinstance(p, dict)
        )
        report["pre_llm"]["bank_passed_ids_equal"] = ids_a == ids_b and len(ids_a) > 0
        report["pre_llm"]["bank_status"] = bank_a.get("status")
        report["pre_llm"]["passed_count"] = len(ids_a)

        slim_a = slim_live_context(ctx_a)
        slim_b = slim_live_context(ctx_b)
        report["pre_llm"]["slim_display_label_same"] = (
            (slim_a.get("company") or {}).get("display_label")
            == (slim_b.get("company") or {}).get("display_label")
            == "ваша компания"
        )
        report["pre_llm"]["slim_products_differ"] = _product_map(
            slim_a.get("case_company_context") or {}
        ) != _product_map(slim_b.get("case_company_context") or {})
        report["pre_llm"]["slim_no_impact_numbers"] = (
            slim_a.get("impact") is None
            and slim_a.get("impact_results") is None
            and slim_b.get("impact") is None
        )
        # Manual name must not appear in slim company block
        report["pre_llm"]["slim_hides_manual_names"] = (
            seed["name_a"] not in str(slim_a.get("company"))
            and seed["name_b"] not in str(slim_b.get("company"))
        )

        # Login + membership isolation via HTTP
        login_a = client.post(
            "/api/v1/auth/login",
            json={"email": seed["email_a"], "password": USER_PASSWORD},
        )
        login_b = client.post(
            "/api/v1/auth/login",
            json={"email": seed["email_b"], "password": USER_PASSWORD},
        )
        report["pre_llm"]["login_a"] = login_a.status_code
        report["pre_llm"]["login_b"] = login_b.status_code
        if login_a.status_code != 200 or login_b.status_code != 200:
            raise RuntimeError("login failed")
        headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}
        headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

        # A cannot open for B company
        forbid = client.post(
            f"/api/v1/events/{seed['event_id']}/assistant/conversations",
            headers=headers_a,
            json={"company_id": seed["company_b_id"]},
        )
        report["pre_llm"]["a_open_b_company_status"] = forbid.status_code

        # PDF check (one fragment)
        frag_id = ids_a[0] if ids_a else None
        pdf_ok = False
        if frag_id:
            fr = client.get(f"/api/v1/bank-materials/fragments/{frag_id}", headers=headers_a)
            body = fr.json() if fr.status_code == 200 else {}
            href = body.get("content_href")
            no_bearer = client.get(href).status_code if href else None
            with_bearer = client.get(href, headers=headers_a) if href else None
            pdf_ok = (
                fr.status_code == 200
                and with_bearer is not None
                and with_bearer.status_code == 200
                and "pdf" in (with_bearer.headers.get("content-type") or "").lower()
                and hashlib.sha256(with_bearer.content).hexdigest() == EXPECTED_PDF_SHA
                and no_bearer in {401, 403}
            )
            report["pre_llm"]["pdf"] = {
                "fragment_http": fr.status_code,
                "pdf_http": with_bearer.status_code if with_bearer else None,
                "no_bearer": no_bearer,
                "sha_ok": (
                    hashlib.sha256(with_bearer.content).hexdigest() == EXPECTED_PDF_SHA
                    if with_bearer and with_bearer.status_code == 200
                    else False
                ),
            }

        # Open conversations — must not call model, must not create impact
        open_a = client.post(
            f"/api/v1/events/{seed['event_id']}/assistant/conversations",
            headers=headers_a,
            json={"company_id": seed["company_a_id"]},
        )
        open_b = client.post(
            f"/api/v1/events/{seed['event_id']}/assistant/conversations",
            headers=headers_b,
            json={"company_id": seed["company_b_id"]},
        )
        report["pre_llm"]["open_a"] = {
            "status": open_a.status_code,
            "assessment_state": (open_a.json() or {}).get("assessment_state"),
            "has_impact_calculation": (open_a.json() or {}).get("has_impact_calculation"),
            "answer_basis": (open_a.json() or {}).get("answer_basis"),
            "answer_model": (open_a.json() or {}).get("answer_model"),
        }
        report["pre_llm"]["open_b"] = {
            "status": open_b.status_code,
            "assessment_state": (open_b.json() or {}).get("assessment_state"),
            "has_impact_calculation": (open_b.json() or {}).get("has_impact_calculation"),
        }
        report["pre_llm"]["model_http_after_open"] = transport.attempts
        if open_a.status_code != 200 or open_b.status_code != 200:
            raise RuntimeError("open conversation failed")
        conv_a = open_a.json()["id"]
        conv_b = open_b.json()["id"]

        with SessionLocal() as session:
            report["pre_llm"]["impact_rows_after_open"] = (
                session.query(EventImpact)
                .filter(EventImpact.event_id == seed["event_id"])
                .count()
            )

        report["pass_matrix"]["pre_llm"] = all(
            [
                report["pre_llm"]["event_impact_rows"] == 0,
                report["pre_llm"]["case_a"]["status"] == "profile_available",
                report["pre_llm"]["case_b"]["status"] == "profile_available",
                report["pre_llm"]["same_snapshot"],
                report["pre_llm"]["a_loa_dep"] == {"LOA": "true", "DEP": "false"},
                report["pre_llm"]["b_loa_dep"] == {"LOA": "false", "DEP": "true"},
                report["pre_llm"]["cross_access_denied"],
                report["pre_llm"]["same_event"],
                report["pre_llm"]["bank_passed_ids_equal"],
                report["pre_llm"]["bank_status"] == "available",
                report["pre_llm"]["slim_products_differ"],
                report["pre_llm"]["slim_no_impact_numbers"],
                report["pre_llm"]["a_open_b_company_status"] == 403,
                report["pre_llm"]["open_a"]["assessment_state"] == CALCULATION_UNAVAILABLE,
                report["pre_llm"]["open_b"]["assessment_state"] == CALCULATION_UNAVAILABLE,
                report["pre_llm"]["open_a"]["has_impact_calculation"] is False,
                report["pre_llm"]["model_http_after_open"] == 0,
                report["pre_llm"]["impact_rows_after_open"] == 0,
                pdf_ok,
            ]
        )

        if not report["pass_matrix"]["pre_llm"]:
            report["live"]["skipped"] = True
            report["live"]["reason"] = "pre_llm_failed"
            raise RuntimeError("pre-LLM checks failed — not calling live model")

        # ========== LIVE A then B ==========
        def _run_live(label: str, conv_id: str, headers: dict) -> dict[str, Any]:
            before = transport.attempts
            post = client.post(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                headers=headers,
                json={
                    "content": QUESTION,
                    "client_message_id": f"e2e33-{label}-{uuid.uuid4().hex[:8]}",
                },
            )
            after = transport.attempts
            out: dict[str, Any] = {
                "post_status": post.status_code,
                "model_http_delta": after - before,
                "model_http_total_after": after,
            }
            if post.status_code != 200:
                err = (
                    post.json().get("error")
                    if post.headers.get("content-type", "").startswith("application/json")
                    else None
                )
                out["error_code"] = (err or {}).get("code")
                out["error_message"] = (err or {}).get("message")
                return out

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
            out["content_len"] = len(content)
            out["content"] = content  # full text for human review in report file only
            out["used_count"] = len(used)
            out["diagnostics"] = {
                "retrieved_count": diagnostics.get("retrieved_count"),
                "passed_to_provider_ids": diagnostics.get("passed_to_provider_ids"),
                "validated_ids": diagnostics.get("validated_ids"),
                "rejected": diagnostics.get("rejected"),
            }
            passed_ids = set(diagnostics.get("passed_to_provider_ids") or [])
            validated_ids = set(diagnostics.get("validated_ids") or [])
            used_ids = {str(u.get("fragment_id")) for u in used if isinstance(u, dict)}
            out["used_subset_of_passed"] = used_ids.issubset(passed_ids) if passed_ids else False
            out["used_eq_validated"] = used_ids == validated_ids
            out["all_used_rev_pinned"] = all(
                isinstance(u, dict) and u.get("revision") is not None for u in used
            )
            # Exact quotes
            quote_checks = []
            with SessionLocal() as session:
                for u in used:
                    if not isinstance(u, dict) or u.get("text_kind") != "exact_quote":
                        continue
                    frag = session.get(BankFragment, u.get("fragment_id"))
                    if frag is None:
                        quote_checks.append({"ok": False, "reason": "missing"})
                        continue
                    ok = (u.get("text") or "").strip() == (frag.verified_transcript or "").strip()
                    quote_checks.append({"ok": ok, "revision": frag.revision})
            out["exact_quote_ok"] = all(c.get("ok") for c in quote_checks) if quote_checks else True
            out["exact_quote_checks"] = quote_checks

            if case_refs:
                cref = case_refs[0].get("data") or {}
                out["case_context_ref"] = {
                    "status": cref.get("status"),
                    "snapshot_id": cref.get("snapshot_id"),
                    "source_file": cref.get("source_file"),
                }
            else:
                out["case_context_ref"] = None

            # History
            msgs = client.get(
                f"/api/v1/assistant/conversations/{conv_id}/messages",
                headers=headers,
            )
            out["history_http"] = msgs.status_code
            out["history_message_count"] = len(msgs.json()) if msgs.status_code == 200 else 0
            return out

        live_a = _run_live("A", conv_a, headers_a)
        report["live"]["A"] = {k: v for k, v in live_a.items() if k != "content"}
        report["live"]["A"]["content_sample"] = (live_a.get("content") or "")[:500]
        report["live"]["A_full_content"] = live_a.get("content")

        live_b = _run_live("B", conv_b, headers_b)
        report["live"]["B"] = {k: v for k, v in live_b.items() if k != "content"}
        report["live"]["B"]["content_sample"] = (live_b.get("content") or "")[:500]
        report["live"]["B_full_content"] = live_b.get("content")

        report["live"]["model_http_attempts"] = transport.attempts
        report["live"]["model_http_hosts"] = transport.hosts
        report["live"]["model_http_paths"] = transport.paths
        report["live"]["model_http_statuses"] = transport.statuses
        report["live"]["usage_items"] = last_usage["items"]
        report["live"]["captured_provider_contexts"] = captured_contexts
        report["live"]["question"] = QUESTION

        with SessionLocal() as session:
            report["live"]["impact_rows_after_live"] = (
                session.query(EventImpact)
                .filter(EventImpact.event_id == seed["event_id"])
                .count()
            )
            report["live"]["scenario_count"] = session.query(Scenario).count()
            report["live"]["decision_count"] = session.query(Decision).count()
            report["live"]["conversation_count"] = session.query(AssistantConversation).count()
            report["live"]["message_count"] = session.query(AssistantMessage).count()

        # Technical pass
        def _tech_ok(side: dict) -> bool:
            return bool(
                side.get("post_status") == 200
                and side.get("case_context_ref")
                and side["case_context_ref"].get("snapshot_id") == seed["snap_id"]
                and side.get("used_subset_of_passed")
                and side.get("all_used_rev_pinned")
                and side.get("exact_quote_ok")
                and side.get("history_http") == 200
                and side.get("history_message_count", 0) >= 3
            )

        report["pass_matrix"]["live_http_budget"] = (
            1 <= transport.attempts <= MODEL_HTTP_BUDGET
            and all("changellenge" in h for h in transport.hosts if h)
            and not any("openai.com" in h for h in transport.hosts)
            and not any("gigachat" in h for h in transport.hosts)
        )
        report["pass_matrix"]["tech_a"] = _tech_ok(report["live"]["A"])
        report["pass_matrix"]["tech_b"] = _tech_ok(report["live"]["B"])
        report["pass_matrix"]["no_impact_created"] = report["live"]["impact_rows_after_live"] == 0
        report["pass_matrix"]["no_scenario_decision"] = (
            report["live"]["scenario_count"] == 0 and report["live"]["decision_count"] == 0
        )
        report["pass_matrix"]["provider_context_products"] = (
            len(captured_contexts) >= 2
            and any(c.get("products", {}).get("LOA") == "true" for c in captured_contexts)
            and any(c.get("products", {}).get("DEP") == "true" for c in captured_contexts)
            and all(c.get("impact") is None for c in captured_contexts)
            and all(
                c.get("assessment_state") == CALCULATION_UNAVAILABLE for c in captured_contexts
            )
        )

        # Content review (human-oriented heuristics + excerpts)
        rev_a = _review_content(
            "A", live_a.get("content") or "", expect_loan=True, expect_deposit=False
        )
        rev_b = _review_content(
            "B", live_b.get("content") or "", expect_loan=False, expect_deposit=True
        )
        report["content_review"]["A"] = rev_a
        report["content_review"]["B"] = rev_b

        # Contrast: answers should not be near-identical boilerplate
        ca = (live_a.get("content") or "").strip()
        cb = (live_b.get("content") or "").strip()
        same_text = ca == cb
        # Shared generic-only if both lack product-specific markers
        a_has_loan = bool(rev_a["loan_marker_hits"])
        b_has_dep = bool(rev_b["deposit_marker_hits"])
        contrast_signal = a_has_loan and b_has_dep and not same_text

        report["content_review"]["answers_identical"] = same_text
        report["content_review"]["contrast_signal_loan_vs_deposit"] = contrast_signal
        report["content_review"]["shared_safety"] = {
            "both_no_invented_money": rev_a["no_invented_money_effect"]
            and rev_b["no_invented_money_effect"],
            "both_no_safe_from_missing_impact": rev_a["no_treat_missing_impact_as_safe"]
            and rev_b["no_treat_missing_impact_as_safe"],
            "both_bank_not_news_comment": rev_a["bank_not_claimed_as_news_comment"]
            and rev_b["bank_not_claimed_as_news_comment"],
            "both_fact_forecast_heuristic": rev_a["fact_forecast_separated_heuristic"]
            and rev_b["fact_forecast_separated_heuristic"],
        }

        report["pass_matrix"]["content_delivery_ok"] = True  # context was delivered (pre+capture)
        report["pass_matrix"]["content_a_attention"] = rev_a["product_attention_heuristic_pass"]
        report["pass_matrix"]["content_b_attention"] = rev_b["product_attention_heuristic_pass"]
        report["pass_matrix"]["content_shared_safety"] = all(
            report["content_review"]["shared_safety"].values()
        )
        report["pass_matrix"]["content_contrast"] = contrast_signal

        # Honest verdicts (separate dimensions)
        report["verdicts"] = {
            "context_delivery": (
                "PASS"
                if report["pass_matrix"]["pre_llm"]
                and report["pass_matrix"]["provider_context_products"]
                else "FAIL"
            ),
            "source_technical": (
                "PASS"
                if report["pass_matrix"]["tech_a"]
                and report["pass_matrix"]["tech_b"]
                and report["pass_matrix"]["live_http_budget"]
                and report["pass_matrix"]["no_impact_created"]
                and report["pass_matrix"]["no_scenario_decision"]
                else "FAIL"
            ),
            "content_personalization": (
                "PASS"
                if report["pass_matrix"]["content_a_attention"]
                and report["pass_matrix"]["content_b_attention"]
                and report["pass_matrix"]["content_shared_safety"]
                and report["pass_matrix"]["content_contrast"]
                else "FAIL"
            ),
            "note": (
                "One live run does not prove model quality stability. "
                "Content PASS is heuristic review of this run, not a guarantee."
            ),
        }

    except ModelHttpBudgetExceeded as exc:
        report["live"]["budget_stop"] = True
        report["live"]["budget_error"] = str(exc)
        report["live"]["model_http_attempts"] = transport.attempts
        report["verdicts"] = {
            "context_delivery": "PASS" if report["pass_matrix"].get("pre_llm") else "FAIL",
            "source_technical": "FAIL",
            "content_personalization": "FAIL",
            "note": "Stopped by model HTTP budget",
        }
    except Exception as exc:  # noqa: BLE001
        report["exception"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
        report.setdefault(
            "verdicts",
            {
                "context_delivery": "FAIL",
                "source_technical": "FAIL",
                "content_personalization": "FAIL",
            },
        )
    finally:
        client.close()
        app.dependency_overrides.clear()
        hackathon_mod.HackathonProvider.__init__ = _orig_init  # type: ignore[method-assign]
        hackathon_mod.HackathonProvider.generate = _orig_generate  # type: ignore[method-assign]
        engine.dispose()
        get_settings.cache_clear()

    E2E_DIR.mkdir(parents=True, exist_ok=True)
    # Keep full answers in JSON for the doc author; strip nothing except tokens (never stored)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "ok_pre_llm": bool(report.get("pass_matrix", {}).get("pre_llm")),
        "verdicts": report.get("verdicts"),
        "model_http_attempts": report.get("live", {}).get("model_http_attempts"),
        "report": str(REPORT_JSON.relative_to(ROOT)).replace("\\", "/"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report.get("pass_matrix", {}).get("pre_llm") else 1


if __name__ == "__main__":
    raise SystemExit(main())
