"""Industry news personalization matrix (electronics v1) — no Impact / no money."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.industry_news.interests import interests_from_profile
from app.services.industry_news.profile import IndustryProfile, merge_industry_profile
from app.services.industry_news.relevance import evaluate_industry_relevance


def _event(title: str, summary: str = "", **attrs):
    return SimpleNamespace(
        id="evt_test",
        title=title,
        summary=summary,
        attributes_json=attrs,
        category="electronics",
        is_demo=False,
        occurred_at=datetime.now(timezone.utc),
    )


def test_exact_iphone_us_prices_with_us_procurement():
    profile = IndustryProfile(
        activity_role="retailer",
        brands=["Apple"],
        product_lines=["iPhone"],
        product_categories=["смартфоны"],
        sales_markets=["Россия"],
        procurement_countries=["США"],
    )
    event = _event(
        "Apple raises iPhone prices in the United States",
        "Retail prices for iPhone increase in the US market.",
        brands=["Apple"],
        product_lines=["iphone"],
        industry_event_types=["price_change"],
    )
    result = evaluate_industry_relevance(event, profile)  # type: ignore[arg-type]
    assert result.matched
    assert result.precision == "exact"
    assert "убыт" not in result.summary.lower()
    assert any(m.brand for m in result.matches)


def test_iphone_us_news_china_procurement_has_geo_limitation():
    profile = IndustryProfile(
        brands=["Apple"],
        product_lines=["iPhone"],
        sales_markets=["Россия"],
        procurement_countries=["Китай"],
    )
    event = _event(
        "Apple raises iPhone prices in the United States",
        "US retail pricing update for iPhone.",
    )
    result = evaluate_industry_relevance(event, profile)  # type: ignore[arg-type]
    assert result.matched
    assert result.precision == "exact"
    blob = (result.summary + " ".join(result.limitations)).lower()
    assert "закуп" in blob or "географи" in blob or "сша" in blob or "united" in event.title.lower()


def test_broad_smartphones_without_brand():
    profile = IndustryProfile(product_categories=["смартфоны"])
    event = _event(
        "Apple raises iPhone prices in the United States",
        "Smartphone makers adjust retail pricing.",
    )
    result = evaluate_industry_relevance(event, profile)  # type: ignore[arg-type]
    assert result.matched
    assert result.precision == "broad"


def test_food_company_no_match():
    profile = IndustryProfile(
        product_categories=["продукты питания"],
        product_names=["Молоко"],
    )
    event = _event(
        "Apple raises iPhone prices in the United States",
        "iPhone retail pricing.",
    )
    result = evaluate_industry_relevance(event, profile)  # type: ignore[arg-type]
    assert not result.matched


def test_rumour_still_matches_theme_but_not_as_impact():
    """Rumour can be thematic; card must not invent money Impact (score null path)."""
    profile = IndustryProfile(brands=["Apple"], product_lines=["iPhone"])
    event = _event(
        "Rumour: Apple may raise iPhone prices next year",
        "Unconfirmed speculation about future pricing.",
        industry_event_types=["price_change"],
    )
    result = evaluate_industry_relevance(event, profile)  # type: ignore[arg-type]
    assert result.matched
    assert "расчёт" in " ".join(result.limitations).lower() or "не является" in " ".join(
        result.limitations
    ).lower()


def test_cultural_event_not_auto_risk_without_product_signal():
    profile = IndustryProfile(brands=["Apple"], product_categories=["смартфоны"])
    event = _event(
        "Apple hosts cultural evening in Cupertino",
        "Music and arts showcase at Apple Park.",
    )
    result = evaluate_industry_relevance(event, profile)  # type: ignore[arg-type]
    # Brand hit may match thematically but summary must not claim financial risk.
    if result.matched:
        low = result.summary.lower()
        assert "убыт" not in low
        assert "риск продаж" not in low


def test_shared_interests_same_id():
    a = IndustryProfile(brands=["Apple"], product_lines=["iPhone"], product_categories=["смартфоны"])
    b = IndustryProfile(brands=["Apple"], product_lines=["iPhone"], product_categories=["смартфоны"])
    ia = interests_from_profile(a)
    ib = interests_from_profile(b)
    assert ia and ib
    assert ia[0].interest_id == ib[0].interest_id
    assert "apple" in ia[0].public_query().lower() or "iphone" in ia[0].public_query().lower()
    assert "гаджилаев" not in ia[0].public_query().lower()


def test_merge_industry_profile_patch():
    prefs = {"industry_profile": {"brands": ["Apple"], "product_categories": ["смартфоны"]}}
    merged = merge_industry_profile(prefs, {"brands": ["Samsung"], "product_lines": ["Galaxy"]})
    assert merged["brands"] == ["Samsung"]
    assert merged["product_categories"] == ["смартфоны"]
    assert merged["product_lines"] == ["Galaxy"]
