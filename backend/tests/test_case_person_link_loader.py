"""Person–org link loader: temporary SQLite only; no application DATABASE_URL writes."""

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
    CaseOrgCompanyLink,
    CasePerson,
    CasePersonOrgLink,
    CaseSnapshot,
    Company,
    CompanyMembership,
    User,
)
from app.services.case_data.csv_io import sha256_file
from app.services.case_data.load_org_catalog import (
    ContentHashMismatchError,
    ContextMismatchError,
    SnapshotNotBuildingError,
)
from app.services.case_data.load_person_org_links import (
    IncompletePersonLinkImportError,
    PersonLinkValidationError,
    load_person_org_links,
)

ROOT = Path(__file__).resolve().parents[1]

LINK_HEADER = "SYNTHETIC_F;CITY_NAME;RC_NAME;SYNTHETIC_U"


def _uid() -> str:
    return str(uuid.uuid4())


def _link(fid: str, uid: str, *, city: str = "Moscow", rc: str = "RC1") -> str:
    return f"{fid};{city};{rc};{uid}"


def _write_csv(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LINK_HEADER + "\n" + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture
def db_session(tmp_path: Path):
    db_path = tmp_path / "person_link_loader.db"
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
    session: Session, csv_path: Path, *, slot: str = "plink_slot", seq: int = 1
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


def _add_org(
    session: Session,
    snap: CaseSnapshot,
    external_uid: str,
    *,
    has_profile: bool = True,
    resolution: str = "single",
) -> CaseOrg:
    org = CaseOrg(
        id=_uid(),
        snapshot_id=snap.id,
        external_uid=external_uid,
        has_catalog_profile=has_profile,
        profile_resolution=resolution,
    )
    session.add(org)
    session.flush()
    return org


def test_simple_link(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "simple.csv", [_link("F_1", "U_1")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    org = _add_org(db_session, snap, "U_1")
    result = load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()

    assert result.rows_inserted == 1
    assert result.persons_created == 1
    assert result.orgs_created == 0
    person = db_session.scalars(select(CasePerson)).one()
    assert person.external_fid == "F_1"
    link = db_session.scalars(select(CasePersonOrgLink)).one()
    assert link.person_id == person.id
    assert link.case_org_id == org.id
    assert link.city_name == "Moscow"
    assert link.rc_name == "RC1"
    assert link.relation_kind == "unspecified"
    assert link.org_had_catalog_at_import is True
    assert link.source_row_number == 1


def test_one_person_many_orgs(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "one_f.csv",
        [_link("F_1", "U_1"), _link("F_1", "U_2"), _link("F_1", "U_3")],
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(CasePerson)) == 1
    assert db_session.scalar(select(func.count()).select_from(CaseOrg)) == 3
    assert db_session.scalar(select(func.count()).select_from(CasePersonOrgLink)) == 3


def test_many_persons_one_org(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "one_u.csv",
        [_link("F_1", "U_9"), _link("F_2", "U_9"), _link("F_3", "U_9")],
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(CasePerson)) == 3
    assert db_session.scalar(select(func.count()).select_from(CaseOrg)) == 1
    assert db_session.scalar(select(func.count()).select_from(CasePersonOrgLink)) == 3


def test_orphan_org(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "orph.csv", [_link("F_1", "U_99")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    result = load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    assert result.orgs_created == 1
    org = db_session.scalars(select(CaseOrg)).one()
    assert org.has_catalog_profile is False
    assert org.profile_resolution == "absent"
    link = db_session.scalars(select(CasePersonOrgLink)).one()
    assert link.org_had_catalog_at_import is False


def test_reuse_across_batches(db_session: Session, tmp_path: Path):
    lines = [
        _link("F_1", "U_1"),
        _link("F_1", "U_2"),
        _link("F_2", "U_1"),
        _link("F_2", "U_2"),
        _link("F_1", "U_1", city="Spb", rc="RC2"),
    ]
    csv_path = _write_csv(tmp_path / "batches.csv", lines)
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_person_org_links(
        db_session,
        snapshot=snap,
        import_run=run,
        import_file=imp,
        csv_path=csv_path,
        batch_size=2,
    )
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(CasePerson)) == 2
    assert db_session.scalar(select(func.count()).select_from(CaseOrg)) == 2
    assert db_session.scalar(select(func.count()).select_from(CasePersonOrgLink)) == 5


def test_identical_source_rows_kept(db_session: Session, tmp_path: Path):
    same = _link("F_1", "U_1", city="A", rc="R")
    csv_path = _write_csv(tmp_path / "dups.csv", [same, same, same])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    links = db_session.scalars(
        select(CasePersonOrgLink).order_by(CasePersonOrgLink.source_row_number)
    ).all()
    assert len(links) == 3
    assert [lnk.source_row_number for lnk in links] == [1, 2, 3]
    assert len({lnk.id for lnk in links}) == 3


def test_geography_per_row_not_collapsed(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "geo.csv",
        [
            _link("F_1", "U_1", city="Moscow", rc="RC_A"),
            _link("F_1", "U_1", city="Kazan", rc="RC_B"),
            _link("F_1", "U_1", city="", rc=""),
        ],
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    links = db_session.scalars(
        select(CasePersonOrgLink).order_by(CasePersonOrgLink.source_row_number)
    ).all()
    assert [(lnk.city_name, lnk.rc_name) for lnk in links] == [
        ("Moscow", "RC_A"),
        ("Kazan", "RC_B"),
        (None, None),
    ]
    # Person geo stays on links only; one org, no catalog city fields written here
    assert db_session.scalar(select(func.count()).select_from(CaseOrg)) == 1
    assert db_session.scalar(select(func.count()).select_from(CasePerson)) == 1


def test_invalid_ids_and_allowed_empty_geo(db_session: Session, tmp_path: Path):
    bad_f = _write_csv(tmp_path / "bad_f.csv", ["X_1;Moscow;RC;U_1"])
    snap, run, imp = _bootstrap_building(db_session, bad_f)
    with pytest.raises(PersonLinkValidationError) as ei:
        load_person_org_links(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=bad_f
        )
    assert ei.value.field == "SYNTHETIC_F"
    db_session.rollback()

    bad_u = _write_csv(tmp_path / "bad_u.csv", ["F_1;Moscow;RC;not_uid"])
    snap, run, imp = _bootstrap_building(db_session, bad_u, slot="bu", seq=1)
    with pytest.raises(PersonLinkValidationError) as ei:
        load_person_org_links(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=bad_u
        )
    assert ei.value.field == "SYNTHETIC_U"
    db_session.rollback()

    ok_empty = _write_csv(tmp_path / "empty_geo.csv", ["F_1;;;U_1"])
    snap, run, imp = _bootstrap_building(db_session, ok_empty, slot="eg", seq=1)
    load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=ok_empty
    )
    db_session.commit()
    link = db_session.scalars(select(CasePersonOrgLink)).one()
    assert link.city_name is None and link.rc_name is None


def test_completed_skip_partial_hash(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "once.csv", [_link("F_1", "U_1"), _link("F_2", "U_2")]
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    r1 = load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    db_session.refresh(imp)
    r2 = load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    assert r1.skipped is False and r1.rows_inserted == 2
    assert r2.skipped is True and r2.reason == "already_completed_same_hash"
    assert db_session.scalar(select(func.count()).select_from(CasePersonOrgLink)) == 2

    imp.row_count_loaded = 99
    db_session.flush()
    with pytest.raises(IncompletePersonLinkImportError):
        load_person_org_links(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
        )
    db_session.rollback()

    csv2 = _write_csv(tmp_path / "partial.csv", [_link("F_9", "U_9")])
    snap2, run2, imp2 = _bootstrap_building(db_session, csv2, slot="partial", seq=1)
    person = CasePerson(id=_uid(), snapshot_id=snap2.id, external_fid="F_9")
    org = CaseOrg(
        id=_uid(),
        snapshot_id=snap2.id,
        external_uid="U_9",
        has_catalog_profile=False,
        profile_resolution="absent",
    )
    db_session.add_all([person, org])
    db_session.flush()
    db_session.add(
        CasePersonOrgLink(
            id=_uid(),
            snapshot_id=snap2.id,
            import_run_id=run2.id,
            source_file=imp2.source_file,
            source_row_number=1,
            person_id=person.id,
            case_org_id=org.id,
            city_name=None,
            rc_name=None,
            relation_kind="unspecified",
            org_had_catalog_at_import=False,
        )
    )
    imp2.status = "pending"
    db_session.flush()
    with pytest.raises(IncompletePersonLinkImportError):
        load_person_org_links(
            db_session, snapshot=snap2, import_run=run2, import_file=imp2, csv_path=csv2
        )
    db_session.rollback()

    csv_a = _write_csv(tmp_path / "ha.csv", [_link("F_1", "U_1")])
    csv_b = _write_csv(tmp_path / "hb.csv", [_link("F_2", "U_2")])
    snap, run, imp = _bootstrap_building(db_session, csv_a, slot="hash", seq=1)
    with pytest.raises(ContentHashMismatchError):
        load_person_org_links(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_b
        )


def test_reject_active_and_mismatch(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "act.csv", [_link("F_1", "U_1")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    snap.status = "active"
    db_session.flush()
    with pytest.raises(SnapshotNotBuildingError):
        load_person_org_links(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
        )

    snap.status = "building"
    db_session.flush()
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
    other = CaseImportRun(
        id=_uid(),
        snapshot_id=snap2.id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(other)
    db_session.flush()
    with pytest.raises(ContextMismatchError):
        load_person_org_links(
            db_session, snapshot=snap, import_run=other, import_file=imp, csv_path=csv_path
        )


def test_batch_error_then_rollback(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "batch.csv",
        [_link("F_1", "U_1"), "BAD_F;Moscow;RC;U_2"],
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    db_session.commit()
    db_session.refresh(snap)
    db_session.refresh(run)
    db_session.refresh(imp)
    with pytest.raises(PersonLinkValidationError):
        load_person_org_links(
            db_session,
            snapshot=snap,
            import_run=run,
            import_file=imp,
            csv_path=csv_path,
            batch_size=1,
        )
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(CasePersonOrgLink)) == 0
    assert db_session.scalar(select(func.count()).select_from(CasePerson)) == 0
    assert db_session.scalar(select(func.count()).select_from(CaseOrg)) == 0
    db_session.refresh(imp)
    assert imp.status == "pending"


def test_profile_upgrade_does_not_rewrite_historical_flag(
    db_session: Session, tmp_path: Path
):
    csv_path = _write_csv(tmp_path / "hist.csv", [_link("F_1", "U_5")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    link = db_session.scalars(select(CasePersonOrgLink)).one()
    assert link.org_had_catalog_at_import is False
    link_id = link.id

    org = db_session.scalars(select(CaseOrg)).one()
    org.has_catalog_profile = True
    org.profile_resolution = "single"
    db_session.commit()

    # Re-entry skips; historical flag must remain False
    db_session.refresh(imp)
    r2 = load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    assert r2.skipped is True
    db_session.expire_all()
    link2 = db_session.get(CasePersonOrgLink, link_id)
    assert link2 is not None
    assert link2.org_had_catalog_at_import is False
    assert db_session.get(CaseOrg, org.id).has_catalog_profile is True


def test_no_users_company_membership(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "side.csv", [_link("F_1", "U_1")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_person_org_links(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    assert db_session.scalars(select(User)).first() is None
    assert db_session.scalars(select(Company)).first() is None
    assert db_session.scalars(select(CompanyMembership)).first() is None
    assert db_session.scalars(select(CaseOrgCompanyLink)).first() is None
    assert snap.status == "building"


def test_active_pointer_untouched(db_session: Session, tmp_path: Path):
    active_csv = _write_csv(tmp_path / "active.csv", [_link("F_100", "U_100")])
    active_snap, active_run, active_file = _bootstrap_building(
        db_session, active_csv, slot="slot_a"
    )
    load_person_org_links(
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

    building_csv = _write_csv(tmp_path / "building.csv", [_link("F_200", "U_200")])
    bad_path = tmp_path / "tampered.csv"
    bad_path.write_text("not;a;person;link\n", encoding="utf-8")
    b_snap, b_run, b_file = _bootstrap_building(
        db_session, building_csv, slot="slot_a", seq=2
    )
    with pytest.raises(ContentHashMismatchError):
        load_person_org_links(
            db_session,
            snapshot=b_snap,
            import_run=b_run,
            import_file=b_file,
            csv_path=bad_path,
        )
    db_session.rollback()
    ptr = db_session.get(CaseActiveSnapshot, "slot_a")
    assert ptr is not None and ptr.active_snapshot_id == active_snap.id
