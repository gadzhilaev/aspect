"""Orchestrate dry-run preflight + three loaders into a building→ready snapshot.

No SessionLocal / no implicit DATABASE_URL. Caller supplies database_url.
Does not activate snapshots or resume failed/building ones.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, func, inspect as sa_inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.case_data import (
    CaseImportFile,
    CaseImportRun,
    CaseOrg,
    CaseOrgCatalogRow,
    CaseOrgFieldResolution,
    CaseOrgProductMark,
    CasePayment,
    CasePersonOrgLink,
    CaseSnapshot,
)
from app.services.case_data.csv_io import FileRole, inspect_csv_header, iter_csv_rows, sha256_file
from app.services.case_data.dry_run import run_dry_run
from app.services.case_data.load_org_catalog import load_company_catalog
from app.services.case_data.load_payments import load_payments
from app.services.case_data.load_person_org_links import load_person_org_links
from app.services.case_data.resolution import PRODUCT_CODES

ROOT = Path(__file__).resolve().parents[3]
REQUIRED_ROLES = (FileRole.COMPANIES, FileRole.PAYMENTS, FileRole.PERSON_LINKS)


class ImportPipelineError(Exception):
    """Base pipeline error."""


class PreflightFailedError(ImportPipelineError):
    pass


class SchemaNotReadyError(ImportPipelineError):
    pass


class VersionLabelConflictError(ImportPipelineError):
    pass


class FinalVerificationError(ImportPipelineError):
    pass


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    role: str
    source_file: str
    path: Path
    sha256: str
    byte_size: int
    record_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "source_file": self.source_file,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "record_count": self.record_count,
        }


@dataclass
class ImportPipelineResult:
    status: str  # ready | identical_skip | failed | preflight_failed
    snapshot_id: str | None = None
    import_run_id: str | None = None
    slot_key: str | None = None
    version_label: str | None = None
    reason: str | None = None
    manifest: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


def redact_database_url(url: str) -> str:
    """Return a log-safe URL without password."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "<unparseable>"
    if not parsed.scheme:
        return "<redacted>"
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    user = parsed.username or ""
    auth = f"{user}:***@" if user or parsed.password else ""
    path = parsed.path or ""
    return urlunparse((parsed.scheme, f"{auth}{host}{port}", path, "", "", ""))


def _stage_log(message: str) -> None:
    """Sparse stage progress for long imports (no CSV row payloads)."""
    print(f"[case-import] {message}", file=sys.stderr, flush=True)


def _new_id() -> str:
    return str(uuid.uuid4())


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def assert_schema_ready(engine) -> str:
    """Require Alembic head applied; import does not migrate or create_all."""
    cfg = _alembic_config()
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current = context.get_current_revision()
    if current is None:
        raise SchemaNotReadyError(
            "database has no Alembic revision; run migrations separately before --load"
        )
    if head is not None and current != head:
        raise SchemaNotReadyError(
            f"database revision {current!r} != Alembic head {head!r}; "
            "run migrations separately before --load"
        )
    if "case_snapshots" not in sa_inspect(engine).get_table_names():
        raise SchemaNotReadyError("case_snapshots table missing; migrate separately")
    return current or ""


def _make_engine(database_url: str):
    engine = create_engine(database_url)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def _count_records(path: Path) -> int:
    return sum(1 for _ in iter_csv_rows(path))


def _discover_role_files(input_dir: Path) -> dict[FileRole, Path]:
    csv_paths = sorted(p for p in input_dir.glob("*.csv") if p.is_file())
    by_role: dict[FileRole, list[Path]] = {r: [] for r in FileRole}
    for path in csv_paths:
        info = inspect_csv_header(path)
        by_role[info.role].append(path)
    missing = [r.value for r in REQUIRED_ROLES if len(by_role[r]) == 0]
    ambiguous = [r.value for r in REQUIRED_ROLES if len(by_role[r]) > 1]
    if missing or ambiguous:
        parts = []
        if missing:
            parts.append(f"missing roles: {missing}")
        if ambiguous:
            parts.append(f"ambiguous roles: {ambiguous}")
        raise PreflightFailedError("; ".join(parts))
    return {r: by_role[r][0] for r in REQUIRED_ROLES}


