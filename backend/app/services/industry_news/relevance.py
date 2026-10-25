"""Industry thematic relevance — explainable, no EventImpact / no money claim."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.models import Event
from app.services.industry_news.profile import (
    BRAND_SYNONYMS,
    CATEGORY_SYNONYMS,
    LINE_SYNONYMS,
    IndustryProfile,
)

MatchPrecision = Literal["exact", "broad", "none"]

_WORD = re.compile(r"[a-zа-яё0-9]+", re.I)

_EVENT_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "price_change": (
        "price",
        "prices",
        "цен",
        "цена",
        "подорож",
        "подешев",
        " inflat",
        "raise prices",
        "hike",
    ),
    "shortage": ("shortage", "дефицит", "supply chain", "перебо", "нехватк"),
    "import_export_restriction": (
        "export ban",
        "import ban",
        "санкц",
        "restriction",
        "ограничен",
        "embargo",
    ),
    "recall": ("recall", "отзыв", "отзыва продукции"),
    "product_launch": ("launch", "анонс", "unveil", "выпуск", "представил"),
    "product_discontinuation": (
        "discontinu",
        "снят с производства",
        "end of life",
        "eol",
    ),
    "distribution_change": (
        "distributor",
        "дистрибуц",
        "reseller",
        "условия продаж",
    ),
}


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _blob(event: Event) -> str:
    attrs = event.attributes_json if isinstance(event.attributes_json, dict) else {}
    parts = [
        event.title or "",
        event.summary or "",
        " ".join(str(x) for x in (attrs.get("materials") or [])),
        " ".join(str(x) for x in (attrs.get("brands") or [])),
        " ".join(str(x) for x in (attrs.get("product_lines") or [])),
        " ".join(str(x) for x in (attrs.get("product_categories") or [])),
        str(attrs.get("industry_event_type") or ""),
    ]
    return _norm(" ".join(parts))


def _contains_term(blob: str, term: str) -> bool:
    t = _norm(term)
    if not t:
        return False
    if " " in t:
        return t in blob
    # Word-boundary-ish for single tokens (avoid «apple» in «pineapple» via latin;
    # for Cyrillic use substring with letter edges).
    if re.search(rf"(?<![a-zа-яё0-9]){re.escape(t)}(?![a-zа-яё0-9])", blob):
        return True
    return False


def _any_syn(blob: str, syns: tuple[str, ...]) -> list[str]:
    hits = [s for s in syns if _contains_term(blob, s)]
    return hits


@dataclass
class IndustryMatch:
    rule_id: str
    precision: MatchPrecision
    brand: str | None = None
    category: str | None = None
    product_line: str | None = None
    event_type: str | None = None
    geography_note: str | None = None
    explanation: str = ""
    event_signals: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class IndustryRelevanceResult:
    matched: bool
    precision: MatchPrecision
    summary: str
    matches: list[IndustryMatch] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_profile_relevance_dict(self) -> dict[str, Any]:
        """Shape compatible with ProfileRelevanceOut consumers."""
        return {
            "matched": self.matched,
            "label": "По вашим продуктам",
            "summary": self.summary,
            "matches": [
                {
                    "rule_id": m.rule_id,
                    "theme": "industry_electronics",
                    "product_code": (m.brand or m.category or m.product_line or "product"),
                    "product_label": (
                        m.brand
                        or m.product_line
                        or m.category
                        or "Продукт"
                    ),
                    "product_status": m.precision,
                    "explanation": m.explanation,
                    "event_theme_signals": list(m.event_signals),
                    "limitations": list(m.limitations),
                }
                for m in self.matches
            ],
            "limitations": list(self.limitations),
            "provenance": None,
        }


def _detect_event_types(blob: str) -> list[str]:
    found: list[str] = []
    for et, hints in _EVENT_TYPE_HINTS.items():
        if any(h.strip() and h.strip().lower() in blob for h in hints):
            found.append(et)
    return found


def _country_hits(blob: str, countries: list[str]) -> list[str]:
    hits = []
    for c in countries:
        if _contains_term(blob, c):
            hits.append(c)
    return hits


def evaluate_industry_relevance(
    event: Event,
    profile: IndustryProfile,
) -> IndustryRelevanceResult:
    if profile.is_empty():
        return IndustryRelevanceResult(
            matched=False,
            precision="none",
            summary="",
            limitations=["В профиле нет категорий, брендов или продуктов для отраслевого отбора."],
        )

    blob = _blob(event)
    attrs = event.attributes_json if isinstance(event.attributes_json, dict) else {}
    event_types = list(attrs.get("industry_event_types") or []) or _detect_event_types(blob)

    matches: list[IndustryMatch] = []
    limitations: list[str] = [
        "Тематическое совпадение не является расчётом влияния и не денежный ущерб.",
        "Отсутствие бренда в профиле не значит, что компания им не торгует.",
    ]

    # Exact: brand or product line hit
    for brand in profile.brands:
        key = brand.casefold()
        syns = BRAND_SYNONYMS.get(key, (brand,))
        hits = _any_syn(blob, syns)
        if not hits:
            continue
        geo_note = None
        sales_hit = _country_hits(blob, profile.sales_markets)
        proc_hit = _country_hits(blob, profile.procurement_countries)
        lim = list(limitations)
        if sales_hit and not proc_hit:
            geo_note = (
                f"Новость упоминает рынок продаж ({', '.join(sales_hit)}); "
                "связь с вашими закупками не подтверждена."
            )
            lim.append(geo_note)
        elif proc_hit:
            geo_note = (
                f"Упоминается география закупок ({', '.join(proc_hit)}); "
                "условия поставщика всё равно нужно проверить отдельно."
            )
            lim.append(geo_note)
        elif profile.procurement_countries:
            geo_note = (
                "Страна действия новости может отличаться от вашей географии закупок."
            )
            lim.append(geo_note)
        et = event_types[0] if event_types else None
        matches.append(
            IndustryMatch(
                rule_id=f"brand_{key}",
                precision="exact",
                brand=brand,
                event_type=et,
                geography_note=geo_note,
                explanation=f"В профиле указан бренд «{brand}»; публикация его упоминает.",
                event_signals=hits[:5],
                limitations=lim,
            )
        )

    for line in profile.product_lines:
        key = line.casefold()
        syns = LINE_SYNONYMS.get(key, (line,))
        hits = _any_syn(blob, syns)
        if not hits:
            continue
        if any(m.product_line and m.product_line.casefold() == key for m in matches):
            continue
        matches.append(
            IndustryMatch(
                rule_id=f"line_{key}",
                precision="exact",
                product_line=line,
                event_type=event_types[0] if event_types else None,
                explanation=f"В профиле указана линейка «{line}»; публикация её упоминает.",
                event_signals=hits[:5],
                limitations=list(limitations),
            )
        )

    # Also match free-text product names against blob
    for name in profile.product_names:
        if len(name) < 3:
            continue
        if not _contains_term(blob, name):
            # try brand/line inference
            continue
        matches.append(
            IndustryMatch(
                rule_id=f"product_name_{name.casefold()[:24]}",
                precision="exact",
                explanation=f"Совпадение с указанным продуктом «{name}».",
                event_signals=[name],
                limitations=list(limitations),
            )
        )

    # Broad: category only (no brand required)
    if not matches:
        cats = list(profile.product_categories)
        for name in profile.product_names:
            # infer category from product name tokens
            n = name.casefold()
            for canon, syns in CATEGORY_SYNONYMS.items():
                if any(s in n for s in syns) and canon not in cats:
                    cats.append(canon)
        for cat in cats:
            key = cat.casefold()
            syns = CATEGORY_SYNONYMS.get(key, (cat,))
            hits = _any_syn(blob, syns)
            # Also hit known brands in news when profile has category smartphones
            brand_hits: list[str] = []
            if key in {"смартфоны", "электроника"}:
                for bcanon, bsyns in BRAND_SYNONYMS.items():
                    bh = _any_syn(blob, bsyns)
                    if bh:
                        brand_hits.extend(bh[:2])
            if not hits and not brand_hits:
                continue
            lim = list(limitations)
            lim.append(
                "Бренд в профиле не указан — совпадение широкое (категория), "
                "точность ниже точного совпадения по бренду."
            )
            matches.append(
                IndustryMatch(
                    rule_id=f"category_{key}",
                    precision="broad",
                    category=cat,
                    event_type=event_types[0] if event_types else None,
                    explanation=(
                        f"В профиле указана категория «{cat}»; "
                        "публикация относится к этой теме"
                        + (
                            f" (упоминается {', '.join(brand_hits[:3])})"
                            if brand_hits
                            else ""
                        )
                        + "."
                    ),
                    event_signals=(hits + brand_hits)[:6],
                    limitations=lim,
                )
            )

    if not matches:
        return IndustryRelevanceResult(
            matched=False,
            precision="none",
            summary="",
            limitations=limitations
            + ["Связь публикации с продуктами компании не установлена."],
        )

    # Prefer exact over broad
    exact = [m for m in matches if m.precision == "exact"]
    chosen = exact or matches
    precision: MatchPrecision = "exact" if exact else "broad"
    top = chosen[0]
    if precision == "exact":
        summary = (
            f"Вы указали {top.brand or top.product_line or 'продукт'}. "
            "Новость совпадает по продукту"
        )
        if top.geography_note:
            summary += f"; {top.geography_note[0].lower() + top.geography_note[1:]}"
        else:
            summary += (
                "; влияние на ваши закупки и цены пока не подтверждено данными."
            )
    else:
        summary = (
            f"Широкое совпадение по категории «{top.category}». "
            "Точный бренд в профиле не указан — это не расчёт влияния."
        )

    return IndustryRelevanceResult(
        matched=True,
        precision=precision,
        summary=summary,
        matches=chosen[:5],
        limitations=list(chosen[0].limitations),
    )


def evaluate_events_industry_relevance(
    events: list[Event],
    profile: IndustryProfile,
) -> dict[str, IndustryRelevanceResult]:
    return {e.id: evaluate_industry_relevance(e, profile) for e in events}
