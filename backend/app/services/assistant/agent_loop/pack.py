"""Serialize loop payloads without mid-cutting JSON strings."""

from __future__ import annotations

import json
from typing import Any


def json_size(obj: Any) -> int:
    return len(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    )


def pack_object_to_budget(
    data: dict[str, Any],
    *,
    max_chars: int,
    drop_keys_first: tuple[str, ...] = ("text_data", "text_plain_for_validation", "fragments"),
) -> tuple[dict[str, Any], bool]:
    """Fit ``data`` under ``max_chars`` by dropping optional keys / list tails.

    Never truncates a JSON serialization with a string slice.
    Returns ``(packed, truncated)``.
    """
    if max_chars < 2:
        return {"status": "truncated", "reason_code": "budget_too_small"}, True

    current: dict[str, Any] = dict(data)
    if json_size(current) <= max_chars:
        return current, False

    truncated = False

    # 1) Drop heavy optional keys (whole keys only).
    for key in drop_keys_first:
        if key in current:
            current = {k: v for k, v in current.items() if k != key}
            truncated = True
            if json_size(current) <= max_chars:
                current = {**current, "_truncated": True}
                return current, True

    # 2) Shorten list fields from the end (drop whole items).
    for key, value in list(current.items()):
        if not isinstance(value, list) or not value:
            continue
        while value and json_size(current) > max_chars:
            value = value[:-1]
            current[key] = value
            truncated = True
        if json_size(current) <= max_chars:
            current = {**current, "_truncated": True}
            return current, True

    # 3) Replace oversized nested dicts with stubs (no mid-string cut).
    for key, value in list(current.items()):
        if json_size(current) <= max_chars:
            break
        if isinstance(value, (dict, list)) and key not in {"status", "available", "name"}:
            current[key] = {"_omitted": True, "_reason": "size_budget"}
            truncated = True

    if json_size(current) <= max_chars:
        if truncated:
            current = {**current, "_truncated": True}
        return current, truncated

    # Last resort: minimal envelope (still valid JSON object).
    stub = {
        "status": "truncated",
        "reason_code": "result_exceeded_budget",
        "_truncated": True,
    }
    if json_size(stub) <= max_chars:
        return stub, True
    return {"status": "truncated"}, True
