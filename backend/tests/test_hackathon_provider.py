"""Hackathon provider — mocked HTTP only (no live network in pytest)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.assistant.bank_evidence_citations import validate_bank_evidence_citations
from app.services.assistant.hackathon import (
    BUDGET_USER_MESSAGE,
    HACKATHON_ALLOWED_MODELS,
    HackathonProvider,
    assert_hackathon_model,
    extract_usage,
    is_budget_exceeded_payload,
    map_hackathon_http_error,
    parse_hackathon_assistant_payload,
)
from app.services.assistant.provenance import (
    AI_EXPLAIN_HACKATHON,
    explanation_basis,
)
from app.services.assistant.provider import (
    LiveAssistantProvider,
    MockAssistantProvider,
    get_provider,
)
from app.services.ingestion.enrich import enrich_cluster, heuristic_enrich, live_enrich
from app.models.raw_news import RawNewsItem
from datetime import datetime, timezone


class _FakeTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.handler(request)


def _json_response(status: int, payload: dict[str, Any] | str) -> httpx.Response:
    if isinstance(payload, str):
        return httpx.Response(status, text=payload, headers={"Content-Type": "text/plain"})
    return httpx.Response(status, json=payload)


@pytest.fixture
def hackathon_env(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_API_KEY", "hk-test-key")
    monkeypatch.setenv("HACKATHON_BASE_URL", "https://changellenge.up.railway.app/v1")
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    # Ensure openai/gigachat keys cannot be used as silent fallbacks
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ASSISTANT_API_KEY", raising=False)
    monkeypatch.delenv("GIGACHAT_AUTH_KEY", raising=False)
    monkeypatch.delenv("COMPETITION_MODE", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    monkeypatch.delenv("COMPETITION_MODE", raising=False)
    get_settings.cache_clear()


def test_explanation_basis_hackathon():
    assert explanation_basis(provider="hackathon") == AI_EXPLAIN_HACKATHON
    assert "OpenAI" not in AI_EXPLAIN_HACKATHON


def test_allowed_models_and_forbidden():
    for m in HACKATHON_ALLOWED_MODELS:
        assert assert_hackathon_model(m) == m
    with pytest.raises(AppError) as ei:
        assert_hackathon_model("gpt-4o-mini")
    assert ei.value.code == "PROVIDER_MODEL_FORBIDDEN"


def test_budget_detection_not_plain_429():
    assert is_budget_exceeded_payload(
        status_code=429,
        body_text='{"error":"Budget has been exceeded"}',
    )
    assert not is_budget_exceeded_payload(
        status_code=429,
        body_text='{"error":"rate limit exceeded"}',
    )


def test_usage_missing_is_none_not_zero():
    assert extract_usage({}) is None
    assert extract_usage({"usage": {}}) is None
    assert extract_usage({"usage": {"prompt_tokens": 3, "completion_tokens": 5}}) == {
        "prompt_tokens": 3,
        "completion_tokens": 5,
    }


def test_get_provider_hackathon(hackathon_env):
    p = get_provider()
    assert isinstance(p, HackathonProvider)
    assert not isinstance(p, LiveAssistantProvider)
    assert not isinstance(p, MockAssistantProvider)
    assert p.base_url == "https://changellenge.up.railway.app/v1"
    assert p.model == "deepseek/deepseek-v4.1-flash"


def test_missing_key(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(AppError) as ei:
        get_provider()
    assert ei.value.code == "PROVIDER_UNAVAILABLE"
    assert "missing_hackathon_api_key" in str(ei.value.details)
    get_settings.cache_clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()


def test_forbidden_model_in_env(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_API_KEY", "hk-test")
    monkeypatch.setenv("HACKATHON_MODEL", "gpt-4o-mini")
    get_settings.cache_clear()
    with pytest.raises(AppError) as ei:
        get_provider()
    assert ei.value.code == "PROVIDER_MODEL_FORBIDDEN"
    get_settings.cache_clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()


def test_success_chat_completions_url_model_bearer(hackathon_env):
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        assert str(request.url).startswith(
            "https://changellenge.up.railway.app/v1/chat/completions"
        )
        assert "api.openai.com" not in str(request.url)
        assert "gigachat" not in str(request.url).lower()
        assert request.headers.get("Authorization") == "Bearer hk-test-key"
        # Key must not appear in query
        assert "hk-test-key" not in str(request.url)
        body = json.loads(request.content.decode())
        assert body["model"] == "deepseek/deepseek-v4.1-flash"
        assert "response_format" not in body
        assert "tools" not in body
        assert body.get("messages")
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "content": "Кратко по событию для компании.",
                                "tool_calls": [],
                                "bank_evidence_citations": [],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        }
        return _json_response(200, payload)

    transport = _FakeTransport(handler)
    client = httpx.Client(transport=transport)
    provider = HackathonProvider(
        api_key="hk-test-key",
        model="deepseek/deepseek-v4.1-flash",
        base_url="https://changellenge.up.railway.app/v1",
        http_client=client,
    )
    result = provider.generate(
        context={"event": {"title": "Тест"}, "company": {"name": "ООО"}},
        history=[],
        user_text="Почему это влияет?",
    )
    assert result.content.startswith("Кратко")
    assert result.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "total_tokens": 14,
    }
    assert hits["n"] == 1
    client.close()


def test_budget_exceeded_no_retry(hackathon_env):
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return _json_response(429, {"error": "Budget has been exceeded"})

    transport = _FakeTransport(handler)
    client = httpx.Client(transport=transport)
    provider = HackathonProvider(
        api_key="hk-test-key",
        model="deepseek/deepseek-v4.1-flash",
        base_url="https://changellenge.up.railway.app/v1",
        http_client=client,
    )
    with pytest.raises(AppError) as ei:
        provider.generate(context={}, history=[], user_text="привет")
    assert ei.value.code == "PROVIDER_BUDGET_EXCEEDED"
    assert ei.value.message == BUDGET_USER_MESSAGE
    assert hits["n"] == 1  # no internal retry
    client.close()


def test_plain_429_is_rate_limit_not_budget(hackathon_env):
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(429, {"error": "Too Many Requests"})

    client = httpx.Client(transport=_FakeTransport(handler))
    provider = HackathonProvider(
        api_key="hk-test-key",
        model="deepseek/deepseek-v4.1-flash",
        base_url="https://changellenge.up.railway.app/v1",
        http_client=client,
    )
    with pytest.raises(AppError) as ei:
        provider.generate(context={}, history=[], user_text="привет")
    assert ei.value.code == "PROVIDER_RATE_LIMIT"
    assert "бюджет" not in ei.value.message.lower()
    client.close()


def test_401_and_5xx(hackathon_env):
    def handler_401(request: httpx.Request) -> httpx.Response:
        return _json_response(401, {"error": "invalid key"})

    client = httpx.Client(transport=_FakeTransport(handler_401))
    provider = HackathonProvider(
        api_key="hk-test-key",
        model="deepseek/deepseek-v4.1-flash",
        base_url="https://changellenge.up.railway.app/v1",
        http_client=client,
    )
    with pytest.raises(AppError) as ei:
        provider.generate(context={}, history=[], user_text="x")
    assert ei.value.code == "PROVIDER_UNAUTHORIZED"
    client.close()

    def handler_500(request: httpx.Request) -> httpx.Response:
        return _json_response(500, {"error": "boom"})

    client = httpx.Client(transport=_FakeTransport(handler_500))
    provider = HackathonProvider(
        api_key="hk-test-key",
        model="deepseek/deepseek-v4.1-flash",
        base_url="https://changellenge.up.railway.app/v1",
        http_client=client,
    )
    with pytest.raises(AppError) as ei:
        provider.generate(context={}, history=[], user_text="x")
    assert ei.value.code == "PROVIDER_UNAVAILABLE"
    client.close()


def test_timeout(hackathon_env):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = httpx.Client(transport=_FakeTransport(handler))
    provider = HackathonProvider(
        api_key="hk-test-key",
        model="deepseek/deepseek-v4.1-flash",
        base_url="https://changellenge.up.railway.app/v1",
        http_client=client,
    )
    with pytest.raises(AppError) as ei:
        provider.generate(context={}, history=[], user_text="x")
    assert ei.value.code == "PROVIDER_UNAVAILABLE"
    assert ei.value.details[0]["reason"] == "timeout"
    client.close()


def test_bad_structured_payload(hackathon_env):
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            200,
            {"choices": [{"message": {"content": ""}}]},
        )

    client = httpx.Client(transport=_FakeTransport(handler))
    provider = HackathonProvider(
        api_key="hk-test-key",
        model="deepseek/deepseek-v4.1-flash",
        base_url="https://changellenge.up.railway.app/v1",
        http_client=client,
    )
    with pytest.raises(AppError) as ei:
        provider.generate(context={}, history=[], user_text="x")
    assert ei.value.code == "PROVIDER_BAD_RESPONSE"
    client.close()


def test_bank_citations_still_validated(hackathon_env):
    fid = "frag-abc"
    content = json.dumps(
        {
            "content": "Ссылка на материал банка.",
            "tool_calls": [],
            "bank_evidence_citations": [
                {"fragment_id": fid, "revision": 1, "quoted_text": "точная цитата"},
                {"fragment_id": "invented", "revision": 1},
            ],
        },
        ensure_ascii=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {"choices": [{"message": {"content": content}}]})

    client = httpx.Client(transport=_FakeTransport(handler))
    provider = HackathonProvider(
        api_key="hk-test-key",
        model="deepseek/deepseek-v4.1-flash",
        base_url="https://changellenge.up.railway.app/v1",
        http_client=client,
    )
    result = provider.generate(context={}, history=[], user_text="банк")
    passed = {
        fid: {
            "fragment_id": fid,
            "revision": 1,
            "text_kind": "exact_quote",
            "text_plain_for_validation": "точная цитата",
            "content_type": "fact",
            "document_title": "Doc",
            "publication_date": "2026-09-11",
            "publication_date_precision": "day",
            "page_number": 1,
            "source_role": None,
            "qa_method": "ai_vision",
            "document_href": "/api/v1/bank-materials/documents/d1",
            "fragment_href": f"/api/v1/bank-materials/fragments/{fid}",
            "content_href": "/api/v1/bank-materials/files/f1/content",
        }
    }
    check = validate_bank_evidence_citations(
        list(result.bank_evidence_citations),
        passed_index=passed,
    )
    assert [v.fragment_id for v in check.validated] == [fid]
    assert any(r.fragment_id == "invented" for r in check.rejected)
    client.close()


def test_no_openai_host_when_misconfigured_base(hackathon_env):
    """Normal mode: forbidden host → PROVIDER_MISCONFIGURED (no HTTP)."""
    with pytest.raises(AppError) as ei:
        HackathonProvider(
            api_key="hk",
            model="deepseek/deepseek-v4.1-flash",
            base_url="https://api.openai.com/v1",
        )
    assert ei.value.code == "PROVIDER_MISCONFIGURED"
    assert (ei.value.details or [{}])[0].get("reason") == "forbidden_base_url"


def test_no_openai_host_competition_mode(monkeypatch):
    """Competition mode: forbidden host → COMPETITION_MISCONFIGURED (no HTTP)."""
    monkeypatch.setenv("COMPETITION_MODE", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_API_KEY", "hk-test-key")
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("HACKATHON_BASE_URL", "https://changellenge.up.railway.app/v1")
    get_settings.cache_clear()
    try:
        with pytest.raises(AppError) as ei:
            HackathonProvider(
                api_key="hk",
                model="deepseek/deepseek-v4.1-flash",
                base_url="https://api.openai.com/v1",
            )
        assert ei.value.code == "COMPETITION_MISCONFIGURED"
        assert (ei.value.details or [{}])[0].get("reason") == "forbidden_base_url"
    finally:
        monkeypatch.delenv("COMPETITION_MODE", raising=False)
        get_settings.cache_clear()


def test_ingestion_live_blocked_heuristic_ok(hackathon_env):
    item = RawNewsItem(
        id="src1",
        provider="rss",
        external_id="ext-1",
        publisher="Тест",
        title="ЦБ сохранил ключевую ставку",
        excerpt="Ставка без изменений",
        canonical_url="https://example.test/1",
        published_at=datetime.now(timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        content_hash="deadbeef",
        processing_status="pending",
        payload_json={},
    )
    with pytest.raises(AppError) as ei:
        live_enrich([item])
    assert ei.value.code == "INGESTION_LIVE_BLOCKED"

    with pytest.raises(AppError) as ei2:
        enrich_cluster([item], prefer_live=True)
    assert ei2.value.code == "INGESTION_LIVE_BLOCKED"

    heur = enrich_cluster([item], prefer_live=False)
    assert heur.title_ru == item.title
    assert heuristic_enrich([item]).title_ru == item.title


def test_parse_plain_prose():
    model = parse_hackathon_assistant_payload("Просто русский текст без JSON.")
    assert model.content.startswith("Просто")
    assert model.tool_calls == []


def test_map_budget_from_response():
    resp = httpx.Response(402, text="Budget has been exceeded")
    err = map_hackathon_http_error(resp)
    assert err.code == "PROVIDER_BUDGET_EXCEEDED"
    assert err.message == BUDGET_USER_MESSAGE