def _stage_inputs(input_dir: Path, staging_dir: Path) -> list[ManifestEntry]:
    """Copy role files into staging; manifest hashes the staged bytes."""
    role_paths = _discover_role_files(input_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    entries: list[ManifestEntry] = []
    for role in REQUIRED_ROLES:
        src = role_paths[role]
        dest = staging_dir / src.name
        if dest.exists():
            raise PreflightFailedError(f"duplicate staged filename: {src.name}")
        shutil.copy2(src, dest)
        sha, size = sha256_file(dest)
        entries.append(
            ManifestEntry(
                role=role.value,
                source_file=src.name,
                path=dest,
                sha256=sha,
                byte_size=size,
                record_count=_count_records(dest),
            )
        )
    return entries


def _manifest_by_role(entries: list[ManifestEntry]) -> dict[str, str]:
    return {e.role: e.sha256 for e in entries}


def _verify_staged_hash(entry: ManifestEntry) -> None:
    sha, _ = sha256_file(entry.path)
    if sha != entry.sha256:
        raise ImportPipelineError(
            f"staged file {entry.source_file} changed after preflight "
            f"(expected {entry.sha256[:12]}…, got {sha[:12]}…)"
        )


def run_case_import(
    *,
    input_dir: Path,
    database_url: str,
    slot_key: str,
    version_label: str,
    report_dir: Path | None = None,
    batch_size: int = 500,
) -> ImportPipelineResult:
    """Load three competition CSVs into a new building snapshot → ready (or identical_skip)."""
    if batch_size < 1:
        raise ImportPipelineError("batch_size must be positive")
    if not slot_key.strip():
        raise ImportPipelineError("slot_key must be non-empty")
    if not version_label.strip():
        raise ImportPipelineError("version_label must be non-empty")
    if not database_url or not str(database_url).strip():
        raise ImportPipelineError("database_url is required; refusing implicit working DB")

    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise PreflightFailedError(f"input directory not found: {input_dir}")

    report_dir = Path(report_dir) if report_dir else Path("data/case/reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    staging_root = Path(tempfile.mkdtemp(prefix="case_import_stage_"))
    engine = None
    t0 = time.perf_counter()
    try:
        # --- Preflight (no target DB writes) ---
        _stage_log("stage: copying input CSVs to staging")
        try:
            entries = _stage_inputs(input_dir, staging_root)
        except PreflightFailedError as exc:
            return ImportPipelineResult(
                status="preflight_failed",
                reason=str(exc),
                report={"phase": "stage", "error": str(exc)},
            )
        _stage_log(
            "stage: staged "
            + ", ".join(f"{e.role}={e.record_count} rows" for e in entries)
        )

        _stage_log("preflight: dry-run validation starting")
        dry = run_dry_run(input_dir=staging_root, report_dir=report_dir / "preflight")
        _stage_log(
            f"preflight: done ok={dry.ok} duration={dry.duration_seconds:.1f}s "
            f"errors={sum(b.count for b in dry.errors.values())}"
        )
        if not dry.can_proceed_to_load:
            return ImportPipelineResult(
                status="preflight_failed",
                reason="dry-run blocking errors",
                manifest=[e.as_dict() for e in entries],
                report={
                    "phase": "preflight",
                    "blocking_reasons": dry.blocking_reasons,
                    "error_total": sum(b.count for b in dry.errors.values()),
                },
            )

        # Align record counts with dry-run file reports when available.
        by_name = {f["name"]: f for f in dry.files}
        entries = [
            ManifestEntry(
                role=e.role,
                source_file=e.source_file,
                path=e.path,
                sha256=e.sha256,
                byte_size=e.byte_size,
                record_count=int(by_name.get(e.source_file, {}).get("record_count", e.record_count)),
            )
            for e in entries
        ]
        role_sha = _manifest_by_role(entries)

        engine = _make_engine(database_url)
        assert_schema_ready(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        # --- Identical skip / version-label checks (read) ---
        with SessionLocal() as session:
            existing_label = session.scalar(
                select(CaseSnapshot).where(
                    CaseSnapshot.slot_key == slot_key,
                    CaseSnapshot.version_label == version_label,
                )
            )
            identical = _find_identical_success(session, slot_key, role_sha)

            if existing_label is not None:
                if (
                    identical is not None
                    and existing_label.id == identical.id
                    and existing_label.status in {"ready", "active"}
                ):
                    return ImportPipelineResult(
                        status="identical_skip",
                        snapshot_id=existing_label.id,
                        import_run_id=existing_label.import_run_id,
                        slot_key=slot_key,
                        version_label=version_label,
                        reason="identical_skip",
                        manifest=[e.as_dict() for e in entries],
                        report={"phase": "identical_skip", "existing_status": existing_label.status},
                    )
                raise VersionLabelConflictError(
                    f"version_label {version_label!r} already used in slot {slot_key!r} "
                    f"(snapshot={existing_label.id}, status={existing_label.status})"
                )

            if identical is not None:
                return ImportPipelineResult(
                    status="identical_skip",
                    snapshot_id=identical.id,
                    import_run_id=identical.import_run_id,
                    slot_key=slot_key,
                    version_label=identical.version_label,
                    reason="identical_skip",
                    manifest=[e.as_dict() for e in entries],
                    report={
                        "phase": "identical_skip",
                        "existing_status": identical.status,
                        "existing_version_label": identical.version_label,
                    },
                )

            max_seq = session.scalar(
                select(func.max(CaseSnapshot.version_seq)).where(CaseSnapshot.slot_key == slot_key)
            ) or 0
            version_seq = int(max_seq) + 1

        # --- Create building metadata (own transaction) ---
        _stage_log(f"metadata: creating building snapshot seq={version_seq}")
        snap_id, run_id, files_by_role = _create_building_metadata(
            SessionLocal,
            slot_key=slot_key,
            version_label=version_label,
            version_seq=version_seq,
            entries=entries,
        )
        _stage_log(f"metadata: snapshot_id={snap_id}")

        loaders = [
            (FileRole.COMPANIES.value, load_company_catalog),
            (FileRole.PAYMENTS.value, load_payments),
            (FileRole.PERSON_LINKS.value, load_person_org_links),
        ]
        entry_by_role = {e.role: e for e in entries}
        stage_timings: dict[str, float] = {}

        for role_name, loader in loaders:
            entry = entry_by_role[role_name]
            try:
                _verify_staged_hash(entry)
                _stage_log(
                    f"load:{role_name} starting records={entry.record_count} "
                    f"file={entry.source_file}"
                )
                t_role = time.perf_counter()
                with SessionLocal() as session:
                    snap = session.get(CaseSnapshot, snap_id)
                    run = session.get(CaseImportRun, run_id)
                    imp = session.get(CaseImportFile, files_by_role[role_name])
                    assert snap is not None and run is not None and imp is not None
                    loader(
                        session,
                        snapshot=snap,
                        import_run=run,
                        import_file=imp,
                        csv_path=entry.path,
                        batch_size=batch_size,
                    )
                    session.commit()
                stage_timings[role_name] = time.perf_counter() - t_role
                _stage_log(
                    f"load:{role_name} committed in {stage_timings[role_name]:.1f}s"
                )
            except Exception as exc:
                # Current file rolled back with the session; mark failed separately.
                _mark_failed(
                    SessionLocal,
                    snapshot_id=snap_id,
                    import_run_id=run_id,
                    error_summary=f"{role_name}: {exc}",
                )
                err_text = str(exc)
                if len(err_text) > 800:
                    err_text = err_text[:800] + "…"
                return ImportPipelineResult(
                    status="failed",
                    snapshot_id=snap_id,
                    import_run_id=run_id,
                    slot_key=slot_key,
                    version_label=version_label,
                    reason=f"load_failed:{role_name}",
                    manifest=[e.as_dict() for e in entries],
                    report={
                        "phase": "load",
                        "failed_role": role_name,
                        "error": err_text,
                        "database": redact_database_url(database_url),
                    },
                )

        # --- Final verification → ready ---
        _stage_log("final_verify: starting")
        try:
            with SessionLocal() as session:
                snap = session.get(CaseSnapshot, snap_id)
                run = session.get(CaseImportRun, run_id)
                assert snap is not None and run is not None
                files = {
                    role: session.get(CaseImportFile, fid)
                    for role, fid in files_by_role.items()
                }
                checks = _final_verify(session, snap, run, entries, files)
                now = datetime.now(timezone.utc)
                snap.status = "ready"
                snap.built_at = now
                snap.validation_report_json = {
                    "manifest_by_role": role_sha,
                    "manifest": [e.as_dict() for e in entries],
                    "final_checks": checks,
                    "ready_at": now.isoformat(),
                    "stage_timings_seconds": stage_timings,
                    "total_elapsed_seconds": round(time.perf_counter() - t0, 3),
                }
                run.status = "completed"
                run.finished_at = now
                run.error_summary = None
                session.commit()
            _stage_log(
                f"ready: snapshot={snap_id} total_elapsed={time.perf_counter() - t0:.1f}s"
            )
        except Exception as exc:
            _mark_failed(
                SessionLocal,
                snapshot_id=snap_id,
                import_run_id=run_id,
                error_summary=f"final_verify: {exc}",
            )
            return ImportPipelineResult(
                status="failed",
                snapshot_id=snap_id,
                import_run_id=run_id,
                slot_key=slot_key,
                version_label=version_label,
                reason="final_verification_failed",
                manifest=[e.as_dict() for e in entries],
                report={
                    "phase": "final_verify",
                    "error": str(exc),
                    "database": redact_database_url(database_url),
                },
            )

        return ImportPipelineResult(
            status="ready",
            snapshot_id=snap_id,
            import_run_id=run_id,
            slot_key=slot_key,
            version_label=version_label,
            reason=None,
            manifest=[e.as_dict() for e in entries],
            report={
                "phase": "ready",
                "database": redact_database_url(database_url),
                "manifest_by_role": role_sha,
                "stage_timings_seconds": stage_timings,
                "total_elapsed_seconds": round(time.perf_counter() - t0, 3),
            },
        )
    finally:
        if engine is not None:
            engine.dispose()
        shutil.rmtree(staging_root, ignore_errors=True)


def _find_identical_success(
    session: Session, slot_key: str, role_sha: dict[str, str]
) -> CaseSnapshot | None:
    snaps = session.scalars(
        select(CaseSnapshot).where(
            CaseSnapshot.slot_key == slot_key,
            CaseSnapshot.status.in_(("ready", "active")),
        )
    ).all()
    for snap in snaps:
        report = snap.validation_report_json or {}
        prev = report.get("manifest_by_role")
        if isinstance(prev, dict) and prev == role_sha:
            return snap
        # Fallback: compare unordered set of file content hashes on the run.
        if snap.import_run_id:
            shas = set(
                session.scalars(
                    select(CaseImportFile.content_sha256).where(
                        CaseImportFile.import_run_id == snap.import_run_id
                    )
                ).all()
            )
            if shas == set(role_sha.values()) and len(shas) == len(role_sha):
                return snap
    return None


def _create_building_metadata(
    SessionLocal,
    *,
    slot_key: str,
    version_label: str,
    version_seq: int,
    entries: list[ManifestEntry],
) -> tuple[str, str, dict[str, str]]:
    snap_id, run_id = _new_id(), _new_id()
    files_by_role: dict[str, str] = {}
    try:
        with SessionLocal() as session:
            snap = CaseSnapshot(
                id=snap_id,
                slot_key=slot_key,
                version_label=version_label,
                version_seq=version_seq,
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
            for entry in entries:
                fid = _new_id()
                files_by_role[entry.role] = fid
                session.add(
                    CaseImportFile(
                        id=fid,
                        import_run_id=run_id,
                        source_file=entry.source_file,
                        content_sha256=entry.sha256,
                        byte_size=entry.byte_size,
                        row_count_declared=entry.record_count,
                        row_count_loaded=0,
                        status="pending",
                        last_row_number=None,
                    )
                )
            session.commit()
    except IntegrityError as exc:
        raise VersionLabelConflictError(
            f"could not create snapshot for slot={slot_key!r} "
            f"version_label={version_label!r} version_seq={version_seq}: {exc.orig}"
        ) from exc
    return snap_id, run_id, files_by_role


def _mark_failed(
    SessionLocal,
    *,
    snapshot_id: str,
    import_run_id: str,
    error_summary: str,
) -> None:
    with SessionLocal() as session:
        snap = session.get(CaseSnapshot, snapshot_id)
        run = session.get(CaseImportRun, import_run_id)
        if snap is not None and snap.status == "building":
            snap.status = "failed"
        if run is not None and run.status == "running":
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_summary = (error_summary or "")[:4000]
        session.commit()


def _final_verify(
    session: Session,
    snap: CaseSnapshot,
    run: CaseImportRun,
    entries: list[ManifestEntry],
    files: dict[str, CaseImportFile | None],
) -> dict[str, Any]:
    if snap.status != "building":
        raise FinalVerificationError(f"snapshot status is {snap.status!r}, expected building")

    checks: dict[str, Any] = {}
    for entry in entries:
        imp = files.get(entry.role)
        if imp is None:
            raise FinalVerificationError(f"missing import_file for role {entry.role}")
        if imp.status != "completed":
            raise FinalVerificationError(
                f"{entry.role} import_file status={imp.status!r}, expected completed"
            )
        if imp.row_count_loaded != entry.record_count:
            raise FinalVerificationError(
                f"{entry.role} row_count_loaded={imp.row_count_loaded} "
                f"!= manifest {entry.record_count}"
            )
        if imp.content_sha256 != entry.sha256:
            raise FinalVerificationError(f"{entry.role} sha256 mismatch vs manifest")

    # Companies
    comp = next(e for e in entries if e.role == FileRole.COMPANIES.value)
    catalog_n = session.scalar(
        select(func.count())
        .select_from(CaseOrgCatalogRow)
        .where(
            CaseOrgCatalogRow.snapshot_id == snap.id,
            CaseOrgCatalogRow.import_run_id == run.id,
            CaseOrgCatalogRow.source_file == comp.source_file,
        )
    ) or 0
    if catalog_n != comp.record_count:
        raise FinalVerificationError(
            f"catalog rows {catalog_n} != companies manifest {comp.record_count}"
        )
    if catalog_n:
        mark_n = session.scalar(
            select(func.count())
            .select_from(CaseOrgProductMark)
            .where(CaseOrgProductMark.snapshot_id == snap.id)
        ) or 0
        expected_marks = catalog_n * len(PRODUCT_CODES)
        if mark_n != expected_marks:
            raise FinalVerificationError(
                f"product marks {mark_n} != expected {expected_marks}"
            )
        profiled = list(
            session.scalars(
                select(CaseOrg.id).where(
                    CaseOrg.snapshot_id == snap.id,
                    CaseOrg.has_catalog_profile.is_(True),
                )
            ).all()
        )
        if profiled:
            res_n = 0
            for i in range(0, len(profiled), 400):
                chunk = profiled[i : i + 400]
                res_n += session.scalar(
                    select(func.count())
                    .select_from(CaseOrgFieldResolution)
                    .where(
                        CaseOrgFieldResolution.snapshot_id == snap.id,
                        CaseOrgFieldResolution.case_org_id.in_(chunk),
                    )
                ) or 0
            if res_n != len(profiled):
                raise FinalVerificationError(
                    f"resolutions {res_n} != profiled orgs {len(profiled)}"
                )
    checks["companies"] = {"catalog_rows": catalog_n}

    # Payments
    pay = next(e for e in entries if e.role == FileRole.PAYMENTS.value)
    pay_n = session.scalar(
        select(func.count())
        .select_from(CasePayment)
        .where(
            CasePayment.snapshot_id == snap.id,
            CasePayment.import_run_id == run.id,
            CasePayment.source_file == pay.source_file,
        )
    ) or 0
    if pay_n != pay.record_count:
        raise FinalVerificationError(
            f"payment rows {pay_n} != payments manifest {pay.record_count}"
        )
    checks["payments"] = {"rows": pay_n}

    # Person links
    link = next(e for e in entries if e.role == FileRole.PERSON_LINKS.value)
    link_n = session.scalar(
        select(func.count())
        .select_from(CasePersonOrgLink)
        .where(
            CasePersonOrgLink.snapshot_id == snap.id,
            CasePersonOrgLink.import_run_id == run.id,
            CasePersonOrgLink.source_file == link.source_file,
        )
    ) or 0
    if link_n != link.record_count:
        raise FinalVerificationError(
            f"person-link rows {link_n} != manifest {link.record_count}"
        )
    checks["person_links"] = {"rows": link_n}

    # Cross-snapshot leakage: domain rows must all be this snapshot (sampled via counts above).
    foreign_pay = session.scalar(
        select(func.count())
        .select_from(CasePayment)
        .where(
            CasePayment.import_run_id == run.id,
            CasePayment.snapshot_id != snap.id,
        )
    ) or 0
    if foreign_pay:
        raise FinalVerificationError("payment rows reference foreign snapshot")

    return checks
