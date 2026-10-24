"""Human-facing answer provenance — never expose tool names or provider secrets."""

from __future__ import annotations

from typing import Any

# Stable API keys (client maps to Russian copy; never show raw keys in UI).
COMPANY_CALC = "company_calc"
COMPANY_CONTEXT = "company_context"
NEWS_SOURCE = "news_source"
BANK_MATERIAL = "bank_material"
AI_EXPLAIN = "ai_explain"
AI_EXPLAIN_GIGACHAT = "ai_explain_gigachat"
AI_EXPLAIN_HACKATHON = "ai_explain_hackathon"
DEMO_EXPLAIN = "demo_explain"
SAFETY = "safety"

HUMAN_LABELS_RU: dict[str, str] = {
    COMPANY_CALC: "Расчёт компании",
    COMPANY_CONTEXT: "Контекст компании",
    NEWS_SOURCE: "Источник новости",
    BANK_MATERIAL: "Материал банка",
    AI_EXPLAIN: "AI-объяснение",
    AI_EXPLAIN_GIGACHAT: "AI-объяснение · GigaChat",
    # Honest: not OpenAI — organizers' gateway + model shown via answer_model
    AI_EXPLAIN_HACKATHON: "AI-объяснение · hackathon",
    DEMO_EXPLAIN: "Демо-объяснение",
    SAFETY: "Защита запроса",
    # Legacy tokens still may appear in stored messages
    "demo": "Демо-данные",
    "estimate": "Расчётная оценка",
}

# Keys that must never leak to the client UI as-is
FORBIDDEN_RAW = frozenset(
    {
        "openai",
        "api_key",
        "assistant_provider",
        "system",
        "tool",
        "compare_scenarios",
        "get_company_impact",
        "simulate_scenario",
        "live",
        "mock",
        "gigachat",
        "hackathon",
        "openai",
    }
)


def explanation_basis(*, provider: str | None = None, live: bool | None = None) -> str:
    """Map assistant provider → free-text provenance key.

    ``live`` is deprecated (True → openai); prefer ``provider``.
    """
    mode = (provider or "").strip().lower()
    if not mode and live is not None:
        mode = "openai" if live else "mock"
    if mode == "live":
        mode = "openai"
    if mode == "gigachat":
        return AI_EXPLAIN_GIGACHAT
    if mode == "hackathon":
        return AI_EXPLAIN_HACKATHON
    if mode in {"openai", "live"}:
        return AI_EXPLAIN
    return DEMO_EXPLAIN


def labels_for_block(
    *,
    kind: str,
    extra: list[str] | None = None,
    is_demo: bool = False,
) -> list[str]:
    """Build ordered unique provenance labels for a block."""
    out: list[str] = []
    for key in (kind, *(extra or [])):
        if not key or key in out:
            continue
        if key.casefold() in FORBIDDEN_RAW:
            continue
        out.append(key)
    if is_demo and DEMO_EXPLAIN not in out and kind != NEWS_SOURCE:
        # Demo twin data is orthogonal to calc/context; keep calc primary.
        pass
    return out


def sanitize_labels_for_client(labels: list[str] | None) -> list[str]:
    """Drop technical leftovers; map nothing — frontend owns Russian copy."""
    if not labels:
        return []
    cleaned: list[str] = []
    for raw in labels:
        if not isinstance(raw, str):
            continue
        key = raw.strip()
        if not key or key.casefold() in FORBIDDEN_RAW:
            continue
        # Drop snake_case tool-ish leftovers
        if "_" in key and key not in HUMAN_LABELS_RU and key not in {
            COMPANY_CALC,
            COMPANY_CONTEXT,
            NEWS_SOURCE,
            BANK_MATERIAL,
            AI_EXPLAIN,
            AI_EXPLAIN_GIGACHAT,
            AI_EXPLAIN_HACKATHON,
            DEMO_EXPLAIN,
        }:
            # allow our provenance keys with underscore? company_calc has underscore — in HUMAN_LABELS
            if key not in HUMAN_LABELS_RU:
                continue
        if key not in cleaned:
            cleaned.append(key)
    return cleaned


def _strip_explanation_labels(labels: list[str]) -> list[str]:
    """Explanation chips belong on free text, not calc/news tool cards."""
    ban = {DEMO_EXPLAIN, AI_EXPLAIN, AI_EXPLAIN_GIGACHAT, AI_EXPLAIN_HACKATHON, "demo"}
    return [x for x in labels if x not in ban]


def merge_tool_labels(tool_name: str, result: dict[str, Any]) -> list[str]:
    """Provenance for blocks produced from a tool result — one primary kind."""
    existing = _strip_explanation_labels(list(result.get("labels") or []))
    if result.get("type") == "missing_data":
        return [COMPANY_CONTEXT]

    if tool_name in {"compare_scenarios", "simulate_scenario"}:
        return [COMPANY_CALC]

    if tool_name == "get_company_impact":
        return [COMPANY_CALC]

    if tool_name == "get_impact_paths":
        return [COMPANY_CONTEXT]

    if tool_name == "get_event_context":
        return [NEWS_SOURCE]

    if tool_name == "create_decision_draft":
        return [COMPANY_CALC]

    cleaned = sanitize_labels_for_client(_strip_explanation_labels(existing))
    return cleaned[:1] if cleaned else []


FINANCE_MISSING_MESSAGE = (
    "Для финансового сравнения добавьте параметры долга (сумма и доля плавающей ставки) "
    "и/или одну валютную операцию (направление, сумма, валюты)."
)

FINANCE_MISSING_CTA = {
    "label": "Добавить финансовые параметры",
    "href": "/company/setup?step=finance",
}
