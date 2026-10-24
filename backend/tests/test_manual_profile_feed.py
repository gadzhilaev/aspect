"""Manual twin → personal feed without case-link; empty-state honesty; rate vs swap."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Company, CompanyEdge, CompanyMembership, CompanyNode, Event, EventImpact
from app.services.impact import recompute_events_for_company
from app.services.relevance import (
    analyze_event_company_relevance,
    event_suggests_rate_track,
)


def _cleanup_company(db: Session, company_id: str) -> None:
    """Remove test company graph so later suite tests see a stable ready-set."""
    db.query(EventImpact).filter(EventImpact.company_id == company_id).delete()
    db.query(CompanyEdge).filter(CompanyEdge.company_id == company_id).delete()
    db.query(CompanyNode).filter(CompanyNode.company_id == company_id).delete()
    db.query(CompanyMembership).filter(CompanyMembership.company_id == company_id).delete()
    company = db.get(Company, company_id)
    if company is not None:
        db.delete(company)
    db.commit()


def _uid(prefix: str = "x") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _register(client: TestClient, email: str | None = None) -> dict[str, str]:
    mail = email or f"{_uid('u')}@example.com"
    password = "ManualFeed1!"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": mail, "password": password, "display_name": "Manual Feed"},
    )
    assert r.status_code == 200, r.text
    code = (r.json().get("details") or {}).get("demo_code")
    assert code, r.text
    assert (
        client.post(
            "/api/v1/auth/verify-email",
            json={"email": mail, "code": code},
        ).status_code
        == 200
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": mail, "password": password},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _manual_chain(
    db: Session,
    company_id: str,
    *,
    supplier_country: str,
    supplier_name: str,
    component: str,
    product: str,
    market_country: str,
    market_name: str,
) -> None:
    ids: dict[str, str] = {}
    for ntype, name, country, share in (
        ("supplier", supplier_name, supplier_country, None),
        ("component", component, None, None),
        ("production_line", "Линия А", None, 40.0),
        ("facility", "Площадка", "Россия", None),
        ("product", product, None, None),
        ("market", market_name, market_country, None),
    ):
        nid = str(uuid.uuid4())
        ids[ntype] = nid
        db.add(
            CompanyNode(
                id=nid,
                company_id=company_id,
                node_type=ntype,
                name=name,
                country=country,
                status="active",
                output_share_percent=share,
                attributes_json={},
            )
        )
    # autoflush=False: flush nodes before edges (two FKs → company_nodes).
    db.flush()
    pairs = [
        ("supplier", "supplies", "component"),
        ("component", "used_in", "production_line"),
        ("production_line", "produced_at", "facility"),
        ("product", "produced_at", "facility"),
        ("product", "sold_in", "market"),
        ("product", "buys_from", "supplier"),
    ]
    for src, rel, dst in pairs:
        db.add(
            CompanyEdge(
                id=str(uuid.uuid4()),
                company_id=company_id,
                from_node_id=ids[src],
                relation_type=rel,
                to_node_id=ids[dst],
                attributes_json={},
                confidence=0.9,
                source_type="user",
            )
        )
    company = db.get(Company, company_id)
    assert company is not None
    company.profile_status = "ready"
    company.digital_twin_status = "ready"
    company.digital_twin_coverage = 100.0
    db.flush()


def _china_chain(db: Session, company_id: str) -> None:
    _manual_chain(
        db,
        company_id,
        supplier_country="Китай",
        supplier_name="Поставщик (Китай)",
        component="Телефон",
        product="Телефон",
        market_country="Россия",
        market_name="Россия",
    )


def _non_seed_chain(db: Session, company_id: str) -> None:
    """Profile that does not intersect seed_demo China/СНГ events."""
    _manual_chain(
        db,
        company_id,
        supplier_country="Бразилия",
        supplier_name="Поставщик (Бразилия)",
        component="Мебель",
        product="Мебель",
        market_country="США",
        market_name="США",
    )


def test_swap_and_money_market_not_key_rate():
    swap = Event(
        id=_uid("ev"),
        title="Вмененная ставка валютного свопа овернайт в юанях",
        summary="Котировка свопа",
        category="macro",
        event_type="risk",
        severity=60.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_categories_json=["macro"],
        match_countries_json=[],
        match_currencies_json=["RUB"],
        match_materials_json=[],
        attributes_json={},
        is_demo=False,
    )
    miacr = Event(
        id=_uid("ev"),
        title="Ставки группы MIACR",
        summary="",
        category="macro",
        event_type="risk",
        severity=60.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_categories_json=["macro"],
        match_countries_json=[],
        match_currencies_json=["RUB"],
        match_materials_json=[],
        attributes_json={},
        is_demo=False,
    )
    key = Event(
        id=_uid("ev"),
        title="ЦБ сохранил ключевую ставку",
        summary="Решение по ДКП",
        category="macro",
        event_type="risk",
        severity=55.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_categories_json=["macro", "rates"],
        match_countries_json=["Россия"],
        match_currencies_json=["RUB"],
        match_materials_json=[],
        attributes_json={},
        is_demo=False,
    )
    assert event_suggests_rate_track(swap) is False
    assert event_suggests_rate_track(miacr) is False
    assert event_suggests_rate_track(key) is True


def test_manual_profile_empty_feed_without_case_link(
    client: TestClient, db: Session
):
    headers = _register(client)
    created = client.post(
        "/api/v1/companies",
        headers=headers,
        json={
            "name": "упк-тест",
            "industry": "electronics",
            "hq_region": "Махачкала",
            "size_band": "medium",
        },
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]

    _non_seed_chain(db, cid)
    # CBR-like corpus: no country/material overlap; swap must not invent rate match
    db.add(
        Event(
            id=_uid("live"),
            title="Вмененная ставка валютного свопа овернайт в юанях",
            summary="Котировка свопа",
            category="macro",
            event_type="risk",
            severity=60.0,
            urgency_default="watch",
            status="active",
            occurred_at=datetime.now(timezone.utc),
            match_categories_json=["macro"],
            match_countries_json=[],
            match_currencies_json=["RUB"],
            match_materials_json=[],
            attributes_json={},
            is_demo=False,
        )
    )
    db.add(
        Event(
            id=_uid("mkt"),
            title="Проекты нормативных документов Банка России",
            summary="",
            category="market",
            event_type="risk",
            severity=55.0,
            urgency_default="watch",
            status="active",
            occurred_at=datetime.now(timezone.utc),
            match_categories_json=["market"],
            match_countries_json=[],
            match_currencies_json=[],
            match_materials_json=[],
            attributes_json={},
            is_demo=False,
        )
    )
    db.commit()

    company = db.get(Company, cid)
    assert company is not None
    impacts = recompute_events_for_company(db, company, demo_only=False)
    db.commit()
    active = [
        i
        for i in impacts
        if i.status in {"action_required", "monitor"}
    ]
    assert active == []
    assert (
        db.query(EventImpact)
        .filter(
            EventImpact.company_id == cid,
            EventImpact.status.in_(["action_required", "monitor"]),
        )
        .count()
        == 0
    )

    dash = client.get(f"/api/v1/companies/{cid}/dashboard", headers=headers)
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["priority_events"] == []
    empty = body.get("feed_empty") or {}
    assert empty.get("reason") == "no_matching_published_news"
    assert "конкурсн" not in (empty.get("detail") or "").lower()
    assert empty.get("primary_href") == "/news"
    # case block must not invent a linked demo company
    ctx = client.get(f"/api/v1/companies/{cid}/context", headers=headers)
    assert ctx.status_code == 200, ctx.text
    case = (ctx.json().get("case_context") or {})
    assert case.get("status") in {
        "not_linked",
        "integration_not_configured",
        "profile_unavailable",
        None,
    } or case.get("status") != "profile_available"
    _cleanup_company(db, cid)


def test_manual_profile_china_export_enters_feed(
    client: TestClient, db: Session
):
    headers = _register(client)
    created = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "ChainCo", "industry": "electronics"},
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    try:
        _china_chain(db, cid)

        eid = _uid("china")
        db.add(
            Event(
                id=eid,
                title="Ограничения на экспорт электроники из Китая",
                summary="Контроль поставок компонентов",
                category="geopolitics",
                event_type="risk",
                severity=80.0,
                urgency_default="watch",
                status="active",
                occurred_at=datetime.now(timezone.utc),
                match_categories_json=["export_control"],
                match_countries_json=["Китай"],
                match_currencies_json=[],
                match_materials_json=["телефон"],
                attributes_json={},
                is_demo=False,
            )
        )
        db.commit()

        company = db.get(Company, cid)
        nodes = db.query(CompanyNode).filter(CompanyNode.company_id == cid).all()
        rel = analyze_event_company_relevance(db.get(Event, eid), company, nodes)
        assert rel.is_relevant is True

        built = client.post(
            f"/api/v1/companies/{cid}/digital-twin/build",
            headers=headers,
        )
        assert built.status_code == 200, built.text
        assert built.json()["impacts_computed"] >= 1

        dash = client.get(f"/api/v1/companies/{cid}/dashboard", headers=headers)
        assert dash.status_code == 200, dash.text
        body = dash.json()
        ids = [e["id"] for e in body["priority_events"]]
        assert eid in ids
        assert body.get("feed_empty") is None
        # GET must not surface not_relevant leftovers as priority cards
        for card in body["priority_events"]:
            assert card.get("status") != "not_relevant"
    finally:
        _cleanup_company(db, cid)
