"""Load payment CSV into a building case snapshot (no SessionLocal)."""

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
    CasePayment,
    CaseSnapshot,
)
from app.services.case_data.csv_io import (
    FileRole,
    inspect_csv_header,
    iter_csv_rows,
    payment_content_sha256,
    sha256_file,
)
from app.services.case_data.load_org_catalog import (
    ContentHashMismatchError,
    ContextMismatchError,
    SnapshotNotBuildingError,
)
from app.services.case_data.validate import (
    ParseStatus,
    parse_external_uid,
    parse_money_numeric_20_1,
    parse_pay_cnt,
)

# Stay under conservative SQLite / driver bind limits when expanding INSERT rows.
_MAX_BIND_PARAMS = 900
_PAYMENT_INSERT_COLUMNS = 22  # keys in each pending payment dict


class PaymentLoadError(Exception):
    """Base error for payment loader."""


class PaymentValidationError(PaymentLoadError):
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


class IncompletePaymentImportError(PaymentLoadError):
    """Rows/file state exists but load is not safely complete; resume not available."""


@dataclass(frozen=True, slots=True)
class PaymentLoadResult:
    skipped: bool
    reason: str | None
    rows_inserted: int
    orgs_created: int
    self_pay_rows: int
    snapshot_id: str
    import_run_id: str
    import_file_id: str


def _new_id() -> str:
    return str(uuid.uuid4())


