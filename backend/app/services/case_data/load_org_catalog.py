"""Load company catalog CSV into a building case snapshot (no SessionLocal)."""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.models.case_data import (
    CaseImportFile,
    CaseImportRun,
    CaseOrg,
    CaseOrgCatalogRow,
    CaseOrgFieldResolution,
    CaseOrgGroup,
    CaseOrgGroupMember,
    CaseOrgProductMark,
    CaseSnapshot,
)
from app.services.case_data.csv_io import (
    FileRole,
    catalog_conflict_fingerprint,
    inspect_csv_header,
    iter_csv_rows,
    sha256_file,
)
from app.services.case_data.resolution import (
    PRODUCT_CODES,
    RESOLUTION_FIELDS,
    resolve_catalog_variants,
)
from app.services.case_data.validate import (
    ParseStatus,
    parse_bool_flag,
    parse_external_uid,
    parse_group_id,
    parse_money_numeric_20_1,
)

# Same required bool marks as dry-run company scan (missing/invalid → blocking).
COMPANY_BOOL_FIELDS = (
    "NEGATIVEMARK",
    "CL_PRODUCT_RKO_MARK",
    "CL_PRODUCT_GAR_MARK",
    "CL_PRODUCT_LOA_MARK",
    "CL_PRODUCT_LEA_MARK",
    "CL_PRODUCT_DEP_MARK",
    "CL_PRODUCT_ZPP_MARK",
    "FTS_FLAG",
    "FACTORING_MARK",
)

PRODUCT_COLUMN = {
    "RKO": "CL_PRODUCT_RKO_MARK",
    "GAR": "CL_PRODUCT_GAR_MARK",
    "LOA": "CL_PRODUCT_LOA_MARK",
    "LEA": "CL_PRODUCT_LEA_MARK",
    "DEP": "CL_PRODUCT_DEP_MARK",
    "ZPP": "CL_PRODUCT_ZPP_MARK",
}

# Stay under SQLite / driver bind limits for large IN lists and bulk INSERT.
_MAX_BIND_PARAMS = 900
_IN_CHUNK = 400
_RESOLUTION_INSERT_COLUMNS = 9


def _chunks(items: list[str] | set[str], size: int = _IN_CHUNK) -> list[list[str]]:
    seq = list(items)
    if size < 1:
        raise ValueError("chunk size must be positive")
    return [seq[i : i + size] for i in range(0, len(seq), size)]


class CatalogLoadError(Exception):
    """Base error for company catalog loader."""


class SnapshotNotBuildingError(CatalogLoadError):
    pass


class ContextMismatchError(CatalogLoadError):
    pass


class ContentHashMismatchError(CatalogLoadError):
    pass


class CatalogValidationError(CatalogLoadError):
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


class IncompleteCatalogImportError(CatalogLoadError):
    """Rows/file state exists but load is not safely complete; resume not available."""


@dataclass(frozen=True, slots=True)
class CatalogLoadResult:
    skipped: bool
    reason: str | None
    rows_inserted: int
    orgs_created: int
    orgs_upgraded_from_orphan: int
    groups_created: int
    resolutions_written: int
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
) -> CatalogValidationError:
    return CatalogValidationError(
        f"{source_file}#{record_number} field={field} reason={reason}",
        file=source_file,
        record_number=record_number,
        field=field,
        reason=reason,
    )


def _count_csv_records(csv_path: Path) -> int:
    return sum(1 for _ in iter_csv_rows(csv_path))


def _require_bool(
    raw: str,
    *,
    source_file: str,
    record_number: int,
    field: str,
) -> bool:
    parsed = parse_bool_flag(raw)
    if parsed.status is ParseStatus.MISSING:
        raise _validation_error(
            source_file=source_file,
            record_number=record_number,
            field=field,
            reason="missing",
        )
    if parsed.status is ParseStatus.INVALID:
        raise _validation_error(
            source_file=source_file,
            record_number=record_number,
            field=field,
            reason=parsed.error or "invalid",
        )
    return bool(parsed.value)


