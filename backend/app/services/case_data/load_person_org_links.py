"""Load person–org link CSV into a building case snapshot (no SessionLocal)."""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from app.models.case_data import (
    CaseImportFile,
    CaseImportRun,
    CaseOrg,
    CasePerson,
    CasePersonOrgLink,
    CaseSnapshot,
)
from app.services.case_data.csv_io import (
    FileRole,
    inspect_csv_header,
    iter_csv_rows,
    sha256_file,
)
from app.services.case_data.load_org_catalog import (
    ContentHashMismatchError,
    ContextMismatchError,
    SnapshotNotBuildingError,
)
from app.services.case_data.validate import (
    ParseStatus,
    parse_external_fid,
    parse_external_uid,
)

_MAX_BIND_PARAMS = 900
_LINK_INSERT_COLUMNS = 11


class PersonLinkLoadError(Exception):
    """Base error for person–org link loader."""


class PersonLinkValidationError(PersonLinkLoadError):
    """Blocking field/structure error aligned with dry-run."""

    def __init__(
        self,
        message: str,
        *,
        file: str | None = None,
        record_number: int | None = None,
        field: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.file = file
        self.record_number = record_number
        self.field = field
        self.reason = reason


class IncompletePersonLinkImportError(PersonLinkLoadError):
    """Rows/file state exists but load is not safely complete; resume not available."""


@dataclass(frozen=True, slots=True)
class PersonLinkLoadResult:
    skipped: bool
    reason: str | None
    rows_inserted: int
    persons_created: int
    orgs_created: int
    snapshot_id: str
    import_run_id: str
    import_file_id: str


def _new_id() -> str:
    return str(uuid.uuid4())


def _empty_to_none(raw: str) -> str | None:
    text = (raw or "").strip()
    return text if text else None


def _validation_error(
    *,
    source_file: str,
    record_number: int,
    field: str,
    reason: str,
) -> PersonLinkValidationError:
    return PersonLinkValidationError(
        f"{source_file}#{record_number} field={field} reason={reason}",
        file=source_file,
        record_number=record_number,
        field=field,
        reason=reason,
    )


def _count_csv_records(csv_path: Path) -> int:
    return sum(1 for _ in iter_csv_rows(csv_path))


def _chunks(items: list[str], size: int) -> list[list[str]]:
    if size < 1:
        raise ValueError("chunk size must be positive")
    return [items[i : i + size] for i in range(0, len(items), size)]


def _insert_links_chunked(session: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    max_rows = max(1, _MAX_BIND_PARAMS // _LINK_INSERT_COLUMNS)
    for i in range(0, len(rows), max_rows):
        session.execute(insert(CasePersonOrgLink), rows[i : i + max_rows])


def load_person_org_links(
    session: Session,
    *,
    snapshot: CaseSnapshot,
    import_run: CaseImportRun,
    import_file: CaseImportFile,
    csv_path: Path,
    batch_size: int = 500,
) -> PersonLinkLoadResult:
    """Load df_Fid_Uid_link-style CSV into an existing building snapshot.

    Transaction boundary: the **caller** owns the session and must ``commit()``
    or ``rollback()``. This function never commits or rolls back. A raised
    ``PersonLinkLoadError`` is a normal Python exception and does **not** by
    itself put the Session into a failed state.

    Idempotency: skip only when fully complete (``status=completed``, SHA-256
    match, row counts agree). Partial/contradictory state raises
    ``IncompletePersonLinkImportError``. Re-entry after skip does not rewrite
    historical ``org_had_catalog_at_import`` on existing links.

    Does **not** set snapshot to ready/active or touch ``case_active_snapshot``.
    Does **not** create Company / membership / users / nodes / edges / impact.
    Does **not** infer relation_kind beyond ``unspecified``.
    """
    if batch_size < 1:
        raise PersonLinkValidationError(
            f"batch_size must be positive, got {batch_size}",
            field="batch_size",
            reason="non_positive",
        )

    csv_path = Path(csv_path)
    _assert_context(snapshot, import_run, import_file)

    file_sha, _size = sha256_file(csv_path)
    if file_sha != import_file.content_sha256:
        raise ContentHashMismatchError(
            f"CSV sha256 {file_sha} does not match registered file "
            f"{import_file.content_sha256}; refusing to load under stale hash"
        )

    header = inspect_csv_header(csv_path)
    if header.role is not FileRole.PERSON_LINKS:
        raise PersonLinkValidationError(
            f"CSV role is {header.role.value}, expected person_links",
            file=csv_path.name,
            field="header",
            reason="unexpected_role",
        )
    if header.missing_columns:
        raise PersonLinkValidationError(
            f"missing columns: {header.missing_columns}",
            file=csv_path.name,
            field="header",
            reason="missing_columns",
        )
    if header.duplicate_headers:
        raise PersonLinkValidationError(
            f"duplicate headers: {header.duplicate_headers}",
            file=csv_path.name,
            field="header",
            reason="duplicate_headers",
        )

    actual_count = _count_csv_records(csv_path)
    skip = _maybe_skip_completed(
        session,
        import_run=import_run,
        import_file=import_file,
        actual_csv_count=actual_count,
    )
    if skip is not None:
        return skip

    # fid -> person_id; uid -> (org_id, has_catalog_profile at resolve time)
    person_id_by_fid: dict[str, str] = {
        fid: pid
        for fid, pid in session.execute(
            select(CasePerson.external_fid, CasePerson.id).where(
                CasePerson.snapshot_id == snapshot.id
            )
        )
    }
    org_meta_by_uid: dict[str, tuple[str, bool]] = {
        uid: (oid, bool(has_prof))
        for uid, oid, has_prof in session.execute(
            select(CaseOrg.external_uid, CaseOrg.id, CaseOrg.has_catalog_profile).where(
                CaseOrg.snapshot_id == snapshot.id
            )
        )
    }

    persons_created = 0
    orgs_created = 0
    rows_inserted = 0
    pending: list[dict[str, Any]] = []
    source_name = import_file.source_file
    now = datetime.now(timezone.utc)

    def ensure_persons(fids: set[str]) -> None:
        nonlocal persons_created
        missing = sorted(f for f in fids if f not in person_id_by_fid)
        if not missing:
            return
        for chunk in _chunks(missing, max(1, _MAX_BIND_PARAMS // 2)):
            for fid, pid in session.execute(
                select(CasePerson.external_fid, CasePerson.id).where(
                    CasePerson.snapshot_id == snapshot.id,
                    CasePerson.external_fid.in_(chunk),
                )
            ):
                person_id_by_fid[fid] = pid
        still = [f for f in missing if f not in person_id_by_fid]
        if not still:
            return
        rows: list[dict[str, Any]] = []
        for fid in still:
            pid = _new_id()
            person_id_by_fid[fid] = pid
            rows.append(
                {
                    "id": pid,
                    "snapshot_id": snapshot.id,
                    "external_fid": fid,
                }
            )
            persons_created += 1
        max_rows = max(1, _MAX_BIND_PARAMS // 3)
        for i in range(0, len(rows), max_rows):
            session.execute(insert(CasePerson), rows[i : i + max_rows])
        session.flush()

    def ensure_orgs(uids: set[str]) -> None:
        nonlocal orgs_created
        missing = sorted(u for u in uids if u not in org_meta_by_uid)
        if not missing:
            return
        for chunk in _chunks(missing, max(1, _MAX_BIND_PARAMS // 2)):
            for uid, oid, has_prof in session.execute(
                select(CaseOrg.external_uid, CaseOrg.id, CaseOrg.has_catalog_profile).where(
                    CaseOrg.snapshot_id == snapshot.id,
                    CaseOrg.external_uid.in_(chunk),
                )
            ):
                org_meta_by_uid[uid] = (oid, bool(has_prof))
        still = [u for u in missing if u not in org_meta_by_uid]
        if not still:
            return
        rows: list[dict[str, Any]] = []
        for uid in still:
            oid = _new_id()
            org_meta_by_uid[uid] = (oid, False)
            rows.append(
                {
                    "id": oid,
                    "snapshot_id": snapshot.id,
                    "external_uid": uid,
                    "has_catalog_profile": False,
                    "profile_resolution": "absent",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            orgs_created += 1
        max_rows = max(1, _MAX_BIND_PARAMS // 6)
        for i in range(0, len(rows), max_rows):
            session.execute(insert(CaseOrg), rows[i : i + max_rows])
        session.flush()

    def flush_pending() -> None:
        nonlocal pending
        if not pending:
            return
        fids = {p["_fid"] for p in pending}
        uids = {p["_uid"] for p in pending}
        ensure_persons(fids)
        ensure_orgs(uids)
        for p in pending:
            fid = p.pop("_fid")
            uid = p.pop("_uid")
            org_id, had_catalog = org_meta_by_uid[uid]
            p["person_id"] = person_id_by_fid[fid]
            p["case_org_id"] = org_id
            p["org_had_catalog_at_import"] = had_catalog
        _insert_links_chunked(session, pending)
        session.flush()
        pending = []

    for row in iter_csv_rows(csv_path):
        values = row.values
        fid_parsed = parse_external_fid(values.get("SYNTHETIC_F"))
        if fid_parsed.status is not ParseStatus.VALID:
            raise _validation_error(
                source_file=source_name,
                record_number=row.record_number,
                field="SYNTHETIC_F",
                reason=fid_parsed.error or fid_parsed.status.value,
            )
        uid_parsed = parse_external_uid(values.get("SYNTHETIC_U"))
        if uid_parsed.status is not ParseStatus.VALID:
            raise _validation_error(
                source_file=source_name,
                record_number=row.record_number,
                field="SYNTHETIC_U",
                reason=uid_parsed.error or uid_parsed.status.value,
            )

        # CITY_NAME / RC_NAME: empty allowed (dry-run does not block); per-row, not collapsed.
        city = _empty_to_none(values.get("CITY_NAME", ""))
        rc = _empty_to_none(values.get("RC_NAME", ""))

        pending.append(
            {
                "id": _new_id(),
                "snapshot_id": snapshot.id,
                "import_run_id": import_run.id,
                "source_file": source_name,
                "source_row_number": row.record_number,
                "_fid": str(fid_parsed.value),
                "_uid": str(uid_parsed.value),
                "city_name": city,
                "rc_name": rc,
                "relation_kind": "unspecified",
                # filled in flush_pending
                "org_had_catalog_at_import": False,
            }
        )
        rows_inserted += 1
        if rows_inserted % 5_000 == 0:
            print(
                f"[case-import] person_links progress rows={rows_inserted}",
                file=sys.stderr,
                flush=True,
            )

        if len(pending) >= batch_size:
            flush_pending()

    flush_pending()

    session.execute(
        update(CaseImportFile)
        .where(CaseImportFile.id == import_file.id)
        .values(
            status="completed",
            row_count_loaded=rows_inserted,
            last_row_number=rows_inserted if rows_inserted else None,
        )
    )
    session.flush()
    import_file.status = "completed"
    import_file.row_count_loaded = rows_inserted
    import_file.last_row_number = rows_inserted if rows_inserted else None

    return PersonLinkLoadResult(
        skipped=False,
        reason=None,
        rows_inserted=rows_inserted,
        persons_created=persons_created,
        orgs_created=orgs_created,
        snapshot_id=snapshot.id,
        import_run_id=import_run.id,
        import_file_id=import_file.id,
    )


def _maybe_skip_completed(
    session: Session,
    *,
    import_run: CaseImportRun,
    import_file: CaseImportFile,
    actual_csv_count: int,
) -> PersonLinkLoadResult | None:
    row_count = session.scalar(
        select(func.count())
        .select_from(CasePersonOrgLink)
        .where(
            CasePersonOrgLink.import_run_id == import_run.id,
            CasePersonOrgLink.source_file == import_file.source_file,
        )
    ) or 0

    if import_file.status == "completed":
        problems: list[str] = []
        if import_file.row_count_loaded != actual_csv_count:
            problems.append(
                f"row_count_loaded={import_file.row_count_loaded} != csv_records={actual_csv_count}"
            )
        if row_count != actual_csv_count:
            problems.append(
                f"link_rows={row_count} != csv_records={actual_csv_count}"
            )
        if row_count != (import_file.row_count_loaded or 0):
            problems.append(
                f"link_rows={row_count} != row_count_loaded={import_file.row_count_loaded}"
            )
        if problems:
            raise IncompletePersonLinkImportError(
                "completed file has inconsistent counts: " + "; ".join(problems)
            )
        return PersonLinkLoadResult(
            skipped=True,
            reason="already_completed_same_hash",
            rows_inserted=0,
            persons_created=0,
            orgs_created=0,
            snapshot_id=import_run.snapshot_id,
            import_run_id=import_run.id,
            import_file_id=import_file.id,
        )

    if row_count > 0:
        raise IncompletePersonLinkImportError(
            f"import_file status={import_file.status!r} but {row_count} person-org links "
            f"already exist for {import_file.source_file!r}; resume is not implemented"
        )
    return None


def _assert_context(
    snapshot: CaseSnapshot,
    import_run: CaseImportRun,
    import_file: CaseImportFile,
) -> None:
    if snapshot.status != "building":
        raise SnapshotNotBuildingError(
            f"snapshot status is {snapshot.status!r}; only 'building' accepts person-link load"
        )
    if import_run.snapshot_id != snapshot.id:
        raise ContextMismatchError("import_run.snapshot_id does not match snapshot.id")
    if snapshot.import_run_id is not None and snapshot.import_run_id != import_run.id:
        raise ContextMismatchError("snapshot.import_run_id does not match import_run.id")
    if import_file.import_run_id != import_run.id:
        raise ContextMismatchError("import_file.import_run_id does not match import_run.id")
