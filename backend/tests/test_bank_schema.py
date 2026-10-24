"""Bank materials schema: migrations + integrity on temporary DBs only."""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    BankDocument,
    BankDocumentFile,
    BankFragment,
    BankFragmentRegion,
    BankOcrPage,
    BankOcrRun,
    Company,
)
from app.services.bank_materials.eligibility import compute_fragment_eligibility
from tests._alembic_util import (
    ALEMBIC_HEAD,
    alembic_config,
    assert_head_schema,
    sqlite_engine,
    temp_sqlite_path,
    with_db_url,
)

BANK_TABLES = {
    "bank_documents",
    "bank_document_files",
    "bank_ocr_runs",
    "bank_ocr_pages",
    "bank_fragments",
    "bank_fragment_regions",
}


def _sqlite_engine(path: Path):
    engine, url = sqlite_engine(path)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine, url

def _uid() -> str:
    return str(uuid.uuid4())


def _doc(session: Session, slug: str, **kwargs) -> BankDocument:
    defaults = dict(
        id=_uid(),
        slug=slug,
        title=None,
        title_status="unknown",
        publication_date=None,
        publication_year=None,
        publication_month=None,
        publication_date_precision="unknown",
        publication_date_display=None,
        period_covered=None,
        period_covered_status="unknown",
        topics_json=[],
        topics_status="unknown",
        staleness_note=None,
        is_current_stance=False,
        document_visual_status="unverified",
    )
    defaults.update(kwargs)
    row = BankDocument(**defaults)
    session.add(row)
    session.flush()
    return row


