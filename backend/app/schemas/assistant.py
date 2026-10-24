from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


BlockType = Literal[
    "impact_summary",
    "claim_list",
    "scenario_comparison",
    "missing_data",
    "action_plan_draft",
    "source_list",
    "bank_evidence_list",
    "case_context_ref",
]


class AssistantBlock(BaseModel):
    type: BlockType
    title: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)


class AssistantMessageOut(BaseModel):
    id: str
    role: str
    content: str
    blocks: list[AssistantBlock] = Field(default_factory=list)
    client_message_id: str | None = None
    created_at: datetime


class AssistantConversationOut(BaseModel):
    id: str
    user_id: str
    company_id: str
    event_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    suggestion_chips: list[str] = Field(default_factory=list)
    # Human provenance for free-text explanations — never exposes provider secrets
    answer_basis: Literal[
        "ai_explain",
        "ai_explain_gigachat",
        "ai_explain_hackathon",
        "demo_explain",
    ] = "demo_explain"
    # Actual model id when answer_basis is hackathon (honest labeling; not a secret)
    answer_model: str | None = None
    # Additive (stage 3.2): discussion allowed without EventImpact.
    # calculation_unavailable ≠ monitoring_only.
    assessment_state: str | None = None
    has_impact_calculation: bool = True


ConversationListStatus = Literal[
    "active",
    "scenarios_ready",
    "draft_ready",
    "decision_saved",
    "decision_cancelled",
]


class AssistantConversationListItem(BaseModel):
    id: str
    event_id: str
    event_title: str
    event_category: str
    updated_at: datetime
    last_message_preview: str
    status: ConversationListStatus
    decision_id: str | None = None
    # Nullable when no usable EventImpact — never coerce unknown to 0.
    impact_score: float | None = None
    confidence: float | None = None
    has_impact_calculation: bool = False
    assessment_state: str | None = None
    has_scenarios: bool = False
    is_demo: bool = False


class CreateConversationIn(BaseModel):
    company_id: str


class PostMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    client_message_id: str | None = Field(default=None, max_length=64)


class PostMessageOut(BaseModel):
    user_message: AssistantMessageOut
    assistant_message: AssistantMessageOut
    reused: bool = False


class DraftDecisionIn(BaseModel):
    scenario_id: str | None = None
    solution_id: str | None = None
    note: str | None = None
    confirm: bool = False
    client_request_id: str | None = Field(default=None, max_length=64)


class DraftDecisionOut(BaseModel):
    status: Literal["draft", "confirmed"]
    decision_id: str | None = None
    draft: dict[str, Any]
    message: AssistantMessageOut | None = None
    disclaimer: str


class UserCompareScenariosIn(BaseModel):
    """Explicit user-triggered scenario calculation (no LLM). Stage 6.6."""

    client_request_id: str = Field(..., min_length=1, max_length=64)
    # Rate what-if: percentage points (п.п.), not percent.
    assumed_rate_change_pp: float | None = Field(
        default=None,
        description="Explicit key-rate what-if in percentage points (п.п.)",
    )
    # FX what-if: percent change of the quote rate.
    assumed_fx_change_percent: float | None = Field(
        default=None,
        description="Explicit FX rate what-if in percent (%)",
    )
    inventory_days: int = Field(default=14, ge=1, le=365)
    delay_days: int = Field(default=45, ge=1, le=365)


class UserCompareScenariosOut(BaseModel):
    status: Literal["ok", "missing_data", "unavailable", "running"]
    reused: bool = False
    result: dict[str, Any] = Field(default_factory=dict)
    message: AssistantMessageOut | None = None
    scenario_ids: list[str] = Field(default_factory=list)
    decision_created: bool = False
    next_step: str | None = None
    disclaimer: str = (
        "Расчёт выполнен по вашему запросу (не ответ модели). "
        "Решение не создаётся автоматически — выберите сценарий и подтвердите план отдельно."
    )
