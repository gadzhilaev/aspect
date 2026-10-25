"""External company registry lookup by INN — validation, states, confirm, ACL.

Temp SQLite (conftest), DaData upstream mocked via httpx.MockTransport. No live
calls, no LLM. A real live lookup is out of scope here (see docs).
"""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Company, CompanyMembership, EventImpact
from app.services.company_registry import provider
from app.services.company_registry.inn import InnValidationError, normalize_inn

# Valid sample INNs (real control digits).
INN_LEGAL = "7707083893"       # 10-digit legal entity
INN_INDIVIDUAL = "500100732259"  # 12-digit individual
WH = provider.SOURCE_INFO

_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)


def make_legal_inn(prefix9: str) -> str:
    """Build a checksum-valid 10-digit INN from a 9-digit prefix (test isolation)."""
    assert len(prefix9) == 9 and prefix9.isdigit()
    ctrl = (sum(int(prefix9[i]) * _W10[i] for i in range(9)) % 11) % 10
    return prefix9 + str(ctrl)


@pytest.fixture(autouse=True)
def _registry_env(monkeypatch):
    monkeypatch.setenv("DADATA_API_KEY", "test-registry-key")
    from app.core.config import get_settings

    get_settings.cache_clear()
    provider.reset_state()
    yield
    monkeypatch.delenv("DADATA_API_KEY", raising=False)
    get_settings.cache_clear()
    provider.reset_state()


def _legal_suggestion(inn=INN_LEGAL, status="ACTIVE", branch="MAIN", kpp="770701001"):
    return {
        "value": 'ООО "ПРИМЕР"',
        "data": {
            "inn": inn,
            "kpp": kpp,
            "ogrn": "1027700132195",
            "ogrn_date": 1033600000000,
            "type": "LEGAL",
            "branch_type": branch,
            "name": {
                "full_with_opf": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРИМЕР"',
                "short_with_opf": 'ООО "ПРИМЕР"',
            },
            "okved": "26.30",
            "okved_type": "2014",
            "okveds": [
                {"main": True, "code": "26.30", "name": "Производство коммуникационного оборудования"},
            ],
            "state": {"status": status, "actuality_date": 1771891200000, "registration_date": 1033600000000},
            "address": {
                "value": "г Москва, ул Тверская, д 1",
                "data": {"region_with_type": "г Москва", "region": "Москва"},
            },
        },
    }


def _individual_suggestion(inn=INN_INDIVIDUAL):
    return {
        "value": "ИП Иванов Иван Иванович",
        "data": {
            "inn": inn,
            "kpp": None,
            "ogrn": "304500116000157",
            "ogrn_date": 1072915200000,
            "type": "INDIVIDUAL",
            "branch_type": "MAIN",
            "name": {"full_with_opf": None, "short_with_opf": None},
            "fio": {"surname": "Иванов", "name": "Иван", "patronymic": "Иванович"},
            "okved": "47.91",
            "okved_type": "2014",
            "okveds": [{"main": True, "code": "47.91", "name": "Торговля розничная по почте"}],
            "state": {"status": "ACTIVE", "actuality_date": 1771891200000},
            "address": {"value": "г Казань", "data": {"region_with_type": "Респ Татарстан"}},
        },
    }


