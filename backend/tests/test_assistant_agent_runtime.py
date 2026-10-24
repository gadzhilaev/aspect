"""Stage 4.3 — internal read-only agent loop with scripted provider (no network)."""

from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event as sa_event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models import (
    Company,
    CompanyMembership,
    Decision,
    Event,
    EventImpact,
    Scenario,
    User,
)
from app.models.bank_materials import BankDocument, BankDocumentFile, BankFragment, BankOcrRun
from app.services.assistant.agent_loop.budget import (
    LoopStopReason,
    TurnBudget,
    TurnBudgetConfig,
)
from app.services.assistant.agent_loop.outcomes import LoopFinalOutcome, LoopStoppedOutcome
from app.services.assistant.agent_loop.provider_iface import ScriptedLoopProvider
from app.services.assistant.agent_loop.runner import AgentLoopRunner
from app.services.assistant.agent_loop.runtime import (
    AGENT_LOOP_RUNTIME_INTEGRATED,
    ensure_agent_loop_runtime_allowed,
)
from app.services.assistant.agent_loop.scope import ServerScope
from app.services.assistant.agent_loop.sources import SourceLedger
from app.services.assistant.agent_loop.protocol import SourceRef
from app.services.assistant.context_builder import CALCULATION_UNAVAILABLE
from app.services.bank_materials.load import load_bank_document
from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
from tests.test_bank_import_dry_run import _build_valid_corpus, _confirmed_fragment

ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


@pytest.fixture
def loop_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "agent_loop.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "agent-loop-4-3-secret")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    monkeypatch.setenv("ASSISTANT_AGENT_LOOP", "false")
    monkeypatch.setenv("CASE_CONTEXT_SLOT_KEY", "")
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", "")
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", "")
    get_settings.cache_clear()
    command.upgrade(_alembic_config(), "head")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield SessionLocal, tmp_path, monkeypatch, engine, url
    finally:
        engine.dispose()
        get_settings.cache_clear()


