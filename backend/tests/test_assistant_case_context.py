"""Stage 3.1: case_company_context in assistant payload (no live LLM).

Contrast fixtures A/B prove context delivery and isolation rules — not
quality of real personalization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event as sa_event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    AssistantConversation,
    CaseImportFile,
    CaseImportRun,
    CaseOrg,
    CaseOrgCatalogRow,
    CaseOrgFieldResolution,
    CaseOrgGroup,
    CaseOrgGroupMember,
    CaseOrgProductMark,
    CaseSnapshot,
    Company,
    CompanyMembership,
    Event,
    EventImpact,
    User,
)
from app.models.assistant import AssistantMessage
from app.models.bank_materials import BankDocument, BankDocumentFile, BankFragment, BankOcrRun
from app.services.assistant.case_company_context import INTERPRETATION_LIMITS
from app.services.assistant.context_builder import build_conversation_context, slim_live_context
from app.services.assistant.orchestrator import get_or_create_conversation, post_message
from app.services.assistant.provider import (
    LiveAssistantProvider,
    ProviderMessage,
    ProviderResult,
)
from app.services.bank_materials.load import load_bank_document
from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
from app.services.case_data.activate_snapshot import run_activation
from app.services.case_data.link_org_company import run_link
from app.services.case_data.resolution import PRODUCT_CODES, resolve_catalog_variants
from tests.test_bank_import_dry_run import _build_valid_corpus, _confirmed_fragment

ROOT = Path(__file__).resolve().parents[1]
SLOT = "competition_default"
CATALOG_FILE = "df_Uid_data_hack.csv"


def _uid() -> str:
    return str(uuid.uuid4())


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


class ScriptedPayloadProvider(LiveAssistantProvider):
    """Records the actual provider payload (slim path via LiveAssistantProvider)."""

    def __init__(self, *, citations: list[dict[str, Any]] | None = None, content: str = "ok"):
        super().__init__(api_key="test-not-used", model="scripted", base_url="http://localhost")
        self.citations = list(citations or [])
        self.content = content
        self.last_context: dict[str, Any] | None = None
        self.calls = 0

    def generate(
        self,
        *,
        context: dict[str, Any],
        history: list[ProviderMessage],
        user_text: str,
    ) -> ProviderResult:
        self.calls += 1
        self.last_context = context
        return ProviderResult(
            content=self.content,
            blocks=[],
            tool_calls=[],
            bank_evidence_citations=list(self.citations),
        )


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = tmp_path / "asst_case.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "asst-case-context-secret")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    monkeypatch.setenv("CASE_CONTEXT_SLOT_KEY", SLOT)
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", "")
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", "")
    get_settings.cache_clear()
    command.upgrade(_alembic_config(), "head")
    engine.dispose()
    yield url
    get_settings.cache_clear()


def _session(url: str) -> Session:
    engine = create_engine(url)

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return sessionmaker(bind=engine, autoflush=False)()


def _seed_ready_snapshot(session: Session, *, slot: str, label: str, seq: int) -> CaseSnapshot:
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
                row_count_loaded=1,
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
            "companies": {"catalog_rows": 1},
            "payments": {"rows": 1},
            "person_links": {"rows": 1},
        },
        "manifest": [
            {"role": "companies", "source_file": CATALOG_FILE, "record_count": 1},
            {"role": "payments", "source_file": "payments.csv", "record_count": 1},
            {"role": "person_links", "source_file": "links.csv", "record_count": 1},
        ],
    }
    session.flush()
    return snap


def _product_marks(*, loa: bool | None, dep: bool | None) -> dict[str, bool | None]:
    marks = {c: False for c in PRODUCT_CODES}
    marks["RKO"] = True
    marks["LOA"] = loa
    marks["DEP"] = dep
    return marks


def _add_profiled_org(
    session: Session,
    snap: CaseSnapshot,
    *,
    external_uid: str,
    product_marks: dict[str, bool | None] | list[dict[str, bool | None]],
    variants: list[dict] | None = None,
) -> CaseOrg:
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
        "group_external_id": "G_1",
        "city": "Москва",
        "region": "Москва",
    }
    rows_data = variants if variants is not None else [defaults]
    if isinstance(product_marks, list):
        marks_data = product_marks
        assert len(marks_data) == len(rows_data)
    else:
        marks_data = [product_marks for _ in rows_data]

    max_row = session.scalar(
        select(func.max(CaseOrgCatalogRow.source_row_number)).where(
            CaseOrgCatalogRow.import_run_id == snap.import_run_id,
            CaseOrgCatalogRow.source_file == CATALOG_FILE,
        )
    ) or 0

    catalog_ids: list[str] = []
    merged_rows: list[dict] = []
    for i, row in enumerate(rows_data):
        merged = {**defaults, **row}
        merged_rows.append(merged)
        cid = _uid()
        catalog_ids.append(cid)
        session.add(
            CaseOrgCatalogRow(
                id=cid,
                snapshot_id=snap.id,
                import_run_id=snap.import_run_id,
                case_org_id=org.id,
                source_file=CATALOG_FILE,
                source_row_number=max_row + i + 1,
                row_content_sha256=f"{i:064d}"[:64],
                org_type=merged.get("org_type"),
                okfs_name=merged.get("okfs_name"),
                company_age_years_gradation=merged.get("company_age_years_gradation"),
                eco_mark_label=merged.get("eco_mark_label"),
                mainokved_code=merged.get("mainokved_code"),
                mainokved_name=merged.get("mainokved_name"),
                negative_mark=merged.get("negative_mark"),
                workers_fns_gradation=merged.get("workers_fns_gradation"),
                workers_spark_gradation=merged.get("workers_spark_gradation"),
                cl_type=merged.get("cl_type"),
                fts_flag=merged.get("fts_flag"),
                fts_country_name_raw=merged.get("fts_country_name_raw"),
                factoring_mark=merged.get("factoring_mark"),
                revenue_raw=str(merged.get("revenue_raw") or "0.0"),
                revenue_amount=None,
                revenue_parse_status="ok",
                revenue_parse_error=None,
                revenue_unit=None,
                revenue_currency=None,
                group_external_id=merged.get("group_external_id"),
                city=merged.get("city"),
                region=merged.get("region"),
                raw_json={"secret": "must-not-leak"},
            )
        )
        session.flush()
        for code, mark in marks_data[i].items():
            session.add(
                CaseOrgProductMark(
                    id=_uid(),
                    snapshot_id=snap.id,
                    catalog_row_id=cid,
                    product_code=code,
                    mark=mark,
                )
            )

    resolved = resolve_catalog_variants(merged_rows, product_marks_by_row=marks_data)
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
                catalog_row_id=catalog_ids[0],
                is_conflicted_membership=False,
            )
        )
    session.flush()
    return org


def _user_company(session: Session, *, name: str) -> tuple[User, Company]:
    user = User(
        id=_uid(),
        email=f"{_uid()[:8]}@example.com",
        password_hash=hash_password("CaseAsst1!"),
        display_name="Case Asst",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    company = Company(
        id=_uid(),
        name=name,
        industry="manual_industry",
        size_band="medium",
        hq_region="ManualRegion",
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


def _seed_shared_event_impact(
    session: Session,
    *,
    company_id: str,
    event: Event | None = None,
) -> Event:
    if event is None:
        event = Event(
            id=f"evt_{uuid.uuid4().hex[:12]}",
            title="ЦБ сохранил ключевую ставку",
            summary="Банк России оставил ключевую ставку без изменений.",
            category="macro",
            event_type="policy",
            severity=55.0,
            urgency_default="watch",
            status="active",
            occurred_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
            match_countries_json=[],
            match_categories_json=["rates"],
            match_currencies_json=[],
            match_materials_json=[],
            attributes_json={},
            is_demo=True,
        )
        session.add(event)
        session.flush()
    session.add(
        EventImpact(
            id=_uid(),
            event_id=event.id,
            company_id=company_id,
            impact_score=40.0,
            urgency="watch",
            confidence=0.5,
            reason_summary="Сигнал по ставке релевантен профилю.",
            exposure_value=None,
            exposure_label=None,
            exposure_unit=None,
            score_breakdown_json={},
            claims_json={},
            status="action_required",
            model_version="impact-v1.1",
        )
    )
    session.flush()
    return event


def _product_status_map(case_block: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in case_block.get("products") or []:
        if isinstance(p, dict) and p.get("code"):
            out[str(p["code"])] = str(p.get("status"))
    return out


def _configure_bank(monkeypatch, *, run_ids: list[str], storage_root: Path):
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", ",".join(run_ids))
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", str(storage_root))
    get_settings.cache_clear()


def _load_rate_doc(tmp_path: Path, engine, *, slug: str, pub_date: str = "2026-09-11"):
    fragments = [
        _confirmed_fragment(
            id="rate_keep_quote",
            exact_quote="ЦБ сохранил ключевую ставку на уровне 14 процентов.",
            ocr_text="ocr must not reach provider",
        ),
    ]
    ocr, pdf = _build_valid_corpus(
        tmp_path / slug,
        slug=slug,
        pages=1,
        fragments=fragments,
        identity={
            "confirmed_title": "Macro rate note",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": pub_date,
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": pub_date,
            "period_covered_status": "unknown",
            "topics": ["key_rate"],
            "topics_status": "confirmed",
            "staleness_note": None,
            "is_current_stance": False,
        },
    )
    parent = tmp_path / f"stg-{slug}"
    parent.mkdir(parents=True, exist_ok=True)
    staging = stage_corpus(input_dir=ocr, pdf_dir=pdf, staging_parent=parent)
    plan, errs, _ = build_prepared_document(
        staging.ocr_dir / slug,
        input_dir=staging.ocr_dir,
        pdf_dir=staging.pdf_dir,
        storage_root=staging.storage_root,
    )
    assert plan is not None and not errs
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        load_bank_document(session, plan)
        session.commit()
        doc = session.scalar(select(BankDocument).where(BankDocument.slug == slug))
        file = session.scalar(
            select(BankDocumentFile).where(BankDocumentFile.document_id == doc.id)
        )
        run = session.scalar(
            select(BankOcrRun).where(BankOcrRun.document_file_id == file.id)
        )
        frags = {
            f.stable_key: f
            for f in session.scalars(
                select(BankFragment).where(BankFragment.ocr_run_id == run.id)
            ).all()
        }
        return {"staging": staging, "run_id": run.id, "fragments": frags}


@pytest.fixture
def contrast_ab(db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Companies A (LOA=true,DEP=false) and B (LOA=false,DEP=true), same event + bank doc."""
    with _session(db_url) as s:
        snap = _seed_ready_snapshot(s, slot=SLOT, label="asst-v1", seq=1)
        _add_profiled_org(
            s,
            snap,
            external_uid="U_101",
            product_marks=_product_marks(loa=True, dep=False),
        )
        _add_profiled_org(
            s,
            snap,
            external_uid="U_102",
            product_marks=_product_marks(loa=False, dep=True),
        )
        # Conflict: okved + LOA disagree across catalog variants
        _add_profiled_org(
            s,
            snap,
            external_uid="U_103",
            product_marks=[
                _product_marks(loa=True, dep=False),
                _product_marks(loa=False, dep=False),
            ],
            variants=[
                {"mainokved_code": "46.90"},
                {"mainokved_code": "47.11"},
            ],
        )
        s.flush()
        user_a, company_a = _user_company(s, name="Компания Альфа Стенд")
        user_b, company_b = _user_company(s, name="Компания Бета Стенд")
        user_c, company_c = _user_company(s, name="Компания Conflict Стенд")
        event = _seed_shared_event_impact(s, company_id=company_a.id)
        _seed_shared_event_impact(s, company_id=company_b.id, event=event)
        _seed_shared_event_impact(s, company_id=company_c.id, event=event)
        s.commit()
        ids = {
            "snap_id": snap.id,
            "company_a": company_a.id,
            "company_b": company_b.id,
            "company_c": company_c.id,
            "user_a": user_a.id,
            "user_b": user_b.id,
            "user_c": user_c.id,
            "event_id": event.id,
            "name_a": company_a.name,
            "name_b": company_b.name,
        }

    run_activation(
        database_url=db_url,
        slot_key=SLOT,
        snapshot_id=ids["snap_id"],
        expect_no_active=True,
    )
    run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_101",
        company_id=ids["company_a"],
        linked_by="ops",
    )
    run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_102",
        company_id=ids["company_b"],
        linked_by="ops",
    )
    run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_103",
        company_id=ids["company_c"],
        linked_by="ops",
    )

    engine = create_engine(db_url)

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    seeded = _load_rate_doc(tmp_path, engine, slug="case-rate-doc")
    _configure_bank(
        monkeypatch,
        run_ids=[seeded["run_id"]],
        storage_root=seeded["staging"].storage_root,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield {
            "db_url": db_url,
            "SessionLocal": SessionLocal,
            "engine": engine,
            "ids": ids,
            "bank": seeded,
            "monkeypatch": monkeypatch,
        }
    finally:
        engine.dispose()


def test_gap_filled_case_context_in_full_and_slim(contrast_ab):
    SessionLocal = contrast_ab["SessionLocal"]
    ids = contrast_ab["ids"]
    with SessionLocal() as session:
        user_a = session.get(User, ids["user_a"])
        company_a = session.get(Company, ids["company_a"])
        full = build_conversation_context(
            session,
            event_id=ids["event_id"],
            company_id=company_a.id,
            user=user_a,
        )
        assert "case_company_context" in full
        case = full["case_company_context"]
        assert case["status"] == "profile_available"
        assert case["snapshot_id"] == ids["snap_id"]
        assert case["provenance"]["snapshot_id"] == ids["snap_id"]
        assert case["distinct_from_manual_twin"] is True
        assert full["company"]["source"] == "manual_twin"
        assert full["company"]["name"] == ids["name_a"]
        # Own org only — no payment graph / person dumps
        blob = str(case)
        assert "payments" not in blob.lower() or "не_выводить" in str(case.get("interpretation_limits"))
        assert "raw_json" not in blob
        assert "must-not-leak" not in blob

        products = _product_status_map(case)
        assert products["LOA"] == "true"
        assert products["DEP"] == "false"

        slim = slim_live_context(full)
        assert "case_company_context" in slim
        slim_case = slim["case_company_context"]
        assert slim_case["snapshot_id"] == ids["snap_id"]
        assert _product_status_map(slim_case)["LOA"] == "true"
        assert _product_status_map(slim_case)["DEP"] == "false"
        assert slim_case["interpretation_limits"]
        assert INTERPRETATION_LIMITS[0] in slim_case["interpretation_limits"]
        # Manual name anonymized; case marks remain
        assert slim["company"]["display_label"] == "ваша компания"
        assert ids["name_a"] not in str(slim["company"])


def test_contrast_a_vs_b_payload_and_isolation(contrast_ab, monkeypatch):
    SessionLocal = contrast_ab["SessionLocal"]
    ids = contrast_ab["ids"]

    with SessionLocal() as session:
        user_a = session.get(User, ids["user_a"])
        user_b = session.get(User, ids["user_b"])
        full_a = build_conversation_context(
            session, event_id=ids["event_id"], company_id=ids["company_a"], user=user_a
        )
        full_b = build_conversation_context(
            session, event_id=ids["event_id"], company_id=ids["company_b"], user=user_b
        )
        # Same event + bank evidence availability
        assert full_a["event"]["id"] == full_b["event"]["id"]
        assert full_a["bank_evidence"]["status"] == full_b["bank_evidence"]["status"]

        pa = _product_status_map(full_a["case_company_context"])
        pb = _product_status_map(full_b["case_company_context"])
        assert pa["LOA"] == "true" and pa["DEP"] == "false"
        assert pb["LOA"] == "false" and pb["DEP"] == "true"
        assert pa != pb
        assert full_a["case_company_context"]["external_uid"] == "U_101"
        assert full_b["case_company_context"]["external_uid"] == "U_102"
        assert full_a["case_company_context"]["snapshot_id"] == full_b["case_company_context"]["snapshot_id"]

        # Rename company A — product interpretation unchanged
        company_a = session.get(Company, ids["company_a"])
        company_a.name = "Совершенно Другое Имя ООО"
        session.commit()
        full_a2 = build_conversation_context(
            session, event_id=ids["event_id"], company_id=ids["company_a"], user=user_a
        )
        assert _product_status_map(full_a2["case_company_context"]) == pa
        assert full_a2["company"]["name"] == "Совершенно Другое Имя ООО"

        # User A must not receive B's case marks when building for A
        assert full_a["case_company_context"]["external_uid"] != "U_102"
        assert "U_102" not in str(full_a["case_company_context"].get("profile"))

        # Cross-membership: user A reading company B raises / access denied path
        case_cross = build_conversation_context(
            session, event_id=ids["event_id"], company_id=ids["company_b"], user=user_a
        )
        assert case_cross["case_company_context"]["status"] in {
            "access_denied",
            "read_error",
        }
        assert case_cross["case_company_context"]["profile"] is None
        assert case_cross["case_company_context"]["availability"] == "error"

    # Provider payload (slim) differs by marks, not by display name
    provider_a = ScriptedPayloadProvider(content="ответ A")
    provider_b = ScriptedPayloadProvider(content="ответ B")
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider_a
    )
    with SessionLocal() as session:
        user_a = session.get(User, ids["user_a"])
        conv_a, _ = get_or_create_conversation(
            session,
            user=user_a,
            company_id=ids["company_a"],
            event_id=ids["event_id"],
        )
        out_a = post_message(
            session, conversation_id=conv_a.id, user=user_a, content="Как ставка касается нас?"
        )
        assert provider_a.last_context is not None
        slim_a = provider_a.last_context
        assert "case_company_context" in slim_a
        assert _product_status_map(slim_a["case_company_context"])["LOA"] == "true"
        assert _product_status_map(slim_a["case_company_context"])["DEP"] == "false"
        # Live slim anonymizes manual name
        assert slim_a["company"].get("display_label") == "ваша компания"
        refs = [b for b in out_a.assistant_message.blocks if b.type == "case_context_ref"]
        assert len(refs) == 1
        assert refs[0].data["snapshot_id"] == ids["snap_id"]
        assert refs[0].data["status"] == "profile_available"
        # Bank citation block still present (validation path unchanged)
        bank_blocks = [b for b in out_a.assistant_message.blocks if b.type == "bank_evidence_list"]
        assert len(bank_blocks) == 1

    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider_b
    )
    with SessionLocal() as session:
        user_b = session.get(User, ids["user_b"])
        conv_b, _ = get_or_create_conversation(
            session,
            user=user_b,
            company_id=ids["company_b"],
            event_id=ids["event_id"],
        )
        post_message(
            session, conversation_id=conv_b.id, user=user_b, content="Как ставка касается нас?"
        )
        slim_b = provider_b.last_context
        assert slim_b is not None
        assert _product_status_map(slim_b["case_company_context"])["LOA"] == "false"
        assert _product_status_map(slim_b["case_company_context"])["DEP"] == "true"

    # Difference is in product marks, not company display label
    assert slim_a["company"]["display_label"] == slim_b["company"]["display_label"]
    assert _product_status_map(slim_a["case_company_context"]) != _product_status_map(
        slim_b["case_company_context"]
    )