class _Upstream:
    """Configurable mocked DaData endpoint."""

    def __init__(self):
        self.mode = "legal"
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        try:
            q = str(json.loads(request.content.decode("utf-8")).get("query") or "").strip()
        except Exception:
            q = INN_LEGAL
        path = str(request.url)
        if "okved2" in path:
            # Enrichment of okved_name when party omitted okveds[].
            return httpx.Response(
                200,
                json={
                    "suggestions": [
                        {
                            "value": "Производство коммуникационного оборудования",
                            "data": {"kod": q, "name": "Производство коммуникационного оборудования"},
                        }
                    ]
                },
            )
        if self.mode == "timeout":
            raise httpx.ReadTimeout("mock", request=request)
        if self.mode == "network":
            raise httpx.ConnectError("mock", request=request)
        if self.mode == "auth":
            return httpx.Response(403, json={"message": "forbidden"})
        if self.mode == "rate":
            return httpx.Response(429, json={"message": "rate"})
        if self.mode == "server":
            return httpx.Response(502, text="bad gateway")
        if self.mode == "malformed":
            return httpx.Response(200, text="not-json-at-all")
        if self.mode == "redirect":
            return httpx.Response(302, headers={"Location": "https://evil.example.com"})
        if self.mode == "empty":
            return httpx.Response(200, json={"suggestions": []})
        if self.mode == "individual":
            return httpx.Response(200, json={"suggestions": [_individual_suggestion(inn=q or INN_INDIVIDUAL)]})
        if self.mode == "branches":
            return httpx.Response(200, json={"suggestions": [
                _legal_suggestion(inn=q, branch="MAIN", kpp="770701001"),
                _legal_suggestion(inn=q, branch="BRANCH", kpp="540602001"),
            ]})
        if self.mode == "liquidated":
            return httpx.Response(200, json={"suggestions": [_legal_suggestion(inn=q, status="LIQUIDATED")]})
        if self.mode == "nullable":
            return httpx.Response(200, json={"suggestions": [{"value": "X", "data": {"inn": q, "type": "LEGAL", "name": {}, "state": {}}}]})
        if self.mode == "okved_code_only":
            sug = _legal_suggestion(inn=q)
            sug["data"].pop("okveds", None)
            sug["data"]["address"] = {
                "value": "г Махачкала, ул Учительская, д 13Б",
                "data": {
                    "region_with_type": "Респ Дагестан",
                    "region": "Дагестан",
                    "city": "Махачкала",
                    "city_with_type": "г Махачкала",
                },
            }
            return httpx.Response(200, json={"suggestions": [sug]})
        return httpx.Response(200, json={"suggestions": [_legal_suggestion(inn=q)]})


@pytest.fixture
def upstream(monkeypatch):
    up = _Upstream()
    real_client = httpx.Client

    def factory(*a, **kw):
        kw.pop("transport", None)
        return real_client(*a, transport=httpx.MockTransport(up.handler), **kw)

    monkeypatch.setattr(provider.httpx, "Client", factory)
    return up


def _lookup(client: TestClient, headers, inn):
    return client.post("/api/v1/company-registry/lookup", json={"inn": inn}, headers=headers)


# --- INN validation (unit) --------------------------------------------------

@pytest.mark.parametrize("inn", [INN_LEGAL, INN_INDIVIDUAL, "0040000007"])
def test_valid_inn_passes(inn):
    out = normalize_inn(inn)
    assert out.inn == inn
    assert out.length in (10, 12)


def test_leading_zero_preserved():
    assert normalize_inn("0040000007").inn == "0040000007"


def test_outer_whitespace_trimmed():
    assert normalize_inn("  7707083893  ").inn == "7707083893"


@pytest.mark.parametrize(
    "inn,reason",
    [
        ("", "empty"),
        ("   ", "empty"),
        ("77A7083893", "non_digit"),
        ("7707 083893", "non_digit"),
        ("12345", "bad_length"),
        ("12345678901", "bad_length"),  # 11 digits
        ("7707083894", "bad_checksum"),  # wrong control digit
        ("500100732250", "bad_checksum"),
    ],
)
def test_invalid_inn_rejected(inn, reason):
    with pytest.raises(InnValidationError) as exc:
        normalize_inn(inn)
    assert exc.value.reason == reason


def test_12_digits_is_individual_kind_not_ie_claim():
    out = normalize_inn(INN_INDIVIDUAL)
    assert out.inn_kind == "individual"  # syntactic only


# --- lookup endpoint states -------------------------------------------------

def test_lookup_requires_auth(client: TestClient):
    r = client.post("/api/v1/company-registry/lookup", json={"inn": INN_LEGAL})
    assert r.status_code == 401


