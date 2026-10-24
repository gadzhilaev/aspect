"""Stage 4.6.1 — context overflow, HTTP accounting, sources after pack (offline)."""

from __future__ import annotations

import copy
import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.assistant.agent_loop.budget import (
    DEFAULT_MAX_MODEL_HTTP,
    DEFAULT_MAX_RESULT_CHARS,
    DEFAULT_MAX_TRANSCRIPT_CHARS,
    BudgetExhausted,
    LoopStopReason,
    TurnBudget,
    TurnBudgetConfig,
)
from app.services.assistant.agent_loop.context_pack import (
    fragment_ids_in_payload,
    prepare_turn_payload,
)
from app.services.assistant.agent_loop.loop_projections import (
    project_bank_for_model,
    project_case_for_model,
    project_event_for_model,
    slim_source_refs_for_model,
)
from app.services.assistant.agent_loop.outcomes import LoopFinalOutcome, LoopStoppedOutcome
from app.services.assistant.agent_loop.pack import json_size
from app.services.assistant.agent_loop.parse import try_peek_action_kind
from app.services.assistant.agent_loop.protocol import SourceRef
from app.services.assistant.agent_loop.provider_iface import ScriptedLoopProvider
from app.services.assistant.agent_loop.runner import AgentLoopRunner
from app.services.assistant.agent_loop.sources import SourceLedger
from app.services.assistant.agent_loop.api_integration import (
    _incomplete_content,
    _stop_error_code,
)


# Defaults must not grow (stage 4.6.1).
def test_default_limits_unchanged():
    assert DEFAULT_MAX_MODEL_HTTP == 4
    assert DEFAULT_MAX_RESULT_CHARS == 4000
    assert DEFAULT_MAX_TRANSCRIPT_CHARS == 12_000


def _tool(name: str, data: dict[str, Any], *, refs: list[dict] | None = None) -> dict:
    return {
        "call_id": f"lc_{name}",
        "name": name,
        "status": "ok",
        "data": data,
        "source_refs": refs or [],
        "step": 1,
        "role": "tool_result_data",
    }


def _bank_frag(fid: str, text: str, *, revision: int = 1) -> dict[str, Any]:
    return {
        "fragment_id": fid,
        "revision": revision,
        "text_plain": text,
        "text_kind": "exact_quote",
        "content_type": "research",
        "publication_date": "2026-09-01",
        "source_role": "bank_research",
        "document_title": "Doc",
    }


