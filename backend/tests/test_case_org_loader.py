"""Company catalog loader: temporary SQLite only; no application DATABASE_URL writes."""

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
)
from app.services.case_data.csv_io import sha256_file
from app.services.case_data.load_org_catalog import (
    CatalogValidationError,
    ContentHashMismatchError,
    ContextMismatchError,
    IncompleteCatalogImportError,
    SnapshotNotBuildingError,
    load_company_catalog,
)
from app.services.case_data.resolution import resolve_catalog_variants

ROOT = Path(__file__).resolve().parents[1]

COMP_HEADER = (
    "SYNTHETIC_U;ORG_TYPE;OKFS_NAME;COMPANY_AGE_YEARS_GRADATION;ECO_MARK_LABEL;"
    "MAINOKVED_CODE;MAINOKVED_NAME;NEGATIVEMARK;AMOUNT_WORKERS_FNS_GRADATION;"
    "AMOUNT_WORKERS_SPARK_GRADATION;CL_TYPE;CL_PRODUCT_RKO_MARK;CL_PRODUCT_GAR_MARK;"
    "CL_PRODUCT_LOA_MARK;CL_PRODUCT_LEA_MARK;CL_PRODUCT_DEP_MARK;CL_PRODUCT_ZPP_MARK;"
    "FTS_FLAG;FTS_COUNTRY_NAME;FACTORING_MARK;REVENUE_COMPANY;GROUP_ID;CITY;REGION"
)


def _uid() -> str:
    return str(uuid.uuid4())


def _row(
    uid: str,
    *,
    okved: str = "62.01",
    okved_name: str = "IT",
    rev: str = "1000.0",
    city: str = "Moscow",
    region: str = "Moscow",
    eco: str = "Birth",
    neg: str = "0.0",
    rko: str = "1.0",
    factoring: str = "0.0",
    group: str = "G1",
) -> str:
    return (
        f"{uid};ORG;PRIV;0-3;{eco};{okved};{okved_name};{neg};<15;;CLIENT;"
        f"{rko};0.0;0.0;0.0;0.0;0.0;0.0;;{factoring};{rev};{group};{city};{region}"
    )


