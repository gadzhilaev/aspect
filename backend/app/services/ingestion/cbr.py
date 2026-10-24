"""CBR official rates, key rate and news."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree.ElementTree import Element

import httpx

from app.services.ingestion.base import FetchedArticle, SourceProvider
from app.services.ingestion.conditional_http import HttpValidatorCache, conditional_get
from app.services.ingestion.normalize import canonicalize_url

CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
CBR_KEY_RATE_URL = "https://www.cbr.ru/hd_base/KeyRate/"
CBR_NEWS_RSS = "https://www.cbr.ru/rss/RssNews"


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


def _text(el: Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


class CbrProvider(SourceProvider):
    name = "cbr"
    is_official = True

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
        validator_cache: HttpValidatorCache | None = None,
    ) -> None:
        self._client = client
        self._timeout = timeout
        self._validator_cache = validator_cache
        self.last_fetch_errors: list[str] = []

    def _http(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(timeout=self._timeout, follow_redirects=True)

    def fetch(self) -> list[FetchedArticle]:
        self.last_fetch_errors = []
        owns = self._client is None
        client = self._http()
        try:
            items: list[FetchedArticle] = []
            items.extend(self._fetch_fx(client))
            items.extend(self._fetch_key_rate(client))
            items.extend(self._fetch_news_rss(client))
            return items
        finally:
            if owns:
                client.close()

    def _get(self, client: httpx.Client, url: str, *, label: str) -> bytes | None:
        outcome = conditional_get(client, url, cache=self._validator_cache)
        if outcome.not_modified:
            return None
        if outcome.error or outcome.content is None:
            if outcome.error:
                self.last_fetch_errors.append(f"{label}:{outcome.error}")
            return None
        return outcome.content

    def _fetch_fx(self, client: httpx.Client) -> list[FetchedArticle]:
        content = self._get(client, CBR_DAILY_URL, label="fx")
        if content is None:
            return []
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            self.last_fetch_errors.append("fx:parse_error")
            return []
        date = root.attrib.get("Date") or datetime.now(timezone.utc).strftime("%d.%m.%Y")
        wanted = {"USD", "EUR", "CNY"}
        lines: list[str] = []
        payload: dict[str, Any] = {"date": date, "rates": {}}
        for valute in root.findall("Valute"):
            char_code = _text(valute.find("CharCode"))
            if char_code not in wanted:
                continue
            value = _text(valute.find("Value")).replace(",", ".")
            nominal = _text(valute.find("Nominal")) or "1"
            name = _text(valute.find("Name"))
            lines.append(f"{char_code}: {value} ₽ за {nominal} ({name})")
            payload["rates"][char_code] = {"value": value, "nominal": nominal, "name": name}
        if not lines:
            return []
        title = f"Официальные курсы ЦБ на {date}"
        excerpt = "; ".join(lines)
        url = canonicalize_url(f"{CBR_DAILY_URL}?date_req={date}")
        external_id = f"cbr-fx-{date}"
        return [
            FetchedArticle(
                provider=self.name,
                external_id=external_id,
                canonical_url=url,
                publisher="Банк России",
                title=title,
                excerpt=excerpt,
                published_at=datetime.now(timezone.utc),
                language="ru",
                is_official=True,
                payload=payload,
            )
        ]

    def _fetch_key_rate(self, client: httpx.Client) -> list[FetchedArticle]:
        """Best-effort scrape of the latest key-rate row from CBR HTML table."""
        content = self._get(client, CBR_KEY_RATE_URL, label="keyrate")
        if content is None:
            return []
        try:
            html = content.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return []
        # Table cells often look like DD.MM.YYYY and rate like 21,00
        import re

        rows = re.findall(
            r"(\d{2}\.\d{2}\.\d{4})\s*</td>\s*<td[^>]*>\s*([\d,]+)",
            html,
            flags=re.IGNORECASE,
        )
        if not rows:
            return []
        date_s, rate_s = rows[0]
        rate = rate_s.replace(",", ".")
        title = f"Ключевая ставка Банка России: {rate}%"
        excerpt = f"По данным Банка России на {date_s} ключевая ставка составляет {rate}%."
        url = canonicalize_url(f"{CBR_KEY_RATE_URL}#rate-{date_s}")
        return [
            FetchedArticle(
                provider=self.name,
                external_id=f"cbr-keyrate-{date_s}",
                canonical_url=url,
                publisher="Банк России",
                title=title,
                excerpt=excerpt,
                published_at=datetime.now(timezone.utc),
                language="ru",
                is_official=True,
                payload={"date": date_s, "rate_percent": rate},
            )
        ]

    def _fetch_news_rss(self, client: httpx.Client) -> list[FetchedArticle]:
        content = self._get(client, CBR_NEWS_RSS, label="rss")
        if content is None:
            return []
        try:
            root = ET.fromstring(content)
        except Exception:  # noqa: BLE001
            self.last_fetch_errors.append("rss:parse_error")
            return []
        items: list[FetchedArticle] = []
        channel = root.find("channel")
        nodes = channel.findall("item") if channel is not None else root.findall(".//item")
        for item in nodes[:30]:
            title = _text(item.find("title"))
            link = _text(item.find("link")) or _text(item.find("guid"))
            if not title or not link:
                continue
            desc = _text(item.find("description"))
            pub = _parse_rss_date(_text(item.find("pubDate")))
            url = canonicalize_url(link)
            external_id = hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]
            items.append(
                FetchedArticle(
                    provider=self.name,
                    external_id=f"cbr-news-{external_id}",
                    canonical_url=url,
                    publisher="Банк России",
                    title=title,
                    excerpt=desc or None,
                    published_at=pub,
                    language="ru",
                    is_official=True,
                    payload={"source": "cbr_rss", "feed_url": CBR_NEWS_RSS},
                )
            )
        return items
