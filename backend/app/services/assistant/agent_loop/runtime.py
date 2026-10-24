"""Feature-flag gate for the agent loop (stage 4.5: wired into post_message)."""

from __future__ import annotations

from app.core.errors import AppError

# True after post_message can run AgentLoopRunner for ASSISTANT_AGENT_LOOP=true.
AGENT_LOOP_RUNTIME_INTEGRATED: bool = True


def ensure_agent_loop_runtime_allowed(*, enabled: bool) -> None:
    """Refuse enabling the loop until runtime wiring exists."""
    if not enabled:
        return
    if AGENT_LOOP_RUNTIME_INTEGRATED:
        return
    raise AppError(
        "ASSISTANT_AGENT_LOOP_NOT_READY",
        "Многошаговый цикл ассистента ещё не подключён к runtime (ASSISTANT_AGENT_LOOP)",
        501,
        details=[
            {
                "reason": "runtime_not_integrated",
                "flag": "ASSISTANT_AGENT_LOOP",
                "integrated": False,
            }
        ],
    )
