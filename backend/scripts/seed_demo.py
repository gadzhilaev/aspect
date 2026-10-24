"""Idempotent seed: СеверПром demo company, graph, events, solutions.

Usage:
  python -m scripts.seed_demo
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Allow running as script from repo root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
import app.models  # noqa: F401
from app.models import (
    Company,
    CompanyEdge,
    CompanyMembership,
    CompanyNode,
    CompanyProfileSettings,
    Event,
    EventSource,
    SolutionCandidate,
    User,
)
from app.services.impact import recompute_company_impact


DEMO_USER_EMAIL = "demo@kontur.app"
DEMO_PASSWORD = "DemoKontur1!"
COMPANY_ID = "cmp_severprom"
EVENT_EXPORT = "evt_china_export_001"
EVENT_RATE = "evt_rate_hike_001"
EVENT_OPP = "evt_market_opp_001"

# Stable node IDs for idempotent re-runs
N_SUPPLIER = "node_shenzhen_x"
N_COMPONENT = "node_component_b"
N_PRODUCT = "node_pumps"
N_FACILITY = "node_plant_1"
N_LINE = "node_line_2"
N_MARKET_RU = "node_market_ru"
N_MARKET_CIS = "node_market_cis"
N_CUR_RUB = "node_cur_rub"
N_CUR_CNY = "node_cur_cny"
N_CUR_USD = "node_cur_usd"


def upsert_user(db) -> User:
    user = db.query(User).filter(User.email == DEMO_USER_EMAIL).first()
    if user is None:
        user = User(
            id="usr_demo_owner",
            email=DEMO_USER_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            display_name="Демо Владелец",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()
    else:
        user.password_hash = hash_password(DEMO_PASSWORD)
        user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
    return user


def upsert_company(db, user: User) -> Company:
    company = db.get(Company, COMPANY_ID)
    if company is None:
        company = Company(id=COMPANY_ID, created_by=user.id)
        db.add(company)
    company.name = "СеверПром"
    company.legal_name = 'ООО "СеверПром"'
    company.tax_id = "7100000000"
    company.industry = "equipment"
    company.size_band = "medium"
    company.hq_region = "Тула"
    company.profile_status = "ready"
    company.digital_twin_status = "ready"
    company.is_demo = True

    membership = (
        db.query(CompanyMembership)
        .filter(
            CompanyMembership.user_id == user.id,
            CompanyMembership.company_id == company.id,
        )
        .first()
    )
    if membership is None:
        db.add(
            CompanyMembership(
                id=str(uuid4()),
                user_id=user.id,
                company_id=company.id,
                role="owner",
            )
        )

    settings = (
        db.query(CompanyProfileSettings)
        .filter(CompanyProfileSettings.company_id == company.id)
        .first()
    )
    if settings is None:
        settings = CompanyProfileSettings(id=str(uuid4()), company_id=company.id)
        db.add(settings)
    settings.purchase_currencies_json = ["RUB", "CNY", "USD"]
    # Full optional finance so macro/FX demos resolve to finance_ready for СеверПром.
    # Companies without these keys still get finance_data_required (see tests).
    settings.optional_finance_json = {
        "debt_amount": 120_000_000,
        "floating_rate_share_percent": 40,
        "near_term_payments_90d": 18_000_000,
        "fx_purchase_volume": 5_000_000,
        "cash_reserve_days": 45,
        "demo_loan_note": "Демонстрационный параметр, необязательный",
    }
    settings.preferences_json = {}
    settings.warnings_json = []
    return company


def upsert_node(db, **kwargs) -> CompanyNode:
    node = db.get(CompanyNode, kwargs["id"])
    if node is None:
        node = CompanyNode(**kwargs)
        db.add(node)
    else:
        for k, v in kwargs.items():
            setattr(node, k, v)
    return node


def upsert_edge(db, edge_id: str, **kwargs) -> CompanyEdge:
    edge = db.get(CompanyEdge, edge_id)
    if edge is None:
        edge = CompanyEdge(id=edge_id, **kwargs)
        db.add(edge)
    else:
        for k, v in kwargs.items():
            setattr(edge, k, v)
    return edge


def seed_graph(db, company: Company) -> None:
    upsert_node(
        db,
        id=N_SUPPLIER,
        company_id=company.id,
        node_type="supplier",
        name="Shenzhen X",
        country="Китай",
        attributes_json={"countries": ["Китай", "China"], "is_demo": True},
        status="active",
    )
    upsert_node(
        db,
        id=N_COMPONENT,
        company_id=company.id,
        node_type="component",
        name="Электронный модуль B",
        attributes_json={"sku": "B", "materials": ["electronics"], "is_demo": True},
        status="active",
    )
    upsert_node(
        db,
        id=N_PRODUCT,
        company_id=company.id,
        node_type="product",
        name="Промышленные насосы",
        attributes_json={"is_demo": True},
        status="active",
    )
    upsert_node(
        db,
        id=N_FACILITY,
        company_id=company.id,
        node_type="facility",
        name="Завод №1",
        region="Тула",
        country="Россия",
        attributes_json={"is_demo": True},
        status="active",
    )
    upsert_node(
        db,
        id=N_LINE,
        company_id=company.id,
        node_type="production_line",
        name="Линия №2",
        output_share_percent=24.0,
        attributes_json={"is_demo": True, "critical": True},
        status="active",
    )
    upsert_node(
        db,
        id=N_MARKET_RU,
        company_id=company.id,
        node_type="market",
        name="Россия",
        country="Россия",
        attributes_json={"is_demo": True},
        status="active",
    )
    upsert_node(
        db,
        id=N_MARKET_CIS,
        company_id=company.id,
        node_type="market",
        name="СНГ",
        attributes_json={"is_demo": True},
        status="active",
    )
    for nid, code in (
        (N_CUR_RUB, "RUB"),
        (N_CUR_CNY, "CNY"),
        (N_CUR_USD, "USD"),
    ):
        upsert_node(
            db,
            id=nid,
            company_id=company.id,
            node_type="currency",
            name=code,
            attributes_json={"code": code, "is_demo": True},
            status="active",
        )

    db.flush()  # nodes must exist before edge FKs

    upsert_edge(
        db,
        "edge_buys_shenzhen",
        company_id=company.id,
        from_node_id=N_PRODUCT,
        relation_type="buys_from",
        to_node_id=N_SUPPLIER,
        attributes_json={},
        confidence=0.92,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_supplies_b",
        company_id=company.id,
        from_node_id=N_SUPPLIER,
        relation_type="supplies",
        to_node_id=N_COMPONENT,
        attributes_json={},
        confidence=0.95,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_used_in_line",
        company_id=company.id,
        from_node_id=N_COMPONENT,
        relation_type="used_in",
        to_node_id=N_LINE,
        attributes_json={},
        confidence=0.9,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_produced_at",
        company_id=company.id,
        from_node_id=N_PRODUCT,
        relation_type="produced_at",
        to_node_id=N_FACILITY,
        attributes_json={},
        confidence=0.95,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_line_at_plant",
        company_id=company.id,
        from_node_id=N_LINE,
        relation_type="produced_at",
        to_node_id=N_FACILITY,
        attributes_json={},
        confidence=0.95,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_sold_ru",
        company_id=company.id,
        from_node_id=N_PRODUCT,
        relation_type="sold_in",
        to_node_id=N_MARKET_RU,
        attributes_json={},
        confidence=0.9,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_sold_cis",
        company_id=company.id,
        from_node_id=N_PRODUCT,
        relation_type="sold_in",
        to_node_id=N_MARKET_CIS,
        attributes_json={},
        confidence=0.85,
        source_type="seed",
    )
    company.digital_twin_coverage = 85.0


def upsert_event(db, **kwargs) -> Event:
    event = db.get(Event, kwargs["id"])
    if event is None:
        event = Event(**kwargs)
        db.add(event)
    else:
        for k, v in kwargs.items():
            setattr(event, k, v)
    return event


def seed_events(db) -> list[Event]:
    now = datetime(2026, 10, 10, 9, 30, tzinfo=timezone.utc)
    e1 = upsert_event(
        db,
        id=EVENT_EXPORT,
        title="Китай ограничивает экспорт электроники",
        summary=(
            "Демонстрационное событие: вводятся ограничения на экспорт электронных компонентов "
            "из Китая. Данные и источники — заглушки для хакатона."
        ),
        category="geopolitics",
        event_type="risk",
        severity=88.0,
        urgency_default="watch_now",
        status="active",
        occurred_at=now,
        effective_from=now,
        match_countries_json=["Китай", "China"],
        match_categories_json=["electronics", "export_control"],
        match_currencies_json=["CNY"],
        match_materials_json=["electronics", "модуль b", "component b"],
        attributes_json={"demo_story": "export_control"},
        is_demo=True,
    )
    if not db.query(EventSource).filter(EventSource.event_id == e1.id).first():
        db.add(
            EventSource(
                id="src_export_stub",
                event_id=e1.id,
                publisher="Demo Trade Wire (stub)",
                url="https://example.com/demo/china-export-stub",
                published_at=now,
                source_quality=0.78,
                excerpt="Демонстрационный источник. Не является официальной публикацией.",
                is_stub=True,
            )
        )

    e2 = upsert_event(
        db,
        id=EVENT_RATE,
        title="Ключевая ставка повышена",
        summary="Демо-событие: изменение ключевой ставки влияет на стоимость финансирования.",
        category="macro",
        event_type="risk",
        severity=55.0,
        urgency_default="this_week",
        status="active",
        occurred_at=now,
        effective_from=now,
        match_countries_json=["Россия"],
        match_categories_json=["rates"],
        match_currencies_json=["RUB"],
        match_materials_json=[],
        attributes_json={
            "demo_story": "rate_hike",
            # Stage 5.2 trusted observed key-rate decision (not claimed_delta_pp / severity).
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
        },
        is_demo=True,
    )
    if not db.query(EventSource).filter(EventSource.event_id == e2.id).first():
        db.add(
            EventSource(
                id="src_rate_stub",
                event_id=e2.id,
                publisher="Demo Macro Desk (stub)",
                url="https://example.com/demo/rate-stub",
                published_at=now,
                source_quality=0.7,
                excerpt="Демонстрационный источник.",
                is_stub=True,
            )
        )

    e3 = upsert_event(
        db,
        id=EVENT_OPP,
        title="Смягчение условий импорта на рынке СНГ",
        summary="Демо-возможность: изменение условий импорта открывает окно для роста продаж.",
        category="market",
        event_type="opportunity",
        severity=48.0,
        urgency_default="monitor",
        status="active",
        occurred_at=now,
        effective_from=now,
        match_countries_json=["СНГ"],
        match_categories_json=["import", "market"],
        match_currencies_json=[],
        match_materials_json=[],
        attributes_json={"demo_story": "market_opportunity"},
        is_demo=True,
    )
    if not db.query(EventSource).filter(EventSource.event_id == e3.id).first():
        db.add(
            EventSource(
                id="src_opp_stub",
                event_id=e3.id,
                publisher="Demo Market Brief (stub)",
                url="https://example.com/demo/market-stub",
                published_at=now,
                source_quality=0.65,
                excerpt="Демонстрационный источник.",
                is_stub=True,
            )
        )
    return [e1, e2, e3]


def seed_solutions(db, impact_id: str) -> None:
    demos = [
        {
            "id": "sol_thailand_a",
            "name": "Поставщик A (Таиланд)",
            "country": "Таиланд",
            "cost_delta_percent": 12.0,
            "lead_time_days": 35,
            "risk_percent": 28.0,
            "compatibility": 0.82,
            "notes": "Меньше риск — выше стоимость",
        },
        {
            "id": "sol_vietnam_b",
            "name": "Поставщик B (Вьетнам)",
            "country": "Вьетнам",
            "cost_delta_percent": 7.0,
            "lead_time_days": 48,
            "risk_percent": 36.0,
            "compatibility": 0.75,
            "notes": "Дешевле, дольше срок",
        },
        {
            "id": "sol_buffer_stock",
            "name": "Буферный запас + ускорение текущей поставки",
            "country": "Китай",
            "cost_delta_percent": 4.0,
            "lead_time_days": 20,
            "risk_percent": 55.0,
            "compatibility": 0.95,
            "notes": "Быстрее, но зависимость сохраняется",
        },
    ]
    for d in demos:
        row = db.get(SolutionCandidate, d["id"])
        if row is None:
            row = SolutionCandidate(id=d["id"], event_impact_id=impact_id)
            db.add(row)
        row.event_impact_id = impact_id
        row.name = d["name"]
        row.country = d["country"]
        row.cost_delta_percent = d["cost_delta_percent"]
        row.lead_time_days = d["lead_time_days"]
        row.risk_percent = d["risk_percent"]
        row.compatibility = d["compatibility"]
        row.availability_status = "demo_estimate"
        row.is_demo = True
        row.notes = d["notes"]
        row.sort_breakdown_json = {}


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = upsert_user(db)
        company = upsert_company(db, user)
        seed_graph(db, company)
        events = seed_events(db)
        db.flush()

        for event in events:
            impact = recompute_company_impact(db, event, company)
            if event.id == EVENT_EXPORT:
                seed_solutions(db, impact.id)

        db.commit()
        print("OK Seed complete")
        print(f"  user:    {DEMO_USER_EMAIL} / {DEMO_PASSWORD}")
        print(f"  company: {company.name} ({company.id})")
        print(f"  event:   {EVENT_EXPORT}")
        print("  flow:    dashboard -> event -> impact -> solutions -> simulate -> decision")
    finally:
        db.close()


if __name__ == "__main__":
    main()
