"""QA fragment revision apply: synthetic SQLite with FK ON."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.jobs.apply_bank_qa_revisions import main as qa_cli_main
from app.models.bank_materials import BankFragment, BankFragmentRegion
from app.services.bank_materials.apply_qa_revisions import (
    QaBindingError,
    QaConflictError,
    QaPartialStateError,
    apply_qa_revisions,
    load_qa_artifact,
    run_apply_qa_revisions,
)
from app.services.bank_materials.fragment_revision import (
    get_fragment_by_id,
    get_latest_fragment,
    select_latest_with_eligibility,
)
from app.services.bank_materials.load import load_bank_document
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
    path = Path(tmp.name) / "qa.db"
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


def _seed_doc(tmp_path: Path, engine, *, slug: str = "qa-doc"):
    """Load one document with three rev1 fragments (unverified trust, like corpus)."""
    fragments = [
        {
            "id": "policy_rate_cb_decision",
            "kind": "exact_quote",
            "content_type": "fact",
            "page": 1,
            "regions": [{"bbox": {"left": 10, "top": 10, "width": 50, "height": 20}}],
            "ocr_text": "decision ocr",
            "exact_quote": "decision ocr",
            "verification_status": "verified",
        },
        {
            "id": "policy_rate_rhetoric",
            "kind": "exact_quote",
            "content_type": "interpretation",
            "page": 1,
            "regions": [{"bbox": {"left": 10, "top": 40, "width": 50, "height": 20}}],
            "ocr_text": "rhetoric cTana",
            "exact_quote": "rhetoric became tougher",
            "verification_status": "verified",
        },
        {
            "id": "policy_rate_bank_forecast",
            "kind": "exact_quote",
            "content_type": "forecast",
            "page": 1,
            "regions": [{"bbox": {"left": 10, "top": 70, "width": 50, "height": 20}}],
            "ocr_text": "forecast ellipsis…",
            "exact_quote": "forecast ellipsis…",
            "verification_status": "verified",
        },
    ]
    ocr, pdf = _build_valid_corpus(tmp_path / "corp", slug=slug, pages=1, fragments=fragments)
    staging = stage_corpus(input_dir=ocr, pdf_dir=pdf, staging_parent=tmp_path)
    plan, errs, _ = build_prepared_document(
        staging.ocr_dir / slug,
        input_dir=staging.ocr_dir,
        pdf_dir=staging.pdf_dir,
        storage_root=staging.storage_root,
    )
    assert plan is not None and not errs
    with _session(engine) as session:
        r = load_bank_document(session, plan)
        session.commit()
    assert r.status == "inserted"
    return staging, plan


def _qa_artifact(plan, *, out: Path, mutate=None) -> Path:
    revs = [
        {
            "stable_key": "policy_rate_cb_decision",
            "revision": 2,
            "supersedes_stable_key": "policy_rate_cb_decision",
            "supersedes_revision": 1,
            "kind": "exact_quote",
            "page": 1,
            "primary_region_type": "prose",
            "content_type": "fact",
            "content_type_status": "confirmed",
            "verification_status": "verified",
            "ocr_text": "decision ocr",
            "verified_transcript": "decision verified:",
            "summary_text": None,
            "regions": [
                {
                    "page": 1,
                    "sort_order": 0,
                    "region_type": "prose",
                    "bbox": {"left": 10, "top": 10, "width": 50, "height": 20},
                }
            ],
            "ocr_correction": {
                "from": "decision ocr",
                "to": "decision verified:",
                "basis": "test",
            },
            "classification_basis": {"content_type": "fact", "reason": "test"},
        },
        {
            "stable_key": "policy_rate_rhetoric",
            "revision": 2,
            "supersedes_stable_key": "policy_rate_rhetoric",
            "supersedes_revision": 1,
            "kind": "exact_quote",
            "page": 1,
            "primary_region_type": "prose",
            "content_type": "interpretation",
            "content_type_status": "confirmed",
            "verification_status": "verified",
            "ocr_text": "rhetoric cTana",
            "verified_transcript": "rhetoric became tougher",
            "summary_text": None,
            "regions": [
                {
                    "page": 1,
                    "sort_order": 0,
                    "region_type": "prose",
                    "bbox": {"left": 10, "top": 40, "width": 50, "height": 20},
                }
            ],
            "ocr_correction": {"from": "cTana", "to": "стала", "basis": "test"},
            "classification_basis": {"content_type": "interpretation", "reason": "test"},
        },
        {
            "stable_key": "policy_rate_bank_forecast",
            "revision": 2,
            "supersedes_stable_key": "policy_rate_bank_forecast",
            "supersedes_revision": 1,
            "kind": "exact_quote",
            "page": 1,
            "primary_region_type": "prose",
            "content_type": "forecast",
            "content_type_status": "confirmed",
            "verification_status": "verified",
            "ocr_text": "forecast ellipsis…",
            "verified_transcript": "full contiguous forecast paragraph",
            "summary_text": None,
            "regions": [
                {
                    "page": 1,
                    "sort_order": 0,
                    "region_type": "prose",
                    "bbox": {"left": 10, "top": 70, "width": 50, "height": 10},
                },
                {
                    "page": 1,
                    "sort_order": 1,
                    "region_type": "prose",
                    "bbox": {"left": 10, "top": 80, "width": 50, "height": 10},
                },
            ],
            "ocr_correction": {"from": "ellipsis", "to": "full", "basis": "test"},
            "classification_basis": {"content_type": "forecast", "reason": "test"},
        },
    ]
    art = {
        "schema_version": 1,
        "artifact_kind": "bank_fragment_qa_revisions",
        "artifact_id": "test_qa_revisions_v1",
        "created_at": "2026-10-21T00:00:00+00:00",
        "document_slug": plan.slug,
        "source_pdf": {"filename": f"{plan.slug}.pdf", "sha256": plan.source_sha256},
        "ocr_binding": {"fingerprint_hash": plan.fingerprint_hash, "schema_version": 2},
        "page_image_provenance": {"page_number": 1, "check": "test"},
        "verification_session": {
            "method": "ai_vision_over_local_page_png",
            "performed_by": "test agent — AI, not human manual QA",
            "performed_at": "2026-10-21T00:00:00+00:00",
        },
        "fragment_revisions": revs,
    }
    if mutate:
        mutate(art)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(art, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def test_cli_requires_mode_and_database_url():
    assert qa_cli_main(["--qa-artifact", "x.json"]) == 2
    assert qa_cli_main(["--dry-run", "--qa-artifact", "x.json"]) == 2


def test_atomic_apply_and_identical_skip(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        staging, plan = _seed_doc(tmp_path, engine)
        art_path = _qa_artifact(plan, out=tmp_path / "qa.json")
        data, sha = load_qa_artifact(art_path)

        with _session(engine) as session:
            before_f = session.scalar(select(func.count()).select_from(BankFragment))
            before_r = session.scalar(select(func.count()).select_from(BankFragmentRegion))
            result = apply_qa_revisions(session, data, artifact_sha256=sha, dry_run=False)
            session.commit()
        assert result.status == "applied"
        assert result.inserted_fragments == 3
        assert result.inserted_regions == 4  # 1+1+2

        with _session(engine) as session:
            after_f = session.scalar(select(func.count()).select_from(BankFragment))
            after_r = session.scalar(select(func.count()).select_from(BankFragmentRegion))
            assert after_f == before_f + 3
            assert after_r == before_r + 4
            # rev1 unchanged
            rev1 = session.scalar(
                select(BankFragment).where(
                    BankFragment.stable_key == "policy_rate_cb_decision",
                    BankFragment.revision == 1,
                )
            )
            assert rev1 is not None
            assert rev1.verified_transcript == "decision ocr"
            assert rev1.primary_region_type == "unverified"
            rev2 = session.scalar(
                select(BankFragment).where(
                    BankFragment.stable_key == "policy_rate_cb_decision",
                    BankFragment.revision == 2,
                )
            )
            assert rev2 is not None
            assert rev2.supersedes_fragment_id == rev1.id
            assert rev2.primary_region_type == "prose"
            assert rev2.content_type_status == "confirmed"
            assert rev2.ocr_correction_json["qa_provenance"]["method"] == (
                "ai_vision_over_local_page_png"
            )
            assert rev2.ocr_correction_json["qa_provenance"]["artifact_sha256"] == sha
            assert rev2.ocr_correction_json["qa_provenance"]["not_human_manual_qa"] is True

        # identical skip
        with _session(engine) as session:
            r2 = apply_qa_revisions(session, data, artifact_sha256=sha, dry_run=False)
            session.commit()
            f_count = session.scalar(select(func.count()).select_from(BankFragment))
            r_count = session.scalar(select(func.count()).select_from(BankFragmentRegion))
        assert r2.status == "identical_skip"
        assert f_count == after_f
        assert r_count == after_r
    finally:
        engine.dispose()
        tmp.cleanup()


def test_content_conflict(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        _, plan = _seed_doc(tmp_path, engine)
        art_path = _qa_artifact(plan, out=tmp_path / "qa.json")
        run_apply_qa_revisions(artifact_path=art_path, database_url=url, dry_run=False)

        def mutate(art):
            art["fragment_revisions"][0]["verified_transcript"] = "CHANGED"

        art2 = _qa_artifact(plan, out=tmp_path / "qa2.json", mutate=mutate)
        data, sha = load_qa_artifact(art2)
        with _session(engine) as session:
            with pytest.raises(QaConflictError) as ei:
                apply_qa_revisions(session, data, artifact_sha256=sha)
            session.rollback()
        assert ei.value.code == "revision_content_conflict"
    finally:
        engine.dispose()
        tmp.cleanup()


def test_wrong_pdf_sha_and_fingerprint(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        _, plan = _seed_doc(tmp_path, engine)

        def bad_sha(art):
            art["source_pdf"]["sha256"] = "0" * 64

        art = _qa_artifact(plan, out=tmp_path / "bad_sha.json", mutate=bad_sha)
        data, sha = load_qa_artifact(art)
        with _session(engine) as session:
            with pytest.raises(QaBindingError) as ei:
                apply_qa_revisions(session, data, artifact_sha256=sha)
            session.rollback()
        assert ei.value.code == "pdf_sha_mismatch"

        def bad_fp(art):
            art["ocr_binding"]["fingerprint_hash"] = "f" * 64

        art2 = _qa_artifact(plan, out=tmp_path / "bad_fp.json", mutate=bad_fp)
        data2, sha2 = load_qa_artifact(art2)
        with _session(engine) as session:
            with pytest.raises(QaBindingError) as ei:
                apply_qa_revisions(session, data2, artifact_sha256=sha2)
            session.rollback()
        assert ei.value.code == "ocr_fingerprint_mismatch"
    finally:
        engine.dispose()
        tmp.cleanup()


def test_missing_predecessor(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        _, plan = _seed_doc(tmp_path, engine)

        def bump_pred(art):
            for rev in art["fragment_revisions"]:
                rev["supersedes_revision"] = 99
                rev["revision"] = 100

        art = _qa_artifact(plan, out=tmp_path / "miss.json", mutate=bump_pred)
        data, sha = load_qa_artifact(art)
        with _session(engine) as session:
            with pytest.raises(QaBindingError) as ei:
                apply_qa_revisions(session, data, artifact_sha256=sha)
            session.rollback()
        assert ei.value.code == "predecessor_missing"
    finally:
        engine.dispose()
        tmp.cleanup()


def test_partial_state_refuses(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        _, plan = _seed_doc(tmp_path, engine)
        art_path = _qa_artifact(plan, out=tmp_path / "qa.json")
        data, sha = load_qa_artifact(art_path)
        # Apply only first revision manually via truncated artifact
        partial = copy.deepcopy(data)
        partial["fragment_revisions"] = [data["fragment_revisions"][0]]
        with _session(engine) as session:
            apply_qa_revisions(session, partial, artifact_sha256=sha)
            session.commit()
        # Full artifact now sees 1 match + 2 missing
        with _session(engine) as session:
            with pytest.raises(QaPartialStateError) as ei:
                apply_qa_revisions(session, data, artifact_sha256=sha)
            session.rollback()
        assert ei.value.code == "partial_revision_set"
    finally:
        engine.dispose()
        tmp.cleanup()


def test_rollback_keeps_rev1_on_mid_failure(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        _, plan = _seed_doc(tmp_path, engine)
        art_path = _qa_artifact(plan, out=tmp_path / "qa.json")
        data, sha = load_qa_artifact(art_path)
        # Make third region page invalid to fail during normalize of last item
        # after we would have validated all first — inject page 9 on last revision
        data["fragment_revisions"][2]["page"] = 9
        data["fragment_revisions"][2]["regions"][0]["page"] = 9

        with _session(engine) as session:
            before = session.scalar(select(func.count()).select_from(BankFragment))
            with pytest.raises(Exception):
                apply_qa_revisions(session, data, artifact_sha256=sha)
            session.rollback()
            after = session.scalar(select(func.count()).select_from(BankFragment))
            assert after == before
            # no rev2
            n2 = session.scalar(
                select(func.count())
                .select_from(BankFragment)
                .where(BankFragment.revision == 2)
            )
            assert n2 == 0
    finally:
        engine.dispose()
        tmp.cleanup()


def test_latest_selection_no_fallback(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        # Seed with one confirmed prose fragment as rev1 (AI eligible)
        ocr, pdf = _build_valid_corpus(
            tmp_path / "one",
            slug="one-doc",
            pages=1,
            fragments=[_confirmed_fragment(id="quote_v")],
        )
        staging = stage_corpus(input_dir=ocr, pdf_dir=pdf, staging_parent=tmp_path)
        plan, errs, _ = build_prepared_document(
            staging.ocr_dir / "one-doc",
            input_dir=staging.ocr_dir,
            pdf_dir=staging.pdf_dir,
            storage_root=staging.storage_root,
        )
        assert plan is not None and not errs
        with _session(engine) as session:
            load_bank_document(session, plan)
            session.commit()
            rev1 = session.scalars(select(BankFragment)).one()
            run_id = rev1.ocr_run_id
            rev1_id = rev1.id
            rev1_file_id = rev1.document_file_id
            rev1_doc_id = rev1.document_id
            rev1_ocr = rev1.ocr_text
            assert rev1.revision == 1
            sel = select_latest_with_eligibility(
                session, ocr_run_id=run_id, stable_key="quote_v"
            )
            assert sel is not None
            assert sel.eligibility.eligible_ai_evidence

            # Insert unverified rev2 manually
            from datetime import datetime, timezone
            import uuid

            rev2 = BankFragment(
                id=str(uuid.uuid4()),
                ocr_run_id=run_id,
                document_file_id=rev1_file_id,
                document_id=rev1_doc_id,
                stable_key="quote_v",
                revision=2,
                kind="exact_quote",
                primary_region_type="unverified",
                content_type="fact",
                content_type_status="unknown",
                page_number=1,
                ocr_text=rev1_ocr,
                cleaned_text=None,
                verified_transcript="still text",
                summary_text=None,
                verification_status="verified",
                ocr_correction_json=None,
                source_role=None,
                notes=None,
                supersedes_fragment_id=rev1_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(rev2)
            session.flush()
            session.add(
                BankFragmentRegion(
                    id=str(uuid.uuid4()),
                    fragment_id=rev2.id,
                    ocr_run_id=run_id,
                    page_number=1,
                    sort_order=0,
                    region_type="unverified",
                    bbox_left=10,
                    bbox_top=10,
                    bbox_width=50,
                    bbox_height=20,
                    coord_space="page_image_px",
                    note=None,
                )
            )
            session.commit()

        with _session(engine) as session:
            latest = get_latest_fragment(
                session, ocr_run_id=run_id, stable_key="quote_v"
            )
            assert latest is not None and latest.revision == 2
            sel = select_latest_with_eligibility(
                session, ocr_run_id=run_id, stable_key="quote_v"
            )
            assert sel is not None
            assert sel.fragment.revision == 2
            assert not sel.eligibility.eligible_ai_evidence
            # History still available
            old = get_fragment_by_id(session, rev1_id)
            assert old is not None and old.revision == 1
    finally:
        engine.dispose()
        tmp.cleanup()


def test_dry_run_cli_no_write(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        _, plan = _seed_doc(tmp_path, engine)
        art = _qa_artifact(plan, out=tmp_path / "qa.json")
        with _session(engine) as session:
            before = session.scalar(select(func.count()).select_from(BankFragment))
        code = qa_cli_main(
            [
                "--dry-run",
                "--qa-artifact",
                str(art),
                "--database-url",
                url,
                "--report-dir",
                str(tmp_path / "reports"),
            ]
        )
        assert code == 0
        with _session(engine) as session:
            after = session.scalar(select(func.count()).select_from(BankFragment))
            assert after == before
    finally:
        engine.dispose()
        tmp.cleanup()
