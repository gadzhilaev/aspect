"""Whitelist RSS provider — only feeds from configuration."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree.ElementTree import Element

import httpx

from app.core.config import get_settings
from app.services.ingestion.base import FetchedArticle, SourceProvider
from app.services.ingestion.conditional_http import HttpValidatorCache, conditional_get
from app.services.ingestion.normalize import canonicalize_url


def _text(el: Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return (el.text or "").strip()


def _parse_rss_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


def _publisher_from_feed(feed_url: str, channel: Element | None) -> str:
    title = _text(channel.find("title")) if channel is not None else ""
    if title:
        return title[:255]
    host = urlparse(feed_url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "RSS"


class RssProvider(SourceProvider):
    name = "rss"
    is_official = False

    def __init__(
        self,
        *,
        feed_urls: list[str] | None = None,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
        max_per_feed: int = 20,
        validator_cache: HttpValidatorCache | None = None,
    ) -> None:
        settings = get_settings()
        allowed = settings.rss_feed_list()
        requested = feed_urls if feed_urls is not None else allowed
        # Hard whitelist: never fetch URLs outside configured list
        allowed_set = set(allowed)
        self.feed_urls = [u for u in requested if u in allowed_set] if allowed_set else []
        self._client = client
        self._timeout = timeout
        self.max_per_feed = max_per_feed
        self._validator_cache = validator_cache
        self.last_fetch_errors: list[str] = []

    def fetch(self) -> list[FetchedArticle]:
        self.last_fetch_errors = []
        owns = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout, follow_redirects=True)
        try:
            out: list[FetchedArticle] = []
            for feed_url in self.feed_urls:
                out.extend(self._fetch_feed(client, feed_url))
            return out
        finally:
            if owns:
                client.close()

    def _fetch_feed(self, client: httpx.Client, feed_url: str) -> list[FetchedArticle]:
        outcome = conditional_get(client, feed_url, cache=self._validator_cache)
        if outcome.not_modified:
            return []
        if outcome.error or outcome.content is None:
            if outcome.error:
                host = urlparse(feed_url).netloc.lower() or "feed"
                if host.startswith("www."):
                    host = host[4:]
                self.last_fetch_errors.append(f"{host}:{outcome.error}")
            return []
        try:
            root = ET.fromstring(outcome.content)
        except Exception:  # noqa: BLE001
            host = urlparse(feed_url).netloc.lower() or "feed"
            if host.startswith("www."):
                host = host[4:]
            self.last_fetch_errors.append(f"{host}:parse_error")
            return []

        channel = root.find("channel")
        nodes = channel.findall("item") if channel is not None else root.findall(".//{*}item")
        if not nodes:
            nodes = root.findall(".//item")
        publisher = _publisher_from_feed(feed_url, channel)
        # Connector hint only — publish gate uses official_sources host/path rules.
        feed_host = urlparse(feed_url).netloc.lower()
        if feed_host.startswith("www."):
            feed_host = feed_host[4:]
        cbr_feed = feed_host == "cbr.ru" or feed_host.endswith(".cbr.ru")
        items: list[FetchedArticle] = []
        for item in nodes[: self.max_per_feed]:
            title = _text(item.find("title"))
            link = _text(item.find("link")) or _text(item.find("guid"))
            if not title or not link:
                # Atom fallback
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
                if link_el is not None:
                    link = link_el.attrib.get("href", "")
                title = title or _text(item.find("{http://www.w3.org/2005/Atom}title"))
            if not title or not link:
                continue
            desc = _text(item.find("description")) or _text(
                item.find("{http://www.w3.org/2005/Atom}summary")
            )
            pub = _parse_rss_date(
                _text(item.find("pubDate")) or _text(item.find("{http://www.w3.org/2005/Atom}updated"))
            )
            canonical = canonicalize_url(link)
            external_id = hashlib.sha1(f"{feed_url}|{canonical}".encode("utf-8")).hexdigest()[:24]
            items.append(
                FetchedArticle(
                    provider=self.name,
                    external_id=f"rss-{external_id}",
                    canonical_url=canonical,
                    publisher="Банк России" if cbr_feed else publisher,
                    title=title,
                    excerpt=desc or None,
                    published_at=pub,
                    language="ru",
                    is_official=False,
                    payload={"feed_url": feed_url},
                )
            )
        return items
