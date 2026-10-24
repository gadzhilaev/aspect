"""Stage 3.3.1 — mocked HTTP diagnostics / parse / shared retry budget.

Fixtures are **synthetic** (raw company-B response body was not saved in e2e33).
No live network / LLM.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models import Company, CompanyMembership, Event, User
from app.models.assistant import AssistantMessage
from app.services.assistant.bank_evidence_citations import validate_bank_evidence_citations
from app.services.assistant.hackathon import (
    HackathonProvider,
    extract_usage,
    inspect_chat_completions_body,
    is_retryable_bad_response,
    parse_hackathon_assistant_payload,
)
from app.services.assistant.orchestrator import get_or_create_conversation, post_message


# ---------------------------------------------------------------------------
# Synthetic completion shapes (not reconstructed from live B — body was absent)
# ---------------------------------------------------------------------------

_USAGE = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


def _ok_json_content(text: str = "Краткий ответ.", citations: list | None = None) -> str:
    return json.dumps(
        {
            "content": text,
            "tool_calls": [],
            "bank_evidence_citations": list(citations or []),
        },
        ensure_ascii=False,
    )


def _completion(
    *,
    content: Any = None,
    finish_reason: str | None = "stop",
    choices: Any | None = ...,
    message: Any | None = ...,
    extra: dict | None = None,
    usage: dict | None = _USAGE,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if usage is not None:
        body["usage"] = usage
    if choices is ...:
        msg: Any
        if message is ...:
            msg = {"content": content}
        else:
            msg = message
        choice: dict[str, Any] = {"message": msg}
        if finish_reason is not None:
            choice["finish_reason"] = finish_reason
        body["choices"] = [choice]
    elif choices is not None:
        body["choices"] = choices
    if extra:
        body.update(extra)
    return body


class _FakeTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.handler(request)


def _provider(client: httpx.Client) -> HackathonProvider:
    return HackathonProvider(
        api_key="hk-test-key",
        model="deepseek/deepseek-v4.1-flash",
        base_url="https://changellenge.up.railway.app/v1",
        http_client=client,
    )


# ---------- inspect / extract unit ----------


def test_inspect_normal_ok():
    body = _completion(content=_ok_json_content())
    ex = inspect_chat_completions_body(body, http_status=200, request_id="req-1")
    assert ex.failure_reason is None
    assert ex.text
    assert ex.diagnostics.ok is True
    assert ex.diagnostics.choices_count == 1
    assert ex.diagnostics.finish_reason == "stop"
    assert ex.diagnostics.content_type == "str"
    assert ex.diagnostics.content_length and ex.diagnostics.content_length > 0
    assert ex.diagnostics.usage == _USAGE
    assert ex.diagnostics.request_id == "req-1"


def test_inspect_empty_choices():
    ex = inspect_chat_completions_body(_completion(choices=[], usage=_USAGE))
    assert ex.failure_reason == "empty_choices"
    assert ex.diagnostics.usage == _USAGE
    assert is_retryable_bad_response(
        AppError("PROVIDER_BAD_RESPONSE", "x", 502, details=[{"reason": "empty_choices"}])
    )


@pytest.mark.parametrize(
    "content,reason",
    [
        (None, "content_null"),
        ("", "empty_content"),
        ("   ", "empty_content"),
        (123, "unsupported_content_type"),
        ({"text": "no"}, "unsupported_content_type"),
        ([{"type": "image", "image_url": {}}], "unsupported_content_part_type"),
    ],
)
def test_inspect_content_failures(content, reason):
    ex = inspect_chat_completions_body(_completion(content=content, usage=_USAGE))
    assert ex.failure_reason == reason
    assert ex.diagnostics.usage == _USAGE
    assert ex.diagnostics.content_type is not None or reason == "missing_content"


def test_inspect_missing_content_key():
    ex = inspect_chat_completions_body(
        _completion(message={"role": "assistant"}, usage=_USAGE)
    )
    assert ex.failure_reason == "missing_content"
    assert ex.diagnostics.usage == _USAGE


def test_inspect_missing_message():
    body = {"choices": [{"finish_reason": "stop"}], "usage": _USAGE}
    ex = inspect_chat_completions_body(body)
    assert ex.failure_reason == "missing_message"
    assert ex.diagnostics.usage == _USAGE


def test_inspect_finish_reason_length_not_ok():
    text = _ok_json_content("Неполный")
    ex = inspect_chat_completions_body(
        _completion(content=text, finish_reason="length", usage=_USAGE)
    )
    assert ex.failure_reason == "truncated"
    assert ex.text  # text may be present but must not be treated as success
    assert ex.diagnostics.ok is False


def test_inspect_refusal():
    ex = inspect_chat_completions_body(
        _completion(
            message={"content": None, "refusal": "I cannot help with that"},
            usage=_USAGE,
        )
    )
    assert ex.failure_reason == "refusal"
    assert ex.diagnostics.has_refusal is True
    assert not is_retryable_bad_response(
        AppError("PROVIDER_BAD_RESPONSE", "x", 502, details=[{"reason": "refusal"}])
    )


def test_inspect_error_in_http_200():
    body = {"error": {"message": "upstream boom"}, "usage": _USAGE}
    ex = inspect_chat_completions_body(body, http_status=200)
    assert ex.failure_reason == "upstream_error_in_body"
    assert ex.diagnostics.usage == _USAGE


def test_inspect_text_parts_supported():
    body = _completion(
        content=[
            {"type": "text", "text": "Часть один."},
            {"type": "text", "text": "Часть два."},
        ]
    )
    ex = inspect_chat_completions_body(body)
    assert ex.failure_reason is None
    assert "Часть один" in (ex.text or "")
    assert "Часть два" in (ex.text or "")


def test_usage_survives_failed_parse():
    body = {"choices": [], "usage": _USAGE}
    assert extract_usage(body) == _USAGE
    ex = inspect_chat_completions_body(body)
    assert ex.diagnostics.usage == _USAGE


def test_prose_fallback_keeps_empty_citations_for_validation():
    """Prose-fallback is allowed for plain text; citations stay empty (still validated)."""
    model = parse_hackathon_assistant_payload("Просто русский текст без JSON.")
    assert model.content.startswith("Просто")
    assert model.bank_evidence_citations == []
    check = validate_bank_evidence_citations(
        list(model.bank_evidence_citations or []),
        passed_index={},
    )
    assert check.validated == []
    assert check.rejected == []


def test_never_uses_reasoning_content_as_answer():
    body = _completion(
        message={
            "content": "",
            "reasoning_content": "secret chain of thought",
        },
        usage=_USAGE,
    )
    ex = inspect_chat_completions_body(body)
    assert ex.failure_reason == "empty_content"
    assert ex.diagnostics.has_reasoning_content is True
    assert ex.text is None


# ---------- provider generate with diagnostics ----------


def test_provider_normal_and_bad_shapes(hackathon_env_local):
    _ = hackathon_env_local

    def handler_ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_completion(content=_ok_json_content()),
            headers={"x-request-id": "rid-ok"},
        )

    client = httpx.Client(transport=_FakeTransport(handler_ok))
    result = _provider(client).generate(context={}, history=[], user_text="q")
    assert result.content.startswith("Краткий")
    assert result.usage == _USAGE
    client.close()

    cases = [
        (_completion(choices=[]), "empty_choices"),
        (_completion(content=None), "content_null"),
        (_completion(content=""), "empty_content"),
        (_completion(content=42), "unsupported_content_type"),
        (
            _completion(content=_ok_json_content(), finish_reason="length"),
            "truncated",
        ),
        (
            _completion(message={"content": "x", "refusal": "no"}),
            "refusal",
        ),
        ({"error": "boom", "usage": _USAGE}, "upstream_error_in_body"),
    ]
    for payload, reason in cases:
        def handler(request: httpx.Request, p=payload) -> httpx.Response:
            return httpx.Response(200, json=p)

        c = httpx.Client(transport=_FakeTransport(handler))
        with pytest.raises(AppError) as ei:
            _provider(c).generate(context={}, history=[], user_text="q")
        assert ei.value.code == "PROVIDER_BAD_RESPONSE"
        assert ei.value.details[0]["reason"] == reason
        # User-facing message stays generic — no raw payload / reasoning.
        assert "boom" not in ei.value.message
        assert "secret" not in ei.value.message
        if "usage" in payload or payload.get("usage"):
            assert ei.value.details[0].get("usage") == _USAGE or reason == "refusal"
        c.close()


def test_provider_usage_on_unparseable_but_present(hackathon_env_local):
    _ = hackathon_env_local

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [], "usage": _USAGE})

    client = httpx.Client(transport=_FakeTransport(handler))
    with pytest.raises(AppError) as ei:
        _provider(client).generate(context={}, history=[], user_text="q")
    assert ei.value.details[0]["usage"] == _USAGE
    client.close()


@pytest.fixture
def hackathon_env_local(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_API_KEY", "hk-test-key")
    monkeypatch.setenv("HACKATHON_BASE_URL", "https://changellenge.up.railway.app/v1")
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()


# ---------- orchestrator shared one-extra-HTTP budget ----------


def _seed_min(session: Session) -> tuple[User, Company, Event]:
    user = User(
        id=str(uuid4()),
        email=f"diag-{uuid4().hex[:8]}@example.test",
        password_hash=hash_password("DiagPass1!"),
        display_name="Diag",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    company = Company(
        id=str(uuid4()),
        name="ООО Диаг",
        industry="trade",
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
            id=str(uuid4()),
            user_id=user.id,
            company_id=company.id,
            role="owner",
        )
    )
    event = Event(
        id=f"evt_{uuid4().hex[:12]}",
        title="Ставка",
        summary="Тест",
        category="macro",
        event_type="policy",
        severity=50.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        match_countries_json=[],
        match_categories_json=["rates"],
        match_currencies_json=[],
        match_materials_json=[],
        attributes_json={},
        is_demo=True,
    )
    session.add(event)
    session.commit()
    return user, company, event


def test_orchestrator_bad_response_then_ok_citations(
    harness_bank, monkeypatch, hackathon_env_local
):
    """First empty → one shared retry → valid citations validated (not bypassed)."""
    _ = hackathon_env_local
    client_api, SessionLocal, _tmp, monkeypatch, _engine = harness_bank
    _ = client_api

    hits = {"n": 0}
    fid = "frag-diag-1"

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(200, json=_completion(content=""))
        cite = [
            {
                "fragment_id": fid,
                "revision": 1,
            }
        ]
        return httpx.Response(
            200,
            json=_completion(content=_ok_json_content("Ответ после повтора.", cite)),
        )

    transport = _FakeTransport(handler)
    http = httpx.Client(transport=transport)
    provider = _provider(http)

    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider
    )
    # Pass index so citation validates
    passed = {
        fid: {
            "fragment_id": fid,
            "revision": 1,
            "text_kind": "paraphrase",
            "text_plain_for_validation": "x",
            "content_type": "fact",
            "document_title": "D",
            "publication_date": "2026-09-11",
            "publication_date_precision": "day",
            "page_number": 1,
            "source_role": None,
            "qa_method": "ai_vision",
            "document_href": "/d",
            "fragment_href": f"/f/{fid}",
            "content_href": "/c",
        }
    }
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.passed_fragment_index",
        lambda _b: passed,
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.build_conversation_context",
        lambda *_a, **_k: {
            "event": {"title": "t"},
            "company": {"name": "c"},
            "bank_evidence": {"available": True, "status": "available", "fragments": []},
            "assessment_state": "calculation_unavailable",
            "has_impact_calculation": False,
        },
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.slim_live_context",
        lambda ctx: ctx,
    )

    with SessionLocal() as session:
        user, company, event = _seed_min(session)
        user = session.get(User, user.id)
        conv, _ = get_or_create_conversation(
            session, user=user, company_id=company.id, event_id=event.id
        )
        out = post_message(
            session,
            conversation_id=conv.id,
            user=user,
            content="Повтори с цитатой",
        )
        assert hits["n"] == 2
        assert "после повтора" in (out.assistant_message.content or "")
        bank_blocks = [
            b for b in out.assistant_message.blocks if b.type == "bank_evidence_list"
        ]
        assert bank_blocks
        assert bank_blocks[0].data["used"][0]["fragment_id"] == fid
    http.close()


def test_orchestrator_shared_http_budget_no_third_call(
    harness_bank, monkeypatch, hackathon_env_local
):
    """Empty (retryable) then success with bad citation must NOT spend a third HTTP."""
    _ = hackathon_env_local
    _client, SessionLocal, _tmp, monkeypatch, _engine = harness_bank
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(200, json=_completion(content=""))
        # Second: ok text but invented citation → would have triggered citation retry
        # under the old policy; shared budget must block a third call.
        bad = [{"fragment_id": "invented-zzz", "revision": 1}]
        return httpx.Response(
            200,
            json=_completion(content=_ok_json_content("Текст ок.", bad)),
        )

    http = httpx.Client(transport=_FakeTransport(handler))
    provider = _provider(http)
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.passed_fragment_index",
        lambda _b: {},
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.build_conversation_context",
        lambda *_a, **_k: {
            "event": {},
            "company": {},
            "bank_evidence": {"available": True, "status": "available", "fragments": []},
            "assessment_state": "calculation_unavailable",
            "has_impact_calculation": False,
        },
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.slim_live_context",
        lambda ctx: ctx,
    )

    with SessionLocal() as session:
        user, company, event = _seed_min(session)
        user = session.get(User, user.id)
        conv, _ = get_or_create_conversation(
            session, user=user, company_id=company.id, event_id=event.id
        )
        out = post_message(
            session, conversation_id=conv.id, user=user, content="лимит"
        )
        assert hits["n"] == 2
        bank = [b for b in out.assistant_message.blocks if b.type == "bank_evidence_list"]
        if bank:
            assert bank[0].data["used"] == []
            assert bank[0].data["diagnostics"]["rejected"]
    http.close()


def test_no_assistant_message_persisted_on_final_bad_response(
    harness_bank, monkeypatch, hackathon_env_local
):
    _ = hackathon_env_local
    _client, SessionLocal, _tmp, monkeypatch, _engine = harness_bank
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, json=_completion(content=""))

    http = httpx.Client(transport=_FakeTransport(handler))
    provider = _provider(http)
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.get_provider", lambda: provider
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.build_conversation_context",
        lambda *_a, **_k: {
            "event": {},
            "company": {},
            "bank_evidence": {},
            "assessment_state": "calculation_unavailable",
            "has_impact_calculation": False,
        },
    )
    monkeypatch.setattr(
        "app.services.assistant.orchestrator.slim_live_context",
        lambda ctx: ctx,
    )

    with SessionLocal() as session:
        user, company, event = _seed_min(session)
        user = session.get(User, user.id)
        conv, _ = get_or_create_conversation(
            session, user=user, company_id=company.id, event_id=event.id
        )
        conv_id = conv.id
        before = (
            session.query(AssistantMessage)
            .filter(
                AssistantMessage.conversation_id == conv_id,
                AssistantMessage.role == "assistant",
            )
            .count()
        )
        with pytest.raises(AppError) as ei:
            post_message(session, conversation_id=conv_id, user=user, content="fail")
        assert ei.value.code == "PROVIDER_BAD_RESPONSE"
        session.rollback()
        after = (
            session.query(AssistantMessage)
            .filter(
                AssistantMessage.conversation_id == conv_id,
                AssistantMessage.role == "assistant",
            )
            .count()
        )
        assert after == before
        assert hits["n"] == 2  # primary + one shared retry, then fail
    http.close()


def test_budget_and_auth_not_retried(hackathon_env_local):
    _ = hackathon_env_local
    for status, code, payload in [
        (429, "PROVIDER_BUDGET_EXCEEDED", {"error": "Budget has been exceeded"}),
        (401, "PROVIDER_UNAUTHORIZED", {"error": "no"}),
    ]:
        hits = {"n": 0}

        def handler(request: httpx.Request, s=status, p=payload) -> httpx.Response:
            hits["n"] += 1
            return httpx.Response(s, json=p)

        http = httpx.Client(transport=_FakeTransport(handler))
        with pytest.raises(AppError) as ei:
            _provider(http).generate(context={}, history=[], user_text="x")
        assert ei.value.code == code
        assert hits["n"] == 1
        http.close()


@pytest.fixture
def harness_bank(tmp_path, monkeypatch):
    """Minimal DB harness reusing bank-evidence fixture pattern."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from app.db.session import get_db
    from app.main import create_app

    root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "diag331.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "diag-331-secret")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    get_settings.cache_clear()
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")
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
