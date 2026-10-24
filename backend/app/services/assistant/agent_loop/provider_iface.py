"""Loop action provider interface + scripted test provider (no network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

from app.services.assistant.agent_loop.budget import ModelAttemptLease
from app.services.assistant.agent_loop.protocol import (
    ActionEnvelope,
    FinalEnvelope,
    ToolRequestEnvelope,
)

if TYPE_CHECKING:
    from app.services.assistant.agent_loop.budget import TurnBudget
    from app.services.assistant.agent_loop.sources import SourceLedger


@dataclass
class LoopModelRequest:
    """Payload handed to the provider for one model attempt.

    Scripted providers treat inclusion as «handed to test provider».
    ``HackathonLoopProvider`` confirms sources only after successful HTTP via
    ``SourceLedger.confirm_transport_sent``.
    """

    payload: dict[str, Any]
    lease: ModelAttemptLease
    user_question: str
    is_repair: bool = False
    repair_kind: str | None = None  # "format" | "citation" | None
    ledger: SourceLedger | None = None
    # Optional: provider marks transport_started / transport_response on real HTTP.
    budget: "TurnBudget | None" = None


class LoopActionProvider(Protocol):
    def next_action(self, request: LoopModelRequest) -> str | dict[str, Any] | ActionEnvelope:
        """Return raw text, dict, or already-parsed ActionEnvelope."""


StepFactory = Callable[[LoopModelRequest], str | dict[str, Any] | ActionEnvelope]


@dataclass
class ScriptedLoopProvider:
    """Deterministic provider: records every request; returns scripted steps."""

    steps: list[str | dict[str, Any] | ActionEnvelope | StepFactory]
    received: list[LoopModelRequest] = field(default_factory=list)
    _index: int = 0

    def next_action(self, request: LoopModelRequest) -> str | dict[str, Any] | ActionEnvelope:
        self.received.append(request)
        if self._index >= len(self.steps):
            raise RuntimeError("scripted_provider_exhausted")
        step = self.steps[self._index]
        self._index += 1
        if callable(step) and not isinstance(step, (FinalEnvelope, ToolRequestEnvelope)):
            return step(request)  # type: ignore[misc]
        return step  # type: ignore[return-value]

    @property
    def payloads(self) -> list[dict[str, Any]]:
        return [r.payload for r in self.received]
