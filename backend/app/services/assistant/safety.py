"""Safety helpers: treat news/user text as data, never as instructions."""

from __future__ import annotations

import re

from app.services.assistant.prompts import EVENT_DATA_WRAPPER, USER_DATA_WRAPPER

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"you\s+are\s+now", re.I),
    re.compile(r"раскрой\s+(системн|prompt)", re.I),
    re.compile(r"игнорируй\s+(все\s+)?(предыдущие|правила|инструкции)", re.I),
    re.compile(r"забудь\s+(все|правила|инструкции)", re.I),
]


def wrap_user_text(text: str) -> str:
    cleaned = (text or "").strip()
    return USER_DATA_WRAPPER.format(text=cleaned)


def wrap_event_text(text: str) -> str:
    cleaned = (text or "").strip()
    return EVENT_DATA_WRAPPER.format(text=cleaned)


def detect_injection_attempt(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in _INJECTION_PATTERNS)


def sanitize_for_model(text: str, *, kind: str = "user") -> str:
    """Return text wrapped so providers cannot treat it as system instructions."""
    if kind == "event":
        return wrap_event_text(text)
    return wrap_user_text(text)


def honesty_labels(*, is_demo: bool = False, is_estimate: bool = False) -> list[str]:
    """Legacy helper — prefer provenance.labels_for_block for new code.

    Numeric / structural blocks use company_calc only.
    Demo twin data must NOT be labelled demo_explain — that token is reserved for
    free-text mock explanations (conversation answer_basis), not news sources.
    ``is_demo`` is kept for call-site compatibility and intentionally unused.
    """
    from app.services.assistant.provenance import COMPANY_CALC

    _ = is_demo  # twin/demo flag is orthogonal to explanation provenance
    labels: list[str] = []
    if is_estimate:
        labels.append(COMPANY_CALC)
    return labels
