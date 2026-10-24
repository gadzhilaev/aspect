"""Canonical OCR fingerprint hashing (host-absolute paths excluded)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Absolute tool paths must not affect identity or be executed.
STRIP_KEYS = frozenset(
    {
        "tesseract_binary",
        "tessdata_dir",
        "binary",
    }
)

CANONICAL_KEYS = (
    "schema_version",
    "source_sha256",
    "tesseract_version_line",
    "lang",
    "psm",
    "preserve_interword_spaces",
    "eng_traineddata_sha256",
    "rus_traineddata_sha256",
)


def canonicalize_fingerprint(
    raw: dict[str, Any] | None,
    *,
    page_psm_used: list[int | None] | None = None,
) -> dict[str, Any]:
    """Build portable fingerprint dict from manifest fingerprint / tesseract block."""
    src = dict(raw or {})
    # Support nested tesseract block merged by caller
    out: dict[str, Any] = {}
    for key in CANONICAL_KEYS:
        if key == "psm":
            out[key] = src.get("psm", src.get("psm_default"))
        elif key == "tesseract_version_line":
            out[key] = src.get("tesseract_version_line") or src.get("version_line")
        else:
            out[key] = src.get(key)

    # Record distinct non-null page PSM values (fallback awareness) without host paths.
    if page_psm_used is not None:
        used = sorted({int(p) for p in page_psm_used if p is not None})
        out["page_psm_used"] = used
        default = out.get("psm")
        out["used_non_default_psm"] = bool(
            default is not None and any(p != int(default) for p in used)
        )
    return out


def fingerprint_hash(canonical: dict[str, Any]) -> str:
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def strip_absolute_tool_paths(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy without absolute tool location keys (for reporting)."""
    return {k: v for k, v in (raw or {}).items() if k not in STRIP_KEYS}
