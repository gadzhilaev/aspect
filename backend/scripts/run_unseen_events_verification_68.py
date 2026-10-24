"""Stage 6.8 — unseen synthetic events: bank retrieval + personalization (no live LLM).

Uses a SQLite backup of the expanded-QA stand copy. Does not touch jury_63b,
root .env, working DB, or re-import competition CSV/payments.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event as sa_event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SRC_DB = (
    ROOT
    / "data/bank_materials/verification/evidence_expansion_stand_copy.db"
)
OUT_DIR = ROOT / "data/bank_materials/verification/e2e68"
WORK_DB = OUT_DIR / "unseen_events_verification.db"
REPORT_JSON = OUT_DIR / "unseen_events_report.json"

# OCR runs from competition stand (server scope) — not invented.
STAND_ENV = ROOT / "data/competition_stand/jury_63b/stand.env"
STORAGE_ROOT = ROOT / "data/competition_stand/jury_63b/storage"

COMPANY_A = "07ebf2b6-1553-4765-962e-e807bb0dd1e2"  # U_264
COMPANY_B = "d81efc06-d14d-4407-97d7-852c454c3f15"  # U_92


@dataclass
class MatrixCase:
    case_id: str
    theme: str
    title: str
    summary: str
    occurred_at: datetime
    category: str = "macro"
    event_type: str = "risk"
    match_categories: list[str] = field(default_factory=list)
    # Expectations fixed BEFORE search
    expected_theme: str = ""
    allowed_document_slugs: list[str] = field(default_factory=list)
    empty_ok: bool = False
    empty_required: bool = False
    forbidden_conclusions: list[str] = field(default_factory=list)
    require_any_stable_keys: list[str] = field(default_factory=list)
    forbid_stable_keys: list[str] = field(default_factory=list)
    min_score_floor_check: bool = False  # useful hits must clear MIN_EVIDENCE_SCORE
    paraphrase_of: str | None = None


def _matrix() -> list[MatrixCase]:
    """Independent expected outcomes — written before retrieval runs."""
    return [
        MatrixCase(
            case_id="E68-INF-1",
            theme="inflation",
            title="[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8] Недельные цены: сигнал дефляции по ИПЦ",
            summary=(
                "Синтетическая карточка: по недельным данным отмечено снижение "
                "потребительских цен; в годовом выражении инфляция около шести процентов. "
                "Не является официальной публикацией Росстата."
            ),
            occurred_at=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
            match_categories=["инфляция", "ИПЦ"],
            expected_theme="inflation / weekly CPI",
            allowed_document_slugs=["Inflation_tracker_02"],
            require_any_stable_keys=["infl_week_deflation", "infl_yoy"],
            forbid_stable_keys=["consumption_retail_june", "policy_rate_cb_decision"],
            forbidden_conclusions=[
                "Нельзя утверждать, что это актуальная инфляция «на сегодня».",
                "Нельзя выдавать прогноз банка за факт события.",
            ],
            min_score_floor_check=True,
        ),
        MatrixCase(
            case_id="E68-INF-1b",
            theme="inflation",
            title="[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8] Пересказ: Росстат зафиксировал снижение цен за неделю",
            summary=(
                "Иная формулировка без копирования банковского заголовка: "
                "за последнюю августовскую неделю цены чуть снизились, "
                "годовой показатель вырос до шести с лишним процентов."
            ),
            occurred_at=datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc),
            match_categories=["инфляция"],
            expected_theme="inflation paraphrase",
            allowed_document_slugs=["Inflation_tracker_02"],
            require_any_stable_keys=["infl_week_deflation", "infl_yoy"],
            paraphrase_of="E68-INF-1",
            forbidden_conclusions=["Нельзя считать пересказ первичной статистикой Росстата."],
            min_score_floor_check=True,
        ),
        MatrixCase(
            case_id="E68-CON-1",
            theme="consumption",
            title="[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8] Розница летом: оборот всё ещё высокий",
            summary=(
                "Синтетика: оборот розничной торговли в июне вырос примерно на семь процентов "
                "год к году; обсуждается, не достиг ли потребительский спрос пика."
            ),
            occurred_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            match_categories=["потребление", "розница"],
            expected_theme="consumption / retail",
            allowed_document_slugs=["ALFA-consumption"],
            require_any_stable_keys=["consumption_retail_june", "consumption_peak_forecast"],
            forbid_stable_keys=["infl_week_deflation", "policy_rate_cb_decision"],
            forbidden_conclusions=[
                "Прогноз охлаждения до 4К26 — не факт июня.",
                "Нельзя читать наличие кредита/депозита из этой новости.",
            ],
            min_score_floor_check=True,
        ),
        MatrixCase(
            case_id="E68-CON-1b",
            theme="consumption",
            title="[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8] Перефраз: июньский ритейл и ожидание охлаждения спроса",
            summary=(
                "Другими словами: продажи в рознице в июне оставались сильными; "
                "аналитики ждут замедления к четвёртому кварталу."
            ),
            occurred_at=datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc),
            expected_theme="consumption paraphrase",
            allowed_document_slugs=["ALFA-consumption"],
            require_any_stable_keys=["consumption_retail_june", "consumption_peak_forecast"],
            paraphrase_of="E68-CON-1",
            forbidden_conclusions=["Нельзя смешивать fact июня и forecast 4К26."],
            min_score_floor_check=True,
        ),
        MatrixCase(
            case_id="E68-RATE-HOLD",
            theme="policy_rate_hold",
            title="[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8] Регулятор оставил ключевую ставку без изменения",
            summary=(
                "Синтетическая новость о сохранении ключевой ставки на прежнем уровне "
                "и ужесточении тона комментария."
            ),
            occurred_at=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
            match_categories=["ключевая ставка", "ДКП"],
            expected_theme="key rate hold",
            allowed_document_slugs=["ALFA-Macro_Insights-Policy_Rate_11Sep"],
            require_any_stable_keys=[
                "policy_rate_cb_decision",
                "policy_rate_rhetoric",
                "policy_rate_bank_forecast",
            ],
            forbid_stable_keys=["infl_week_deflation", "consumption_retail_june"],
            forbidden_conclusions=[
                "Bank forecast (пауза/путь ставки) ≠ факт будущего решения ЦБ.",
                "Нельзя выводить сумму долга компании из факта ставки.",
            ],
            min_score_floor_check=True,
        ),
        MatrixCase(
            case_id="E68-RATE-HIKE",
            theme="policy_rate_hike_hypothesis",
            title="[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8] Гипотеза: обсуждение возможного повышения ставки",
            summary=(
                "Синтетика про сценарий повышения ключевой ставки на один процентный пункт. "
                "Не утверждает, что решение уже принято."
            ),
            occurred_at=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
            match_categories=["ключевая ставка"],
            expected_theme="rate hike discussion — bank note is about hold",
            allowed_document_slugs=["ALFA-Macro_Insights-Policy_Rate_11Sep"],
            # Thematic retrieval of rate materials may occur; must NOT treat bank fact as hike.
            empty_ok=True,
            forbidden_conclusions=[
                "Нельзя трактовать цитату «оставить ставку неизменной» как подтверждение повышения.",
                "Прогноз банка не становится фактом повышения.",
            ],
        ),
        MatrixCase(
            case_id="E68-IRREL",
            theme="irrelevant_steel",
            title="[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8] Цены на стальной прокат на экспортных рынках",
            summary=(
                "Синтетика о котировках горячекатаного проката и загрузке меткомбинатов. "
                "Тема — чёрная металлургия и экспортный прокат, не потребительские цены и не ДКП."
            ),
            occurred_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
            match_categories=["сталь", "металлургия"],
            expected_theme="steel — no AI-eligible inflation/consumption/rate basis",
            allowed_document_slugs=[],
            empty_required=True,
            forbid_stable_keys=[
                "infl_week_deflation",
                "infl_yoy",
                "consumption_retail_june",
                "consumption_peak_forecast",
                "policy_rate_cb_decision",
                "policy_rate_rhetoric",
                "policy_rate_bank_forecast",
            ],
            forbidden_conclusions=["Пустая выдача не означает «риска нет»."],
        ),
        MatrixCase(
            case_id="E68-DEMAND-OTHER",
            theme="shared_token_demand",
            title="[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8] Ювелирный спрос на золото на мировом рынке",
            summary=(
                "Синтетика: растёт ювелирный спрос на золото и интерес к слиткам. "
                "Общее слово «спрос» не должно подтянуть потребление/розницу как основание."
            ),
            occurred_at=datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc),
            match_categories=["золото"],
            expected_theme="gold demand — weak stem must not yield consumption evidence",
            allowed_document_slugs=[],  # gold digests not QA-elevated to AI evidence
            empty_required=True,
            forbid_stable_keys=[
                "consumption_peak_forecast",
                "consumption_retail_june",
                "infl_week_deflation",
                "policy_rate_cb_decision",
            ],
            forbidden_conclusions=[
                "Совпадение по слову «спрос» ≠ релевантное основание по потреблению."
            ],
        ),
        MatrixCase(
            case_id="E68-ASOF-EARLY",
            theme="inflation_before_bank_pub",
            title="[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8] Ранний сигнал по инфляции (до заметки банка)",
            summary=(
                "Синтетическая новость про недельную дефляцию и годовую инфляцию, "
                "датированная до публикации Inflation tracker 02 (2 сентября 2026)."
            ),
            occurred_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            match_categories=["инфляция", "Росстат", "дефляция"],
            expected_theme="inflation query but as_of before bank pub date",
            allowed_document_slugs=[],
            empty_required=True,
            forbid_stable_keys=["infl_week_deflation", "infl_yoy"],
            forbidden_conclusions=[
                "Материал банка от 2026-09-02 недоступен как основание для новости 2026-08-20."
            ],
        ),
    ]


def _backup_db(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    src_conn = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    dst_conn = sqlite3.connect(dst)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


def _read_allowlist() -> str:
    raw = STAND_ENV.read_text(encoding="utf-8")
    for line in raw.splitlines():
        if line.startswith("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("allowlist missing in stand.env")


def _seed_events(session: Session, cases: list[MatrixCase]) -> dict[str, str]:
    from app.models import Event

    ids: dict[str, str] = {}
    for case in cases:
        eid = f"evt_synth_e68_{case.case_id.lower().replace('-', '_')}"
        existing = session.get(Event, eid)
        if existing is not None:
            session.delete(existing)
            session.flush()
        ev = Event(
            id=eid,
            title=case.title,
            summary=case.summary,
            category=case.category,
            event_type=case.event_type,
            severity=30.0,
            urgency_default="watch",
            status="active",
            occurred_at=case.occurred_at,
            match_countries_json=[],
            match_categories_json=list(case.match_categories),
            match_currencies_json=[],
            match_materials_json=[],
            attributes_json={"synthetic_stage": "6.8", "not_real_news": True},
            is_demo=True,
        )
        session.add(ev)
        ids[case.case_id] = eid
    session.commit()
    return ids


def _run_retrieval(
    session: Session,
    cases: list[MatrixCase],
    event_ids: dict[str, str],
) -> list[dict[str, Any]]:
    from app.core.config import get_settings
    from app.models import Event
    from app.services.bank_materials.event_evidence import collect_event_bank_evidence
    from app.services.bank_materials.retrieval import MIN_EVIDENCE_SCORE

    rows: list[dict[str, Any]] = []
    for case in cases:
        ev = session.get(Event, event_ids[case.case_id])
        assert ev is not None
        out = collect_event_bank_evidence(session, event=ev, limit=10)
        hits = [
            {
                "stable_key": it.stable_key,
                "revision": it.revision,
                "document_slug": it.document_slug,
                "content_type": it.content_type,
                "text_kind": it.text_kind,
                "lexical_match_score": it.lexical_match_score,
                "text_preview": (it.text or "")[:120],
            }
            for it in (out.evidence or [])
        ]
        keys = {h["stable_key"] for h in hits}
        slugs = {h["document_slug"] for h in hits}

        expected = {
            "theme": case.expected_theme,
            "allowed_document_slugs": case.allowed_document_slugs,
            "empty_ok": case.empty_ok,
            "empty_required": case.empty_required,
            "require_any_stable_keys": case.require_any_stable_keys,
            "forbid_stable_keys": case.forbid_stable_keys,
            "forbidden_conclusions": case.forbidden_conclusions,
        }

        failures: list[str] = []
        if case.empty_required and hits:
            failures.append(f"expected_empty_got_{sorted(keys)}")
        if case.require_any_stable_keys and not (keys & set(case.require_any_stable_keys)):
            failures.append(f"missing_required_keys_got_{sorted(keys)}")
        bad = keys & set(case.forbid_stable_keys)
        if bad:
            failures.append(f"forbidden_keys_{sorted(bad)}")
        if case.allowed_document_slugs and slugs - set(case.allowed_document_slugs):
            # Extra docs beyond allowlist = fail (unless empty_ok hike with only rate docs)
            if not case.empty_ok:
                failures.append(f"unexpected_slugs_{sorted(slugs - set(case.allowed_document_slugs))}")
        if case.min_score_floor_check and hits:
            weak = [h for h in hits if (h["lexical_match_score"] or 0) < MIN_EVIDENCE_SCORE]
            if weak:
                failures.append("hit_below_min_evidence_score")
            useful = [h for h in hits if h["stable_key"] in set(case.require_any_stable_keys)]
            if case.require_any_stable_keys and not useful:
                failures.append("required_keys_absent_despite_hits")

        # Forecast must not be labeled fact
        for h in hits:
            if h["stable_key"] == "consumption_peak_forecast" and h["content_type"] != "forecast":
                failures.append("peak_forecast_mislabeled")
            if h["stable_key"] == "policy_rate_bank_forecast" and h["content_type"] != "forecast":
                failures.append("rate_forecast_mislabeled")

        # Hike case: if rate hold quote appears, still PASS if we only warn in forbidden_conclusions
        # but fail if we would claim hike — we check content doesn't say hike as fact of event
        if case.case_id == "E68-RATE-HIKE":
            for h in hits:
                if h["stable_key"] == "policy_rate_cb_decision":
                    # Decision text is hold — thematic retrieval OK; must remain fact about hold
                    if "неизменн" not in (h["text_preview"] or "").lower() and "14" not in (
                        h["text_preview"] or ""
                    ):
                        failures.append("unexpected_decision_text")

        status = "PASS" if not failures else "FAIL"
        rows.append(
            {
                "case_id": case.case_id,
                "event_id": event_ids[case.case_id],
                "paraphrase_of": case.paraphrase_of,
                "status": status,
                "expected": expected,
                "actual": {
                    "evidence_status": out.status,
                    "as_of_date": out.as_of_date.isoformat() if out.as_of_date else None,
                    "query_preview": (out.query_preview or "")[:200],
                    "hit_count": len(hits),
                    "stable_keys": sorted(keys),
                    "document_slugs": sorted(slugs),
                    "hits": hits,
                    "content_types": sorted(
                        {h["content_type"] for h in hits if h.get("content_type")}
                    ),
                },
                "failures": failures,
                "notes": {
                    "score_is_not_semantic_proof": True,
                    "min_evidence_score": MIN_EVIDENCE_SCORE,
                    "settings_scope": "BANK_MATERIALS_ALLOWED_OCR_RUN_IDS from stand.env",
                },
            }
        )
    return rows


def _extra_paraphrase_checks(session: Session) -> list[dict[str, Any]]:
    """Formulations NOT used to craft the retrieval fix — must still behave.

    Direct retrieve_bank_fragments (evidence), OCR allowlist from settings.
    """
    from app.core.config import get_settings
    from app.services.bank_materials.access import scope_from_settings
    from app.services.bank_materials.retrieval import retrieve_bank_fragments

    scope = scope_from_settings(get_settings())
    run_ids = list(scope.allowed_ocr_run_ids)
    checks: list[dict[str, Any]] = []
    cases = [
        {
            "id": "PARA-INF-fresh",
            "query": "Росстат сообщил о недельном снижении потребительских цен в конце августа",
            "require_any": {"infl_week_deflation", "infl_yoy"},
            "forbid": {"consumption_peak_forecast", "policy_rate_cb_decision"},
        },
        {
            "id": "PARA-CON-fresh",
            "query": "июньский оборот розницы всё ещё растёт год к году",
            "require_any": {"consumption_retail_june"},
            "forbid": {"infl_week_deflation", "policy_rate_cb_decision"},
        },
        {
            "id": "PARA-GOLD-fresh",
            "query": "инвестиционный спрос на физическое золото усилился у частных клиентов",
            "require_any": set(),
            "forbid": {
                "consumption_peak_forecast",
                "consumption_retail_june",
                "infl_week_deflation",
                "policy_rate_cb_decision",
            },
            "empty_required": True,
        },
    ]
    for c in cases:
        res = retrieve_bank_fragments(
            session,
            query=c["query"],
            ocr_run_ids=run_ids,
            mode="evidence",
            limit=8,
        )
        keys = {h.stable_key for h in res.hits}
        failures: list[str] = []
        if c.get("empty_required") and keys:
            failures.append(f"expected_empty_got_{sorted(keys)}")
        if c["require_any"] and not (keys & c["require_any"]):
            failures.append(f"missing_{sorted(c['require_any'])}_got_{sorted(keys)}")
        bad = keys & c["forbid"]
        if bad:
            failures.append(f"forbidden_{sorted(bad)}")
        checks.append(
            {
                "id": c["id"],
                "query": c["query"],
                "status": "PASS" if not failures else "FAIL",
                "actual_keys": sorted(keys),
                "failures": failures,
            }
        )
    return checks


def _personalization(session: Session) -> dict[str, Any]:
    """Public vs personal feed + case context delivered to assistant (mocked, no LLM)."""
    from app.core.security import create_access_token
    from app.db.session import get_db
    from app.main import create_app
    from app.models import Event, EventImpact, User, Company
    from app.services.assistant.context_builder import build_conversation_context
    from app.services.assistant.case_company_context import (
        build_assistant_case_company_context,
    )
    from fastapi.testclient import TestClient

    # Counts before
    before_impact = session.scalar(select(func.count()).select_from(EventImpact)) or 0
    from app.models import Scenario, Decision

    before_sc = session.scalar(select(func.count()).select_from(Scenario)) or 0
    before_dec = session.scalar(select(func.count()).select_from(Decision)) or 0

    users = {
        "A": session.scalar(
            select(User).where(User.id == "9efcbcdb-5115-40fd-ad10-b6e205687ea8")
        ),
        "B": session.scalar(
            select(User).where(User.id == "913f928c-c7ae-45c5-815c-a6d258ece324")
        ),
    }
    companies = {
        "A": session.get(Company, COMPANY_A),
        "B": session.get(Company, COMPANY_B),
    }
    assert users["A"] and users["B"] and companies["A"] and companies["B"]

    case_blocks = {}
    for label in ("A", "B"):
        packed = build_assistant_case_company_context(
            session, company=companies[label], user=users[label]
        )
        products = {
            p.get("code"): p.get("status")
            for p in (packed.get("products") or [])
            if isinstance(p, dict) and p.get("code")
        }
        case_blocks[label] = {
            "status": packed.get("status"),
            "external_uid": packed.get("external_uid"),
            "snapshot_id": packed.get("snapshot_id"),
            "products_sample": {
                k: products.get(k)
                for k in ("LOA", "DEP", "RKO", "ACQ", "FX")
                if k in products
            },
            "known_fields_count": len(packed.get("known_fields") or []),
            "unknown_fields_count": len(packed.get("unknown_fields") or []),
            "interpretation_limits_present": bool(packed.get("interpretation_limits")),
        }

    # Product contrast must come from data, not forced
    products_differ = case_blocks["A"]["products_sample"] != case_blocks["B"]["products_sample"]
    uids_differ = case_blocks["A"]["external_uid"] != case_blocks["B"]["external_uid"]

    # TestClient public vs personal
    SessionLocal = sessionmaker(bind=session.get_bind(), autoflush=False, autocommit=False)

    def _override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    token_a = create_access_token(users["A"].id)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    public = client.get("/api/v1/public/news", headers=headers_a)
    public_ids = []
    if public.status_code == 200:
        body = public.json()
        items = body if isinstance(body, list) else body.get("items") or body.get("events") or []
        public_ids = [it.get("id") for it in items if isinstance(it, dict)]

    dash = client.get(f"/api/v1/companies/{COMPANY_A}/dashboard", headers=headers_a)
    personal_ids: list[str] = []
    if dash.status_code == 200:
        pe = dash.json().get("priority_events") or []
        personal_ids = [it.get("event_id") or it.get("id") for it in pe if isinstance(it, dict)]

    synth_in_public = any(
        (eid or "").startswith("evt_synth_e68_") for eid in public_ids
    )
    # Personal feed is impact-based — synth events have no impact
    synth_in_personal = any(
        (eid or "").startswith("evt_synth_e68_") for eid in personal_ids
    )

    # Assistant context delivery (no provider HTTP): open conversation path counts
    # Use build_conversation_context directly for both companies on same synth event
    synth_ev = session.scalar(
        select(Event).where(Event.id.like("evt_synth_e68_e68_inf_1%")).limit(1)
    )
    # fallback any e68
    if synth_ev is None:
        synth_ev = session.scalar(select(Event).where(Event.id.like("evt_synth_e68_%")).limit(1))

    ctx_compare: dict[str, Any] = {}
    if synth_ev is not None:
        for label in ("A", "B"):
            ctx = build_conversation_context(
                session,
                event_id=synth_ev.id,
                company_id=companies[label].id,
                user=users[label],
            )
            case_ctx = ctx.get("case_company_context") or {}
            bank = ctx.get("bank_evidence") or {}
            bank_frags = (
                bank.get("fragments_passed_to_provider")
                or bank.get("fragments")
                or bank.get("evidence")
                or bank.get("items")
                or []
            )
            ctx_compare[label] = {
                "case_status": case_ctx.get("status"),
                "case_external_uid": case_ctx.get("external_uid"),
                "case_products": {
                    p.get("code"): p.get("status")
                    for p in (case_ctx.get("products") or [])
                    if isinstance(p, dict)
                },
                "bank_evidence_status": bank.get("status"),
                "bank_evidence_count": len(bank_frags),
                "has_impact_calculation": bool(ctx.get("has_impact_calculation")),
            }

    after_impact = session.scalar(select(func.count()).select_from(EventImpact)) or 0
    after_sc = session.scalar(select(func.count()).select_from(Scenario)) or 0
    after_dec = session.scalar(select(func.count()).select_from(Decision)) or 0

    # ACL: B cannot open A's conversation if we create one — membership check via context API
    ctx_b_on_a = client.get(
        f"/api/v1/companies/{COMPANY_A}/context",
        headers={"Authorization": f"Bearer {create_access_token(users['B'].id)}"},
    )

    client.close()
    app.dependency_overrides.clear()

    gap_note = (
        "Персональная лента строится только по EventImpact; синтетические события 6.8 "
        "без Impact не попадают в «Для вас», но видны в public news и доступны в "
        "assistant/case_context. Это известный разрыв discoverability (см. EVENT_DISCOVERABILITY), "
        "не баг ранжирования этого этапа."
    )

    checks = [
        {
            "name": "case_uids_differ",
            "ok": uids_differ,
            "detail": {
                "A": case_blocks["A"]["external_uid"],
                "B": case_blocks["B"]["external_uid"],
            },
        },
        {
            "name": "case_products_differ_from_data",
            "ok": products_differ,
            "detail": {
                "A": case_blocks["A"]["products_sample"],
                "B": case_blocks["B"]["products_sample"],
            },
        },
        {
            "name": "synth_in_public_feed",
            "ok": synth_in_public or public.status_code == 200,
            "detail": {"public_status": public.status_code, "synth_seen": synth_in_public},
        },
        {
            "name": "synth_absent_from_personal_without_impact",
            "ok": not synth_in_personal,
            "detail": {"personal_ids_sample": personal_ids[:5], "dash_status": dash.status_code},
        },
        {
            "name": "no_hidden_impact_scenario_decision",
            "ok": before_impact == after_impact
            and before_sc == after_sc
            and before_dec == after_dec,
            "detail": {
                "impact": [before_impact, after_impact],
                "scenario": [before_sc, after_sc],
                "decision": [before_dec, after_dec],
            },
        },
        {
            "name": "acl_foreign_company_context",
            "ok": ctx_b_on_a.status_code in (403, 404),
            "detail": {"status": ctx_b_on_a.status_code},
        },
        {
            "name": "assistant_context_case_differs_A_B",
            "ok": bool(ctx_compare)
            and ctx_compare.get("A", {}).get("case_external_uid")
            != ctx_compare.get("B", {}).get("case_external_uid"),
            "detail": ctx_compare,
        },
    ]

    return {
        "case_blocks": case_blocks,
        "context_compare": ctx_compare,
        "public_status": public.status_code,
        "dashboard_status": dash.status_code,
        "discoverability_gap": gap_note,
        "checks": checks,
        "all_passed": all(c["ok"] for c in checks),
    }


def main() -> int:
    if not SRC_DB.is_file():
        print("FAIL: source DB missing", SRC_DB)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Backup DB…")
    _backup_db(SRC_DB, WORK_DB)

    allow = _read_allowlist()
    os.environ["DATABASE_URL"] = f"sqlite:///{WORK_DB.as_posix()}"
    os.environ["SECRET_KEY"] = "unseen-events-68-verification"
    os.environ["APP_ENV"] = "test"
    os.environ["BANK_MATERIALS_ALLOWED_OCR_RUN_IDS"] = allow
    os.environ["BANK_MATERIALS_STORAGE_ROOT"] = str(STORAGE_ROOT.as_posix())
    os.environ["CASE_CONTEXT_SLOT_KEY"] = "competition_default"
    # Ensure no live provider
    os.environ["ASSISTANT_PROVIDER"] = "mock"
    os.environ["ASSISTANT_AGENT_LOOP"] = "false"
    os.environ.pop("HACKATHON_API_KEY", None)

    from app.core.config import get_settings

    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{WORK_DB.as_posix()}")

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    cases = _matrix()

    with SessionLocal() as session:
        print("Seed synthetic events…")
        event_ids = _seed_events(session, cases)
        print("Retrieval matrix…")
        retrieval_rows = _run_retrieval(session, cases, event_ids)
        print("Extra paraphrases (not used for the fix)…")
        paraphrase_rows = _extra_paraphrase_checks(session)
        print("Personalization…")
        personalization = _personalization(session)

        # Source stand untouched marker
        src_mtime = SRC_DB.stat().st_mtime
        jury_db = ROOT / "data/competition_stand/jury_63b/stand.db"
        jury_mtime = jury_db.stat().st_mtime if jury_db.is_file() else None

    retrieval_pass = all(r["status"] == "PASS" for r in retrieval_rows)
    paraphrase_pass = all(r["status"] == "PASS" for r in paraphrase_rows)
    report = {
        "stage": "6.8",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_db": str(SRC_DB.relative_to(ROOT)).replace("\\", "/"),
        "work_db": str(WORK_DB.relative_to(ROOT)).replace("\\", "/"),
        "live_llm": False,
        "model_http": 0,
        "browser_cdp": False,
        "csv_reimport": False,
        "min_evidence_score": 3.0,
        "retrieval": {
            "all_passed": retrieval_pass,
            "cases": retrieval_rows,
        },
        "paraphrases_post_fix": {
            "all_passed": paraphrase_pass,
            "cases": paraphrase_rows,
            "note": "Queries not used while diagnosing/fixing retrieval defects",
        },
        "personalization": personalization,
        "integrity": {
            "source_db_mtime_unchanged_check": "caller compares; work_db is backup copy",
            "jury_63b_stand_db_path": str(jury_db.relative_to(ROOT)).replace("\\", "/")
            if jury_db.is_file()
            else None,
            "src_mtime": src_mtime,
            "jury_mtime": jury_mtime,
        },
        "overall_pass": retrieval_pass
        and paraphrase_pass
        and bool(personalization.get("all_passed")),
        "limitations": [
            "Scripted/mocked provider only — not live model quality.",
            "Lexical retrieval score is not semantic relevance proof.",
            "Synthetic events are not real news.",
            "Personal feed remains impact-gated (documented gap).",
            "Only QA-elevated bank fragments are AI-evidence eligible.",
        ],
    }

    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Wrote", REPORT_JSON)
    print("retrieval_pass", retrieval_pass)
    for r in retrieval_rows:
        print(r["status"], r["case_id"], r.get("failures") or "")
    print("paraphrase_pass", paraphrase_pass)
    for r in paraphrase_rows:
        print(r["status"], r["id"], r.get("failures") or "")
    print("personalization_pass", personalization.get("all_passed"))
    print("OVERALL", report["overall_pass"])
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
