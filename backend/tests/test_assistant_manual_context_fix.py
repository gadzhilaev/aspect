"""Manual twin in agent loop — scripted/offline (not live LLM quality proof)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    Company,
    CompanyEdge,
    CompanyMembership,
    CompanyNode,
    Event,
    User,
)
from app.services.assistant.agent_loop.budget import TurnBudget, TurnBudgetConfig
from app.services.assistant.agent_loop.loop_projections import project_manual_for_model
from app.services.assistant.agent_loop.loop_tools import TurnToolCache, execute_loop_tool
from app.services.assistant.agent_loop.outcomes import LoopFinalOutcome, LoopStoppedOutcome
from app.services.assistant.agent_loop.provider_iface import ScriptedLoopProvider
from app.services.assistant.agent_loop.runner import AgentLoopRunner
from app.services.assistant.agent_loop.scope import ResolvedScope, ServerScope, resolve_server_scope
from app.services.assistant.context_builder import (
    CALCULATION_UNAVAILABLE,
    CALCULATION_UNAVAILABLE_EXPLANATION,
    calculation_unavailable_payload,
)
from app.services.assistant.manual_company_context import (
    build_manual_company_context_block,
    slim_manual_company_context_for_provider,
)

ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture
def db_sess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "manual_ctx.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "manual-ctx-test-secret")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "mock")
    monkeypatch.setenv("ASSISTANT_AGENT_LOOP", "false")
    monkeypatch.setenv("CASE_CONTEXT_SLOT_KEY", "")
    get_settings.cache_clear()
    command.upgrade(_alembic_config(), "head")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield SessionLocal
    finally:
        engine.dispose()
        get_settings.cache_clear()


def _seed_company(
    session: Session,
    *,
    with_twin: bool = True,
    partial_unknown: bool = False,
) -> tuple[str, str, str]:
    user_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    session.add(
        User(
            id=user_id,
            email=f"m_{uuid.uuid4().hex[:8]}@ex.com",
            password_hash=hash_password("ManualCtx1!"),
            display_name="Manual",
            email_verified_at=datetime.now(timezone.utc),
        )
    )
    session.flush()
    session.add(
        Company(
            id=company_id,
            name="упк-test",
            industry="electronics",
            size_band="small",
            hq_region="Махачкала",
            profile_status="ready",
            digital_twin_status="ready" if with_twin else "not_built",
            digital_twin_coverage=0.6 if with_twin else 0.0,
            is_demo=False,
            created_by=user_id,
        )
    )
    session.flush()
    session.add(
        CompanyMembership(id=str(uuid.uuid4()), user_id=user_id, company_id=company_id, role="owner")
    )
    session.add(
        Event(
            id=event_id,
            title="История и искусство: в ФТС России открылись тематические экспозиции",
            summary="Музейная экспозиция и художественная выставка.",
            category="macro",
            event_type="risk",
            severity=60.0,
            urgency_default="watch",
            status="active",
            is_demo=False,
            occurred_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
            match_countries_json=[],
            match_categories_json=[],
            match_currencies_json=[],
            match_materials_json=[],
            attributes_json={},
        )
    )
    if with_twin:
        supplier_id = str(uuid.uuid4())
        phone_id = str(uuid.uuid4())
        session.add(
            CompanyNode(
                id=supplier_id,
                company_id=company_id,
                node_type="supplier",
                name="Поставщик (Китай)",
                country="Китай",
                status="active",
                attributes_json={"countries": ["Китай"]},
            )
        )
        session.add(
            CompanyNode(
                id=phone_id,
                company_id=company_id,
                node_type="component",
                name="Телефон",
                status="active",
                attributes_json={},
            )
        )
        session.flush()
        session.add(
            CompanyEdge(
                id=str(uuid.uuid4()),
                company_id=company_id,
                from_node_id=supplier_id,
                to_node_id=phone_id,
                relation_type="supplies",
                confidence=0.9,
                source_type="user",
                attributes_json={},
            )
        )
        if partial_unknown:
            session.add(
                CompanyNode(
                    id=str(uuid.uuid4()),
                    company_id=company_id,
                    node_type="supplier",
                    name="",
                    status="unknown",
                    attributes_json={},
                )
            )
    session.commit()
    return user_id, company_id, event_id


def _final(content: str) -> dict:
    return {"kind": "final", "content": content, "bank_evidence_citations": []}


def _tool(name: str) -> dict:
    return {
        "kind": "tool_request",
        "action": {"name": name, "arguments": {}},
    }


def test_manual_without_case_link_or_impact(db_sess):
    SessionLocal = db_sess
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_company(session, with_twin=True)
        resolved = resolve_server_scope(
            session,
            ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
        )
        block = build_manual_company_context_block(
            session, company=resolved.company, user=resolved.user
        )
        assert block["availability"] == "available"
        assert block["independent_of_case_link"] is True
        assert block["independent_of_event_impact"] is True
        names = {n["name"] for n in block["known_nodes"]}
        assert "Телефон" in names
        assert "Поставщик (Китай)" in names
        assert any(
            e["from"]["name"].startswith("Поставщик") and e["to"]["name"] == "Телефон"
            for e in block["known_edges"]
        )
        # No case link table rows required
        slim = slim_manual_company_context_for_provider(block)
        proj = project_manual_for_model(slim)
        assert "id" not in proj.get("company", {})
        assert "id_internal" not in proj.get("company", {})
        exec_r = execute_loop_tool(
            session,
            resolved=resolved,
            name="get_company_manual_context",
            step=1,
            max_result_chars=4000,
            cache=TurnToolCache(),
        )
        assert exec_r.envelope.status == "ok"
        data = exec_r.envelope.data
        assert data["source"] == "manual_twin"
        assert any(n.get("name") == "Телефон" for n in data["known_nodes"])


def test_partial_unknown_not_confirmed_chain(db_sess):
    SessionLocal = db_sess
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_company(
            session, with_twin=True, partial_unknown=True
        )
        company = session.get(Company, company_id)
        user = session.get(User, user_id)
        block = build_manual_company_context_block(session, company=company, user=user)
        assert block["availability"] in {"available", "partial"}
        # Unknown empty-name node must not appear as known
        assert all(n.get("name") for n in block["known_nodes"])
        assert any("status=unknown" in u for u in block["unknown_fields"])
        # Incomplete edges are not inventing a chain for unknown endpoints
        for e in block["known_edges"]:
            assert e["from"]["name"] and e["to"]["name"]


def test_relevance_question_sees_seeded_manual_data(db_sess):
    SessionLocal = db_sess
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_company(session, with_twin=True)

    def assert_seed_then_final(req):
        obs = req.payload["observations"]
        assert obs, "manual twin must be seeded before first model call"
        assert obs[0]["name"] == "get_company_manual_context"
        nodes = (obs[0].get("data") or {}).get("known_nodes") or []
        assert any(n.get("name") == "Телефон" for n in nodes)
        assert any("Китай" in (n.get("name") or "") or n.get("country") == "Китай" for n in nodes)
        return _final(
            "Факты публикации: выставка ФТС. "
            "Известные данные компании: поставщик Китай → компонент Телефон. "
            "Вывод: прямой связи с выставкой нет. "
            "Отсутствие расчёта — состояние приложения, не ограничение регулятора."
        )

    provider = ScriptedLoopProvider(steps=[assert_seed_then_final])
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
            budget=TurnBudget(config=TurnBudgetConfig(max_model_http=2, max_tool_calls=3)),
        ).run(user_question="Касается ли новость моей компании?")

    assert isinstance(out, LoopFinalOutcome)
    assert "Китай" in out.content or "Телефон" in out.content
    assert "регулятора" in out.content


def test_exhibition_vs_investigation_calc_unavailable_wording():
    """Fixtures/rules: calc unavailable ≠ regulator restrictions (no live LLM)."""
    payload = calculation_unavailable_payload(tool_name="get_available_assessment")
    assert payload["assessment_state"] == CALCULATION_UNAVAILABLE
    blob = (payload["message"] + " " + CALCULATION_UNAVAILABLE_EXPLANATION).lower()
    assert "регулятор" in blob or "приложения" in blob
    assert "уже введённые ограничения" not in blob or "не" in blob
    # Explicit negation in explanation
    assert "не мера регулятора" in CALCULATION_UNAVAILABLE_EXPLANATION
    assert "не «уже введённые ограничения»" in CALCULATION_UNAVAILABLE_EXPLANATION


def test_empty_twin_does_not_claim_user_profile_void(db_sess):
    SessionLocal = db_sess
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_company(session, with_twin=False)
        resolved = resolve_server_scope(
            session,
            ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
        )
        block = build_manual_company_context_block(
            session, company=resolved.company, user=resolved.user
        )
        assert block["availability"] == "unavailable"
        assert "не означает, что компания" in block["explanation"].lower() or "не утверждайте" in block["explanation"].lower()


def test_acl_other_company_denied(db_sess):
    SessionLocal = db_sess
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_company(session, with_twin=True)
        other_co = str(uuid.uuid4())
        session.add(
            Company(
                id=other_co,
                name="Other",
                profile_status="ready",
                digital_twin_status="ready",
                is_demo=False,
                created_by=user_id,
            )
        )
        session.commit()

    provider = ScriptedLoopProvider(steps=[_final("should not run")])
    with SessionLocal() as session:
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=other_co, event_id=event_id),
            provider=provider,
            budget=TurnBudget(config=TurnBudgetConfig(max_model_http=1, max_tool_calls=0)),
        ).run(user_question="acl")
    assert isinstance(out, LoopStoppedOutcome)
    assert out.reason.value == "invalid_action"
    assert "acl" in (out.detail or "")


def test_loop_budget_limits_unchanged_with_seed(db_sess):
    """Seed must not spend tool budget; max_tool_calls still enforced."""
    SessionLocal = db_sess
    with SessionLocal() as session:
        user_id, company_id, event_id = _seed_company(session, with_twin=True)

    provider = ScriptedLoopProvider(
        steps=[
            _tool("get_event_context"),
            _tool("get_available_assessment"),
            _final("ok"),
        ]
    )
    with SessionLocal() as session:
        budget = TurnBudget(config=TurnBudgetConfig(max_model_http=4, max_tool_calls=2))
        out = AgentLoopRunner(
            db=session,
            scope=ServerScope(user_id=user_id, company_id=company_id, event_id=event_id),
            provider=provider,
            budget=budget,
        ).run(user_question="budget")
    assert isinstance(out, LoopFinalOutcome)
    assert budget.tool_calls_used == 2
    # Seed present but not counted
    assert provider.received[0].payload["observations"][0].get("server_seeded") is True
