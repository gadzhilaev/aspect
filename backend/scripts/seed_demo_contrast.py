"""Idempotent contrast demo company (Company B) for personalization proof.

СеверПром (A) remains the primary seed from scripts.seed_demo.
This script adds ВолгПром (B): comparable manufacturer with a *Russian* supplier
of electronics — no China supplier in the twin.

Usage (do NOT run against a user's production DB from the agent):
  python -m scripts.seed_demo_contrast

Safe for the isolated test DB (called from tests).
Requires scripts.seed_demo to have created the China export event.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

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
    User,
)
from app.services.impact import recompute_events_for_company
from scripts.seed_demo import EVENT_EXPORT

DEMO_B_EMAIL = "demo_volga@kontur.app"
DEMO_B_PASSWORD = "DemoKontur1!"
COMPANY_B_ID = "cmp_volgaprom"

N_SUPPLIER_RU = "node_volga_supplier_ru"
N_COMPONENT = "node_volga_component_b"
N_PRODUCT = "node_volga_pumps"
N_FACILITY = "node_volga_plant"
N_LINE = "node_volga_line_1"
N_MARKET_RU = "node_volga_market_ru"
N_CUR_RUB = "node_volga_cur_rub"


def upsert_user_b(db) -> User:
    user = db.query(User).filter(User.email == DEMO_B_EMAIL).first()
    if user is None:
        user = User(
            id="usr_demo_volga",
            email=DEMO_B_EMAIL,
            password_hash=hash_password(DEMO_B_PASSWORD),
            display_name="Демо ВолгПром",
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()
    else:
        user.password_hash = hash_password(DEMO_B_PASSWORD)
        user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
    return user


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


def upsert_company_b(db, user: User) -> Company:
    company = db.get(Company, COMPANY_B_ID)
    if company is None:
        company = Company(id=COMPANY_B_ID, created_by=user.id)
        db.add(company)
    company.name = "ВолгПром"
    company.legal_name = 'ООО "ВолгПром"'
    company.tax_id = "6300000000"
    company.industry = "equipment"
    company.size_band = "medium"
    company.hq_region = "Самара"
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
    # RUB only — no CNY that could be mistaken for China exposure
    settings.purchase_currencies_json = ["RUB"]
    settings.optional_finance_json = {}
    settings.preferences_json = {}
    settings.warnings_json = []
    return company


def seed_graph_b(db, company: Company) -> None:
    """Russian supplier → electronics component → line (share known). No China nodes."""
    upsert_node(
        db,
        id=N_SUPPLIER_RU,
        company_id=company.id,
        node_type="supplier",
        name="ООО КомплектПром",
        country="Россия",
        attributes_json={
            "countries": ["Россия", "Russia"],
            "is_demo": True,
            "note": "Происхождение закупок поставщика в профиле не указано",
        },
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
        name="Завод ВолгПром",
        region="Самара",
        country="Россия",
        attributes_json={"is_demo": True},
        status="active",
    )
    upsert_node(
        db,
        id=N_LINE,
        company_id=company.id,
        node_type="production_line",
        name="Линия №1",
        output_share_percent=30.0,
        attributes_json={"is_demo": True},
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
        id=N_CUR_RUB,
        company_id=company.id,
        node_type="currency",
        name="RUB",
        attributes_json={"code": "RUB", "is_demo": True},
        status="active",
    )
    db.flush()

    upsert_edge(
        db,
        "edge_volga_buys",
        company_id=company.id,
        from_node_id=N_PRODUCT,
        relation_type="buys_from",
        to_node_id=N_SUPPLIER_RU,
        attributes_json={},
        confidence=0.9,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_volga_supplies",
        company_id=company.id,
        from_node_id=N_SUPPLIER_RU,
        relation_type="supplies",
        to_node_id=N_COMPONENT,
        attributes_json={},
        confidence=0.9,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_volga_used_in",
        company_id=company.id,
        from_node_id=N_COMPONENT,
        relation_type="used_in",
        to_node_id=N_LINE,
        attributes_json={},
        confidence=0.88,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_volga_produced",
        company_id=company.id,
        from_node_id=N_PRODUCT,
        relation_type="produced_at",
        to_node_id=N_FACILITY,
        attributes_json={},
        confidence=0.9,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_volga_line_plant",
        company_id=company.id,
        from_node_id=N_LINE,
        relation_type="produced_at",
        to_node_id=N_FACILITY,
        attributes_json={},
        confidence=0.9,
        source_type="seed",
    )
    upsert_edge(
        db,
        "edge_volga_sold_ru",
        company_id=company.id,
        from_node_id=N_PRODUCT,
        relation_type="sold_in",
        to_node_id=N_MARKET_RU,
        attributes_json={},
        confidence=0.85,
        source_type="seed",
    )
    company.digital_twin_coverage = 80.0


def add_china_supplier_link(db, company: Company) -> CompanyNode:
    """Test helper: attach a China supplier + edges into the existing component."""
    node = upsert_node(
        db,
        id="node_volga_supplier_cn",
        company_id=company.id,
        node_type="supplier",
        name="Shenzhen Volga Link",
        country="Китай",
        attributes_json={"countries": ["Китай", "China"], "is_demo": True},
        status="active",
    )
    db.flush()  # node must exist before edge FK
    upsert_edge(
        db,
        "edge_volga_cn_supplies",
        company_id=company.id,
        from_node_id=node.id,
        relation_type="supplies",
        to_node_id=N_COMPONENT,
        attributes_json={},
        confidence=0.9,
        source_type="seed",
    )
    db.flush()
    return node


def remove_china_supplier_link(db, company: Company) -> None:
    """Test helper: remove China supplier link (edges + node)."""
    from app.models import CompanyEdge

    db.query(CompanyEdge).filter(CompanyEdge.id == "edge_volga_cn_supplies").delete()
    node = db.get(CompanyNode, "node_volga_supplier_cn")
    if node is not None:
        db.delete(node)
    db.flush()


def seed_contrast(db) -> Company:
    user = upsert_user_b(db)
    company = upsert_company_b(db, user)
    seed_graph_b(db, company)
    db.flush()
    # Recompute: China export should NOT create an active impact for B
    recompute_events_for_company(db, company, demo_only=False)
    return company


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.get(Event, EVENT_EXPORT) is None:
            raise SystemExit(
                "Missing evt_china_export_001 — run scripts.seed_demo first."
            )
        company = seed_contrast(db)
        db.commit()
        print("OK Contrast seed complete")
        print(f"  user B:  {DEMO_B_EMAIL} / {DEMO_B_PASSWORD}")
        print(f"  company: {company.name} ({company.id})")
        print(f"  event:   {EVENT_EXPORT} (expect: not relevant for B)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
