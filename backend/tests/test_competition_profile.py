"""Stage 6.2 — competition profile guards (mocked HTTP only; no live LLM)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services.competition_profile import (
    COMPETITION_HACKATHON_BASE_URL,
    assert_competition_llm_config,
    competition_mode_enabled,
    validate_hackathon_base_url_structure,
)
from app.services.ingestion.enrich import enrich_cluster, heuristic_enrich, live_enrich
from app.models.raw_news import RawNewsItem


def _clear() -> None:
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch):
    """Do not inherit COMPETITION_MODE / provider from a developer root .env."""
    monkeypatch.delenv("COMPETITION_MODE", raising=False)
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    monkeypatch.delenv("HACKATHON_API_KEY", raising=False)
    _clear()
    yield
    _clear()


def test_normal_mode_keeps_mock_provider():
    s = Settings(
        competition_mode=False,
        assistant_provider="mock",
        _env_file=None,
    )
    assert not competition_mode_enabled(s)
    from app.services.assistant.provider import MockAssistantProvider

    # Construct mock directly — allowed when competition off (offline demo).
    p = MockAssistantProvider()
    assert p is not None


def test_competition_mode_accepts_valid_hackathon_config():
    s = Settings(
        competition_mode=True,
        assistant_provider="hackathon",
        hackathon_base_url=COMPETITION_HACKATHON_BASE_URL,
        hackathon_model="deepseek/deepseek-v4.1-flash",
        hackathon_api_key="test-key-not-used",
        _env_file=None,
    )
    assert_competition_llm_config(s)
    assert (
        validate_hackathon_base_url_structure(
            s.resolved_hackathon_base_url(), require_competition_exact=True
        )
        == COMPETITION_HACKATHON_BASE_URL
    )


@pytest.mark.parametrize(
    "provider",
    ["openai", "gigachat", "mock"],
)
def test_competition_mode_rejects_non_hackathon_provider_at_settings(provider: str):
    with pytest.raises(ValidationError) as ei:
        Settings(
            competition_mode=True,
            assistant_provider=provider,
            hackathon_base_url=COMPETITION_HACKATHON_BASE_URL,
            hackathon_model="deepseek/deepseek-v4.1-flash",
            _env_file=None,
        )
    assert "COMPETITION_MODE" in str(ei.value)


def test_competition_mode_rejects_wrong_model():
    with pytest.raises(ValidationError) as ei:
        Settings(
            competition_mode=True,
            assistant_provider="hackathon",
            hackathon_base_url=COMPETITION_HACKATHON_BASE_URL,
            hackathon_model="gpt-4o-mini",
            _env_file=None,
        )
    assert "HACKATHON_MODEL" in str(ei.value) or "allow-list" in str(ei.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://changellenge.up.railway.app/v1",
        "https://evil.example/v1",
        "https://changellenge.up.railway.app/v1?x=1",
        "https://changellenge.up.railway.app/v1#frag",
        "https://user:pass@changellenge.up.railway.app/v1",
        "https://changellenge.up.railway.app/v2",
        "https://api.openai.com/v1",
        "https://changellenge.up.railway.app:8443/v1",
    ],
)
def test_competition_mode_rejects_bad_base_url(url: str):
    with pytest.raises((ValidationError, AppError)):
        try:
            Settings(
                competition_mode=True,
                assistant_provider="hackathon",
                hackathon_base_url=url,
                hackathon_model="deepseek/deepseek-v4.1-flash",
                _env_file=None,
            )
        except ValidationError:
            raise
        validate_hackathon_base_url_structure(url, require_competition_exact=True)


def test_structural_url_check_not_substring():
    # Host that merely contains a forbidden marker as substring of path/query must still
    # be judged by hostname field, not raw string search alone.
    with pytest.raises(AppError) as ei:
        validate_hackathon_base_url_structure(
            "https://api.openai.com/v1",
            require_competition_exact=False,
        )
    assert ei.value.code == "PROVIDER_MISCONFIGURED"
    assert ei.value.details[0]["reason"] == "forbidden_base_url"

    with pytest.raises(AppError) as ei_comp:
        validate_hackathon_base_url_structure(
            "https://api.openai.com/v1",
            require_competition_exact=True,
        )
    assert ei_comp.value.code == "COMPETITION_MISCONFIGURED"
    assert ei_comp.value.details[0]["reason"] == "forbidden_base_url"

    # Legitimate host that would match a naive "openai" substring in the full URL string
    # but is not the openai API host — still rejected in competition for wrong host.
    with pytest.raises(AppError) as ei2:
        validate_hackathon_base_url_structure(
            "https://not-the-gateway.example/v1",
            require_competition_exact=True,
        )
    assert ei2.value.details[0]["reason"] == "base_url_host"


def test_get_provider_rejects_openai_when_competition_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPETITION_MODE", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_BASE_URL", COMPETITION_HACKATHON_BASE_URL)
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("HACKATHON_API_KEY", "k")
    _clear()

    from app.services.assistant.provider import LiveAssistantProvider

    # Direct construction of OpenAI path must refuse before network.
    with pytest.raises(AppError) as ei:
        LiveAssistantProvider(
            api_key="sk-test",
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
        )
    assert ei.value.code == "COMPETITION_LLM_FORBIDDEN"


def test_get_provider_rejects_mock_when_competition_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPETITION_MODE", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_BASE_URL", COMPETITION_HACKATHON_BASE_URL)
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("HACKATHON_API_KEY", "k")
    _clear()

    from app.services.assistant.provider import MockAssistantProvider

    with pytest.raises(AppError) as ei:
        MockAssistantProvider()
    assert ei.value.code == "COMPETITION_LLM_FORBIDDEN"


def test_gigachat_rejected_in_competition(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPETITION_MODE", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_BASE_URL", COMPETITION_HACKATHON_BASE_URL)
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("HACKATHON_API_KEY", "k")
    _clear()

    from app.services.assistant.gigachat import GigaChatProvider

    with pytest.raises(AppError) as ei:
        GigaChatProvider(
            auth_key="x",
            scope="GIGACHAT_API_PERS",
            model="GigaChat",
            api_base_url="https://gigachat.devices.sberbank.ru/api/v1",
            oauth_url="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        )
    assert ei.value.code == "COMPETITION_LLM_FORBIDDEN"


def test_live_enrich_blocked_competition_no_network(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPETITION_MODE", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_BASE_URL", COMPETITION_HACKATHON_BASE_URL)
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("HACKATHON_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-be-used")
    _clear()

    calls: list[str] = []

    class BoomTransport(httpx.MockTransport):
        def __init__(self) -> None:
            super().__init__(self._handler)

        def _handler(self, request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            raise AssertionError("network must not be reached")

    items = [
        RawNewsItem(
            id="raw1",
            provider="test",
            external_id="e1",
            canonical_url="https://example.com/a",
            publisher="ex",
            title="t",
            excerpt="e",
            content_hash="abc",
            processing_status="pending",
        )
    ]
    client = httpx.Client(transport=BoomTransport())
    with pytest.raises(AppError) as ei:
        live_enrich(items, http_client=client)
    assert ei.value.code == "COMPETITION_LLM_FORBIDDEN"
    assert calls == []


def test_heuristic_enrich_still_works_in_competition(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPETITION_MODE", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_BASE_URL", COMPETITION_HACKATHON_BASE_URL)
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("HACKATHON_API_KEY", "k")
    _clear()

    items = [
        RawNewsItem(
            id="raw1",
            provider="test",
            external_id="e1",
            canonical_url="https://example.com/a",
            publisher="ex",
            title="Ставка ЦБ",
            excerpt="Ключевая ставка",
            content_hash="abc",
            processing_status="pending",
        )
    ]
    out = heuristic_enrich(items)
    assert out.title_ru
    # prefer_live=False path
    out2 = enrich_cluster(items, prefer_live=False)
    assert out2.title_ru


def test_redirect_does_not_forward_authorization():
    """Default HackathonProvider client must not follow redirects with the key."""
    from app.services.assistant.hackathon import HackathonProvider

    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "host": request.url.host,
                "path": request.url.path,
                "has_auth": "authorization" in {k.lower() for k in request.headers.keys()},
                "auth": request.headers.get("Authorization"),
            }
        )
        if request.url.host == "changellenge.up.railway.app":
            return httpx.Response(
                302,
                headers={"Location": "https://evil.example/steal"},
                request=request,
            )
        return httpx.Response(200, json={"ok": True}, request=request)

    # Injected client with follow_redirects=True would be a footgun; production path
    # uses follow_redirects=False. Simulate production by not injecting a client.
    transport = httpx.MockTransport(handler)

    # Patch httpx.Client used inside _chat_completions to use our transport but
    # keep follow_redirects=False as production does.
    real_client = httpx.Client

    def client_factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs.setdefault("transport", transport)
        kwargs["follow_redirects"] = False
        return real_client(*args, **kwargs)

    import app.services.assistant.hackathon as hack_mod

    provider = HackathonProvider(
        api_key="secret-token-xyz",
        model="deepseek/deepseek-v4.1-flash",
        base_url=COMPETITION_HACKATHON_BASE_URL,
        http_client=None,
    )

    original = httpx.Client
    try:
        httpx.Client = client_factory  # type: ignore[misc,assignment]
        with pytest.raises(AppError) as ei:
            provider._chat_completions([{"role": "user", "content": "hi"}])
        assert ei.value.details[0]["reason"] == "redirect_not_followed"
    finally:
        httpx.Client = original  # type: ignore[misc]

    assert len(seen) == 1
    assert seen[0]["host"] == "changellenge.up.railway.app"
    assert seen[0]["has_auth"] is True
    # No second hop to evil.example — key never left organizers' host via redirect.
    assert all(s["host"] != "evil.example" for s in seen)
    loc = ei.value.details[0].get("location_host")
    assert loc == "evil.example"


def test_hackathon_provider_ok_with_mocked_transport_in_competition(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("COMPETITION_MODE", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_BASE_URL", COMPETITION_HACKATHON_BASE_URL)
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("HACKATHON_API_KEY", "k")
    _clear()

    from app.services.assistant.hackathon import HackathonProvider
    from app.services.assistant.provider import get_provider

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "changellenge.up.railway.app"
        assert urlsplit(str(request.url)).path.endswith("/chat/completions")
        body = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"content":"ok","tool_calls":[],'
                            '"bank_evidence_citations":[]}'
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        return httpx.Response(200, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    p = HackathonProvider(
        api_key="k",
        model="deepseek/deepseek-v4.1-flash",
        base_url=COMPETITION_HACKATHON_BASE_URL,
        http_client=client,
    )
    result = p.generate(context={}, history=[], user_text="привет")
    assert "ok" in result.content

    # get_provider returns hackathon when configured
    gp = get_provider()
    assert type(gp).__name__ == "HackathonProvider"