def load_company_catalog(
    session: Session,
    *,
    snapshot: CaseSnapshot,
    import_run: CaseImportRun,
    import_file: CaseImportFile,
    csv_path: Path,
    batch_size: int = 500,
) -> CatalogLoadResult:
    """Load df_Uid_data-style CSV into an existing building snapshot.

    Transaction boundary: the **caller** owns the session and must ``commit()``
    or ``rollback()``. This function never commits or rolls back. A raised
    ``CatalogLoadError`` / ``CatalogValidationError`` is a normal Python
    exception and does **not** by itself put the Session into a failed state;
    unflushed or flushed-but-uncommitted work remains until the caller rolls back.

    Idempotency: skip only when the registered file is fully complete
    (``status=completed``, SHA-256 match, row counts agree, derived catalog
    data present). Partial or contradictory state raises
    ``IncompleteCatalogImportError`` — no skip, no auto-resume, no deletes.

    Empty company CSV (header only) is allowed: completed with 0 rows can be
    skipped on re-entry.

    Does **not** set snapshot to ready/active or touch ``case_active_snapshot``.
    Does **not** create Company / membership.
    """
    csv_path = Path(csv_path)
    _assert_context(snapshot, import_run, import_file)

    file_sha, _size = sha256_file(csv_path)
    if file_sha != import_file.content_sha256:
        raise ContentHashMismatchError(
            f"CSV sha256 {file_sha} does not match registered file "
            f"{import_file.content_sha256}; refusing to load under stale hash"
        )

    header = inspect_csv_header(csv_path)
    if header.role is not FileRole.COMPANIES:
        raise CatalogValidationError(
            f"CSV role is {header.role.value}, expected companies",
            file=csv_path.name,
            field="header",
            reason="unexpected_role",
        )
    if header.missing_columns:
        raise CatalogValidationError(
            f"missing columns: {header.missing_columns}",
            file=csv_path.name,
            field="header",
            reason="missing_columns",
        )
    if header.duplicate_headers:
        raise CatalogValidationError(
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

    # Preload existing orgs in this snapshot (including orphans).
    org_id_by_uid: dict[str, str] = {
        uid: oid
        for uid, oid in session.execute(
            select(CaseOrg.external_uid, CaseOrg.id).where(CaseOrg.snapshot_id == snapshot.id)
        )
    }
    orphan_uids = {
        uid
        for uid, in session.execute(
            select(CaseOrg.external_uid).where(
                CaseOrg.snapshot_id == snapshot.id,
                CaseOrg.has_catalog_profile.is_(False),
            )
        )
    }

    group_id_by_ext: dict[str, str] = {
        ext: gid
        for ext, gid in session.execute(
            select(CaseOrgGroup.external_group_id, CaseOrgGroup.id).where(
                CaseOrgGroup.snapshot_id == snapshot.id
            )
        )
    }

    orgs_created = 0
    orgs_upgraded = 0
    groups_created = 0
    rows_inserted = 0

    pending_orgs: list[dict[str, Any]] = []
    pending_rows: list[dict[str, Any]] = []
    pending_products: list[dict[str, Any]] = []
    pending_groups: list[dict[str, Any]] = []
    pending_members: list[dict[str, Any]] = []
    touched_org_ids: set[str] = set()
    source_name = import_file.source_file

    def flush_pending() -> None:
        nonlocal pending_orgs, pending_rows, pending_products, pending_groups, pending_members
        if pending_orgs:
            session.execute(insert(CaseOrg), pending_orgs)
            pending_orgs = []
        if pending_groups:
            session.execute(insert(CaseOrgGroup), pending_groups)
            pending_groups = []
        if pending_rows:
            session.execute(insert(CaseOrgCatalogRow), pending_rows)
            pending_rows = []
        if pending_products:
            session.execute(insert(CaseOrgProductMark), pending_products)
            pending_products = []
        if pending_members:
            session.execute(insert(CaseOrgGroupMember), pending_members)
            pending_members = []
        session.flush()

    for row in iter_csv_rows(csv_path):
        values = row.values
        uid_parsed = parse_external_uid(values.get("SYNTHETIC_U"))
        if uid_parsed.status is not ParseStatus.VALID:
            raise _validation_error(
                source_file=source_name,
                record_number=row.record_number,
                field="SYNTHETIC_U",
                reason=uid_parsed.error or uid_parsed.status.value,
            )
        external_uid = str(uid_parsed.value)

        revenue = parse_money_numeric_20_1(values.get("REVENUE_COMPANY"))
        if revenue.status is not ParseStatus.VALID:
            raise _validation_error(
                source_file=source_name,
                record_number=row.record_number,
                field="REVENUE_COMPANY",
                reason=revenue.error or revenue.status.value,
            )

        group_parsed = parse_group_id(values.get("GROUP_ID"))
        if group_parsed.status is not ParseStatus.VALID:
            raise _validation_error(
                source_file=source_name,
                record_number=row.record_number,
                field="GROUP_ID",
                reason=group_parsed.error or group_parsed.status.value,
            )
        group_ext = str(group_parsed.value)

        bool_values: dict[str, bool] = {}
        for bf in COMPANY_BOOL_FIELDS:
            bool_values[bf] = _require_bool(
                values.get(bf, ""),
                source_file=source_name,
                record_number=row.record_number,
                field=bf,
            )

        org_id = org_id_by_uid.get(external_uid)
        if org_id is None:
            org_id = _new_id()
            org_id_by_uid[external_uid] = org_id
            pending_orgs.append(
                {
                    "id": org_id,
                    "snapshot_id": snapshot.id,
                    "external_uid": external_uid,
                    "has_catalog_profile": True,
                    "profile_resolution": "single",
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            orgs_created += 1
        elif external_uid in orphan_uids:
            orgs_upgraded += 1
            orphan_uids.discard(external_uid)

        touched_org_ids.add(org_id)

        catalog_row_id = _new_id()
        row_content_sha = catalog_conflict_fingerprint(values)

        pending_rows.append(
            {
                "id": catalog_row_id,
                "snapshot_id": snapshot.id,
                "import_run_id": import_run.id,
                "case_org_id": org_id,
                "source_file": import_file.source_file,
                "source_row_number": row.record_number,
                "row_content_sha256": row_content_sha,
                "org_type": _empty_to_none(values.get("ORG_TYPE", "")),
                "okfs_name": _empty_to_none(values.get("OKFS_NAME", "")),
                "company_age_years_gradation": _empty_to_none(
                    values.get("COMPANY_AGE_YEARS_GRADATION", "")
                ),
                "eco_mark_label": _empty_to_none(values.get("ECO_MARK_LABEL", "")),
                "mainokved_code": _empty_to_none(values.get("MAINOKVED_CODE", "")),
                "mainokved_name": _empty_to_none(values.get("MAINOKVED_NAME", "")),
                "negative_mark": bool_values["NEGATIVEMARK"],
                "workers_fns_gradation": _empty_to_none(
                    values.get("AMOUNT_WORKERS_FNS_GRADATION", "")
                ),
                "workers_spark_gradation": _empty_to_none(
                    values.get("AMOUNT_WORKERS_SPARK_GRADATION", "")
                ),
                "cl_type": _empty_to_none(values.get("CL_TYPE", "")),
                "fts_flag": bool_values["FTS_FLAG"],
                "fts_country_name_raw": _empty_to_none(values.get("FTS_COUNTRY_NAME", "")),
                "factoring_mark": bool_values["FACTORING_MARK"],
                "revenue_raw": revenue.raw,
                "revenue_amount": revenue.value,
                "revenue_parse_status": "ok",
                "revenue_parse_error": None,
                "revenue_unit": None,
                "revenue_currency": None,
                "group_external_id": group_ext,
                "city": _empty_to_none(values.get("CITY", "")),
                "region": _empty_to_none(values.get("REGION", "")),
                "raw_json": dict(values),
            }
        )
        rows_inserted += 1
        if rows_inserted % 10_000 == 0:
            print(
                f"[case-import] companies progress rows={rows_inserted}",
                file=sys.stderr,
                flush=True,
            )

        for code in PRODUCT_CODES:
            col = PRODUCT_COLUMN[code]
            pending_products.append(
                {
                    "id": _new_id(),
                    "snapshot_id": snapshot.id,
                    "catalog_row_id": catalog_row_id,
                    "product_code": code,
                    "mark": bool_values[col],
                }
            )

        gid = group_id_by_ext.get(group_ext)
        if gid is None:
            gid = _new_id()
            group_id_by_ext[group_ext] = gid
            pending_groups.append(
                {
                    "id": gid,
                    "snapshot_id": snapshot.id,
                    "external_group_id": group_ext,
                }
            )
            groups_created += 1
        pending_members.append(
            {
                "id": _new_id(),
                "snapshot_id": snapshot.id,
                "group_id": gid,
                "case_org_id": org_id,
                "catalog_row_id": catalog_row_id,
                "is_conflicted_membership": False,
            }
        )

        if len(pending_rows) >= batch_size:
            flush_pending()

    flush_pending()

    if touched_org_ids:
        now_ts = datetime.now(timezone.utc)
        for chunk in _chunks(touched_org_ids):
            session.execute(
                update(CaseOrg)
                .where(CaseOrg.id.in_(chunk))
                .values(has_catalog_profile=True, updated_at=now_ts)
            )
        session.flush()

    resolutions_written = _write_resolutions(
        session,
        snapshot_id=snapshot.id,
        import_run_id=import_run.id,
        org_ids=touched_org_ids,
    )

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
    # Keep caller's object in sync for subsequent reads in the same transaction.
    import_file.status = "completed"
    import_file.row_count_loaded = rows_inserted
    import_file.last_row_number = rows_inserted if rows_inserted else None

    return CatalogLoadResult(
        skipped=False,
        reason=None,
        rows_inserted=rows_inserted,
        orgs_created=orgs_created,
        orgs_upgraded_from_orphan=orgs_upgraded,
        groups_created=groups_created,
        resolutions_written=resolutions_written,
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
) -> CatalogLoadResult | None:
    """Return skip result if fully complete; raise if partial/contradictory; else None."""
    row_count = session.scalar(
        select(func.count())
        .select_from(CaseOrgCatalogRow)
        .where(
            CaseOrgCatalogRow.import_run_id == import_run.id,
            CaseOrgCatalogRow.source_file == import_file.source_file,
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
                f"catalog_rows={row_count} != csv_records={actual_csv_count}"
            )
        if row_count != (import_file.row_count_loaded or 0):
            problems.append(
                f"catalog_rows={row_count} != row_count_loaded={import_file.row_count_loaded}"
            )
        if problems:
            raise IncompleteCatalogImportError(
                "completed file has inconsistent counts: " + "; ".join(problems)
            )
        _assert_derived_complete(
            session,
            import_run_id=import_run.id,
            source_file=import_file.source_file,
            expected_rows=actual_csv_count,
        )
        return CatalogLoadResult(
            skipped=True,
            reason="already_completed_same_hash",
            rows_inserted=0,
            orgs_created=0,
            orgs_upgraded_from_orphan=0,
            groups_created=0,
            resolutions_written=0,
            snapshot_id=import_run.snapshot_id,
            import_run_id=import_run.id,
            import_file_id=import_file.id,
        )

    # Not completed: any existing catalog rows for this file ⇒ incomplete (no resume).
    if row_count > 0:
        raise IncompleteCatalogImportError(
            f"import_file status={import_file.status!r} but {row_count} catalog rows "
            f"already exist for {import_file.source_file!r}; resume is not implemented"
        )
    return None


def _assert_derived_complete(
    session: Session,
    *,
    import_run_id: str,
    source_file: str,
    expected_rows: int,
) -> None:
    if expected_rows == 0:
        return

    catalog_ids = list(
        session.scalars(
            select(CaseOrgCatalogRow.id).where(
                CaseOrgCatalogRow.import_run_id == import_run_id,
                CaseOrgCatalogRow.source_file == source_file,
            )
        )
    )
    if len(catalog_ids) != expected_rows:
        raise IncompleteCatalogImportError(
            f"expected {expected_rows} catalog rows for derived check, found {len(catalog_ids)}"
        )

    mark_count = 0
    for chunk in _chunks(catalog_ids):
        mark_count += session.scalar(
            select(func.count())
            .select_from(CaseOrgProductMark)
            .where(CaseOrgProductMark.catalog_row_id.in_(chunk))
        ) or 0
    expected_marks = expected_rows * len(PRODUCT_CODES)
    if mark_count != expected_marks:
        raise IncompleteCatalogImportError(
            f"product marks incomplete: have {mark_count}, expected {expected_marks}"
        )

    org_ids = list(
        session.scalars(
            select(CaseOrgCatalogRow.case_org_id)
            .where(
                CaseOrgCatalogRow.import_run_id == import_run_id,
                CaseOrgCatalogRow.source_file == source_file,
            )
            .distinct()
        )
    )
    res_count = 0
    for chunk in _chunks(org_ids):
        res_count += session.scalar(
            select(func.count())
            .select_from(CaseOrgFieldResolution)
            .where(CaseOrgFieldResolution.case_org_id.in_(chunk))
        ) or 0
    if res_count != len(org_ids):
        raise IncompleteCatalogImportError(
            f"field resolutions incomplete: have {res_count}, expected {len(org_ids)}"
        )


def _assert_context(
    snapshot: CaseSnapshot,
    import_run: CaseImportRun,
    import_file: CaseImportFile,
) -> None:
    if snapshot.status != "building":
        raise SnapshotNotBuildingError(
            f"snapshot status is {snapshot.status!r}; only 'building' accepts catalog load"
        )
    if import_run.snapshot_id != snapshot.id:
        raise ContextMismatchError("import_run.snapshot_id does not match snapshot.id")
    if snapshot.import_run_id is not None and snapshot.import_run_id != import_run.id:
        raise ContextMismatchError("snapshot.import_run_id does not match import_run.id")
    if import_file.import_run_id != import_run.id:
        raise ContextMismatchError("import_file.import_run_id does not match import_run.id")


def _write_resolutions(
    session: Session,
    *,
    snapshot_id: str,
    import_run_id: str,
    org_ids: set[str],
) -> int:
    if not org_ids:
        return 0

    org_id_list = list(org_ids)
    rows: list[CaseOrgCatalogRow] = []
    for chunk in _chunks(org_id_list):
        rows.extend(
            session.execute(
                select(CaseOrgCatalogRow).where(
                    CaseOrgCatalogRow.snapshot_id == snapshot_id,
                    CaseOrgCatalogRow.case_org_id.in_(chunk),
                )
            ).scalars().all()
        )

    by_org: dict[str, list[CaseOrgCatalogRow]] = {}
    for r in rows:
        by_org.setdefault(r.case_org_id, []).append(r)

    catalog_ids = [r.id for r in rows]
    marks_by_catalog: dict[str, dict[str, bool | None]] = {cid: {} for cid in catalog_ids}
    for chunk in _chunks(catalog_ids):
        for mark in session.execute(
            select(CaseOrgProductMark).where(CaseOrgProductMark.catalog_row_id.in_(chunk))
        ).scalars():
            marks_by_catalog.setdefault(mark.catalog_row_id, {})[mark.product_code] = mark.mark

    for chunk in _chunks(org_id_list):
        session.execute(
            delete(CaseOrgFieldResolution).where(
                CaseOrgFieldResolution.snapshot_id == snapshot_id,
                CaseOrgFieldResolution.case_org_id.in_(chunk),
            )
        )

    resolution_rows: list[dict[str, Any]] = []
    org_updates: list[tuple[str, str]] = []
    conflicted_org_ids: set[str] = set()

    for org_id, variants in by_org.items():
        field_dicts = []
        product_lists = []
        for v in variants:
            field_dicts.append({f: getattr(v, f) for f in RESOLUTION_FIELDS})
            product_lists.append(marks_by_catalog.get(v.id, {}))
        resolved = resolve_catalog_variants(field_dicts, product_marks_by_row=product_lists)
        resolution_rows.append(
            {
                "id": _new_id(),
                "snapshot_id": snapshot_id,
                "case_org_id": org_id,
                "import_run_id": import_run_id,
                "consensus_json": resolved["consensus_json"],
                "conflict_json": resolved["conflict_json"],
                "absent_json": resolved["absent_json"],
                "variant_count": resolved["variant_count"],
                "confirmed_field_count": resolved["confirmed_field_count"],
            }
        )
        org_updates.append((org_id, resolved["profile_resolution"]))
        if resolved["group_membership_conflicted"]:
            conflicted_org_ids.add(org_id)

    if resolution_rows:
        max_rows = max(1, _MAX_BIND_PARAMS // _RESOLUTION_INSERT_COLUMNS)
        for i in range(0, len(resolution_rows), max_rows):
            session.execute(
                insert(CaseOrgFieldResolution), resolution_rows[i : i + max_rows]
            )

    now_ts = datetime.now(timezone.utc)
    for org_id, profile_resolution in org_updates:
        session.execute(
            update(CaseOrg)
            .where(CaseOrg.id == org_id)
            .values(
                has_catalog_profile=True,
                profile_resolution=profile_resolution,
                updated_at=now_ts,
            )
        )

    if conflicted_org_ids:
        for chunk in _chunks(conflicted_org_ids):
            session.execute(
                update(CaseOrgGroupMember)
                .where(
                    CaseOrgGroupMember.snapshot_id == snapshot_id,
                    CaseOrgGroupMember.case_org_id.in_(chunk),
                )
                .values(is_conflicted_membership=True)
            )

    session.flush()
    return len(resolution_rows)
