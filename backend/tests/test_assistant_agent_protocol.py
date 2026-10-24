"""Stage 4.2 — agent loop protocol, parse, budget (no network / no orchestrator wiring)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services.assistant.agent_loop.budget import (
    BudgetExhausted,
    LoopStopReason,
    TurnBudget,
    TurnBudgetConfig,
)
from app.services.assistant.agent_loop.parse import ActionParseError, parse_action_envelope
from app.services.assistant.agent_loop.protocol import (
    FinalEnvelope,
    SourceRef,
    ToolRequestEnvelope,
    ToolResultEnvelope,
)
from app.services.assistant.agent_loop.runtime import (
    AGENT_LOOP_RUNTIME_INTEGRATED,
    ensure_agent_loop_runtime_allowed,
)
from app.services.assistant.agent_loop.sources import ExactQuotePolicy, SourceLedger


# ---------- parse / schema ----------


def test_valid_tool_request():
    raw = json.dumps(
        {
            "kind": "tool_request",
            "action": {
                "name": "get_event_context",
                "goal": "Уточнить факты события",
                "arguments": {},
            },
        },
        ensure_ascii=False,
    )
    env = parse_action_envelope(raw)
    assert isinstance(env, ToolRequestEnvelope)
    assert env.action.name == "get_event_context"


def test_valid_final_with_citations():
    raw = json.dumps(
        {
            "kind": "final",
            "content": "Краткий ответ пользователю.",
            "bank_evidence_citations": [
                {"fragment_id": "frag-1", "revision": 2},
            ],
        },
        ensure_ascii=False,
    )
    env = parse_action_envelope(raw)
    assert isinstance(env, FinalEnvelope)
    assert env.content.startswith("Краткий")
    assert env.bank_evidence_citations[0].fragment_id == "frag-1"


def test_markdown_fence_whole_payload_ok():
    body = '{"kind":"final","content":"Ок","bank_evidence_citations":[]}'
    fenced = f"```json\n{body}\n```"
    env = parse_action_envelope(fenced)
    assert isinstance(env, FinalEnvelope)


def test_prose_embedded_json_rejected():
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope('Вот ответ: {"kind":"final","content":"x"} хвост')
    assert ei.value.code in {"invalid_json", "ambiguous_markdown_fence"}


def test_unknown_kind():
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope('{"kind":"plan","goal":"x"}')
    assert ei.value.code == "unknown_kind"


def test_unknown_tool_not_legacy():
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope(
            json.dumps(
                {
                    "kind": "tool_request",
                    "action": {"name": "compare_scenarios", "arguments": {}},
                }
            )
        )
    assert ei.value.code == "unknown_tool"


def test_unknown_fields_forbidden():
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope(
            json.dumps(
                {
                    "kind": "final",
                    "content": "x",
                    "bank_evidence_citations": [],
                    "extra_field": 1,
                }
            )
        )
    assert ei.value.code == "schema_validation"


def test_conflict_final_plus_action():
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope(
            json.dumps(
                {
                    "kind": "final",
                    "content": "текст",
                    "action": {"name": "get_event_context", "arguments": {}},
                }
            )
        )
    assert ei.value.code == "conflicting_fields"


def test_conflict_tool_request_with_content():
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope(
            json.dumps(
                {
                    "kind": "tool_request",
                    "action": {"name": "get_bank_evidence", "arguments": {}},
                    "content": "нельзя",
                }
            )
        )
    assert ei.value.code == "conflicting_fields"


def test_scope_via_arguments_rejected():
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope(
            json.dumps(
                {
                    "kind": "tool_request",
                    "action": {
                        "name": "get_company_case_context",
                        "arguments": {"company_id": "other-co"},
                    },
                }
            )
        )
    assert ei.value.code == "scope_via_arguments"


def test_nonempty_arguments_rejected():
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope(
            json.dumps(
                {
                    "kind": "tool_request",
                    "action": {
                        "name": "get_available_assessment",
                        "arguments": {"foo": 1},
                    },
                }
            )
        )
    assert ei.value.code == "scope_via_arguments"


def test_empty_final_rejected():
    with pytest.raises(ActionParseError):
        parse_action_envelope(
            json.dumps({"kind": "final", "content": "   ", "bank_evidence_citations": []})
        )


def test_bad_citation_shape():
    with pytest.raises(ActionParseError):
        parse_action_envelope(
            json.dumps(
                {
                    "kind": "final",
                    "content": "ok",
                    "bank_evidence_citations": [{"fragment_id": ""}],
                }
            )
        )


def test_legacy_without_kind_rejected():
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope(
            json.dumps({"content": "старый формат", "tool_calls": []})
        )
    assert ei.value.code == "missing_kind_not_legacy"


def test_duplicate_json_keys():
    raw = '{"kind":"final","kind":"tool_request","content":"x"}'
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope(raw)
    assert ei.value.code == "duplicate_json_key"


def test_payload_too_large():
    with pytest.raises(ActionParseError) as ei:
        parse_action_envelope('{"kind":"final","content":"x"}', max_raw_chars=5)
    assert ei.value.code == "payload_too_large"


def test_tool_result_envelope_server_fields():
    tr = ToolResultEnvelope(
        call_id="c1",
        name="get_event_context",
        status="ok",
        data={"title": "t"},
        source_refs=[],
        reason_code=None,
        step=1,
    )
    assert tr.call_id == "c1"
    with pytest.raises(ValidationError):
        ToolResultEnvelope(
            call_id="c1",
            name="compare_scenarios",  # type: ignore[arg-type]
            status="ok",
        )


# ---------- budget ----------


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def test_exactly_n_model_attempts():
    clock = FakeClock()
    budget = TurnBudget(
        config=TurnBudgetConfig(max_model_http=4, timeout_s=90),
        clock=clock,
    )
    for i in range(4):
        lease = budget.begin_model_attempt()
        assert lease.attempt_index == i + 1
        assert lease.remaining_timeout_s == 90.0
    with pytest.raises(BudgetExhausted) as ei:
        budget.begin_model_attempt()
    assert ei.value.reason == LoopStopReason.budget_exhausted
    assert budget.model_http_used == 4


def test_failed_http_attempt_still_counted():
    """Reserve before send — failure after send must not refund (mechanic only)."""
    budget = TurnBudget(config=TurnBudgetConfig(max_model_http=2, timeout_s=90))
    budget.begin_model_attempt()
    # simulate failed HTTP — no refund API exists
    assert budget.model_http_used == 1
    budget.begin_model_attempt()
    with pytest.raises(BudgetExhausted):
        budget.begin_model_attempt()


def test_one_shared_repair():
    budget = TurnBudget(
        config=TurnBudgetConfig(max_model_http=4, max_repairs=1, timeout_s=90)
    )
    budget.begin_model_attempt(as_repair=True)
    assert budget.repairs_used == 1
    assert budget.model_http_used == 1
    with pytest.raises(BudgetExhausted) as ei:
        budget.begin_model_attempt(as_repair=True)
    assert "repair" in ei.value.detail


def test_deadline_fake_clock_no_sleep():
    clock = FakeClock(0.0)
    budget = TurnBudget(
        config=TurnBudgetConfig(max_model_http=4, timeout_s=10.0),
        clock=clock,
    )
    budget.begin_model_attempt()
    clock.advance(10.1)
    with pytest.raises(BudgetExhausted) as ei:
        budget.begin_model_attempt()
    assert ei.value.reason == LoopStopReason.timeout


def test_remaining_timeout_for_transport():
    clock = FakeClock(0.0)
    budget = TurnBudget(
        config=TurnBudgetConfig(max_model_http=4, timeout_s=90.0),
        clock=clock,
    )
    clock.advance(30.0)
    lease = budget.begin_model_attempt()
    assert abs(lease.remaining_timeout_s - 60.0) < 1e-6


def test_last_call_final_only():
    budget = TurnBudget(
        config=TurnBudgetConfig(max_model_http=2, max_tool_calls=3, timeout_s=90)
    )
    assert budget.allows_tool_request() is True
    budget.begin_model_attempt()
    assert budget.model_http_remaining == 1
    assert budget.is_final_only_mode() is True
    assert budget.allows_tool_request() is False


def test_tool_budget():
    budget = TurnBudget(
        config=TurnBudgetConfig(max_model_http=4, max_tool_calls=2, timeout_s=90)
    )
    budget.begin_tool_call()
    budget.begin_tool_call()
    with pytest.raises(BudgetExhausted) as ei:
        budget.begin_tool_call()
    assert ei.value.reason == LoopStopReason.budget_exhausted


def test_transcript_size_budget_is_per_payload_not_cumulative():
    budget = TurnBudget(
        config=TurnBudgetConfig(max_transcript_chars=100, timeout_s=90)
    )
    budget.record_transcript_chars(80)
    # Second attempt with a smaller payload must not sum with the first.
    budget.record_transcript_chars(30)
    assert budget.transcript_chars == 30
    assert budget.peak_payload_chars == 80
    with pytest.raises(BudgetExhausted) as ei:
        budget.record_transcript_chars(101)
    assert ei.value.reason == LoopStopReason.context_limit


def test_stop_reasons_distinct_from_final():
    assert LoopStopReason.budget_exhausted.value != "final"
    assert set(LoopStopReason) >= {
        LoopStopReason.budget_exhausted,
        LoopStopReason.context_limit,
        LoopStopReason.timeout,
        LoopStopReason.invalid_action,
        LoopStopReason.no_progress,
        LoopStopReason.provider_daily_budget,
    }


# ---------- sources ----------


def test_source_inclusion_stages_and_citable():
    ledger = SourceLedger()
    ref = SourceRef(type="bank_fragment", id="f1", revision=2)
    ledger.record_obtained(ref)
    assert ledger.citable_refs() == []
    ledger.mark_prepared(ref)
    assert ledger.citable_refs() == []
    ledger.mark_sent(ref)
    assert len(ledger.citable_refs()) == 1
    assert "f1" in ledger.passed_index_for_citations()


def test_exact_quote_not_mid_cut():
    policy = ExactQuotePolicy(max_quote_chars=10)
    text, excluded = policy.accept_exact_quote("12345678901", remaining_chars=100)
    assert text is None and excluded is True
    text2, excluded2 = policy.accept_exact_quote("12345", remaining_chars=100)
    assert text2 == "12345" and excluded2 is False

    ledger = SourceLedger(policy=policy)
    ref = SourceRef(type="bank_fragment", id="f1", revision=1)
    ledger.record_obtained(ref)
    out = ledger.attach_exact_quote(ref, "too-long-quote-here", remaining_chars=5)
    assert out.exact_quote_excluded is True
    ledger.mark_sent(out)
    # Excluded quote must not remain as citable bank basis
    assert ledger.passed_index_for_citations() == {}


# ---------- config / flag ----------


def test_default_flag_off(monkeypatch):
    monkeypatch.delenv("ASSISTANT_AGENT_LOOP", raising=False)
    get_settings.cache_clear()
    s = Settings()
    assert s.assistant_agent_loop is False
    ensure_agent_loop_runtime_allowed(enabled=False)
    get_settings.cache_clear()


def test_flag_on_allowed_when_runtime_integrated():
    assert AGENT_LOOP_RUNTIME_INTEGRATED is True
    ensure_agent_loop_runtime_allowed(enabled=True)


def test_invalid_config_limits():
    with pytest.raises(ValidationError):
        Settings(assistant_loop_max_model_http=0)
    with pytest.raises(ValidationError):
        Settings(assistant_loop_timeout_s=0)
    with pytest.raises(ValueError):
        TurnBudgetConfig(max_model_http=0)


def test_settings_budget_config_defaults():
    s = Settings()
    cfg = s.agent_loop_budget_config()
    assert cfg.max_model_http == 4
    assert cfg.max_tool_calls == 3
    assert cfg.max_repairs == 1
    assert cfg.timeout_s == 90.0


def test_orchestrator_routes_loop_behind_flag():
    """Stage 4.5: loop path is gated; legacy body remains for flag off."""
    import inspect

    from app.services.assistant import orchestrator

    src = inspect.getsource(orchestrator.post_message)
    assert "assistant_agent_loop" in src
    assert "post_message_agent_loop" in src
    # Legacy generate path still present after the early return
    assert "provider.generate" in src
