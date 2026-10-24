"""Stage 4.5 — AgentLoopRunner behind ASSISTANT_AGENT_LOOP via TestClient + mocked HTTP."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
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
from app.models import Company, CompanyMembership, Decision, Event, EventImpact, Scenario, User
from app.models.assistant import AssistantMessage
from app.models.bank_materials import BankDocument, BankDocumentFile, BankOcrRun
from app.services.assistant.agent_loop.api_integration import set_loop_http_client_for_tests
from app.services.bank_materials.load import load_bank_document
from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
from tests.test_bank_import_dry_run import _build_valid_corpus, _confirmed_fragment

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://changellenge.up.railway.app/v1"
MODEL = "deepseek/deepseek-v4.1-flash"


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


class _FakeTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[httpx.Request] = []
        self.lock = threading.Lock()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            self.calls.append(request)
        return self.handler(request)


def _assistant_message(content: str, *, finish_reason: str = "stop") -> dict[str, Any]:
    return {
        "id": "chatcmpl-api",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def _tool(name: str) -> str:
    return json.dumps(
        {"kind": "tool_request", "action": {"name": name, "arguments": {}}},
        ensure_ascii=False,
    )


def _final(content: str, citations: list | None = None) -> str:
    return json.dumps(
        {
            "kind": "final",
            "content": content,
            "bank_evidence_citations": citations or [],
        },
        ensure_ascii=False,
    )


@pytest.fixture
def api_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "agent_api_45.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "agent-api-45-secret")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_API_KEY", "hk-test-key")
    monkeypatch.setenv("HACKATHON_BASE_URL", BASE)
    monkeypatch.setenv("HACKATHON_MODEL", MODEL)
    monkeypatch.setenv("ASSISTANT_AGENT_LOOP", "false")
    monkeypatch.setenv("CASE_CONTEXT_SLOT_KEY", "")
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", "")
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GIGACHAT_AUTH_KEY", raising=False)
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
        set_loop_http_client_for_tests(None)
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def _enable_loop(monkeypatch, transport: _FakeTransport) -> None:
    monkeypatch.setenv("ASSISTANT_AGENT_LOOP", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    get_settings.cache_clear()
    set_loop_http_client_for_tests(httpx.Client(transport=transport))


def _seed_user_company_event(session: Session, *, with_impact: bool = False):
    user_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    session.add(
        User(
            id=user_id,
            email=f"api45_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("ApiLoop45!"),
            display_name="API45",
            email_verified_at=datetime.now(timezone.utc),
        )
    )
    session.flush()
    session.add(
        Company(
            id=company_id,
            name="API45 Co",
            industry="manufacturing",
            size_band="small",
            hq_region="Москва",
            profile_status="ready",
            digital_twin_status="built",
            digital_twin_coverage=0.5,
            is_demo=False,
            created_by=user_id,
        )
    )
    session.flush()
    session.add(
        CompanyMembership(
            id=str(uuid.uuid4()), user_id=user_id, company_id=company_id, role="owner"
        )
    )
    session.add(
        Event(
            id=event_id,
            title="ЦБ сохранил ключевую ставку",
            summary="Банк России оставил ключевую ставку без изменений.",
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
    )
    session.flush()
    if with_impact:
        session.add(
            EventImpact(
                id=str(uuid.uuid4()),
                event_id=event_id,
                company_id=company_id,
                impact_score=28.0,
                urgency="watch",
                confidence=0.5,
                reason_summary="t",
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
    return user_id, company_id, event_id


def _auth(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _create_conv(client: TestClient, headers: dict, company_id: str) -> dict:
    r = client.post(
        "/api/v1/assistant/conversations",
        headers=headers,
        json={"company_id": company_id, "event_id": None},
    )
    # CreateConversationIn may only take company_id — check schema
    if r.status_code >= 400:
        r = client.post(
            "/api/v1/assistant/conversations",
            headers=headers,
            json={"company_id": company_id},
        )
    assert r.status_code == 200, r.text
    return r.json()


def _load_bank(tmp_path, engine, monkeypatch, slug="api45-rate"):
    fragments = [
        _confirmed_fragment(
            id="api45_quote",
            exact_quote="ЦБ сохранил ключевую ставку на уровне 14 процентов.",
            ocr_text="ocr",
        ),
    ]
    ocr, pdf = _build_valid_corpus(
        tmp_path / slug,
        slug=slug,
        pages=1,
        fragments=fragments,
        identity={
            "confirmed_title": "API45 rate",
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
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", run.id)
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", str(staging.storage_root))
    get_settings.cache_clear()
    return run.id


# ---------- tests ----------


def test_flag_off_uses_legacy_mock_path(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    monkeypatch.setenv("ASSISTANT_AGENT_LOOP", "false")
    get_settings.cache_clear()
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=True)
    # Bind conversation to event via create — need event on company flow
    # get_or_create uses company + picks event? Check create API
    headers = _auth(user_id)
    # Manually create conversation with event
    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        conv = AssistantConversation(
            id=str(uuid4()),
            user_id=user_id,
            company_id=company_id,
            event_id=event_id,
            status="active",
        )
        session.add(conv)
        session.commit()
        cid = conv.id

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=headers,
        json={"content": "привет legacy", "client_message_id": "legacy-1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reused"] is False
    assert body["assistant_message"]["content"]
    # No loop incomplete markers
    assert not any(
        (b.get("data") or {}).get("reason") == "loop_incomplete"
        for b in body["assistant_message"]["blocks"]
    )


def test_flag_on_tool_observation_final(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(BASE)
        assert b"api.openai.com" not in request.url.raw_host
        i = idx["i"]
        idx["i"] += 1
        if i == 0:
            raw = request.content.decode("utf-8")
            assert "14 процентов" not in raw or "observations" in raw
            return httpx.Response(200, json=_assistant_message(_tool("get_event_context")))
        return httpx.Response(200, json=_assistant_message(_final("Итог по событию")))

    transport = _FakeTransport(handler)
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        conv = AssistantConversation(
            id=str(uuid4()),
            user_id=user_id,
            company_id=company_id,
            event_id=event_id,
            status="active",
        )
        session.add(conv)
        session.commit()
        cid = conv.id

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(user_id),
        json={"content": "Что случилось?", "client_message_id": "loop-1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["assistant_message"]["content"].startswith("Итог")
    assert len(transport.calls) == 2


def test_multi_tool_bank_citations(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    _load_bank(tmp_path, engine, monkeypatch)
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    idx = {"i": 0}
    cited: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        user = json.loads(request.content.decode())["messages"][-1]["content"]
        if i == 0:
            return httpx.Response(200, json=_assistant_message(_tool("get_bank_evidence")))
        import re

        assert "14 процентов" in user
        m = re.search(r'"fragment_id"\s*:\s*"([^"]+)"', user)
        assert m
        cited["fid"] = m.group(1)
        rm = re.search(r'"revision"\s*:\s*(\d+)', user)
        cited["rev"] = int(rm.group(1)) if rm else 1
        return httpx.Response(
            200,
            json=_assistant_message(
                _final("По банку", [{"fragment_id": cited["fid"], "revision": cited["rev"]}])
            ),
        )

    transport = _FakeTransport(handler)
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid,
                user_id=user_id,
                company_id=company_id,
                event_id=event_id,
                status="active",
            )
        )
        session.commit()

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(user_id),
        json={"content": "банк?", "client_message_id": "bank-1"},
    )
    assert r.status_code == 200, r.text
    blocks = r.json()["assistant_message"]["blocks"]
    bank = next(b for b in blocks if b["type"] == "bank_evidence_list")
    assert bank["data"]["used"]
    assert bank["data"]["used"][0]["fragment_id"] == cited["fid"]
    assert bank["data"]["used"][0]["revision"] == cited["rev"]


def test_without_impact_discussion(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        if i == 0:
            return httpx.Response(
                200, json=_assistant_message(_tool("get_available_assessment"))
            )
        user = json.loads(request.content.decode())["messages"][-1]["content"]
        assert "unavailable" in user or "calculation_unavailable" in user
        return httpx.Response(200, json=_assistant_message(_final("обсуждаем без оценки")))

    transport = _FakeTransport(handler)
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    before = {"impact": 0}
    with SessionLocal() as session:
        before["impact"] = session.scalar(select(func.count()).select_from(EventImpact)) or 0
        before["scenario"] = session.scalar(select(func.count()).select_from(Scenario)) or 0
        before["decision"] = session.scalar(select(func.count()).select_from(Decision)) or 0

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(user_id),
        json={"content": "есть оценка?", "client_message_id": "noimp-1"},
    )
    assert r.status_code == 200, r.text
    with SessionLocal() as session:
        assert (session.scalar(select(func.count()).select_from(EventImpact)) or 0) == before[
            "impact"
        ]
        assert (session.scalar(select(func.count()).select_from(Scenario)) or 0) == before[
            "scenario"
        ]
        assert (session.scalar(select(func.count()).select_from(Decision)) or 0) == before[
            "decision"
        ]


def test_followup_with_history(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        user = json.loads(request.content.decode())["messages"][-1]["content"]
        if i == 0:
            return httpx.Response(200, json=_assistant_message(_final("первый ответ")))
        # History must be present as DATA (whole prior turns), not as system instructions.
        assert "conversation_history" in user or "первый ответ" in user
        return httpx.Response(200, json=_assistant_message(_final("уточнение учтено")))

    transport = _FakeTransport(handler)
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    h = _auth(user_id)
    r1 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "сначала", "client_message_id": "h1"},
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "а почему?", "client_message_id": "h2"},
    )
    assert r2.status_code == 200, r2.text
    assert "уточнение" in r2.json()["assistant_message"]["content"]
    msgs = client.get(f"/api/v1/assistant/conversations/{cid}/messages", headers=h)
    assert msgs.status_code == 200
    assert len(msgs.json()) >= 4  # opening? + 2 user + 2 assistant — may vary


def test_foreign_company_forbidden(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)
        stranger = str(uuid.uuid4())
        session.add(
            User(
                id=stranger,
                email=f"str_{uuid.uuid4().hex[:8]}@example.com",
                password_hash=hash_password("Str1!aaaa"),
                display_name="S",
                email_verified_at=datetime.now(timezone.utc),
            )
        )
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    transport = _FakeTransport(lambda r: httpx.Response(200, json=_assistant_message(_final("x"))))
    _enable_loop(monkeypatch, transport)
    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(stranger),
        json={"content": "hack", "client_message_id": "acl-1"},
    )
    assert r.status_code in {403, 404}
    assert len(transport.calls) == 0


def test_bad_citation_and_shared_repair(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    _load_bank(tmp_path, engine, monkeypatch, slug="api45-rep")
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        if i == 0:
            return httpx.Response(200, json=_assistant_message("not-json"))
        if i == 1:
            return httpx.Response(200, json=_assistant_message(_tool("get_bank_evidence")))
        return httpx.Response(
            200,
            json=_assistant_message(
                _final("x", [{"fragment_id": "ghost", "revision": 1}])
            ),
        )

    transport = _FakeTransport(handler)
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(user_id),
        json={"content": "cite", "client_message_id": "cite-1"},
    )
    assert r.status_code in {409, 429, 504}
    assert r.json()["error"]["code"].startswith("ASSISTANT_LOOP_")
    assert len(transport.calls) == 3  # format repair used; no citation repair HTTP


def test_timeout_stop_and_idempotent_replay(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    transport = _FakeTransport(handler)
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    h = _auth(user_id)
    r1 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "timeout", "client_message_id": "to-1"},
    )
    assert r1.status_code == 504
    assert r1.json()["error"]["code"] == "ASSISTANT_LOOP_TIMEOUT"
    assert len(transport.calls) == 1

    r2 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "timeout", "client_message_id": "to-1"},
    )
    # Replay incomplete → same structured error, not successful final; no new HTTP
    assert r2.status_code == 504
    assert r2.json()["error"]["code"] == "ASSISTANT_LOOP_TIMEOUT"
    assert r2.json()["error"]["details"][0].get("reused") is True
    assert r2.json()["error"]["details"][0].get("not_ai_final") is True
    assert len(transport.calls) == 1


def test_success_idempotent_replay(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_assistant_message(_final("готово")))

    transport = _FakeTransport(handler)
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    h = _auth(user_id)
    r1 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "ok", "client_message_id": "ok-1"},
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "ok", "client_message_id": "ok-1"},
    )
    assert r2.status_code == 200
    assert r2.json()["reused"] is True
    assert r2.json()["assistant_message"]["content"] == "готово"
    assert len(transport.calls) == 1
    with SessionLocal() as session:
        n = (
            session.query(AssistantMessage)
            .filter(
                AssistantMessage.conversation_id == cid,
                AssistantMessage.client_message_id == "ok-1",
            )
            .count()
        )
        assert n == 1


def test_unsupported_provider_no_http(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    transport = _FakeTransport(lambda r: httpx.Response(200, json=_assistant_message(_final("x"))))
    monkeypatch.setenv("ASSISTANT_AGENT_LOOP", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()
    set_loop_http_client_for_tests(httpx.Client(transport=transport))

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(user_id),
        json={"content": "x", "client_message_id": "bad-prov"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "ASSISTANT_AGENT_LOOP_UNSUPPORTED_PROVIDER"
    assert len(transport.calls) == 0


def test_http_budget_cap(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    seq = [
        _tool("get_event_context"),
        _tool("get_available_assessment"),
        _tool("get_company_case_context"),
        _final("cap"),
    ]
    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        return httpx.Response(200, json=_assistant_message(seq[i]))

    transport = _FakeTransport(handler)
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(user_id),
        json={"content": "4steps", "client_message_id": "cap-1"},
    )
    assert r.status_code == 200, r.text
    assert len(transport.calls) <= 4


def test_budget_exhausted_stop(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    monkeypatch.setenv("ASSISTANT_LOOP_MAX_MODEL_HTTP", "1")
    get_settings.cache_clear()
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    # One model slot + tool_request cannot finish → budget/invalid stop, not success final.
    transport = _FakeTransport(
        lambda r: httpx.Response(200, json=_assistant_message(_tool("get_event_context")))
    )
    _enable_loop(monkeypatch, transport)
    monkeypatch.setenv("ASSISTANT_LOOP_MAX_MODEL_HTTP", "1")
    get_settings.cache_clear()

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(user_id),
        json={"content": "budget", "client_message_id": "bud-1"},
    )
    assert r.status_code in {409, 429}
    assert r.json()["error"]["code"].startswith("ASSISTANT_LOOP_")
    assert len(transport.calls) == 1


def test_no_progress_stop(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    # Same tool repeatedly → turn cache / no_progress.
    transport = _FakeTransport(
        lambda r: httpx.Response(200, json=_assistant_message(_tool("get_event_context")))
    )
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(user_id),
        json={"content": "loop", "client_message_id": "np-1"},
    )
    assert r.status_code in {409, 429}
    code = r.json()["error"]["code"]
    assert code.startswith("ASSISTANT_LOOP_")
    assert code in {
        "ASSISTANT_LOOP_NO_PROGRESS",
        "ASSISTANT_LOOP_BUDGET_EXHAUSTED",
        "ASSISTANT_LOOP_INVALID_ACTION",
        "ASSISTANT_LOOP_INCOMPLETE",
    }


def test_duplicate_in_progress_without_reply(api_harness):
    """Same client_message_id with user row but no assistant → IN_PROGRESS, no HTTP.

    Covers the concurrent-duplicate window without threading TestClient
    (portal is not safe for nested requests from two threads).
    """
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    transport = _FakeTransport(
        lambda r: httpx.Response(200, json=_assistant_message(_final("не должен")))
    )
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.add(
            AssistantMessage(
                id=str(uuid4()),
                conversation_id=cid,
                role="user",
                content="in flight",
                blocks_json=[],
                client_message_id="conc-1",
            )
        )
        session.commit()

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(user_id),
        json={"content": "in flight", "client_message_id": "conc-1"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ASSISTANT_MESSAGE_IN_PROGRESS"
    assert len(transport.calls) == 0
    with SessionLocal() as session:
        assert (
            session.query(AssistantMessage)
            .filter(
                AssistantMessage.conversation_id == cid,
                AssistantMessage.client_message_id == "conc-1",
            )
            .count()
            == 1
        )


def test_old_messages_readable_after_loop(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    transport = _FakeTransport(
        lambda r: httpx.Response(200, json=_assistant_message(_final("архив ок")))
    )
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    h = _auth(user_id)
    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "запомни", "client_message_id": "old-1"},
    )
    assert r.status_code == 200
    msgs = client.get(f"/api/v1/assistant/conversations/{cid}/messages", headers=h)
    assert msgs.status_code == 200
    body = msgs.json()
    assert any(m["role"] == "user" and m["content"] == "запомни" for m in body)
    assert any(m["role"] == "assistant" and "архив" in m["content"] for m in body)


# ---------- stage 4.5.1: history integrity + replay contract ----------


def test_history_omits_long_message_without_slicing(api_harness):
    """Long prior message with a trailing caveat is omitted whole; flags mark incomplete."""
    from app.services.assistant.agent_loop.api_integration import (
        MAX_HISTORY_TOTAL_CHARS,
        build_conversation_history_data,
    )

    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    caveat = "ВАЖНАЯ_ОГОВОРКА_В_КОНЦЕ_НЕ_ОБРЕЗАТЬ"
    long_text = ("x" * (MAX_HISTORY_TOTAL_CHARS + 50)) + caveat

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        user = json.loads(request.content.decode())["messages"][-1]["content"]
        marker = "BEGIN_UNTRUSTED_APPLICATION_DATA"
        end_marker = "END_UNTRUSTED_APPLICATION_DATA"
        i0 = user.find(marker)
        i1 = user.find(end_marker)
        assert i0 >= 0 and i1 > i0
        blob = user[i0 + len(marker) : i1]
        # Skip prose line before JSON
        start = blob.find("{")
        data = json.loads(blob[start:])
        captured["data"] = data
        assert "а почему?" in (data.get("user_question") or "")
        hist = data.get("conversation_history") or []
        joined = "\n".join(str(h.get("content") or "") for h in hist)
        # Long prior turn omitted whole — caveat must not appear mid-sliced
        assert caveat not in joined
        assert "…" not in joined
        assert data.get("history_incomplete") is True
        assert int(data.get("history_omitted_count") or 0) >= 1
        return httpx.Response(200, json=_assistant_message(_final("учтено неполное")))

    transport = _FakeTransport(handler)
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.add(
            AssistantMessage(
                id=str(uuid4()),
                conversation_id=cid,
                role="assistant",
                content=long_text,
                blocks_json=[],
                client_message_id=None,
            )
        )
        session.commit()

    # Unit: pack omits whole message (no char slice)
    from types import SimpleNamespace

    pack = build_conversation_history_data(
        [SimpleNamespace(id="m1", role="assistant", content=long_text, blocks_json=[])]
    )
    assert pack.messages == []
    assert pack.history_incomplete is True
    assert pack.history_omitted_count == 1

    r = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=_auth(user_id),
        json={"content": "а почему?", "client_message_id": "hist-1"},
    )
    assert r.status_code == 200, r.text
    assert "а почему?" in (captured["data"].get("user_question") or "")


def test_client_message_id_text_conflict(api_harness):
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    transport = _FakeTransport(
        lambda r: httpx.Response(200, json=_assistant_message(_final("первый")))
    )
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    h = _auth(user_id)
    r1 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "вопрос A", "client_message_id": "same-id"},
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "вопрос B", "client_message_id": "same-id"},
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "ASSISTANT_MESSAGE_ID_CONFLICT"
    assert len(transport.calls) == 1
    assert r2.json()["error"]["details"][0]["reason"] == "text_mismatch"


def test_terminal_failure_replays_stay_incomplete(api_harness):
    """timeout / invalid_action / budget / no_progress → error replay, never final."""
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    def _run_case(*, mid: str, text: str, status: int, code: str, setup, handler) -> None:
        setup()
        transport = _FakeTransport(handler)
        _enable_loop(monkeypatch, transport)
        with SessionLocal() as session:
            from app.models import AssistantConversation
            from uuid import uuid4

            cid = str(uuid4())
            session.add(
                AssistantConversation(
                    id=cid,
                    user_id=user_id,
                    company_id=company_id,
                    event_id=event_id,
                    status="active",
                )
            )
            session.commit()

        h = _auth(user_id)
        r1 = client.post(
            f"/api/v1/assistant/conversations/{cid}/messages",
            headers=h,
            json={"content": text, "client_message_id": mid},
        )
        assert r1.status_code == status, r1.text
        assert r1.json()["error"]["code"] == code
        calls = len(transport.calls)
        r2 = client.post(
            f"/api/v1/assistant/conversations/{cid}/messages",
            headers=h,
            json={"content": text, "client_message_id": mid},
        )
        assert r2.status_code == status
        assert r2.json()["error"]["code"] == code
        assert r2.json()["error"]["details"][0].get("not_ai_final") is True
        assert r2.json()["error"]["details"][0].get("reused") is True
        assert len(transport.calls) == calls

        msgs = client.get(f"/api/v1/assistant/conversations/{cid}/messages", headers=h)
        assert msgs.status_code == 200
        asst = [m for m in msgs.json() if m["role"] == "assistant"]
        assert asst
        last = asst[-1]
        assert any(
            (b.get("data") or {}).get("reason") == "loop_incomplete" for b in last["blocks"]
        )
        assert not any(b.get("type") == "bank_evidence_list" for b in last["blocks"])
        assert not any(
            (b.get("data") or {}).get("internal_reply_link") for b in last["blocks"]
        )

    _run_case(
        mid="to-r",
        text="timeout",
        status=504,
        code="ASSISTANT_LOOP_TIMEOUT",
        setup=lambda: None,
        handler=lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("t", request=r)),
    )

    # Sole model slot is final_only → tool_request stops as invalid_action
    def _inv_setup():
        monkeypatch.setenv("ASSISTANT_LOOP_MAX_MODEL_HTTP", "1")
        get_settings.cache_clear()

    _run_case(
        mid="inv-r",
        text="bad-tool",
        status=409,
        code="ASSISTANT_LOOP_INVALID_ACTION",
        setup=_inv_setup,
        handler=lambda r: httpx.Response(
            200, json=_assistant_message(_tool("get_event_context"))
        ),
    )

    # Repeated same tool → no_progress or budget; replay stays incomplete
    monkeypatch.setenv("ASSISTANT_LOOP_MAX_MODEL_HTTP", "4")
    monkeypatch.setenv("ASSISTANT_LOOP_MAX_TOOL_CALLS", "2")
    get_settings.cache_clear()
    transport = _FakeTransport(
        lambda r: httpx.Response(200, json=_assistant_message(_tool("get_event_context")))
    )
    _enable_loop(monkeypatch, transport)
    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()
    h = _auth(user_id)
    r1 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "np", "client_message_id": "np-r"},
    )
    assert r1.status_code in {409, 429}
    code = r1.json()["error"]["code"]
    assert code.startswith("ASSISTANT_LOOP_")
    calls = len(transport.calls)
    r2 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "np", "client_message_id": "np-r"},
    )
    assert r2.status_code == r1.status_code
    assert r2.json()["error"]["code"] == code
    assert r2.json()["error"]["details"][0].get("reused") is True
    assert r2.json()["error"]["details"][0].get("not_ai_final") is True
    assert len(transport.calls) == calls


def test_new_attempt_after_failure_uses_new_client_id(api_harness):
    """After terminal failure, a new client_message_id may start a new cycle."""
    client, SessionLocal, tmp_path, monkeypatch, engine = api_harness
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        if i == 0:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json=_assistant_message(_final("вторая попытка")))

    transport = _FakeTransport(handler)
    _enable_loop(monkeypatch, transport)

    with SessionLocal() as session:
        from app.models import AssistantConversation
        from uuid import uuid4

        cid = str(uuid4())
        session.add(
            AssistantConversation(
                id=cid, user_id=user_id, company_id=company_id, event_id=event_id, status="active"
            )
        )
        session.commit()

    h = _auth(user_id)
    r1 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "вопрос", "client_message_id": "fail-1"},
    )
    assert r1.status_code == 504
    r2 = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers=h,
        json={"content": "вопрос", "client_message_id": "fail-2"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["assistant_message"]["content"] == "вторая попытка"
    assert len(transport.calls) == 2