def test_unknown_conflict_not_coerced_and_snapshot_frozen(contrast_ab):
    SessionLocal = contrast_ab["SessionLocal"]
    ids = contrast_ab["ids"]
    with SessionLocal() as session:
        user_c = session.get(User, ids["user_c"])
        full = build_conversation_context(
            session, event_id=ids["event_id"], company_id=ids["company_c"], user=user_c
        )
        case = full["case_company_context"]
        assert case["status"] == "profile_available"
        # okved conflict across variants → conflict, not true/false
        okved = (case.get("profile") or {}).get("okved_code") or {}
        assert okved.get("status") == "conflict"
        assert "okved_code" in (case.get("conflict_fields") or [])
        assert okved.get("status") not in {"true", "false"}

        products = _product_status_map(case)
        # LOA conflict must stay conflict — never coerced to true/false
        assert products["LOA"] == "conflict"
        assert "product:LOA" in (case.get("conflict_fields") or [])
        for p in case["products"]:
            assert p["status"] in {"true", "false", "unknown", "conflict"}

        slim = slim_live_context(full)
        slim_okved = (slim["case_company_context"].get("profile") or {}).get("okved_code") or {}
        assert slim_okved.get("status") == "conflict"
        assert _product_status_map(slim["case_company_context"])["LOA"] == "conflict"

        # Snapshot pinned once per build
        assert case["snapshot_id"] == ids["snap_id"]
        assert case["provenance"]["snapshot_id"] == ids["snap_id"]


