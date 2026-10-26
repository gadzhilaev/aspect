"""Shared httpx client factory for hackathon organizers' gateway."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import httpx

from app.core.config import get_settings


def hackathon_http_client_kwargs(*, timeout: float) -> dict:
    """Build httpx.Client kwargs (SOCKS/HTTP proxy optional, never trust system proxy)."""
    settings = get_settings()
    proxy = (getattr(settings, "hackathon_socks_proxy", None) or "").strip()
    kwargs: dict = {
        "timeout": timeout,
        "follow_redirects": False,
        "trust_env": False,
    }
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs


@contextmanager
def hackathon_http_client(
    *,
    timeout: float,
    injected: httpx.Client | None = None,
) -> Iterator[httpx.Client]:
    if injected is not None:
        yield injected
        return
    with httpx.Client(**hackathon_http_client_kwargs(timeout=timeout)) as client:
        yield client
