"""Normalized search interests from industry profile — shared across companies.

Never sends private company name, contacts, or finance to external search.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable

from app.services.industry_news.profile import (
    BRAND_SYNONYMS,
    CATEGORY_SYNONYMS,
    LINE_SYNONYMS,
    IndustryProfile,
)


EVENT_TYPES_V1: tuple[str, ...] = (
    "price_change",
    "product_launch",
    "product_discontinuation",
    "shortage",
    "import_export_restriction",
    "recall",
    "distribution_change",
)


@dataclass(frozen=True)
class SearchInterest:
    """One deduped interest key used by scheduler / GDELT query builder."""

    interest_id: str
    category: str | None
    brand: str | None
    product_line: str | None
    event_types: tuple[str, ...]
    query_terms: tuple[str, ...]

    def public_query(self) -> str:
        """Safe public query string — product terms only, no company PII."""
        return " OR ".join(self.query_terms[:8])


def _canon_brand(name: str) -> str | None:
    n = name.strip().casefold()
    for canon, syns in BRAND_SYNONYMS.items():
        if n == canon or n in syns:
            return canon
    if len(n) >= 2:
        return n
    return None


def _canon_category(name: str) -> str | None:
    n = name.strip().casefold()
    for canon, syns in CATEGORY_SYNONYMS.items():
        if n == canon or any(n == s or s in n or n in s for s in syns):
            return canon
    return None


def _canon_line(name: str) -> str | None:
    n = name.strip().casefold()
    for canon, syns in LINE_SYNONYMS.items():
        if n == canon or n in syns:
            return canon
    return None


def _terms_for(
    *,
    category: str | None,
    brand: str | None,
    line: str | None,
) -> tuple[str, ...]:
    terms: list[str] = []
    if brand:
        terms.extend(BRAND_SYNONYMS.get(brand, (brand,)))
    if line:
        terms.extend(LINE_SYNONYMS.get(line, (line,)))
    if category:
        terms.extend(CATEGORY_SYNONYMS.get(category, (category,))[:4])
    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        k = t.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return tuple(out)


def _interest_id(category: str | None, brand: str | None, line: str | None) -> str:
    raw = f"{category or ''}|{brand or ''}|{line or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def interests_from_profile(profile: IndustryProfile) -> list[SearchInterest]:
    """Build shared interests; identical profiles share interest_id."""
    categories = [
        c
        for c in (_canon_category(x) for x in profile.product_categories)
        if c
    ]
    # Also infer category from free-text product names
    for name in profile.product_names:
        c = _canon_category(name)
        if c and c not in categories:
            categories.append(c)
    brands = [b for b in (_canon_brand(x) for x in profile.brands) if b]
    # Infer brand from product names / lines
    for name in list(profile.product_names) + list(profile.product_lines):
        b = _canon_brand(name)
        if b and b not in brands:
            brands.append(b)
    lines = [ln for ln in (_canon_line(x) for x in profile.product_lines) if ln]
    for name in profile.product_names:
        ln = _canon_line(name)
        if ln and ln not in lines:
            lines.append(ln)

    if not categories and not brands and not lines:
        return []

    if not categories:
        categories = [None]  # type: ignore[list-item]

    interests: list[SearchInterest] = []
    seen: set[str] = set()
    cats: Iterable[str | None] = categories or [None]
    brand_opts: Iterable[str | None] = brands or [None]
    line_opts: Iterable[str | None] = lines or [None]

    # Prefer brand×line, else brand×category, else category-only
    combos: list[tuple[str | None, str | None, str | None]] = []
    if brands or lines:
        for b in brand_opts:
            for ln in line_opts:
                if b is None and ln is None:
                    continue
                combos.append((categories[0] if categories else None, b, ln))
    else:
        for c in cats:
            combos.append((c, None, None))

    for category, brand, line in combos:
        iid = _interest_id(category, brand, line)
        if iid in seen:
            continue
        terms = _terms_for(category=category, brand=brand, line=line)
        if not terms:
            continue
        seen.add(iid)
        interests.append(
            SearchInterest(
                interest_id=iid,
                category=category,
                brand=brand,
                product_line=line,
                event_types=EVENT_TYPES_V1,
                query_terms=terms,
            )
        )
    return interests


def dedupe_interests(items: Iterable[SearchInterest]) -> list[SearchInterest]:
    by_id: dict[str, SearchInterest] = {}
    for it in items:
        by_id.setdefault(it.interest_id, it)
    return list(by_id.values())
