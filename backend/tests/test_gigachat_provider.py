"""GigaChat provider unit tests — no real network."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.assistant.gigachat import (
    GigaChatProvider,
    GigaChatTokenClient,
    extract_gigachat_chat_text,
    parse_gigachat_assistant_payload,
)
from app.services.assistant.provenance import (
    AI_EXPLAIN,
    AI_EXPLAIN_GIGACHAT,
    DEMO_EXPLAIN,
    explanation_basis,
)
from app.services.assistant.provider import get_provider


class _FakeTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.handler(request)


def _json_response(status: int, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(status, json=payload)


def test_explanation_basis_providers():
    assert explanation_basis(provider="mock") == DEMO_EXPLAIN
    assert explanation_basis(provider="openai") == AI_EXPLAIN
    assert explanation_basis(provider="live") == AI_EXPLAIN  # deprecated alias
    assert explanation_basis(provider="gigachat") == AI_EXPLAIN_GIGACHAT
    assert explanation_basis(live=True) == AI_EXPLAIN
    assert explanation_basis(live=False) == DEMO_EXPLAIN


def test_oauth_token_cached(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "gigachat")
    get_settings.cache_clear()
    expires_ms = int((time.time() + 1800) * 1000)
    oauth_hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth"):
            oauth_hits["n"] += 1
            assert request.headers.get("Authorization", "").startswith("Basic ")
            assert b"GIGACHAT_API_PERS" in request.content
            return _json_response(
                200,
                {"access_token": "tok-cached", "expires_at": expires_ms},
            )
        raise AssertionError(f"unexpected {request.url}")

    transport = _FakeTransport(handler)
    client = httpx.Client(transport=transport)
    tokens = GigaChatTokenClient(
        auth_key="dGVzdA==",
        scope="GIGACHAT_API_PERS",
        oauth_url="https://oauth.test/api/v2/oauth",
        http_client=client,
    )
    a = tokens.get_access_token()
    b = tokens.get_access_token()
    assert a == b == "tok-cached"
    assert oauth_hits["n"] == 1
    client.close()
    get_settings.cache_clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()


def test_chat_401_refreshes_token_once():
    expires_ms = int((time.time() + 1800) * 1000)
    state = {"oauth": 0, "chat": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth"):
            state["oauth"] += 1
            return _json_response(
                200,
                {"access_token": f"tok-{state['oauth']}", "expires_at": expires_ms},
            )
        if path.endswith("/chat/completions"):
            state["chat"] += 1
            auth = request.headers.get("Authorization", "")
            if state["chat"] == 1:
                assert auth == "Bearer tok-1"
                return httpx.Response(401, json={"error": "expired"})
            assert auth == "Bearer tok-2"
            return _json_response(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"content": "Ставка влияет на стоимость долга.", "tool_calls": []},
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                },
            )
        raise AssertionError(path)

    transport = _FakeTransport(handler)
    client = httpx.Client(transport=transport)
    provider = GigaChatProvider(
        auth_key="dGVzdA==",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        api_base_url="https://api.test/v1",
        oauth_url="https://oauth.test/api/v2/oauth",
        http_client=client,
    )
    result = provider.generate(
        context={"event": {"title": "Ставка"}, "impact_results": {"impact_score": 30}},
        history=[],
        user_text="Как ставка влияет на компанию?",
    )
    assert "долга" in result.content or "Ставка" in result.content
    assert state["oauth"] == 2
    assert state["chat"] == 2
    # Auth key must never appear in chat Authorization (only Bearer access token)
    chat_auths = [
        c.headers.get("Authorization", "")
        for c in transport.calls
        if c.url.path.endswith("/chat/completions")
    ]
    assert all(a.startswith("Bearer ") for a in chat_auths)
    assert all("dGVzdA==" not in a for a in chat_auths)
    client.close()


def test_gigachat_builds_single_leading_system_message():
    provider = GigaChatProvider(
        auth_key="dGVzdA==",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        api_base_url="https://api.test/v1",
        oauth_url="https://oauth.test/api/v2/oauth",
    )
    messages = provider._build_messages(
        context={"event": {"title": "Ставка"}, "impact_results": {"impact_score": 30}},
        history=[],
        user_text="Как ставка влияет?",
    )
    assert messages[0]["role"] == "system"
    assert sum(1 for m in messages if m["role"] == "system") == 1
    assert messages[-1]["role"] == "user"


def test_normalize_gigachat_response_json_and_plain():
    body = {
        "choices": [
            {"message": {"content": '{"content":"Ок","tool_calls":[{"name":"get_company_impact","arguments":{}}]}'}}
        ]
    }
    raw = extract_gigachat_chat_text(body)
    model = parse_gigachat_assistant_payload(raw)
    assert model.content == "Ок"
    assert model.tool_calls[0]["name"] == "get_company_impact"

    plain = parse_gigachat_assistant_payload("Простое объяснение на русском.")
    assert plain.content.startswith("Простое")
    assert plain.tool_calls == []


def test_parse_strips_markdown_bold_json_wrapper():
    raw = (
        '**{"content":"оценка влияния ключевой ставки",'
        '"tool_calls":[{"name":"get_company_impact","arguments":{}}]}**'
    )
    model = parse_gigachat_assistant_payload(raw)
    assert model.content == "оценка влияния ключевой ставки"
    assert '"tool_calls"' not in model.content
    assert model.tool_calls[0]["name"] == "get_company_impact"


def test_429_and_network_become_provider_unavailable():
    def handler_429(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth"):
            return _json_response(
                200,
                {"access_token": "tok", "expires_at": int((time.time() + 1800) * 1000)},
            )
        return httpx.Response(429, json={"error": "rate"})

    client = httpx.Client(transport=_FakeTransport(handler_429))
    provider = GigaChatProvider(
        auth_key="dGVzdA==",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        api_base_url="https://api.test/v1",
        oauth_url="https://oauth.test/api/v2/oauth",
        http_client=client,
    )
    with pytest.raises(AppError) as ei:
        provider.generate(context={}, history=[], user_text="привет")
    assert ei.value.code == "PROVIDER_UNAVAILABLE"
    assert ei.value.status_code == 503
    client.close()

    def handler_net(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client2 = httpx.Client(transport=_FakeTransport(handler_net))
    tokens = GigaChatTokenClient(
        auth_key="dGVzdA==",
        scope="GIGACHAT_API_PERS",
        oauth_url="https://oauth.test/api/v2/oauth",
        http_client=client2,
    )
    with pytest.raises(AppError) as e2:
        tokens.get_access_token()
    assert e2.value.code == "PROVIDER_UNAVAILABLE"
    client2.close()


def test_missing_gigachat_key_raises_config_error(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "gigachat")
    monkeypatch.delenv("GIGACHAT_AUTH_KEY", raising=False)
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(AppError) as ei:
        get_provider()
    assert ei.value.code == "PROVIDER_UNAVAILABLE"
    assert "GIGACHAT" in (ei.value.message or "").upper() or "настроен" in (ei.value.message or "")
    get_settings.cache_clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()


def test_live_alias_maps_to_openai(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    assert get_settings().normalized_assistant_provider() == "openai"
    get_settings.cache_clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()


def test_mock_still_works_and_no_secret_leak(client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "super-secret-auth-key-value")
    get_settings.cache_clear()
    conv = client.post(
        "/api/v1/events/evt_rate_hike_001/assistant/conversations",
        headers=auth_headers,
        json={"company_id": "cmp_severprom"},
    )
    assert conv.status_code == 200
    body = conv.json()
    assert body["answer_basis"] == "demo_explain"
    blob = json.dumps(body).lower()
    assert "super-secret-auth-key-value" not in blob
    assert "gigachat_auth" not in blob
    assert "api_key" not in blob
    msg = client.post(
        f"/api/v1/assistant/conversations/{body['id']}/messages",
        headers=auth_headers,
        json={"content": "Кратко о влиянии", "client_message_id": "gigachat-mock-safe"},
    )
    assert msg.status_code == 200
    out = msg.json()
    assert "super-secret-auth-key-value" not in json.dumps(out)
    get_settings.cache_clear()


def test_conversation_answer_basis_gigachat_label(client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "gigachat")
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "dGVzdA==")
    get_settings.cache_clear()
    conv = client.post(
        "/api/v1/events/evt_china_export_001/assistant/conversations",
        headers=auth_headers,
        json={"company_id": "cmp_severprom"},
    )
    assert conv.status_code == 200
    assert conv.json()["answer_basis"] == "ai_explain_gigachat"
    assert "dGVzdA==" not in json.dumps(conv.json())
    get_settings.cache_clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()