def test_lookup_invalid_inn_400(client: TestClient, auth_headers):
    r = _lookup(client, auth_headers, "7707083894")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "INVALID_INN"
    assert body["error"]["details"][0]["reason"] == "bad_checksum"


def test_lookup_legal_ok(client: TestClient, auth_headers, upstream):
    upstream.mode = "legal"
    r = _lookup(client, auth_headers, "  7707083893 ")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["query_inn"] == INN_LEGAL
    assert body["lookup_id"]
    assert body["candidate_count"] == 1
    cand = body["candidates"][0]
    assert cand["org_type"] == "legal"
    assert cand["inn"] == INN_LEGAL
    assert cand["kpp"] == "770701001"
    assert cand["ogrn"] == "1027700132195"
    assert cand["ogrn_date"]
    assert cand["region"] == "г Москва"
    assert cand["okved"] == "26.30"
    assert cand["okved_name"]
    assert cand["status"] == "active"
    assert cand["is_active"] is True
    assert cand["branch_type"] == "main"
    assert cand["suggested_industry"] == "electronics"
    # source is named honestly (intermediary, not direct FNS)
    assert "ФНС" in body["source"]["title"]
    assert "не прямой запрос" in body["source"]["note"].lower() or "посредник" in body["source"]["note"].lower()
    # No manager/founder personal data leaks
    assert "management" not in json.dumps(body, ensure_ascii=False)
    # okveds[] present → no extra okved2 call
    assert upstream.calls == 1


def test_lookup_city_and_okved_enrichment(client: TestClient, auth_headers, upstream):
    """Party often has city + okved code but no okveds[] names — enrich via okved2."""
    upstream.mode = "okved_code_only"
    cand = _lookup(client, auth_headers, INN_LEGAL).json()["candidates"][0]
    assert cand["city"] == "Махачкала"
    assert cand["region"] == "Респ Дагестан"
    assert cand["okved"] == "26.30"
    assert cand["okved_name"] == "Производство коммуникационного оборудования"
    assert upstream.calls == 2  # party + okved2


def test_lookup_individual(client: TestClient, auth_headers, upstream):
    upstream.mode = "individual"
    r = _lookup(client, auth_headers, INN_INDIVIDUAL)
    cand = r.json()["candidates"][0]
    assert cand["org_type"] == "individual"
    assert cand["kpp"] is None


def test_lookup_branches_multiple(client: TestClient, auth_headers, upstream):
    upstream.mode = "branches"
    body = _lookup(client, auth_headers, INN_LEGAL).json()
    assert body["candidate_count"] == 2
    kinds = {c["branch_type"] for c in body["candidates"]}
    assert kinds == {"main", "branch"}


def test_lookup_liquidated_status(client: TestClient, auth_headers, upstream):
    upstream.mode = "liquidated"
    cand = _lookup(client, auth_headers, INN_LEGAL).json()["candidates"][0]
    assert cand["status"] == "liquidated"
    assert cand["is_active"] is False


def test_lookup_nullable_fields(client: TestClient, auth_headers, upstream):
    upstream.mode = "nullable"
    cand = _lookup(client, auth_headers, INN_LEGAL).json()["candidates"][0]
    assert cand["kpp"] is None
    assert cand["ogrn"] is None
    assert cand["region"] is None
    assert cand["status"] == "unknown"


def test_lookup_not_found(client: TestClient, auth_headers, upstream):
    upstream.mode = "empty"
    body = _lookup(client, auth_headers, INN_LEGAL).json()
    assert body["status"] == "not_found"
    assert body["lookup_id"] is None


