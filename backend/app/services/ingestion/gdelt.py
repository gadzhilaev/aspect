"""GDELT DOC 2.1 — global business news queries."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.services.ingestion.base import FetchedArticle, SourceProvider
from app.services.ingestion.conditional_http import HttpValidatorCache, conditional_get
from app.services.ingestion.normalize import canonicalize_url

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    # GDELT often returns YYYYMMDDHHMMSS
    if len(raw) >= 14 and raw[:14].isdigit():
        try:
            return datetime(
                int(raw[0:4]),
                int(raw[4:6]),
                int(raw[6:8]),
                int(raw[8:10]),
                int(raw[10:12]),
                int(raw[12:14]),
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


class GdeltProvider(SourceProvider):
    name = "gdelt"
    is_official = False

    def __init__(
        self,
        *,
        queries: list[str] | None = None,
        client: httpx.Client | None = None,
        timeout: float = 25.0,
        max_per_query: int = 15,
        validator_cache: HttpValidatorCache | None = None,
    ) -> None:
        settings = get_settings()
        self.queries = queries if queries is not None else settings.gdelt_query_list()
        self._client = client
        self._timeout = timeout
        self.max_per_query = max_per_query
        self._validator_cache = validator_cache
        self.last_fetch_errors: list[str] = []

    def fetch(self) -> list[FetchedArticle]:
        self.last_fetch_errors = []
        owns = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout, follow_redirects=True)
        try:
            seen: set[str] = set()
            out: list[FetchedArticle] = []
            for query in self.queries:
                for article in self._fetch_query(client, query):
                    if article.canonical_url in seen:
                        continue
                    seen.add(article.canonical_url)
                    out.append(article)
            return out
        finally:
            if owns:
                client.close()

    def _fetch_query(self, client: httpx.Client, query: str) -> list[FetchedArticle]:
        params = {
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(self.max_per_query),
            "sort": "DateDesc",
        }
        url = f"{GDELT_DOC_URL}?{urlencode(params)}"
        outcome = conditional_get(client, url, cache=self._validator_cache)
        if outcome.not_modified:
            return []
        if outcome.error or outcome.content is None:
            if outcome.error:
                self.last_fetch_errors.append(f"query:{outcome.error}")
            return []
        try:
            import json as _json

            body: dict[str, Any] = _json.loads(outcome.content.decode("utf-8"))
        except Exception:  # noqa: BLE001
            self.last_fetch_errors.append("query:parse_error")
            return []
        articles = body.get("articles") or []
        items: list[FetchedArticle] = []
        for row in articles:
            if not isinstance(row, dict):
                continue
            link = (row.get("url") or "").strip()
            title = (row.get("title") or "").strip()
            if not link or not title:
                continue
            canonical = canonicalize_url(link)
            domain = (row.get("domain") or "").strip() or "GDELT"
            seendate = _parse_date(row.get("seendate") or row.get("datetime"))
            external_id = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:24]
            items.append(
                FetchedArticle(
                    provider=self.name,
                    external_id=f"gdelt-{external_id}",
                    canonical_url=canonical,
                    publisher=domain,
                    title=title,
                    excerpt=(row.get("seendate") and f"GDELT signal · {query}") or None,
                    published_at=seendate,
                    language=(row.get("language") or None),
                    is_official=False,
                    payload={"query": query, "raw": {k: row.get(k) for k in ("domain", "language", "sourcecountry")}},
                )
            )
        return items
