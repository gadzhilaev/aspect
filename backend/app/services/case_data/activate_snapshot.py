"""Atomic activation of a ready case snapshot (does not import data)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import create_engine, event, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.case_data import (
    CaseActiveSnapshot,
    CaseImportFile,
    CaseImportRun,
    CaseSnapshot,
)


class ActivationError(Exception):
    """Base activation error."""


class ActivationPreconditionError(ActivationError):
    pass


class ActivationConflictError(ActivationError):
    """Expected active pointer no longer matches (stale request / race)."""


class ActivationIntegrityError(ActivationError):
    """Pointer and status disagree; refuse to auto-repair."""


Outcome = Literal["activated", "already_active"]

# Test-only: when True, raise after status updates and before pointer write.
_test_fail_before_pointer: bool = False


@dataclass(frozen=True, slots=True)
class ActivationResult:
    outcome: Outcome
    slot_key: str
    previous_snapshot_id: str | None
    current_snapshot_id: str
    activated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ActiveSnapshotRef:
    """Stable snapshot id for one read pass (do not re-resolve mid-request)."""

    slot_key: str
    snapshot_id: str
    version_label: str
    version_seq: int
    status: str


@dataclass(frozen=True, slots=True)
class NoActiveSnapshot:
    slot_key: str
    reason: str


def get_active_snapshot(
    session: Session, *, slot_key: str
) -> ActiveSnapshotRef | NoActiveSnapshot:
    """Resolve the visible snapshot via ``case_active_snapshot``, not max(date).

    Validates pointer ↔ status consistency. Callers should keep ``snapshot_id``
    for the whole read pass so an activation mid-request cannot mix versions.
    """
    pointer = session.get(CaseActiveSnapshot, slot_key)
    actives = list(
        session.scalars(
            select(CaseSnapshot).where(
                CaseSnapshot.slot_key == slot_key,
                CaseSnapshot.status == "active",
            )
        ).all()
    )
    if len(actives) > 1:
        raise ActivationIntegrityError(
            f"slot {slot_key!r} has {len(actives)} rows with status=active"
        )

    if pointer is None or pointer.active_snapshot_id is None:
        if actives:
            raise ActivationIntegrityError(
                f"slot {slot_key!r} has active snapshot {actives[0].id} "
                "but active pointer is missing/NULL"
            )
        return NoActiveSnapshot(slot_key=slot_key, reason="no_active_pointer")

    snap = session.get(CaseSnapshot, pointer.active_snapshot_id)
    if snap is None:
        raise ActivationIntegrityError(
            f"pointer for {slot_key!r} references missing snapshot "
            f"{pointer.active_snapshot_id}"
        )
    if snap.slot_key != slot_key:
        raise ActivationIntegrityError(
            f"pointer snapshot {snap.id} belongs to slot {snap.slot_key!r}, "
            f"not {slot_key!r}"
        )
    if snap.status != "active":
        raise ActivationIntegrityError(
            f"pointer for {slot_key!r} points to {snap.id} with status={snap.status!r}, "
            "expected active"
        )
    if not actives or actives[0].id != snap.id:
        raise ActivationIntegrityError(
            f"pointer/status mismatch for slot {slot_key!r}: "
            f"pointer={snap.id}, active_rows={[a.id for a in actives]}"
        )
    return ActiveSnapshotRef(
        slot_key=slot_key,
        snapshot_id=snap.id,
        version_label=snap.version_label,
        version_seq=snap.version_seq,
        status=snap.status,
    )


def activate_case_snapshot(
    session: Session,
    *,
    slot_key: str,
    snapshot_id: str,
    expected_active_snapshot_id: str | None = None,
    expect_no_active: bool = False,
) -> ActivationResult:
    """Activate a ready snapshot in the current transaction.

    Caller owns commit/rollback. Acquire a DB-level slot lock first via
    ``acquire_activation_lock`` when using a fresh connection (CLI does this).

    Exactly one of ``expected_active_snapshot_id`` / ``expect_no_active`` must be set.
    """
    if expect_no_active and expected_active_snapshot_id is not None:
        raise ActivationPreconditionError(
            "pass either expect_no_active or expected_active_snapshot_id, not both"
        )
    if not expect_no_active and not expected_active_snapshot_id:
        raise ActivationPreconditionError(
            "expected_active_snapshot_id or expect_no_active is required"
        )
    if not slot_key.strip():
        raise ActivationPreconditionError("slot_key must be non-empty")

    now = datetime.now(timezone.utc)
    candidate = session.get(CaseSnapshot, snapshot_id)
    if candidate is None:
        raise ActivationPreconditionError(f"snapshot {snapshot_id} not found")
    if candidate.slot_key != slot_key:
        raise ActivationPreconditionError(
            f"snapshot {snapshot_id} belongs to slot {candidate.slot_key!r}, "
            f"not {slot_key!r}"
        )

    _assert_slot_integrity(session, slot_key)
    previous_id = _current_active_id(session, slot_key)
    _assert_expected(session, slot_key, previous_id, expected_active_snapshot_id, expect_no_active)

    # Idempotent: already the consistent active snapshot.
    if candidate.status == "active" and previous_id == candidate.id:
        return ActivationResult(
            outcome="already_active",
            slot_key=slot_key,
            previous_snapshot_id=previous_id,
            current_snapshot_id=candidate.id,
            activated_at=candidate.activated_at,
        )

    if candidate.status != "ready":
        raise ActivationPreconditionError(
            f"snapshot status is {candidate.status!r}; only ready can be activated "
            f"(building/failed/retired are refused)"
        )

    _assert_import_ready(session, candidate)

    # Order matters for partial UNIQUE (slot_key) WHERE status='active':
    # retire old active first, then promote ready → active, then update pointer.
    if previous_id is not None and previous_id != candidate.id:
        prev = session.get(CaseSnapshot, previous_id)
        if prev is None or prev.status != "active":
            raise ActivationIntegrityError(
                f"expected previous active {previous_id} not found or not active"
            )
        session.execute(
            update(CaseSnapshot)
            .where(CaseSnapshot.id == previous_id, CaseSnapshot.status == "active")
            .values(status="retired", retired_at=now)
        )

    updated = session.execute(
        update(CaseSnapshot)
        .where(
            CaseSnapshot.id == candidate.id,
            CaseSnapshot.status == "ready",
            CaseSnapshot.slot_key == slot_key,
        )
        .values(status="active", activated_at=now)
    )
    if updated.rowcount != 1:
        raise ActivationConflictError(
            f"snapshot {candidate.id} was no longer ready at activation time"
        )

    if _test_fail_before_pointer:
        raise RuntimeError("injected failure before pointer update")

    pointer = session.get(CaseActiveSnapshot, slot_key)
    if pointer is None:
        session.add(
            CaseActiveSnapshot(
                slot_key=slot_key,
                active_snapshot_id=candidate.id,
                updated_at=now,
            )
        )
    else:
        pointer.active_snapshot_id = candidate.id
        pointer.updated_at = now

    session.flush()
    # Re-check consistency after writes (same txn).
    _assert_slot_integrity(session, slot_key)
    return ActivationResult(
        outcome="activated",
        slot_key=slot_key,
        previous_snapshot_id=previous_id,
        current_snapshot_id=candidate.id,
        activated_at=now,
    )


def acquire_activation_lock(session: Session, *, slot_key: str) -> None:
    """DB-side lock so concurrent activators serialize (not process-local).

    SQLite: transaction must already be BEGIN IMMEDIATE (see ``run_activation``).
    PostgreSQL: transaction-scoped advisory lock on slot_key.
    """
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:slot))"),
            {"slot": slot_key},
        )


def make_activation_engine(database_url: str) -> Engine:
    engine = create_engine(database_url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def run_activation(
    *,
    database_url: str,
    slot_key: str,
    snapshot_id: str,
    expected_active_snapshot_id: str | None = None,
    expect_no_active: bool = False,
) -> ActivationResult:
    """Open a connection, lock the slot, activate, commit (or rollback on error)."""
    engine = make_activation_engine(database_url)
    try:
        with engine.connect() as conn:
            dialect = engine.dialect.name
            if dialect == "sqlite":
                # Reserved write lock before any decision reads (covers missing pointer).
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            session = Session(bind=conn, autoflush=False)
            try:
                acquire_activation_lock(session, slot_key=slot_key)
                result = activate_case_snapshot(
                    session,
                    slot_key=slot_key,
                    snapshot_id=snapshot_id,
                    expected_active_snapshot_id=expected_active_snapshot_id,
                    expect_no_active=expect_no_active,
                )
                session.flush()
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
            finally:
                session.close()
    finally:
        engine.dispose()


def _current_active_id(session: Session, slot_key: str) -> str | None:
    pointer = session.get(CaseActiveSnapshot, slot_key)
    if pointer is not None and pointer.active_snapshot_id:
        return pointer.active_snapshot_id
    active = session.scalar(
        select(CaseSnapshot.id).where(
            CaseSnapshot.slot_key == slot_key,
            CaseSnapshot.status == "active",
        )
    )
    return active


def _assert_expected(
    session: Session,
    slot_key: str,
    previous_id: str | None,
    expected_active_snapshot_id: str | None,
    expect_no_active: bool,
) -> None:
    if expect_no_active:
        if previous_id is not None:
            raise ActivationConflictError(
                f"expected no active snapshot for slot {slot_key!r}, "
                f"but found {previous_id}"
            )
        return
    assert expected_active_snapshot_id is not None
    if previous_id != expected_active_snapshot_id:
        raise ActivationConflictError(
            f"expected active {expected_active_snapshot_id}, current is {previous_id}"
        )


def _assert_slot_integrity(session: Session, slot_key: str) -> None:
    """Refuse contradictory pointer/status; do not repair."""
    pointer = session.get(CaseActiveSnapshot, slot_key)
    actives = list(
        session.scalars(
            select(CaseSnapshot).where(
                CaseSnapshot.slot_key == slot_key,
                CaseSnapshot.status == "active",
            )
        ).all()
    )
    if len(actives) > 1:
        raise ActivationIntegrityError(
            f"slot {slot_key!r} has multiple active snapshots: {[a.id for a in actives]}"
        )

    ptr_id = pointer.active_snapshot_id if pointer else None
    active_id = actives[0].id if actives else None

    if ptr_id is None and active_id is None:
        return
    if ptr_id is None and active_id is not None:
        raise ActivationIntegrityError(
            f"slot {slot_key!r}: status=active on {active_id} but pointer is empty"
        )
    if ptr_id is not None and active_id is None:
        snap = session.get(CaseSnapshot, ptr_id)
        status = snap.status if snap else "missing"
        raise ActivationIntegrityError(
            f"slot {slot_key!r}: pointer={ptr_id} status={status!r}, no active row"
        )
    if ptr_id != active_id:
        raise ActivationIntegrityError(
            f"slot {slot_key!r}: pointer={ptr_id} but active row={active_id}"
        )
    snap = session.get(CaseSnapshot, ptr_id)
    if snap is None or snap.slot_key != slot_key or snap.status != "active":
        raise ActivationIntegrityError(
            f"slot {slot_key!r}: pointer target inconsistent"
        )


def _assert_import_ready(session: Session, snap: CaseSnapshot) -> None:
    if not snap.import_run_id:
        raise ActivationPreconditionError("snapshot has no import_run_id")
    run = session.get(CaseImportRun, snap.import_run_id)
    if run is None:
        raise ActivationPreconditionError("import run missing")
    if run.snapshot_id != snap.id:
        raise ActivationPreconditionError("import_run.snapshot_id mismatch")
    if run.status != "completed":
        raise ActivationPreconditionError(
            f"import run status is {run.status!r}, expected completed"
        )

    files = list(
        session.scalars(
            select(CaseImportFile).where(CaseImportFile.import_run_id == run.id)
        ).all()
    )
    if len(files) < 3:
        raise ActivationPreconditionError(
            f"expected ≥3 import files, found {len(files)}"
        )
    if any(f.status != "completed" for f in files):
        raise ActivationPreconditionError(
            "not all import files are completed: "
            + ", ".join(f"{f.source_file}={f.status}" for f in files)
        )

    report = snap.validation_report_json
    if not isinstance(report, dict):
        raise ActivationPreconditionError(
            "validation_report_json missing; final import verification required"
        )
    if "final_checks" not in report or not report.get("ready_at"):
        raise ActivationPreconditionError(
            "validation_report_json lacks final_checks/ready_at "
            "(final import verification not successful)"
        )
    # Counters in report vs files when manifest present.
    manifest = report.get("manifest")
    if isinstance(manifest, list) and manifest:
        by_file = {f.source_file: f for f in files}
        for entry in manifest:
            if not isinstance(entry, dict):
                continue
            name = entry.get("source_file")
            expected = entry.get("record_count")
            if name in by_file and expected is not None:
                if by_file[name].row_count_loaded != expected:
                    raise ActivationPreconditionError(
                        f"file {name} row_count_loaded="
                        f"{by_file[name].row_count_loaded} != manifest {expected}"
                    )
    # Ensure report final_checks mention required roles when structured as in pipeline.
    checks = report.get("final_checks")
    if isinstance(checks, dict):
        for role in ("companies", "payments", "person_links"):
            if role not in checks:
                raise ActivationPreconditionError(
                    f"final_checks missing role {role!r}"
                )