def _file(
    session: Session,
    doc: BankDocument,
    *,
    sha: str,
    supersedes: BankDocumentFile | None = None,
) -> BankDocumentFile:
    row = BankDocumentFile(
        id=_uid(),
        document_id=doc.id,
        sha256=sha,
        original_filename=f"{doc.slug}.pdf",
        page_count=2,
        byte_size=1000,
        storage_key=f"bank/{doc.slug}/{sha[:12]}.pdf",
        supersedes_file_id=supersedes.id if supersedes else None,
        imported_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return row


def _run(session: Session, file: BankDocumentFile, fingerprint: str) -> BankOcrRun:
    row = BankOcrRun(
        id=_uid(),
        document_file_id=file.id,
        fingerprint_hash=fingerprint,
        schema_version=2,
        tesseract_version_line="tesseract v5.4.0.20240606",
        lang="rus+eng",
        psm_default=3,
        preserve_interword_spaces=True,
        eng_traineddata_sha256="a" * 64,
        rus_traineddata_sha256="b" * 64,
        params_json={"schema_version": 2},
        processing_status="complete",
        pages_ok_json=[1, 2],
        pages_failed_json=[],
        artifact_root_key=f"bank/ocr/{file.sha256[:12]}",
    )
    session.add(row)
    session.flush()
    return row


def _page(session: Session, run: BankOcrRun, page: int) -> BankOcrPage:
    row = BankOcrPage(
        id=_uid(),
        ocr_run_id=run.id,
        page_number=page,
        processing_status="ok",
        width=1000,
        height=1400,
        visual_verification_status="verified_spot_check",
        content_regions_json=[{"type": "prose", "status": "verified_ok"}],
        visual_checks_json={},
        mean_confidence=95.0,
    )
    session.add(row)
    session.flush()
    return row


def _sha(label: str) -> str:
    import hashlib

    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _chain(session: Session, slug: str = "doc-a"):
    doc = _doc(
        session,
        slug,
        title="Test",
        title_status="confirmed",
        publication_date=date(2026, 9, 11),
        publication_year=2026,
        publication_month=9,
        publication_date_precision="day",
        publication_date_display="11 сентября 2026 г.",
        period_covered_status="confirmed",
        topics_status="confirmed",
        document_visual_status="partial_spot_check",
    )
    file = _file(session, doc, sha=_sha(f"pdf:{slug}"))
    run = _run(session, file, fingerprint=_sha(f"ocr:{slug}"))
    p1 = _page(session, run, 1)
    p2 = _page(session, run, 2)
    return doc, file, run, p1, p2


@pytest.fixture
def sqlite_migrated():
    with temp_sqlite_path("bank.db") as db_path:
        engine, url = _sqlite_engine(db_path)
        try:
            with with_db_url(url):
                command.upgrade(alembic_config(), "head")
                SessionLocal = sessionmaker(bind=engine)
                yield engine, SessionLocal
        finally:
            engine.dispose()


def test_upgrade_head_from_scratch_sqlite():
    with temp_sqlite_path("bank_from_scratch.db") as db_path:
        engine, url = _sqlite_engine(db_path)
        try:
            with with_db_url(url):
                command.upgrade(alembic_config(), "head")
                assert BANK_TABLES.issubset(set(inspect(engine).get_table_names()))
                assert_head_schema(engine)
        finally:
            engine.dispose()


def test_upgrade_from_006_preserves_company_sqlite():
    with temp_sqlite_path("bank_from_006.db") as db_path:
        engine, url = _sqlite_engine(db_path)
        try:
            with with_db_url(url):
                command.upgrade(alembic_config(), "006")
                SessionLocal = sessionmaker(bind=engine)
                company_id = _uid()
                with SessionLocal() as session:
                    session.add(
                        Company(
                            id=company_id,
                            name="Preserve Bank Mig",
                            profile_status="draft",
                            digital_twin_status="not_built",
                            digital_twin_coverage=0.0,
                            is_demo=False,
                        )
                    )
                    session.commit()

                command.upgrade(alembic_config(), "head")
                with SessionLocal() as session:
                    company = session.get(Company, company_id)
                    assert company is not None
                    assert company.name == "Preserve Bank Mig"
                assert BANK_TABLES.issubset(set(inspect(engine).get_table_names()))
                assert_head_schema(engine)
        finally:
            engine.dispose()


def test_downgrade_007_then_reupgrade_sqlite():
    """Round-trip through 008 SQLite DROP COLUMN subscription_id + re-upgrade to head."""
    with temp_sqlite_path("bank_down.db") as db_path:
        engine, url = _sqlite_engine(db_path)
        try:
            with with_db_url(url):
                cfg = alembic_config()
                command.upgrade(cfg, "head")
                command.downgrade(cfg, "006")
                tables = set(inspect(engine).get_table_names())
                assert "bank_documents" not in tables
                assert "case_snapshots" in tables
                with engine.connect() as conn:
                    ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                assert ver == "006"
                command.upgrade(cfg, "head")
                assert BANK_TABLES.issubset(set(inspect(engine).get_table_names()))
                assert_head_schema(engine)
                assert ALEMBIC_HEAD == "011"
        finally:
            engine.dispose()

def test_unique_pdf_sha_and_ocr_fingerprint(sqlite_migrated):
    _engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        doc, file, run, _p1, _p2 = _chain(session)
        session.commit()

        with pytest.raises(IntegrityError):
            with SessionLocal() as s2:
                _file(s2, doc, sha=file.sha256)
                s2.commit()

        with pytest.raises(IntegrityError):
            with SessionLocal() as s2:
                # reload ids
                doc2 = s2.get(BankDocument, doc.id)
                file2 = s2.get(BankDocumentFile, file.id)
                assert doc2 and file2
                _run(s2, file2, fingerprint=run.fingerprint_hash)
                s2.commit()


def test_fragment_revisions_preserve_old_text(sqlite_migrated):
    _engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        doc, file, run, _p1, _p2 = _chain(session)
        f1 = BankFragment(
            id=_uid(),
            ocr_run_id=run.id,
            document_file_id=file.id,
            document_id=doc.id,
            stable_key="policy_rate_rhetoric",
            revision=1,
            kind="exact_quote",
            primary_region_type="prose",
            content_type="interpretation",
            content_type_status="confirmed",
            page_number=1,
            ocr_text="риторика cTana жестче",
            verified_transcript="риторика cTana жестче",
            verification_status="verified",
        )
        session.add(f1)
        session.flush()
        f2 = BankFragment(
            id=_uid(),
            ocr_run_id=run.id,
            document_file_id=file.id,
            document_id=doc.id,
            stable_key="policy_rate_rhetoric",
            revision=2,
            kind="exact_quote",
            primary_region_type="prose",
            content_type="interpretation",
            content_type_status="confirmed",
            page_number=1,
            ocr_text="риторика cTana жестче",
            verified_transcript="риторика стала жестче",
            verification_status="verified",
            ocr_correction_json={"from": "cTana", "to": "стала"},
            supersedes_fragment_id=f1.id,
        )
        session.add(f2)
        session.commit()

    with SessionLocal() as session:
        rows = (
            session.query(BankFragment)
            .filter_by(stable_key="policy_rate_rhetoric")
            .order_by(BankFragment.revision)
            .all()
        )
        assert len(rows) == 2
        assert rows[0].verified_transcript == "риторика cTana жестче"
        assert rows[1].verified_transcript == "риторика стала жестче"
        assert rows[1].supersedes_fragment_id == rows[0].id

        with pytest.raises(IntegrityError):
            session.add(
                BankFragment(
                    id=_uid(),
                    ocr_run_id=rows[0].ocr_run_id,
                    document_file_id=rows[0].document_file_id,
                    document_id=rows[0].document_id,
                    stable_key="policy_rate_rhetoric",
                    revision=1,
                    kind="exact_quote",
                    primary_region_type="prose",
                    content_type="interpretation",
                    content_type_status="confirmed",
                    page_number=1,
                    verified_transcript="dup",
                    verification_status="verified",
                )
            )
            session.commit()


def test_rejects_cross_document_and_cross_run_links(sqlite_migrated):
    _engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        doc_a, file_a, run_a, _p1a, _p2a = _chain(session, "doc-a")
        doc_b, file_b, run_b, _p1b, _p2b = _chain(session, "doc-b")
        session.commit()

        # Fragment claiming doc_b while run belongs to file_a
        with pytest.raises(IntegrityError):
            with SessionLocal() as s2:
                s2.add(
                    BankFragment(
                        id=_uid(),
                        ocr_run_id=run_a.id,
                        document_file_id=file_a.id,
                        document_id=doc_b.id,
                        stable_key="x",
                        revision=1,
                        kind="exact_quote",
                        primary_region_type="prose",
                        content_type="fact",
                        content_type_status="confirmed",
                        page_number=1,
                        verified_transcript="t",
                        verification_status="verified",
                    )
                )
                s2.commit()

        # Region on page of another run
        with SessionLocal() as s2:
            frag = BankFragment(
                id=_uid(),
                ocr_run_id=run_a.id,
                document_file_id=file_a.id,
                document_id=doc_a.id,
                stable_key="ok",
                revision=1,
                kind="summary",
                primary_region_type="prose",
                content_type="fact",
                content_type_status="confirmed",
                page_number=1,
                summary_text="s",
                verification_status="verified",
            )
            s2.add(frag)
            s2.flush()
            with pytest.raises(IntegrityError):
                s2.add(
                    BankFragmentRegion(
                        id=_uid(),
                        fragment_id=frag.id,
                        ocr_run_id=run_b.id,
                        page_number=1,
                        sort_order=0,
                        region_type="prose",
                    )
                )
                s2.commit()

        # supersedes across documents/stable_keys blocked by composite FK
        with SessionLocal() as s2:
            fa = BankFragment(
                id=_uid(),
                ocr_run_id=run_a.id,
                document_file_id=file_a.id,
                document_id=doc_a.id,
                stable_key="key-a",
                revision=1,
                kind="exact_quote",
                primary_region_type="prose",
                content_type="fact",
                content_type_status="confirmed",
                page_number=1,
                verified_transcript="a",
                verification_status="verified",
            )
            fb = BankFragment(
                id=_uid(),
                ocr_run_id=run_b.id,
                document_file_id=file_b.id,
                document_id=doc_b.id,
                stable_key="key-b",
                revision=1,
                kind="exact_quote",
                primary_region_type="prose",
                content_type="fact",
                content_type_status="confirmed",
                page_number=1,
                verified_transcript="b",
                verification_status="verified",
            )
            s2.add_all([fa, fb])
            s2.flush()
            with pytest.raises(IntegrityError):
                s2.add(
                    BankFragment(
                        id=_uid(),
                        ocr_run_id=run_a.id,
                        document_file_id=file_a.id,
                        document_id=doc_a.id,
                        stable_key="key-a",
                        revision=2,
                        kind="exact_quote",
                        primary_region_type="prose",
                        content_type="fact",
                        content_type_status="confirmed",
                        page_number=1,
                        verified_transcript="a2",
                        verification_status="verified",
                        supersedes_fragment_id=fb.id,
                    )
                )
                s2.commit()

        # supersedes_file across documents
        with pytest.raises(IntegrityError):
            with SessionLocal() as s2:
                da = s2.get(BankDocument, doc_a.id)
                fb = s2.get(BankDocumentFile, file_b.id)
                assert da and fb
                _file(s2, da, sha="9" * 64, supersedes=fb)
                s2.commit()


def test_date_and_bbox_constraints(sqlite_migrated):
    _engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        # month precision must keep publication_date NULL
        with pytest.raises(IntegrityError):
            _doc(
                session,
                "bad-month",
                publication_date=date(2026, 8, 1),
                publication_year=2026,
                publication_month=8,
                publication_date_precision="month",
            )
            session.commit()
        session.rollback()

        with pytest.raises(IntegrityError):
            _doc(
                session,
                "bad-month-num",
                publication_year=2026,
                publication_month=13,
                publication_date_precision="month",
            )
            session.commit()
        session.rollback()

        ok = _doc(
            session,
            "gold-month",
            title="Обзор рынка золота",
            title_status="confirmed",
            publication_year=2026,
            publication_month=8,
            publication_date_precision="month",
            publication_date_display="АВГУСТ 2026",
            period_covered_status="confirmed",
            topics_status="confirmed",
            document_visual_status="partial_spot_check",
        )
        assert ok.publication_date is None
        session.commit()

    with SessionLocal() as session:
        doc, file, run, _p1, _p2 = _chain(session, "bbox-doc")
        frag = BankFragment(
            id=_uid(),
            ocr_run_id=run.id,
            document_file_id=file.id,
            document_id=doc.id,
            stable_key="r1",
            revision=1,
            kind="exact_quote",
            primary_region_type="prose",
            content_type="fact",
            content_type_status="confirmed",
            page_number=1,
            verified_transcript="x",
            verification_status="verified",
        )
        session.add(frag)
        session.commit()
        frag_id, run_id = frag.id, run.id

    with SessionLocal() as session:
        with pytest.raises(IntegrityError):
            session.add(
                BankFragmentRegion(
                    id=_uid(),
                    fragment_id=frag_id,
                    ocr_run_id=run_id,
                    page_number=1,
                    sort_order=0,
                    region_type="prose",
                    bbox_left=1,
                    bbox_top=None,
                    bbox_width=10,
                    bbox_height=10,
                )
            )
            session.commit()

    with SessionLocal() as session:
        session.add(
            BankFragmentRegion(
                id=_uid(),
                fragment_id=frag_id,
                ocr_run_id=run_id,
                page_number=1,
                sort_order=0,
                region_type="prose",
                bbox_left=109,
                bbox_top=411,
                bbox_width=1155,
                bbox_height=47,
            )
        )
        session.commit()


def test_eligibility_matrix():
    # verified prose exact quote
    e = compute_fragment_eligibility(
        verification_status="verified",
        kind="exact_quote",
        primary_region_type="prose",
        content_type="fact",
        content_type_status="confirmed",
        verified_transcript="ЦБ оставил ставку 14,0%",
        summary_text=None,
        region_count=1,
        page_visual_verification_status="verified_spot_check",
        mean_confidence=99.0,
    )
    assert e.eligible_search and e.eligible_ai_evidence and e.eligible_exact_quote
    assert not e.evidence_as_summary_only

    # verified summary — evidence as summary only
    e = compute_fragment_eligibility(
        verification_status="verified",
        kind="summary",
        primary_region_type="prose",
        content_type="interpretation",
        content_type_status="confirmed",
        verified_transcript=None,
        summary_text="Банк мониторит кредитование.",
        region_count=1,
    )
    assert e.eligible_search and e.eligible_ai_evidence
    assert not e.eligible_exact_quote
    assert e.evidence_as_summary_only

    # needs_reverification — search only
    e = compute_fragment_eligibility(
        verification_status="needs_reverification",
        kind="exact_quote",
        primary_region_type="prose",
        content_type="fact",
        content_type_status="confirmed",
        verified_transcript="text",
        summary_text=None,
        region_count=1,
        mean_confidence=99.0,
    )
    assert e.eligible_search
    assert not e.eligible_ai_evidence and not e.eligible_exact_quote

    # high confidence + spot-check page do not unlock quote for unverified
    e = compute_fragment_eligibility(
        verification_status="unverified",
        kind="exact_quote",
        primary_region_type="prose",
        content_type="fact",
        content_type_status="confirmed",
        verified_transcript="text",
        summary_text=None,
        region_count=1,
        page_visual_verification_status="verified_spot_check",
        mean_confidence=99.9,
    )
    assert e.eligible_search
    assert not e.eligible_ai_evidence and not e.eligible_exact_quote

    # table blocked
    e = compute_fragment_eligibility(
        verification_status="verified",
        kind="exact_quote",
        primary_region_type="table",
        content_type="fact",
        content_type_status="confirmed",
        verified_transcript="14,0%",
        summary_text=None,
        region_count=1,
    )
    assert not e.eligible_search and not e.eligible_ai_evidence and not e.eligible_exact_quote

    # contradictory exact_quote without transcript
    e = compute_fragment_eligibility(
        verification_status="verified",
        kind="exact_quote",
        primary_region_type="prose",
        content_type="fact",
        content_type_status="confirmed",
        verified_transcript="  ",
        summary_text=None,
        region_count=1,
    )
    assert e.eligible_search
    assert not e.eligible_ai_evidence and not e.eligible_exact_quote

    # unconfirmed content_type blocks AI/quote
    e = compute_fragment_eligibility(
        verification_status="verified",
        kind="exact_quote",
        primary_region_type="prose",
        content_type="fact",
        content_type_status="unconfirmed",
        verified_transcript="ok",
        summary_text=None,
        region_count=1,
    )
    assert e.eligible_search
    assert not e.eligible_ai_evidence and not e.eligible_exact_quote

    # verified without regions — search only
    e = compute_fragment_eligibility(
        verification_status="verified",
        kind="exact_quote",
        primary_region_type="prose",
        content_type="fact",
        content_type_status="confirmed",
        verified_transcript="ok",
        summary_text=None,
        region_count=0,
    )
    assert e.eligible_search
    assert not e.eligible_ai_evidence and not e.eligible_exact_quote


def test_postgres_bank_schema_optional():
    db_url = os.getenv("ALEMBIC_POSTGRES_URL")
    if not db_url:
        pytest.skip("PostgreSQL not checked: ALEMBIC_POSTGRES_URL unset")
    pytest.skip("Use ALEMBIC_POSTGRES_URL via test_alembic_smoke for disposable _test DB")
