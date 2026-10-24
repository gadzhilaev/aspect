"""HTTP API: additive case_context on GET /companies/{id}/context (temp SQLite)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import create_app
from app.models import (
    CaseActiveSnapshot,
    CaseImportFile,
    CaseImportRun,
    CaseOrg,
    CaseOrgCatalogRow,
    CaseOrgCompanyLink,
    CaseOrgFieldResolution,
    CaseOrgProductMark,
    CaseSnapshot,
    Company,
    CompanyMembership,
    User,
)
from app.services.case_data.activate_snapshot import run_activation
from app.services.case_data.link_org_company import run_link
from app.services.case_data.resolution import PRODUCT_CODES, resolve_catalog_variants

ROOT = Path(__file__).resolve().parents[1]
SLOT = "competition_default"
CATALOG_FILE = "df_Uid_data_hack.csv"


def _uid() -> str:
    return str(uuid.uuid4())


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture
def api_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "case_ctx_api.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "case-context-api-test-secret")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CASE_CONTEXT_SLOT_KEY", SLOT)
    get_settings.cache_clear()

    command.upgrade(_alembic_config(), "head")

    SessionLocal = sessionmaker(bind=engine, autoflush=False)

    def _override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    try:
        yield client, SessionLocal, url
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def _session(SessionLocal) -> Session:
    return SessionLocal()


def _seed_ready(session: Session, *, slot: str, label: str, seq: int) -> CaseSnapshot:
    snap_id, run_id = _uid(), _uid()
    snap = CaseSnapshot(
        id=snap_id,
        slot_key=slot,
        version_label=label,
        version_seq=seq,
        status="building",
        import_run_id=None,
    )
    session.add(snap)
    session.flush()
    run = CaseImportRun(
        id=run_id,
        snapshot_id=snap_id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    snap.import_run_id = run_id
    for name in (CATALOG_FILE, "payments.csv", "links.csv"):
        session.add(
            CaseImportFile(
                id=_uid(),
                import_run_id=run_id,
                source_file=name,
                content_sha256="c" * 64,
                byte_size=10,
                row_count_loaded=1,
                status="completed",
            )
        )
    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    snap.status = "ready"
    snap.built_at = datetime.now(timezone.utc)
    snap.validation_report_json = {
        "ready_at": datetime.now(timezone.utc).isoformat(),
        "final_checks": {
            "companies": {"catalog_rows": 1},
            "payments": {"rows": 1},
            "person_links": {"rows": 1},
        },
        "manifest": [
            {"role": "companies", "source_file": CATALOG_FILE, "record_count": 1},
            {"role": "payments", "source_file": "payments.csv", "record_count": 1},
            {"role": "person_links", "source_file": "links.csv", "record_count": 1},
        ],
    }
    session.flush()
    return snap


def _add_org(
    session: Session,
    snap: CaseSnapshot,
    *,
    external_uid: str,
    variants: list[dict] | None = None,
    product_marks: list[dict[str, bool | None]] | None = None,
    orphan: bool = False,
) -> CaseOrg:
    assert snap.import_run_id
    org = CaseOrg(
        id=_uid(),
        snapshot_id=snap.id,
        external_uid=external_uid,
        has_catalog_profile=not orphan,
        profile_resolution="absent" if orphan else "single",
    )
    session.add(org)
    session.flush()
    if orphan:
        return org

    defaults = {
        "org_type": "ООО",
        "okfs_name": None,
        "company_age_years_gradation": "5-10",
        "eco_mark_label": None,
        "mainokved_code": "46.90",
        "mainokved_name": "Торговля",
        "negative_mark": False,
        "workers_fns_gradation": "15-100",
        "workers_spark_gradation": None,
        "cl_type": None,
        "fts_flag": True,
        "fts_country_name_raw": "Китай",
        "factoring_mark": True,
        "revenue_raw": "1234567890.1",
        "group_external_id": "G_1",
        "city": "Москва",
        "region": "Москва",
    }
    rows_data = variants if variants is not None else [defaults]
    marks_data = product_marks or [
        {c: (True if c == "RKO" else False) for c in PRODUCT_CODES} for _ in rows_data
    ]
    max_row = (
        session.scalar(
            select(func.max(CaseOrgCatalogRow.source_row_number)).where(
                CaseOrgCatalogRow.import_run_id == snap.import_run_id,
                CaseOrgCatalogRow.source_file == CATALOG_FILE,
            )
        )
        or 0
    )
    merged_rows: list[dict] = []
    for i, row in enumerate(rows_data):
        merged = {**defaults, **row}
        merged_rows.append(merged)
        cid = _uid()
        session.add(
            CaseOrgCatalogRow(
                id=cid,
                snapshot_id=snap.id,
                import_run_id=snap.import_run_id,
                case_org_id=org.id,
                source_file=CATALOG_FILE,
                source_row_number=max_row + i + 1,
                row_content_sha256=f"{(max_row + i):064d}"[:64],
                org_type=merged.get("org_type"),
                okfs_name=merged.get("okfs_name"),
                company_age_years_gradation=merged.get("company_age_years_gradation"),
                eco_mark_label=merged.get("eco_mark_label"),
                mainokved_code=merged.get("mainokved_code"),
                mainokved_name=merged.get("mainokved_name"),
                negative_mark=merged.get("negative_mark"),
                workers_fns_gradation=merged.get("workers_fns_gradation"),
                workers_spark_gradation=merged.get("workers_spark_gradation"),
                cl_type=merged.get("cl_type"),
                fts_flag=merged.get("fts_flag"),
                fts_country_name_raw=merged.get("fts_country_name_raw"),
                factoring_mark=merged.get("factoring_mark"),
                revenue_raw=str(merged.get("revenue_raw") or "0.0"),
                revenue_amount=None,
                revenue_parse_status="ok",
                group_external_id=merged.get("group_external_id"),
                city=merged.get("city"),
                region=merged.get("region"),
                raw_json={"secret": "must-not-leak", "path": "C:/secret/path.csv"},
            )
        )
        session.flush()
        for code, mark in marks_data[i].items():
            session.add(
                CaseOrgProductMark(
                    id=_uid(),
                    snapshot_id=snap.id,
                    catalog_row_id=cid,
                    product_code=code,
                    mark=mark,
                )
            )
    resolved = resolve_catalog_variants(merged_rows, product_marks_by_row=marks_data)
    org.profile_resolution = resolved["profile_resolution"]
    session.add(
        CaseOrgFieldResolution(
            id=_uid(),
            snapshot_id=snap.id,
            case_org_id=org.id,
            import_run_id=snap.import_run_id,
            consensus_json=resolved["consensus_json"],
            conflict_json=resolved["conflict_json"],
            absent_json=resolved["absent_json"],
            variant_count=resolved["variant_count"],
            confirmed_field_count=resolved["confirmed_field_count"],
        )
    )
    session.flush()
    return org


def _user_company(session: Session, *, name: str = "API Co", industry: str = "electronics"):
    user = User(
        id=_uid(),
        email=f"{_uid()[:8]}@api.test",
        password_hash=hash_password("ApiTest1!"),
        display_name="API User",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    company = Company(
        id=_uid(),
        name=name,
        industry=industry,
        size_band="medium",
        hq_region="ManualHQ",
        profile_status="ready",
        digital_twin_status="built",
        digital_twin_coverage=0.4,
        is_demo=False,
        created_by=user.id,
    )
    session.add(company)
    session.flush()
    session.add(
        CompanyMembership(id=_uid(), user_id=user.id, company_id=company.id, role="owner")
    )
    session.flush()
    return user, company


def _auth_headers(user_id: str) -> dict[str, str]:
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _activate(url: str, snap_id: str, *, expected: str | None = None, expect_no_active: bool = True):
    return run_activation(
        database_url=url,
        slot_key=SLOT,
        snapshot_id=snap_id,
        expect_no_active=expect_no_active,
        expected_active_snapshot_id=expected,
    )


def test_legacy_fields_preserved_and_not_linked(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_100")
        user, company = _user_company(s, industry="electronics")
        s.commit()
        snap_id, company_id, user_id = snap.id, company.id, user.id
        name = company.name

    _activate(url, snap_id)

    resp = client.get(
        f"/api/v1/companies/{company_id}/context",
        headers=_auth_headers(user_id),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["company_name"] == name
    assert body["profile_ready"] is True
    assert body["hq_region"] == "ManualHQ"
    assert body["size_label"]  # mapped from medium
    # Manual industry not replaced by case OKVED
    assert body["industry_label"] == "Электроника"
    assert "46.90" not in (body.get("industry_label") or "")
    assert body["coverage_total"] >= 1
    cc = body["case_context"]
    assert cc["status"] == "not_linked"
    assert cc["profile"] is None
    assert "привязана" in cc["explanation"].lower() or "не привязана" in cc["explanation"].lower()


def test_integration_not_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "no_slot.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SECRET_KEY", "case-context-api-test-secret")
    monkeypatch.delenv("CASE_CONTEXT_SLOT_KEY", raising=False)
    monkeypatch.setenv("CASE_CONTEXT_SLOT_KEY", "")
    get_settings.cache_clear()
    command.upgrade(_alembic_config(), "head")
    SessionLocal = sessionmaker(bind=engine, autoflush=False)

    def _override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as client:
        with SessionLocal() as s:
            user, company = _user_company(s)
            s.commit()
            company_id, user_id = company.id, user.id
        resp = client.get(
            f"/api/v1/companies/{company_id}/context",
            headers=_auth_headers(user_id),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["company_name"]
        assert body["case_context"]["status"] == "integration_not_configured"
        assert body["case_context"]["profile"] is None
        assert body["case_context"]["slot_key"] is None
    app.dependency_overrides.clear()
    engine.dispose()
    get_settings.cache_clear()


def test_profile_available_conflicts_products_factoring(api_harness):
    client, SessionLocal, url = api_harness
    marks_a = {c: False for c in PRODUCT_CODES}
    marks_b = {c: False for c in PRODUCT_CODES}
    marks_a["RKO"] = True
    marks_b["RKO"] = True
    marks_a["GAR"] = True
    marks_b["GAR"] = None  # unknown, not false
    marks_a["LOA"] = True
    marks_b["LOA"] = False  # conflict

    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(
            s,
            snap,
            external_uid="U_200",
            variants=[
                {"city": "Москва", "factoring_mark": True},
                {"city": "Казань", "factoring_mark": True},
            ],
            product_marks=[marks_a, marks_b],
        )
        user, company = _user_company(s)
        s.commit()
        snap_id, company_id, user_id = snap.id, company.id, user.id
        manual_size = company.size_band

    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_200",
        company_id=company_id,
        linked_by="ops",
    )

    with _session(SessionLocal) as s:
        links_before = s.scalar(select(func.count()).select_from(CaseOrgCompanyLink))
        memberships_before = s.scalar(select(func.count()).select_from(CompanyMembership))

    resp = client.get(
        f"/api/v1/companies/{company_id}/context",
        headers=_auth_headers(user_id),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["size_label"]  # still from manual size_band
    cc = body["case_context"]
    assert cc["status"] == "profile_available"
    assert cc["external_uid"] == "U_200"
    assert cc["snapshot_id"] == snap_id
    assert cc["version_label"] == "v1"
    profile = cc["profile"]
    assert profile["okved_code"]["status"] == "confirmed"
    assert profile["okved_code"]["value"] == "46.90"
    assert profile["city"]["status"] == "conflict"
    assert profile["city"]["value"] is None
    assert "city" in profile["conflicts"]
    by_code = {p["code"]: p["status"] for p in profile["products"]}
    assert by_code["RKO"] == "true"
    assert by_code["DEP"] == "false"
    assert by_code["GAR"] == "unknown"
    assert by_code["LOA"] == "conflict"
    assert by_code["GAR"] != "false"
    assert profile["factoring"]["status"] == "true"
    assert "факторинг" in profile["factoring"]["explanation"].lower()
    assert "услов" in profile["factoring"]["explanation"].lower()
    assert profile["revenue"]["amount"] == "1234567890.1"
    assert profile["revenue"]["unit"] is None
    assert "do_not_treat_as_rub" in profile["revenue"]["limitations"]
    assert "₽" not in str(profile["revenue"])
    assert "руб" not in str(profile["revenue"]).lower()
    assert profile["provenance"]["snapshot_id"] == snap_id
    assert profile["provenance"]["source_file"] == CATALOG_FILE
    blob = str(body)
    assert "must-not-leak" not in blob
    assert "raw_json" not in blob
    assert "C:/secret" not in blob
    assert "U_999" not in blob  # no foreign orgs

    with _session(SessionLocal) as s:
        assert s.scalar(select(func.count()).select_from(CaseOrgCompanyLink)) == links_before
        assert (
            s.scalar(select(func.count()).select_from(CompanyMembership))
            == memberships_before
        )
        company = s.get(Company, company_id)
        assert company is not None
        assert company.size_band == manual_size


def test_no_active_and_uid_missing(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        a = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, a, external_uid="U_300", variants=[{"city": "CityA"}])
        b = _seed_ready(s, slot=SLOT, label="v2", seq=2)
        _add_org(s, b, external_uid="U_301")  # U_300 missing
        user, company = _user_company(s)
        s.commit()
        a_id, b_id, company_id, user_id = a.id, b.id, company.id, user.id

    _activate(url, a_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_300",
        company_id=company_id,
    )

    # Clear active for no_active_snapshot
    with _session(SessionLocal) as s:
        ptr = s.get(CaseActiveSnapshot, SLOT)
        assert ptr is not None
        ptr.active_snapshot_id = None
        snap = s.get(CaseSnapshot, a_id)
        assert snap is not None
        snap.status = "ready"
        snap.activated_at = None
        s.commit()

    resp = client.get(
        f"/api/v1/companies/{company_id}/context",
        headers=_auth_headers(user_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["case_context"]["status"] == "no_active_snapshot"

    # Restore A then switch to B where UID missing
    with _session(SessionLocal) as s:
        snap = s.get(CaseSnapshot, a_id)
        assert snap is not None
        snap.status = "ready"
        s.commit()
    _activate(url, a_id, expect_no_active=True)
    _activate(url, b_id, expect_no_active=False, expected=a_id)

    resp2 = client.get(
        f"/api/v1/companies/{company_id}/context",
        headers=_auth_headers(user_id),
    )
    assert resp2.status_code == 200, resp2.text
    cc = resp2.json()["case_context"]
    assert cc["status"] == "uid_missing_in_snapshot"
    assert cc["profile"] is None
    assert cc["snapshot_id"] == b_id
    assert "CityA" not in str(cc)


def test_acl_stranger_forbidden(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        snap = _seed_ready(s, slot=SLOT, label="v1", seq=1)
        _add_org(s, snap, external_uid="U_400")
        member, company = _user_company(s)
        stranger = User(
            id=_uid(),
            email=f"{_uid()[:8]}@x.test",
            password_hash=hash_password("ApiTest1!"),
            display_name="Stranger",
            email_verified_at=datetime.now(timezone.utc),
        )
        s.add(stranger)
        s.commit()
        snap_id, company_id, stranger_id = snap.id, company.id, stranger.id
    _activate(url, snap_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_400",
        company_id=company_id,
    )
    resp = client.get(
        f"/api/v1/companies/{company_id}/context",
        headers=_auth_headers(stranger_id),
    )
    assert resp.status_code == 403


def test_snapshot_provenance_updates_on_switch(api_harness):
    client, SessionLocal, url = api_harness
    with _session(SessionLocal) as s:
        a = _seed_ready(s, slot=SLOT, label="hack-v1", seq=1)
        _add_org(s, a, external_uid="U_500", variants=[{"city": "A"}])
        b = _seed_ready(s, slot=SLOT, label="hack-v2", seq=2)
        _add_org(s, b, external_uid="U_500", variants=[{"city": "B"}])
        user, company = _user_company(s)
        s.commit()
        a_id, b_id, company_id, user_id = a.id, b.id, company.id, user.id

    _activate(url, a_id)
    run_link(
        database_url=url,
        slot_key=SLOT,
        external_uid="U_500",
        company_id=company_id,
    )
    r1 = client.get(
        f"/api/v1/companies/{company_id}/context",
        headers=_auth_headers(user_id),
    ).json()["case_context"]
    assert r1["profile"]["city"]["value"] == "A"
    assert r1["profile"]["provenance"]["snapshot_id"] == a_id
    assert r1["version_label"] == "hack-v1"

    _activate(url, b_id, expect_no_active=False, expected=a_id)
    r2 = client.get(
        f"/api/v1/companies/{company_id}/context",
        headers=_auth_headers(user_id),
    ).json()["case_context"]
    assert r2["profile"]["city"]["value"] == "B"
    assert r2["profile"]["provenance"]["snapshot_id"] == b_id
    assert r2["version_label"] == "hack-v2"
