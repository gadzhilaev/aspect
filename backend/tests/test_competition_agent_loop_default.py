"""Competition mode defaults ASSISTANT_AGENT_LOOP on when unset (K10)."""

from __future__ import annotations

from app.core.config import Settings


def test_competition_mode_enables_agent_loop_when_unset() -> None:
    s = Settings(
        competition_mode=True,
        assistant_provider="hackathon",
        hackathon_base_url="https://changellenge.up.railway.app/v1",
        hackathon_model="deepseek/deepseek-v4.1-flash",
    )
    assert s.competition_mode is True
    assert s.assistant_agent_loop is True


def test_competition_mode_respects_explicit_loop_off() -> None:
    s = Settings(
        competition_mode=True,
        assistant_provider="hackathon",
        hackathon_base_url="https://changellenge.up.railway.app/v1",
        hackathon_model="deepseek/deepseek-v4.1-flash",
        assistant_agent_loop=False,
    )
    assert s.assistant_agent_loop is False


def test_non_competition_keeps_loop_default_off() -> None:
    s = Settings(
        competition_mode=False,
        assistant_provider="mock",
    )
    assert s.assistant_agent_loop is False
