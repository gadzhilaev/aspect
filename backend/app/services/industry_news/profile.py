"""Industry personalization profile — additive prefs under company settings.

Stored in ``CompanyProfileSettings.preferences_json["industry_profile"]``.
Does not overwrite registry / case competition data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


INDUSTRY_PROFILE_KEY = "industry_profile"

# Synonyms for electronics v1 matching (RU/EN).
CATEGORY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "смартфоны": (
        "смартфон",
        "смартфоны",
        "smartphone",
        "smartphones",
        "mobile phone",
        "телефоны",
        "телефон",
        "handset",
    ),
    "электроника": (
        "электроника",
        "electronics",
        "consumer electronics",
        "бытовая электроника",
    ),
    "комплектующие": (
        "комплектующие",
        "components",
        "полупроводники",
        "semiconductor",
        "chip",
        "чипы",
    ),
}

BRAND_SYNONYMS: dict[str, tuple[str, ...]] = {
    "apple": ("apple", "эппл", "iphone", "айфон", "ipad", "макбук", "macbook"),
    "samsung": ("samsung", "самсунг", "galaxy"),
    "xiaomi": ("xiaomi", "сяоми", "redmi", "poco"),
    "huawei": ("huawei", "хуавей", "honor"),
}

LINE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "iphone": ("iphone", "айфон"),
    "galaxy": ("galaxy", "галэкси"),
    "pixel": ("pixel", "пиксель"),
}


def _norm_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        s = " ".join(str(item or "").strip().split())
        if not s:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


@dataclass
class IndustryProfile:
    """Manual industry signals for thematic news matching."""

    activity_role: str = ""  # retailer | manufacturer | distributor | other | ""
    product_categories: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    product_lines: list[str] = field(default_factory=list)
    sales_markets: list[str] = field(default_factory=list)
    procurement_countries: list[str] = field(default_factory=list)
    purchase_currencies: list[str] = field(default_factory=list)
    # Free-text product names from twin nodes (not brands).
    product_names: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            [
                self.activity_role,
                self.product_categories,
                self.brands,
                self.product_lines,
                self.sales_markets,
                self.procurement_countries,
                self.product_names,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_role": self.activity_role or "",
            "product_categories": list(self.product_categories),
            "brands": list(self.brands),
            "product_lines": list(self.product_lines),
            "sales_markets": list(self.sales_markets),
            "procurement_countries": list(self.procurement_countries),
            "purchase_currencies": list(self.purchase_currencies),
        }


def parse_industry_profile(preferences: dict[str, Any] | None) -> IndustryProfile:
    raw = (preferences or {}).get(INDUSTRY_PROFILE_KEY)
    if not isinstance(raw, dict):
        raw = {}
    role = str(raw.get("activity_role") or "").strip().lower()
    if role not in {"retailer", "manufacturer", "distributor", "other", ""}:
        role = ""
    return IndustryProfile(
        activity_role=role,
        product_categories=_norm_list(raw.get("product_categories")),
        brands=_norm_list(raw.get("brands")),
        product_lines=_norm_list(raw.get("product_lines")),
        sales_markets=_norm_list(raw.get("sales_markets")),
        procurement_countries=_norm_list(raw.get("procurement_countries")),
        purchase_currencies=_norm_list(raw.get("purchase_currencies")),
    )


def merge_industry_profile(
    existing: dict[str, Any] | None,
    patch: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge PATCH into industry_profile (absent key → keep; null/[] → clear)."""
    base = parse_industry_profile(existing).to_dict()
    if not isinstance(patch, dict):
        return base
    for key in (
        "activity_role",
        "product_categories",
        "brands",
        "product_lines",
        "sales_markets",
        "procurement_countries",
        "purchase_currencies",
    ):
        if key not in patch:
            continue
        val = patch[key]
        if val is None:
            base[key] = "" if key == "activity_role" else []
        elif key == "activity_role":
            role = str(val).strip().lower()
            base[key] = (
                role
                if role in {"retailer", "manufacturer", "distributor", "other", ""}
                else base[key]
            )
        elif isinstance(val, list):
            base[key] = _norm_list(val)
        elif isinstance(val, str) and key != "activity_role":
            base[key] = _norm_list([val])
    return base


def put_industry_profile(
    preferences: dict[str, Any] | None,
    industry: dict[str, Any],
) -> dict[str, Any]:
    prefs = dict(preferences or {})
    prefs[INDUSTRY_PROFILE_KEY] = industry
    return prefs
