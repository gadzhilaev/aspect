"""Stage 6.6: user-triggered finance/supply scenarios without LLM."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Company, Decision, Event, EventImpact, Scenario
from app.services.impact import assessment_state_for_impact, recompute_company_impact


RATE_DEBT = {
    "debt_amount": 100_000_000,
    "debt_amount_unit": "RUB",
    "floating_rate_share_percent": 40,
}

FX_PAYMENT = {
    "fx_exposure_amount": 1000,
    "fx_exposure_currency": "CNY",
    "fx_exposure_direction": "payment",
    "fx_quote_currency": "RUB",
    "fx_quote_convention": "quote_per_exposure",
}

CLEAR_RATE = {
    "debt_amount": None,
    "debt_amount_unit": None,
    "floating_rate_share_percent": None,
}

CLEAR_FX = {
    "fx_exposure_amount": None,
    "fx_exposure_currency": None,
    "fx_exposure_direction": None,
    "fx_quote_currency": None,
    "fx_quote_convention": None,
    "fx_rate_from": None,
    "fx_rate_to": None,
}


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


@pytest.fixture
def competition_loop(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPETITION_MODE", "true")
    monkeypatch.setenv("ASSISTANT_PROVIDER", "hackathon")
    monkeypatch.setenv("ASSISTANT_AGENT_LOOP", "true")
    monkeypatch.setenv("HACKATHON_BASE_URL", "https://changellenge.up.railway.app/v1")
    monkeypatch.setenv("HACKATHON_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("HACKATHON_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _block_model_http(monkeypatch: pytest.MonkeyPatch) -> list:
    hits: list[str] = []
    real_request = httpx.Client.request

    def guarded(self, method, url, *args, **kwargs):  # noqa: ANN001
        u = str(url)
        if "changellenge" in u or "openai.com" in u or "sberbank" in u:
            hits.append(u)
            raise AssertionError(f"model HTTP forbidden in 6.6 tests: {u}")
        return real_request(self, method, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "request", guarded)
    return hits


def _create_company(client: TestClient, headers: dict) -> str:
    r = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": f"UT Finance {_uid('co')}", "industry": "manufacturing"},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _patch_finance(client: TestClient, headers: dict, company_id: str, finance: dict) -> None:
    r = client.patch(
        f"/api/v1/companies/{company_id}/finance",
        headers=headers,
        json={"purchase_currencies": ["CNY", "RUB"], "optional_finance": finance},
    )
    assert r.status_code == 200, r.text


def _event(db: Session, *, attrs: dict, currencies: list[str] | None = None) -> Event:
    ev = Event(
        id=_uid("evt"),
        title="Rate event",
        summary="s",
        category="macro",
        event_type="risk",
        severity=40.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        match_countries_json=[],
        match_categories_json=[],
        match_currencies_json=currencies or [],
        match_materials_json=[],
        attributes_json=attrs,
        is_demo=False,
    )
    db.add(ev)
    db.commit()
    return ev


def _prepare_impact(db: Session, event: Event, company_id: str) -> None:
    company = db.get(Company, company_id)
    assert company is not None
    recompute_company_impact(db, event, company)
    db.commit()


def _open_conv(client: TestClient, headers: dict, event_id: str, company_id: str) -> str:
    r = client.post(
        f"/api/v1/events/{event_id}/assistant/conversations",
        headers=headers,
        json={"company_id": company_id},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _compare(
    client: TestClient,
    headers: dict,
    conv_id: str,
    *,
    req_id: str,
    rate_pp: float | None = None,
    fx_pct: float | None = None,
):
    body: dict = {"client_request_id": req_id}
    if rate_pp is not None:
        body["assumed_rate_change_pp"] = rate_pp
    if fx_pct is not None:
        body["assumed_fx_change_percent"] = fx_pct
    return client.post(
        f"/api/v1/assistant/conversations/{conv_id}/compare-scenarios",
        headers=headers,
        json=body,
    )


def test_rate_and_fx_user_path_no_model_http(
    client: TestClient,
    auth_headers: dict,
    db: Session,
    competition_loop,
    monkeypatch: pytest.MonkeyPatch,
):
    hits = _block_model_http(monkeypatch)
    cid = _create_company(client, auth_headers)

    ev_rate = _event(
        db,
        attrs={
            "rate_decision_status": "observed",
            "rate_from": 16.0,
            "rate_to": 17.0,
        },
        currencies=["RUB"],
    )
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, ev_rate, cid)
    impact = db.query(EventImpact).filter_by(company_id=cid, event_id=ev_rate.id).one()
    assert assessment_state_for_impact(db, ev_rate, impact) == "finance_ready"
    conv = _open_conv(client, auth_headers, ev_rate.id, cid)
    r = _compare(client, auth_headers, conv, req_id="rate-1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok", json.dumps(body, ensure_ascii=False)[:2000]
    assert body["decision_created"] is False
    assert body["message"]["role"] == "system"
    assert "Расчёт по вашему запросу" in body["message"]["content"]
    assert body["scenario_ids"]
    assert hits == []

    ev_fx = _event(
        db,
        attrs={
            "fx_rate_decision": {
                "status": "observed",
                "exposure_currency": "CNY",
                "quote_currency": "RUB",
                "quote_convention": "quote_per_exposure",
                "rate_from": 12.0,
                "rate_to": 13.0,
            }
        },
        currencies=["CNY"],
    )
    _patch_finance(client, auth_headers, cid, {**CLEAR_RATE, **FX_PAYMENT})
    _prepare_impact(db, ev_fx, cid)
    conv2 = _open_conv(client, auth_headers, ev_fx.id, cid)
    r2 = _compare(client, auth_headers, conv2, req_id="fx-1")
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "ok"
    assert r2.json()["scenario_ids"]
    assert hits == []


def test_acl_foreign_conversation(
    client: TestClient,
    auth_headers: dict,
    db: Session,
    competition_loop,
    monkeypatch: pytest.MonkeyPatch,
):
    _block_model_http(monkeypatch)
    cid = _create_company(client, auth_headers)
    ev = _event(
        db,
        attrs={"rate_decision_status": "observed", "rate_from": 16.0, "rate_to": 17.0},
        currencies=["RUB"],
    )
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, ev, cid)
    conv = _open_conv(client, auth_headers, ev.id, cid)

    # Second user via register
    email = f"{_uid('u')}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "DemoKontur1!", "display_name": "Other"},
    )
    assert reg.status_code in {200, 201}, reg.text
    code = (reg.json().get("details") or {}).get("demo_code") or "000000"
    client.post("/api/v1/auth/verify-email", json={"email": email, "code": code})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "DemoKontur1!"}
    )
    assert login.status_code == 200, login.text
    h2 = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = _compare(client, h2, conv, req_id="acl-x")
    assert r.status_code in {403, 404}


def test_no_usable_impact(
    client: TestClient,
    auth_headers: dict,
    db: Session,
    competition_loop,
    monkeypatch: pytest.MonkeyPatch,
):
    _block_model_http(monkeypatch)
    cid = _create_company(client, auth_headers)
    ev = _event(
        db,
        attrs={"rate_decision_status": "observed", "rate_from": 16.0, "rate_to": 17.0},
        currencies=["RUB"],
    )
    conv = _open_conv(client, auth_headers, ev.id, cid)
    r = _compare(client, auth_headers, conv, req_id="no-impact")
    assert r.status_code == 200, r.text
    assert r.json()["status"] in {"missing_data", "unavailable"}
    assert r.json()["scenario_ids"] == []


def test_profile_ready_without_basis(
    client: TestClient,
    auth_headers: dict,
    db: Session,
    competition_loop,
    monkeypatch: pytest.MonkeyPatch,
):
    _block_model_http(monkeypatch)
    cid = _create_company(client, auth_headers)
    ev = _event(db, attrs={})
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, ev, cid)
    conv = _open_conv(client, auth_headers, ev.id, cid)
    r = _compare(client, auth_headers, conv, req_id="no-basis")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision_created"] is False
    if body["status"] == "ok":
        # Should not invent money without basis/what-if
        scenarios = body["result"].get("scenarios") or []
        assert scenarios == [] or body["result"].get("status") == "unavailable"
    else:
        assert body["scenario_ids"] == []


def test_assumed_what_if_not_mixed_as_observed(
    client: TestClient,
    auth_headers: dict,
    db: Session,
    competition_loop,
    monkeypatch: pytest.MonkeyPatch,
):
    _block_model_http(monkeypatch)
    cid = _create_company(client, auth_headers)
    ev = _event(
        db,
        attrs={"rate_decision_status": "observed", "rate_from": 16.0, "rate_to": 16.0},
        currencies=["RUB"],
    )
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, ev, cid)
    conv = _open_conv(client, auth_headers, ev.id, cid)
    r = _compare(client, auth_headers, conv, req_id="assumed-1", rate_pp=1.5)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"
    scenarios = r.json()["result"].get("scenarios") or []
    assert scenarios
    assumed_seen = False
    for s in scenarios:
        pres = s.get("presentation") or {}
        basis = s.get("rate_change_basis") or pres.get("basis")
        if basis == "assumed" or pres.get("what_if_line"):
            assumed_seen = True
        if basis == "observed":
            # Hold observation may coexist; what-if must not be labeled as the only observed money
            assert s.get("kind") != "baseline" or float(s.get("extra_annual_cost") or 0) == 0
    assert assumed_seen


def test_idempotent_same_request_id(
    client: TestClient,
    auth_headers: dict,
    db: Session,
    competition_loop,
    monkeypatch: pytest.MonkeyPatch,
):
    _block_model_http(monkeypatch)
    cid = _create_company(client, auth_headers)
    ev = _event(
        db,
        attrs={"rate_decision_status": "observed", "rate_from": 16.0, "rate_to": 17.0},
        currencies=["RUB"],
    )
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, ev, cid)
    conv = _open_conv(client, auth_headers, ev.id, cid)
    a = _compare(client, auth_headers, conv, req_id="idem-1")
    b = _compare(client, auth_headers, conv, req_id="idem-1")
    assert a.status_code == 200 and b.status_code == 200
    assert b.json()["reused"] is True
    assert a.json()["scenario_ids"] == b.json()["scenario_ids"]
    n = (
        db.query(Scenario)
        .filter(Scenario.company_id == cid, Scenario.event_id == ev.id)
        .count()
    )
    assert n == len(a.json()["scenario_ids"])


def test_conflict_same_id_different_params(
    client: TestClient,
    auth_headers: dict,
    db: Session,
    competition_loop,
    monkeypatch: pytest.MonkeyPatch,
):
    _block_model_http(monkeypatch)
    cid = _create_company(client, auth_headers)
    ev = _event(
        db,
        attrs={"rate_decision_status": "observed", "rate_from": 16.0, "rate_to": 16.0},
        currencies=["RUB"],
    )
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, ev, cid)
    conv = _open_conv(client, auth_headers, ev.id, cid)
    a = _compare(client, auth_headers, conv, req_id="conflict-1", rate_pp=1.0)
    assert a.status_code == 200, a.text
    b = _compare(client, auth_headers, conv, req_id="conflict-1", rate_pp=2.0)
    assert b.status_code == 409
    assert b.json()["error"]["code"] == "USER_COMPARE_REQUEST_CONFLICT"


def test_decision_only_after_user_confirm(
    client: TestClient,
    auth_headers: dict,
    db: Session,
    competition_loop,
    monkeypatch: pytest.MonkeyPatch,
):
    _block_model_http(monkeypatch)
    cid = _create_company(client, auth_headers)
    ev = _event(
        db,
        attrs={"rate_decision_status": "observed", "rate_from": 16.0, "rate_to": 17.0},
        currencies=["RUB"],
    )
    _patch_finance(client, auth_headers, cid, {**RATE_DEBT, **CLEAR_FX})
    _prepare_impact(db, ev, cid)
    conv = _open_conv(client, auth_headers, ev.id, cid)
    r = _compare(client, auth_headers, conv, req_id="dec-1")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok", r.json()
    assert r.json()["decision_created"] is False
    scenarios = r.json()["result"]["scenarios"]
    assert all(s.get("action_id") != "reduce_fx_exposure" for s in scenarios)
    baseline = next(s for s in scenarios if s.get("kind") == "baseline")
    before = db.query(Decision).count()
    sid = baseline["scenario_id"]
    draft = client.post(
        f"/api/v1/assistant/conversations/{conv}/draft-decision",
        headers=auth_headers,
        json={"scenario_id": sid, "confirm": False, "client_request_id": "d1"},
    )
    assert draft.status_code == 200
    assert draft.json()["status"] == "draft"
    assert "Черновик" in (draft.json()["draft"].get("note") or "")
    assert db.query(Decision).count() == before
    conf = client.post(
        f"/api/v1/assistant/conversations/{conv}/draft-decision",
        headers=auth_headers,
        json={"scenario_id": sid, "confirm": True, "client_request_id": "d1-confirm"},
    )
    assert conf.status_code == 200, conf.text
    assert conf.json()["status"] == "confirmed"
    assert "Решение подтверждено" in (conf.json()["draft"].get("note") or "")
    assert "Черновик" not in (conf.json()["draft"].get("note") or "")
    msg_blocks = conf.json()["message"]["blocks"]
    plan = next(b for b in msg_blocks if b["type"] == "action_plan_draft")
    assert plan["title"] == "Решение сохранено"
    assert plan["data"]["status"] == "confirmed"
    did = conf.json()["decision_id"]
    assert did
    assert db.query(Decision).count() == before + 1
    detail = client.get(f"/api/v1/decisions/{did}", headers=auth_headers)
    assert detail.status_code == 200
    # Title follows selected scenario label (baseline), not FX hypothesis.
    assert "валютн" not in detail.json()["title"].lower()
