"""SourceProvider contract and shared article DTO."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FetchedArticle:
    provider: str
    external_id: str
    canonical_url: str
    publisher: str
    title: str
    excerpt: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    is_official: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


class SourceProvider(ABC):
    name: str
    is_official: bool = False

    @abstractmethod
    def fetch(self) -> list[FetchedArticle]:
        raise NotImplementedError
