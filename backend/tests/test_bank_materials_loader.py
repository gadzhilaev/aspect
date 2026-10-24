"""Bank materials loader: synthetic fixtures on temporary SQLite (FK ON)."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.jobs.import_bank_materials import main as cli_main
from app.models.bank_materials import (
    BankDocument,
    BankDocumentFile,
    BankFragment,
    BankFragmentRegion,
    BankOcrPage,
    BankOcrRun,
)
from app.services.bank_materials.eligibility import compute_fragment_eligibility
from app.services.bank_materials.load import (
    DocumentConflictError,
    IncompleteRunError,
    assert_bank_schema_ready,
    load_bank_document,
    run_bank_materials_load,
)
from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
from tests.test_bank_import_dry_run import _build_valid_corpus, _confirmed_fragment

ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@contextmanager
def _with_db_url(db_url: str):
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    get_settings.cache_clear()
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        get_settings.cache_clear()


def _sqlite_migrated():
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / "bank_load.db"
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    with _with_db_url(url):
        command.upgrade(_alembic_config(), "head")
    return tmp, engine, url


def _session(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _prepare(tmp_path: Path, **kwargs):
    ocr, pdf = _build_valid_corpus(tmp_path, **kwargs)
    staging = stage_corpus(input_dir=ocr, pdf_dir=pdf, staging_parent=tmp_path)
    plan, errs, _warns = build_prepared_document(
        staging.ocr_dir / kwargs.get("slug", "sample-doc"),
        input_dir=staging.ocr_dir,
        pdf_dir=staging.pdf_dir,
        storage_root=staging.storage_root,
    )
    assert plan is not None, errs
    assert not errs
    return staging, plan


def test_cli_load_requires_database_url():
    assert cli_main(["--load"]) == 2
    assert cli_main([]) == 2


def test_schema_not_ready_without_tables(tmp_path: Path):
    empty = tmp_path / "empty.db"
    url = f"sqlite:///{empty.as_posix()}"
    engine = create_engine(url)
    with pytest.raises(Exception) as ei:
        assert_bank_schema_ready(engine)
    assert "schema" in str(ei.value).lower() or "missing" in str(ei.value).lower()
    engine.dispose()


def test_successful_load_and_idempotent_skip(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        staging, plan = _prepare(
            tmp_path,
            fragments=[_confirmed_fragment()],
        )
        with _session(engine) as session:
            r1 = load_bank_document(session, plan)
            session.commit()
        assert r1.status == "inserted"
        assert r1.eligibility_after_read["exact_quote"] == 1
        assert r1.eligibility_after_read["ai_evidence"] == 1

        with _session(engine) as session:
            docs = session.scalars(select(BankDocument)).all()
            files = session.scalars(select(BankDocumentFile)).all()
            runs = session.scalars(select(BankOcrRun)).all()
            pages = session.scalars(select(BankOcrPage)).all()
            frags = session.scalars(select(BankFragment)).all()
            regs = session.scalars(select(BankFragmentRegion)).all()
            n1 = (len(docs), len(files), len(runs), len(pages), len(frags), len(regs))

        with _session(engine) as session:
            r2 = load_bank_document(session, plan)
            session.commit()
        assert r2.status == "identical_skip"

        with _session(engine) as session:
            n2 = (
                session.scalar(select(func.count()).select_from(BankDocument)),
                session.scalar(select(func.count()).select_from(BankDocumentFile)),
                session.scalar(select(func.count()).select_from(BankOcrRun)),
                session.scalar(select(func.count()).select_from(BankOcrPage)),
                session.scalar(select(func.count()).select_from(BankFragment)),
                session.scalar(select(func.count()).select_from(BankFragmentRegion)),
            )
        assert n1 == n2
    finally:
        engine.dispose()
        tmp.cleanup()


def test_content_conflict_same_revision(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        staging, plan = _prepare(tmp_path, fragments=[_confirmed_fragment()])
        with _session(engine) as session:
            load_bank_document(session, plan)
            session.commit()

        # Mutate staged fragment text under same revision
        frag_path = staging.ocr_dir / "sample-doc" / "fragments.json"
        data = json.loads(frag_path.read_text(encoding="utf-8"))
        data["fragments"][0]["exact_quote"] = "CHANGED TEXT"
        data["fragments"][0]["ocr_text"] = "CHANGED TEXT"
        frag_path.write_text(json.dumps(data), encoding="utf-8")
        # Refresh staging SHA for that file so prepare still works from disk
        plan2, errs, _ = build_prepared_document(
            staging.ocr_dir / "sample-doc",
            input_dir=staging.ocr_dir,
            pdf_dir=staging.pdf_dir,
            storage_root=staging.storage_root,
        )
        assert plan2 is not None and not errs

        with _session(engine) as session:
            with pytest.raises(DocumentConflictError) as ei:
                load_bank_document(session, plan2)
            session.rollback()
        assert ei.value.code == "fragment_content_conflict"
    finally:
        engine.dispose()
        tmp.cleanup()


def test_new_revision_preserves_previous(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        f1 = _confirmed_fragment(id="quote_v", revision=1, exact_quote="v1", ocr_text="v1")
        staging, plan = _prepare(tmp_path, fragments=[f1])
        with _session(engine) as session:
            load_bank_document(session, plan)
            session.commit()

        f2 = _confirmed_fragment(
            id="quote_v",
            revision=2,
            exact_quote="v2",
            ocr_text="v2",
            supersedes_stable_key="quote_v",
            supersedes_revision=1,
        )
        # Plan must include both revisions
        frag_path = staging.ocr_dir / "sample-doc" / "fragments.json"
        frag_path.write_text(
            json.dumps({"schema_version": 2, "fragments": [f1, f2]}, ensure_ascii=False),
            encoding="utf-8",
        )
        plan2, errs, _ = build_prepared_document(
            staging.ocr_dir / "sample-doc",
            input_dir=staging.ocr_dir,
            pdf_dir=staging.pdf_dir,
            storage_root=staging.storage_root,
        )
        assert plan2 is not None and not errs

        with _session(engine) as session:
            r = load_bank_document(session, plan2)
            session.commit()
        assert r.status == "inserted"
        assert r.code == "revision_appended"

        with _session(engine) as session:
            frags = session.scalars(
                select(BankFragment).order_by(BankFragment.revision)
            ).all()
            assert len(frags) == 2
            assert frags[0].verified_transcript == "v1"
            assert frags[1].verified_transcript == "v2"
            assert frags[1].supersedes_fragment_id == frags[0].id
            assert frags[0].stable_key == frags[1].stable_key
    finally:
        engine.dispose()
        tmp.cleanup()


def test_new_ocr_run_keeps_previous(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        staging, plan = _prepare(tmp_path, fragments=[_confirmed_fragment()])
        with _session(engine) as session:
            load_bank_document(session, plan)
            session.commit()

        # Change fingerprint via page meta psm_used (affects canonical fingerprint)
        doc_dir = staging.ocr_dir / "sample-doc"
        for meta_path in doc_dir.glob("page_*_meta.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["ocr"]["psm_used"] = 6
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
        man = json.loads((doc_dir / "manifest.json").read_text(encoding="utf-8"))
        man["fingerprint"]["psm"] = 6
        (doc_dir / "manifest.json").write_text(json.dumps(man), encoding="utf-8")

        plan2, errs, _ = build_prepared_document(
            doc_dir,
            input_dir=staging.ocr_dir,
            pdf_dir=staging.pdf_dir,
            storage_root=staging.storage_root,
        )
        assert plan2 is not None and not errs
        assert plan2.fingerprint_hash != plan.fingerprint_hash

        with _session(engine) as session:
            r = load_bank_document(session, plan2)
            session.commit()
        assert r.status == "inserted"

        with _session(engine) as session:
            runs = session.scalars(select(BankOcrRun)).all()
            assert len(runs) == 2
            frags = session.scalars(select(BankFragment)).all()
            assert len(frags) == 2
    finally:
        engine.dispose()
        tmp.cleanup()


def test_partial_run_does_not_skip(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        staging, plan = _prepare(tmp_path, fragments=[_confirmed_fragment()], pages=2)
        with _session(engine) as session:
            load_bank_document(session, plan)
            session.commit()

        # Force incomplete run via SQL (no ORM cascade / self-FK ordering issues).
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM bank_fragment_regions"))
            conn.execute(text("DELETE FROM bank_fragments"))
            conn.execute(
                text(
                    "DELETE FROM bank_ocr_pages WHERE page_number = ("
                    "SELECT MIN(page_number) FROM bank_ocr_pages)"
                )
            )

        with _session(engine) as session:
            with pytest.raises(IncompleteRunError) as ei:
                load_bank_document(session, plan)
            session.rollback()
        assert ei.value.code == "incomplete_or_partial_ocr_run"
    finally:
        engine.dispose()
        tmp.cleanup()


def test_rollback_on_error_after_partial_children(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        staging, plan = _prepare(tmp_path, fragments=[_confirmed_fragment()])
        # Force failure mid-flight by making a second conflicting slug file sha owned by
        # another document inserted first, then loading plan that conflicts on metadata.
        with _session(engine) as session:
            load_bank_document(session, plan)
            session.commit()

        # Attempt to load same slug with different publication → conflict + rollback
        man_path = staging.ocr_dir / "sample-doc" / "manifest.json"
        man = json.loads(man_path.read_text(encoding="utf-8"))
        man["document_identity"]["confirmed_publication_date"] = "2026-01-01"
        man_path.write_text(json.dumps(man), encoding="utf-8")
        plan2, errs, _ = build_prepared_document(
            staging.ocr_dir / "sample-doc",
            input_dir=staging.ocr_dir,
            pdf_dir=staging.pdf_dir,
            storage_root=staging.storage_root,
        )
        assert plan2 is not None and not errs

        with _session(engine) as session:
            before_docs = session.scalar(select(func.count()).select_from(BankDocument))
            with pytest.raises(DocumentConflictError):
                load_bank_document(session, plan2)
            session.rollback()
            after_docs = session.scalar(select(func.count()).select_from(BankDocument))
            after_files = session.scalar(select(func.count()).select_from(BankDocumentFile))
        assert before_docs == after_docs == 1
        assert after_files == 1
    finally:
        engine.dispose()
        tmp.cleanup()


def test_dates_day_month_unknown_and_null_bbox(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        # day
        ocr1, pdf1 = _build_valid_corpus(
            tmp_path / "day",
            slug="doc-day",
            fragments=[
                _confirmed_fragment(
                    id="q",
                    regions=[{"region_type": "prose", "bbox": None}],
                )
            ],
        )
        # Fix confirmed fragment to allow null bbox — map_fragment allows null bbox
        frag = {
            "id": "q_null_bbox",
            "kind": "exact_quote",
            "content_type": "fact",
            "content_type_status": "confirmed",
            "primary_region_type": "prose",
            "page": 1,
            "regions": [{"region_type": "prose", "bbox": None}],
            "ocr_text": "hello",
            "exact_quote": "hello",
            "verification_status": "verified",
        }
        (ocr1 / "doc-day" / "fragments.json").write_text(
            json.dumps({"schema_version": 2, "fragments": [frag]}), encoding="utf-8"
        )

        staging = stage_corpus(input_dir=ocr1, pdf_dir=pdf1, staging_parent=tmp_path)
        plan, errs, _ = build_prepared_document(
            staging.ocr_dir / "doc-day",
            input_dir=staging.ocr_dir,
            pdf_dir=staging.pdf_dir,
            storage_root=staging.storage_root,
        )
        assert plan is not None and not errs
        assert plan.publication.precision == "day"
        assert plan.fragments[0].regions[0].bbox_left is None

        with _session(engine) as session:
            load_bank_document(session, plan)
            session.commit()
            doc = session.scalars(select(BankDocument)).one()
            assert doc.publication_date_precision == "day"
            assert doc.publication_date is not None
            reg = session.scalars(select(BankFragmentRegion)).one()
            assert reg.bbox_left is None

        # month
        ocr2, pdf2 = _build_valid_corpus(
            tmp_path / "month",
            slug="doc-month",
            identity={
                "confirmed_title": "Month Doc",
                "confirmed_title_status": "confirmed",
                "confirmed_publication_date": "2026-08",
                "confirmed_publication_date_status": "confirmed",
                "confirmed_publication_date_display": "АВГУСТ 2026",
                "period_covered": None,
                "period_covered_status": "unknown",
                "topics": [],
                "topics_status": "unknown",
            },
            fragments=[_confirmed_fragment(id="m1")],
        )
        result = run_bank_materials_load(
            input_dir=ocr2,
            pdf_dir=pdf2,
            database_url=url,
            report_dir=tmp_path / "reports_month",
            staging_parent=tmp_path,
        )
        assert result.ok or result.inserted >= 1
        with _session(engine) as session:
            doc = session.scalar(
                select(BankDocument).where(BankDocument.slug == "doc-month")
            )
            assert doc is not None
            assert doc.publication_date_precision == "month"
            assert doc.publication_date is None
            assert doc.publication_year == 2026
            assert doc.publication_month == 8

        # unknown
        ocr3, pdf3 = _build_valid_corpus(
            tmp_path / "unk",
            slug="doc-unk",
            identity={
                "confirmed_title": None,
                "confirmed_title_status": "unknown",
                "confirmed_publication_date": None,
                "confirmed_publication_date_status": "unknown",
                "period_covered_status": "unknown",
                "topics": [],
                "topics_status": "unknown",
            },
            fragments=[_confirmed_fragment(id="u1")],
        )
        result = run_bank_materials_load(
            input_dir=ocr3,
            pdf_dir=pdf3,
            database_url=url,
            report_dir=tmp_path / "reports_unk",
            staging_parent=tmp_path,
        )
        assert result.inserted >= 1
        with _session(engine) as session:
            doc = session.scalar(
                select(BankDocument).where(BankDocument.slug == "doc-unk")
            )
            assert doc.publication_date_precision == "unknown"
            assert doc.publication_date is None
            assert doc.publication_year is None
    finally:
        engine.dispose()
        tmp.cleanup()


def test_no_trust_elevation_after_db_read(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        # Default corpus fragment lacks primary_region_type / content_type_status
        staging, plan = _prepare(tmp_path)
        assert plan.fragments[0].primary_region_type == "unverified"
        assert plan.fragments[0].content_type_status == "unknown"
        assert plan.dry_run_eligibility["ai_evidence"] == 0

        with _session(engine) as session:
            r = load_bank_document(session, plan)
            session.commit()
        assert r.eligibility_after_read == r.dry_run_eligibility
        assert r.eligibility_after_read["ai_evidence"] == 0
        assert r.eligibility_after_read["exact_quote"] == 0
        assert r.eligibility_after_read["search"] == 1

        with _session(engine) as session:
            frag = session.scalars(select(BankFragment)).one()
            assert frag.primary_region_type == "unverified"
            assert frag.content_type_status == "unknown"
            assert frag.verification_status == "verified"
            elig = compute_fragment_eligibility(
                verification_status=frag.verification_status,
                kind=frag.kind,
                primary_region_type=frag.primary_region_type,
                content_type=frag.content_type,
                content_type_status=frag.content_type_status,
                verified_transcript=frag.verified_transcript,
                summary_text=frag.summary_text,
                region_count=1,
            )
            assert not elig.eligible_ai_evidence
            assert not elig.eligible_exact_quote
    finally:
        engine.dispose()
        tmp.cleanup()


def test_orchestrator_partial_success_and_pipeline(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        ocr, pdf = _build_valid_corpus(
            tmp_path / "corp",
            slug="ok-doc",
            fragments=[_confirmed_fragment()],
        )
        # Second broken doc: missing pdf
        bad = ocr / "bad-doc"
        bad.mkdir()
        (bad / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "source_filename": "missing.pdf",
                    "source_sha256": "0" * 64,
                    "page_count": 1,
                    "processing_status": "complete",
                    "fingerprint": {
                        "schema_version": 2,
                        "source_sha256": "0" * 64,
                        "tesseract_version_line": "tesseract v5",
                        "lang": "rus+eng",
                        "psm": 3,
                        "preserve_interword_spaces": True,
                        "eng_traineddata_sha256": "a" * 64,
                        "rus_traineddata_sha256": "b" * 64,
                    },
                    "document_identity": {},
                    "pages": [],
                }
            ),
            encoding="utf-8",
        )
        result = run_bank_materials_load(
            input_dir=ocr,
            pdf_dir=pdf,
            database_url=url,
            report_dir=tmp_path / "reports",
            staging_parent=tmp_path,
        )
        # Preflight should fail on bad doc → no load
        assert result.status == "preflight_failed"
        assert result.ok is False
    finally:
        engine.dispose()
        tmp.cleanup()


def test_run_load_cli_with_temp_db(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        ocr, pdf = _build_valid_corpus(
            tmp_path,
            fragments=[_confirmed_fragment()],
        )
        code = cli_main(
            [
                "--load",
                "--database-url",
                url,
                "--input-dir",
                str(ocr),
                "--pdf-dir",
                str(pdf),
                "--report-dir",
                str(tmp_path / "reports"),
            ]
        )
        assert code == 0
        with _session(engine) as session:
            assert session.scalar(select(func.count()).select_from(BankDocument)) == 1
            frag = session.scalars(select(BankFragment)).one()
            assert frag.primary_region_type == "prose"
            assert frag.content_type_status == "confirmed"
    finally:
        engine.dispose()
        tmp.cleanup()
