"""Strict ActionEnvelope / ToolResultEnvelope types for the agent loop (4.2).

Discriminated union: ``tool_request`` vs ``final``.
Unknown fields forbidden. Legacy ``{content, tool_calls}`` is not accepted as this protocol.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

# MVP read-only allow-list (stage 4.2). Unknown names → validation error, not legacy run_tool.
LOOP_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "get_event_context",
        "get_company_manual_context",
        "get_company_case_context",
        "get_bank_evidence",
        "get_available_assessment",
    }
)

LoopToolName = Literal[
    "get_event_context",
    "get_company_manual_context",
    "get_company_case_context",
    "get_bank_evidence",
    "get_available_assessment",
]

ToolResultStatus = Literal["ok", "unavailable", "error", "denied", "truncated"]

SourceInclusion = Literal[
    "tool_result_obtained",
    "prepared_for_context",
    "sent_to_model",
]

# Reject scope / injection via arguments — only empty object allowed for MVP tools.
_FORBIDDEN_ARG_KEYS = frozenset(
    {
        "company_id",
        "user_id",
        "event_id",
        "ocr_run_id",
        "ocr_run_ids",
        "storage_root",
        "url",
        "sql",
        "query",
        "path",
        "http",
        "headers",
        "authorization",
        "api_key",
        "database_url",
    }
)

ShortGoal = Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]


class EmptyToolArguments(BaseModel):
    """MVP loop tools take no model-supplied arguments (server scope is separate)."""

    model_config = ConfigDict(extra="forbid")


class ToolAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: LoopToolName
    goal: ShortGoal | None = None
    arguments: EmptyToolArguments = Field(default_factory=EmptyToolArguments)

    @field_validator("arguments", mode="before")
    @classmethod
    def _only_empty_object(cls, value: Any) -> Any:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("arguments_must_be_object")
        if value:
            # Any non-empty dict is invalid for MVP; surface forbidden keys preferentially.
            forbidden = sorted(
                str(k) for k in value if str(k).lower() in _FORBIDDEN_ARG_KEYS
            )
            if forbidden:
                raise ValueError(f"forbidden_argument_keys:{','.join(forbidden)}")
            raise ValueError("arguments_must_be_empty")
        return {}


class CitationDraft(BaseModel):
    """Structured citation claim from the model (server still validates against sent sources)."""

    model_config = ConfigDict(extra="forbid")

    fragment_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    revision: int | None = None
    section_hint: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    quoted_text: Annotated[str, StringConstraints(max_length=4000)] | None = None

    @field_validator("revision")
    @classmethod
    def _revision_positive(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("revision_must_be_positive_int")
        return value


class ToolRequestEnvelope(BaseModel):
    """One tool request — must not carry a final user answer."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool_request"]
    action: ToolAction

    @model_validator(mode="before")
    @classmethod
    def _reject_final_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Conflict / legacy bleed
        for banned in ("content", "bank_evidence_citations", "tool_calls", "trace", "plan"):
            if banned in data and data[banned] not in (None, [], {}):
                raise ValueError(f"tool_request_must_not_include:{banned}")
        # Even null content key with other noise — forbid presence of final keys entirely
        for banned in ("content", "bank_evidence_citations", "tool_calls", "trace", "plan"):
            if banned in data:
                raise ValueError(f"tool_request_must_not_include:{banned}")
        return data


class FinalEnvelope(BaseModel):
    """Final user-visible answer — must not request tools in the same object."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["final"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
    bank_evidence_citations: list[CitationDraft] = Field(default_factory=list, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def _reject_action_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for banned in ("action", "tool_calls", "trace", "plan", "reasoning", "reasoning_content"):
            if banned in data:
                raise ValueError(f"final_must_not_include:{banned}")
        return data


ActionEnvelope = Annotated[
    ToolRequestEnvelope | FinalEnvelope,
    Field(discriminator="kind"),
]


class SourceRef(BaseModel):
    """Provenance pointer. Inclusion stage is assigned by the server, not the model."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["bank_fragment", "event_source", "case_snapshot", "assessment"]
    id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    revision: int | None = None
    inclusion: SourceInclusion = "tool_result_obtained"
    # Exact quote text only when fully included (never mid-cut); None if omitted for size.
    exact_quote: str | None = None
    exact_quote_excluded: bool = False


class ToolResultEnvelope(BaseModel):
    """Server → model observation. call_id / step assigned by server."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool_result"] = "tool_result"
    call_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    name: LoopToolName
    status: ToolResultStatus
    data: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=50)
    reason_code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None = None
    step: int | None = Field(default=None, ge=1, le=100)

    @field_validator("data")
    @classmethod
    def _data_is_object(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("data_must_be_object")
        return value


def type_adapter_action_envelope():
    """Lazy TypeAdapter for parse helpers (pydantic v2)."""
    from pydantic import TypeAdapter

    return TypeAdapter(ActionEnvelope)
