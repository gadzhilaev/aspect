"""Case org ↔ Company link + read context on temporary SQLite only."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.jobs import link_case_org_company as link_job
from app.models import (
    CaseActiveSnapshot,
    CaseImportFile,
    CaseImportRun,
    CaseOrg,
    CaseOrgCatalogRow,
    CaseOrgCompanyLink,
    CaseOrgFieldResolution,
    CaseOrgGroup,
    CaseOrgGroupMember,
    CaseOrgProductMark,
    CaseSnapshot,
    Company,
    CompanyMembership,
    User,
)
from app.services.case_data.activate_snapshot import run_activation
from app.services.case_data.company_case_context import (
    CaseContextAccessError,
    read_case_company_context,
)
from app.services.case_data.link_org_company import (
    LinkConflictError,
    LinkPreconditionError,
    run_link,
)
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
def db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "case_ctx.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    try:
        command.upgrade(_alembic_config(), "head")
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        get_settings.cache_clear()
        engine.dispose()
    return url


def _session(url: str) -> Session:
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return sessionmaker(bind=engine, autoflush=False)()


def _seed_ready_snapshot(
    session: Session,
    *,
    slot: str,
    label: str,
    seq: int,
) -> CaseSnapshot:
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
                content_sha256="b" * 64,
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


def _add_profiled_org(
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
        "fts_country_name_raw": "Китай, Германия",
        "factoring_mark": False,
        "revenue_raw": "1000.0",
        "group_external_id": "G_1",
        "city": "Москва",
        "region": "Москва",
    }
    rows_data = variants if variants is not None else [defaults]
    marks_data = product_marks
    if marks_data is None:
        marks_data = [
            {c: (True if c == "RKO" else False) for c in PRODUCT_CODES}
            for _ in rows_data
        ]

    # UNIQUE(import_run_id, source_file, source_row_number) — allocate globally per run.
    max_row = session.scalar(
        select(func.max(CaseOrgCatalogRow.source_row_number)).where(
            CaseOrgCatalogRow.import_run_id == snap.import_run_id,
            CaseOrgCatalogRow.source_file == CATALOG_FILE,
        )
    ) or 0

    catalog_ids: list[str] = []
    merged_rows: list[dict] = []
    for i, row in enumerate(rows_data):
        merged = {**defaults, **row}
        merged_rows.append(merged)
        cid = _uid()
        catalog_ids.append(cid)
        session.add(
            CaseOrgCatalogRow(
                id=cid,
                snapshot_id=snap.id,
                import_run_id=snap.import_run_id,
                case_org_id=org.id,
                source_file=CATALOG_FILE,
                source_row_number=max_row + i + 1,
                row_content_sha256=f"{i:064d}"[:64],
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
                revenue_parse_error=None,
                revenue_unit=None,
                revenue_currency=None,
                group_external_id=merged.get("group_external_id"),
                city=merged.get("city"),
                region=merged.get("region"),
                raw_json={"secret": "must-not-leak"},
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

    gid = resolved["consensus_json"].get("group_external_id")
    if gid and "group_external_id" not in resolved["conflict_json"]:
        group = session.scalars(
            select(CaseOrgGroup).where(
                CaseOrgGroup.snapshot_id == snap.id,
                CaseOrgGroup.external_group_id == str(gid),
            )
        ).first()
        if group is None:
            group = CaseOrgGroup(
                id=_uid(), snapshot_id=snap.id, external_group_id=str(gid)
            )
            session.add(group)
            session.flush()
        session.add(
            CaseOrgGroupMember(
                id=_uid(),
                snapshot_id=snap.id,
                group_id=group.id,
                case_org_id=org.id,
                catalog_row_id=catalog_ids[0],
                is_conflicted_membership=False,
            )
        )
    session.flush()
    return org


def _user_company_member(
    session: Session, *, name: str = "Acme", industry: str = "manual_industry"
) -> tuple[User, Company]:
    user = User(
        id=_uid(),
        email=f"{_uid()[:8]}@example.test",
        password_hash=hash_password("TestPass1!"),
        display_name="Tester",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.flush()
    company = Company(
        id=_uid(),
        name=name,
        industry=industry,
        size_band="medium",
        hq_region="ManualRegion",
        profile_status="ready",
        digital_twin_status="built",
        digital_twin_coverage=0.5,
        is_demo=False,
        created_by=user.id,
    )
    session.add(company)
    session.flush()
    session.add(
        CompanyMembership(
            id=_uid(),
            user_id=user.id,
            company_id=company.id,
            role="owner",
        )
    )
    session.flush()
    return user, company


def _activate(url: str, slot: str, snap_id: str, *, expect_no_active: bool = True, expected: str | None = None):
    return run_activation(
        database_url=url,
        slot_key=slot,
        snapshot_id=snap_id,
        expect_no_active=expect_no_active,
        expected_active_snapshot_id=expected,
    )


# --- linking -----------------------------------------------------------------


def test_link_success_and_idempotent(db_url: str):
    with _session(db_url) as s:
        snap = _seed_ready_snapshot(s, slot=SLOT, label="v1", seq=1)
        _add_profiled_org(s, snap, external_uid="U_100")
        user, company = _user_company_member(s)
        s.commit()
        snap_id, company_id = snap.id, company.id

    _activate(db_url, SLOT, snap_id, expect_no_active=True)

    r1 = run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_100",
        company_id=company_id,
        linked_by="ops-1",
    )
    assert r1.outcome == "linked"
    linked_at = r1.linked_at

    r2 = run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_100",
        company_id=company_id,
        linked_by="ops-2",
    )
    assert r2.outcome == "already_linked"
    assert r2.link_id == r1.link_id
    # SQLite may drop tzinfo on round-trip; compare naive instants.
    assert r2.linked_at.replace(tzinfo=None) == linked_at.replace(tzinfo=None)
    assert r2.linked_by == "ops-1"

    with _session(db_url) as s:
        assert s.scalar(select(func.count()).select_from(CaseOrgCompanyLink)) == 1
        assert s.scalar(select(func.count()).select_from(CompanyMembership)) == 1


def test_link_conflict_and_missing_company_orphan(db_url: str):
    with _session(db_url) as s:
        snap = _seed_ready_snapshot(s, slot=SLOT, label="v1", seq=1)
        _add_profiled_org(s, snap, external_uid="U_1")
        _add_profiled_org(s, snap, external_uid="U_2")
        _add_profiled_org(s, snap, external_uid="U_900", orphan=True)
        u1, c1 = _user_company_member(s, name="C1")
        u2, c2 = _user_company_member(s, name="C2")
        s.commit()
        snap_id, c1_id, c2_id = snap.id, c1.id, c2.id

    _activate(db_url, SLOT, snap_id, expect_no_active=True)

    run_link(database_url=db_url, slot_key=SLOT, external_uid="U_1", company_id=c1_id)

    with pytest.raises(LinkConflictError):
        run_link(database_url=db_url, slot_key=SLOT, external_uid="U_2", company_id=c1_id)

    with pytest.raises(LinkConflictError):
        run_link(database_url=db_url, slot_key=SLOT, external_uid="U_1", company_id=c2_id)

    with pytest.raises(LinkPreconditionError, match="does not exist"):
        run_link(database_url=db_url, slot_key=SLOT, external_uid="U_2", company_id=_uid())

    with pytest.raises(LinkPreconditionError, match="orphan"):
        run_link(
            database_url=db_url,
            slot_key=SLOT,
            external_uid="U_900",
            company_id=c2_id,
        )

    with _session(db_url) as s:
        assert s.scalar(select(func.count()).select_from(CaseOrgCompanyLink)) == 1
        # No new memberships beyond the two seeds.
        assert s.scalar(select(func.count()).select_from(CompanyMembership)) == 2


def test_link_cli(db_url: str):
    with _session(db_url) as s:
        snap = _seed_ready_snapshot(s, slot=SLOT, label="v1", seq=1)
        _add_profiled_org(s, snap, external_uid="U_901")
        _, company = _user_company_member(s)
        s.commit()
        snap_id, company_id = snap.id, company.id
    _activate(db_url, SLOT, snap_id, expect_no_active=True)

    rc = link_job.main(
        [
            "--database-url",
            db_url,
            "--slot-key",
            SLOT,
            "--external-uid",
            "U_901",
            "--company-id",
            company_id,
            "--linked-by",
            "cli-ops",
        ]
    )
    assert rc == 0


# --- reading -----------------------------------------------------------------


def test_member_access_stranger_denied_and_not_linked(db_url: str):
    with _session(db_url) as s:
        snap = _seed_ready_snapshot(s, slot=SLOT, label="v1", seq=1)
        _add_profiled_org(s, snap, external_uid="U_10")
        member, company = _user_company_member(s)
        stranger = User(
            id=_uid(),
            email=f"{_uid()[:8]}@x.test",
            password_hash=hash_password("TestPass1!"),
            display_name="Stranger",
        )
        session_company2 = Company(
            id=_uid(),
            name="Other",
            profile_status="draft",
            digital_twin_status="not_built",
            digital_twin_coverage=0.0,
            is_demo=False,
        )
        s.add(stranger)
        s.add(session_company2)
        s.commit()
        snap_id = snap.id
        company_id = company.id
        member_id = member.id
        stranger_id = stranger.id

    _activate(db_url, SLOT, snap_id, expect_no_active=True)

    with _session(db_url) as s:
        ctx = read_case_company_context(
            s, user=member_id, company_id=company_id, slot_key=SLOT
        )
        assert ctx.status == "not_linked"
        with pytest.raises(CaseContextAccessError):
            read_case_company_context(
                s, user=stranger_id, company_id=company_id, slot_key=SLOT
            )


def test_profile_available_conflicts_products_provenance(db_url: str):
    with _session(db_url) as s:
        snap = _seed_ready_snapshot(s, slot=SLOT, label="v1", seq=1)
        marks_a = {c: True if c == "RKO" else False for c in PRODUCT_CODES}
        marks_b = {c: True if c == "RKO" else (None if c == "GAR" else False) for c in PRODUCT_CODES}
        # GAR: True vs None → incomplete → unknown, not false
        marks_b["GAR"] = None
        marks_a["GAR"] = True
        # LOA: True vs False → conflict
        marks_a["LOA"] = True
        marks_b["LOA"] = False
        _add_profiled_org(
            s,
            snap,
            external_uid="U_902",
            variants=[
                {"city": "Москва", "mainokved_code": "46.90", "factoring_mark": False},
                {"city": "Казань", "mainokved_code": "46.90", "factoring_mark": False},
            ],
            product_marks=[marks_a, marks_b],
        )
        user, company = _user_company_member(s, industry="manual_keep")
        original_industry = company.industry
        original_size = company.size_band
        s.commit()
        snap_id, company_id, user_id = snap.id, company.id, user.id

    _activate(db_url, SLOT, snap_id, expect_no_active=True)
    run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_902",
        company_id=company_id,
        linked_by="ops",
    )

    with _session(db_url) as s:
        before_links = s.scalar(select(func.count()).select_from(CaseOrgCompanyLink))
        before_memberships = s.scalar(select(func.count()).select_from(CompanyMembership))
        company_row = s.get(Company, company_id)
        assert company_row is not None
        industry_before = company_row.industry

        ctx = read_case_company_context(
            s, user=user_id, company_id=company_id, slot_key=SLOT
        )
        assert ctx.status == "profile_available"
        assert ctx.read_only is True
        assert ctx.profile is not None
        assert ctx.manual.industry == "manual_keep"
        assert ctx.profile.okved_code.status == "confirmed"
        assert ctx.profile.okved_code.value == "46.90"
        assert ctx.profile.city.status == "conflict"
        assert ctx.profile.city.value is None
        assert "city" in ctx.profile.conflicts

        by_code = {p.code: p.status for p in ctx.profile.products}
        assert by_code["RKO"] == "true"
        assert by_code["DEP"] == "false"
        assert by_code["GAR"] == "unknown"
        assert by_code["LOA"] == "conflict"
        assert by_code["GAR"] != "false"

        assert ctx.profile.factoring.status == "false"
        assert ctx.profile.fts_countries.status == "confirmed"
        assert "Китай" in ctx.profile.fts_countries.countries_raw
        assert ctx.profile.fts_countries.note == "raw_fts_country_only_no_trade_direction"
        assert ctx.profile.revenue.unit is None
        assert "do_not_treat_as_rub" in ctx.profile.revenue.limitations
        assert ctx.profile.provenance.snapshot_id == snap_id
        assert ctx.profile.provenance.source_file == CATALOG_FILE
        assert len(ctx.profile.provenance.source_row_numbers) == 2
        assert "secret" not in str(ctx.profile.conflicts)
        assert "must-not-leak" not in str(ctx.profile.absent)

        # Read must not write.
        s.flush()
        assert s.scalar(select(func.count()).select_from(CaseOrgCompanyLink)) == before_links
        assert (
            s.scalar(select(func.count()).select_from(CompanyMembership))
            == before_memberships
        )
        s.refresh(company_row)
        assert company_row.industry == industry_before == original_industry
        assert company_row.size_band == original_size


def test_snapshot_switch_keeps_link_no_backfill(db_url: str):
    with _session(db_url) as s:
        a = _seed_ready_snapshot(s, slot=SLOT, label="v1", seq=1)
        _add_profiled_org(
            s,
            a,
            external_uid="U_903",
            variants=[{"city": "CityA", "mainokved_code": "10.00"}],
        )
        b = _seed_ready_snapshot(s, slot=SLOT, label="v2", seq=2)
        # B has a different org only — U_903 missing.
        _add_profiled_org(s, b, external_uid="U_904")
        user, company = _user_company_member(s)
        s.commit()
        a_id, b_id, company_id, user_id = a.id, b.id, company.id, user.id

    _activate(db_url, SLOT, a_id, expect_no_active=True)
    run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_903",
        company_id=company_id,
    )

    with _session(db_url) as s:
        ctx_a = read_case_company_context(
            s, user=user_id, company_id=company_id, slot_key=SLOT
        )
        assert ctx_a.status == "profile_available"
        assert ctx_a.profile is not None
        assert ctx_a.profile.city.value == "CityA"
        assert ctx_a.active_snapshot is not None
        assert ctx_a.active_snapshot.snapshot_id == a_id

    _activate(db_url, SLOT, b_id, expect_no_active=False, expected=a_id)

    with _session(db_url) as s:
        assert s.scalar(select(func.count()).select_from(CaseOrgCompanyLink)) == 1
        link = s.scalars(select(CaseOrgCompanyLink)).one()
        assert link.external_uid == "U_903"

        ctx_b = read_case_company_context(
            s, user=user_id, company_id=company_id, slot_key=SLOT
        )
        assert ctx_b.status == "uid_missing_in_snapshot"
        assert ctx_b.profile is None
        assert ctx_b.missing_external_uid == "U_903"
        assert ctx_b.active_snapshot is not None
        assert ctx_b.active_snapshot.snapshot_id == b_id
        # Must not silently return CityA from retired A.
        assert ctx_b.profile is None


def test_slots_do_not_mix(db_url: str):
    slot_a, slot_b = "slot_a", "slot_b"
    with _session(db_url) as s:
        sa = _seed_ready_snapshot(s, slot=slot_a, label="v1", seq=1)
        _add_profiled_org(
            s, sa, external_uid="U_905", variants=[{"city": "FromA"}]
        )
        sb = _seed_ready_snapshot(s, slot=slot_b, label="v1", seq=1)
        _add_profiled_org(
            s, sb, external_uid="U_905", variants=[{"city": "FromB"}]
        )
        user, company = _user_company_member(s)
        s.commit()
        sa_id, sb_id, company_id, user_id = sa.id, sb.id, company.id, user.id

    _activate(db_url, slot_a, sa_id, expect_no_active=True)
    _activate(db_url, slot_b, sb_id, expect_no_active=True)
    run_link(
        database_url=db_url,
        slot_key=slot_a,
        external_uid="U_905",
        company_id=company_id,
    )

    with _session(db_url) as s:
        ctx_a = read_case_company_context(
            s, user=user_id, company_id=company_id, slot_key=slot_a
        )
        assert ctx_a.status == "profile_available"
        assert ctx_a.profile is not None
        assert ctx_a.profile.city.value == "FromA"

        ctx_b = read_case_company_context(
            s, user=user_id, company_id=company_id, slot_key=slot_b
        )
        assert ctx_b.status == "not_linked"


def test_profile_absent_in_active(db_url: str):
    with _session(db_url) as s:
        snap = _seed_ready_snapshot(s, slot=SLOT, label="v1", seq=1)
        # Profiled enough to link, then we will manually strip for a second org path:
        # Link requires catalog profile — so link U_P, then add orphan-only path
        # via switching is covered above. Here: org with has_catalog but we simulate
        # profile_absent by linking then clearing? Better: seed orphan cannot link.
        # For profile_absent after link: create profiled → link → replace active with
        # snapshot where same UID exists as orphan.
        _add_profiled_org(s, snap, external_uid="U_906")
        snap2 = _seed_ready_snapshot(s, slot=SLOT, label="v2", seq=2)
        _add_profiled_org(s, snap2, external_uid="U_906", orphan=True)
        user, company = _user_company_member(s)
        s.commit()
        s1, s2, company_id, user_id = snap.id, snap2.id, company.id, user.id

    _activate(db_url, SLOT, s1, expect_no_active=True)
    run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_906",
        company_id=company_id,
    )
    _activate(db_url, SLOT, s2, expect_no_active=False, expected=s1)

    with _session(db_url) as s:
        ctx = read_case_company_context(
            s, user=user_id, company_id=company_id, slot_key=SLOT
        )
        assert ctx.status == "profile_absent"
        assert ctx.profile is None
        assert ctx.link is not None
        assert ctx.link.external_uid == "U_906"


def test_no_active_snapshot_status(db_url: str):
    with _session(db_url) as s:
        snap = _seed_ready_snapshot(s, slot=SLOT, label="v1", seq=1)
        _add_profiled_org(s, snap, external_uid="U_907")
        user, company = _user_company_member(s)
        # Manually insert link without activating (operator mistake path: link needs active;
        # so activate, link, then clear pointer for read test).
        s.commit()
        snap_id, company_id, user_id = snap.id, company.id, user.id

    _activate(db_url, SLOT, snap_id, expect_no_active=True)
    run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid="U_907",
        company_id=company_id,
    )

    with _session(db_url) as s:
        ptr = s.get(CaseActiveSnapshot, SLOT)
        assert ptr is not None
        ptr.active_snapshot_id = None
        snap_row = s.get(CaseSnapshot, snap_id)
        assert snap_row is not None
        snap_row.status = "ready"
        snap_row.activated_at = None
        s.commit()

        ctx = read_case_company_context(
            s, user=user_id, company_id=company_id, slot_key=SLOT
        )
        assert ctx.status == "no_active_snapshot"
        assert ctx.profile is None
