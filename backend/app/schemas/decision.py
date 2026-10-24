from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ActionStatus = Literal["todo", "in_progress", "done"]


class ActionItemOut(BaseModel):
    id: str
    title: str
    status: ActionStatus
    status_label: str
    assignee_name: str | None = None
    due_at: datetime | None = None


class DecisionEventOut(BaseModel):
    id: str
    title: str
    category: str
    category_label: str
    occurred_at: datetime | None = None
    is_demo: bool = False


class DecisionScenarioOut(BaseModel):
    id: str
    title: str
    reason: str
    is_estimate: bool = True
    # Stages 5.3–5.4 additive — rate/FX presentation contract (clients may ignore).
    presentation: dict[str, Any] | None = None
    model_version: str | None = None


class DecisionProgressOut(BaseModel):
    done: int
    total: int
    label: str


class DecisionCancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class DecisionDetailOut(BaseModel):
    id: str
    status: str
    status_label: str
    title: str
    summary: str
    expected_effect: str | None = None
    horizon: str | None = None
    confidence: float | None = None
    progress: DecisionProgressOut
    event: DecisionEventOut
    scenario: DecisionScenarioOut
    action_items: list[ActionItemOut] = Field(default_factory=list)
    conversation_href: str | None = None
    news_href: str
    created_at: datetime
    disclaimer: str
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    actions_locked: bool = False


class ActionItemPatchOut(BaseModel):
    id: str
    title: str
    status: ActionStatus
    status_label: str
    assignee_name: str | None = None
    due_at: datetime | None = None
    progress: DecisionProgressOut
