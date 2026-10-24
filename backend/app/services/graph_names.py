"""Detect unconfirmed / placeholder twin node names.

Users sometimes type UI labels like «Не знаю» into chain fields. Those must not
become a confirmed supply-chain path with an output share.
"""

from __future__ import annotations

import re
import unicodedata

# Explicit unknown / empty answers — not a hardcode of any one user phrase.
_UNCONFIRMED_EXACT = frozenset(
    {
        "не знаю",
        "неизвестно",
        "не известно",
        "нет данных",
        "нет информации",
        "без данных",
        "unknown",
        "n/a",
        "na",
        "none",
        "null",
        "undefined",
        "tbd",
        "todo",
        "?",
        "-",
        "—",
        "–",
    }
)


def normalize_node_name(name: str | None) -> str:
    raw = unicodedata.normalize("NFKC", (name or "")).strip().lower()
    raw = re.sub(r"\s+", " ", raw)
    return raw


def is_unconfirmed_node_name(name: str | None) -> bool:
    """True when the name is an explicit unknown/empty marker, not real twin data."""
    norm = normalize_node_name(name)
    if not norm:
        return True
    if norm in _UNCONFIRMED_EXACT:
        return True
    # «не знаю …» / «unknown …» prefixes
    if norm.startswith("не знаю") or norm.startswith("unknown"):
        return True
    return False


def path_has_unconfirmed_nodes(nodes: list[dict] | None) -> bool:
    if not nodes:
        return False
    for node in nodes:
        if is_unconfirmed_node_name(node.get("name") if isinstance(node, dict) else None):
            return True
    return False
