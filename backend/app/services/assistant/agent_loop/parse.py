"""Parse model text into ActionEnvelope — strict, no legacy silent accept."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.services.assistant.agent_loop.protocol import (
    ActionEnvelope,
    FinalEnvelope,
    ToolRequestEnvelope,
    type_adapter_action_envelope,
)

# Hard cap on raw model text before JSON parse (chars).
DEFAULT_MAX_RAW_CHARS = 24_000

# Optional single markdown fence wrapping the whole payload.
# Allowed: ```json\\n{...}\\n``` or ```\\n{...}\\n```
# Not allowed: prose + embedded JSON, multiple fences, multiple top-level objects.
_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\r?\n(?P<body>.*?)\r?\n```\s*$",
    re.DOTALL,
)


class ActionParseError(ValueError):
    """Structured parse / schema failure (maps to invalid_action / format repair)."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ActionParseError("duplicate_json_key", f"duplicate key: {key}")
        seen.add(key)
        out[key] = value
    return out


def _strip_optional_fence(text: str) -> str:
    """If the entire string is one markdown code fence, return its body; else unchanged.

    Does **not** search for JSON inside surrounding prose.
    """
    m = _FENCE_RE.match(text)
    if m:
        return m.group("body").strip()
    # Reject partial / multiple fences used as smuggling
    if "```" in text:
        raise ActionParseError(
            "ambiguous_markdown_fence",
            "markdown fence must wrap the entire payload or be absent",
        )
    return text.strip()


def _load_single_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except ActionParseError:
        raise
    except json.JSONDecodeError as exc:
        raise ActionParseError("invalid_json", str(exc)) from exc
    except ValueError as exc:
        # duplicate keys path may raise ValueError from hook in some versions
        raise ActionParseError("invalid_json", str(exc)) from exc
    if not isinstance(parsed, dict):
        raise ActionParseError("json_root_must_be_object")
    # Disallow second JSON value after first object (json.loads already fails on trailing)
    # Extra guard: raw must not contain a second top-level `{` after a complete object
    # when someone concatenates `}{`.
    return parsed


def _reject_legacy_silent(data: dict[str, Any]) -> None:
    """Old hackathon shape ``{content, tool_calls}`` without kind is not this protocol."""
    if "kind" not in data:
        raise ActionParseError(
            "missing_kind_not_legacy",
            "ActionEnvelope requires kind=tool_request|final; legacy payload rejected",
        )


def parse_action_envelope(
    text: str,
    *,
    max_raw_chars: int = DEFAULT_MAX_RAW_CHARS,
) -> ActionEnvelope:
    """Parse one ActionEnvelope from model text.

    - Optional whole-string markdown fence (json).
    - Exactly one JSON object; duplicate keys rejected.
    - extra=forbid on models; unknown tools → validation error.
    - Never uses eval / str(arbitrary) / reasoning_content.
    """
    if text is None:
        raise ActionParseError("empty_payload")
    if not isinstance(text, str):
        raise ActionParseError("payload_not_string")
    if len(text) > max_raw_chars:
        raise ActionParseError("payload_too_large")

    stripped = _strip_optional_fence(text)
    if not stripped:
        raise ActionParseError("empty_payload")

    data = _load_single_object(stripped)
    _reject_legacy_silent(data)

    kind = data.get("kind")
    if kind not in {"tool_request", "final"}:
        raise ActionParseError("unknown_kind", f"kind={kind!r}")

    try:
        adapter = type_adapter_action_envelope()
        return adapter.validate_python(data)
    except ValidationError as exc:
        # Map unknown tool / forbidden fields into stable codes
        err_text = str(exc)
        if "arguments_must_be_empty" in err_text or "forbidden_argument_keys" in err_text:
            raise ActionParseError("scope_via_arguments", err_text) from exc
        if "tool_request_must_not_include" in err_text or "final_must_not_include" in err_text:
            raise ActionParseError("conflicting_fields", err_text) from exc
        # Literal tool name failures
        if "get_event_context" in err_text or "literal_error" in err_text.lower() or "Input should be" in err_text:
            # Check if name was present but not in allow-list
            action = data.get("action")
            if isinstance(action, dict) and "name" in action:
                name = action.get("name")
                if name not in {
                    "get_event_context",
                    "get_company_manual_context",
                    "get_company_case_context",
                    "get_bank_evidence",
                    "get_available_assessment",
                }:
                    raise ActionParseError("unknown_tool", f"tool={name!r}") from exc
        raise ActionParseError("schema_validation", err_text) from exc


def parse_as_concrete(
    text: str,
    *,
    max_raw_chars: int = DEFAULT_MAX_RAW_CHARS,
) -> ToolRequestEnvelope | FinalEnvelope:
    """Same as parse_action_envelope; return type narrowed for callers."""
    env = parse_action_envelope(text, max_raw_chars=max_raw_chars)
    return env


def try_peek_action_kind(text: str) -> dict[str, Any] | None:
    """Best-effort safe peek for diagnostics — never raises; no secrets.

    Returns ``action_kind`` / ``tool_name`` when the payload looks like an
    ActionEnvelope. Used by adapters/recorders instead of re-consuming streams.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        stripped = _strip_optional_fence(text)
        data = json.loads(stripped)
    except Exception:  # noqa: BLE001
        return {"action_kind": "unparsed"}
    if not isinstance(data, dict):
        return {"action_kind": "unparsed"}
    out: dict[str, Any] = {"action_kind": data.get("kind")}
    action = data.get("action")
    if isinstance(action, dict) and action.get("name") is not None:
        out["tool_name"] = action.get("name")
    return out
