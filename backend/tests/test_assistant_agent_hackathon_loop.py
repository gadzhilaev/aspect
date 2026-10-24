"""Stage 4.4 — HackathonLoopProvider + AgentLoopRunner on mocked HTTP (no network)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event as sa_event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models import Company, CompanyMembership, Decision, Event, EventImpact, Scenario, User
from app.models.bank_materials import BankDocument, BankDocumentFile, BankFragment, BankOcrRun
from app.services.assistant.agent_loop.budget import LoopStopReason, TurnBudget, TurnBudgetConfig
from app.services.assistant.agent_loop.hackathon_loop import HackathonLoopProvider
from app.services.assistant.agent_loop.outcomes import LoopFinalOutcome, LoopStoppedOutcome
from app.services.assistant.agent_loop.runner import AgentLoopRunner
from app.services.assistant.agent_loop.runtime import AGENT_LOOP_RUNTIME_INTEGRATED
from app.services.assistant.agent_loop.scope import ServerScope
from app.services.assistant.context_builder import CALCULATION_UNAVAILABLE
from app.services.assistant.hackathon import HackathonProvider
from app.services.bank_materials.load import load_bank_document
from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
from tests.test_bank_import_dry_run import _build_valid_corpus, _confirmed_fragment

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://changellenge.up.railway.app/v1"
MODEL = "deepseek/deepseek-v4.1-flash"


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


class _FakeTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.handler(request)


def _assistant_message(content: str, *, finish_reason: str = "stop") -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _tool(name: str) -> str:
    return json.dumps(
        {"kind": "tool_request", "action": {"name": name, "arguments": {}}},
        ensure_ascii=False,
    )


def _final(content: str, citations: list | None = None) -> str:
    return json.dumps(
        {
            "kind": "final",
            "content": content,
            "bank_evidence_citations": citations or [],
        },
        ensure_ascii=False,
    )


def _req_json(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content.decode("utf-8"))


@pytest.fixture
def loop_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "agent_hack_loop.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "agent-hack-loop-secret")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    monkeypatch.setenv("ASSISTANT_AGENT_LOOP", "false")
    monkeypatch.setenv("CASE_CONTEXT_SLOT_KEY", "")
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", "")
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GIGACHAT_AUTH_KEY", raising=False)
    get_settings.cache_clear()
    command.upgrade(_alembic_config(), "head")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield SessionLocal, tmp_path, monkeypatch, engine
    finally:
        engine.dispose()
        get_settings.cache_clear()


def _seed(session: Session, *, with_impact: bool = False) -> tuple[str, str, str]:
    user_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    session.add(
        User(
            id=user_id,
            email=f"hl_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("HackLoop1!"),
            display_name="HL",
            email_verified_at=datetime.now(timezone.utc),
        )
    )
    session.flush()
    session.add(
        Company(
            id=company_id,
            name="HL Co",
            industry="manufacturing",
            size_band="small",
            hq_region="Москва",
            profile_status="ready",
            digital_twin_status="built",
            digital_twin_coverage=0.5,
            is_demo=False,
            created_by=user_id,
        )
    )
    session.flush()
    session.add(
        CompanyMembership(
            id=str(uuid.uuid4()), user_id=user_id, company_id=company_id, role="owner"
        )
    )
    session.add(
        Event(
            id=event_id,
            title="ЦБ сохранил ключевую ставку",
            summary="Банк России оставил ключевую ставку без изменений.",
            category="macro",
            event_type="policy",
            severity=40.0,
            urgency_default="watch",
            status="active",
            occurred_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
            match_countries_json=[],
            match_categories_json=["rates"],
            match_currencies_json=[],
            match_materials_json=[],
            attributes_json={},
            is_demo=True,
        )
    )
    session.flush()
    if with_impact:
        session.add(
            EventImpact(
                id=str(uuid.uuid4()),
                event_id=event_id,
                company_id=company_id,
                impact_score=30.0,
                urgency="watch",
                confidence=0.5,
                reason_summary="test",
                exposure_value=None,
                exposure_label=None,
                exposure_unit=None,
                score_breakdown_json={},
                claims_json={},
                status="action_required",
                model_version="impact-v1.1",
            )
        )
    session.commit()
    return user_id, company_id, event_id


def _load_bank(tmp_path: Path, engine, monkeypatch, *, slug: str = "hl-rate"):
    fragments = [
        _confirmed_fragment(
            id="hl_rate_quote",
            exact_quote="ЦБ сохранил ключевую ставку на уровне 14 процентов.",
            ocr_text="ocr hidden",
        ),
    ]
    ocr, pdf = _build_valid_corpus(
        tmp_path / slug,
        slug=slug,
        pages=1,
        fragments=fragments,
        identity={
            "confirmed_title": "HL rate",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-09-11",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "2026-09-11",
            "period_covered_status": "unknown",
            "topics": ["key_rate"],
            "topics_status": "confirmed",
            "staleness_note": None,
            "is_current_stance": False,
        },
    )
    parent = tmp_path / f"stg-{slug}"
    parent.mkdir(parents=True, exist_ok=True)
    staging = stage_corpus(input_dir=ocr, pdf_dir=pdf, staging_parent=parent)
    plan, errs, _ = build_prepared_document(
        staging.ocr_dir / slug,
        input_dir=staging.ocr_dir,
        pdf_dir=staging.pdf_dir,
        storage_root=staging.storage_root,
    )
    assert plan is not None and not errs
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        load_bank_document(session, plan)
        session.commit()
        doc = session.scalar(select(BankDocument).where(BankDocument.slug == slug))
        file = session.scalar(
            select(BankDocumentFile).where(BankDocumentFile.document_id == doc.id)
        )
        run = session.scalar(
            select(BankOcrRun).where(BankOcrRun.document_file_id == file.id)
        )
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", run.id)
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", str(staging.storage_root))
    get_settings.cache_clear()
    return run.id


def _provider(transport: _FakeTransport) -> HackathonLoopProvider:
    client = httpx.Client(transport=transport)
    return HackathonLoopProvider(
        api_key="hk-test-key",
        model=MODEL,
        base_url=BASE,
        http_client=client,
        transport_timeout_s=45.0,
    )


def _counts(session: Session) -> dict[str, int]:
    return {
        "impact": session.scalar(select(func.count()).select_from(EventImpact)) or 0,
        "scenario": session.scalar(select(func.count()).select_from(Scenario)) or 0,
        "decision": session.scalar(select(func.count()).select_from(Decision)) or 0,
    }


def test_tool_then_observation_in_next_http_then_final(loop_db):
    SessionLocal, tmp_path, monkeypatch, engine = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    bodies = [
        _assistant_message(_tool("get_event_context")),
        _assistant_message(_final("Итог по событию")),
    ]
    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(BASE)
        assert MODEL in request.content.decode("utf-8")
        assert b"api.openai.com" not in request.url.raw_host
        body = _req_json(request)
        assert body["model"] == MODEL
        assert "tools" not in body
        assert "response_format" not in body
        i = idx["i"]
        idx["i"] += 1
        if i == 0:
            # First request: no full case/bank/assessment bodies
            raw = request.content.decode("utf-8")
            assert "get_bank_evidence" in raw  # tool listed in system
            assert '"profile"' not in raw or "observations" in raw
            user = body["messages"][-1]["content"]
            assert "user_question" in user
            assert "observations" in user
        if i == 1:
            user = body["messages"][-1]["content"]
            assert "get_event_context" in user
            assert "ключевую ставку" in user
            assert body["messages"][0]["content"].startswith("Ты — серверный")
        return httpx.Response(200, json=bodies[i])

    transport = _FakeTransport(handler)
    provider = _provider(transport)
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
        ).run(user_question="Что случилось?")

    assert isinstance(out, LoopFinalOutcome)
    assert out.content.startswith("Итог")
    assert len(transport.calls) == 2
    assert provider.http_attempts == 2


def test_two_tools_then_final(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session, with_impact=False)

    seq = [
        _assistant_message(_tool("get_event_context")),
        _assistant_message(_tool("get_available_assessment")),
        _assistant_message(_final("два шага готовы")),
    ]
    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        if i == 2:
            user = _req_json(request)["messages"][-1]["content"]
            assert "get_event_context" in user
            assert "unavailable" in user or CALCULATION_UNAVAILABLE in user
        return httpx.Response(200, json=seq[i])

    transport = _FakeTransport(handler)
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport),
        ).run(user_question="два")

    assert isinstance(out, LoopFinalOutcome)
    assert len(transport.calls) == 3


def test_bank_absent_first_then_present_and_citable(loop_db):
    SessionLocal, tmp_path, monkeypatch, engine = loop_db
    _load_bank(tmp_path, engine, monkeypatch)
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    idx = {"i": 0}
    cited: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        user = _req_json(request)["messages"][-1]["content"]
        if i == 0:
            assert "14 процентов" not in user
            return httpx.Response(200, json=_assistant_message(_tool("get_bank_evidence")))
        if i == 1:
            assert "14 процентов" in user
            assert "text_plain" in user
            # fragment_id appears in observation DATA actually sent over HTTP
            import re

            m = re.search(r'"fragment_id"\s*:\s*"([^"]+)"', user)
            assert m, "fragment_id must be present in HTTP body"
            cited["fid"] = m.group(1)
            rm = re.search(r'"revision"\s*:\s*(\d+)', user)
            cited["rev"] = int(rm.group(1)) if rm else 1
            return httpx.Response(
                200,
                json=_assistant_message(
                    _final(
                        "По банку",
                        [{"fragment_id": cited["fid"], "revision": cited["rev"]}],
                    )
                ),
            )
        raise AssertionError("extra http")

    transport = _FakeTransport(handler)
    provider = _provider(transport)
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
        ).run(user_question="банк")

    assert isinstance(out, LoopFinalOutcome)
    assert len(out.citations) == 1
    assert provider.last_sent_manifest
    assert provider.last_sent_manifest[0].fragment_id == cited["fid"]


def test_excluded_fragment_not_citable_via_ghost_id(loop_db):
    SessionLocal, tmp_path, monkeypatch, engine = loop_db
    _load_bank(tmp_path, engine, monkeypatch, slug="hl-excl")
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        if i == 0:
            return httpx.Response(200, json=_assistant_message(_tool("get_bank_evidence")))
        return httpx.Response(
            200,
            json=_assistant_message(
                _final("bad", [{"fragment_id": "never-sent-frag", "revision": 1}])
            ),
        )

    transport = _FakeTransport(handler)
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport),
            budget=TurnBudget(config=TurnBudgetConfig(max_repairs=0, timeout_s=90)),
        ).run(user_question="cite ghost")

    assert isinstance(out, LoopStoppedOutcome)
    assert "citation" in out.detail


def test_unavailable_assessment_in_http_body(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session, with_impact=False)

    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        if i == 0:
            return httpx.Response(
                200, json=_assistant_message(_tool("get_available_assessment"))
            )
        user = _req_json(request)["messages"][-1]["content"]
        assert "unavailable" in user
        assert CALCULATION_UNAVAILABLE in user
        return httpx.Response(200, json=_assistant_message(_final("понял unavailable")))

    transport = _FakeTransport(handler)
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport),
        ).run(user_question="оценка?")

    assert isinstance(out, LoopFinalOutcome)
    assert len(transport.calls) == 2


def test_invalid_json_one_format_repair(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        if i == 0:
            return httpx.Response(200, json=_assistant_message("это не json envelope"))
        user = _req_json(request)["messages"][-1]["content"]
        assert "format_repair" in user or "repair" in user
        return httpx.Response(200, json=_assistant_message(_final("починили")))

    transport = _FakeTransport(handler)
    provider = _provider(transport)
    with SessionLocal() as session:
        budget = TurnBudget(config=TurnBudgetConfig(max_model_http=4, max_repairs=1))
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
            budget=budget,
        ).run(user_question="repair")

    assert isinstance(out, LoopFinalOutcome)
    assert budget.repairs_used == 1
    assert len(transport.calls) == 2


def test_citation_repair_blocked_after_format_repair(loop_db):
    """Shared repair budget: format then bad citation → no second repair."""
    SessionLocal, tmp_path, monkeypatch, engine = loop_db
    _load_bank(tmp_path, engine, monkeypatch, slug="hl-rep")
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        if i == 0:
            return httpx.Response(200, json=_assistant_message("not-json"))
        if i == 1:
            # After format repair: tool then we need another path — return tool
            return httpx.Response(200, json=_assistant_message(_tool("get_bank_evidence")))
        if i == 2:
            return httpx.Response(
                200,
                json=_assistant_message(
                    _final("x", [{"fragment_id": "ghost", "revision": 1}])
                ),
            )
        raise AssertionError(f"unexpected http #{i}")

    transport = _FakeTransport(handler)
    with SessionLocal() as session:
        budget = TurnBudget(config=TurnBudgetConfig(max_model_http=4, max_repairs=1))
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport),
            budget=budget,
        ).run(user_question="no second repair")

    assert isinstance(out, LoopStoppedOutcome)
    assert budget.repairs_used == 1
    assert "citation" in out.detail
    # No 4th HTTP for citation repair
    assert len(transport.calls) == 3


def test_401_and_budget_no_retry(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    transport = _FakeTransport(handler_401)
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport),
        ).run(user_question="auth")
    assert isinstance(out, LoopStoppedOutcome)
    assert len(transport.calls) == 1
    assert "UNAUTHORIZED" in out.detail

    def handler_budget(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Budget has been exceeded")

    transport2 = _FakeTransport(handler_budget)
    with SessionLocal() as session:
        out2 = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport2),
        ).run(user_question="budget")
    assert isinstance(out2, LoopStoppedOutcome)
    assert out2.reason == LoopStopReason.provider_daily_budget
    assert len(transport2.calls) == 1


def test_timeout_and_truncated(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    def handler_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    transport = _FakeTransport(handler_timeout)
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport),
        ).run(user_question="timeout")
    assert isinstance(out, LoopStoppedOutcome)
    assert out.reason == LoopStopReason.timeout
    assert len(transport.calls) == 1

    def handler_trunc(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_assistant_message('{"kind":"final","content":"x"}', finish_reason="length"),
        )

    transport2 = _FakeTransport(handler_trunc)
    with SessionLocal() as session:
        out2 = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport2),
            budget=TurnBudget(config=TurnBudgetConfig(max_repairs=0)),
        ).run(user_question="trunc")
    assert isinstance(out2, LoopStoppedOutcome)
    assert len(transport2.calls) == 1


def test_final_only_and_max_four_http(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    seq = [
        _tool("get_event_context"),
        _tool("get_available_assessment"),
        _tool("get_company_case_context"),
        _final("done"),
    ]
    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        body = _req_json(request)
        if i == 3:
            assert "FINAL_ONLY=true" in body["messages"][0]["content"]
            data = body["messages"][-1]["content"]
            assert "final_only" in data
        return httpx.Response(200, json=_assistant_message(seq[i]))

    transport = _FakeTransport(handler)
    provider = _provider(transport)
    with SessionLocal() as session:
        budget = TurnBudget(config=TurnBudgetConfig(max_model_http=4, max_tool_calls=3))
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
            budget=budget,
        ).run(user_question="4")

    assert isinstance(out, LoopFinalOutcome)
    assert len(transport.calls) == 4
    assert provider.http_attempts == 4
    assert budget.model_http_used == 4


def test_tool_on_last_slot_stopped(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    seq = [
        _tool("get_event_context"),
        _tool("get_available_assessment"),
        _tool("get_company_case_context"),
        _tool("get_bank_evidence"),
    ]
    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        return httpx.Response(200, json=_assistant_message(seq[i]))

    transport = _FakeTransport(handler)
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport),
            budget=TurnBudget(config=TurnBudgetConfig(max_model_http=4, max_tool_calls=3)),
        ).run(user_question="last tool")

    assert isinstance(out, LoopStoppedOutcome)
    assert "last_model_slot" in out.detail
    assert len(transport.calls) == 4


def test_base_url_model_no_other_providers(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{BASE}/chat/completions"
        assert request.headers["Authorization"] == "Bearer hk-test-key"
        body = _req_json(request)
        assert body["model"] == MODEL
        host = request.url.host
        assert "openai.com" not in host
        assert "sberbank" not in host
        return httpx.Response(200, json=_assistant_message(_final("ok")))

    transport = _FakeTransport(handler)
    with SessionLocal() as session:
        AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport),
        ).run(user_question="url")
    assert len(transport.calls) == 1


def test_no_new_impact_scenario_decision(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session, with_impact=True)
        before = _counts(session)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_assistant_message(_final("stable")))

    transport = _FakeTransport(handler)
    with SessionLocal() as session:
        AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport),
        ).run(user_question="stable")
        after = _counts(session)
    assert after == before


def test_legacy_hackathon_provider_still_works(monkeypatch):
    """Legacy generate path unchanged — prose/JSON still accepted there."""
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("HACKATHON_API_KEY", "hk-test-key")
    monkeypatch.setenv("HACKATHON_BASE_URL", BASE)
    monkeypatch.setenv("HACKATHON_MODEL", MODEL)
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_assistant_message(
                json.dumps(
                    {"content": "legacy ok", "tool_calls": [], "bank_evidence_citations": []}
                )
            ),
        )

    transport = _FakeTransport(handler)
    client = httpx.Client(transport=transport)
    p = HackathonProvider(
        api_key="hk-test-key", model=MODEL, base_url=BASE, http_client=client
    )
    result = p.generate(
        context={"event": {"title": "t"}, "company": {"id": "c"}},
        history=[],
        user_text="hi",
    )
    assert result.content == "legacy ok"
    assert len(transport.calls) == 1
    get_settings.cache_clear()


def test_prose_not_final_in_loop_adapter(loop_db):
    assert AGENT_LOOP_RUNTIME_INTEGRATED is True
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed(session)

    def handler(request: httpx.Request) -> httpx.Response:
        # Plain prose — must NOT become final in loop mode
        return httpx.Response(200, json=_assistant_message("просто текст без envelope"))

    transport = _FakeTransport(handler)
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=_provider(transport),
            budget=TurnBudget(config=TurnBudgetConfig(max_repairs=0)),
        ).run(user_question="prose")
    assert isinstance(out, LoopStoppedOutcome)
    assert not isinstance(out, LoopFinalOutcome)


def test_forbidden_host_rejected():
    with pytest.raises(AppError) as ei:
        HackathonLoopProvider(
            api_key="k",
            model=MODEL,
            base_url="https://api.openai.com/v1",
        )
    # Normal mode: forbidden host → PROVIDER_MISCONFIGURED (no HTTP).
    assert ei.value.code == "PROVIDER_MISCONFIGURED"
    assert ei.value.details and ei.value.details[0].get("reason") == "forbidden_base_url"
