"""Verified primary / official source policy for the publish gate.

Classification uses feed URL + article canonical URL (host/path).
Does NOT trust publisher display names, RSS/user payload ``is_official``,
or lookalike domains.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.models.raw_news import RawNewsItem
from app.services.ingestion.normalize import canonicalize_url


def _host(url: str) -> str:
    h = urlparse(url or "").netloc.lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def _path(url: str) -> str:
    return urlparse(url or "").path or "/"


@dataclass(frozen=True)
class PrimarySourceRule:
    """Allow official-primary only when feed and article match these constraints."""

    source_id: str
    article_hosts: frozenset[str]
    feed_hosts: frozenset[str]
    # Article path must start with one of these (empty = any path on host).
    article_path_prefixes: tuple[str, ...] = ()
    # Feed URL path must start with one of these (empty = any path on feed host).
    feed_path_prefixes: tuple[str, ...] = ()
    # Optional: feed query must contain key=value (informational; not required for match
    # when documented as ineffective — see notes).
    trust_basis: str = ""
    thematic_limitations: str = ""


# Minimal allow-list. Expand only with documented primary org feeds.
PRIMARY_SOURCE_RULES: tuple[PrimarySourceRule, ...] = (
    PrimarySourceRule(
        source_id="cbr",
        article_hosts=frozenset({"cbr.ru"}),
        feed_hosts=frozenset({"cbr.ru"}),
        trust_basis=(
            "Банк России — первичная публикация на cbr.ru "
            "(RSS whitelist / CbrProvider)."
        ),
    ),
    PrimarySourceRule(
        source_id="wto",
        article_hosts=frozenset({"wto.org"}),
        feed_hosts=frozenset({"wto.org"}),
        article_path_prefixes=("/english/news_e/", "/english/tratop_e/", "/english/docs_e/"),
        feed_path_prefixes=("/library/rss/",),
        trust_basis=(
            "ВТО — первичная лента wto.org/library/rss и страницы новостей на wto.org."
        ),
        thematic_limitations=(
            "Публикация подтверждает происхождение сообщения ВТО, "
            "не вступившую меру третьей страны и не ущерб конкретной компании."
        ),
    ),
    PrimarySourceRule(
        source_id="fts_ru",
        article_hosts=frozenset({"customs.gov.ru"}),
        feed_hosts=frozenset({"customs.gov.ru"}),
        article_path_prefixes=("/press/",),
        feed_path_prefixes=("/press/",),
        trust_basis=(
            "ФТС России — первичная пресс-лента customs.gov.ru/press/…"
        ),
        thematic_limitations=(
            "Институциональные пресс-релизы ФТС ≠ автоматически экспортное ограничение."
        ),
    ),
    PrimarySourceRule(
        source_id="ec_presscorner",
        article_hosts=frozenset({"ec.europa.eu"}),
        feed_hosts=frozenset({"ec.europa.eu"}),
        article_path_prefixes=("/commission/presscorner/",),
        feed_path_prefixes=("/commission/presscorner/",),
        trust_basis=(
            "Еврокомиссия — первичные материалы presscorner на ec.europa.eu."
        ),
        thematic_limitations=(
            "Параметр dossier=trade в RSS API фактически не фильтрует выдачу "
            "(проверено 2026-10-24: те же заголовки с/без dossier). "
            "Ленту нельзя называть «торговой»; это общая presscorner-выдача. "
            "Официальность = происхождение EC, не тема trade."
        ),
    ),
)


@dataclass(frozen=True)
class OfficialClassification:
    is_official_primary: bool
    source_id: str | None
    reason: str
    trust_basis: str = ""
    limitations: str = ""


def _feed_url_of(item: RawNewsItem) -> str:
    payload = item.payload_json if isinstance(item.payload_json, dict) else {}
    raw = payload.get("feed_url") or payload.get("source_feed_url") or ""
    if isinstance(raw, str) and raw.strip():
        return canonicalize_url(raw) or raw.strip()
    # CbrProvider / HTML connectors may omit feed_url; article host alone + provider.
    if (item.provider or "").lower() == "cbr":
        return canonicalize_url(item.canonical_url) or (item.canonical_url or "")
    return ""


def _path_allowed(path: str, prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return True
    p = path if path.startswith("/") else f"/{path}"
    return any(p.startswith(pref) for pref in prefixes)


def classify_official_primary(item: RawNewsItem) -> OfficialClassification:
    """Return whether the item is a verified primary official publication."""
    article_url = canonicalize_url(item.canonical_url) or (item.canonical_url or "")
    article_host = _host(article_url)
    article_path = _path(article_url)
    feed_url = _feed_url_of(item)
    feed_host = _host(feed_url) if feed_url else ""
    feed_path = _path(feed_url) if feed_url else ""

    # Explicitly ignore forged signals
    payload = item.payload_json if isinstance(item.payload_json, dict) else {}
    _ = payload.get("is_official")  # never used for trust

    if not article_host:
        return OfficialClassification(
            False, None, "missing_article_host", limitations="no_canonical_url"
        )

    for rule in PRIMARY_SOURCE_RULES:
        if article_host not in rule.article_hosts:
            continue
        if not _path_allowed(article_path, rule.article_path_prefixes):
            continue
        # Feed must be present and on allowed host (except pure cbr provider articles
        # where feed_url may equal article when provider=cbr).
        if not feed_host:
            if (item.provider or "").lower() == "cbr" and article_host in rule.article_hosts:
                return OfficialClassification(
                    True,
                    rule.source_id,
                    "official_primary_cbr_provider",
                    trust_basis=rule.trust_basis,
                    limitations=rule.thematic_limitations,
                )
            continue
        if feed_host not in rule.feed_hosts:
            continue
        if not _path_allowed(feed_path, rule.feed_path_prefixes):
            continue
        return OfficialClassification(
            True,
            rule.source_id,
            f"official_primary:{rule.source_id}",
            trust_basis=rule.trust_basis,
            limitations=rule.thematic_limitations,
        )

    return OfficialClassification(
        False,
        None,
        "not_in_primary_source_allowlist",
    )


def is_official_primary_item(item: RawNewsItem) -> bool:
    return classify_official_primary(item).is_official_primary


def classification_dict(item: RawNewsItem) -> dict[str, Any]:
    c = classify_official_primary(item)
    return {
        "is_official_primary": c.is_official_primary,
        "source_id": c.source_id,
        "reason": c.reason,
        "trust_basis": c.trust_basis,
        "limitations": c.limitations,
        "article_host": _host(item.canonical_url or ""),
        "feed_url": _feed_url_of(item),
    }
