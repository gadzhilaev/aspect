"""Dry-run validation of competition CSV files (no application DB)."""

from __future__ import annotations

import json
import tempfile
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.case_data.csv_io import (
    FileRole,
    catalog_conflict_fingerprint,
    inspect_csv_header,
    iter_csv_rows,
    payment_content_sha256,
)
from app.services.case_data.validate import (
    ParseStatus,
    parse_bool_flag,
    parse_external_fid,
    parse_external_uid,
    parse_group_id,
    parse_money_numeric_20_1,
    parse_pay_cnt,
)

EXAMPLE_LIMIT = 15

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


@dataclass(slots=True)
class IssueExample:
    file: str
    record_number: int
    field: str | None
    code: str
    detail: str


@dataclass
class IssueBucket:
    count: int = 0
    examples: list[IssueExample] = field(default_factory=list)

    def add(
        self,
        *,
        file: str,
        record_number: int,
        code: str,
        detail: str,
        field_name: str | None = None,
    ) -> None:
        self.count += 1
        if len(self.examples) < EXAMPLE_LIMIT:
            self.examples.append(
                IssueExample(
                    file=file,
                    record_number=record_number,
                    field=field_name,
                    code=code,
                    detail=detail,
                )
            )


@dataclass
class DryRunResult:
    ok: bool
    started_at: str
    finished_at: str
    duration_seconds: float
    peak_memory_bytes: int | None
    files: list[dict[str, Any]]
    errors: dict[str, IssueBucket]
    warnings: dict[str, IssueBucket]
    stats: dict[str, Any]
    blocking_reasons: list[str]
    can_proceed_to_load: bool

    def to_json_dict(self) -> dict[str, Any]:
        def dump_bucket(b: IssueBucket) -> dict[str, Any]:
            return {
                "count": b.count,
                "examples": [
                    {
                        "file": ex.file,
                        "record_number": ex.record_number,
                        "field": ex.field,
                        "code": ex.code,
                        "detail": ex.detail,
                    }
                    for ex in b.examples
                ],
            }

        return {
            "ok": self.ok,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 3),
            "peak_memory_bytes": self.peak_memory_bytes,
            "files": self.files,
            "errors": {k: dump_bucket(v) for k, v in sorted(self.errors.items())},
            "warnings": {k: dump_bucket(v) for k, v in sorted(self.warnings.items())},
            "stats": self.stats,
            "blocking_reasons": self.blocking_reasons,
            "can_proceed_to_load": self.can_proceed_to_load,
            "notes": [
                "Currency, monetary units, and payment period remain unknown.",
                "Orphans and identical payment rows are warnings, not auto-fixes.",
                "No confirmed turnover totals are computed.",
                "Dry-run does not connect to the application database.",
            ],
        }


def _bucket(store: dict[str, IssueBucket], key: str) -> IssueBucket:
    if key not in store:
        store[key] = IssueBucket()
    return store[key]


def _memory_peak_bytes() -> int | None:
    try:
        current, peak = tracemalloc.get_traced_memory()
        return int(peak)
    except Exception:
        return None