def test_three_tools_fit_under_transcript_with_overhead():
    """event → bank → case must fit in 12k after compact projections + JSON overhead."""
    event = project_event_for_model(
        {
            "event": {
                "id": "evt1",
                "title": "Ставка",
                "summary": "Краткое описание события " * 20,
                "occurred_at": "2026-09-20",
                "category": "macro",
            },
            "sources": [{"publisher": "X", "excerpt": "excerpt " * 30}],
            "company": {"id": "c1", "name": "Co"},
            "assessment_state": "missing",
            "has_impact_calculation": False,
            "labels": ["news_source"],
        }
    )
    case = project_case_for_model(
        {
            "status": "ok",
            "availability": "available",
            "snapshot_id": "snap1",
            "pinned_snapshot_id": "snap1",
            "profile": {
                "okved_code": "62.01",
                "city": "Москва",
                "products": [
                    {"code": "RKO", "status": "active"},
                    {"code": "LOA", "status": "active"},
                    {"code": "DEP", "status": "absent"},
                ],
                "group": {"status": "unknown", "is_conflicted": False},
            },
            "unknown_fields": ["workers_fns", "revenue"],
            "conflict_fields": [],
            "interpretation_limits": ["case_data_is_not_bank_opinion"],
            "known_fields": ["okved_code", "city"],
        }
    )
    # Three medium fragments — whole texts, no href duplication
    texts = [
        "Факт: ключевая ставка составляет 14 процентов годовых. " * 8,
        "Прогноз: ожидается сохранение ставки на текущем уровне. " * 8,
        "Комментарий по кредитованию малого бизнеса. " * 8,
    ]
    bank = project_bank_for_model(
        {
            "status": "available",
            "available": True,
            "fragments": [
                {
                    "fragment_id": f"f{i}",
                    "revision": 1,
                    "text_plain_for_validation": t,
                    "content_type": "research",
                    "publication_date": "2026-09-01",
                    "source_role": "bank_research",
                    "document_href": "https://example/should-not-appear",
                    "fragment_href": "https://example/frag",
                }
                for i, t in enumerate(texts)
            ],
        }
    )
    assert "document_href" not in json.dumps(bank)
    obs = [
        _tool("get_event_context", event),
        _tool(
            "get_bank_evidence",
            bank,
            refs=[{"type": "bank_fragment", "id": "f0", "exact_quote": texts[0]}],
        ),
        _tool("get_company_case_context", case),
    ]
    # source_refs must not keep duplicated quotes after slim
    assert "exact_quote" not in json.dumps(slim_source_refs_for_model(obs[1]["source_refs"]))

    packed = prepare_turn_payload(
        user_question="Разбери эту новость для моей компании",
        task={
            "constraints": ["read_only_tools_only", "cite_only_dispatched_bank_fragments"],
            "available_tools": [{"name": "get_event_context"}],
            "note": "tools required",
        },
        observations=obs,
        conversation_history=[],
        history_incomplete=False,
        history_omitted_count=0,
        budget_meta={"final_only": False, "attempt_index": 4},
        repair_note=None,
        revision_conflicts=[],
        max_chars=DEFAULT_MAX_TRANSCRIPT_CHARS,
    )
    assert packed.fits
    assert packed.payload_chars <= DEFAULT_MAX_TRANSCRIPT_CHARS
    names = [o.get("name") for o in packed.payload["observations"]]
    assert "get_event_context" in names
    assert "get_bank_evidence" in names
    assert "get_company_case_context" in names
    # Preserve uncertainty marks
    case_obs = next(o for o in packed.payload["observations"] if o["name"] == "get_company_case_context")
    assert "workers_fns" in (case_obs["data"].get("unknown_fields") or [])
    bank_obs = next(o for o in packed.payload["observations"] if o["name"] == "get_bank_evidence")
    plains = " ".join(
        str(f.get("text_plain") or "") for f in (bank_obs["data"].get("fragments") or [])
    )
    assert "14" in plains
    assert "Прогноз" in plains or "прогноз" in plains.lower()


def test_oversized_indivisible_fragment_dropped_whole():
    huge = "X" * 9000
    bank = project_bank_for_model(
        {
            "available": True,
            "fragments": [
                {
                    "fragment_id": "keep",
                    "revision": 1,
                    "text_plain_for_validation": "short ok quote",
                    "content_type": "research",
                },
                {
                    "fragment_id": "huge",
                    "revision": 1,
                    "text_plain_for_validation": huge,
                    "content_type": "research",
                },
            ],
        }
    )
    obs = [_tool("get_bank_evidence", bank)]
    packed = prepare_turn_payload(
        user_question="Q",
        task={"constraints": ["c"], "available_tools": [], "note": "n"},
        observations=obs,
        conversation_history=[],
        history_incomplete=False,
        history_omitted_count=0,
        budget_meta={},
        repair_note=None,
        revision_conflicts=[],
        max_chars=4000,
    )
    assert packed.fits
    ids = fragment_ids_in_payload(packed.payload)
    assert "huge" not in ids
    assert "huge" in packed.dropped_fragment_ids
    # Excluded source must not be citable from payload
    assert "keep" in ids or packed.context_incomplete


def test_excluded_fragment_not_in_cite_scope():
    ledger = SourceLedger()
    for fid in ("a", "b"):
        ref = SourceRef(type="bank_fragment", id=fid, revision=1)
        ledger.record_obtained(ref)
        ledger.mark_prepared(
            ref,
            citation_payload={
                "fragment_id": fid,
                "revision": 1,
                "text_kind": "exact_quote",
                "text_plain_for_validation": f"text-{fid}",
            },
        )
        ledger.mark_dispatched(
            ref,
            citation_payload={
                "fragment_id": fid,
                "revision": 1,
                "text_kind": "exact_quote",
                "text_plain_for_validation": f"text-{fid}",
            },
        )
    ledger.begin_request_cite_scope({"a"})
    index = ledger.passed_index_for_citations()
    assert "a" in index
    assert "b" not in index


