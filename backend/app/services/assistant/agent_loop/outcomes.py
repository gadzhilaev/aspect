"""Typed loop outcomes — final success vs stopped (never a fake final)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.assistant.agent_loop.budget import LoopStopReason
from app.services.assistant.bank_evidence_citations import ValidatedCitation


@dataclass
class TraceStep:
    kind: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopFinalOutcome:
    status: Literal["final"] = "final"
    content: str = ""
    citations: list[ValidatedCitation] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)
    budget_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopStoppedOutcome:
    status: Literal["stopped"] = "stopped"
    reason: LoopStopReason = LoopStopReason.invalid_action
    detail: str = ""
    partial_content: str | None = None  # never published as completed answer
    trace: list[TraceStep] = field(default_factory=list)
    budget_snapshot: dict[str, Any] = field(default_factory=dict)


LoopOutcome = LoopFinalOutcome | LoopStoppedOutcome
