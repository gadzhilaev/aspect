"""DaData findById/party caller + bounded outcomes, TTL cache, per-user rate limit.

Security / ops:
- API key read from server config only; never logged, never returned to client.
- Only the single fixed allow-listed URL is called; redirects are not followed
  (so Authorization is never replayed to another host).
- Response size and timeout are bounded.
- Cache stores PUBLIC requisites only, keyed by INN. Auth errors / timeouts are
  never cached as not_found.
- Rate limit and cache are in-process (per worker). For multi-process deploys the
  effective limit is per process — see docs/COMPANY_INN_LOOKUP.md.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings
from app.services.company_registry.normalize import (
    RegistryCandidate,
    normalize_suggestion,
    source_actuality_date,
)

logger = logging.getLogger(__name__)

# Fixed, allow-listed upstream endpoints (never taken from the request).
DADATA_FIND_PARTY_URL = (
    "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
)
DADATA_SUGGEST_PARTY_URL = (
    "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"
)
# Party often returns only OKVED code; names come from okved2 (or okveds[]).
DADATA_FIND_OKVED2_URL = (
    "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/okved2"
)

SOURCE_INFO = {
    "provider": "dadata",
    "title": "DaData · данные ЕГРЮЛ/ЕГРИП ФНС России",
    "note": (
        "Публичные реестровые сведения через посредника DaData. "
        "Это не прямой запрос в ФНС и не подтверждение полномочий."
    ),
}

_OK = "ok"
_NOT_FOUND = "not_found"
_NOT_CONFIGURED = "not_configured"
_TIMEOUT = "timeout"
_UNAVAILABLE = "unavailable"
_AUTH_ERROR = "auth_error"
_RATE_LIMITED = "rate_limited"
_BAD_RESPONSE = "bad_response"


@dataclass
class LookupOutcome:
    kind: str
    candidates: list[RegistryCandidate] = field(default_factory=list)
    retrieved_at: float | None = None
    source_actuality_date: str | None = None


# --- in-process TTL cache (public requisites only) -------------------------

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, list[RegistryCandidate], str | None, float]] = {}
# OKVED code → human name (or None if upstream had no match).
_okved_name_cache: dict[str, str | None] = {}

# --- in-process per-user fixed-window rate limiter -------------------------

_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = {}


def reset_state() -> None:
    """Clear cache + rate windows (tests / explicit ops reset)."""
    with _cache_lock:
        _cache.clear()
        _okved_name_cache.clear()
    with _rate_lock:
        _rate_hits.clear()


def check_user_rate(user_id: str, *, now: float | None = None) -> bool:
    """Return True if the user may make another lookup within the window."""
    settings = get_settings()
    limit = int(getattr(settings, "company_registry_user_rate_per_minute", 20) or 20)
    if limit <= 0:
        return True
    ts = now if now is not None else time.monotonic()
    window = 60.0
    with _rate_lock:
        hits = [t for t in _rate_hits.get(user_id, []) if ts - t < window]
        if len(hits) >= limit:
            _rate_hits[user_id] = hits
            return False
        hits.append(ts)
        _rate_hits[user_id] = hits
        return True


def _cache_get(inn: str) -> tuple[list[RegistryCandidate], str | None, float] | None:
    ttl = int(getattr(get_settings(), "company_registry_cache_ttl_seconds", 3600) or 0)
    if ttl <= 0:
        return None
    with _cache_lock:
        row = _cache.get(inn)
        if row is None:
            return None
        expires_at, candidates, actuality, retrieved_at = row
        if time.monotonic() >= expires_at:
            _cache.pop(inn, None)
            return None
        return candidates, actuality, retrieved_at


def _cache_put(inn: str, candidates: list[RegistryCandidate], actuality: str | None, retrieved_at: float) -> None:
    ttl = int(getattr(get_settings(), "company_registry_cache_ttl_seconds", 3600) or 0)
    if ttl <= 0:
        return
    with _cache_lock:
        _cache[inn] = (time.monotonic() + ttl, candidates, actuality, retrieved_at)


def _parse_suggestions(
    body: object, max_candidates: int
) -> tuple[list[RegistryCandidate], list[dict]]:
    if not isinstance(body, dict):
        raise ValueError("response_not_object")
    suggestions = body.get("suggestions")
    if not isinstance(suggestions, list):
        raise ValueError("suggestions_not_list")
    candidates: list[RegistryCandidate] = []
    for idx, item in enumerate(suggestions[:max_candidates]):
        if not isinstance(item, dict):
            continue
        cand = normalize_suggestion(idx, item)
        if cand is not None:
            candidates.append(cand)
    return candidates, suggestions[:max_candidates]


def _okved_name_from_body(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    suggestions = body.get("suggestions")
    if not isinstance(suggestions, list) or not suggestions:
        return None
    first = suggestions[0]
    if not isinstance(first, dict):
        return None
    value = first.get("value")
    if isinstance(value, str) and value.strip():
        return value.strip()
    data = first.get("data")
    if isinstance(data, dict):
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _enrich_okved_names(
    client: httpx.Client,
    *,
    api_key: str,
    candidates: list[RegistryCandidate],
    max_bytes: int,
) -> None:
    """Fill okved_name via findById/okved2 when party payload omitted okveds[]."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Token {api_key}",
    }
    for cand in candidates:
        if cand.okved_name or not cand.okved:
            continue
        code = cand.okved.strip()
        with _cache_lock:
            if code in _okved_name_cache:
                cached_name = _okved_name_cache[code]
                if cached_name:
                    cand.okved_name = cached_name
                continue
        try:
            resp = client.post(
                DADATA_FIND_OKVED2_URL,
                headers=headers,
                json={"query": code},
            )
        except httpx.HTTPError:
            continue
        if resp.status_code != 200:
            continue
        content = resp.content or b""
        if len(content) > max_bytes:
            continue
        try:
            name = _okved_name_from_body(resp.json())
        except (ValueError, httpx.DecodingError):
            name = None
        with _cache_lock:
            _okved_name_cache[code] = name
        if name:
            cand.okved_name = name