def test_size_check_before_http_does_not_count_transport():
    budget = TurnBudget(config=TurnBudgetConfig(max_transcript_chars=50, max_model_http=4))
    with pytest.raises(BudgetExhausted) as ei:
        budget.check_prepared_payload_chars(100)
    assert ei.value.reason == LoopStopReason.context_limit
    assert budget.model_http_used == 0
    assert budget.model_http_transport == 0


def test_transport_not_refunded_after_start():
    budget = TurnBudget(config=TurnBudgetConfig(max_model_http=2, timeout_s=90))
    lease = budget.begin_model_attempt()
    assert lease.attempt_index == 1
    budget.mark_transport_started()
    # Timeout after start — slot stays spent
    assert budget.model_http_used == 1
    assert budget.model_http_transport == 1
    assert budget.model_http_remaining == 1


def test_user_facing_stop_reasons_distinct():
    assert "лимит шагов" in _incomplete_content(LoopStopReason.budget_exhausted)
    ctx = _incomplete_content(LoopStopReason.context_limit)
    assert "контекст" in ctx.lower() or "лимит запроса" in ctx.lower()
    assert "гарантирует" in ctx  # must not promise retry-same as fix
    assert "бюджет провайдера" in _incomplete_content(LoopStopReason.provider_daily_budget).lower()
    assert _stop_error_code(LoopStopReason.context_limit) == "ASSISTANT_LOOP_CONTEXT_LIMIT"
    assert _stop_error_code(LoopStopReason.provider_daily_budget) == (
        "ASSISTANT_LOOP_PROVIDER_DAILY_BUDGET"
    )


def test_scripted_event_bank_case_final_under_budget(monkeypatch):
    """Full loop: 3 tools + final ≤ 4 HTTP; assessment not required."""
    from app.services.assistant.agent_loop import runner as runner_mod
    from app.services.assistant.agent_loop.scope import ResolvedScope

    event_data = project_event_for_model(
        {
            "event": {"id": "e", "title": "T", "summary": "S", "occurred_at": "2026-09-20"},
            "sources": [],
            "company": {"id": "c", "name": "N"},
            "has_impact_calculation": False,
        }
    )
    bank_data = project_bank_for_model(
        {
            "available": True,
            "fragments": [
                {
                    "fragment_id": "frag1",
                    "revision": 1,
                    "text_plain_for_validation": "Ставка 14 процентов.",
                    "content_type": "research",
                    "publication_date": "2026-09-01",
                    "source_role": "bank_research",
                }
            ],
        }
    )
    case_data = project_case_for_model(
        {
            "status": "ok",
            "availability": "available",
            "snapshot_id": "snap",
            "pinned_snapshot_id": "snap",
            "unknown_fields": ["revenue"],
            "conflict_fields": [],
            "interpretation_limits": ["limit"],
            "profile": {
                "products": [{"code": "LOA", "status": "active"}],
                "group": {"status": "unknown", "is_conflicted": False},
            },
        }
    )

    class FakeExec:
        def __init__(self, name: str, data: dict):
            from app.services.assistant.agent_loop.protocol import ToolResultEnvelope

            self.envelope = ToolResultEnvelope(
                call_id=f"lc_{name}",
                name=name,  # type: ignore[arg-type]
                status="ok",
                data=data,
                source_refs=(
                    [
                        SourceRef(
                            type="bank_fragment",
                            id="frag1",
                            revision=1,
                        )
                    ]
                    if name == "get_bank_evidence"
                    else (
                        [SourceRef(type="case_snapshot", id="snap")]
                        if name == "get_company_case_context"
                        else [SourceRef(type="event_source", id="e")]
                    )
                ),
                step=1,
            )
            self.obtained_bank = (
                [
                    {
                        "fragment_id": "frag1",
                        "revision": 1,
                        "text_plain_for_validation": "Ставка 14 процентов.",
                        "content_type": "research",
                        "publication_date": "2026-09-01",
                        "source_role": "bank_research",
                    }
                ]
                if name == "get_bank_evidence"
                else []
            )
            self.dispatch_bank = list(self.obtained_bank)
            self.excluded_bank_ids: list[str] = []
            self.pinned_snapshot_id = "snap" if name == "get_company_case_context" else None

    def fake_execute(db, *, resolved, name, step, max_result_chars, cache):
        mapping = {
            "get_event_context": FakeExec("get_event_context", event_data),
            "get_bank_evidence": FakeExec("get_bank_evidence", bank_data),
            "get_company_case_context": FakeExec(
                "get_company_case_context", case_data
            ),
        }
        return mapping[name]

    monkeypatch.setattr(runner_mod, "execute_loop_tool", fake_execute)
    monkeypatch.setattr(
        runner_mod,
        "resolve_server_scope",
        lambda db, scope: MagicMock(spec=ResolvedScope),
    )

    steps = [
        {
            "kind": "tool_request",
            "action": {"name": "get_event_context", "arguments": {}},
        },
        {
            "kind": "tool_request",
            "action": {"name": "get_bank_evidence", "arguments": {}},
        },
        {
            "kind": "tool_request",
            "action": {"name": "get_company_case_context", "arguments": {}},
        },
        {
            "kind": "final",
            "content": "Итог с учётом ставки 14%.",
            "bank_evidence_citations": [
                {
                    "fragment_id": "frag1",
                    "revision": 1,
                    "quoted_text": "Ставка 14 процентов.",
                }
            ],
        },
    ]
    provider = ScriptedLoopProvider(steps=steps)
    budget = TurnBudget(config=TurnBudgetConfig())
    runner = AgentLoopRunner(
        db=MagicMock(),
        scope=MagicMock(),
        provider=provider,
        budget=budget,
    )
    outcome = runner.run(user_question="Разбери новость")
    assert isinstance(outcome, LoopFinalOutcome)
    assert budget.model_http_used == 4
    assert budget.model_http_used <= DEFAULT_MAX_MODEL_HTTP
    # Scripted provider does not mark transport — reserved != transport until HTTP
    assert budget.model_http_transport == 0
    # Final payload to model must have carried all three tools
    last = provider.payloads[-1]
    names = [o.get("name") for o in last.get("observations") or []]
    assert set(names) >= {
        "get_event_context",
        "get_bank_evidence",
        "get_company_case_context",
    }
    assert json_size(last) <= DEFAULT_MAX_TRANSCRIPT_CHARS


