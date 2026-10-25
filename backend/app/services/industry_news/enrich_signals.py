"""Extract electronics industry signals from title/excerpt — no invented facts."""

from __future__ import annotations

import re
from typing import Any

from app.services.industry_news.profile import BRAND_SYNONYMS, CATEGORY_SYNONYMS, LINE_SYNONYMS
from app.services.industry_news.relevance import _detect_event_types, _norm

_LETTER = re.compile(r"[a-zа-яё0-9]", re.I)


def _hit(blob: str, term: str) -> bool:
    t = _norm(term)
    if not t:
        return False
    if " " in t:
        return t in blob
    return bool(
        re.search(rf"(?<![a-zа-яё0-9]){re.escape(t)}(?![a-zа-яё0-9])", blob)
    )


def extract_industry_signals(title: str, excerpt: str) -> dict[str, Any]:
    blob = _norm(f"{title} {excerpt}")
    brands: list[str] = []
    lines: list[str] = []
    categories: list[str] = []
    for canon, syns in BRAND_SYNONYMS.items():
        if any(_hit(blob, s) for s in syns):
            brands.append(canon.title() if canon != "apple" else "Apple")
    # nicer labels
    brand_labels = {
        "apple": "Apple",
        "samsung": "Samsung",
        "xiaomi": "Xiaomi",
        "huawei": "Huawei",
    }
    brands = [brand_labels.get(b.casefold(), b) for b in brands]

    for canon, syns in LINE_SYNONYMS.items():
        if any(_hit(blob, s) for s in syns):
            lines.append(canon)
    for canon, syns in CATEGORY_SYNONYMS.items():
        if any(_hit(blob, s) for s in syns):
            categories.append(canon)

    event_types = _detect_event_types(blob)
    return {
        "brands": brands,
        "product_lines": lines,
        "product_categories": categories,
        "industry_event_types": event_types,
        "industry_classifier_version": "electronics_v1",
    }