def _dadata_party(url: str, query: str, *, cache_key: str) -> LookupOutcome:
    """Shared DaData party call (findById or suggest). Key never logged."""
    settings = get_settings()
    api_key = (getattr(settings, "dadata_api_key", None) or "").strip()
    if not api_key:
        return LookupOutcome(kind=_NOT_CONFIGURED)

    cached = _cache_get(cache_key)
    if cached is not None:
        candidates, actuality, retrieved_at = cached
        kind = _OK if candidates else _NOT_FOUND
        return LookupOutcome(
            kind=kind,
            candidates=candidates,
            retrieved_at=retrieved_at,
            source_actuality_date=actuality,
        )

    timeout = float(getattr(settings, "company_registry_timeout_seconds", 6.0) or 6.0)
    max_candidates = int(getattr(settings, "company_registry_max_candidates", 10) or 10)
    max_bytes = int(getattr(settings, "company_registry_max_response_bytes", 1_000_000) or 1_000_000)
    candidates: list[RegistryCandidate] = []
    raw_suggestions: list[dict] = []

    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Token {api_key}",
                },
                json={"query": query, "count": max_candidates},
            )
            if resp.status_code in (401, 402, 403):
                logger.warning("company_registry_upstream_auth status=%s", resp.status_code)
                return LookupOutcome(kind=_AUTH_ERROR)
            if resp.status_code == 429:
                logger.info("company_registry_upstream_rate_limited")
                return LookupOutcome(kind=_RATE_LIMITED)
            if resp.status_code >= 500:
                return LookupOutcome(kind=_UNAVAILABLE)
            if resp.status_code >= 300:
                return LookupOutcome(kind=_BAD_RESPONSE)

            content = resp.content or b""
            if len(content) > max_bytes:
                logger.info("company_registry_response_too_large bytes=%s", len(content))
                return LookupOutcome(kind=_BAD_RESPONSE)

            try:
                body = resp.json()
                candidates, raw_suggestions = _parse_suggestions(body, max_candidates)
            except (ValueError, httpx.DecodingError):
                return LookupOutcome(kind=_BAD_RESPONSE)

            if candidates:
                _enrich_okved_names(
                    client, api_key=api_key, candidates=candidates, max_bytes=max_bytes
                )
    except httpx.TimeoutException:
        logger.info("company_registry_timeout")
        return LookupOutcome(kind=_TIMEOUT)
    except httpx.HTTPError:
        logger.info("company_registry_network_error")
        return LookupOutcome(kind=_UNAVAILABLE)

    retrieved_at = time.time()
    actuality = source_actuality_date(raw_suggestions)
    if candidates:
        _cache_put(cache_key, candidates, actuality, retrieved_at)
        return LookupOutcome(
            kind=_OK,
            candidates=candidates,
            retrieved_at=retrieved_at,
            source_actuality_date=actuality,
        )
    return LookupOutcome(kind=_NOT_FOUND, retrieved_at=retrieved_at, source_actuality_date=actuality)


def lookup_inn(inn: str) -> LookupOutcome:
    """Exact party by INN (DaData findById/party)."""
    return _dadata_party(DADATA_FIND_PARTY_URL, inn, cache_key=f"inn:{inn}")


def suggest_party(query: str) -> LookupOutcome:
    """Fuzzy party by name / free text (DaData suggest/party)."""
    q = (query or "").strip()
    if not q:
        return LookupOutcome(kind=_NOT_FOUND)
    return _dadata_party(
        DADATA_SUGGEST_PARTY_URL,
        q,
        cache_key=f"name:{q.casefold()}",
    )
