"""Case data schema: migrations + integrity on temporary DBs only."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.models import (
    CaseActiveSnapshot,
    CaseImportRun,
    CaseOrg,
    CaseOrgCatalogRow,
    CaseOrgCompanyLink,
    CasePayment,
    CasePerson,
    CasePersonOrgLink,
    CaseSnapshot,
    Company,
    CompanyMembership,
)
from tests._alembic_util import (
    ALEMBIC_HEAD,
    alembic_config,
    assert_head_schema,
    sqlite_engine,
    temp_sqlite_path,
    with_db_url,
)

CASE_TABLES = {
    "case_snapshots",
    "case_active_snapshot",
    "case_import_runs",
    "case_import_files",
    "case_org",
    "case_org_catalog_rows",
    "case_org_product_marks",
    "case_org_field_resolution",
    "case_org_groups",
    "case_org_group_members",
    "case_payments",
    "case_persons",
    "case_person_org_links",
    "case_org_company_links",
}


def _sqlite_engine(path: Path):
    engine, url = sqlite_engine(path)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine, url

def _uid() -> str:
    return str(uuid.uuid4())


def _company(session: Session, name: str) -> Company:
    c = Company(
        id=_uid(),
        name=name,
        profile_status="draft",
        digital_twin_status="not_built",
        digital_twin_coverage=0.0,
        is_demo=False,
    )
    session.add(c)
    session.flush()
    return c


def _bootstrap_snapshot(session: Session, *, slot: str, seq: int, status: str = "building"):
    snap_id = _uid()
    run_id = _uid()
    snap = CaseSnapshot(
        id=snap_id,
        slot_key=slot,
        version_label=f"v{seq}",
        version_seq=seq,
        status=status,
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
    session.flush()
    return snap, run


def _add_org(session: Session, snap: CaseSnapshot, external_uid: str, *, catalog: bool = False):
    org = CaseOrg(
        id=_uid(),
        snapshot_id=snap.id,
        external_uid=external_uid,
        has_catalog_profile=catalog,
        profile_resolution="single" if catalog else "absent",
    )
    session.add(org)
    session.flush()
    return org


@pytest.fixture
def sqlite_migrated():
    with temp_sqlite_path("case.db") as db_path:
        engine, url = _sqlite_engine(db_path)
        try:
            with with_db_url(url):
                command.upgrade(alembic_config(), "head")
                SessionLocal = sessionmaker(bind=engine)
                yield engine, SessionLocal
        finally:
            engine.dispose()


def test_upgrade_head_from_scratch_sqlite():
    with temp_sqlite_path("case_from_scratch.db") as db_path:
        engine, url = _sqlite_engine(db_path)
        try:
            with with_db_url(url):
                command.upgrade(alembic_config(), "head")
                assert CASE_TABLES.issubset(set(inspect(engine).get_table_names()))
                assert_head_schema(engine)
        finally:
            engine.dispose()


def test_upgrade_from_005_preserves_company_sqlite():
    with temp_sqlite_path("case_from_005.db") as db_path:
        engine, url = _sqlite_engine(db_path)
        try:
            with with_db_url(url):
                command.upgrade(alembic_config(), "005")
                SessionLocal = sessionmaker(bind=engine)
                company_id = _uid()
                with SessionLocal() as session:
                    session.add(
                        Company(
                            id=company_id,
                            name="Preserve Me",
                            profile_status="draft",
                            digital_twin_status="not_built",
                            digital_twin_coverage=0.0,
                            is_demo=False,
                        )
                    )
                    session.commit()

                command.upgrade(alembic_config(), "head")
                with SessionLocal() as session:
                    company = session.get(Company, company_id)
                    assert company is not None
                    assert company.name == "Preserve Me"
                    assert session.query(Company).count() == 1
                assert CASE_TABLES.issubset(set(inspect(engine).get_table_names()))
                assert_head_schema(engine)
        finally:
            engine.dispose()


def test_downgrade_006_then_reupgrade_sqlite():
    """Round-trip past 008 SQLite outbox column drop, then back to head 010."""
    with temp_sqlite_path("case_down_up.db") as db_path:
        engine, url = _sqlite_engine(db_path)
        try:
            with with_db_url(url):
                cfg = alembic_config()
                command.upgrade(cfg, "head")
                command.downgrade(cfg, "005")
                tables = set(inspect(engine).get_table_names())
                assert not (CASE_TABLES & tables)
                with engine.connect() as conn:
                    ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                assert ver == "005"

                command.upgrade(cfg, "head")
                assert CASE_TABLES.issubset(set(inspect(engine).get_table_names()))
                assert_head_schema(engine)
        finally:
            engine.dispose()

def test_duplicate_external_uid_same_snapshot(sqlite_migrated):
    engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        snap, _ = _bootstrap_snapshot(session, slot="s", seq=1)
        _add_org(session, snap, "U_1")
        session.add(
            CaseOrg(
                id=_uid(),
                snapshot_id=snap.id,
                external_uid="U_1",
                has_catalog_profile=False,
                profile_resolution="absent",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_identity_link_unique_and_no_membership(sqlite_migrated):
    engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        company = _company(session, "Linked")
        snap, _ = _bootstrap_snapshot(session, slot="s", seq=1)
        _add_org(session, snap, "U_1")
        session.add(
            CaseOrgCompanyLink(
                id=_uid(),
                slot_key="s",
                external_uid="U_1",
                company_id=company.id,
                linked_at=datetime.now(timezone.utc),
            )
        )
        session.flush()
        session.add(
            CaseOrgCompanyLink(
                id=_uid(),
                slot_key="s",
                external_uid="U_1",
                company_id=company.id,
                linked_at=datetime.now(timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    with SessionLocal() as session:
        company = _company(session, "Linked2")
        snap, _ = _bootstrap_snapshot(session, slot="s2", seq=1)
        _add_org(session, snap, "U_9")
        session.add(
            CaseOrgCompanyLink(
                id=_uid(),
                slot_key="s2",
                external_uid="U_9",
                company_id=company.id,
                linked_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        assert session.query(CompanyMembership).filter_by(company_id=company.id).count() == 0


def test_identity_survives_next_snapshot_slots_independent(sqlite_migrated):
    engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        company_a = _company(session, "A")
        company_b = _company(session, "B")
        snap1, _ = _bootstrap_snapshot(session, slot="slot_a", seq=1, status="active")
        _add_org(session, snap1, "U_SHARED")
        session.add(
            CaseOrgCompanyLink(
                id=_uid(),
                slot_key="slot_a",
                external_uid="U_SHARED",
                company_id=company_a.id,
                linked_at=datetime.now(timezone.utc),
            )
        )
        session.flush()

        snap2, _ = _bootstrap_snapshot(session, slot="slot_a", seq=2, status="building")
        _add_org(session, snap2, "U_SHARED")
        links = (
            session.query(CaseOrgCompanyLink)
            .filter_by(slot_key="slot_a", external_uid="U_SHARED")
            .all()
        )
        assert len(links) == 1
        assert links[0].company_id == company_a.id

        snap_b, _ = _bootstrap_snapshot(session, slot="slot_b", seq=1)
        _add_org(session, snap_b, "U_SHARED")
        session.add(
            CaseOrgCompanyLink(
                id=_uid(),
                slot_key="slot_b",
                external_uid="U_SHARED",
                company_id=company_b.id,
                linked_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        assert session.query(CaseOrgCompanyLink).count() == 2


def test_active_pointer_rejects_foreign_slot(sqlite_migrated):
    engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        snap_a, _ = _bootstrap_snapshot(session, slot="slot_a", seq=1, status="active")
        _bootstrap_snapshot(session, slot="slot_b", seq=1, status="building")
        session.add(
            CaseActiveSnapshot(
                slot_key="slot_b",
                active_snapshot_id=snap_a.id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_one_active_snapshot_per_slot(sqlite_migrated):
    engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        _bootstrap_snapshot(session, slot="one", seq=1, status="active")
        session.flush()
        with pytest.raises(IntegrityError):
            _bootstrap_snapshot(session, slot="one", seq=2, status="active")


def test_cross_snapshot_payment_and_person_link_rejected(sqlite_migrated):
    engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        snap1, run1 = _bootstrap_snapshot(session, slot="x", seq=1)
        snap2, _ = _bootstrap_snapshot(session, slot="x", seq=2)
        org1b = _add_org(session, snap1, "U_B")
        org2p = _add_org(session, snap2, "U_P")
        session.add(
            CasePayment(
                id=_uid(),
                snapshot_id=snap1.id,
                import_run_id=run1.id,
                source_file="df_Uid_payment_hack.csv",
                source_row_number=1,
                row_content_sha256="a" * 64,
                payer_org_id=org2p.id,
                beneficiary_org_id=org1b.id,
                pay_amt_raw="1000.0",
                pay_amt=Decimal("1000.0"),
                pay_amt_parse_status="ok",
                pay_cnt_raw="1",
                pay_cnt=1,
                pay_cnt_parse_status="ok",
                is_self_pay=False,
                intra_file_dup_rank=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    with SessionLocal() as session:
        s1, r1 = _bootstrap_snapshot(session, slot="plink", seq=1)
        s2, _ = _bootstrap_snapshot(session, slot="plink", seq=2)
        org1 = _add_org(session, s1, "U_1")
        person2 = CasePerson(id=_uid(), snapshot_id=s2.id, external_fid="F_1")
        session.add(person2)
        session.flush()
        session.add(
            CasePersonOrgLink(
                id=_uid(),
                snapshot_id=s1.id,
                import_run_id=r1.id,
                source_file="df_Fid_Uid_link_hack.csv",
                source_row_number=1,
                person_id=person2.id,
                case_org_id=org1.id,
                relation_kind="unspecified",
                org_had_catalog_at_import=False,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_duplicate_payment_rows_and_null_units(sqlite_migrated):
    engine, SessionLocal = sqlite_migrated
    with SessionLocal() as session:
        snap, run = _bootstrap_snapshot(session, slot="pay", seq=1)
        payer = _add_org(session, snap, "U_A")
        bene = _add_org(session, snap, "U_B")
        sha = "b" * 64
        for rank, row_no in ((1, 1), (2, 2)):
            session.add(
                CasePayment(
                    id=_uid(),
                    snapshot_id=snap.id,
                    import_run_id=run.id,
                    source_file="df_Uid_payment_hack.csv",
                    source_row_number=row_no,
                    row_content_sha256=sha,
                    payer_org_id=payer.id,
                    beneficiary_org_id=bene.id,
                    pay_amt_raw="5000.0",
                    pay_amt=Decimal("5000.0"),
                    pay_amt_parse_status="ok",
                    pay_cnt_raw="1",
                    pay_cnt=1,
                    pay_cnt_parse_status="ok",
                    amount_unit=None,
                    amount_currency=None,
                    period_label=None,
                    is_self_pay=False,
                    intra_file_dup_rank=rank,
                )
            )
        session.add(
            CasePayment(
                id=_uid(),
                snapshot_id=snap.id,
                import_run_id=run.id,
                source_file="df_Uid_payment_hack.csv",
                source_row_number=3,
                row_content_sha256="c" * 64,
                payer_org_id=payer.id,
                beneficiary_org_id=bene.id,
                pay_amt_raw="bad",
                pay_amt=None,
                pay_amt_parse_status="error",
                pay_amt_parse_error="invalid_format",
                pay_cnt_raw="1",
                pay_cnt=1,
                pay_cnt_parse_status="ok",
                is_self_pay=False,
                intra_file_dup_rank=1,
            )
        )
        org = _add_org(session, snap, "U_R", catalog=True)
        session.add(
            CaseOrgCatalogRow(
                id=_uid(),
                snapshot_id=snap.id,
                import_run_id=run.id,
                case_org_id=org.id,
                source_file="df_Uid_data_hack.csv",
                source_row_number=1,
                row_content_sha256="d" * 64,
                revenue_raw="1000.0",
                revenue_amount=Decimal("1000.0"),
                revenue_parse_status="ok",
                revenue_unit=None,
                revenue_currency=None,
                raw_json={"SYNTHETIC_U": "U_R"},
            )
        )
        session.commit()

        rows = session.query(CasePayment).filter_by(snapshot_id=snap.id).order_by(
            CasePayment.source_row_number
        ).all()
        assert len(rows) == 3
        assert rows[0].intra_file_dup_rank == 1 and rows[1].intra_file_dup_rank == 2
        assert rows[0].row_content_sha256 == rows[1].row_content_sha256
        assert all(r.amount_unit is None and r.amount_currency is None for r in rows)
        assert rows[2].pay_amt is None and rows[2].pay_amt_parse_status == "error"
        cat = session.query(CaseOrgCatalogRow).one()
        assert cat.revenue_unit is None and cat.revenue_currency is None


def test_postgres_case_schema_optional():
    db_url = os.getenv("ALEMBIC_POSTGRES_URL")
    if not db_url:
        pytest.skip("ALEMBIC_POSTGRES_URL not set — PostgreSQL case schema not verified")

    name = (urlparse(db_url).path or "").lstrip("/").split("?", 1)[0]
    if not name.endswith("_test"):
        pytest.fail(f"Refusing non-test Postgres DB name {name!r}")

    with with_db_url(db_url):
        engine = create_engine(db_url, poolclass=NullPool)
        inspector = inspect(engine)
        with engine.begin() as conn:
            for table in reversed(inspector.get_table_names()):
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
        engine.dispose()

        command.upgrade(alembic_config(), "head")
        engine = create_engine(db_url, poolclass=NullPool)
        assert CASE_TABLES.issubset(set(inspect(engine).get_table_names()))
        assert_head_schema(engine)
        assert ALEMBIC_HEAD == "011"
        engine.dispose()