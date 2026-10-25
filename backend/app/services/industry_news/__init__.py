"""Industry news personalization (electronics v1) — additive to twin Impact path."""

from app.services.industry_news.interests import (
    SearchInterest,
    dedupe_interests,
    interests_from_profile,
)
from app.services.industry_news.profile import (
    INDUSTRY_PROFILE_KEY,
    IndustryProfile,
    merge_industry_profile,
    parse_industry_profile,
    put_industry_profile,
)
from app.services.industry_news.relevance import (
    IndustryRelevanceResult,
    evaluate_events_industry_relevance,
    evaluate_industry_relevance,
)

__all__ = [
    "INDUSTRY_PROFILE_KEY",
    "IndustryProfile",
    "IndustryRelevanceResult",
    "SearchInterest",
    "dedupe_interests",
    "evaluate_events_industry_relevance",
    "evaluate_industry_relevance",
    "interests_from_profile",
    "merge_industry_profile",
    "parse_industry_profile",
    "put_industry_profile",
]