def _seed_user_company_event(session: Session, *, with_impact: bool = True) -> tuple[str, str, str]:
    """Return ``(user_id, company_id, event_id)`` — safe after session close."""
    user_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    user = User(
        id=user_id,
        email=f"loop_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("LoopTest1!"),
        display_name="Loop User",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    company = Company(
        id=company_id,
        name="Loop Co",
        industry="manufacturing",
        size_band="small",
        hq_region="Москва",
        profile_status="ready",
        digital_twin_status="built",
        digital_twin_coverage=0.5,
        is_demo=False,
        created_by=user_id,
    )
    session.add(company)
    session.flush()
    session.add(
        CompanyMembership(
            id=str(uuid.uuid4()), user_id=user_id, company_id=company_id, role="owner"
        )
    )
    event = Event(
        id=event_id,
        title="Тестовое событие loop",
        summary="Краткое описание для agent loop.",
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
    session.add(event)
    session.flush()
    if with_impact:
        session.add(
            EventImpact(
                id=str(uuid.uuid4()),
                event_id=event_id,
                company_id=company_id,
                impact_score=33.0,
                urgency="watch",
                confidence=0.6,
                reason_summary="Тестовая оценка.",
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


def _configure_bank(monkeypatch, *, run_id: str, storage_root: Path) -> None:
    monkeypatch.setenv("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", run_id)
    monkeypatch.setenv("BANK_MATERIALS_STORAGE_ROOT", str(storage_root))
    get_settings.cache_clear()


def _load_bank(tmp_path: Path, engine, *, slug: str = "loop-rate"):
    fragments = [
        _confirmed_fragment(
            id="loop_rate_quote",
            exact_quote="ЦБ сохранил ключевую ставку на уровне 14 процентов.",
            ocr_text="ocr must not reach provider",
        ),
    ]
    ocr, pdf = _build_valid_corpus(
        tmp_path / slug,
        slug=slug,
        pages=1,
        fragments=fragments,
        identity={
            "confirmed_title": "Loop rate note",
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
        frags = list(
            session.scalars(select(BankFragment).where(BankFragment.ocr_run_id == run.id)).all()
        )
        return {"staging": staging, "run_id": run.id, "fragments": frags}


def _tool(name: str) -> dict:
    return {"kind": "tool_request", "action": {"name": name, "arguments": {}}}


def _final(content: str, citations: list | None = None) -> dict:
    return {
        "kind": "final",
        "content": content,
        "bank_evidence_citations": citations or [],
    }


def _counts(session: Session):
    return {
        "impact": session.scalar(select(func.count()).select_from(EventImpact)) or 0,
        "scenario": session.scalar(select(func.count()).select_from(Scenario)) or 0,
        "decision": session.scalar(select(func.count()).select_from(Decision)) or 0,
        "company": session.scalar(select(func.count()).select_from(Company)) or 0,
    }


# ---------- scenarios ----------


def test_tool_observation_final(loop_db):
    SessionLocal, tmp_path, monkeypatch, engine, url = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)
        before = _counts(session)

    provider = ScriptedLoopProvider(
        steps=[
            _tool("get_event_context"),
            lambda req: _final(
                f"ok:{req.payload['observations'][-1]['data']['event']['title']}"
            ),
        ]
    )
    with SessionLocal() as session:
        runner = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
        )
        out = runner.run(user_question="Что случилось?")
        after = _counts(session)

    assert isinstance(out, LoopFinalOutcome)
    assert "Тестовое событие" in out.content
    assert len(provider.received) == 2
    # Manual twin is server-seeded (not case/bank/assessment bodies).
    seed_obs = provider.received[0].payload["observations"]
    assert len(seed_obs) == 1
    assert seed_obs[0]["name"] == "get_company_manual_context"
    assert seed_obs[0].get("server_seeded") is True
    assert "bank_evidence" not in provider.received[0].payload
    assert "impact" not in provider.received[0].payload
    names = [o["name"] for o in provider.received[1].payload["observations"]]
    assert names == ["get_company_manual_context", "get_event_context"]
    assert provider.received[1].payload["observations"][-1]["role"] == "tool_result_data"
    assert after == before


def test_two_tools_then_final(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    provider = ScriptedLoopProvider(
        steps=[
            _tool("get_event_context"),
            _tool("get_available_assessment"),
            lambda req: _final(
                "saw:"
                + req.payload["observations"][1]["name"]
                + "+"
                + req.payload["observations"][2]["status"]
            ),
        ]
    )
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
        ).run(user_question="Два инструмента")

    assert isinstance(out, LoopFinalOutcome)
    assert "get_event_context+unavailable" in out.content
    assert len(provider.received) == 3
    assert provider.received[0].payload["observations"][0]["name"] == "get_company_manual_context"


def test_next_action_depends_on_observation(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    def step2(req):
        obs = req.payload["observations"][-1]
        assert obs["status"] == "unavailable"
        assert obs["data"].get("unavailable_reason") == CALCULATION_UNAVAILABLE
        return _final(f"continued_after_{obs['status']}")

    provider = ScriptedLoopProvider(steps=[_tool("get_available_assessment"), step2])
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
        ).run(user_question="Оценка?")

    assert isinstance(out, LoopFinalOutcome)
    assert out.content == "continued_after_unavailable"


def test_bank_tool_valid_citation(loop_db):
    SessionLocal, tmp_path, monkeypatch, engine, url = loop_db
    loaded = _load_bank(tmp_path, engine)
    _configure_bank(
        monkeypatch, run_id=loaded["run_id"], storage_root=loaded["staging"].storage_root
    )

    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    def step_final(req):
        obs = req.payload["observations"][-1]
        assert obs["name"] == "get_bank_evidence"
        frags = obs["data"].get("fragments") or []
        assert frags, "bank fragments must reach observation"
        fid = frags[0]["fragment_id"]
        rev = frags[0]["revision"]
        # Use fragment text from DB for exact quote if needed
        return _final(
            "С учётом банковского фрагмента.",
            [{"fragment_id": fid, "revision": rev}],
        )

    provider = ScriptedLoopProvider(steps=[_tool("get_bank_evidence"), step_final])
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
        ).run(user_question="Банк?")

    assert isinstance(out, LoopFinalOutcome)
    assert len(out.citations) == 1
    assert out.citations[0].fragment_id


def test_excluded_fragment_not_citable(loop_db):
    """Fragment obtained/retrieved but not dispatched must fail citation validation."""
    SessionLocal, tmp_path, monkeypatch, engine, url = loop_db
    loaded = _load_bank(tmp_path, engine, slug="loop-excl")
    _configure_bank(
        monkeypatch, run_id=loaded["run_id"], storage_root=loaded["staging"].storage_root
    )
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    ghost_id = "never-dispatched-frag"

    def step_final(req):
        return _final("bad cite", [{"fragment_id": ghost_id, "revision": 1}])

    provider = ScriptedLoopProvider(steps=[_tool("get_bank_evidence"), step_final])
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
            budget=TurnBudget(
                config=TurnBudgetConfig(max_model_http=4, max_repairs=0, timeout_s=90)
            ),
        ).run(user_question="Cite ghost")

    assert isinstance(out, LoopStoppedOutcome)
    assert out.reason == LoopStopReason.invalid_action
    assert "citation" in out.detail


def test_unavailable_assessment_visible(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    seen = {}

    def step2(req):
        seen["status"] = req.payload["observations"][-1]["status"]
        seen["reason"] = req.payload["observations"][-1].get("reason_code")
        return _final("no zeros")

    provider = ScriptedLoopProvider(steps=[_tool("get_available_assessment"), step2])
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
        ).run(user_question="impact?")

    assert isinstance(out, LoopFinalOutcome)
    assert seen["status"] == "unavailable"
    assert seen["reason"] == CALCULATION_UNAVAILABLE


def test_scope_smuggle_and_unknown_write_tool(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)

    # Unknown / write tool name in scripted payload → parse or stop
    provider = ScriptedLoopProvider(
        steps=[
            {
                "kind": "tool_request",
                "action": {
                    "name": "compare_scenarios",
                    "arguments": {"company_id": "other"},
                },
            }
        ]
    )
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
            budget=TurnBudget(config=TurnBudgetConfig(max_repairs=0, timeout_s=90)),
        ).run(user_question="write?")

    assert isinstance(out, LoopStoppedOutcome)
    assert out.reason == LoopStopReason.invalid_action


def test_acl_foreign_company(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session)
        stranger_id = str(uuid.uuid4())
        session.add(
            User(
                id=stranger_id,
                email=f"str_{uuid.uuid4().hex[:8]}@example.com",
                password_hash=hash_password("Stranger1!"),
                display_name="Stranger",
                email_verified_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    provider = ScriptedLoopProvider(steps=[_final("should not run")])
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(
                user_id=stranger_id, company_id=company_id, event_id=event_id
            ),
            provider=provider,
        ).run(user_question="hack")

    assert isinstance(out, LoopStoppedOutcome)
    assert "FORBIDDEN" in out.detail or out.reason == LoopStopReason.invalid_action
    assert provider.received == []


def test_duplicate_tool_then_no_progress(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    provider = ScriptedLoopProvider(
        steps=[
            _tool("get_event_context"),
            _tool("get_event_context"),  # controlled duplicate notice
            _tool("get_event_context"),  # no_progress
        ]
    )
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
        ).run(user_question="dup")

    assert isinstance(out, LoopStoppedOutcome)
    assert out.reason == LoopStopReason.no_progress
    # Second observation should be denied duplicate
    assert any(
        o.get("reason_code") == "duplicate_tool_call"
        for r in provider.received
        for o in r.payload.get("observations") or []
    )


def test_deadline_fake_clock(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    clock = FakeClock(0.0)

    def after_first(req):
        clock.advance(100.0)
        return _tool("get_available_assessment")

    provider = ScriptedLoopProvider(steps=[_tool("get_event_context"), after_first])
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
            budget=TurnBudget(
                config=TurnBudgetConfig(timeout_s=10.0, max_model_http=4),
                clock=clock,
            ),
            clock=clock,
        ).run(user_question="time")

    assert isinstance(out, LoopStoppedOutcome)
    assert out.reason == LoopStopReason.timeout


def test_budget_four_three_tools_plus_final(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    provider = ScriptedLoopProvider(
        steps=[
            _tool("get_event_context"),
            _tool("get_available_assessment"),
            _tool("get_company_case_context"),
            _final("done after three tools"),
        ]
    )
    with SessionLocal() as session:
        budget = TurnBudget(config=TurnBudgetConfig(max_model_http=4, max_tool_calls=3))
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
            budget=budget,
        ).run(user_question="4 slots")

    assert isinstance(out, LoopFinalOutcome)
    assert budget.model_http_used == 4
    assert budget.tool_calls_used == 3
    assert provider.received[-1].lease.final_only is True


def test_tool_request_on_last_slot(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    provider = ScriptedLoopProvider(
        steps=[
            _tool("get_event_context"),
            _tool("get_available_assessment"),
            _tool("get_company_case_context"),
            _tool("get_bank_evidence"),  # 4th = final_only slot
        ]
    )
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
            budget=TurnBudget(config=TurnBudgetConfig(max_model_http=4, max_tool_calls=3)),
        ).run(user_question="last slot tool")

    assert isinstance(out, LoopStoppedOutcome)
    assert out.reason == LoopStopReason.invalid_action
    assert "last_model_slot" in out.detail


def test_shared_repair_budget(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=False)

    provider = ScriptedLoopProvider(
        steps=[
            "not-json-at-all",
            _final("repaired"),
            "still-bad",  # would need second repair — should stop if tried
        ]
    )
    with SessionLocal() as session:
        budget = TurnBudget(config=TurnBudgetConfig(max_model_http=4, max_repairs=1))
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
            budget=budget,
        ).run(user_question="repair")

    assert isinstance(out, LoopFinalOutcome)
    assert out.content == "repaired"
    assert budget.repairs_used == 1


def test_revision_conflict_keeps_first(loop_db):
    ledger = SourceLedger()
    r1 = SourceRef(type="bank_fragment", id="f1", revision=1)
    r2 = SourceRef(type="bank_fragment", id="f1", revision=2)
    ledger.record_obtained(r1)
    ledger.mark_prepared(
        r1,
        citation_payload={
            "fragment_id": "f1",
            "revision": 1,
            "text_kind": "exact_quote",
            "text_plain_for_validation": "v1",
        },
    )
    ledger.mark_dispatched(
        r1,
        citation_payload={
            "fragment_id": "f1",
            "revision": 1,
            "text_kind": "exact_quote",
            "text_plain_for_validation": "v1",
        },
    )
    _, conflict = ledger.mark_dispatched(
        r2,
        citation_payload={
            "fragment_id": "f1",
            "revision": 2,
            "text_kind": "exact_quote",
            "text_plain_for_validation": "v2",
        },
    )
    assert conflict is True
    idx = ledger.passed_index_for_citations()
    assert idx["f1"]["revision"] == 1
    assert idx["f1"]["text_plain_for_validation"] == "v1"


def test_no_new_impact_scenario_decision_company(loop_db):
    SessionLocal, *_ = loop_db
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_user_company_event(session, with_impact=True)
        before = _counts(session)

    provider = ScriptedLoopProvider(
        steps=[
            _tool("get_event_context"),
            _tool("get_available_assessment"),
            _final("stable"),
        ]
    )
    with SessionLocal() as session:
        AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
        ).run(user_question="no writes")
        after = _counts(session)

    assert after == before


def test_runtime_integrated_and_flag_gate():
    assert AGENT_LOOP_RUNTIME_INTEGRATED is True
    ensure_agent_loop_runtime_allowed(enabled=True)

    import inspect

    from app.services.assistant import orchestrator

    src = inspect.getsource(orchestrator.post_message)
    assert "post_message_agent_loop" in src
    # Scripted provider stays out of the HTTP/API path
    assert "ScriptedLoopProvider" not in src
