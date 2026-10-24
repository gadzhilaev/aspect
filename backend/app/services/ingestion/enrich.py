"""Structured event draft from title+excerpt+source metadata only — no invented URLs/numbers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.models.raw_news import RawNewsItem

EventCategory = Literal[
    "geopolitics",
    "macro",
    "market",
    "electronics",
    "equipment",
    "logistics",
    "energy",
    "other",
]
EventType = Literal["risk", "opportunity", "market", "neutral"]

# HTML entities / tags stripped before keyword matching (avoid &laquo; noise).
_HTML_BITS = re.compile(r"&[a-z]+;|<[^>]+>", re.I)
_LETTER = re.compile(r"[a-zа-яё0-9]", re.I)


def _left_is_boundary(blob: str, start: int) -> bool:
    left = blob[start - 1] if start > 0 else ""
    return not left or not _LETTER.match(left)


class EnrichedClaim(BaseModel):
    text: str
    claim_type: Literal["confirmed_fact", "inference", "assumption", "estimate"] = "inference"
    source_id: str  # must be a provided source id


class EventEnrichment(BaseModel):
    title_ru: str
    summary_ru: str
    category: EventCategory = "other"
    event_type: EventType = "neutral"
    # None = significance not established (do not invent 0 / 50 as “known”).
    severity: float | None = Field(default=None, ge=0, le=100)
    countries: list[str] = Field(default_factory=list)
    currencies: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    effective_from: datetime | None = None
    claims: list[EnrichedClaim] = Field(default_factory=list)
    # Opaque diagnostics for attributes_json — not user-facing labels.
    classification_meta: dict[str, Any] = Field(default_factory=dict)


ENRICH_SCHEMA_HINT = {
    "type": "object",
    "required": [
        "title_ru",
        "summary_ru",
        "category",
        "event_type",
        "severity",
        "countries",
        "currencies",
        "materials",
        "claims",
    ],
    "properties": {
        "title_ru": {"type": "string"},
        "summary_ru": {"type": "string"},
        "category": {
            "type": "string",
            "enum": [
                "geopolitics",
                "macro",
                "market",
                "electronics",
                "equipment",
                "logistics",
                "energy",
                "other",
            ],
        },
        "event_type": {
            "type": "string",
            "enum": ["risk", "opportunity", "market", "neutral"],
        },
        "severity": {"type": ["number", "null"]},
        "countries": {"type": "array", "items": {"type": "string"}},
        "currencies": {"type": "array", "items": {"type": "string"}},
        "materials": {"type": "array", "items": {"type": "string"}},
        "effective_from": {"type": ["string", "null"]},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "claim_type", "source_id"],
                "properties": {
                    "text": {"type": "string"},
                    "claim_type": {
                        "type": "string",
                        "enum": [
                            "confirmed_fact",
                            "inference",
                            "assumption",
                            "estimate",
                        ],
                    },
                    "source_id": {"type": "string"},
                },
            },
        },
    },
}


def _source_payload(items: list[RawNewsItem]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": item.id,
            "publisher": item.publisher,
            "title": item.title,
            "excerpt": (item.excerpt or "")[:500],
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "canonical_url": item.canonical_url,
            "provider": item.provider,
        }
        for item in items
    ]


def _filter_claims(claims: list[EnrichedClaim], allowed_ids: set[str]) -> list[EnrichedClaim]:
    return [c for c in claims if c.source_id in allowed_ids]


def _normalize_blob(text: str) -> str:
    t = _HTML_BITS.sub(" ", (text or "").lower())
    t = t.replace("ё", "е")
    return re.sub(r"\s+", " ", t)


def blob_has_stem(
    blob: str,
    stem: str,
    *,
    forbid_prefixes: tuple[str, ...] = (),
    left_boundary: bool = True,
) -> bool:
    """Substring match with left word boundary and forbidden prefixes.

    Example: stem ``ставк`` must not match inside ``выставки`` (prefix ``вы``).
    Right side may continue (inflection: ставка/ставки).
    """
    stem_l = stem.lower()
    start = 0
    while True:
        i = blob.find(stem_l, start)
        if i < 0:
            return False
        if any(i >= len(p) and blob[i - len(p) : i] == p for p in forbid_prefixes):
            start = i + 1
            continue
        if left_boundary and not _left_is_boundary(blob, i):
            start = i + 1
            continue
        return True



def blob_has_any(
    blob: str,
    stems: tuple[str, ...],
    *,
    forbid_prefixes: tuple[str, ...] = (),
    left_boundary: bool = True,
) -> bool:
    return any(
        blob_has_stem(
            blob, s, forbid_prefixes=forbid_prefixes, left_boundary=left_boundary
        )
        for s in stems
    )


def _phrase_has(blob: str, phrases: tuple[str, ...]) -> bool:
    return any(p in blob for p in phrases)


def heuristic_enrich(items: list[RawNewsItem]) -> EventEnrichment:
    """Deterministic offline enricher — never invents URLs or numeric facts beyond source text.

    Official source ≠ negative / high economic importance.
    Unknown significance → severity=None, event_type=neutral (not fake 0/50/risk).
    """
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    primary = max(items, key=lambda i: i.published_at or epoch)
    raw_blob = " ".join(f"{i.title} {i.excerpt or ''}" for i in items)
    blob = _normalize_blob(raw_blob)

    category: EventCategory = "other"
    event_type: EventType = "neutral"
    severity: float | None = None
    countries: list[str] = []
    currencies: list[str] = []
    materials: list[str] = []
    matched: list[str] = []

    # --- Cultural / ceremonial institutional notice (before risk heuristics) ---
    cultural = _phrase_has(
        blob,
        (
            "экспозиц",
            "выставк",
            "музей",
            "культур",
            "художеств",
            "картин",
            "праздничн",
            "мемориал",
            "памятник",
            "наградн",
        ),
    )
    # Customs/agency mention alone is not a trade risk.
    if cultural:
        category = "other"
        event_type = "neutral"
        severity = None
        matched.append("cultural_or_ceremonial_notice")

    # --- Enacted export / sanctions restriction ---
    enacted_restriction = _phrase_has(
        blob,
        (
            "введен запрет",
            "введены ограничения",
            "введено ограничение",
            "export ban",
            "export control imposed",
            "санкц",
        ),
    ) or (
        blob_has_stem(blob, "запрет")
        and blob_has_any(blob, ("экспорт", "export"), left_boundary=False)
    )
    if enacted_restriction and not cultural:
        category = "geopolitics"
        event_type = "risk"
        severity = 75.0
        matched.append("enacted_export_or_sanctions")

    # --- Investigation / review without enacted measure ---
    investigation = _phrase_has(
        blob,
        (
            "расследован",
            "investigation",
            "safeguard investigation",
            "антидемпингов",
            "открыто расследование",
            "launches safeguard",
        ),
    )
    if investigation and not enacted_restriction:
        category = "geopolitics" if category == "other" else category
        event_type = "neutral"
        severity = None  # measure not established — do not invent high risk
        matched.append("investigation_without_measure")

    # --- Key rate / FX macro (not «выставки», not bare «таможня») ---
    key_rate = blob_has_stem(blob, "ставк", forbid_prefixes=("вы",)) and (
        _phrase_has(
            blob, ("ключев", "цб рф", "банк россии", "key rate", "рефинанс")
        )
        or bool(re.search(r"(?<![a-zа-яё])цб(?![a-zа-яё])", blob))
    )
    fx_macro = _phrase_has(blob, ("валютн", "курс руб", " forex")) or (
        blob_has_stem(blob, "курс")
        and blob_has_any(
            blob, ("руб", "доллар", "евро", "yuan", "валют"), left_boundary=False
        )
    )
    if (key_rate or fx_macro) and not cultural:
        category = "macro"
        if event_type == "neutral":
            event_type = "market"
        severity = 60.0 if severity is None else severity
        if "RUB" not in currencies:
            currencies.append("RUB")
        matched.append("key_rate_or_fx" if key_rate or fx_macro else "macro")

    # --- Electronics ---
    if blob_has_any(
        blob,
        ("полупровод", "semiconductor"),
        left_boundary=False,
    ) or _phrase_has(blob, ("микросхем", "электронн компонент", "chip ")):
        if not cultural:
            category = "electronics"
            materials = ["electronics"]
            if severity is None and event_type != "neutral":
                severity = 70.0
            elif severity is None:
                severity = None
            matched.append("electronics")

    # --- Logistics (not substring of «экспорт») ---
    if (
        _phrase_has(blob, ("логистич", "shipping", "freight"))
        or blob_has_stem(blob, "порт", forbid_prefixes=("экс", "аэро", "теле"))
    ) and not cultural and "enacted_export_or_sanctions" not in matched:
        category = "logistics"
        matched.append("logistics")

    # --- Opportunity markers ---
    if _phrase_has(blob, ("возможност", "смягчен", "рост продаж", "opportunity")):
        event_type = "opportunity"
        if severity is not None:
            severity = min(severity, 50.0)
        matched.append("opportunity")

    # --- Neutral statistics ---
    if _phrase_has(blob, ("росстат", "статистик", "индекс потребитель", "cpi report")):
        if not enacted_restriction and not investigation:
            category = "other"
            event_type = "neutral"
            severity = None
            matched.append("neutral_statistics")

    # Currencies / countries — boundary-aware; no «ес» inside «честь»
    for code in ("USD", "EUR", "CNY", "RUB"):
        token = code.lower()
        if blob_has_stem(blob, token) or code in raw_blob:
            if code not in currencies:
                currencies.append(code)

    country_stems = (
        ("китай", "Китай"),
        ("кнр", "Китай"),
        ("росси", "Россия"),  # россия/россии/россию
        ("сша", "США"),
        ("евросоюз", "ЕС"),
        ("european union", "ЕС"),
        ("china", "China"),
        ("russia", "Russia"),
    )
    for stem, label in country_stems:
        if blob_has_stem(blob, stem):
            if label not in countries:
                countries.append(label)
    # Explicit « ЕС » / «EU» tokens only (not substring «ес»)
    if re.search(r"(?<![a-zа-яё])ес(?![a-zа-яё])", blob) or re.search(
        r"(?<![a-z])eu(?![a-z])", blob
    ):
        if "ЕС" not in countries:
            countries.append("ЕС")

    claims = [
        EnrichedClaim(
            text=f"Источник «{i.publisher}»: {i.title}",
            claim_type="confirmed_fact",
            source_id=i.id,
        )
        for i in items
    ]

    summary = (primary.excerpt or primary.title).strip()
    if len(summary) > 600:
        summary = summary[:597] + "..."

    meta = {
        "basis": "heuristic_v2",
        "matched_rules": matched,
        "severity_known": severity is not None,
        "official_source_does_not_imply_risk": True,
    }

    return EventEnrichment(
        title_ru=primary.title[:512],
        summary_ru=summary,
        category=category,
        event_type=event_type,
        severity=severity,
        countries=countries[:8],
        currencies=currencies[:8],
        materials=materials[:8],
        effective_from=primary.published_at,
        claims=claims,
        classification_meta=meta,
    )


def live_enrich(items: list[RawNewsItem], *, http_client: httpx.Client | None = None) -> EventEnrichment:
    """Call OpenAI Responses API for structured enrichment; falls back to heuristic on failure.

    When ASSISTANT_PROVIDER=hackathon, live enrichment is explicitly blocked so the
    competition mode never silently calls api.openai.com / another provider.
    """
    from app.core.errors import AppError

    from app.services.competition_profile import refuse_non_hackathon_llm

    # Competition profile and hackathon provider both forbid OpenAI enrich.
    refuse_non_hackathon_llm(path="ingestion.live_enrich")

    settings = get_settings()
    if settings.normalized_assistant_provider() == "hackathon":
        raise AppError(
            "INGESTION_LIVE_BLOCKED",
            "Live-обогащение новостей недоступно при ASSISTANT_PROVIDER=hackathon "
            "(используйте --heuristic-enrich). Хакатон-шлюз не подключён к ingestion.",
            503,
            details=[{"reason": "hackathon_mode_blocks_openai_enrich"}],
        )
    api_key = settings.resolved_openai_api_key()
    if not api_key:
        return heuristic_enrich(items)

    allowed_ids = {i.id for i in items}
    sources = _source_payload(items)
    system = (
        "You normalize news clusters into structured Russian event cards. "
        "Use ONLY the provided titles, excerpts and metadata. "
        "Never invent URLs, numbers, publishers or source_id values. "
        "Every claim.source_id MUST be one of the provided source_id values. "
        "Official publisher does NOT imply risk or high severity. "
        "If significance or risk direction is unclear, use event_type=neutral "
        "and severity=null (do not invent 0 or 50). "
        "Respond with a single JSON object matching the schema."
    )
    user_payload = {
        "sources": sources,
        "schema": ENRICH_SCHEMA_HINT,
        "rules": [
            "title_ru and summary_ru in Russian",
            "Do not invent facts not present in sources",
            "claims must cite source_id from the list",
            "severity may be null when unknown",
        ],
    }
    payload = {
        "model": settings.resolved_openai_model(),
        "input": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False, default=str)[:14000],
            },
        ],
        "text": {"format": {"type": "json_object"}},
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    base = settings.assistant_base_url.rstrip("/")
    url = f"{base}/responses"

    owns = http_client is None
    client = http_client or httpx.Client(timeout=45.0)
    try:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()
        text = _extract_responses_text(body)
        parsed = json.loads(text)
        model = EventEnrichment.model_validate(parsed)
        model.claims = _filter_claims(model.claims, allowed_ids)
        if not model.claims:
            # Force grounded claims from sources — never leave uncited facts
            model.claims = heuristic_enrich(items).claims
        return model
    except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError, TypeError):
        return heuristic_enrich(items)
    finally:
        if owns:
            client.close()


def _extract_responses_text(body: dict[str, Any]) -> str:
    """Parse OpenAI Responses API output."""
    if isinstance(body.get("output_text"), str) and body["output_text"]:
        return body["output_text"]
    chunks: list[str] = []
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"} and part.get("text"):
                chunks.append(str(part["text"]))
    if chunks:
        return "\n".join(chunks)
    # Fallback chat-completions-shaped response (tests / proxies)
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise KeyError("no text in responses body") from exc


def enrich_cluster(items: list[RawNewsItem], *, prefer_live: bool = True) -> EventEnrichment:
    settings = get_settings()
    if prefer_live and settings.normalized_assistant_provider() == "hackathon":
        # Surface the block instead of silently falling through to OpenAI or heuristic.
        return live_enrich(items)
    if prefer_live and settings.resolved_openai_api_key():
        return live_enrich(items)
    return heuristic_enrich(items)


_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?%?")


def strip_invented_numbers(summary: str, source_texts: list[str]) -> str:
    """Drop numeric tokens in summary that do not appear in any source text."""
    joined = "\n".join(source_texts).lower().replace(",", ".")
    parts: list[str] = []
    last = 0
    for m in _NUM_RE.finditer(summary):
        token = m.group(0)
        norm = token.lower().replace(",", ".")
        if norm in joined or token in joined:
            parts.append(summary[last : m.end()])
        else:
            parts.append(summary[last : m.start()])
            parts.append("[число из источника не подтверждено]")
        last = m.end()
    parts.append(summary[last:])
    return "".join(parts)
