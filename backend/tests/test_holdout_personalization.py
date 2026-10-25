"""Hold-out personalization (K04): events outside Policy Rate / China-export seeds."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.industry_news.profile import IndustryProfile
from app.services.industry_news.relevance import evaluate_industry_relevance

# Titles that must NOT be the familiar demo seeds.
FORBIDDEN_SUBSTRINGS = (
    "ключевая ставка",
    "policy rate",
    "14%",
    "китай ограничивает экспорт",
    "china export",
)


def _event(title: str, summary: str = "", **attrs):
    blob = f"{title} {summary}".lower()
    for bad in FORBIDDEN_SUBSTRINGS:
        assert bad not in blob, f"hold-out event must not reuse seed: {bad}"
    return SimpleNamespace(
        id="evt_holdout",
        title=title,
        summary=summary,
        attributes_json=attrs,
        category="macro",
        is_demo=False,
        occurred_at=datetime.now(timezone.utc),
    )


def test_holdout_semiconductor_export_license_matches_electronics():
    profile = IndustryProfile(
        brands=["Samsung"],
        product_categories=["электроника", "полупроводники"],
        procurement_countries=["Южная Корея"],
    )
    event = _event(
        "South Korea tightens export licenses for advanced memory chips",
        "New licensing rules for DRAM and NAND shipments to selected markets.",
        brands=["Samsung"],
        product_categories=["semiconductors", "electronics"],
        industry_event_types=["regulation"],
    )
    result = evaluate_industry_relevance(event, profile)  # type: ignore[arg-type]
    assert result.matched
    assert result.precision in {"exact", "broad"}


def test_holdout_copper_price_no_match_for_phone_retailer():
    profile = IndustryProfile(
        brands=["Apple"],
        product_categories=["смартфоны"],
        sales_markets=["Россия"],
    )
    event = _event(
        "LME copper jumps after mine outage in Chile",
        "Industrial metals rally; no consumer electronics announcement.",
        product_categories=["commodities", "metals"],
    )
    result = evaluate_industry_relevance(event, profile)  # type: ignore[arg-type]
    assert not result.matched


def test_holdout_logistics_strike_matches_procurement_geo():
    profile = IndustryProfile(
        brands=["Apple"],
        product_lines=["iPhone"],
        procurement_countries=["Китай"],
        product_categories=["смартфоны"],
    )
    event = _event(
        "Port congestion delays electronics containers from Shanghai",
        "Waiting times rise for consumer electronics shipments out of China.",
        brands=["Apple"],
        product_categories=["electronics"],
        industry_event_types=["logistics"],
    )
    result = evaluate_industry_relevance(event, profile)  # type: ignore[arg-type]
    assert result.matched


def test_holdout_eu_vat_change_broad_retail_category():
    profile = IndustryProfile(
        activity_role="retailer",
        product_categories=["электроника"],
        sales_markets=["ЕС", "Россия"],
    )
    event = _event(
        "EU proposes higher VAT on consumer electronics repairs",
        "Draft directive may change after-sales economics for device retailers.",
        product_categories=["electronics"],
        industry_event_types=["regulation", "tax"],
    )
    result = evaluate_industry_relevance(event, profile)  # type: ignore[arg-type]
    assert result.matched
    assert result.precision in {"exact", "broad"}