def _write_csv(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(COMP_HEADER + "\n" + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture
def db_session(tmp_path: Path):
    db_path = tmp_path / "org_loader.db"
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
        SessionLocal = sessionmaker(bind=engine)
        with SessionLocal() as session:
            yield session
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        get_settings.cache_clear()
        engine.dispose()


def _bootstrap_building(
    session: Session, csv_path: Path, *, slot: str = "test_slot", seq: int = 1
):
    snap_id, run_id, file_id = _uid(), _uid(), _uid()
    sha, size = sha256_file(csv_path)
    snap = CaseSnapshot(
        id=snap_id,
        slot_key=slot,
        version_label=f"v{seq}",
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
    imp = CaseImportFile(
        id=file_id,
        import_run_id=run_id,
        source_file=csv_path.name,
        content_sha256=sha,
        byte_size=size,
        row_count_declared=None,
        row_count_loaded=0,
        status="pending",
        last_row_number=None,
    )
    session.add(imp)
    session.flush()
    return snap, run, imp


def test_resolve_incomplete_coverage_not_consensus():
    out = resolve_catalog_variants(
        [
            {"eco_mark_label": "Birth", "city": "Moscow", "org_type": "ORG"},
            {"eco_mark_label": "", "city": "Moscow", "org_type": "ORG"},
        ]
    )
    assert "eco_mark_label" in out["absent_json"]
    assert out["absent_json"]["eco_mark_label"]["reason"] == "incomplete_coverage"
    assert out["consensus_json"].get("city") == "Moscow"
    assert "eco_mark_label" not in out["consensus_json"]


def test_load_simple_company(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "companies.csv", [_row("U_1", factoring="1.0")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    result = load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()

    assert result.rows_inserted == 1
    assert result.orgs_created == 1
    org = db_session.scalar(select(CaseOrg).where(CaseOrg.external_uid == "U_1"))
    assert org is not None
    assert org.has_catalog_profile is True
    assert org.profile_resolution == "single"
    row = db_session.scalar(select(CaseOrgCatalogRow).where(CaseOrgCatalogRow.case_org_id == org.id))
    assert row is not None
    assert row.factoring_mark is True
    assert row.revenue_unit is None and row.revenue_currency is None
    marks = db_session.scalars(
        select(CaseOrgProductMark).where(CaseOrgProductMark.catalog_row_id == row.id)
    ).all()
    assert len(marks) == 6
    assert {m.product_code: m.mark for m in marks}["RKO"] is True
    res = db_session.scalar(
        select(CaseOrgFieldResolution).where(CaseOrgFieldResolution.case_org_id == org.id)
    )
    assert res is not None
    assert res.variant_count == 1
    assert res.consensus_json.get("mainokved_code") == "62.01"
    assert db_session.scalars(select(Company)).first() is None
    assert db_session.scalars(select(CompanyMembership)).first() is None


def test_identical_and_conflicting_uid_variants(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "dup.csv",
        [
            _row("U_9", okved="46.90", city="Moscow", group="G1"),
            _row("U_9", okved="46.90", city="Moscow", group="G1"),  # identical twin
            _row("U_9", okved="62.01", city="Kazan", group="G1"),  # conflict fields
        ],
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()

    org = db_session.scalar(select(CaseOrg).where(CaseOrg.external_uid == "U_9"))
    assert org is not None
    rows = db_session.scalars(
        select(CaseOrgCatalogRow).where(CaseOrgCatalogRow.case_org_id == org.id)
    ).all()
    assert len(rows) == 3
    assert org.profile_resolution == "conflict"
    res = db_session.scalar(
        select(CaseOrgFieldResolution).where(CaseOrgFieldResolution.case_org_id == org.id)
    )
    assert "mainokved_code" in res.conflict_json
    assert "city" in res.conflict_json
    # agreeing fields across all three (org_type etc.) stay confirmed
    assert res.consensus_json.get("org_type") == "ORG"
    assert res.consensus_json.get("group_external_id") == "G1"


def test_product_flags_and_group_conflict(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "groups.csv",
        [
            _row("U_2", rko="1.0", group="G_A"),
            _row("U_2", rko="0.0", group="G_B"),
        ],
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()

    org = db_session.scalar(select(CaseOrg).where(CaseOrg.external_uid == "U_2"))
    res = db_session.scalar(
        select(CaseOrgFieldResolution).where(CaseOrgFieldResolution.case_org_id == org.id)
    )
    assert "products" in res.conflict_json
    assert "RKO" in res.conflict_json["products"]
    assert "group_external_id" in res.conflict_json
    groups = db_session.scalars(select(CaseOrgGroup)).all()
    assert {g.external_group_id for g in groups} == {"G_A", "G_B"}
    members = db_session.scalars(
        select(CaseOrgGroupMember).where(CaseOrgGroupMember.case_org_id == org.id)
    ).all()
    assert len(members) == 2
    assert all(m.is_conflicted_membership for m in members)


def test_orphan_upgraded_keeps_id(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "orphan.csv", [_row("U_5")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    orphan = CaseOrg(
        id=_uid(),
        snapshot_id=snap.id,
        external_uid="U_5",
        has_catalog_profile=False,
        profile_resolution="absent",
    )
    db_session.add(orphan)
    db_session.flush()
    orphan_id = orphan.id

    result = load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()

    assert result.orgs_upgraded_from_orphan == 1
    assert result.orgs_created == 0
    org = db_session.scalar(select(CaseOrg).where(CaseOrg.external_uid == "U_5"))
    assert org.id == orphan_id
    assert org.has_catalog_profile is True
    assert org.profile_resolution == "single"
    assert db_session.scalar(
        select(func.count()).select_from(CaseOrg).where(CaseOrg.snapshot_id == snap.id)
    ) == 1


def test_large_org_in_lists_are_chunked(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Regression: SQLite rejects huge IN lists; catalog post-pass must chunk."""
    import app.services.case_data.load_org_catalog as cat_mod

    monkeypatch.setattr(cat_mod, "_IN_CHUNK", 2)
    monkeypatch.setattr(cat_mod, "_MAX_BIND_PARAMS", 40)
    lines = [_row(f"U_{i}") for i in range(1, 21)]
    csv_path = _write_csv(tmp_path / "many.csv", lines)
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    result = load_company_catalog(
        db_session,
        snapshot=snap,
        import_run=run,
        import_file=imp,
        csv_path=csv_path,
        batch_size=3,
    )
    db_session.commit()
    assert result.rows_inserted == 20
    assert db_session.scalar(select(func.count()).select_from(CaseOrg)) == 20
    assert db_session.scalar(select(func.count()).select_from(CaseOrgFieldResolution)) == 20
    assert db_session.scalar(select(func.count()).select_from(CaseOrgProductMark)) == 120


def test_rerun_completed_same_hash_skipped(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "once.csv", [_row("U_1"), _row("U_2")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    r1 = load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    db_session.refresh(imp)
    assert imp.status == "completed" and imp.row_count_loaded == 2
    r2 = load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    assert r1.skipped is False and r1.rows_inserted == 2
    assert r2.skipped is True and r2.reason == "already_completed_same_hash"
    assert db_session.scalar(select(func.count()).select_from(CaseOrgCatalogRow)) == 2


def test_partial_rows_without_completed_not_skipped(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "partial.csv", [_row("U_1")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    # Simulate interrupted load: one catalog row, file still pending.
    org = CaseOrg(
        id=_uid(),
        snapshot_id=snap.id,
        external_uid="U_1",
        has_catalog_profile=True,
        profile_resolution="single",
    )
    db_session.add(org)
    db_session.flush()
    db_session.add(
        CaseOrgCatalogRow(
            id=_uid(),
            snapshot_id=snap.id,
            import_run_id=run.id,
            case_org_id=org.id,
            source_file=imp.source_file,
            source_row_number=1,
            row_content_sha256="a" * 64,
            revenue_raw="1000.0",
            revenue_amount=None,
            revenue_parse_status="ok",
            raw_json={"SYNTHETIC_U": "U_1"},
        )
    )
    imp.status = "pending"
    db_session.flush()
    with pytest.raises(IncompleteCatalogImportError):
        load_company_catalog(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
        )


def test_completed_with_wrong_counter_rejected(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "cnt.csv", [_row("U_1"), _row("U_2")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    db_session.refresh(imp)
    imp.row_count_loaded = 99
    db_session.flush()
    with pytest.raises(IncompleteCatalogImportError):
        load_company_catalog(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
        )


def test_invalid_bool_group_money_block_like_dry_run(db_session: Session, tmp_path: Path):
    bad_bool = _write_csv(tmp_path / "bad_bool.csv", [_row("U_1", rko="yes")])
    snap, run, imp = _bootstrap_building(db_session, bad_bool)
    with pytest.raises(CatalogValidationError) as ei:
        load_company_catalog(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=bad_bool
        )
    assert ei.value.field == "CL_PRODUCT_RKO_MARK"
    db_session.rollback()

    bad_group = _write_csv(tmp_path / "bad_group.csv", [_row("U_1", group="G 1")])
    snap, run, imp = _bootstrap_building(db_session, bad_group, slot="g", seq=1)
    with pytest.raises(CatalogValidationError) as ei:
        load_company_catalog(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=bad_group
        )
    assert ei.value.field == "GROUP_ID"
    db_session.rollback()

    bad_money = _write_csv(tmp_path / "bad_money.csv", [_row("U_1", rev="1.23")])
    snap, run, imp = _bootstrap_building(db_session, bad_money, slot="m", seq=1)
    with pytest.raises(CatalogValidationError) as ei:
        load_company_catalog(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=bad_money
        )
    assert ei.value.field == "REVENUE_COMPANY"
    assert ei.value.reason == "too_many_fraction_digits"


def test_allowed_empty_eco_and_spark_ok(db_session: Session, tmp_path: Path):
    # ECO empty and SPARK workers empty are allowed (same as dry-run non-errors).
    line = _row("U_1", eco="")
    csv_path = _write_csv(tmp_path / "sparse.csv", [line])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    result = load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    assert result.rows_inserted == 1
    row = db_session.scalars(select(CaseOrgCatalogRow)).one()
    assert row.eco_mark_label is None
    assert row.workers_spark_gradation is None


def test_batch_error_then_rollback_leaves_nothing(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "batch.csv",
        [_row("U_1"), _row("U_2", rko="nope")],
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    # Commit context first so rollback only undoes the failed load attempt.
    db_session.commit()
    db_session.refresh(snap)
    db_session.refresh(run)
    db_session.refresh(imp)
    with pytest.raises(CatalogValidationError):
        load_company_catalog(
            db_session,
            snapshot=snap,
            import_run=run,
            import_file=imp,
            csv_path=csv_path,
            batch_size=1,
        )
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(CaseOrgCatalogRow)) == 0
    assert db_session.scalar(select(func.count()).select_from(CaseOrg)) == 0
    assert db_session.scalar(select(func.count()).select_from(CaseOrgProductMark)) == 0
    db_session.refresh(imp)
    assert imp.status == "pending"


def test_empty_file_completed_then_skip(db_session: Session, tmp_path: Path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text(COMP_HEADER + "\n", encoding="utf-8", newline="\n")
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    r1 = load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    db_session.refresh(imp)
    assert r1.rows_inserted == 0
    assert imp.status == "completed" and imp.row_count_loaded == 0
    r2 = load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    assert r2.skipped is True


def test_hash_mismatch_refuses(db_session: Session, tmp_path: Path):
    csv_a = _write_csv(tmp_path / "a.csv", [_row("U_1")])
    csv_b = _write_csv(tmp_path / "b.csv", [_row("U_2")])
    snap, run, imp = _bootstrap_building(db_session, csv_a)
    with pytest.raises(ContentHashMismatchError):
        load_company_catalog(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_b
        )
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(CaseOrgCatalogRow)) == 0


def test_reject_active_snapshot(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "act.csv", [_row("U_1")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    snap.status = "active"
    db_session.flush()
    with pytest.raises(SnapshotNotBuildingError):
        load_company_catalog(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
        )


def test_reject_mismatched_run_file(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "m.csv", [_row("U_1")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    other = CaseImportRun(
        id=_uid(),
        snapshot_id=snap.id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    # unique snapshot_id on runs — use different snapshot
    snap2 = CaseSnapshot(
        id=_uid(),
        slot_key="other",
        version_label="v1",
        version_seq=1,
        status="building",
        import_run_id=None,
    )
    db_session.add(snap2)
    db_session.flush()
    other.snapshot_id = snap2.id
    db_session.add(other)
    db_session.flush()
    with pytest.raises(ContextMismatchError):
        load_company_catalog(
            db_session, snapshot=snap, import_run=other, import_file=imp, csv_path=csv_path
        )


def test_active_pointer_untouched_on_failed_building_load(db_session: Session, tmp_path: Path):
    # Active snapshot with pointer
    active_csv = _write_csv(tmp_path / "active.csv", [_row("U_100")])
    active_snap, active_run, active_file = _bootstrap_building(
        db_session, active_csv, slot="slot_a"
    )
    load_company_catalog(
        db_session,
        snapshot=active_snap,
        import_run=active_run,
        import_file=active_file,
        csv_path=active_csv,
    )
    active_snap.status = "active"
    db_session.add(
        CaseActiveSnapshot(
            slot_key="slot_a",
            active_snapshot_id=active_snap.id,
            updated_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    # New building snapshot fails hash check
    building_csv = _write_csv(tmp_path / "building.csv", [_row("U_200")])
    bad_path = tmp_path / "tampered.csv"
    bad_path.write_text("not;a;valid;companies;file\n", encoding="utf-8")
    b_snap, b_run, b_file = _bootstrap_building(
        db_session, building_csv, slot="slot_a", seq=2
    )
    # Register hash of building_csv but pass tampered path → mismatch
    with pytest.raises(ContentHashMismatchError):
        load_company_catalog(
            db_session,
            snapshot=b_snap,
            import_run=b_run,
            import_file=b_file,
            csv_path=bad_path,
        )
    db_session.rollback()

    ptr = db_session.get(CaseActiveSnapshot, "slot_a")
    assert ptr is not None
    assert ptr.active_snapshot_id == active_snap.id
    active = db_session.get(CaseSnapshot, active_snap.id)
    assert active.status == "active"
    # Building snap still building, no catalog from failed load
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CaseOrgCatalogRow)
            .where(CaseOrgCatalogRow.snapshot_id == b_snap.id)
        )
        == 0
    )


def test_no_company_link_side_effects(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "n.csv", [_row("U_1")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_company_catalog(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    assert db_session.scalars(select(Company)).first() is None
    assert db_session.scalars(select(CompanyMembership)).first() is None
    assert db_session.scalars(select(CaseOrgCompanyLink)).first() is None
    assert snap.status == "building"
