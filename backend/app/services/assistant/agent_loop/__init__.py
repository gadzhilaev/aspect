"""Multi-step assistant protocol + read-only runner (stages 4.2–4.5).

``ASSISTANT_AGENT_LOOP`` defaults to off (legacy ``post_message``).
When on with ``ASSISTANT_PROVIDER=hackathon``, ``post_message`` uses
``AgentLoopRunner`` (``AGENT_LOOP_RUNTIME_INTEGRATED=True``).
"""

from app.services.assistant.agent_loop.budget import (
    BudgetDefaults,
    BudgetExhausted,
    LoopStopReason,
    TurnBudget,
    TurnBudgetConfig,
)
from app.services.assistant.agent_loop.outcomes import (
    LoopFinalOutcome,
    LoopOutcome,
    LoopStoppedOutcome,
)
from app.services.assistant.agent_loop.parse import (
    ActionParseError,
    parse_action_envelope,
)
from app.services.assistant.agent_loop.protocol import (
    LOOP_TOOL_NAMES,
    ActionEnvelope,
    CitationDraft,
    FinalEnvelope,
    SourceInclusion,
    SourceRef,
    ToolAction,
    ToolRequestEnvelope,
    ToolResultEnvelope,
    ToolResultStatus,
)
from app.services.assistant.agent_loop.hackathon_loop import HackathonLoopProvider
from app.services.assistant.agent_loop.provider_iface import (
    LoopModelRequest,
    ScriptedLoopProvider,
)
from app.services.assistant.agent_loop.runner import AgentLoopRunner
from app.services.assistant.agent_loop.runtime import (
    AGENT_LOOP_RUNTIME_INTEGRATED,
    ensure_agent_loop_runtime_allowed,
)
from app.services.assistant.agent_loop.scope import ServerScope
from app.services.assistant.agent_loop.sources import (
    ExactQuotePolicy,
    SourceLedger,
)

__all__ = [
    "AGENT_LOOP_RUNTIME_INTEGRATED",
    "ActionEnvelope",
    "ActionParseError",
    "AgentLoopRunner",
    "BudgetDefaults",
    "BudgetExhausted",
    "CitationDraft",
    "ExactQuotePolicy",
    "FinalEnvelope",
    "HackathonLoopProvider",
    "LOOP_TOOL_NAMES",
    "LoopFinalOutcome",
    "LoopModelRequest",
    "LoopOutcome",
    "LoopStopReason",
    "LoopStoppedOutcome",
    "ScriptedLoopProvider",
    "ServerScope",
    "SourceInclusion",
    "SourceLedger",
    "SourceRef",
    "ToolAction",
    "ToolRequestEnvelope",
    "ToolResultEnvelope",
    "ToolResultStatus",
    "TurnBudget",
    "TurnBudgetConfig",
    "ensure_agent_loop_runtime_allowed",
    "parse_action_envelope",
]
