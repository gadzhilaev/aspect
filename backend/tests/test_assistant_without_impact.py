"""Stage 3.2: discuss events without EventImpact (no live LLM)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sa_event, func, select
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
    Scenario,
    User,
)
from app.models.bank_materials import BankDocument, BankDocumentFile, BankFragment, BankOcrRun
from app.services.assistant.context_builder import (
    CALCULATION_UNAVAILABLE,
    build_conversation_context,
    slim_live_context,
)
from app.services.assistant.provider import (
    LiveAssistantProvider,
    ProviderMessage,
    ProviderResult,
)
from app.services.bank_materials.load import load_bank_document
from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
from app.services.case_data.activate_snapshot import run_activation
from app.services.case_data.link_org_company import run_link
from tests.test_assistant_case_context import (
    SLOT,
    _add_profiled_org,
    _product_marks,
    _seed_ready_snapshot,
    _user_company,
)
from tests.test_bank_import_dry_run import _build_valid_corpus, _confirmed_fragment

ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


class ScriptedPayloadProvider(LiveAssistantProvider):
    def __init__(self, *, content: str = "ok", tool_calls: list[dict] | None = None):
        super().__init__(api_key="test-not-used", model="scripted", base_url="http://localhost")
        self.content = content
        self.tool_calls = list(tool_calls or [])
        self.last_context: dict[str, Any] | None = None

    def generate(
        self,
        *,
        context: dict[str, Any],
        history: list[ProviderMessage],
        user_text: str,
    ) -> ProviderResult:
        self.last_context = context
        return ProviderResult(
            content=self.content,
            blocks=[],
            tool_calls=list(self.tool_calls),
            bank_evidence_citations=[],
        )


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "asst_no_impact.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "asst-no-impact-secret")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    monkeypatch.setenv("CASE_CONTEXT_SLOT_KEY", SLOT)
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
        yield client, SessionLocal, tmp_path, monkeypatch, engine, url
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def _auth(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _seed_user_company_event(session: Session, *, with_impact: bool = False):
    user = User(
        id=str(uuid.uuid4()),
        email=f"noimp_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("NoImpact1!"),
        display_name="No Impact",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    company = Company(
        id=str(uuid.uuid4()),
        name="No Impact Co",
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
        title="Макросигнал без персонального расчёта",
        summary="Событие доступно для обсуждения без EventImpact.",
        category="macro",
        event_type="policy",
        severity=40.0,
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
    if with_impact:
        session.add(
            EventImpact(
                id=str(uuid.uuid4()),
                event_id=event.id,
                company_id=company.id,
                impact_score=0.0,  # known zero — must stay 0, not null
                urgency="watch",
                confidence=0.55,
                reason_summary="Известный нулевой индекс для регрессии.",
                exposure_value=0.0,  # known zero exposure
                exposure_label="Доля выпуска",
                exposure_unit="percent",
                score_breakdown_json={},
                claims_json={},
                status="monitor",
                model_version="impact-v1.1",
            )
        )
    session.commit()
    return user, company, event


def _load_bank(tmp_path: Path, engine, monkeypatch):
    fragments = [
        _confirmed_fragment(
            id="rate_keep_quote",
            exact_quote="ЦБ сохранил ключевую ставку на уровне 14 процентов.",
            ocr_text="ocr must not leak",
        ),
    ]
    ocr, pdf = _build_valid_corpus(
        tmp_path / "noimp-doc",
        slug="noimp-doc",
        pages=1,
        fragments=fragments,
        identity={
            "confirmed_title": "Macro rate note",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-09-11",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "2026-09-11",
            "period_covered_status": "unknown",
            "topics": ["key_rate"],
            "topics_status": "confirmed",
            "staleness_note": None,
            "is_current_stance": False,
        },
    )
    parent = tmp_path / "stg-noimp"
    parent.mkdir(parents=True, exist_ok=True)
    staging = stage_corpus(input_dir=ocr, pdf_dir=pdf, staging_parent=parent)
    plan, errs, _ = build_prepared_document(
        staging.ocr_dir / "noimp-doc",
        input_dir=staging.ocr_dir,
        pdf_dir=staging.pdf_dir,
        storage_root=staging.storage_root,
    )
    assert plan is not None and not errs
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        load_bank_document(session, plan)
        session.commit()
        doc = session.scalar(select(BankDocument).where(BankDocument.slug == "noimp-doc"))
        file = session.scalar(
            select(BankDocumentFile).where(BankDocumentFile.document_id == doc.id)
        )
        run = session.scalar(
            select(BankOcrRun).where(BankOcrRun.document_file_id == file.id)
        )
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", run.id)
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", str(staging.storage_root))
    get_settings.cache_clear()
    return run.id


def test_open_discuss_history_without_impact(harness):
    client, SessionLocal, tmp_path, monkeypatch, engine, _url = harness
    _load_bank(tmp_path, engine, monkeypatch)

    with SessionLocal() as session:
        user, company, event = _seed_user_company_event(session, with_impact=False)
        user_id, company_id, event_id = user.id, company.id, event.id
        assert (
            session.query(EventImpact)
            .filter(EventImpact.event_id == event_id, EventImpact.company_id == company_id)
            .count()
            == 0
        )

    headers = _auth(user_id)
    r = client.post(
        f"/api/v1/events/{event_id}/assistant/conversations",
        headers=headers,
        json={"company_id": company_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event_id"] == event_id
    assert body["assessment_state"] == CALCULATION_UNAVAILABLE
    assert body["has_impact_calculation"] is False
    conv_id = body["id"]

    # Re-open same conversation
    r2 = client.post(
        f"/api/v1/events/{event_id}/assistant/conversations",
        headers=headers,
        json={"company_id": company_id},
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == conv_id

    # No EventImpact created as side effect
    with SessionLocal() as session:
        assert (
            session.query(EventImpact)
            .filter(EventImpact.event_id == event_id, EventImpact.company_id == company_id)
            .count()
            == 0
        )

    msgs = client.get(
        f"/api/v1/assistant/conversations/{conv_id}/messages", headers=headers
    )
    assert msgs.status_code == 200
    assert len(msgs.json()) >= 1
    opening = msgs.json()[0]
    assert opening["role"] == "assistant"
    assert "отсутствует" in opening["content"].lower() or "расчёт" in opening["content"].lower()

    provider = ScriptedPayloadProvider(content="Обсуждаю без расчёта.")
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider
    )
    post = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Что произошло?", "client_message_id": "m1"},
    )
    assert post.status_code == 200, post.text
    assert provider.last_context is not None
    slim = provider.last_context
    assert slim["assessment_state"] == CALCULATION_UNAVAILABLE
    assert slim["has_impact_calculation"] is False
    assert slim.get("impact") is None
    assert slim.get("impact_results") is None
    # No fabricated zeros
    blob = str(slim)
    assert "'impact_score': 0" not in blob
    assert '"impact_score": 0' not in blob

    hist = client.get(
        f"/api/v1/assistant/conversations/{conv_id}/messages", headers=headers
    )
    assert hist.status_code == 200
    assert len(hist.json()) >= 3  # opening + user + assistant

    listing = client.get(
        f"/api/v1/assistant/conversations?company_id={company_id}", headers=headers
    )
    assert listing.status_code == 200
    item = next(i for i in listing.json() if i["id"] == conv_id)
    assert item["impact_score"] is None
    assert item["confidence"] is None
    assert item["has_impact_calculation"] is False
    assert item["assessment_state"] == CALCULATION_UNAVAILABLE


def test_case_and_bank_delivered_without_impact(harness):
    client, SessionLocal, tmp_path, monkeypatch, engine, url = harness
    _load_bank(tmp_path, engine, monkeypatch)

    with SessionLocal() as session:
        snap = _seed_ready_snapshot(session, slot=SLOT, label="noimp-v1", seq=1)
        _add_profiled_org(
            session,
            snap,
            external_uid="U_201",
            product_marks=_product_marks(loa=True, dep=False),
        )
        user, company = _user_company(session, name="Case NoImpact Co")
        event = Event(
            id=f"evt_{uuid.uuid4().hex[:12]}",
            title="Ставка без impact",
            summary="Обсуждение с case + bank без EventImpact.",
            category="macro",
            event_type="policy",
            severity=42.0,
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
        session.commit()
        ids = {
            "snap": snap.id,
            "user": user.id,
            "company": company.id,
            "event": event.id,
        }

    run_activation(
        database_url=url,
        slot_key=SLOT,
        snapshot_id=ids["snap"],
        expect_no_active=True,
    )
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_201",
        company_id=ids["company"],
        linked_by="ops",
    )

    with SessionLocal() as session:
        user = session.get(User, ids["user"])
        ctx = build_conversation_context(
            session,
            event_id=ids["event"],
            company_id=ids["company"],
            user=user,
        )
        assert ctx["impact"] is None
        assert ctx["assessment_state"] == CALCULATION_UNAVAILABLE
        assert ctx["case_company_context"]["status"] == "profile_available"
        assert ctx["bank_evidence"]["status"] == "available"
        slim = slim_live_context(ctx)
        assert slim["impact"] is None
        assert slim["case_company_context"]["status"] == "profile_available"
        assert slim["bank_evidence"]["available"] is True


def test_calculation_tools_blocked_no_scenario_created(harness, monkeypatch):
    client, SessionLocal, tmp_path, monkeypatch, engine, _url = harness

    with SessionLocal() as session:
        user, company, event = _seed_user_company_event(session, with_impact=False)
        user_id, company_id, event_id = user.id, company.id, event.id

    headers = _auth(user_id)
    conv = client.post(
        f"/api/v1/events/{event_id}/assistant/conversations",
        headers=headers,
        json={"company_id": company_id},
    ).json()
    conv_id = conv["id"]

    provider = ScriptedPayloadProvider(
        content="Пытаюсь сравнить сценарии",
        tool_calls=[{"name": "compare_scenarios", "arguments": {}}],
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider
    )
    before = 0
    with SessionLocal() as session:
        before = session.query(func.count()).select_from(Scenario).scalar() or 0

    post = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Покажи три сценария", "client_message_id": "sc1"},
    )
    assert post.status_code == 200, post.text
    blocks = post.json()["assistant_message"]["blocks"]
    unavailable = [
        b
        for b in blocks
        if b.get("type") == "missing_data"
        and (
            (b.get("data") or {}).get("unavailable_reason") == CALCULATION_UNAVAILABLE
            or (b.get("data") or {}).get("type") == "tool_unavailable"
        )
    ]
    assert unavailable, blocks
    assert not any(b.get("type") == "scenario_comparison" for b in blocks)

    with SessionLocal() as session:
        after = session.query(func.count()).select_from(Scenario).scalar() or 0
        assert after == before
        assert (
            session.query(EventImpact)
            .filter(EventImpact.event_id == event_id, EventImpact.company_id == company_id)
            .count()
            == 0
        )

    draft = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/draft-decision",
        headers=headers,
        json={"scenario_id": str(uuid.uuid4()), "confirm": False},
    )
    assert draft.status_code == 409
    assert draft.json()["error"]["code"] == "CALCULATION_UNAVAILABLE"


def test_foreign_company_and_conversation_forbidden(harness):
    client, SessionLocal, *_ = harness
    with SessionLocal() as session:
        user_a, company_a, event = _seed_user_company_event(session, with_impact=False)
        user_b = User(
            id=str(uuid.uuid4()),
            email=f"other_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("Other1!"),
            display_name="Other",
            email_verified_at=datetime.now(timezone.utc),
        )
        session.add(user_b)
        session.flush()
        company_b = Company(
            id=str(uuid.uuid4()),
            name="Other Co",
            industry="other",
            size_band="small",
            hq_region="X",
            profile_status="ready",
            digital_twin_status="built",
            digital_twin_coverage=0.1,
            is_demo=False,
            created_by=user_b.id,
        )
        session.add(company_b)
        session.flush()
        session.add(
            CompanyMembership(
                id=str(uuid.uuid4()),
                user_id=user_b.id,
                company_id=company_b.id,
                role="owner",
            )
        )
        session.commit()
        ids = {
            "a": user_a.id,
            "b": user_b.id,
            "ca": company_a.id,
            "cb": company_b.id,
            "e": event.id,
        }

    # A cannot open for B's company
    r = client.post(
        f"/api/v1/events/{ids['e']}/assistant/conversations",
        headers=_auth(ids["a"]),
        json={"company_id": ids["cb"]},
    )
    assert r.status_code == 403

    conv = client.post(
        f"/api/v1/events/{ids['e']}/assistant/conversations",
        headers=_auth(ids["a"]),
        json={"company_id": ids["ca"]},
    ).json()
    # B cannot read A's conversation
    forbidden = client.get(
        f"/api/v1/assistant/conversations/{conv['id']}/messages",
        headers=_auth(ids["b"]),
    )
    assert forbidden.status_code == 403


def test_known_zero_preserved_and_with_impact_flow_intact(harness, monkeypatch):
    client, SessionLocal, *_rest = harness
    with SessionLocal() as session:
        user, company, event = _seed_user_company_event(session, with_impact=True)
        user_id, company_id, event_id = user.id, company.id, event.id
        ctx = build_conversation_context(
            session, event_id=event_id, company_id=company_id, user=user
        )
        assert ctx["has_impact_calculation"] is True
        assert ctx["impact"] is not None
        assert ctx["impact"]["impact_score"] == 0.0
        assert ctx["impact"]["exposure_value"] == 0.0
        assert ctx["impact"]["confidence"] == 0.55
        # Distinct from calculation_unavailable
        assert ctx["assessment_state"] != CALCULATION_UNAVAILABLE

    headers = _auth(user_id)
    conv = client.post(
        f"/api/v1/events/{event_id}/assistant/conversations",
        headers=headers,
        json={"company_id": company_id},
    )
    assert conv.status_code == 200
    assert conv.json()["has_impact_calculation"] is True
    assert conv.json()["assessment_state"] != CALCULATION_UNAVAILABLE

    listing = client.get(
        f"/api/v1/assistant/conversations?company_id={company_id}", headers=headers
    )
    item = next(i for i in listing.json() if i["id"] == conv.json()["id"])
    assert item["impact_score"] == 0.0
    assert item["confidence"] == 0.55
    assert item["has_impact_calculation"] is True

    # Mixed list: one with impact, one without
    with SessionLocal() as session:
        event2 = Event(
            id=f"evt_{uuid.uuid4().hex[:12]}",
            title="Без расчёта в списке",
            summary="second",
            category="macro",
            event_type="policy",
            severity=10.0,
            urgency_default="watch",
            status="active",
            occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            match_countries_json=[],
            match_categories_json=[],
            match_currencies_json=[],
            match_materials_json=[],
            attributes_json={},
            is_demo=True,
        )
        session.add(event2)
        session.commit()
        event2_id = event2.id

    conv2 = client.post(
        f"/api/v1/events/{event2_id}/assistant/conversations",
        headers=headers,
        json={"company_id": company_id},
    )
    assert conv2.status_code == 200
    listing2 = client.get(
        f"/api/v1/assistant/conversations?company_id={company_id}", headers=headers
    )
    by_id = {i["id"]: i for i in listing2.json()}
    assert by_id[conv.json()["id"]]["impact_score"] == 0.0
    assert by_id[conv2.json()["id"]]["impact_score"] is None
    assert by_id[conv2.json()["id"]]["has_impact_calculation"] is False


def test_context_null_impact_not_monitoring_only(harness):
    _client, SessionLocal, *_ = harness
    with SessionLocal() as session:
        user, company, event = _seed_user_company_event(session, with_impact=False)
        ctx = build_conversation_context(
            session, event_id=event.id, company_id=company.id, user=user
        )
        assert ctx["assessment_state"] == CALCULATION_UNAVAILABLE
        assert ctx["assessment_state"] != "monitoring_only"
        assert ctx["impact"] is None
        assert ctx["paths"] == []
        assert ctx["solutions"] == []
        assert ctx["tools_available"]["compare_scenarios"] is False
        assert ctx["tools_available"]["discuss_event"] is True
        slim = slim_live_context(ctx)
        assert slim["impact_results"] is None
        assert slim["calculation"]["available"] is False