def test_lookup_not_configured_without_key(client: TestClient, auth_headers, monkeypatch, upstream):
    monkeypatch.delenv("DADATA_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    body = _lookup(client, auth_headers, INN_LEGAL).json()
    assert body["status"] == "not_configured"
    assert upstream.calls == 0  # no demo fallback, no upstream call


@pytest.mark.parametrize(
    "mode,status,code",
    [
        ("timeout", 504, "REGISTRY_TIMEOUT"),
        ("network", 503, "REGISTRY_UNAVAILABLE"),
        ("server", 503, "REGISTRY_UNAVAILABLE"),
        ("auth", 503, "REGISTRY_AUTH_ERROR"),
        ("rate", 503, "REGISTRY_UPSTREAM_RATE_LIMITED"),
        ("malformed", 502, "REGISTRY_BAD_RESPONSE"),
        ("redirect", 502, "REGISTRY_BAD_RESPONSE"),
    ],
)
def test_lookup_upstream_failures(client, auth_headers, upstream, mode, status, code):
    upstream.mode = mode
    r = _lookup(client, auth_headers, INN_LEGAL)
    assert r.status_code == status
    assert r.json()["error"]["code"] == code


def test_upstream_auth_error_does_not_logout_user(client, auth_headers, upstream):
    upstream.mode = "auth"
    r = _lookup(client, auth_headers, INN_LEGAL)
    assert r.status_code != 401  # our session stays valid


def test_user_rate_limit(client, auth_headers, upstream, monkeypatch):
    monkeypatch.setenv("COMPANY_REGISTRY_USER_RATE_PER_MINUTE", "3")
    from app.core.config import get_settings

    get_settings.cache_clear()
    provider.reset_state()
    upstream.mode = "legal"
    seen = [_lookup(client, auth_headers, INN_LEGAL).status_code for _ in range(4)]
    assert seen[:3] == [200, 200, 200]
    assert seen[3] == 429


def test_lookup_does_not_create_business_entities(client, auth_headers, upstream, db: Session):
    upstream.mode = "legal"
    companies_before = db.query(Company).count()
    impacts_before = db.query(EventImpact).count()
    _lookup(client, auth_headers, INN_LEGAL)
    db.expire_all()
    assert db.query(Company).count() == companies_before
    assert db.query(EventImpact).count() == impacts_before


# --- confirm flow -----------------------------------------------------------

def test_confirm_creates_own_profile(client, auth_headers, upstream, db: Session):
    upstream.mode = "legal"
    look = _lookup(client, auth_headers, INN_LEGAL).json()
    r = client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": look["lookup_id"], "candidate_id": "0"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True
    assert body["opened_existing"] is False
    assert body["company"]["tax_id"] == INN_LEGAL
    assert body["company"]["name"] == 'ООО "ПРИМЕР"'
    assert "tax_id" in body["applied_fields"]
    # industry not auto-applied (OKVED ≠ industry); offered as suggestion
    assert body["company"]["industry"] is None
    assert body["suggested_industry"] == "electronics"
    # provenance recorded
    cid = body["company"]["id"]
    prof = client.get(f"/api/v1/companies/{cid}/profile", headers=auth_headers).json()
    prov = prof["settings"]["preferences"]["registry_provenance"]
    assert prov["source"]["provider"] == "dadata"
    assert prov["fields_from_registry"]["tax_id"] == INN_LEGAL
    assert prov["verified_scope"] == "public_requisites"


def test_confirm_expired_lookup(client, auth_headers, upstream, monkeypatch):
    monkeypatch.setenv("COMPANY_REGISTRY_LOOKUP_TTL_SECONDS", "0")
    from app.core.config import get_settings

    get_settings.cache_clear()
    upstream.mode = "legal"
    look = _lookup(client, auth_headers, INN_LEGAL).json()
    r = client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": look["lookup_id"], "candidate_id": "0"},
        headers=auth_headers,
    )
    assert r.status_code == 410
    assert r.json()["error"]["code"] == "LOOKUP_EXPIRED"


def test_confirm_forged_lookup_id(client, auth_headers):
    r = client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": f"forged-{uuid4()}", "candidate_id": "0"},
        headers=auth_headers,
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "LOOKUP_NOT_FOUND"


def test_confirm_bad_candidate_id(client, auth_headers, upstream):
    upstream.mode = "legal"
    look = _lookup(client, auth_headers, INN_LEGAL).json()
    r = client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": look["lookup_id"], "candidate_id": "99"},
        headers=auth_headers,
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "CANDIDATE_NOT_FOUND"


