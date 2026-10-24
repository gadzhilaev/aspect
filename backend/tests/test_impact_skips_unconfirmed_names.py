"""Paths with unconfirmed node names must not yield supply_chain_ready reasons."""

from __future__ import annotations

from uuid import uuid4

from app.models import Company, CompanyEdge, CompanyNode, Event, User
from app.services.impact import recompute_company_impact
from app.services.graph_names import is_unconfirmed_node_name


def test_recompute_skips_unconfirmed_component(db):
    assert is_unconfirmed_node_name("не знаю")
    user = db.query(User).first()
    company = Company(
        id=str(uuid4()),
        name="Probe Co",
        created_by=user.id,
        size_band="medium",
        industry="manufacturing",
    )
    db.add(company)
    db.flush()
    supplier = CompanyNode(
        id=str(uuid4()),
        company_id=company.id,
        node_type="supplier",
        name="Поставщик (Китай)",
        country="Китай",
    )
    component = CompanyNode(
        id=str(uuid4()),
        company_id=company.id,
        node_type="component",
        name="не знаю",
    )
    line = CompanyNode(
        id=str(uuid4()),
        company_id=company.id,
        node_type="production_line",
        name="большая",
        output_share_percent=24.0,
    )
    db.add_all([supplier, component, line])
    # Session autoflush=False + dual FK to company_nodes requires nodes before edges.
    db.flush()
    db.add(
        CompanyEdge(
            id=str(uuid4()),
            company_id=company.id,
            from_node_id=supplier.id,
            to_node_id=component.id,
            relation_type="supplies",
            confidence=0.9,
            source_type="user",
        )
    )
    db.add(
        CompanyEdge(
            id=str(uuid4()),
            company_id=company.id,
            from_node_id=component.id,
            to_node_id=line.id,
            relation_type="used_in",
            confidence=0.9,
            source_type="user",
        )
    )
    event = db.get(Event, "evt_china_export_001")
    assert event is not None
    db.commit()

    impact = recompute_company_impact(db, event, company)
    db.commit()
    assert "не знаю" not in (impact.reason_summary or "").lower()
    assert "→" not in (impact.reason_summary or "") or "Ограничение связано с не знаю" not in (
        impact.reason_summary or ""
    )
    # Must not claim confirmed chain through the placeholder
    assert not (impact.reason_summary or "").startswith("Ограничение связано с не знаю")

    # Avoid polluting session DB for later recompute_event_for_ready_companies tests.
    from app.models import EventImpact

    db.query(EventImpact).filter(EventImpact.company_id == company.id).delete()
    db.query(CompanyEdge).filter(CompanyEdge.company_id == company.id).delete()
    db.query(CompanyNode).filter(CompanyNode.company_id == company.id).delete()
    db.delete(company)
    db.commit()
