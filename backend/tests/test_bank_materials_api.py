"""HTTP API: authorized read-only bank materials (temp SQLite + synthetic files)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import create_app
from app.models import User
from app.models.bank_materials import (
    BankDocument,
    BankDocumentFile,
    BankFragment,
    BankFragmentRegion,
    BankOcrRun,
)
from app.services.bank_materials.apply_qa_revisions import apply_qa_revisions, load_qa_artifact
from app.services.bank_materials.load import load_bank_document
from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
from tests.test_bank_import_dry_run import _build_valid_corpus, _confirmed_fragment
from tests.test_bank_qa_revisions import _qa_artifact, _seed_doc

ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture
def api_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "bank_api.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "bank-materials-api-test-secret")
    monkeypatch.setenv("APP_ENV", "test")
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


def _auth_headers(session: Session) -> dict[str, str]:
    user = User(
        id=str(uuid.uuid4()),
        email=f"bankapi_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("TestBankApi1!"),
        display_name="Bank API Tester",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def _configure_scope(
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_ids: list[str],
    storage_root: Path | None,
) -> None:
    monkeypatch.setenv(
        "BANK_MATERIALS_ALLOWED_OCR_RUN_IDS",
        ",".join(run_ids),
    )
    if storage_root is not None:
        monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", str(storage_root))
    else:
        monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", "")
    get_settings.cache_clear()


def _load_quote_summary_unverified(tmp_path: Path, engine, *, slug: str):
    fragments = [
        _confirmed_fragment(
            id="quote_ok",
            exact_quote="Verified contiguous quote about the rate.",
            ocr_text="ocr should not appear as quote",
        ),
        {
            "id": "summary_ok",
            "kind": "summary",
            "content_type": "interpretation",
            "content_type_status": "confirmed",
            "primary_region_type": "prose",
            "page": 1,
            "regions": [
                {
                    "region_type": "prose",
                    "bbox": {"left": 10, "top": 40, "width": 40, "height": 20},
                }
            ],
            "summary": "Bank paraphrase of the stance, not a quote.",
            "verification_status": "verified",
        },
        {
            "id": "unverified_frag",
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
            "ocr_text": "RAW OCR MUST NOT LEAK AS QUOTE",
            "exact_quote": "RAW OCR MUST NOT LEAK AS QUOTE",
            "verification_status": "unverified",
        },
    ]
    ocr, pdf = _build_valid_corpus(tmp_path / slug, slug=slug, pages=1, fragments=fragments)
    staging_parent = tmp_path / f"stg-{slug}"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = stage_corpus(input_dir=ocr, pdf_dir=pdf, staging_parent=staging_parent)
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
        run_id = session.scalars(select(BankOcrRun)).all()
        # last loaded run for this slug's file
        doc = session.scalar(select(BankDocument).where(BankDocument.slug == slug))
        assert doc is not None
        file = session.scalar(
            select(BankDocumentFile).where(BankDocumentFile.document_id == doc.id)
        )
        assert file is not None
        run = session.scalar(
            select(BankOcrRun).where(BankOcrRun.document_file_id == file.id)
        )
        assert run is not None
        frags = {
            f.stable_key: f
            for f in session.scalars(
                select(BankFragment).where(BankFragment.ocr_run_id == run.id)
            ).all()
        }
        return {
            "staging": staging,
            "document_id": doc.id,
            "file_id": file.id,
            "run_id": run.id,
            "fragments": frags,
            "pdf_sha": file.sha256,
            "storage_key": file.storage_key,
        }


def test_unauthorized(api_harness):
    client, *_ = api_harness
    r = client.get("/api/v1/bank-materials/documents/any")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_not_configured(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    seeded = _load_quote_summary_unverified(tmp_path, engine, slug="cfg-doc")
    with SessionLocal() as session:
        headers = _auth_headers(session)
    # empty allowed runs
    _configure_scope(monkeypatch, run_ids=[], storage_root=seeded["staging"].storage_root)
    r = client.get(
        f"/api/v1/bank-materials/documents/{seeded['document_id']}", headers=headers
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "BANK_MATERIALS_NOT_CONFIGURED"
    body = json.dumps(r.json())
    assert "storage" not in body.lower() or "BANK_MATERIALS" in body
    assert str(seeded["staging"].storage_root) not in body


def test_allowed_document_fragment_and_pdf(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    seeded = _load_quote_summary_unverified(tmp_path, engine, slug="ok-doc")
    _configure_scope(
        monkeypatch,
        run_ids=[seeded["run_id"]],
        storage_root=seeded["staging"].storage_root,
    )
    with SessionLocal() as session:
        headers = _auth_headers(session)
        before_docs = session.scalar(select(func.count()).select_from(BankDocument))
        before_frags = session.scalar(select(func.count()).select_from(BankFragment))

    r = client.get(
        f"/api/v1/bank-materials/documents/{seeded['document_id']}", headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["document_id"] == seeded["document_id"]
    assert data["title_status"]
    assert "publication_date_precision" in data
    assert "is_current_stance" in data
    assert data["files"]
    assert data["files"][0]["content_href"].endswith(
        f"/bank-materials/files/{seeded['file_id']}/content"
    )
    assert "storage_key" not in json.dumps(data)
    assert str(tmp_path) not in json.dumps(data)

    quote = seeded["fragments"]["quote_ok"]
    rq = client.get(f"/api/v1/bank-materials/fragments/{quote.id}", headers=headers)
    assert rq.status_code == 200
    q = rq.json()
    assert q["text_kind"] == "exact_quote"
    assert q["text"] == "Verified contiguous quote about the rate."
    assert "RAW OCR" not in (q["text"] or "")
    assert q["eligible_exact_quote"] is True
    assert q["is_latest_revision"] is True
    assert q["is_superseded"] is False

    summary = seeded["fragments"]["summary_ok"]
    rs = client.get(f"/api/v1/bank-materials/fragments/{summary.id}", headers=headers)
    assert rs.status_code == 200
    s = rs.json()
    assert s["text_kind"] == "summary"
    assert "paraphrase" in (s["text"] or "").lower() or "stance" in (s["text"] or "").lower()
    assert s["eligible_exact_quote"] is False
    assert s["text_restricted"] is False

    unver = seeded["fragments"]["unverified_frag"]
    ru = client.get(f"/api/v1/bank-materials/fragments/{unver.id}", headers=headers)
    assert ru.status_code == 200
    u = ru.json()
    assert u["text_kind"] == "restricted"
    assert u["text"] is None
    assert u["text_restricted"] is True
    assert u["restriction_reasons"]
    blob = json.dumps(u)
    assert "RAW OCR MUST NOT LEAK" not in blob
    assert "ocr_text" not in blob

    pdf = client.get(
        f"/api/v1/bank-materials/files/{seeded['file_id']}/content", headers=headers
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert "attachment" in pdf.headers.get("content-disposition", "").lower()
    assert pdf.content[:4] == b"%PDF"

    with SessionLocal() as session:
        after_docs = session.scalar(select(func.count()).select_from(BankDocument))
        after_frags = session.scalar(select(func.count()).select_from(BankFragment))
    assert before_docs == after_docs
    assert before_frags == after_frags


def test_out_of_scope_and_cross_id(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    a = _load_quote_summary_unverified(tmp_path, engine, slug="scope-a")
    b = _load_quote_summary_unverified(tmp_path, engine, slug="scope-b")
    # Only A allowed; storage covers both staged roots? Use parent of both.
    # Each staging has its own storage_root; point to A's root and expect B file 404 anyway by scope.
    _configure_scope(
        monkeypatch,
        run_ids=[a["run_id"]],
        storage_root=a["staging"].storage_root,
    )
    with SessionLocal() as session:
        headers = _auth_headers(session)

    r = client.get(f"/api/v1/bank-materials/documents/{b['document_id']}", headers=headers)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"

    r = client.get(
        f"/api/v1/bank-materials/fragments/{b['fragments']['quote_ok'].id}",
        headers=headers,
    )
    assert r.status_code == 404

    r = client.get(
        f"/api/v1/bank-materials/files/{b['file_id']}/content", headers=headers
    )
    assert r.status_code == 404
    assert "storage" not in r.json()["error"]["message"].lower()
    assert str(tmp_path) not in r.text


def test_historical_revision_marked_superseded(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    staging, plan = _seed_doc(tmp_path, engine, slug="hist-doc")
    art = _qa_artifact(plan, out=tmp_path / "qa.json")
    data, sha = load_qa_artifact(art)
    with SessionLocal() as session:
        apply_qa_revisions(session, data, artifact_sha256=sha)
        session.commit()
        run_id = session.scalars(select(BankOcrRun)).first().id
        old = session.scalar(
            select(BankFragment).where(
                BankFragment.stable_key == "policy_rate_cb_decision",
                BankFragment.revision == 1,
            )
        )
        new = session.scalar(
            select(BankFragment).where(
                BankFragment.stable_key == "policy_rate_cb_decision",
                BankFragment.revision == 2,
            )
        )
        assert old is not None and new is not None
        old_id, new_id = old.id, new.id
        headers = _auth_headers(session)

    _configure_scope(
        monkeypatch, run_ids=[run_id], storage_root=staging.storage_root
    )

    ro = client.get(f"/api/v1/bank-materials/fragments/{old_id}", headers=headers)
    assert ro.status_code == 200
    o = ro.json()
    assert o["revision"] == 1
    assert o["is_latest_revision"] is False
    assert o["is_superseded"] is True
    assert o["latest_revision"] == 2

    rn = client.get(f"/api/v1/bank-materials/fragments/{new_id}", headers=headers)
    assert rn.status_code == 200
    n = rn.json()
    assert n["revision"] == 2
    assert n["is_latest_revision"] is True
    assert n["is_superseded"] is False
    # Must not silently redirect old → new
    assert o["fragment_id"] != n["fragment_id"]


def test_missing_file_sha_mismatch_path_traversal(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    seeded = _load_quote_summary_unverified(tmp_path, engine, slug="file-doc")
    _configure_scope(
        monkeypatch,
        run_ids=[seeded["run_id"]],
        storage_root=seeded["staging"].storage_root,
    )
    with SessionLocal() as session:
        headers = _auth_headers(session)

    # Path traversal via malicious storage_key
    with SessionLocal() as session:
        file = session.get(BankDocumentFile, seeded["file_id"])
        assert file is not None
        file.storage_key = "../../outside_secret.pdf"
        session.commit()
    outside = tmp_path / "outside_secret.pdf"
    outside.write_bytes(b"%PDF-1.4 escape")
    r = client.get(
        f"/api/v1/bank-materials/files/{seeded['file_id']}/content", headers=headers
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "BANK_FILE_UNAVAILABLE"
    assert "outside" not in r.text.lower()
    assert ".." not in r.json()["error"]["message"]
    assert str(tmp_path) not in r.text

    # Restore key, then missing file
    with SessionLocal() as session:
        file = session.get(BankDocumentFile, seeded["file_id"])
        file.storage_key = seeded["storage_key"]
        session.commit()
        path = seeded["staging"].storage_root / seeded["storage_key"]
    assert path.is_file()
    path.unlink()
    r = client.get(
        f"/api/v1/bank-materials/files/{seeded['file_id']}/content", headers=headers
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "BANK_FILE_UNAVAILABLE"

    # Recreate with wrong SHA
    path.write_bytes(b"%PDF-1.4 tampered-content-not-matching-sha")
    r = client.get(
        f"/api/v1/bank-materials/files/{seeded['file_id']}/content", headers=headers
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "BANK_FILE_INTEGRITY"
    assert str(path) not in r.text
    assert "\\" not in r.json()["error"]["message"]