def test_confirm_dedupes_own_company(client, auth_headers, upstream):
    upstream.mode = "legal"
    inn = make_legal_inn("700000010")
    first = client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": _lookup(client, auth_headers, inn).json()["lookup_id"], "candidate_id": "0"},
        headers=auth_headers,
    ).json()
    assert first["created"] is True
    second = client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": _lookup(client, auth_headers, inn).json()["lookup_id"], "candidate_id": "0"},
        headers=auth_headers,
    ).json()
    assert second["created"] is False
    assert second["opened_existing"] is True
    assert second["company"]["id"] == first["company"]["id"]


def _register_second_user(client: TestClient) -> dict:
    email = f"second-{uuid4().hex[:8]}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": "Second-pass-1", "display_name": "Second"})
    client.post("/api/v1/auth/verify-email", json={"email": email, "code": "123456"})
    tok = client.post("/api/v1/auth/login", json={"email": email, "password": "Second-pass-1"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_inn_does_not_grant_access_to_other_users_company(client, auth_headers, upstream, db: Session):
    upstream.mode = "legal"
    inn = make_legal_inn("700000030")
    owner = client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": _lookup(client, auth_headers, inn).json()["lookup_id"], "candidate_id": "0"},
        headers=auth_headers,
    ).json()
    owner_cid = owner["company"]["id"]

    other = _register_second_user(client)
    confirmed = client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": _lookup(client, other, inn).json()["lookup_id"], "candidate_id": "0"},
        headers=other,
    ).json()
    # Second user gets a NEW own profile, never the first user's company.
    assert confirmed["created"] is True
    assert confirmed["company"]["id"] != owner_cid
    # And has no membership/access to the owner's company.
    prof = client.get(f"/api/v1/companies/{owner_cid}/profile", headers=other)
    assert prof.status_code == 403


def test_confirm_no_case_org_link_created(client, auth_headers, upstream, db: Session):
    from app.models import CaseOrgCompanyLink

    upstream.mode = "legal"
    before = db.query(CaseOrgCompanyLink).count()
    client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": _lookup(client, auth_headers, INN_LEGAL).json()["lookup_id"], "candidate_id": "0"},
        headers=auth_headers,
    )
    db.expire_all()
    assert db.query(CaseOrgCompanyLink).count() == before


def test_manual_edit_drops_registry_origin(client, auth_headers, upstream):
    upstream.mode = "legal"
    inn = make_legal_inn("700000020")
    created = client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": _lookup(client, auth_headers, inn).json()["lookup_id"], "candidate_id": "0"},
        headers=auth_headers,
    ).json()
    assert created["created"] is True
    cid = created["company"]["id"]
    r = client.patch(f"/api/v1/companies/{cid}", json={"name": "Моё название"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    prof = client.get(f"/api/v1/companies/{cid}/profile", headers=auth_headers).json()
    prov = prof["settings"]["preferences"]["registry_provenance"]
    assert "name" in prov["fields_overridden_manually"]
    assert "name" not in prov["fields_from_registry"]
    # tax_id still from registry (not edited)
    assert prov["fields_from_registry"]["tax_id"] == inn


# --- existing behaviour must keep working -----------------------------------

def test_manual_company_create_still_works(client, auth_headers):
    r = client.post(
        "/api/v1/companies",
        json={"name": "Ручная компания", "industry": "equipment"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Ручная компания"


def test_search_only_returns_own_companies(client, auth_headers, upstream):
    upstream.mode = "legal"
    inn = make_legal_inn("700000040")
    # Owner creates a company via confirm.
    client.post(
        "/api/v1/company-registry/confirm",
        json={"lookup_id": _lookup(client, auth_headers, inn).json()["lookup_id"], "candidate_id": "0"},
        headers=auth_headers,
    )
    other = _register_second_user(client)
    # Second user searches by the owner's INN — must not see owner's company.
    res = client.get(f"/api/v1/companies/search?q={inn}", headers=other)
    assert res.status_code == 200
    assert all(c["tax_id"] != inn for c in res.json())