def test_without_user_does_not_invent_profile(contrast_ab):
    SessionLocal = contrast_ab["SessionLocal"]
    ids = contrast_ab["ids"]
    with SessionLocal() as session:
        full = build_conversation_context(
            session, event_id=ids["event_id"], company_id=ids["company_a"], user=None
        )
        case = full["case_company_context"]
        assert case["status"] == "reader_not_provided"
        assert case["profile"] is None
        assert case["snapshot_id"] is None


def test_provenance_not_rewritten_on_old_messages(contrast_ab, monkeypatch):
    SessionLocal = contrast_ab["SessionLocal"]
    ids = contrast_ab["ids"]
    provider = ScriptedPayloadProvider(content="msg1")
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider
    )
    with SessionLocal() as session:
        user_a = session.get(User, ids["user_a"])
        conv, _ = get_or_create_conversation(
            session,
            user=user_a,
            company_id=ids["company_a"],
            event_id=ids["event_id"],
        )
        out1 = post_message(
            session, conversation_id=conv.id, user=user_a, content="Первый вопрос"
        )
        msg1_id = out1.assistant_message.id
        snap1 = [
            b.data.get("snapshot_id")
            for b in out1.assistant_message.blocks
            if b.type == "case_context_ref"
        ][0]

    provider.content = "msg2"
    with SessionLocal() as session:
        user_a = session.get(User, ids["user_a"])
        conv = (
            session.query(AssistantConversation)
            .filter(
                AssistantConversation.user_id == ids["user_a"],
                AssistantConversation.company_id == ids["company_a"],
                AssistantConversation.event_id == ids["event_id"],
            )
            .one()
        )
        out2 = post_message(
            session, conversation_id=conv.id, user=user_a, content="Второй вопрос"
        )
        # Old message unchanged
        old = session.get(AssistantMessage, msg1_id)
        assert old is not None
        old_refs = [b for b in (old.blocks_json or []) if b.get("type") == "case_context_ref"]
        assert len(old_refs) == 1
        assert old_refs[0]["data"]["snapshot_id"] == snap1
        # New message has its own ref (same snapshot — still not rewritten onto old)
        new_refs = [b for b in out2.assistant_message.blocks if b.type == "case_context_ref"]
        assert len(new_refs) == 1
        assert new_refs[0].data["snapshot_id"] == snap1


