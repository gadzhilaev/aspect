"""Bounded HTTP GET with optional ETag/Last-Modified and 429 Retry-After.

Used by ingestion providers so scheduled polls do not re-download unchanged feeds.
Cache keys are URL strings; values never include secrets or Authorization headers.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 20.0
MAX_RETRIES_429 = 2
MAX_RETRY_AFTER_S = 30.0


@dataclass
class FetchOutcome:
    """Result of a conditional GET."""

    status_code: int
    content: bytes | None
    not_modified: bool = False
    error: str | None = None


class HttpValidatorCache:
    """Persist ETag / Last-Modified per URL (JSON file)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._data: dict[str, dict[str, str]] = {}
        if path is not None and path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = {
                        str(k): {str(ak): str(av) for ak, av in (v or {}).items()}
                        for k, v in raw.items()
                        if isinstance(v, dict)
                    }
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                self._data = {}

    def headers_for(self, url: str) -> dict[str, str]:
        row = self._data.get(url) or {}
        out: dict[str, str] = {}
        etag = (row.get("etag") or "").strip()
        lm = (row.get("last_modified") or "").strip()
        if etag:
            out["If-None-Match"] = etag
        if lm:
            out["If-Modified-Since"] = lm
        return out

    def update_from_response(self, url: str, resp: httpx.Response) -> None:
        etag = (resp.headers.get("ETag") or "").strip()
        lm = (resp.headers.get("Last-Modified") or "").strip()
        if not etag and not lm:
            return
        row = dict(self._data.get(url) or {})
        if etag:
            row["etag"] = etag
        if lm:
            row["last_modified"] = lm
        self._data[url] = row
        self._persist()

    def _persist(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except OSError:
            logger.debug("http_validator_cache_persist_failed", exc_info=True)


def _retry_after_seconds(resp: httpx.Response) -> float:
    raw = (resp.headers.get("Retry-After") or "").strip()
    if not raw:
        return 2.0
    try:
        return min(float(raw), MAX_RETRY_AFTER_S)
    except ValueError:
        return 2.0


def conditional_get(
    client: httpx.Client,
    url: str,
    *,
    cache: HttpValidatorCache | None = None,
    max_retries_429: int = MAX_RETRIES_429,
    sleep_fn: Any = time.sleep,
) -> FetchOutcome:
    """GET with validators + limited 429 retries. Soft-fails into FetchOutcome.error."""
    headers = cache.headers_for(url) if cache is not None else {}
    attempt = 0
    while True:
        try:
            resp = client.get(url, headers=headers)
        except httpx.TimeoutException:
            return FetchOutcome(status_code=0, content=None, error="timeout")
        except httpx.HTTPError:
            return FetchOutcome(status_code=0, content=None, error="http_error")
        except Exception:  # noqa: BLE001
            return FetchOutcome(status_code=0, content=None, error="fetch_error")

        if resp.status_code == 304:
            return FetchOutcome(status_code=304, content=None, not_modified=True)

        if resp.status_code == 429 and attempt < max_retries_429:
            delay = _retry_after_seconds(resp)
            attempt += 1
            sleep_fn(delay)
            continue

        if resp.status_code == 429:
            return FetchOutcome(status_code=429, content=None, error="http_429")

        if resp.status_code >= 400:
            return FetchOutcome(
                status_code=resp.status_code,
                content=None,
                error=f"http_{resp.status_code}",
            )

        if cache is not None:
            cache.update_from_response(url, resp)
        return FetchOutcome(status_code=resp.status_code, content=resp.content)
