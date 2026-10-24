"""Snapshot activation: synthetic data on temporary SQLite only."""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.jobs import activate_case_snapshot as activate_job
from app.jobs import import_case_data as import_job
from app.models import (
    CaseActiveSnapshot,
    CaseImportFile,
    CaseImportRun,
    CaseOrg,
    CaseSnapshot,
)
from app.services.case_data import activate_snapshot as act_mod
from app.services.case_data.activate_snapshot import (
    ActivationConflictError,
    ActivationIntegrityError,
    ActivationPreconditionError,
    NoActiveSnapshot,
    activate_case_snapshot,
    get_active_snapshot,
    run_activation,
)

ROOT = Path(__file__).resolve().parents[1]


def _uid() -> str:
    return str(uuid.uuid4())


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "activate.db"
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


def _seed_ready(
    session: Session,
    *,
    slot: str,
    label: str,
    seq: int,
    incomplete: bool = False,
    bad_report: bool = False,
    status: str = "ready",
) -> CaseSnapshot:
    snap_id, run_id = _uid(), _uid()
    snap = CaseSnapshot(
        id=snap_id,
        slot_key=slot,
        version_label=label,
        version_seq=seq,
        status=status if status != "ready" else "building",
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
    for name in (
        "companies.csv",
        "payments.csv",
        "links.csv",
    ):
        session.add(
            CaseImportFile(
                id=_uid(),
                import_run_id=run_id,
                source_file=name,
                content_sha256="a" * 64,
                byte_size=10,
                row_count_loaded=0 if incomplete else 1,
                status="pending" if incomplete else "completed",
            )
        )
    if not incomplete and not bad_report and status == "ready":
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
                {"role": "companies", "source_file": "companies.csv", "record_count": 1},
                {"role": "payments", "source_file": "payments.csv", "record_count": 1},
                {"role": "person_links", "source_file": "links.csv", "record_count": 1},
            ],
        }
    elif status != "ready":
        snap.status = status
        if status == "failed":
            run.status = "failed"
    elif incomplete:
        run.status = "running"
        snap.status = "building"
    elif bad_report:
        run.status = "completed"
        snap.status = "ready"
        snap.validation_report_json = {"note": "missing final_checks"}
    session.flush()
    return snap


def test_first_activation(db_url: str):
    with _session(db_url) as s:
        snap = _seed_ready(s, slot="slot_a", label="v1", seq=1)
        s.commit()
        sid = snap.id

    result = run_activation(
        database_url=db_url,
        slot_key="slot_a",
        snapshot_id=sid,
        expect_no_active=True,
    )
    assert result.outcome == "activated"
    assert result.previous_snapshot_id is None
    assert result.current_snapshot_id == sid

    with _session(db_url) as s:
        ref = get_active_snapshot(s, slot_key="slot_a")
        assert not isinstance(ref, NoActiveSnapshot)
        assert ref.snapshot_id == sid
        assert s.get(CaseSnapshot, sid).status == "active"
        assert s.get(CaseActiveSnapshot, "slot_a").active_snapshot_id == sid


def test_switch_a_to_b_and_idempotent_b(db_url: str):
    with _session(db_url) as s:
        a = _seed_ready(s, slot="slot_a", label="v1", seq=1)
        b = _seed_ready(s, slot="slot_a", label="v2", seq=2)
        s.commit()
        a_id, b_id = a.id, b.id

    r1 = run_activation(
        database_url=db_url, slot_key="slot_a", snapshot_id=a_id, expect_no_active=True
    )
    assert r1.outcome == "activated"
    activated_at = None
    with _session(db_url) as s:
        activated_at = s.get(CaseSnapshot, a_id).activated_at

    r2 = run_activation(
        database_url=db_url,
        slot_key="slot_a",
        snapshot_id=b_id,
        expected_active_snapshot_id=a_id,
    )
    assert r2.outcome == "activated"
    assert r2.previous_snapshot_id == a_id
    assert r2.current_snapshot_id == b_id

    with _session(db_url) as s:
        assert s.get(CaseSnapshot, a_id).status == "retired"
        assert s.get(CaseSnapshot, a_id).retired_at is not None
        b_snap = s.get(CaseSnapshot, b_id)
        assert b_snap.status == "active"
        b_activated = b_snap.activated_at

    r3 = run_activation(
        database_url=db_url,
        slot_key="slot_a",
        snapshot_id=b_id,
        expected_active_snapshot_id=b_id,
    )
    assert r3.outcome == "already_active"
    with _session(db_url) as s:
        assert s.get(CaseSnapshot, b_id).activated_at == b_activated
        # A timestamps unchanged by no-op on B
        assert s.get(CaseSnapshot, a_id).activated_at == activated_at