def test_bank_citation_validation_still_works(contrast_ab, monkeypatch):
    SessionLocal = contrast_ab["SessionLocal"]
    ids = contrast_ab["ids"]
    with SessionLocal() as session:
        user_a = session.get(User, ids["user_a"])
        ctx = build_conversation_context(
            session, event_id=ids["event_id"], company_id=ids["company_a"], user=user_a
        )
        frag = ctx["bank_evidence"]["fragments_passed_to_provider"][0]
        fid = frag["fragment_id"]
        rev = frag["revision"]
        plain = frag["text_plain_for_validation"]
        text_kind = frag["text_kind"]

    provider = ScriptedPayloadProvider(
        citations=[
            {
                "fragment_id": fid,
                "revision": rev,
                "text_kind": text_kind,
                "quoted_text": plain if text_kind == "exact_quote" else None,
            }
        ],
        content="Цитата банка",
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider
    )
    with SessionLocal() as session:
        user_a = session.get(User, ids["user_a"])
        conv, _ = get_or_create_conversation(
            session,
            user=user_a,
            company_id=ids["company_a"],
            event_id=ids["event_id"],
        )
        out = post_message(
            session, conversation_id=conv.id, user=user_a, content="Что банк пишет?"
        )
        bank = [b for b in out.assistant_message.blocks if b.type == "bank_evidence_list"][0]
        assert bank.data["used"]
        assert bank.data["used"][0]["fragment_id"] == fid
        # case ref coexists
        assert any(b.type == "case_context_ref" for b in out.assistant_message.blocks)
        # Fake id rejected
    provider2 = ScriptedPayloadProvider(
        citations=[{"fragment_id": "invented-case-999"}],
        content="fake",
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider2
    )
    with SessionLocal() as session:
        user_a = session.get(User, ids["user_a"])
        conv = (
            session.query(AssistantConversation)
            .filter(
                AssistantConversation.user_id == ids["user_a"],
                AssistantConversation.company_id == ids["company_a"],
            )
            .one()
        )
        out2 = post_message(
            session, conversation_id=conv.id, user=user_a, content="Ещё раз"
        )
        bank2 = [b for b in out2.assistant_message.blocks if b.type == "bank_evidence_list"][0]
        assert bank2.data["used"] == []
        assert bank2.data["diagnostics"]["rejected"]