def test_context_limit_stop_without_fake_final(monkeypatch):
    from app.services.assistant.agent_loop import runner as runner_mod

    monkeypatch.setattr(
        runner_mod,
        "resolve_server_scope",
        lambda db, scope: MagicMock(),
    )

    provider = ScriptedLoopProvider(
        steps=[{"kind": "final", "content": "should not run", "bank_evidence_citations": []}]
    )
    budget = TurnBudget(
        config=TurnBudgetConfig(max_transcript_chars=80, max_model_http=4)
    )
    runner = AgentLoopRunner(
        db=MagicMock(),
        scope=MagicMock(),
        provider=provider,
        budget=budget,
    )
    # Tiny limit + long question + long task note forces context_limit before HTTP
    outcome = runner.run(user_question="Q" * 200)
    assert isinstance(outcome, LoopStoppedOutcome)
    assert outcome.reason == LoopStopReason.context_limit
    assert budget.model_http_used == 0
    assert budget.model_http_transport == 0
    assert provider._index == 0  # never called


def test_recorder_peek_does_not_need_raw_stream():
    peek = try_peek_action_kind(
        '```json\n{"kind":"tool_request","action":{"name":"get_event_context","arguments":{}}}\n```'
    )
    assert peek is not None
    assert peek["action_kind"] == "tool_request"
    assert peek["tool_name"] == "get_event_context"


def test_per_tool_sum_not_equal_transcript_budget():
    """Three × 4000 does not guarantee payload ≤ 12000 once JSON wrappers exist."""
    chunk = {"blob": "Z" * 3900}
    obs = [_tool(f"t{i}", copy.deepcopy(chunk)) for i in range(3)]
    total_parts = sum(json_size(o) for o in obs)
    assert total_parts > 11000
    wrapped = {
        "user_question": "q",
        "task": {"constraints": ["a"], "note": "n", "available_tools": []},
        "observations": obs,
        "budget": {"attempt_index": 1},
    }
    # Overhead pushes over naive 3*4000 thinking
    assert json_size(wrapped) > total_parts
