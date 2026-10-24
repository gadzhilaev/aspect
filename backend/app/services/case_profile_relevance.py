"""Explainable case-profile relevance for the personal feed (no EventImpact required).

Uses the active competition snapshot via ``build_case_context_block`` (caller loads
once per request). Does not invent debt amounts, deposit balances, or trade
direction. Does not write to the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from app.models import Event

ThemeId = Literal["policy_rate"]

# Structured match_categories phrases (normalized) that establish policy-rate theme.
# A single generic token such as «ставка» alone is not enough.
_RATE_CATEGORY_PHRASES: frozenset[str] = frozenset(
    {
        "ключевая ставка",
        "ключевой ставки",
        "ключевую ставку",
        "дкп",
        "monetary policy",
        "policy rate",
        "key rate",
    }
)

_PRODUCT_LABELS: dict[str, str] = {
    "RKO": "Расчётно-кассовое обслуживание",
    "GAR": "Банковские гарантии",
    "LOA": "Кредиты",
    "LEA": "Лизинг",
    "DEP": "Депозиты",
    "ZPP": "Зарплатный проект",
}


def norm_text(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("ё", "е").split())


@dataclass(frozen=True)
class ProfileRule:
    rule_id: str
    theme: ThemeId
    product_code: str
    explanation: str
    limitations: tuple[str, ...]


# Small explicit v1 rule set — products × themes only.
PROFILE_RULES: tuple[ProfileRule, ...] = (
    ProfileRule(
        rule_id="policy_rate_loan_mark",
        theme="policy_rate",
        product_code="LOA",
        explanation="В данных компании указан кредитный продукт",
        limitations=(
            "Отметка кредита не означает известную сумму долга или плавающую ставку.",
            "Связь с профилем — не расчёт влияния и не денежный эффект.",
        ),
    ),
    ProfileRule(
        rule_id="policy_rate_deposit_mark",
        theme="policy_rate",
        product_code="DEP",
        explanation="В данных компании указан депозитный продукт",
        limitations=(
            "Отметка депозита не означает известный остаток или условия вклада.",
            "Связь с профилем — не расчёт влияния и не денежный эффект.",
        ),
    ),
)


@dataclass
class ThemeDetection:
    theme: ThemeId
    signals: list[str] = field(default_factory=list)
    via_text_fallback: bool = False


@dataclass
class ProfileMatch:
    rule_id: str
    theme: ThemeId
    product_code: str
    product_label: str
    product_status: str
    explanation: str
    event_theme_signals: list[str]
    limitations: list[str]


@dataclass
class ProfileRelevanceResult:
    matched: bool
    summary: str
    matches: list[ProfileMatch] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    themes_detected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "summary": self.summary,
            "matches": [
                {
                    "rule_id": m.rule_id,
                    "theme": m.theme,
                    "product_code": m.product_code,
                    "product_label": m.product_label,
                    "product_status": m.product_status,
                    "explanation": m.explanation,
                    "event_theme_signals": list(m.event_theme_signals),
                    "limitations": list(m.limitations),
                }
                for m in self.matches
            ],
            "limitations": list(self.limitations),
            "themes_detected": list(self.themes_detected),
        }


@dataclass(frozen=True)
class CaseProductSnapshot:
    """Known product marks from one case_context load (per request)."""

    status_by_code: dict[str, str]
    case_status: str
    external_uid: str | None
    snapshot_id: str | None
    version_label: str | None
    version_seq: int | None
    provenance: dict[str, Any] | None

    @property
    def usable(self) -> bool:
        return self.case_status == "profile_available" and bool(self.status_by_code)


def product_snapshot_from_case_context(case_context: Any) -> CaseProductSnapshot:
    """Extract product marks from CaseContextOut / dict without re-querying."""
    if case_context is None:
        return CaseProductSnapshot({}, "integration_not_configured", None, None, None, None, None)

    if hasattr(case_context, "model_dump"):
        raw = case_context.model_dump()
    elif isinstance(case_context, dict):
        raw = case_context
    else:
        raw = {
            "status": getattr(case_context, "status", None),
            "external_uid": getattr(case_context, "external_uid", None),
            "snapshot_id": getattr(case_context, "snapshot_id", None),
            "version_label": getattr(case_context, "version_label", None),
            "version_seq": getattr(case_context, "version_seq", None),
            "profile": getattr(case_context, "profile", None),
        }

    status = str(raw.get("status") or "")
    profile = raw.get("profile") if isinstance(raw.get("profile"), dict) else None
    if profile is None and getattr(case_context, "profile", None) is not None:
        pobj = case_context.profile
        if hasattr(pobj, "model_dump"):
            profile = pobj.model_dump()
        elif isinstance(pobj, dict):
            profile = pobj

    status_by_code: dict[str, str] = {}
    provenance: dict[str, Any] | None = None
    if isinstance(profile, dict):
        for p in profile.get("products") or []:
            if not isinstance(p, dict):
                continue
            code = str(p.get("code") or "").strip().upper()
            pst = str(p.get("status") or "").strip().lower()
            if code and pst in {"true", "false", "unknown", "conflict"}:
                status_by_code[code] = pst
        prov = profile.get("provenance")
        if isinstance(prov, dict):
            provenance = {
                "snapshot_id": prov.get("snapshot_id"),
                "version_label": prov.get("version_label"),
                "version_seq": prov.get("version_seq"),
                "source_file": prov.get("source_file"),
                "source_row_numbers": list(prov.get("source_row_numbers") or []),
                "catalog_row_ids": list(prov.get("catalog_row_ids") or []),
                "variant_count": int(prov.get("variant_count") or 0),
            }

    return CaseProductSnapshot(
        status_by_code=status_by_code,
        case_status=status,
        external_uid=raw.get("external_uid"),
        snapshot_id=raw.get("snapshot_id") or (provenance or {}).get("snapshot_id"),
        version_label=raw.get("version_label"),
        version_seq=raw.get("version_seq"),
        provenance=provenance,
    )


def detect_event_themes(event: Event) -> list[ThemeDetection]:
    """Conservative theme detection from structured fields, then text fallback."""
    out: list[ThemeDetection] = []
    cats_raw = event.match_categories_json if isinstance(event.match_categories_json, list) else []
    cats = [norm_text(str(c)) for c in cats_raw if str(c).strip()]
    signals: list[str] = []

    for phrase in cats:
        if phrase in _RATE_CATEGORY_PHRASES:
            signals.append(f"match_category:{phrase}")

    # Compound structured signal: «ставка» + (ключев|дкп|цб) in categories blob.
    cat_blob = " ".join(cats)
    if not signals:
        has_rate = "ставк" in cat_blob
        has_policy = any(x in cat_blob for x in ("ключев", "дкп", "цб рф", "банк россии"))
        if has_rate and has_policy:
            signals.append("match_categories:rate+policy_compound")

    if signals:
        out.append(ThemeDetection(theme="policy_rate", signals=signals, via_text_fallback=False))
        return out

    # Text fallback — require multi-signal, not a lone shared token.
    title = norm_text(event.title or "")
    summary = norm_text(event.summary or "")
    text = f"{title} {summary}"
    fb_signals: list[str] = []
    if "ключев" in text and "ставк" in text:
        fb_signals.append("text:key_rate_pair")
    elif "ставк" in text and ("цб" in text or "банк россии" in text) and (
        "решен" in text or "сохран" in text or "повыш" in text or "сниж" in text
    ):
        fb_signals.append("text:cb_rate_decision")
    if fb_signals:
        out.append(
            ThemeDetection(theme="policy_rate", signals=fb_signals, via_text_fallback=True)
        )
    return out


def evaluate_profile_relevance(
    event: Event,
    products: CaseProductSnapshot,
) -> ProfileRelevanceResult:
    """Return positive matches only when product status is explicitly true."""
    base_limits = [
        "Отсутствие совпадения с правилами профиля не означает, что новость не влияет.",
        "false в каталоге — отсутствие отметки в данном источнике, не «нет продукта во всех банках».",
        "unknown/conflict не дают положительного основания.",
    ]
    if not products.usable:
        return ProfileRelevanceResult(
            matched=False,
            summary="Конкурсный профиль недоступен для профильной релевантности.",
            limitations=base_limits
            + [f"case_context.status={products.case_status or 'unknown'}"],
        )

    themes = detect_event_themes(event)
    theme_map = {t.theme: t for t in themes}
    if not theme_map:
        return ProfileRelevanceResult(
            matched=False,
            summary="Тема события не сопоставлена с правилами профиля.",
            limitations=base_limits,
            themes_detected=[],
        )

    matches: list[ProfileMatch] = []
    for rule in PROFILE_RULES:
        theme_hit = theme_map.get(rule.theme)
        if theme_hit is None:
            continue
        pst = products.status_by_code.get(rule.product_code)
        if pst != "true":
            continue
        limits = list(rule.limitations)
        if theme_hit.via_text_fallback:
            limits.append("Тема определена консервативным текстовым fallback, не только category.")
        matches.append(
            ProfileMatch(
                rule_id=rule.rule_id,
                theme=rule.theme,
                product_code=rule.product_code,
                product_label=_PRODUCT_LABELS.get(rule.product_code, rule.product_code),
                product_status="true",
                explanation=rule.explanation,
                event_theme_signals=list(theme_hit.signals),
                limitations=limits,
            )
        )

    if not matches:
        return ProfileRelevanceResult(
            matched=False,
            summary="Тема события распознана, но подтверждённых отметок продуктов для правил нет.",
            limitations=base_limits,
            themes_detected=sorted(theme_map.keys()),
        )

    # Stable order by rule_id
    matches.sort(key=lambda m: m.rule_id)
    summary_parts = [m.explanation for m in matches]
    # Dedupe explanations while preserving order
    seen: set[str] = set()
    uniq_summary: list[str] = []
    for s in summary_parts:
        if s not in seen:
            seen.add(s)
            uniq_summary.append(s)

    all_limits: list[str] = list(base_limits)
    for m in matches:
        for lim in m.limitations:
            if lim not in all_limits:
                all_limits.append(lim)

    return ProfileRelevanceResult(
        matched=True,
        summary="; ".join(uniq_summary),
        matches=matches,
        limitations=all_limits,
        themes_detected=sorted(theme_map.keys()),
    )


def evaluate_events_profile_relevance(
    events: Iterable[Event],
    products: CaseProductSnapshot,
) -> dict[str, ProfileRelevanceResult]:
    """Batch evaluate — same product snapshot for all events (no per-event case reload)."""
    return {ev.id: evaluate_profile_relevance(ev, products) for ev in events}
