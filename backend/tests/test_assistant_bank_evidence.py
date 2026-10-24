"""Assistant bank evidence: context packing, citation validation, history (no live LLM)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import create_app
from app.models import (
    Company,
    CompanyMembership,
    Event,
    EventImpact,
    User,
)
from app.models.assistant import AssistantMessage
from app.models.bank_materials import BankDocument, BankDocumentFile, BankFragment, BankOcrRun
from app.services.assistant.bank_evidence_citations import validate_bank_evidence_citations
from app.services.assistant.bank_evidence_context import (
    build_bank_evidence_context_block,
    passed_fragment_index,
)
from app.services.assistant.context_builder import build_conversation_context, slim_live_context
from app.services.assistant.orchestrator import post_message
from app.services.assistant.provider import AssistantProvider, ProviderMessage, ProviderResult
from app.services.bank_materials.load import load_bank_document
from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
from tests.test_bank_import_dry_run import _build_valid_corpus, _confirmed_fragment

ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


class ScriptedProvider(AssistantProvider):
    """Test double: returns scripted citations; records last context."""

    def __init__(self, citations: list[dict[str, Any]] | None = None, content: str = "ok"):
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
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "asst_bank.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "asst-bank-evidence-secret")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", "")
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", "")
    get_settings.cache_clear()
    command.upgrade(_alembic_config(), "head")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    try:
        yield client, SessionLocal, tmp_path, monkeypatch, engine
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def _configure(monkeypatch, *, run_ids: list[str], storage_root: Path):
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", ",".join(run_ids))
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", str(storage_root))
    get_settings.cache_clear()


def _seed_company_event_impact(session: Session, *, occurred_at: datetime) -> tuple[User, Company, Event]:
    user = User(
        id=str(uuid.uuid4()),
        email=f"asst_bank_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("AsstBank1!"),
        display_name="Asst Bank",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    company = Company(
        id=str(uuid.uuid4()),
        name="Asst Co",
        industry="manufacturing",
        size_band="small",
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
            id=str(uuid.uuid4()), user_id=user.id, company_id=company.id, role="owner"
        )
    )
    event = Event(
        id=f"evt_{uuid.uuid4().hex[:12]}",
        title="ЦБ сохранил ключевую ставку",
        summary="Банк России оставил ключевую ставку без изменений.",
        category="macro",
        event_type="policy",
        severity=55.0,
        urgency_default="watch",
        status="active",
        occurred_at=occurred_at,
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
            id=str(uuid.uuid4()),
            event_id=event.id,
            company_id=company.id,
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
    session.commit()
    return user, company, event


def _load_rate_doc(tmp_path: Path, engine, *, slug: str, pub_date: str = "2026-09-11"):
    fragments = [
        _confirmed_fragment(
            id="rate_keep_quote",
            exact_quote="ЦБ сохранил ключевую ставку на уровне 14 процентов.",
            ocr_text="ocr must not reach provider",
        ),
        {
            "id": "rate_forecast",
            "kind": "summary",
            "content_type": "forecast",
            "content_type_status": "confirmed",
            "primary_region_type": "prose",
            "page": 1,
            "regions": [
                {
                    "region_type": "prose",
                    "bbox": {"left": 10, "top": 40, "width": 40, "height": 20},
                }
            ],
            "summary": "Банк ожидает сохранения паузы по ставке.",
            "verification_status": "verified",
        },
        {
            "id": "unverified_noise",
            "kind": "exact_quote",
            "content_type": "fact",
            "content_type_status": "unknown",
            "primary_region_type": "unverified",
            "page": 1,
            "regions": [
                {
                    "region_type": "unverified",
                    "bbox": {"left": 10, "top": 70, "width": 40, "height": 20},
                }
            ],
            "ocr_text": "RAW UNVERIFIED",
            "exact_quote": "RAW UNVERIFIED",
            "verification_status": "unverified",
        },
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
        return {
            "staging": staging,
            "run_id": run.id,
            "fragments": frags,
        }


def test_validate_citations_unit():
    passed = {
        "frag-1": {
            "fragment_id": "frag-1",
            "revision": 2,
            "text_kind": "exact_quote",
            "text_plain_for_validation": "Hello quote",
            "content_type": "fact",
            "document_title": "Doc",
            "publication_date": "2026-09-11",
            "publication_date_precision": "day",
            "page_number": 1,
            "source_role": None,
            "qa_method": None,
            "document_href": "/api/v1/bank-materials/documents/d",
            "fragment_href": "/api/v1/bank-materials/fragments/frag-1",
            "content_href": "/api/v1/bank-materials/files/f/content",
        }
    }
    ok = validate_bank_evidence_citations(
        [{"fragment_id": "frag-1", "revision": 2, "quoted_text": "Hello quote"}],
        passed_index=passed,
    )
    assert len(ok.validated) == 1
    bad_id = validate_bank_evidence_citations(
        [{"fragment_id": "nope"}], passed_index=passed
    )
    assert bad_id.validated == []
    assert bad_id.rejected[0].reason == "unknown_or_not_passed_fragment_id"
    bad_quote = validate_bank_evidence_citations(
        [{"fragment_id": "frag-1", "quoted_text": "tampered"}],
        passed_index=passed,
    )
    assert bad_quote.rejected[0].reason == "exact_quote_text_mismatch"


def test_context_excludes_unverified_and_future(harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    seeded = _load_rate_doc(tmp_path, engine, slug="ctx-doc", pub_date="2026-09-11")
    _configure(
        monkeypatch, run_ids=[seeded["run_id"]], storage_root=seeded["staging"].storage_root
    )
    with SessionLocal() as session:
        user, company, event = _seed_company_event_impact(
            session, occurred_at=datetime(2026, 9, 12, tzinfo=timezone.utc)
        )
        ctx = build_conversation_context(session, event_id=event.id, company_id=company.id)
        bank = ctx["bank_evidence"]
        assert bank["status"] == "available"
        passed = bank["fragments_passed_to_provider"]
        assert passed
        keys = {f["stable_key"] for f in passed}
        assert "unverified_noise" not in keys
        blob = str(passed)
        assert "ocr must not reach provider" not in blob
        assert "RAW UNVERIFIED" not in blob
        assert "storage" not in blob.lower() or "storage_key" not in blob

        slim = slim_live_context(ctx)
        assert "text_plain_for_validation" not in str(slim.get("bank_evidence"))
        assert slim["bank_evidence"]["available"] is True

    # Future publication relative to older event date
    seeded2 = _load_rate_doc(tmp_path, engine, slug="future-doc", pub_date="2026-10-01")
    _configure(
        monkeypatch,
        run_ids=[seeded2["run_id"]],
        storage_root=seeded2["staging"].storage_root,
    )
    with SessionLocal() as session:
        user, company, event = _seed_company_event_impact(
            session, occurred_at=datetime(2026, 9, 12, tzinfo=timezone.utc)
        )
        block = build_bank_evidence_context_block(session, event=event)
        assert block["status"] == "no_matching_evidence"
        assert block["fragments_passed_to_provider"] == []


def test_post_message_valid_citation_and_reject_fake(harness, monkeypatch):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    seeded = _load_rate_doc(tmp_path, engine, slug="cite-doc", pub_date="2026-09-11")
    _configure(
        monkeypatch, run_ids=[seeded["run_id"]], storage_root=seeded["staging"].storage_root
    )

    with SessionLocal() as session:
        user, company, event = _seed_company_event_impact(
            session, occurred_at=datetime(2026, 9, 15, tzinfo=timezone.utc)
        )
        user_id, company_id, event_id = user.id, company.id, event.id
        ctx = build_conversation_context(session, event_id=event_id, company_id=company_id)
        frag = ctx["bank_evidence"]["fragments_passed_to_provider"][0]
        fid = frag["fragment_id"]
        rev = frag["revision"]
        plain = frag["text_plain_for_validation"]
        text_kind = frag["text_kind"]

    # Valid citation
    provider = ScriptedProvider(
        citations=[
            {
                "fragment_id": fid,
                "revision": rev,
                "text_kind": text_kind,
                "quoted_text": plain if text_kind == "exact_quote" else None,
                "section_hint": "rates",
            }
        ],
        content="Ссылка на материал банка.",
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider
    )

    with SessionLocal() as session:
        from app.services.assistant.orchestrator import get_or_create_conversation

        user = session.get(User, user_id)
        conv, _ = get_or_create_conversation(
            session, user=user, company_id=company_id, event_id=event_id
        )
        out = post_message(
            session,
            conversation_id=conv.id,
            user=user,
            content="Что банк пишет про ставку?",
        )
        msg = out.assistant_message
        bank_blocks = [b for b in msg.blocks if b.type == "bank_evidence_list"]
        assert len(bank_blocks) == 1
        data = bank_blocks[0].data
        assert data["used"]
        assert data["used"][0]["fragment_id"] == fid
        assert data["used"][0]["revision"] == rev
        assert data["diagnostics"]["validated_ids"] == [fid]
        assert data["diagnostics"]["retrieved_count"] >= 1
        # Not auto-attributing all retrieved
        assert set(data["diagnostics"]["validated_ids"]).issubset(
            set(data["diagnostics"]["passed_to_provider_ids"])
        )
        assert provider.last_context is not None
        be = provider.last_context.get("bank_evidence") or {}
        assert be.get("available") is True

    # Fake ID rejected — not published as used
    provider2 = ScriptedProvider(
        citations=[{"fragment_id": "invented-id-999"}],
        content="Выдуманная ссылка",
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider2
    )
    with SessionLocal() as session:
        from app.services.assistant.orchestrator import get_or_create_conversation

        user = session.get(User, user_id)
        conv, _ = get_or_create_conversation(
            session, user=user, company_id=company_id, event_id=event_id
        )
        out2 = post_message(
            session,
            conversation_id=conv.id,
            user=user,
            content="Снова про ставку банка",
        )
        data2 = [b for b in out2.assistant_message.blocks if b.type == "bank_evidence_list"][
            0
        ].data
        assert data2["used"] == []
        assert data2["diagnostics"]["rejected"]
        assert data2["diagnostics"]["rejected"][0]["reason"] == "unknown_or_not_passed_fragment_id"


def test_tampered_exact_quote_rejected(harness, monkeypatch):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    seeded = _load_rate_doc(tmp_path, engine, slug="tamper-doc", pub_date="2026-09-11")
    _configure(
        monkeypatch, run_ids=[seeded["run_id"]], storage_root=seeded["staging"].storage_root
    )
    with SessionLocal() as session:
        user, company, event = _seed_company_event_impact(
            session, occurred_at=datetime(2026, 9, 15, tzinfo=timezone.utc)
        )
        user_id, company_id, event_id = user.id, company.id, event.id
        ctx = build_conversation_context(session, event_id=event_id, company_id=company_id)
        quote_frags = [
            f
            for f in ctx["bank_evidence"]["fragments_passed_to_provider"]
            if f.get("text_kind") == "exact_quote"
        ]
        assert quote_frags
        frag = quote_frags[0]
        frag_id, frag_rev = frag["fragment_id"], frag["revision"]

    provider = ScriptedProvider(
        citations=[
            {
                "fragment_id": frag_id,
                "revision": frag_rev,
                "quoted_text": "completely different invented quote",
            }
        ]
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider
    )
    with SessionLocal() as session:
        from app.services.assistant.orchestrator import get_or_create_conversation

        user = session.get(User, user_id)
        conv, _ = get_or_create_conversation(
            session, user=user, company_id=company_id, event_id=event_id
        )
        out = post_message(
            session, conversation_id=conv.id, user=user, content="Цитата банка"
        )
        data = [b for b in out.assistant_message.blocks if b.type == "bank_evidence_list"][
            0
        ].data
        assert data["used"] == []
        assert any(r["reason"] == "exact_quote_text_mismatch" for r in data["diagnostics"]["rejected"])


def test_empty_statuses_and_fetch_error_flag(harness, monkeypatch):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    # Not configured
    with SessionLocal() as session:
        user, company, event = _seed_company_event_impact(
            session, occurred_at=datetime(2026, 9, 15, tzinfo=timezone.utc)
        )
        ctx = build_conversation_context(session, event_id=event.id, company_id=company.id)
        assert ctx["bank_evidence"]["status"] == "integration_not_configured"
        assert ctx["bank_evidence"]["available"] is False

    # Technical error must not look like no_matching
    def _boom(*_a, **_k):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(
        "app.services.assistant.bank_evidence_context.collect_event_bank_evidence",
        _boom,
    )
    with SessionLocal() as session:
        event = session.scalars(select(Event)).first()
        block = build_bank_evidence_context_block(session, event=event)
        assert block["status"] == "fetch_error"
        assert block["fetch_error"]
        assert block["status"] != "no_matching_evidence"


def test_history_pins_revision_old_messages_untouched(harness, monkeypatch):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    seeded = _load_rate_doc(tmp_path, engine, slug="hist-doc", pub_date="2026-09-11")
    _configure(
        monkeypatch, run_ids=[seeded["run_id"]], storage_root=seeded["staging"].storage_root
    )
    with SessionLocal() as session:
        user, company, event = _seed_company_event_impact(
            session, occurred_at=datetime(2026, 9, 15, tzinfo=timezone.utc)
        )
        user_id, company_id, event_id = user.id, company.id, event.id
        ctx = build_conversation_context(session, event_id=event_id, company_id=company_id)
        frag = ctx["bank_evidence"]["fragments_passed_to_provider"][0]
        frag_id = frag["fragment_id"]
        old_rev = frag["revision"]

    provider = ScriptedProvider(
        citations=[{"fragment_id": frag_id, "revision": old_rev}]
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider
    )
    with SessionLocal() as session:
        from app.services.assistant.orchestrator import get_or_create_conversation
        from app.models.bank_materials import BankFragmentRegion

        user = session.get(User, user_id)
        conv, _ = get_or_create_conversation(
            session, user=user, company_id=company_id, event_id=event_id
        )
        out = post_message(
            session, conversation_id=conv.id, user=user, content="Ставка банка"
        )
        mid = out.assistant_message.id
        used_rev = [
            b for b in out.assistant_message.blocks if b.type == "bank_evidence_list"
        ][0].data["used"][0]["revision"]

        # Bump fragment revision in DB — history must keep old snapshot
        row = session.get(BankFragment, frag_id)
        newer = BankFragment(
            id=str(uuid.uuid4()),
            ocr_run_id=row.ocr_run_id,
            document_file_id=row.document_file_id,
            document_id=row.document_id,
            stable_key=row.stable_key,
            revision=old_rev + 1,
            kind=row.kind,
            primary_region_type=row.primary_region_type,
            content_type=row.content_type,
            content_type_status=row.content_type_status,
            page_number=row.page_number,
            ocr_text=row.ocr_text,
            cleaned_text=None,
            verified_transcript=(row.verified_transcript or "") + " NEW",
            summary_text=row.summary_text,
            verification_status=row.verification_status,
            ocr_correction_json=None,
            source_role=row.source_role,
            notes=None,
            supersedes_fragment_id=row.id,
            created_at=datetime.now(timezone.utc),
        )
        session.add(newer)
        session.flush()
        session.add(
            BankFragmentRegion(
                id=str(uuid.uuid4()),
                fragment_id=newer.id,
                ocr_run_id=row.ocr_run_id,
                page_number=1,
                sort_order=0,
                region_type="prose",
                bbox_left=1,
                bbox_top=1,
                bbox_width=10,
                bbox_height=10,
                coord_space="page_image_px",
                note=None,
            )
        )
        session.commit()

        stored = session.get(AssistantMessage, mid)
        assert stored is not None
        bank = next(b for b in (stored.blocks_json or []) if b.get("type") == "bank_evidence_list")
        assert bank["data"]["used"][0]["revision"] == used_rev == old_rev
        assert " NEW" not in (bank["data"]["used"][0].get("text") or "")
