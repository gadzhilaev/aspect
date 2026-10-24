"""Answer provenance labels + missing_data CTA + compare idempotency."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AssistantMessage
from app.services.assistant.orchestrator import _blocks_from_tool_result
from app.services.assistant.provenance import (
    AI_EXPLAIN,
    AI_EXPLAIN_HACKATHON,
    COMPANY_CALC,
    COMPANY_CONTEXT,
    DEMO_EXPLAIN,
    FINANCE_MISSING_CTA,
    FINANCE_MISSING_MESSAGE,
    HUMAN_LABELS_RU,
    NEWS_SOURCE,
    explanation_basis,
    sanitize_labels_for_client,
)
from app.services.assistant.provider import MockAssistantProvider
from app.services.assistant.tools import compare_scenarios

COMPANY_ID = "cmp_severprom"
EVENT_CHINA = "evt_china_export_001"
EVENT_RATE = "evt_rate_hike_001"


def test_human_labels_never_expose_secrets():
    assert explanation_basis(live=False) == DEMO_EXPLAIN
    assert explanation_basis(live=True) == AI_EXPLAIN
    assert HUMAN_LABELS_RU[COMPANY_CALC] == "Расчёт компании"
    assert HUMAN_LABELS_RU[COMPANY_CONTEXT] == "Контекст компании"
    assert HUMAN_LABELS_RU[NEWS_SOURCE] == "Источник новости"
    assert HUMAN_LABELS_RU[AI_EXPLAIN] == "AI-объяснение"
    assert HUMAN_LABELS_RU[DEMO_EXPLAIN] == "Демо-объяснение"
    for banned in ("openai", "api_key", "assistant_provider", "compare_scenarios", "live"):
        assert banned not in HUMAN_LABELS_RU
        assert banned not in sanitize_labels_for_client([banned, COMPANY_CALC])


def test_conversation_answer_basis_mock(client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()
    conv = client.post(
        f"/api/v1/events/{EVENT_CHINA}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    )
    assert conv.status_code == 200, conv.text
    body = conv.json()
    assert body["answer_basis"] == "demo_explain"
    blob = str(body).lower()
    for secret in ("openai", "api_key", "sk-", "assistant_api_key"):
        assert secret not in blob


def test_conversation_answer_basis_live_label(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "live")
    get_settings.cache_clear()
    # live is a deprecated alias → openai
    assert get_settings().normalized_assistant_provider() == "openai"
    assert explanation_basis(provider=get_settings().normalized_assistant_provider()) == AI_EXPLAIN
    get_settings.cache_clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()


def test_conversation_answer_basis_hackathon(client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_API_KEY", "hk-test-not-used-for-open")
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    get_settings.cache_clear()
    assert explanation_basis(provider="hackathon") == AI_EXPLAIN_HACKATHON
    conv = client.post(
        f"/api/v1/events/{EVENT_CHINA}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    )
    assert conv.status_code == 200, conv.text
    body = conv.json()
    assert body["answer_basis"] == "ai_explain_hackathon"
    assert body["answer_model"] == "deepseek/deepseek-v4.1-flash"
    blob = str(body)
    assert "hk-test" not in blob
    assert "OPENAI" not in blob.upper() or body["answer_basis"] == "ai_explain_hackathon"
    get_settings.cache_clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    get_settings.cache_clear()


def test_missing_data_finance_has_human_message_and_cta():
    blocks = _blocks_from_tool_result(
        "compare_scenarios",
        {
            "type": "missing_data",
            "assessment_state": "finance_data_required",
            "fields": ["debt_amount"],
            "message": FINANCE_MISSING_MESSAGE,
            "cta": dict(FINANCE_MISSING_CTA),
            "labels": [COMPANY_CONTEXT],
        },
    )
    assert len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "missing_data"
    assert block["data"]["message"] == FINANCE_MISSING_MESSAGE
    assert block["data"]["cta"]["href"] == "/company/setup?step=finance"
    assert "Добавить" in block["data"]["cta"]["label"] or "финанс" in block["data"]["cta"]["label"].lower()
    assert COMPANY_CONTEXT in block["labels"]
    assert "openai" not in str(block).lower()
    assert "api_key" not in str(block).lower()


def test_compare_double_click_same_client_id_no_duplicate_user(
    client: TestClient, auth_headers: dict, db: Session
):
    conv = client.post(
        f"/api/v1/events/{EVENT_CHINA}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    ).json()
    cid = "quick:покажи три сценария"
    a = client.post(
        f"/api/v1/assistant/conversations/{conv['id']}/messages",
        headers=auth_headers,
        json={"content": "Покажи три сценария", "client_message_id": cid},
    )
    b = client.post(
        f"/api/v1/assistant/conversations/{conv['id']}/messages",
        headers=auth_headers,
        json={"content": "Покажи три сценария", "client_message_id": cid},
    )
    assert a.status_code == 200 and b.status_code == 200
    assert b.json()["reused"] is True
    user_count = (
        db.query(AssistantMessage)
        .filter(
            AssistantMessage.conversation_id == conv["id"],
            AssistantMessage.client_message_id == cid,
        )
        .count()
    )
    assert user_count == 1
    # Reload: the stable client_message_id appears once (other history may exist)
    msgs = client.get(
        f"/api/v1/assistant/conversations/{conv['id']}/messages",
        headers=auth_headers,
    ).json()
    with_id = [m for m in msgs if m.get("client_message_id") == cid]
    assert len(with_id) == 1
    assert b.json()["user_message"]["id"] == a.json()["user_message"]["id"]


def test_supply_chain_and_finance_scenario_labels(
    client: TestClient, auth_headers: dict, db: Session
):
    user_id = client.get("/api/v1/users/me", headers=auth_headers).json()["id"]

    china_conv = client.post(
        f"/api/v1/events/{EVENT_CHINA}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    ).json()
    china = compare_scenarios(
        db,
        conversation_id=china_conv["id"],
        event_id=EVENT_CHINA,
        company_id=COMPANY_ID,
        user_id=user_id,
    )
    db.commit()
    assert china.get("assessment_state") == "supply_chain_ready"
    blocks = _blocks_from_tool_result("compare_scenarios", china)
    assert blocks[0]["labels"] == [COMPANY_CALC]
    assert blocks[0]["data"]["source"] == "calculation"

    client.patch(
        f"/api/v1/companies/{COMPANY_ID}/finance",
        headers=auth_headers,
        json={
            "purchase_currencies": ["RUB", "CNY"],
            "optional_finance": {
                "debt_amount": 120_000_000,
                "floating_rate_share_percent": 40,
                "near_term_payments_90d": 18_000_000,
                "fx_purchase_volume": 5_000_000,
                "cash_reserve_days": 45,
            },
        },
    )
    rate_conv = client.post(
        f"/api/v1/events/{EVENT_RATE}/assistant/conversations",
        headers=auth_headers,
        json={"company_id": COMPANY_ID},
    ).json()
    fin = compare_scenarios(
        db,
        conversation_id=rate_conv["id"],
        event_id=EVENT_RATE,
        company_id=COMPANY_ID,
        user_id=user_id,
    )
    db.commit()
    assert fin.get("assessment_state") == "finance_ready"
    fin_blocks = _blocks_from_tool_result("compare_scenarios", fin)
    assert fin_blocks[0]["labels"] == [COMPANY_CALC]
    assert fin_blocks[0]["data"]["source"] == "financial_calculation"
    assert "stop_risk" not in str(fin_blocks[0]["labels"])


def test_mock_provider_scenario_missing_data_uses_finance_copy():
    provider = MockAssistantProvider()
    result = provider.generate(
        context={
            "assessment_state": "finance_data_required",
            "impact": {"assessment_state": "finance_data_required"},
            "event": {"is_demo": True, "labels": []},
            "paths": [],
            "company": {"name": "СеверПром"},
        },
        history=[],
        user_text="Покажи три сценария",
    )
    assert result.blocks
    assert result.blocks[0]["type"] == "missing_data"
    assert result.blocks[0]["data"]["cta"]["href"].endswith("step=finance")
    assert COMPANY_CONTEXT in result.blocks[0]["labels"]
    assert FINANCE_MISSING_MESSAGE in (result.content or "")


def test_mock_free_text_tied_to_event_and_news_source_label():
    provider = MockAssistantProvider()
    result = provider.generate(
        context={
            "assessment_state": "finance_ready",
            "impact": {
                "assessment_state": "finance_ready",
                "impact_score": 72,
                "confidence": 0.81,
                "reason_summary": "Ставка давит на стоимость долга.",
            },
            "event": {"title": "ЦБ повысил ключевую ставку", "is_demo": True, "labels": []},
            "company": {"name": "СеверПром"},
            "sources": [
                {
                    "publisher": "Банк России",
                    "url": "https://www.cbr.ru/example",
                    "published_at": "2026-01-15T00:00:00Z",
                }
            ],
            "paths": [],
        },
        history=[],
        user_text="Как ключевая ставка влияет на мою компанию?",
    )
    assert "СеверПром" in (result.content or "")
    assert "ключев" in (result.content or "").lower() or "ставк" in (result.content or "").lower()
    source_blocks = [b for b in result.blocks if b.get("type") == "source_list"]
    assert source_blocks
    assert source_blocks[0]["labels"] == [NEWS_SOURCE]
    assert DEMO_EXPLAIN not in source_blocks[0]["labels"]
    assert "Банк России" in str(source_blocks[0]["data"])
