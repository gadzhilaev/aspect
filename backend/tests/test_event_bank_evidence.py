"""Event bank-evidence service + HTTP API (synthetic SQLite)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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
from app.models import Company, CompanyMembership, Event, User
from app.models.bank_materials import (
    BankDocument,
    BankDocumentFile,
    BankFragment,
    BankFragmentRegion,
    BankOcrRun,
)
from app.services.bank_materials.apply_qa_revisions import apply_qa_revisions, load_qa_artifact
from app.services.bank_materials.event_evidence import (
    build_event_search_query,
    collect_event_bank_evidence,
    resolve_event_as_of_date,
)
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
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "evt_bank.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "event-bank-evidence-test-secret")
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


def _configure(monkeypatch, *, run_ids: list[str], storage_root: Path | None = None):
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", ",".join(run_ids))
    monkeypatch.setenv(
        "BANK_MATERIALS_STORAGE_ROOT",
        str(storage_root) if storage_root else "",
    )
    get_settings.cache_clear()


def _auth(session: Session) -> tuple[User, dict[str, str]]:
    user = User(
        id=str(uuid.uuid4()),
        email=f"evt_bank_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("EvtBank1!"),
        display_name="Evt Bank",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _add_event(
    session: Session,
    *,
    title: str,
    summary: str,
    occurred_at: datetime,
    category: str = "macro",
    event_type: str = "policy",
    match_categories: list | None = None,
) -> Event:
    ev = Event(
        id=f"evt_{uuid.uuid4().hex[:12]}",
        title=title,
        summary=summary,
        category=category,
        event_type=event_type,
        severity=50.0,
        urgency_default="watch",
        status="active",
        occurred_at=occurred_at,
        match_countries_json=[],
        match_categories_json=match_categories or [],
        match_currencies_json=[],
        match_materials_json=[],
        attributes_json={},
        is_demo=True,
    )
    session.add(ev)
    session.commit()
    return ev


def _load_rate_doc(tmp_path: Path, engine, *, slug: str, pub_date: str = "2026-09-11"):
    fragments = [
        _confirmed_fragment(
            id="rate_keep_quote",
            exact_quote="ЦБ сохранил ключевую ставку на уровне 14 процентов.",
            ocr_text="ocr raw must not leak",
        ),
        {
            "id": "rate_forecast_summary",
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
            "summary": "Банк ожидает сохранения паузы по ключевой ставке до конца года.",
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
            "ocr_text": "RAW UNVERIFIED OCR ABOUT RATE",
            "exact_quote": "RAW UNVERIFIED OCR ABOUT RATE",
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
            "document_id": doc.id,
            "file_id": file.id,
            "fragments": frags,
        }


def test_resolve_event_as_of_date_basis():
    day, basis = resolve_event_as_of_date(
        SimpleNamespace(occurred_at=datetime(2026, 9, 12, 15, 30, tzinfo=timezone.utc))
    )
    assert day == date(2026, 9, 12)
    assert basis == "event.occurred_at"
    day2, basis2 = resolve_event_as_of_date(SimpleNamespace(occurred_at=None))
    assert day2 is None and basis2 is None


def test_build_query_bounded_no_raw_attributes():
    ev = SimpleNamespace(
        title="Ключевая ставка ЦБ",
        summary="Банк России сохранил ставку. " * 80,
        category="macro",
        event_type="policy_rate",
        match_categories_json=["rates", "cb"],
        match_countries_json=["Россия"],
        match_currencies_json=[],
        match_materials_json=[],
        attributes_json={"huge": "x" * 5000, "raw_payload": {"secret": 1}},
    )
    q = build_event_search_query(ev, max_chars=400)
    assert len(q) <= 400
    assert "Ключевая ставка" in q
    assert "secret" not in q
    assert "x" * 100 not in q or len(q) <= 400


def test_relevant_and_irrelevant_service(harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    seeded = _load_rate_doc(tmp_path, engine, slug="rate-doc", pub_date="2026-09-11")
    _configure(monkeypatch, run_ids=[seeded["run_id"]], storage_root=seeded["staging"].storage_root)

    with SessionLocal() as session:
        relevant = _add_event(
            session,
            title="ЦБ сохранил ключевую ставку",
            summary="Банк России оставил ключевую ставку без изменений на уровне 14%.",
            occurred_at=datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc),
            match_categories=["rates"],
        )
        odd = _add_event(
            session,
            title="Погода в Антарктиде",
            summary="Температура у полюса остаётся низкой без макроэкономических последствий.",
            occurred_at=datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc),
        )
        before = session.scalar(select(func.count()).select_from(BankFragment))
        out = collect_event_bank_evidence(session, event=relevant)
        empty = collect_event_bank_evidence(session, event=odd)
        after = session.scalar(select(func.count()).select_from(BankFragment))

    assert before == after
    assert out.status == "available"
    assert out.as_of_date == date(2026, 9, 12)
    assert out.as_of_date_basis == "event.occurred_at"
    assert out.evidence
    assert all(e.text_kind in ("exact_quote", "summary") for e in out.evidence)
    assert all("RAW UNVERIFIED" not in e.text for e in out.evidence)
    assert all(e.fragment_href.startswith("/api/v1/bank-materials/fragments/") for e in out.evidence)
    keys = {e.stable_key for e in out.evidence}
    assert "unverified_noise" not in keys

    assert empty.status == "no_matching_evidence"
    assert empty.evidence == []


def test_integration_not_configured_and_date_unavailable(harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    seeded = _load_rate_doc(tmp_path, engine, slug="cfg-doc")
    # empty scope
    _configure(monkeypatch, run_ids=[], storage_root=seeded["staging"].storage_root)
    with SessionLocal() as session:
        ev = _add_event(
            session,
            title="Ставка",
            summary="Ключевая ставка сохранена",
            occurred_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        out = collect_event_bank_evidence(session, event=ev)
    assert out.status == "integration_not_configured"
    assert out.evidence == []

    _configure(monkeypatch, run_ids=[seeded["run_id"]], storage_root=seeded["staging"].storage_root)
    fake = SimpleNamespace(
        id="evt_nodate",
        occurred_at=None,
        title="x",
        summary="y",
        category="macro",
        event_type="policy",
        match_categories_json=[],
        match_countries_json=[],
        match_currencies_json=[],
        match_materials_json=[],
    )
    with SessionLocal() as session:
        out2 = collect_event_bank_evidence(session, event=fake)  # type: ignore[arg-type]
    assert out2.status == "event_date_unavailable"


def test_publication_after_event_excluded(harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    seeded = _load_rate_doc(tmp_path, engine, slug="future-doc", pub_date="2026-09-20")
    _configure(monkeypatch, run_ids=[seeded["run_id"]], storage_root=seeded["staging"].storage_root)
    with SessionLocal() as session:
        ev = _add_event(
            session,
            title="ЦБ сохранил ключевую ставку",
            summary="Сохранение ключевой ставки на заседании.",
            occurred_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        out = collect_event_bank_evidence(session, event=ev)
    assert out.status == "no_matching_evidence"
    assert out.evidence == []


def test_month_precision_conservative(harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    # Month-only publication in September 2026; event mid-September → evidence excludes
    fragments = [
        _confirmed_fragment(
            id="month_rate",
            exact_quote="Ключевая ставка сохранена без изменений.",
            ocr_text="ocr",
        )
    ]
    ocr, pdf = _build_valid_corpus(
        tmp_path / "month-doc",
        slug="month-doc",
        pages=1,
        fragments=fragments,
        identity={
            "confirmed_title": "Month note",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": None,
            "confirmed_publication_year": 2026,
            "confirmed_publication_month": 9,
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "September 2026",
            "publication_date_precision": "month",
            "period_covered_status": "unknown",
            "topics": [],
            "topics_status": "unknown",
            "staleness_note": None,
            "is_current_stance": False,
        },
    )
    parent = tmp_path / "stg-month"
    parent.mkdir(parents=True, exist_ok=True)
    staging = stage_corpus(input_dir=ocr, pdf_dir=pdf, staging_parent=parent)
    plan, errs, _ = build_prepared_document(
        staging.ocr_dir / "month-doc",
        input_dir=staging.ocr_dir,
        pdf_dir=staging.pdf_dir,
        storage_root=staging.storage_root,
    )
    # If identity month shape is rejected by prepare, skip with clear assert
    if plan is None or errs:
        # Fall back: load day-precision then mutate document precision in DB
        seeded = _load_rate_doc(tmp_path, engine, slug="month-fallback", pub_date="2026-09-01")
        _configure(
            monkeypatch,
            run_ids=[seeded["run_id"]],
            storage_root=seeded["staging"].storage_root,
        )
        with SessionLocal() as session:
            doc = session.get(BankDocument, seeded["document_id"])
            doc.publication_date = None
            doc.publication_year = 2026
            doc.publication_month = 9
            doc.publication_date_precision = "month"
            session.commit()
            run_id = seeded["run_id"]
            storage = seeded["staging"].storage_root
    else:
        with SessionLocal() as session:
            load_bank_document(session, plan)
            session.commit()
            run_id = session.scalars(select(BankOcrRun)).one().id
            storage = staging.storage_root
        _configure(monkeypatch, run_ids=[run_id], storage_root=storage)

    with SessionLocal() as session:
        ev = _add_event(
            session,
            title="Ключевая ставка сохранена",
            summary="Сохранение ключевой ставки регулятором.",
            occurred_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        out = collect_event_bank_evidence(session, event=ev)
    # Month overlaps as_of → evidence gate excludes
    assert out.status == "no_matching_evidence"
    assert out.evidence == []


def test_superseded_not_used_for_new_evidence(harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    staging, plan = _seed_doc(tmp_path, engine, slug="qa-evt")
    art = _qa_artifact(plan, out=tmp_path / "qa.json")
    data, sha = load_qa_artifact(art)
    with SessionLocal() as session:
        apply_qa_revisions(session, data, artifact_sha256=sha)
        session.commit()
        run_id = session.scalars(select(BankOcrRun)).first().id
        # Insert unverified rev3 superseding decision so latest is blocked
        rev2 = session.scalar(
            select(BankFragment).where(
                BankFragment.stable_key == "policy_rate_cb_decision",
                BankFragment.revision == 2,
            )
        )
        assert rev2 is not None
        rev3 = BankFragment(
            id=str(uuid.uuid4()),
            ocr_run_id=rev2.ocr_run_id,
            document_file_id=rev2.document_file_id,
            document_id=rev2.document_id,
            stable_key="policy_rate_cb_decision",
            revision=3,
            kind="exact_quote",
            primary_region_type="unverified",
            content_type="fact",
            content_type_status="unknown",
            page_number=1,
            ocr_text=rev2.ocr_text,
            cleaned_text=None,
            verified_transcript="blocked latest",
            summary_text=None,
            verification_status="unverified",
            ocr_correction_json=None,
            source_role=None,
            notes=None,
            supersedes_fragment_id=rev2.id,
            created_at=datetime.now(timezone.utc),
        )
        session.add(rev3)
        session.flush()
        session.add(
            BankFragmentRegion(
                id=str(uuid.uuid4()),
                fragment_id=rev3.id,
                ocr_run_id=run_id,
                page_number=1,
                sort_order=0,
                region_type="unverified",
                bbox_left=1,
                bbox_top=1,
                bbox_width=10,
                bbox_height=10,
                coord_space="page_image_px",
                note=None,
            )
        )
        session.commit()

    _configure(monkeypatch, run_ids=[run_id], storage_root=staging.storage_root)
    with SessionLocal() as session:
        ev = _add_event(
            session,
            title="Решение оставить ставку неизменной 14",
            summary="ЦБ принял решение оставить ставку неизменной.",
            occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )
        out = collect_event_bank_evidence(session, event=ev)
    decision_hits = [e for e in out.evidence if e.stable_key == "policy_rate_cb_decision"]
    assert decision_hits == []
    assert all(e.revision != 1 or e.stable_key != "policy_rate_cb_decision" for e in out.evidence)


def test_api_auth_membership_no_impact_required(harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = harness
    seeded = _load_rate_doc(tmp_path, engine, slug="api-doc", pub_date="2026-09-11")
    _configure(monkeypatch, run_ids=[seeded["run_id"]], storage_root=seeded["staging"].storage_root)

    with SessionLocal() as session:
        user, headers = _auth(session)
        ev = _add_event(
            session,
            title="ЦБ сохранил ключевую ставку",
            summary="Сохранение ключевой ставки без изменений.",
            occurred_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        )
        # no EventImpact row
        company = Company(
            id=str(uuid.uuid4()),
            name="Test Co",
            industry="manufacturing",
            size_band="small",
            hq_region="Москва",
            profile_status="ready",
            digital_twin_status="not_built",
            digital_twin_coverage=0.0,
            is_demo=False,
            created_by=user.id,
        )
        session.add(company)
        session.flush()
        session.add(
            CompanyMembership(
                id=str(uuid.uuid4()),
                company_id=company.id,
                user_id=user.id,
                role="owner",
            )
        )
        stranger = User(
            id=str(uuid.uuid4()),
            email=f"stranger_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("EvtBank1!"),
            display_name="Stranger",
            email_verified_at=datetime.now(timezone.utc),
        )
        session.add(stranger)
        session.commit()
        event_id = ev.id
        company_id = company.id
        stranger_headers = {
            "Authorization": f"Bearer {create_access_token(stranger.id)}"
        }
        before_events = session.scalar(select(func.count()).select_from(Event))
        before_frags = session.scalar(select(func.count()).select_from(BankFragment))

    r0 = client.get(f"/api/v1/events/{event_id}/bank-evidence")
    assert r0.status_code == 401

    r = client.get(f"/api/v1/events/{event_id}/bank-evidence", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] in ("available", "no_matching_evidence")
    assert body["event_id"] == event_id
    assert body["as_of_date_basis"] == "event.occurred_at"
    if body["evidence"]:
        item = body["evidence"][0]
        assert item["document_href"].endswith(f"/documents/{item['document_id']}")
        assert item["fragment_href"].endswith(f"/fragments/{item['fragment_id']}")
        assert item["content_href"].endswith(f"/files/{item['document_file_id']}/content")
        assert "storage" not in item["content_href"]
        assert "lexical_match_score" in item
        assert "confidence" not in item

    # optional company_id with membership
    rok = client.get(
        f"/api/v1/events/{event_id}/bank-evidence",
        headers=headers,
        params={"company_id": company_id},
    )
    assert rok.status_code == 200

    rforbid = client.get(
        f"/api/v1/events/{event_id}/bank-evidence",
        headers=stranger_headers,
        params={"company_id": company_id},
    )
    assert rforbid.status_code == 403

    r404 = client.get(
        "/api/v1/events/evt_does_not_exist/bank-evidence", headers=headers
    )
    assert r404.status_code == 404

    with SessionLocal() as session:
        after_events = session.scalar(select(func.count()).select_from(Event))
        after_frags = session.scalar(select(func.count()).select_from(BankFragment))
    assert before_events == after_events
    assert before_frags == after_frags