def _validation_error(
    *,
    source_file: str,
    record_number: int,
    field: str,
    reason: str,
) -> PaymentValidationError:
    return PaymentValidationError(
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


def _insert_rows_chunked(session: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    max_rows = max(1, _MAX_BIND_PARAMS // _PAYMENT_INSERT_COLUMNS)
    for i in range(0, len(rows), max_rows):
        session.execute(insert(CasePayment), rows[i : i + max_rows])


def load_payments(
    session: Session,
    *,
    snapshot: CaseSnapshot,
    import_run: CaseImportRun,
    import_file: CaseImportFile,
    csv_path: Path,
    batch_size: int = 500,
) -> PaymentLoadResult:
    """Load df_Uid_payment-style CSV into an existing building snapshot.

    Transaction boundary: the **caller** owns the session and must ``commit()``
    or ``rollback()``. This function never commits or rolls back. A raised
    ``PaymentLoadError`` / ``PaymentValidationError`` is a normal Python
    exception and does **not** by itself put the Session into a failed state;
    unflushed or flushed-but-uncommitted work remains until the caller rolls back.

    Idempotency: skip only when the registered file is fully complete
    (``status=completed``, SHA-256 match, row counts agree). Partial or
    contradictory state raises ``IncompletePaymentImportError`` — no skip,
    no auto-resume, no deletes.

    Empty payment CSV (header only) is allowed: completed with 0 rows can be
    skipped on re-entry.

    Does **not** set snapshot to ready/active or touch ``case_active_snapshot``.
    Does **not** create Company / membership / nodes / edges / impact.
    Does **not** sum payments or compute confirmed turnover.
    """
    if batch_size < 1:
        raise PaymentValidationError(
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
    if header.role is not FileRole.PAYMENTS:
        raise PaymentValidationError(
            f"CSV role is {header.role.value}, expected payments",
            file=csv_path.name,
            field="header",
            reason="unexpected_role",
        )
    if header.missing_columns:
        raise PaymentValidationError(
            f"missing columns: {header.missing_columns}",
            file=csv_path.name,
            field="header",
            reason="missing_columns",
        )
    if header.duplicate_headers:
        raise PaymentValidationError(
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

    # uid -> org_id for this snapshot (grows with distinct parties, not payment hashes)
    org_id_by_uid: dict[str, str] = {
        uid: oid
        for uid, oid in session.execute(
            select(CaseOrg.external_uid, CaseOrg.id).where(CaseOrg.snapshot_id == snapshot.id)
        )
    }

    orgs_created = 0
    rows_inserted = 0
    self_pay_rows = 0
    # Staging rows before org id / dup-rank resolution (no ORM instances).
    pending: list[dict[str, Any]] = []
    source_name = import_file.source_file
    now = datetime.now(timezone.utc)

    def ensure_orgs(uids: set[str]) -> None:
        nonlocal orgs_created
        missing = sorted(u for u in uids if u not in org_id_by_uid)
        if not missing:
            return
        for chunk in _chunks(missing, max(1, _MAX_BIND_PARAMS // 2)):
            for uid, oid in session.execute(
                select(CaseOrg.external_uid, CaseOrg.id).where(
                    CaseOrg.snapshot_id == snapshot.id,
                    CaseOrg.external_uid.in_(chunk),
                )
            ):
                org_id_by_uid[uid] = oid
        still_missing = [u for u in missing if u not in org_id_by_uid]
        if not still_missing:
            return
        org_rows: list[dict[str, Any]] = []
        for uid in still_missing:
            oid = _new_id()
            org_id_by_uid[uid] = oid
            org_rows.append(
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
        max_org_rows = max(1, _MAX_BIND_PARAMS // 6)
        for i in range(0, len(org_rows), max_org_rows):
            session.execute(insert(CaseOrg), org_rows[i : i + max_org_rows])
        session.flush()

    def flush_pending() -> None:
        nonlocal pending
        if not pending:
            return
        needed: set[str] = set()
        for p in pending:
            needed.add(p["_payer_uid"])
            needed.add(p["_ben_uid"])
        ensure_orgs(needed)

        for p in pending:
            p["payer_org_id"] = org_id_by_uid[p.pop("_payer_uid")]
            p["beneficiary_org_id"] = org_id_by_uid[p.pop("_ben_uid")]

        # Dup ranks: DB max for this (run, source_file) + order inside this batch.
        shas = [p["row_content_sha256"] for p in pending]
        unique_shas = list(dict.fromkeys(shas))
        max_rank: dict[str, int] = {}
        for chunk in _chunks(unique_shas, max(1, _MAX_BIND_PARAMS // 2)):
            for sha, mx in session.execute(
                select(
                    CasePayment.row_content_sha256,
                    func.max(CasePayment.intra_file_dup_rank),
                )
                .where(
                    CasePayment.import_run_id == import_run.id,
                    CasePayment.source_file == source_name,
                    CasePayment.row_content_sha256.in_(chunk),
                )
                .group_by(CasePayment.row_content_sha256)
            ):
                max_rank[sha] = int(mx or 0)
        running = dict(max_rank)
        for pay, sha in zip(pending, shas, strict=True):
            nxt = running.get(sha, 0) + 1
            running[sha] = nxt
            pay["intra_file_dup_rank"] = nxt
        _insert_rows_chunked(session, pending)
        session.flush()
        pending = []

    for row in iter_csv_rows(csv_path):
        values = row.values
        ben = parse_external_uid(values.get("BENEFICIARY"))
        if ben.status is not ParseStatus.VALID:
            raise _validation_error(
                source_file=source_name,
                record_number=row.record_number,
                field="BENEFICIARY",
                reason=ben.error or ben.status.value,
            )
        payer = parse_external_uid(values.get("PAYER"))
        if payer.status is not ParseStatus.VALID:
            raise _validation_error(
                source_file=source_name,
                record_number=row.record_number,
                field="PAYER",
                reason=payer.error or payer.status.value,
            )
        amt = parse_money_numeric_20_1(values.get("PAY_AMT"))
        if amt.status is not ParseStatus.VALID:
            raise _validation_error(
                source_file=source_name,
                record_number=row.record_number,
                field="PAY_AMT",
                reason=amt.error or amt.status.value,
            )
        cnt = parse_pay_cnt(values.get("PAY_CNT"))
        if cnt.status is not ParseStatus.VALID:
            raise _validation_error(
                source_file=source_name,
                record_number=row.record_number,
                field="PAY_CNT",
                reason=cnt.error or cnt.status.value,
            )

        ben_uid = str(ben.value)
        payer_uid = str(payer.value)
        is_self = ben_uid == payer_uid
        if is_self:
            self_pay_rows += 1

        content_sha = payment_content_sha256(ben_uid, payer_uid, amt.raw, cnt.raw)
        pending.append(
            {
                "id": _new_id(),
                "snapshot_id": snapshot.id,
                "import_run_id": import_run.id,
                "source_file": source_name,
                "source_row_number": row.record_number,
                "row_content_sha256": content_sha,
                "_payer_uid": payer_uid,
                "_ben_uid": ben_uid,
                "pay_amt_raw": amt.raw,
                "pay_amt": amt.value,
                "pay_amt_parse_status": "ok",
                "pay_amt_parse_error": None,
                "pay_cnt_raw": cnt.raw,
                "pay_cnt": int(cnt.value),
                "pay_cnt_parse_status": "ok",
                "amount_unit": None,
                "amount_currency": None,
                "period_label": None,
                "is_self_pay": is_self,
                "intra_file_dup_rank": 1,
                "semantics_note": "payment_aggregate_only",
            }
        )
        rows_inserted += 1
        if rows_inserted % 50_000 == 0:
            print(
                f"[case-import] payments progress rows={rows_inserted}",
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

    return PaymentLoadResult(
        skipped=False,
        reason=None,
        rows_inserted=rows_inserted,
        orgs_created=orgs_created,
        self_pay_rows=self_pay_rows,
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
) -> PaymentLoadResult | None:
    row_count = session.scalar(
        select(func.count())
        .select_from(CasePayment)
        .where(
            CasePayment.import_run_id == import_run.id,
            CasePayment.source_file == import_file.source_file,
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
                f"payment_rows={row_count} != csv_records={actual_csv_count}"
            )
        if row_count != (import_file.row_count_loaded or 0):
            problems.append(
                f"payment_rows={row_count} != row_count_loaded={import_file.row_count_loaded}"
            )
        if problems:
            raise IncompletePaymentImportError(
                "completed file has inconsistent counts: " + "; ".join(problems)
            )
        return PaymentLoadResult(
            skipped=True,
            reason="already_completed_same_hash",
            rows_inserted=0,
            orgs_created=0,
            self_pay_rows=0,
            snapshot_id=import_run.snapshot_id,
            import_run_id=import_run.id,
            import_file_id=import_file.id,
        )

    if row_count > 0:
        raise IncompletePaymentImportError(
            f"import_file status={import_file.status!r} but {row_count} payment rows "
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
            f"snapshot status is {snapshot.status!r}; only 'building' accepts payment load"
        )
    if import_run.snapshot_id != snapshot.id:
        raise ContextMismatchError("import_run.snapshot_id does not match snapshot.id")
    if snapshot.import_run_id is not None and snapshot.import_run_id != import_run.id:
        raise ContextMismatchError("snapshot.import_run_id does not match import_run.id")
    if import_file.import_run_id != import_run.id:
        raise ContextMismatchError("import_file.import_run_id does not match import_run.id")