def test_wrong_slot_and_bad_statuses(db_url: str):
    with _session(db_url) as s:
        snap = _seed_ready(s, slot="slot_a", label="v1", seq=1)
        building = _seed_ready(s, slot="slot_a", label="v2", seq=2, status="building")
        failed = _seed_ready(s, slot="slot_b", label="v1", seq=1, status="failed")
        s.commit()
        sid, bid, fid = snap.id, building.id, failed.id

    with pytest.raises(ActivationPreconditionError):
        run_activation(
            database_url=db_url, slot_key="other", snapshot_id=sid, expect_no_active=True
        )
    with pytest.raises(ActivationPreconditionError):
        run_activation(
            database_url=db_url, slot_key="slot_a", snapshot_id=bid, expect_no_active=True
        )
    with pytest.raises(ActivationPreconditionError):
        run_activation(
            database_url=db_url, slot_key="slot_b", snapshot_id=fid, expect_no_active=True
        )


def test_incomplete_import_and_bad_final_report(db_url: str):
    with _session(db_url) as s:
        inc = _seed_ready(s, slot="slot_a", label="v1", seq=1, incomplete=True)
        bad = _seed_ready(s, slot="slot_a", label="v2", seq=2, bad_report=True)
        s.commit()
        iid, bid = inc.id, bad.id

    with pytest.raises(ActivationPreconditionError):
        run_activation(
            database_url=db_url, slot_key="slot_a", snapshot_id=iid, expect_no_active=True
        )
    with pytest.raises(ActivationPreconditionError):
        run_activation(
            database_url=db_url, slot_key="slot_a", snapshot_id=bid, expect_no_active=True
        )


def test_stale_expected_active_id(db_url: str):
    with _session(db_url) as s:
        a = _seed_ready(s, slot="slot_a", label="v1", seq=1)
        b = _seed_ready(s, slot="slot_a", label="v2", seq=2)
        s.commit()
        a_id, b_id = a.id, b.id
    run_activation(
        database_url=db_url, slot_key="slot_a", snapshot_id=a_id, expect_no_active=True
    )
    with pytest.raises(ActivationConflictError):
        run_activation(
            database_url=db_url,
            slot_key="slot_a",
            snapshot_id=b_id,
            expected_active_snapshot_id="00000000-0000-0000-0000-000000000099",
        )


def test_injected_failure_rolls_back(db_url: str):
    with _session(db_url) as s:
        a = _seed_ready(s, slot="slot_a", label="v1", seq=1)
        b = _seed_ready(s, slot="slot_a", label="v2", seq=2)
        org = CaseOrg(
            id=_uid(),
            snapshot_id=a.id,
            external_uid="U_1",
            has_catalog_profile=False,
            profile_resolution="absent",
        )
        s.add(org)
        s.commit()
        a_id, b_id, org_id = a.id, b.id, org.id

    run_activation(
        database_url=db_url, slot_key="slot_a", snapshot_id=a_id, expect_no_active=True
    )
    act_mod._test_fail_before_pointer = True
    try:
        with pytest.raises(RuntimeError, match="injected"):
            run_activation(
                database_url=db_url,
                slot_key="slot_a",
                snapshot_id=b_id,
                expected_active_snapshot_id=a_id,
            )
    finally:
        act_mod._test_fail_before_pointer = False

    with _session(db_url) as s:
        assert s.get(CaseSnapshot, a_id).status == "active"
        assert s.get(CaseSnapshot, b_id).status == "ready"
        assert s.get(CaseActiveSnapshot, "slot_a").active_snapshot_id == a_id
        # Old domain data intact
        assert s.get(CaseOrg, org_id) is not None
        assert s.scalar(select(func.count()).select_from(CaseOrg)) == 1