def run_dry_run(*, input_dir: Path, report_dir: Path) -> DryRunResult:
    """Validate competition CSV under input_dir; write reports to report_dir.

    Uses a temporary local scratch SQLite file for join/dup checks only.
    Never opens DATABASE_URL or case_* application tables.
    """
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    tracemalloc.start()

    errors: dict[str, IssueBucket] = {}
    warnings: dict[str, IssueBucket] = {}
    file_reports: list[dict[str, Any]] = []
    blocking: list[str] = []

    input_dir = input_dir.resolve()
    report_dir = report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    csv_paths = sorted(p for p in input_dir.glob("*.csv") if p.is_file())
    if not csv_paths:
        _bucket(errors, "no_csv_files").add(
            file=str(input_dir),
            record_number=0,
            code="no_csv_files",
            detail="No *.csv files in input directory",
        )
        blocking.append("no_csv_files")

    inspected = [inspect_csv_header(p) for p in csv_paths]
    by_role: dict[FileRole, list] = {r: [] for r in FileRole}
    for info in inspected:
        by_role[info.role].append(info)

    for role in (FileRole.COMPANIES, FileRole.PAYMENTS, FileRole.PERSON_LINKS):
        found = by_role[role]
        if len(found) == 0:
            _bucket(errors, "missing_required_file").add(
                file=role.value,
                record_number=0,
                code="missing_role",
                detail=f"No CSV detected for role {role.value}",
            )
            blocking.append(f"missing_{role.value}")
        elif len(found) > 1:
            _bucket(errors, "ambiguous_role_files").add(
                file=",".join(i.path.name for i in found),
                record_number=0,
                code="ambiguous_role",
                detail=f"Multiple CSVs matched role {role.value}",
            )
            blocking.append(f"ambiguous_{role.value}")

    for info in inspected:
        fr: dict[str, Any] = {
            "name": info.path.name,
            "path": str(info.path),
            "role": info.role.value,
            "sha256": info.sha256,
            "byte_size": info.byte_size,
            "columns": info.fieldnames,
            "record_count": 0,
        }
        if info.role is FileRole.UNKNOWN:
            _bucket(errors, "unknown_file_role").add(
                file=info.path.name,
                record_number=0,
                code="unknown_role",
                detail="Could not detect file role from columns",
            )
            blocking.append(f"unknown_role:{info.path.name}")
        if info.duplicate_headers:
            _bucket(errors, "duplicate_headers").add(
                file=info.path.name,
                record_number=0,
                code="duplicate_headers",
                detail=",".join(info.duplicate_headers),
            )
            blocking.append(f"duplicate_headers:{info.path.name}")
        if info.missing_columns:
            _bucket(errors, "missing_columns").add(
                file=info.path.name,
                record_number=0,
                code="missing_columns",
                detail=",".join(info.missing_columns),
            )
            blocking.append(f"missing_columns:{info.path.name}")
        file_reports.append(fr)

    stats: dict[str, Any] = {
        "companies": {},
        "payments": {},
        "person_links": {},
        "units_currency_period": "unknown",
    }

    scratch_dir: Path | None = None
    try:
        if not blocking:
            # Local scratch dir for optional spill files (not DATABASE_URL / app DB).
            scratch_dir = Path(tempfile.mkdtemp(prefix="case_dry_run_"))
            role_files = {info.role: info for info in inspected if info.role is not FileRole.UNKNOWN}
            companies_info = role_files[FileRole.COMPANIES]
            payments_info = role_files[FileRole.PAYMENTS]
            links_info = role_files[FileRole.PERSON_LINKS]

            index = ScratchIndex()
            company_stats = _scan_companies(
                companies_info, index, errors, warnings, file_reports
            )
            # Spill catalog UID set to scratch for join checks / debugging footprint.
            spill = scratch_dir / "catalog_uids.txt"
            spill.write_text("\n".join(sorted(index.catalog_uids)), encoding="utf-8")

            payment_stats = _scan_payments(
                payments_info, index, errors, warnings, file_reports
            )
            link_stats = _scan_links(links_info, index, errors, warnings, file_reports)
            stats["companies"] = company_stats
            stats["payments"] = payment_stats
            stats["person_links"] = link_stats
            stats["scratch_spill"] = str(spill)

            _bucket(warnings, "unknown_money_units").add(
                file="*",
                record_number=0,
                code="units_unknown",
                detail="REVENUE_COMPANY/PAY_AMT currency and units are not stated in source files",
            )
            _bucket(warnings, "unknown_payment_period").add(
                file="*",
                record_number=0,
                code="period_unknown",
                detail="Payment aggregation period is not stated in source files",
            )
    finally:
        if scratch_dir is not None and scratch_dir.exists():
            for p in scratch_dir.iterdir():
                try:
                    p.unlink()
                except OSError:
                    pass
            try:
                scratch_dir.rmdir()
            except OSError:
                pass

    # Blocking if any error buckets have count > 0
    for key, bucket in errors.items():
        if bucket.count > 0 and key not in blocking:
            blocking.append(key)

    peak = _memory_peak_bytes()
    tracemalloc.stop()
    finished_at = datetime.now(timezone.utc).isoformat()
    duration = time.perf_counter() - started
    can_load = len(errors) == 0 or all(b.count == 0 for b in errors.values())
    # Recompute: can proceed only if no error counts
    error_total = sum(b.count for b in errors.values())
    can_load = error_total == 0
    ok = can_load

    result = DryRunResult(
        ok=ok,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration,
        peak_memory_bytes=peak,
        files=file_reports,
        errors=errors,
        warnings=warnings,
        stats=stats,
        blocking_reasons=sorted(set(blocking)) if error_total else [],
        can_proceed_to_load=can_load,
    )

    _write_reports(report_dir, result)
    return result


