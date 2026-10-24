"""Payment loader: temporary SQLite only; no application DATABASE_URL writes."""

from __future__ import annotations

import os
import time
import tracemalloc
import uuid
from datetime import datetime, timezone
from decimal import Decimal
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
    CasePayment,
    CaseSnapshot,
    Company,
    CompanyMembership,
)
from app.services.case_data.csv_io import payment_content_sha256, sha256_file
from app.services.case_data.load_org_catalog import (
    ContentHashMismatchError,
    ContextMismatchError,
    SnapshotNotBuildingError,
)
from app.services.case_data.load_payments import (
    IncompletePaymentImportError,
    PaymentValidationError,
    load_payments,
)

ROOT = Path(__file__).resolve().parents[1]

PAY_HEADER = "BENEFICIARY;PAYER;PAY_AMT;PAY_CNT"


def _uid() -> str:
    return str(uuid.uuid4())


def _pay(ben: str, payer: str, amt: str = "100.0", cnt: str = "1") -> str:
    return f"{ben};{payer};{amt};{cnt}"


def _write_csv(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PAY_HEADER + "\n" + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture
def db_session(tmp_path: Path):
    db_path = tmp_path / "pay_loader.db"
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
    session: Session, csv_path: Path, *, slot: str = "pay_slot", seq: int = 1
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


def _add_catalog_org(
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


def test_both_parties_known(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "both.csv", [_pay("U_1", "U_2", "250.5", "3")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    o1 = _add_catalog_org(db_session, snap, "U_1")
    o2 = _add_catalog_org(db_session, snap, "U_2")
    result = load_payments(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()

    assert result.rows_inserted == 1
    assert result.orgs_created == 0
    pay = db_session.scalars(select(CasePayment)).one()
    assert pay.beneficiary_org_id == o1.id
    assert pay.payer_org_id == o2.id
    assert pay.pay_amt == Decimal("250.5")
    assert pay.pay_amt_raw == "250.5"
    assert pay.pay_cnt == 3
    assert pay.pay_cnt_raw == "3"
    assert pay.amount_unit is None and pay.amount_currency is None and pay.period_label is None
    assert pay.is_self_pay is False
    assert pay.intra_file_dup_rank == 1
    assert pay.semantics_note == "payment_aggregate_only"


def test_one_and_both_orphans(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "orph.csv",
        [_pay("U_10", "U_20"), _pay("U_30", "U_40")],
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    known = _add_catalog_org(db_session, snap, "U_10")
    result = load_payments(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()

    assert result.orgs_created == 3  # U_20, U_30, U_40
    orgs = {o.external_uid: o for o in db_session.scalars(select(CaseOrg)).all()}
    assert orgs["U_10"].id == known.id
    assert orgs["U_10"].has_catalog_profile is True
    for uid in ("U_20", "U_30", "U_40"):
        assert orgs[uid].has_catalog_profile is False
        assert orgs[uid].profile_resolution == "absent"
    assert db_session.scalar(select(func.count()).select_from(CasePayment)) == 2


def test_self_payment(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "self.csv", [_pay("U_5", "U_5", "10.0", "2")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    result = load_payments(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    assert result.self_pay_rows == 1
    pay = db_session.scalars(select(CasePayment)).one()
    assert pay.is_self_pay is True
    assert pay.payer_org_id == pay.beneficiary_org_id
    assert db_session.scalar(select(func.count()).select_from(CaseOrg)) == 1


def test_same_uid_across_batches_one_org(db_session: Session, tmp_path: Path):
    lines = [_pay("U_1", "U_2", f"{i}.0", "1") for i in range(1, 6)]
    csv_path = _write_csv(tmp_path / "batches.csv", lines)
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_payments(
        db_session,
        snapshot=snap,
        import_run=run,
        import_file=imp,
        csv_path=csv_path,
        batch_size=2,
    )
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(CaseOrg)) == 2
    assert db_session.scalar(select(func.count()).select_from(CasePayment)) == 5


def test_duplicates_within_and_across_batches(db_session: Session, tmp_path: Path):
    identical = _pay("U_1", "U_2", "50.0", "4")
    # ranks: 1,2 in first batches; gap; then 3 after other rows
    lines = [
        identical,
        identical,
        _pay("U_3", "U_4", "1.0", "1"),
        _pay("U_5", "U_6", "2.0", "1"),
        identical,
    ]
    csv_path = _write_csv(tmp_path / "dups.csv", lines)
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_payments(
        db_session,
        snapshot=snap,
        import_run=run,
        import_file=imp,
        csv_path=csv_path,
        batch_size=2,
    )
    db_session.commit()

    sha = payment_content_sha256("U_1", "U_2", "50.0", "4")
    dups = db_session.scalars(
        select(CasePayment)
        .where(CasePayment.row_content_sha256 == sha)
        .order_by(CasePayment.source_row_number)
    ).all()
    assert [d.intra_file_dup_rank for d in dups] == [1, 2, 3]
    assert db_session.scalar(select(func.count()).select_from(CasePayment)) == 5


def test_same_pair_different_amt_or_cnt(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "variants.csv",
        [
            _pay("U_1", "U_2", "10.0", "1"),
            _pay("U_1", "U_2", "20.0", "1"),
            _pay("U_1", "U_2", "10.0", "2"),
        ],
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_payments(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    rows = db_session.scalars(
        select(CasePayment).order_by(CasePayment.source_row_number)
    ).all()
    assert len(rows) == 3
    assert len({r.row_content_sha256 for r in rows}) == 3
    assert all(r.intra_file_dup_rank == 1 for r in rows)


def test_decimal_precision_and_raw(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "dec.csv", [_pay("U_1", "U_2", "1234567890123.0", "7")]
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    load_payments(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    db_session.expire_all()
    pay = db_session.scalars(select(CasePayment)).one()
    assert pay.pay_amt_raw == "1234567890123.0"
    assert pay.pay_amt == Decimal("1234567890123.0")
    assert isinstance(pay.pay_amt, Decimal)
    assert pay.pay_cnt == 7
    assert pay.pay_cnt_raw == "7"


def test_invalid_id_amt_cnt_block(db_session: Session, tmp_path: Path):
    bad_id = _write_csv(tmp_path / "bad_id.csv", [_pay("X_1", "U_2")])
    snap, run, imp = _bootstrap_building(db_session, bad_id)
    with pytest.raises(PaymentValidationError) as ei:
        load_payments(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=bad_id
        )
    assert ei.value.field == "BENEFICIARY"
    db_session.rollback()

    bad_amt = _write_csv(tmp_path / "bad_amt.csv", [_pay("U_1", "U_2", "1.23", "1")])
    snap, run, imp = _bootstrap_building(db_session, bad_amt, slot="a", seq=1)
    with pytest.raises(PaymentValidationError) as ei:
        load_payments(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=bad_amt
        )
    assert ei.value.field == "PAY_AMT"
    assert ei.value.reason == "too_many_fraction_digits"
    db_session.rollback()

    bad_cnt = _write_csv(tmp_path / "bad_cnt.csv", [_pay("U_1", "U_2", "1.0", "0")])
    snap, run, imp = _bootstrap_building(db_session, bad_cnt, slot="c", seq=1)
    with pytest.raises(PaymentValidationError) as ei:
        load_payments(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=bad_cnt
        )
    assert ei.value.field == "PAY_CNT"


def test_completed_skip_partial_error_hash_mismatch(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "once.csv", [_pay("U_1", "U_2"), _pay("U_3", "U_4")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    r1 = load_payments(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    db_session.refresh(imp)
    r2 = load_payments(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    assert r1.skipped is False and r1.rows_inserted == 2
    assert r2.skipped is True and r2.reason == "already_completed_same_hash"
    assert db_session.scalar(select(func.count()).select_from(CasePayment)) == 2

    # wrong counter
    imp.row_count_loaded = 99
    db_session.flush()
    with pytest.raises(IncompletePaymentImportError):
        load_payments(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
        )
    db_session.rollback()
    db_session.refresh(imp)

    # partial without completed
    csv2 = _write_csv(tmp_path / "partial.csv", [_pay("U_9", "U_8")])
    snap2, run2, imp2 = _bootstrap_building(db_session, csv2, slot="partial", seq=1)
    org = CaseOrg(
        id=_uid(),
        snapshot_id=snap2.id,
        external_uid="U_9",
        has_catalog_profile=False,
        profile_resolution="absent",
    )
    db_session.add(org)
    db_session.flush()
    db_session.add(
        CasePayment(
            id=_uid(),
            snapshot_id=snap2.id,
            import_run_id=run2.id,
            source_file=imp2.source_file,
            source_row_number=1,
            row_content_sha256="b" * 64,
            payer_org_id=org.id,
            beneficiary_org_id=org.id,
            pay_amt_raw="1.0",
            pay_amt=Decimal("1.0"),
            pay_amt_parse_status="ok",
            pay_cnt_raw="1",
            pay_cnt=1,
            pay_cnt_parse_status="ok",
            is_self_pay=True,
            intra_file_dup_rank=1,
        )
    )
    imp2.status = "pending"
    db_session.flush()
    with pytest.raises(IncompletePaymentImportError):
        load_payments(
            db_session, snapshot=snap2, import_run=run2, import_file=imp2, csv_path=csv2
        )
    db_session.rollback()

    # hash mismatch
    csv_a = _write_csv(tmp_path / "ha.csv", [_pay("U_1", "U_2")])
    csv_b = _write_csv(tmp_path / "hb.csv", [_pay("U_3", "U_4")])
    snap, run, imp = _bootstrap_building(db_session, csv_a, slot="hash", seq=1)
    with pytest.raises(ContentHashMismatchError):
        load_payments(
            db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_b
        )


def test_reject_active_and_mismatched_context(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "act.csv", [_pay("U_1", "U_2")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    snap.status = "active"
    db_session.flush()
    with pytest.raises(SnapshotNotBuildingError):
        load_payments(
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
        load_payments(
            db_session, snapshot=snap, import_run=other, import_file=imp, csv_path=csv_path
        )


def test_batch_error_then_rollback_leaves_nothing(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "batch.csv",
        [_pay("U_1", "U_2"), _pay("U_3", "BAD")],
    )
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    db_session.commit()
    db_session.refresh(snap)
    db_session.refresh(run)
    db_session.refresh(imp)
    with pytest.raises(PaymentValidationError):
        load_payments(
            db_session,
            snapshot=snap,
            import_run=run,
            import_file=imp,
            csv_path=csv_path,
            batch_size=1,
        )
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(CasePayment)) == 0
    assert db_session.scalar(select(func.count()).select_from(CaseOrg)) == 0
    db_session.refresh(imp)
    assert imp.status == "pending"


def test_active_pointer_and_company_untouched(db_session: Session, tmp_path: Path):
    active_csv = _write_csv(tmp_path / "active.csv", [_pay("U_100", "U_101")])
    active_snap, active_run, active_file = _bootstrap_building(
        db_session, active_csv, slot="slot_a"
    )
    load_payments(
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

    building_csv = _write_csv(tmp_path / "building.csv", [_pay("U_200", "U_201")])
    bad_path = tmp_path / "tampered.csv"
    bad_path.write_text("not;payments\n", encoding="utf-8")
    b_snap, b_run, b_file = _bootstrap_building(
        db_session, building_csv, slot="slot_a", seq=2
    )
    with pytest.raises(ContentHashMismatchError):
        load_payments(
            db_session,
            snapshot=b_snap,
            import_run=b_run,
            import_file=b_file,
            csv_path=bad_path,
        )
    db_session.rollback()

    ptr = db_session.get(CaseActiveSnapshot, "slot_a")
    assert ptr is not None and ptr.active_snapshot_id == active_snap.id
    assert db_session.get(CaseSnapshot, active_snap.id).status == "active"
    assert db_session.scalars(select(Company)).first() is None
    assert db_session.scalars(select(CompanyMembership)).first() is None
    assert db_session.scalars(select(CaseOrgCompanyLink)).first() is None


def test_existing_profile_not_mutated(db_session: Session, tmp_path: Path):
    csv_path = _write_csv(tmp_path / "prof.csv", [_pay("U_1", "U_2")])
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    org = _add_catalog_org(db_session, snap, "U_1", has_profile=True, resolution="consensus")
    load_payments(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    db_session.refresh(org)
    assert org.has_catalog_profile is True
    assert org.profile_resolution == "consensus"


def test_empty_file_completed_then_skip(db_session: Session, tmp_path: Path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text(PAY_HEADER + "\n", encoding="utf-8", newline="\n")
    snap, run, imp = _bootstrap_building(db_session, csv_path)
    r1 = load_payments(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    db_session.commit()
    db_session.refresh(imp)
    assert r1.rows_inserted == 0
    assert imp.status == "completed" and imp.row_count_loaded == 0
    r2 = load_payments(
        db_session, snapshot=snap, import_run=run, import_file=imp, csv_path=csv_path
    )
    assert r2.skipped is True


def test_synthetic_50k_timing_and_tracemalloc(db_session: Session, tmp_path: Path):
    """Limited synthetic scale check. tracemalloc ≠ process RSS; not full real volume."""
    n = 50_000
    csv_path = tmp_path / "synth_50k.csv"
    with csv_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(PAY_HEADER + "\n")
        for i in range(n):
            # Mix of unique pairs and occasional identical content for dup ranks.
            if i % 1000 == 0:
                f.write(_pay("U_1", "U_2", "9.0", "1") + "\n")
            else:
                f.write(_pay(f"U_{i}", f"U_{i + 1}", f"{(i % 100) + 1}.0", "1") + "\n")

    snap, run, imp = _bootstrap_building(db_session, csv_path)
    tracemalloc.start()
    t0 = time.perf_counter()
    result = load_payments(
        db_session,
        snapshot=snap,
        import_run=run,
        import_file=imp,
        csv_path=csv_path,
        batch_size=500,
    )
    elapsed = time.perf_counter() - t0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    db_session.commit()

    assert result.rows_inserted == n
    assert db_session.scalar(select(func.count()).select_from(CasePayment)) == n
    # Persist metrics for the stage report (not RSS).
    metrics_path = tmp_path / "synth_50k_metrics.txt"
    metrics_path.write_text(
        f"rows={n}\n"
        f"elapsed_sec={elapsed:.3f}\n"
        f"tracemalloc_peak_bytes={peak}\n"
        f"note=tracemalloc_is_not_process_RSS_and_not_full_real_volume\n",
        encoding="utf-8",
    )
    assert elapsed > 0
    assert peak > 0
    # Sanity: identical U_1→U_2 rows get increasing ranks
    sha = payment_content_sha256("U_1", "U_2", "9.0", "1")
    ranks = db_session.scalars(
        select(CasePayment.intra_file_dup_rank)
        .where(CasePayment.row_content_sha256 == sha)
        .order_by(CasePayment.source_row_number)
    ).all()
    assert ranks == list(range(1, len(ranks) + 1))
    assert len(ranks) == 50  # every 1000th of 50k
