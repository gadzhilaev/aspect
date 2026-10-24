"""Provable personalization: same news, different companies, profile change, feed sort."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Company, CompanyNode, Event, EventImpact
from app.services.impact import (
    IMPACT_STATUS_NOT_RELEVANT,
    event_matches_company,
    recompute_company_impact,
    recompute_events_for_company,
)
from app.services.relevance import analyze_event_company_relevance
from scripts.seed_demo import COMPANY_ID as COMPANY_A
from scripts.seed_demo import EVENT_EXPORT
from scripts.seed_demo_contrast import (
    COMPANY_B_ID,
    DEMO_B_EMAIL,
    DEMO_B_PASSWORD,
    add_china_supplier_link,
    remove_china_supplier_link,
    seed_contrast,
)


def _auth_b(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_B_EMAIL, "password": DEMO_B_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_seed_contrast_and_divergent_china_results(db: Session, client: TestClient, auth_headers: dict):
    seed_contrast(db)
    db.commit()

    event = db.get(Event, EVENT_EXPORT)
    company_a = db.get(Company, COMPANY_A)
    company_b = db.get(Company, COMPANY_B_ID)
    assert event and company_a and company_b

    nodes_a = db.query(CompanyNode).filter(CompanyNode.company_id == COMPANY_A).all()
    nodes_b = db.query(CompanyNode).filter(CompanyNode.company_id == COMPANY_B_ID).all()

    rel_a = analyze_event_company_relevance(event, company_a, nodes_a, purchase_currencies=["RUB", "CNY"])
    rel_b = analyze_event_company_relevance(event, company_b, nodes_b, purchase_currencies=["RUB"])
    assert rel_a.is_relevant is True
    assert any(m.role == "supplier" for m in rel_a.matched_features)
    assert rel_b.is_relevant is False
    assert "не установлена" in rel_b.summary.lower() or "не указан" in rel_b.summary.lower()

    impact_a = recompute_company_impact(db, event, company_a)
    db.commit()
    assert (impact_a.score_breakdown_json or {}).get("assessment_state") == "supply_chain_ready"
    assert (impact_a.score_breakdown_json or {}).get("score_kind") == "company_calculated"
    assert impact_a.exposure_value is not None and impact_a.exposure_value > 0

    # B: no active impact for China export
    impacts_b = recompute_events_for_company(db, company_b)
    active_china = [
        i
        for i in impacts_b
        if i.event_id == EVENT_EXPORT and i.status != IMPACT_STATUS_NOT_RELEVANT
    ]
    assert active_china == []

    # API: A has impact, B relevance endpoint explains absence (no side-effect create)
    ok_a = client.get(
        f"/api/v1/events/{EVENT_EXPORT}/impact",
        params={"company_id": COMPANY_A},
        headers=auth_headers,
    )
    assert ok_a.status_code == 200
    assert ok_a.json()["score_kind"] == "company_calculated"

    headers_b = _auth_b(client)
    before = (
        db.query(EventImpact)
        .filter(EventImpact.company_id == COMPANY_B_ID, EventImpact.event_id == EVENT_EXPORT)
        .count()
    )
    rel = client.get(
        f"/api/v1/events/{EVENT_EXPORT}/relevance",
        params={"company_id": COMPANY_B_ID},
        headers=headers_b,
    )
    assert rel.status_code == 200
    body = rel.json()
    assert body["is_relevant"] is False
    assert body["has_active_impact"] is False
    after = (
        db.query(EventImpact)
        .filter(EventImpact.company_id == COMPANY_B_ID, EventImpact.event_id == EVENT_EXPORT)
        .count()
    )
    assert after == before  # GET did not create impact

    miss = client.get(
        f"/api/v1/events/{EVENT_EXPORT}/impact",
        params={"company_id": COMPANY_B_ID},
        headers=headers_b,
    )
    assert miss.status_code == 404


def test_same_graph_different_names_same_relevance(db: Session):
    seed_contrast(db)
    db.commit()
    event = db.get(Event, EVENT_EXPORT)
    company_b = db.get(Company, COMPANY_B_ID)
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == COMPANY_B_ID).all()
    assert event and company_b
    r1 = analyze_event_company_relevance(event, company_b, nodes, purchase_currencies=["RUB"])
    # Rename company — must not change relevance
    company_b.name = "Совсем Другое Имя"
    r2 = analyze_event_company_relevance(event, company_b, nodes, purchase_currencies=["RUB"])
    assert r1.is_relevant == r2.is_relevant
    assert r1.level == r2.level


def test_market_china_not_confused_with_supplier(db: Session):
    """Sales market in China must not open export-control personalization."""
    seed_contrast(db)
    db.commit()
    event = db.get(Event, EVENT_EXPORT)
    company_b = db.get(Company, COMPANY_B_ID)
    assert event and company_b
    # Add China as sales market only
    db.add(
        CompanyNode(
            id="node_volga_market_cn_tmp",
            company_id=COMPANY_B_ID,
            node_type="market",
            name="Китай",
            country="Китай",
            attributes_json={"countries": ["China"], "is_demo": True},
            status="active",
        )
    )
    db.flush()
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == COMPANY_B_ID).all()
    rel = analyze_event_company_relevance(event, company_b, nodes, purchase_currencies=["RUB"])
    assert rel.is_relevant is False
    assert any("рынок" in lim.lower() or "поставок" in lim.lower() for lim in rel.limitations) or (
        "не установлена" in rel.summary.lower()
    )
    db.query(CompanyNode).filter(CompanyNode.id == "node_volga_market_cn_tmp").delete()
    db.commit()


def test_other_country_no_false_chain(db: Session):
    company_a = db.get(Company, COMPANY_A)
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == COMPANY_A).all()
    foreign = Event(
        id="evt_tmp_brazil",
        title="Бразилия",
        summary="s",
        category="geopolitics",
        event_type="risk",
        severity=70,
        urgency_default="watch",
        status="active",
        occurred_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        match_countries_json=["Бразилия"],
        match_categories_json=["export_control"],
        match_currencies_json=[],
        match_materials_json=["electronics"],
        attributes_json={},
        is_demo=True,
    )
    assert event_matches_company(foreign, company_a, nodes, purchase_currencies=["CNY"]) is False


def test_profile_change_adds_and_removes_relevance(db: Session):
    seed_contrast(db)
    db.commit()
    event = db.get(Event, EVENT_EXPORT)
    company_b = db.get(Company, COMPANY_B_ID)
    assert event and company_b

    recompute_events_for_company(db, company_b)
    active = (
        db.query(EventImpact)
        .filter(
            EventImpact.company_id == COMPANY_B_ID,
            EventImpact.event_id == EVENT_EXPORT,
            EventImpact.status != IMPACT_STATUS_NOT_RELEVANT,
        )
        .all()
    )
    assert active == []

    add_china_supplier_link(db, company_b)
    db.flush()
    impacts = recompute_events_for_company(db, company_b)
    china = [i for i in impacts if i.event_id == EVENT_EXPORT]
    assert len(china) == 1
    assert china[0].status != IMPACT_STATUS_NOT_RELEVANT
    assert (china[0].score_breakdown_json or {}).get("score_kind") == "company_calculated"
    impact_id = china[0].id
    old_score = china[0].impact_score

    # Second recompute must not duplicate
    impacts2 = recompute_events_for_company(db, company_b)
    china2 = [i for i in impacts2 if i.event_id == EVENT_EXPORT]
    assert len(china2) == 1
    assert china2[0].id == impact_id

    remove_china_supplier_link(db, company_b)
    db.flush()
    recompute_events_for_company(db, company_b)
    row = (
        db.query(EventImpact)
        .filter(
            EventImpact.company_id == COMPANY_B_ID,
            EventImpact.event_id == EVENT_EXPORT,
        )
        .one()
    )
    assert row.status == IMPACT_STATUS_NOT_RELEVANT
    assert row.id == impact_id  # same row, not deleted
    # Historical score not rewritten to a new calculation
    assert row.impact_score == old_score


def test_feed_groups_comparable_kinds(
    client: TestClient, auth_headers: dict, db: Session
):
    # Ensure SeverProm has both company_calculated (China) and severity signal (rate)
    company = db.get(Company, COMPANY_A)
    assert company
    recompute_events_for_company(db, company)

    dash = client.get(
        f"/api/v1/companies/{COMPANY_A}/dashboard",
        headers=auth_headers,
    )
    assert dash.status_code == 200
    body = dash.json()
    assert "feed_sort_rule" in body
    cards = body["priority_events"]
    kinds = [c.get("score_kind") for c in cards]
    if "company_calculated" in kinds and "event_severity_signal" in kinds:
        first_calc = kinds.index("company_calculated")
        first_sig = kinds.index("event_severity_signal")
        assert first_calc < first_sig

    listing = client.get(
        f"/api/v1/companies/{COMPANY_A}/events",
        headers=auth_headers,
    )
    assert listing.status_code == 200
    assert "feed_sort_rule" in listing.json()
    assert ":" in (listing.json().get("next_cursor") or "0:0") or listing.json().get(
        "next_cursor"
    ) is None


def test_public_news_independent_of_personal_impact(client: TestClient, db: Session):
    seed_contrast(db)
    db.commit()
    pub = client.get(f"/api/v1/public/news/{EVENT_EXPORT}")
    assert pub.status_code == 200
    assert pub.json()["id"] == EVENT_EXPORT


def test_acl_b_cannot_read_a_impact(client: TestClient, db: Session):
    seed_contrast(db)
    db.commit()
    headers_b = _auth_b(client)
    denied = client.get(
        f"/api/v1/events/{EVENT_EXPORT}/impact",
        params={"company_id": COMPANY_A},
        headers=headers_b,
    )
    assert denied.status_code in {403, 404}


def test_materials_alone_do_not_open_china_export_for_b(db: Session):
    seed_contrast(db)
    db.commit()
    event = db.get(Event, EVENT_EXPORT)
    company_b = db.get(Company, COMPANY_B_ID)
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == COMPANY_B_ID).all()
    # B has electronics materials but Russian supplier only
    assert any(
        "electronics" in str((n.attributes_json or {}).get("materials") or []).lower()
        for n in nodes
        if n.node_type == "component"
    )
    assert event_matches_company(event, company_b, nodes, purchase_currencies=["RUB"]) is False