def test_pointer_status_contradiction_refused(db_url: str):
    with _session(db_url) as s:
        a = _seed_ready(s, slot="slot_a", label="v1", seq=1)
        b = _seed_ready(s, slot="slot_a", label="v2", seq=2)
        s.commit()
        a_id, b_id = a.id, b.id
    run_activation(
        database_url=db_url, slot_key="slot_a", snapshot_id=a_id, expect_no_active=True
    )
    # Corrupt: pointer still A, but force A to retired without updating pointer.
    with _session(db_url) as s:
        s.execute(
            text("UPDATE case_snapshots SET status='retired' WHERE id=:id"),
            {"id": a_id},
        )
        s.commit()

    with pytest.raises(ActivationIntegrityError):
        run_activation(
            database_url=db_url,
            slot_key="slot_a",
            snapshot_id=b_id,
            expected_active_snapshot_id=a_id,
        )
    with pytest.raises(ActivationIntegrityError):
        with _session(db_url) as s:
            get_active_snapshot(s, slot_key="slot_a")


def test_concurrent_switch_one_wins(db_url: str, tmp_path: Path):
    """Two connections: one activates B, the other with stale expected conflicts."""
    with _session(db_url) as s:
        a = _seed_ready(s, slot="slot_a", label="v1", seq=1)
        b = _seed_ready(s, slot="slot_a", label="v2", seq=2)
        c = _seed_ready(s, slot="slot_a", label="v3", seq=3)
        s.commit()
        a_id, b_id, c_id = a.id, b.id, c.id
    run_activation(
        database_url=db_url, slot_key="slot_a", snapshot_id=a_id, expect_no_active=True
    )

    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def worker(name: str, target: str) -> None:
        try:
            barrier.wait(timeout=10)
            outcomes[name] = run_activation(
                database_url=db_url,
                slot_key="slot_a",
                snapshot_id=target,
                expected_active_snapshot_id=a_id,
            )
        except Exception as exc:  # noqa: BLE001
            outcomes[name] = exc

    t1 = threading.Thread(target=worker, args=("b", b_id))
    t2 = threading.Thread(target=worker, args=("c", c_id))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    results = list(outcomes.values())
    successes = [r for r in results if not isinstance(r, Exception)]
    conflicts = [r for r in results if isinstance(r, ActivationConflictError)]
    # Under SQLite serialization one may also see OperationalError (locked); treat as conflict-ish
    others = [
        r
        for r in results
        if isinstance(r, Exception) and not isinstance(r, ActivationConflictError)
    ]
    assert len(successes) == 1, outcomes
    assert successes[0].outcome == "activated"
    assert len(conflicts) + len(others) == 1, outcomes

    with _session(db_url) as s:
        actives = s.scalars(
            select(CaseSnapshot).where(
                CaseSnapshot.slot_key == "slot_a", CaseSnapshot.status == "active"
            )
        ).all()
        assert len(actives) == 1
        assert s.get(CaseActiveSnapshot, "slot_a").active_snapshot_id == actives[0].id
        assert actives[0].id in {b_id, c_id}


def test_cli_requires_expect_and_database_url(db_url: str):
    with _session(db_url) as s:
        snap = _seed_ready(s, slot="slot_cli", label="v1", seq=1)
        s.commit()
        sid = snap.id
    with pytest.raises(SystemExit):
        activate_job.main([])
    # Missing expect flags → argparse mutually exclusive group required
    with pytest.raises(SystemExit):
        activate_job.main(
            [
                "--database-url",
                db_url,
                "--slot-key",
                "slot_cli",
                "--snapshot-id",
                sid,
            ]
        )
    code = activate_job.main(
        [
            "--database-url",
            db_url,
            "--slot-key",
            "slot_cli",
            "--snapshot-id",
            sid,
            "--expect-no-active",
        ]
    )
    assert code == 0


def test_import_cli_does_not_activate():
    # Import without --load/--dry-run still refuses; no activation path.
    assert import_job.main([]) == 2


def test_postgres_concurrency_not_configured():
    """Document: PostgreSQL race test skipped unless ALEMBIC_POSTGRES_URL is set."""
    if not os.environ.get("ALEMBIC_POSTGRES_URL"):
        pytest.skip("ALEMBIC_POSTGRES_URL not set — PostgreSQL concurrency not verified")