@dataclass
class ScratchIndex:
    """In-memory join indexes for streaming dry-run (not the application DB)."""

    catalog_uids: set[str] = field(default_factory=set)
    # uid -> (fingerprint, occurrences, conflict)
    catalog_meta: dict[str, tuple[str, int, bool]] = field(default_factory=dict)
    # content_sha -> count
    pay_content_counts: dict[str, int] = field(default_factory=dict)
    # (beneficiary, payer) -> first content sha seen
    pay_pair_first_sha: dict[tuple[str, str], str] = field(default_factory=dict)
    # pairs that saw more than one distinct content hash
    pay_pair_multi: set[tuple[str, str]] = field(default_factory=set)


def _set_record_count(file_reports: list[dict[str, Any]], name: str, count: int) -> None:
    for fr in file_reports:
        if fr["name"] == name:
            fr["record_count"] = count
            break


def _scan_companies(
    info,
    index: ScratchIndex,
    errors: dict[str, IssueBucket],
    warnings: dict[str, IssueBucket],
    file_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    fname = info.path.name
    n = 0
    for row in iter_csv_rows(info.path):
        n += 1
        v = row.values
        uid = parse_external_uid(v.get("SYNTHETIC_U"))
        if uid.status is ParseStatus.MISSING:
            _bucket(errors, "invalid_company_uid").add(
                file=fname,
                record_number=row.record_number,
                field_name="SYNTHETIC_U",
                code="missing",
                detail="empty SYNTHETIC_U",
            )
            continue
        if uid.status is ParseStatus.INVALID:
            _bucket(errors, "invalid_company_uid").add(
                file=fname,
                record_number=row.record_number,
                field_name="SYNTHETIC_U",
                code=uid.error or "invalid",
                detail=uid.raw[:64],
            )
            continue

        gid = parse_group_id(v.get("GROUP_ID"))
        if gid.status is not ParseStatus.VALID:
            _bucket(errors, "invalid_group_id").add(
                file=fname,
                record_number=row.record_number,
                field_name="GROUP_ID",
                code=gid.error or gid.status.value,
                detail=gid.raw[:64],
            )

        rev = parse_money_numeric_20_1(v.get("REVENUE_COMPANY"))
        if rev.status is not ParseStatus.VALID:
            _bucket(errors, "invalid_revenue").add(
                file=fname,
                record_number=row.record_number,
                field_name="REVENUE_COMPANY",
                code=rev.error or rev.status.value,
                detail=rev.raw[:64],
            )

        for bf in COMPANY_BOOL_FIELDS:
            flag = parse_bool_flag(v.get(bf))
            if flag.status is ParseStatus.MISSING:
                _bucket(errors, "invalid_bool_flag").add(
                    file=fname,
                    record_number=row.record_number,
                    field_name=bf,
                    code="missing",
                    detail="empty flag",
                )
            elif flag.status is ParseStatus.INVALID:
                _bucket(errors, "invalid_bool_flag").add(
                    file=fname,
                    record_number=row.record_number,
                    field_name=bf,
                    code=flag.error or "invalid",
                    detail=flag.raw[:64],
                )

        fp = catalog_conflict_fingerprint(v)
        existing = index.catalog_meta.get(uid.value)
        if existing is None:
            index.catalog_meta[uid.value] = (fp, 1, False)
            index.catalog_uids.add(uid.value)
        else:
            prev_fp, occ, conf = existing
            fields_differ = prev_fp != fp
            new_conf = conf or fields_differ
            index.catalog_meta[uid.value] = (prev_fp, occ + 1, new_conf)
            _bucket(warnings, "duplicate_company_uid").add(
                file=fname,
                record_number=row.record_number,
                field_name="SYNTHETIC_U",
                code="duplicate_uid",
                detail=f"uid={uid.value} fields_differ={fields_differ}",
            )
            if fields_differ and not conf:
                _bucket(warnings, "conflicting_company_uid").add(
                    file=fname,
                    record_number=row.record_number,
                    field_name="SYNTHETIC_U",
                    code="uid_field_conflict",
                    detail=f"uid={uid.value}",
                )

    dup_uid_rows = sum(1 for _fp, occ, _c in index.catalog_meta.values() if occ > 1)
    conflict_count = sum(1 for _fp, _occ, conf in index.catalog_meta.values() if conf)
    _set_record_count(file_reports, fname, n)
    return {
        "records": n,
        "unique_uids": len(index.catalog_uids),
        "uids_with_multiple_rows": dup_uid_rows,
        "uids_with_field_conflicts": conflict_count,
    }


def _scan_payments(
    info,
    index: ScratchIndex,
    errors: dict[str, IssueBucket],
    warnings: dict[str, IssueBucket],
    file_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    fname = info.path.name
    n = 0
    both = one = none = 0
    self_pay = 0
    identical_extra = 0
    seen_orphan_party: set[str] = set()
    catalog = index.catalog_uids

    for row in iter_csv_rows(info.path):
        n += 1
        v = row.values
        ben = parse_external_uid(v.get("BENEFICIARY"))
        payer = parse_external_uid(v.get("PAYER"))
        amt = parse_money_numeric_20_1(v.get("PAY_AMT"))
        cnt = parse_pay_cnt(v.get("PAY_CNT"))

        for parsed, field_name in ((ben, "BENEFICIARY"), (payer, "PAYER")):
            if parsed.status is not ParseStatus.VALID:
                _bucket(errors, "invalid_payment_uid").add(
                    file=fname,
                    record_number=row.record_number,
                    field_name=field_name,
                    code=parsed.error or parsed.status.value,
                    detail=parsed.raw[:64],
                )

        if amt.status is not ParseStatus.VALID:
            _bucket(errors, "invalid_pay_amt").add(
                file=fname,
                record_number=row.record_number,
                field_name="PAY_AMT",
                code=amt.error or amt.status.value,
                detail=amt.raw[:64],
            )
        if cnt.status is not ParseStatus.VALID:
            _bucket(errors, "invalid_pay_cnt").add(
                file=fname,
                record_number=row.record_number,
                field_name="PAY_CNT",
                code=cnt.error or cnt.status.value,
                detail=cnt.raw[:64],
            )

        if ben.status is not ParseStatus.VALID or payer.status is not ParseStatus.VALID:
            continue

        if ben.value == payer.value:
            self_pay += 1

        ben_known = ben.value in catalog
        pay_known = payer.value in catalog
        if ben_known and pay_known:
            both += 1
        elif ben_known or pay_known:
            one += 1
        else:
            none += 1

        for party, known in ((ben.value, ben_known), (payer.value, pay_known)):
            if not known:
                seen_orphan_party.add(party)

        sha = payment_content_sha256(
            ben.value, payer.value, amt.raw if amt.raw else "", cnt.raw if cnt.raw else ""
        )
        prev = index.pay_content_counts.get(sha, 0)
        index.pay_content_counts[sha] = prev + 1
        if prev > 0:
            identical_extra += 1
            _bucket(warnings, "identical_payment_rows").add(
                file=fname,
                record_number=row.record_number,
                field_name=None,
                code="identical_content",
                detail=f"sha={sha[:12]}… occurrence={prev + 1}",
            )

        pair = (ben.value, payer.value)
        first = index.pay_pair_first_sha.get(pair)
        if first is None:
            index.pay_pair_first_sha[pair] = sha
        elif first != sha:
            index.pay_pair_multi.add(pair)

    pair_multi_variant = len(index.pay_pair_multi)
    if pair_multi_variant:
        bucket = _bucket(warnings, "payment_pair_value_variants")
        bucket.count = pair_multi_variant
        for i, _pair in enumerate(index.pay_pair_multi):
            if i >= EXAMPLE_LIMIT:
                break
            bucket.examples.append(
                IssueExample(
                    file=fname,
                    record_number=0,
                    field=None,
                    code="pair_multi_value",
                    detail="pair has multiple PAY_AMT/PAY_CNT contents",
                )
            )

    parties_not_in_catalog = len(seen_orphan_party)
    if parties_not_in_catalog:
        bucket = _bucket(warnings, "payment_party_not_in_catalog")
        bucket.count = parties_not_in_catalog
        sample = next(iter(seen_orphan_party), None)
        if sample and not bucket.examples:
            bucket.examples.append(
                IssueExample(
                    file=fname,
                    record_number=0,
                    field=None,
                    code="orphan_party",
                    detail=f"example_uid={sample}; unique_orphan_parties={parties_not_in_catalog}",
                )
            )

    _set_record_count(file_reports, fname, n)
    return {
        "records": n,
        "both_ends_in_catalog": both,
        "one_end_in_catalog": one,
        "neither_end_in_catalog": none,
        "self_pay_rows": self_pay,
        "identical_content_extra_rows": identical_extra,
        "unique_content_hashes": len(index.pay_content_counts),
        "pairs_with_multiple_value_variants": pair_multi_variant,
        "unique_parties_not_in_catalog": parties_not_in_catalog,
    }


def _scan_links(
    info,
    index: ScratchIndex,
    errors: dict[str, IssueBucket],
    warnings: dict[str, IssueBucket],
    file_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    fname = info.path.name
    n = 0
    missing_org = 0
    unique_f: set[str] = set()
    unique_u: set[str] = set()
    catalog = index.catalog_uids
    for row in iter_csv_rows(info.path):
        n += 1
        v = row.values
        fid = parse_external_fid(v.get("SYNTHETIC_F"))
        uid = parse_external_uid(v.get("SYNTHETIC_U"))
        if fid.status is not ParseStatus.VALID:
            _bucket(errors, "invalid_person_fid").add(
                file=fname,
                record_number=row.record_number,
                field_name="SYNTHETIC_F",
                code=fid.error or fid.status.value,
                detail=fid.raw[:64],
            )
        else:
            unique_f.add(fid.value)
        if uid.status is not ParseStatus.VALID:
            _bucket(errors, "invalid_link_uid").add(
                file=fname,
                record_number=row.record_number,
                field_name="SYNTHETIC_U",
                code=uid.error or uid.status.value,
                detail=uid.raw[:64],
            )
            continue
        unique_u.add(uid.value)
        if uid.value not in catalog:
            missing_org += 1
            _bucket(warnings, "person_link_org_not_in_catalog").add(
                file=fname,
                record_number=row.record_number,
                field_name="SYNTHETIC_U",
                code="orphan_org",
                detail=f"uid={uid.value}",
            )

    _set_record_count(file_reports, fname, n)
    return {
        "records": n,
        "unique_fids": len(unique_f),
        "unique_uids": len(unique_u),
        "links_to_missing_org": missing_org,
    }


def _write_reports(report_dir: Path, result: DryRunResult) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = report_dir / f"case_dry_run_{stamp}.json"
    md_path = report_dir / f"case_dry_run_{stamp}.md"
    latest_json = report_dir / "case_dry_run_latest.json"
    latest_md = report_dir / "case_dry_run_latest.md"

    payload = result.to_json_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")

    md = _render_markdown(payload)
    md_path.write_text(md, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Case CSV dry-run report",
        "",
        f"- Started: `{payload['started_at']}`",
        f"- Finished: `{payload['finished_at']}`",
        f"- Duration: `{payload['duration_seconds']}s`",
        f"- Peak memory (tracemalloc): `{payload['peak_memory_bytes']}` bytes",
        f"- Can proceed to load: **{payload['can_proceed_to_load']}**",
        "",
        "## Files",
        "",
    ]
    for fr in payload["files"]:
        lines.append(
            f"- `{fr['name']}` role=`{fr['role']}` records=`{fr['record_count']}` "
            f"bytes=`{fr['byte_size']}` sha256=`{fr['sha256'][:16]}…`"
        )
    lines += ["", "## Errors", ""]
    if not payload["errors"]:
        lines.append("_None_")
    else:
        for key, bucket in payload["errors"].items():
            lines.append(f"- **{key}**: {bucket['count']}")
            for ex in bucket["examples"][:5]:
                lines.append(
                    f"  - {ex['file']}#{ex['record_number']} field={ex['field']} "
                    f"`{ex['code']}` {ex['detail']}"
                )
    lines += ["", "## Warnings", ""]
    if not payload["warnings"]:
        lines.append("_None_")
    else:
        for key, bucket in payload["warnings"].items():
            lines.append(f"- **{key}**: {bucket['count']}")
            for ex in bucket["examples"][:5]:
                lines.append(
                    f"  - {ex['file']}#{ex['record_number']} field={ex['field']} "
                    f"`{ex['code']}` {ex['detail']}"
                )
    lines += ["", "## Stats", "", "```json", json.dumps(payload["stats"], ensure_ascii=False, indent=2), "```", ""]
    if payload["blocking_reasons"]:
        lines += ["## Blocking", ""]
        for b in payload["blocking_reasons"]:
            lines.append(f"- {b}")
    lines += [
        "",
        "## Notes",
        "",
    ]
    for n in payload.get("notes", []):
        lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)
