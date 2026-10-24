"""Stage 6.9: personal feed includes case-profile matches without EventImpact."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import (
    CaseOrgCompanyLink,
    Company,
    CompanyNode,
    Decision,
    Event,
    EventImpact,
    Scenario,
)
from app.services.case_profile_feed import entry_after_cursor, parse_feed_cursor, FeedEntry
from app.services.case_data.link_org_company import run_link
from app.services.case_data.resolution import PRODUCT_CODES
from app.services.case_profile_relevance import (
    CaseProductSnapshot,
    detect_event_themes,
    evaluate_profile_relevance,
)
from tests.test_case_context_api import (
    SLOT,
    _activate,
    _add_org,
    _auth_headers,
    _seed_ready,
    _session,
    _user_company,
    api_harness,
)

pytest_plugins = []  # api_harness imported from test_case_context_api


def _uid() -> str:
    return str(uuid.uuid4())


def _rate_event(
    session,
    *,
    title: str = "[СИНТЕТИЧЕСКИЙ] Регулятор сохранил ключевую ставку",
    categories: list[str] | None = None,
    event_id: str | None = None,
) -> Event:
    ev = Event(
        id=event_id or f"evt_rate_{_uid()[:8]}",
        title=title,
        summary="Синтетическая новость о решении по ключевой ставке.",
        category="macro",
        event_type="risk",
        severity=40.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
        match_countries_json=[],
        match_categories_json=categories
        if categories is not None
        else ["ключевая ставка", "ДКП"],
        match_currencies_json=[],
        match_materials_json=[],
        attributes_json={"synthetic": True},
        is_demo=True,
    )
    session.add(ev)
    session.flush()
    return ev


def _steel_event(session) -> Event:
    ev = Event(
        id=f"evt_steel_{_uid()[:8]}",
        title="[СИНТЕТИЧЕСКИЙ] Цены на стальной прокат",
        summary="Котировки горячекатаного проката.",
        category="market",
        event_type="risk",
        severity=20.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
        match_countries_json=[],
        match_categories_json=["сталь", "металлургия"],
        match_currencies_json=[],
        match_materials_json=[],
        attributes_json={"synthetic": True},
        is_demo=True,
    )
    session.add(ev)
    session.flush()
    return ev


def _marks(*, loan: bool = False, deposit: bool = False) -> dict[str, bool | None]:
    return {c: (c == "LOA" and loan) or (c == "DEP" and deposit) for c in PRODUCT_CODES}


# --- unit ---


def test_theme_requires_compound_not_lone_rate_token():
    ev = Event(
        id="x",
        title="Обновление ставок по вкладам партнёров",
        summary="Маркетинговая рассылка.",
        category="macro",
        event_type="info",
        severity=1,
        urgency_default="watch",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_categories_json=["ставка"],
    )
    assert detect_event_themes(ev) == []


def test_theme_from_structured_key_rate():
    ev = Event(
        id="x",
        title="Новость",
        summary="Текст",
        category="macro",
        event_type="risk",
        severity=1,
        urgency_default="watch",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_categories_json=["ключевая ставка"],
    )
    themes = detect_event_themes(ev)
    assert len(themes) == 1 and themes[0].theme == "policy_rate"


def test_false_unknown_conflict_do_not_match():
    ev = Event(
        id="x",
        title="Ставка",
        summary="ЦБ",
        category="macro",
        event_type="risk",
        severity=1,
        urgency_default="watch",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_categories_json=["ключевая ставка", "ДКП"],
    )
    for pst in ("false", "unknown", "conflict"):
        snap = CaseProductSnapshot(
            status_by_code={"LOA": pst, "DEP": "false"},
            case_status="profile_available",
            external_uid="U_1",
            snapshot_id="s",
            version_label="v",
            version_seq=1,
            provenance=None,
        )
        assert evaluate_profile_relevance(ev, snap).matched is False


def test_loan_and_deposit_rules_differ():
    ev = Event(
        id="x",
        title="Новость",
        summary="Текст",
        category="macro",
        event_type="risk",
        severity=1,
        urgency_default="watch",
        status="active",
        occurred_at=datetime.now(timezone.utc),
        match_categories_json=["ключевая ставка"],
    )
    loan = CaseProductSnapshot(
        {"LOA": "true", "DEP": "false"},
        "profile_available",
        "U_A",
        "s",
        "v",
        1,
        None,
    )
    dep = CaseProductSnapshot(
        {"LOA": "false", "DEP": "true"},
        "profile_available",
        "U_B",
        "s",
        "v",
        1,
        None,
    )
    r_loan = evaluate_profile_relevance(ev, loan)
    r_dep = evaluate_profile_relevance(ev, dep)
    assert r_loan.matched and r_dep.matched
    assert {m.product_code for m in r_loan.matches} == {"LOA"}
    assert {m.product_code for m in r_dep.matches} == {"DEP"}


# --- API ---


def test_rate_event_loan_vs_deposit_bases(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(
            s,
            snap,
            external_uid="U_901",
            product_marks=[_marks(loan=True)],
        )
        _add_org(
            s,
            snap,
            external_uid="U_902",
            product_marks=[_marks(deposit=True)],
        )
        user_a, company_a = _user_company(s, name="Альфа Кредит")
        user_b, company_b = _user_company(s, name="Бета Депозит")
        ev = _rate_event(s)
        steel = _steel_event(s)
        s.commit()
        snap_id = snap.id
        company_a_id, company_b_id = company_a.id, company_b.id
        user_a_id, user_b_id = user_a.id, user_b.id
        event_id, steel_id = ev.id, steel.id

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_901",
        company_id=company_a_id,
        linked_by="ops",
    )
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_902",
        company_id=company_b_id,
        linked_by="ops",
    )

    dash_a = client.get(
        f"/api/v1/companies/{company_a_id}/dashboard",
        headers=_auth_headers(user_a_id),
    )
    dash_b = client.get(
        f"/api/v1/companies/{company_b_id}/dashboard",
        headers=_auth_headers(user_b_id),
    )
    assert dash_a.status_code == 200, dash_a.text
    assert dash_b.status_code == 200, dash_b.text
    cards_a = {c["id"]: c for c in dash_a.json()["priority_events"]}
    cards_b = {c["id"]: c for c in dash_b.json()["priority_events"]}
    assert event_id in cards_a and event_id in cards_b
    assert steel_id not in cards_a and steel_id not in cards_b

    ca, cb = cards_a[event_id], cards_b[event_id]
    assert ca["score_kind"] == "case_profile_match"
    assert cb["score_kind"] == "case_profile_match"
    assert ca["profile_relevance"]["matches"][0]["product_code"] == "LOA"
    assert cb["profile_relevance"]["matches"][0]["product_code"] == "DEP"
    assert "кредит" in ca["profile_relevance"]["summary"].lower()
    assert "депозит" in cb["profile_relevance"]["summary"].lower()
    assert ca["impact_score"] is None
    assert ca["impact_score_available"] is False
    assert cb["impact_score"] is None
    assert cb["impact_score_available"] is False


def test_rename_company_does_not_change_profile_match(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_903", product_marks=[_marks(loan=True)])
        user, company = _user_company(s, name="Старое Имя")
        ev = _rate_event(s)
        s.commit()
        snap_id, cid, uid, eid = snap.id, company.id, user.id, ev.id

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_903",
        company_id=cid,
        linked_by="ops",
    )

    before = client.get(f"/api/v1/companies/{cid}/dashboard", headers=_auth_headers(uid))
    assert before.status_code == 200
    card_before = next(c for c in before.json()["priority_events"] if c["id"] == eid)

    with _session(SessionLocal) as s:
        company = s.get(Company, cid)
        assert company
        company.name = "Совершенно Новое Юрлицо"
        s.commit()

    after = client.get(f"/api/v1/companies/{cid}/dashboard", headers=_auth_headers(uid))
    card_after = next(c for c in after.json()["priority_events"] if c["id"] == eid)
    assert card_before["profile_relevance"]["matches"] == card_after["profile_relevance"]["matches"]
    assert after.json()["company_name"] == "Совершенно Новое Юрлицо"


def test_no_duplicate_when_impact_and_profile(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_904", product_marks=[_marks(loan=True)])
        user, company = _user_company(s)
        ev = _rate_event(s)
        s.add(
            EventImpact(
                id=_uid(),
                event_id=ev.id,
                company_id=company.id,
                impact_score=72.0,
                urgency="watch",
                confidence=0.5,
                reason_summary="Тестовый расчёт",
                status="monitor",
                model_version="test",
                computed_at=datetime.now(timezone.utc),
                score_breakdown_json={
                    "assessment_state": "monitoring_only",
                    "score_kind": "event_severity_signal",
                },
                claims_json={},
            )
        )
        s.commit()
        snap_id, cid, uid, eid = snap.id, company.id, user.id, ev.id

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_904",
        company_id=cid,
        linked_by="ops",
    )

    dash = client.get(f"/api/v1/companies/{cid}/dashboard", headers=_auth_headers(uid))
    assert dash.status_code == 200
    ids = [c["id"] for c in dash.json()["priority_events"]]
    assert ids.count(eid) == 1
    card = next(c for c in dash.json()["priority_events"] if c["id"] == eid)
    assert card["score_kind"] == "event_severity_signal"
    assert "case_profile" in card["inclusion_bases"]
    assert card["profile_relevance"]["matched"] is True
    assert card["impact_score"] == 72.0
    assert card["impact_score_available"] is True


def test_get_dashboard_does_not_create_rows(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_905", product_marks=[_marks(deposit=True)])
        user, company = _user_company(s)
        _rate_event(s)
        s.commit()
        snap_id, cid, uid = snap.id, company.id, user.id
        before_i = s.scalar(select(func.count()).select_from(EventImpact)) or 0
        before_s = s.scalar(select(func.count()).select_from(Scenario)) or 0
        before_d = s.scalar(select(func.count()).select_from(Decision)) or 0
        before_links = s.scalar(select(func.count()).select_from(CaseOrgCompanyLink)) or 0

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_905",
        company_id=cid,
        linked_by="ops",
    )

    with _session(SessionLocal) as s:
        after_link_i = s.scalar(select(func.count()).select_from(EventImpact)) or 0
        links = s.scalar(select(func.count()).select_from(CaseOrgCompanyLink)) or 0
    assert after_link_i == before_i
    assert links == before_links + 1

    assert (
        client.get(f"/api/v1/companies/{cid}/dashboard", headers=_auth_headers(uid)).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/companies/{cid}/events", headers=_auth_headers(uid)).status_code
        == 200
    )

    with _session(SessionLocal) as s:
        assert (s.scalar(select(func.count()).select_from(EventImpact)) or 0) == before_i
        assert (s.scalar(select(func.count()).select_from(Scenario)) or 0) == before_s
        assert (s.scalar(select(func.count()).select_from(Decision)) or 0) == before_d


def test_acl_foreign_company(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_906", product_marks=[_marks(loan=True)])
        user_a, company_a = _user_company(s, name="A")
        user_b, _company_b = _user_company(s, name="B")
        _rate_event(s)
        s.commit()
        snap_id, cid_a, uid_b = snap.id, company_a.id, user_b.id

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_906",
        company_id=cid_a,
        linked_by="ops",
    )
    denied = client.get(
        f"/api/v1/companies/{cid_a}/dashboard", headers=_auth_headers(uid_b)
    )
    assert denied.status_code == 403


def test_pagination_no_dupes(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_907", product_marks=[_marks(loan=True)])
        user, company = _user_company(s)
        for i in range(5):
            _rate_event(
                s,
                title=f"[СИНТЕТИЧЕСКИЙ] Ставка кейс {i}",
                event_id=f"evt_page_rate_{i}",
            )
        s.commit()
        snap_id, cid, uid = snap.id, company.id, user.id

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_907",
        company_id=cid,
        linked_by="ops",
    )

    page1 = client.get(
        f"/api/v1/companies/{cid}/events",
        params={"limit": 2},
        headers=_auth_headers(uid),
    )
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1.get("next_cursor")
    page2 = client.get(
        f"/api/v1/companies/{cid}/events",
        params={"limit": 2, "cursor": body1["next_cursor"]},
        headers=_auth_headers(uid),
    )
    ids1 = [i["id"] for i in body1["items"]]
    ids2 = [i["id"] for i in page2.json()["items"]]
    assert not set(ids1) & set(ids2)


def test_assistant_open_without_impact_for_profile_event(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_908", product_marks=[_marks(deposit=True)])
        user, company = _user_company(s)
        ev = _rate_event(s)
        s.commit()
        snap_id, cid, uid, eid = snap.id, company.id, user.id, ev.id

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_908",
        company_id=cid,
        linked_by="ops",
    )

    opened = client.post(
        f"/api/v1/events/{eid}/assistant/conversations",
        headers=_auth_headers(uid),
        json={"company_id": cid},
    )
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body.get("has_impact_calculation") is False or body.get("assessment_state") in {
        "calculation_unavailable",
        "monitoring_only",
        None,
    }


def test_pagination_equal_occurred_at_covers_all(api_harness):
    client, SessionLocal, url = api_harness
    same_ts = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_910", product_marks=[_marks(loan=True)])
        user, company = _user_company(s)
        ids = []
        for i in range(5):
            ev = _rate_event(
                s,
                title=f"[СИНТЕТИЧЕСКИЙ] Equal ts {i}",
                event_id=f"evt_eq_ts_{i:02d}",
            )
            ev.occurred_at = same_ts
            ids.append(ev.id)
        s.commit()
        snap_id, cid, uid = snap.id, company.id, user.id

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_910",
        company_id=cid,
        linked_by="ops",
    )

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params: dict = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        resp = client.get(
            f"/api/v1/companies/{cid}/events",
            params=params,
            headers=_auth_headers(uid),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        page_ids = [it["id"] for it in body["items"]]
        assert len(set(page_ids)) == len(page_ids)
        seen.extend(page_ids)
        cursor = body.get("next_cursor")
        if not cursor:
            break
    assert sorted(seen) == sorted(ids)
    assert len(seen) == len(set(seen))


def test_pagination_equal_impact_scores_covers_all(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_911", product_marks=[_marks(loan=True)])
        user, company = _user_company(s)
        ids = []
        for i in range(5):
            ev = _rate_event(s, title=f"Impact equal {i}", event_id=f"evt_eq_sc_{i:02d}")
            s.add(
                EventImpact(
                    id=_uid(),
                    event_id=ev.id,
                    company_id=company.id,
                    impact_score=55.0,
                    urgency="watch",
                    confidence=0.4,
                    reason_summary="same score",
                    status="monitor",
                    model_version="test",
                    computed_at=datetime.now(timezone.utc),
                    score_breakdown_json={
                        "assessment_state": "monitoring_only",
                        "score_kind": "event_severity_signal",
                    },
                    claims_json={},
                )
            )
            ids.append(ev.id)
        s.commit()
        snap_id, cid, uid = snap.id, company.id, user.id

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_911",
        company_id=cid,
        linked_by="ops",
    )

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params: dict = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        resp = client.get(
            f"/api/v1/companies/{cid}/events",
            params=params,
            headers=_auth_headers(uid),
        )
        assert resp.status_code == 200
        body = resp.json()
        for it in body["items"]:
            if it["id"] in ids:
                assert it["impact_score"] == 55.0
                assert it["impact_score_available"] is True
        seen.extend([it["id"] for it in body["items"] if it["id"] in ids])
        cursor = body.get("next_cursor")
        if not cursor:
            break
    assert sorted(seen) == sorted(ids)
    assert len(seen) == len(set(seen))
    # Cursor must include event_id
    assert body1_cursor_has_event_id(client, cid, uid)


def body1_cursor_has_event_id(client, cid, uid) -> bool:
    r = client.get(
        f"/api/v1/companies/{cid}/events",
        params={"limit": 1},
        headers=_auth_headers(uid),
    )
    cur = r.json().get("next_cursor") or ""
    return cur.count(":") == 2 and bool(cur.split(":")[-1])


def test_invalid_cursor_422(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_912", product_marks=[_marks(loan=True)])
        user, company = _user_company(s)
        _rate_event(s)
        s.commit()
        snap_id, cid, uid = snap.id, company.id, user.id
    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_912",
        company_id=cid,
        linked_by="ops",
    )
    bad = client.get(
        f"/api/v1/companies/{cid}/events",
        params={"limit": 2, "cursor": "not-a-cursor"},
        headers=_auth_headers(uid),
    )
    assert bad.status_code == 422


def test_known_zero_score_remains_zero(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_913", product_marks=[_marks(loan=True)])
        user, company = _user_company(s)
        ev = _rate_event(s, event_id="evt_known_zero")
        s.add(
            EventImpact(
                id=_uid(),
                event_id=ev.id,
                company_id=company.id,
                impact_score=0.0,
                urgency="watch",
                confidence=0.5,
                reason_summary="known zero",
                status="monitor",
                model_version="test",
                computed_at=datetime.now(timezone.utc),
                score_breakdown_json={
                    "assessment_state": "monitoring_only",
                    "score_kind": "event_severity_signal",
                },
                claims_json={},
            )
        )
        s.commit()
        snap_id, cid, uid, eid = snap.id, company.id, user.id, ev.id
    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_913",
        company_id=cid,
        linked_by="ops",
    )
    dash = client.get(f"/api/v1/companies/{cid}/dashboard", headers=_auth_headers(uid))
    card = next(c for c in dash.json()["priority_events"] if c["id"] == eid)
    assert card["impact_score"] == 0.0
    assert card["impact_score_available"] is True
    assert card["score_kind"] != "case_profile_match"


def test_get_with_twin_ready_creates_no_rows(api_harness):
    """GET dashboard/events must not lazy-recompute impacts when twin is ready."""
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_914", product_marks=[_marks(deposit=True)])
        user, company = _user_company(s)
        company.digital_twin_status = "ready"
        company.digital_twin_coverage = 0.5
        s.add(
            CompanyNode(
                id=_uid(),
                company_id=company.id,
                node_type="product",
                name="Line",
                attributes_json={},
            )
        )
        _rate_event(s)
        s.commit()
        snap_id, cid, uid = snap.id, company.id, user.id
        before_i = s.scalar(select(func.count()).select_from(EventImpact)) or 0

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_914",
        company_id=cid,
        linked_by="ops",
    )

    dash = client.get(f"/api/v1/companies/{cid}/dashboard", headers=_auth_headers(uid))
    assert dash.status_code == 200
    # Profile feed still works without impact
    assert any(
        c.get("score_kind") == "case_profile_match" for c in dash.json()["priority_events"]
    )
    assert client.get(
        f"/api/v1/companies/{cid}/events", headers=_auth_headers(uid)
    ).status_code == 200

    with _session(SessionLocal) as s:
        after_i = s.scalar(select(func.count()).select_from(EventImpact)) or 0
    assert after_i == before_i


def test_cursor_tie_break_unit():
    from app.services.case_profile_feed import FeedCursor

    a = FeedEntry(event_id="evt_a", score_kind="case_profile_match", sort_key=1.0, card=None)  # type: ignore[arg-type]
    b = FeedEntry(event_id="evt_b", score_kind="case_profile_match", sort_key=1.0, card=None)  # type: ignore[arg-type]
    cur = FeedCursor(group=2, sort_key=1.0, event_id="evt_a")
    assert entry_after_cursor(a, cur) is False
    assert entry_after_cursor(b, cur) is True
    legacy = FeedCursor(group=2, sort_key=1.0, event_id=None)
    assert entry_after_cursor(a, legacy) is False
    assert entry_after_cursor(b, legacy) is False
    assert parse_feed_cursor("2:1.0:evt_a") == cur
