"""Load prepared bank materials into a caller-supplied SQLAlchemy Session.

No SessionLocal, no implicit DATABASE_URL, no auto-migrations.
One document (+ children) per call; commit/rollback belongs to the orchestrator.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, event, func, inspect as sa_inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.bank_materials import (
    BankDocument,
    BankDocumentFile,
    BankFragment,
    BankFragmentRegion,
    BankOcrPage,
    BankOcrRun,
)
from app.services.bank_materials.dry_run import write_reports
from app.services.bank_materials.eligibility import compute_fragment_eligibility
from app.services.bank_materials.normalize import NormalizedFragment
from app.services.bank_materials.prepare import (
    PrepareError,
    StagingIntegrityError,
    StagingManifest,
    build_prepared_document,
    preflight_corpus,
    stage_corpus,
    PreparedDocument,
)


class BankLoadError(Exception):
    """Base loader error (caller should roll back the document transaction)."""

    def __init__(self, code: str, detail: str, *, document: str | None = None):
        self.code = code
        self.detail = detail
        self.document = document
        super().__init__(f"[{code}] {detail}")


class SchemaNotReadyError(BankLoadError):
    def __init__(self, detail: str):
        super().__init__("schema_not_ready", detail)


class DocumentConflictError(BankLoadError):
    pass


class IncompleteRunError(BankLoadError):
    pass


REQUIRED_TABLES = (
    "bank_documents",
    "bank_document_files",
    "bank_ocr_runs",
    "bank_ocr_pages",
    "bank_fragments",
    "bank_fragment_regions",
)


def assert_bank_schema_ready(engine) -> None:
    """Refuse load when bank_* tables are missing. Does not run migrations."""
    names = set(sa_inspect(engine).get_table_names())
    missing = [t for t in REQUIRED_TABLES if t not in names]
    if missing:
        raise SchemaNotReadyError(
            "bank materials schema incomplete / missing tables: "
            + ", ".join(missing)
            + ". Apply Alembic migrations separately before --load "
            "(loader will not migrate automatically)."
        )


def redact_database_url(url: str) -> str:
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


def _make_engine(database_url: str):
    engine = create_engine(database_url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _connection_record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


@dataclass
class CorpusLoadResult:
    ok: bool
    partial_success: bool
    status: str  # loaded | partial | preflight_failed | schema_not_ready | failed
    database: str
    documents: list[DocumentLoadResult] = field(default_factory=list)
    preflight_errors: int = 0
    preflight_warnings: int = 0
    inserted: int = 0
    identical_skip: int = 0
    failed: int = 0
    eligibility_totals: dict[str, int] = field(default_factory=dict)
    detail: str | None = None
    report_paths: dict[str, str] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "partial_success": self.partial_success,
            "status": self.status,
            "database": self.database,
            "preflight_errors": self.preflight_errors,
            "preflight_warnings": self.preflight_warnings,
            "inserted": self.inserted,
            "identical_skip": self.identical_skip,
            "failed": self.failed,
            "eligibility_totals": self.eligibility_totals,
            "detail": self.detail,
            "documents": [asdict(d) for d in self.documents],
            "report_paths": self.report_paths,
        }


def run_bank_materials_load(
    *,
    input_dir: Path,
    pdf_dir: Path,
    database_url: str,
    storage_root: Path | None = None,
    report_dir: Path | None = None,
    staging_parent: Path | None = None,
) -> CorpusLoadResult:
    """Preflight whole corpus, then load each document in its own transaction.

    ``database_url`` is mandatory (no env fallback). Migrations are not applied.
    """
    if not database_url or not str(database_url).strip():
        raise BankLoadError(
            "database_url_required",
            "explicit --database-url is required for --load; "
            "refusing to use DATABASE_URL from the environment",
        )

    report_dir = Path(report_dir) if report_dir else Path("data/bank_materials/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    redacted = redact_database_url(database_url)

    staging: StagingManifest | None = None
    engine = None
    try:
        staging = stage_corpus(
            input_dir=Path(input_dir),
            pdf_dir=Path(pdf_dir),
            storage_root=storage_root,
            staging_parent=staging_parent,
        )
        dry = preflight_corpus(input_dir=staging.ocr_dir, pdf_dir=staging.pdf_dir)
        json_path, md_path = write_reports(dry, report_dir / "preflight")
        if not dry.ok:
            return CorpusLoadResult(
                ok=False,
                partial_success=False,
                status="preflight_failed",
                database=redacted,
                preflight_errors=dry.blocking_error_count,
                preflight_warnings=dry.warning_count,
                detail="corpus preflight has blocking errors; no documents loaded",
                report_paths={"preflight_json": str(json_path), "preflight_md": str(md_path)},
            )

        staging.verify_unchanged()
        engine = _make_engine(database_url)
        try:
            assert_bank_schema_ready(engine)
        except SchemaNotReadyError as exc:
            return CorpusLoadResult(
                ok=False,
                partial_success=False,
                status="schema_not_ready",
                database=redacted,
                preflight_errors=0,
                preflight_warnings=dry.warning_count,
                detail=str(exc),
                report_paths={"preflight_json": str(json_path), "preflight_md": str(md_path)},
            )

        SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        doc_results: list[DocumentLoadResult] = []
        storage = staging.storage_root

        for doc_dir in sorted(
            p for p in staging.ocr_dir.iterdir() if p.is_dir() and (p / "manifest.json").is_file()
        ):
            try:
                staging.verify_unchanged()
            except StagingIntegrityError as exc:
                doc_results.append(
                    DocumentLoadResult(
                        status="error",
                        slug=doc_dir.name,
                        code="staging_integrity",
                        detail=str(exc),
                    )
                )
                break

            plan, plan_errs, _plan_warns = build_prepared_document(
                doc_dir,
                input_dir=staging.ocr_dir,
                pdf_dir=staging.pdf_dir,
                storage_root=storage,
            )
            if plan is None or plan_errs:
                detail = "; ".join(e.detail for e in plan_errs[:5]) if plan_errs else "prepare failed"
                doc_results.append(
                    DocumentLoadResult(
                        status="error",
                        slug=doc_dir.name,
                        code="prepare_failed",
                        detail=detail,
                    )
                )
                continue

            with SessionFactory() as session:
                try:
                    result = load_bank_document(session, plan)
                    session.commit()
                    doc_results.append(result)
                except BankLoadError as exc:
                    session.rollback()
                    doc_results.append(
                        DocumentLoadResult(
                            status="conflict" if isinstance(exc, DocumentConflictError) else "error",
                            slug=plan.slug,
                            code=exc.code,
                            detail=exc.detail,
                            dry_run_eligibility=dict(plan.dry_run_eligibility),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    session.rollback()
                    doc_results.append(
                        DocumentLoadResult(
                            status="error",
                            slug=plan.slug,
                            code="unexpected_error",
                            detail=str(exc),
                            dry_run_eligibility=dict(plan.dry_run_eligibility),
                        )
                    )

        inserted = sum(1 for d in doc_results if d.status == "inserted")
        skipped = sum(1 for d in doc_results if d.status == "identical_skip")
        failed = sum(1 for d in doc_results if d.status in ("error", "conflict"))
        elig = {"search": 0, "ai_evidence": 0, "exact_quote": 0}
        for d in doc_results:
            for k in elig:
                elig[k] += int((d.eligibility_after_read or {}).get(k) or 0)

        partial = inserted + skipped > 0 and failed > 0
        all_ok = failed == 0 and (inserted + skipped) > 0
        status = (
            "loaded"
            if all_ok
            else ("partial" if partial else "failed")
        )
        out = CorpusLoadResult(
            ok=all_ok,
            partial_success=partial,
            status=status,
            database=redacted,
            documents=doc_results,
            preflight_errors=0,
            preflight_warnings=dry.warning_count,
            inserted=inserted,
            identical_skip=skipped,
            failed=failed,
            eligibility_totals=elig,
            detail=(
                None
                if all_ok
                else (
                    f"partial success: {inserted} inserted, {skipped} skipped, "
                    f"{failed} failed"
                    if partial
                    else f"load failed: {failed} document error(s)"
                )
            ),
            report_paths={"preflight_json": str(json_path), "preflight_md": str(md_path)},
        )
        load_report = report_dir / "bank_import_load_latest.json"
        load_report.write_text(
            json.dumps(out.to_json_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        out.report_paths["load_json"] = str(load_report)
        return out
    except PrepareError as exc:
        return CorpusLoadResult(
            ok=False,
            partial_success=False,
            status="failed",
            database=redacted,
            detail=str(exc),
        )
    finally:
        if engine is not None:
            engine.dispose()
        if staging is not None:
            # Ephemeral staging (no caller storage_root) is discarded after load.
            # When the caller supplied storage_root, stage_corpus places durable
            # files under it — deleting would break PDF/OCR download keys.
            if storage_root is None:
                shutil.rmtree(staging.staging_root, ignore_errors=True)


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DocumentLoadResult:
    status: str  # inserted | identical_skip | conflict | error
    slug: str
    document_id: str | None = None
    file_id: str | None = None
    ocr_run_id: str | None = None
    code: str | None = None
    detail: str | None = None
    counts: dict[str, int] = field(default_factory=dict)
    eligibility_after_read: dict[str, int] = field(default_factory=dict)
    dry_run_eligibility: dict[str, int] = field(default_factory=dict)


def _doc_meta_tuple(plan: PreparedDocument) -> tuple[Any, ...]:
    pub = plan.publication
    return (
        plan.title,
        plan.title_status,
        pub.precision,
        pub.publication_date,
        pub.publication_year,
        pub.publication_month,
        pub.display,
        plan.period_covered,
        plan.period_covered_status,
        json_canon_list(plan.topics_json),
        plan.topics_status,
        plan.staleness_note,
        plan.is_current_stance,
        plan.document_visual_status,
    )


def json_canon_list(value: list[Any]) -> tuple[Any, ...]:
    return tuple(value or [])


def _existing_doc_meta_tuple(doc: BankDocument) -> tuple[Any, ...]:
    return (
        doc.title,
        doc.title_status,
        doc.publication_date_precision,
        doc.publication_date,
        doc.publication_year,
        doc.publication_month,
        doc.publication_date_display,
        doc.period_covered,
        doc.period_covered_status,
        json_canon_list(list(doc.topics_json or [])),
        doc.topics_status,
        doc.staleness_note,
        bool(doc.is_current_stance),
        doc.document_visual_status,
    )


def _fragment_payload(f: NormalizedFragment) -> dict[str, Any]:
    return {
        "stable_key": f.stable_key,
        "revision": f.revision,
        "kind": f.kind,
        "primary_region_type": f.primary_region_type,
        "content_type": f.content_type,
        "content_type_status": f.content_type_status,
        "page_number": f.page_number,
        "ocr_text": f.ocr_text,
        "cleaned_text": f.cleaned_text,
        "verified_transcript": f.verified_transcript,
        "summary_text": f.summary_text,
        "verification_status": f.verification_status,
        "ocr_correction_json": f.ocr_correction_json,
        "source_role": f.source_role,
        "fragment_notes": f.fragment_notes,
        "supersedes_stable_key": f.supersedes_stable_key,
        "supersedes_revision": f.supersedes_revision,
        "regions": [
            (
                r.page_number,
                r.sort_order,
                r.region_type,
                r.bbox_left,
                r.bbox_top,
                r.bbox_width,
                r.bbox_height,
                r.note,
            )
            for r in sorted(f.regions, key=lambda x: x.sort_order)
        ],
    }


def _db_fragment_payload(
    frag: BankFragment,
    regions: list[BankFragmentRegion],
    *,
    supersedes_stable_key: str | None,
    supersedes_revision: int | None,
) -> dict[str, Any]:
    return {
        "stable_key": frag.stable_key,
        "revision": frag.revision,
        "kind": frag.kind,
        "primary_region_type": frag.primary_region_type,
        "content_type": frag.content_type,
        "content_type_status": frag.content_type_status,
        "page_number": frag.page_number,
        "ocr_text": frag.ocr_text,
        "cleaned_text": frag.cleaned_text,
        "verified_transcript": frag.verified_transcript,
        "summary_text": frag.summary_text,
        "verification_status": frag.verification_status,
        "ocr_correction_json": frag.ocr_correction_json,
        "source_role": frag.source_role,
        "fragment_notes": frag.notes,
        "supersedes_stable_key": supersedes_stable_key,
        "supersedes_revision": supersedes_revision,
        "regions": [
            (
                r.page_number,
                r.sort_order,
                r.region_type,
                r.bbox_left,
                r.bbox_top,
                r.bbox_width,
                r.bbox_height,
                r.note,
            )
            for r in sorted(regions, key=lambda x: x.sort_order)
        ],
    }


def _read_run_payload(
    session: Session, run: BankOcrRun
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    pages = session.scalars(
        select(BankOcrPage).where(BankOcrPage.ocr_run_id == run.id)
    ).all()
    frags = session.scalars(
        select(BankFragment).where(BankFragment.ocr_run_id == run.id)
    ).all()
    frag_ids = [f.id for f in frags]
    regions_by_frag: dict[str, list[BankFragmentRegion]] = {fid: [] for fid in frag_ids}
    if frag_ids:
        regs = session.scalars(
            select(BankFragmentRegion).where(BankFragmentRegion.fragment_id.in_(frag_ids))
        ).all()
        for r in regs:
            regions_by_frag.setdefault(r.fragment_id, []).append(r)

    id_to_frag = {f.id: f for f in frags}
    payloads: list[dict[str, Any]] = []
    for f in frags:
        ss_key = None
        ss_rev = None
        if f.supersedes_fragment_id and f.supersedes_fragment_id in id_to_frag:
            prev = id_to_frag[f.supersedes_fragment_id]
            ss_key = prev.stable_key
            ss_rev = prev.revision
        payloads.append(
            _db_fragment_payload(
                f,
                regions_by_frag.get(f.id, []),
                supersedes_stable_key=ss_key,
                supersedes_revision=ss_rev,
            )
        )
    counts = {
        "pages": len(pages),
        "fragments": len(frags),
        "regions": sum(len(v) for v in regions_by_frag.values()),
    }
    return counts, payloads


def _eligibility_from_db_fragments(frags: list[BankFragment], region_counts: dict[str, int]) -> dict[str, int]:
    totals = {"search": 0, "ai_evidence": 0, "exact_quote": 0}
    for f in frags:
        elig = compute_fragment_eligibility(
            verification_status=f.verification_status,
            kind=f.kind,
            primary_region_type=f.primary_region_type,
            content_type=f.content_type,
            content_type_status=f.content_type_status,
            verified_transcript=f.verified_transcript,
            summary_text=f.summary_text,
            region_count=region_counts.get(f.id, 0),
        )
        if elig.eligible_search:
            totals["search"] += 1
        if elig.eligible_ai_evidence:
            totals["ai_evidence"] += 1
        if elig.eligible_exact_quote:
            totals["exact_quote"] += 1
    return totals


def _check_revision_graph(fragments: list[NormalizedFragment], *, document: str) -> None:
    by_key: dict[str, list[NormalizedFragment]] = {}
    for f in fragments:
        by_key.setdefault(f.stable_key, []).append(f)

    for key, revs in by_key.items():
        revisions = sorted(f.revision for f in revs)
        if len(revisions) != len(set(revisions)):
            raise DocumentConflictError(
                "duplicate_revision",
                f"duplicate revision for stable_key={key!r}",
                document=document,
            )
        # Monotonicity: each supersedes target must have lower revision
        for f in revs:
            if f.supersedes_stable_key is None:
                continue
            if f.supersedes_stable_key != f.stable_key:
                # Cross-key supersedes not supported by DB composite FK
                raise DocumentConflictError(
                    "supersedes_cross_key",
                    f"{f.stable_key!r} supersedes other key {f.supersedes_stable_key!r}",
                    document=document,
                )
            target_rev = f.supersedes_revision
            if target_rev is None:
                # Resolve to max lower revision present
                lower = [r for r in revisions if r < f.revision]
                if not lower:
                    raise DocumentConflictError(
                        "supersedes_target_missing",
                        f"{key!r} rev={f.revision} supersedes missing prior revision",
                        document=document,
                    )
                target_rev = max(lower)
            if target_rev >= f.revision:
                raise DocumentConflictError(
                    "revision_not_monotonic",
                    f"{key!r} rev={f.revision} must be > supersedes rev={target_rev}",
                    document=document,
                )
            if target_rev not in revisions and not any(
                x.revision == target_rev for x in revs
            ):
                # May exist only in DB — checked later when resolving IDs
                pass

        # Cycle detection within planned chain
        points: dict[int, int | None] = {}
        for f in revs:
            if f.supersedes_stable_key == f.stable_key:
                points[f.revision] = f.supersedes_revision
            else:
                points[f.revision] = None
        for start in points:
            seen: set[int] = set()
            cur: int | None = start
            while cur is not None:
                if cur in seen:
                    raise DocumentConflictError(
                        "supersedes_cycle",
                        f"supersedes cycle in stable_key={key!r}",
                        document=document,
                    )
                seen.add(cur)
                cur = points.get(cur)


def load_bank_document(session: Session, plan: PreparedDocument) -> DocumentLoadResult:
    """Insert or identical_skip one document tree. Does not commit."""
    slug = plan.slug
    dry_elig = dict(plan.dry_run_eligibility)
    _check_revision_graph(plan.fragments, document=slug)

    # --- Document identity (slug) ---
    existing_doc = session.scalar(
        select(BankDocument).where(BankDocument.slug == slug)
    )

    # SHA owned by another slug?
    file_by_sha = session.scalar(
        select(BankDocumentFile).where(BankDocumentFile.sha256 == plan.source_sha256)
    )
    if file_by_sha is not None:
        owner = session.get(BankDocument, file_by_sha.document_id)
        if owner is not None and owner.slug != slug:
            raise DocumentConflictError(
                "sha_slug_conflict",
                f"PDF sha {plan.source_sha256[:12]}… already belongs to slug "
                f"{owner.slug!r}, refusing merge with {slug!r}",
                document=slug,
            )

    if existing_doc is not None:
        if _existing_doc_meta_tuple(existing_doc) != _doc_meta_tuple(plan):
            raise DocumentConflictError(
                "document_metadata_conflict",
                f"slug {slug!r} exists with different metadata; refusing silent update",
                document=slug,
            )
        document = existing_doc
    else:
        if file_by_sha is not None:
            raise DocumentConflictError(
                "sha_without_matching_slug",
                f"PDF sha exists but slug {slug!r} is new — identity contradiction",
                document=slug,
            )
        document = BankDocument(
            id=_uid(),
            slug=slug,
            title=plan.title,
            title_status=plan.title_status,
            publication_date=plan.publication.publication_date,
            publication_year=plan.publication.publication_year,
            publication_month=plan.publication.publication_month,
            publication_date_precision=plan.publication.precision,
            publication_date_display=plan.publication.display,
            period_covered=plan.period_covered,
            period_covered_status=plan.period_covered_status,
            topics_json=list(plan.topics_json),
            topics_status=plan.topics_status,
            staleness_note=plan.staleness_note,
            is_current_stance=plan.is_current_stance,
            document_visual_status=plan.document_visual_status,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(document)
        session.flush()

    # --- File ---
    if file_by_sha is not None:
        if file_by_sha.document_id != document.id:
            raise DocumentConflictError(
                "file_document_mismatch",
                "existing file document_id does not match slug document",
                document=slug,
            )
        if file_by_sha.page_count != plan.page_count:
            raise DocumentConflictError(
                "file_page_count_conflict",
                f"existing file page_count={file_by_sha.page_count} != {plan.page_count}",
                document=slug,
            )
        doc_file = file_by_sha
    else:
        doc_file = BankDocumentFile(
            id=_uid(),
            document_id=document.id,
            sha256=plan.source_sha256,
            original_filename=plan.original_filename,
            page_count=plan.page_count,
            byte_size=plan.byte_size,
            storage_key=plan.pdf_storage_key,
            pdf_producer=None,
            pdf_creation_date=None,
            revision_label=None,
            supersedes_file_id=None,
            imported_at=_now(),
        )
        session.add(doc_file)
        session.flush()

    # --- OCR run ---
    existing_run = session.scalar(
        select(BankOcrRun).where(
            BankOcrRun.document_file_id == doc_file.id,
            BankOcrRun.fingerprint_hash == plan.fingerprint_hash,
        )
    )

    if existing_run is not None:
        return _identical_or_conflict_existing_run(
            session,
            plan=plan,
            document=document,
            doc_file=doc_file,
            run=existing_run,
            dry_elig=dry_elig,
        )

    # New OCR fingerprint → insert run (+ pages/fragments); keep any previous runs.
    run = BankOcrRun(
        id=_uid(),
        document_file_id=doc_file.id,
        fingerprint_hash=plan.fingerprint_hash,
        schema_version=plan.schema_version,
        tesseract_version_line=plan.tesseract_version_line,
        lang=plan.lang,
        psm_default=plan.psm_default,
        preserve_interword_spaces=plan.preserve_interword_spaces,
        eng_traineddata_sha256=plan.eng_traineddata_sha256,
        rus_traineddata_sha256=plan.rus_traineddata_sha256,
        params_json=dict(plan.fingerprint_canonical),
        processing_status=plan.processing_status,
        pages_ok_json=list(plan.pages_ok_json),
        pages_failed_json=list(plan.pages_failed_json),
        artifact_root_key=plan.artifact_root_key,
        created_at=_now(),
    )
    session.add(run)
    session.flush()

    for page in plan.pages:
        session.add(
            BankOcrPage(
                id=_uid(),
                ocr_run_id=run.id,
                page_number=page.page_number,
                processing_status=page.processing_status,
                width=page.width,
                height=page.height,
                image_storage_key=page.image_storage_key,
                raw_text_storage_key=page.raw_text_storage_key,
                cleaned_text_storage_key=page.cleaned_text_storage_key,
                tsv_storage_key=page.tsv_storage_key,
                words_storage_key=page.words_storage_key,
                word_count=page.word_count,
                mean_confidence=page.mean_confidence,
                median_confidence=page.median_confidence,
                psm_used=page.psm_used,
                visual_verification_status=page.visual_verification_status,
                content_regions_json=list(page.content_regions_json),
                visual_checks_json=dict(page.visual_checks_json),
                error=page.error,
            )
        )
    session.flush()

    # Insert fragments ordered by (stable_key, revision) so supersedes targets exist.
    frag_id_by_key_rev: dict[tuple[str, int], str] = {}
    # Also load any prior revisions already in this run (shouldn't exist for new run)
    for f in sorted(plan.fragments, key=lambda x: (x.stable_key, x.revision)):
        supersedes_id = None
        if f.supersedes_stable_key:
            target_rev = f.supersedes_revision
            if target_rev is None:
                prior = [
                    rev
                    for (k, rev) in frag_id_by_key_rev
                    if k == f.stable_key and rev < f.revision
                ]
                if not prior:
                    raise DocumentConflictError(
                        "supersedes_target_missing",
                        f"no prior revision for {f.stable_key!r} before {f.revision}",
                        document=slug,
                    )
                target_rev = max(prior)
            key = (f.stable_key, target_rev)
            supersedes_id = frag_id_by_key_rev.get(key)
            if supersedes_id is None:
                raise DocumentConflictError(
                    "supersedes_target_missing",
                    f"missing ({f.stable_key!r}, rev={target_rev})",
                    document=slug,
                )
            if target_rev >= f.revision:
                raise DocumentConflictError(
                    "revision_not_monotonic",
                    f"{f.stable_key!r} rev={f.revision} <= supersedes {target_rev}",
                    document=slug,
                )

        frag_id = _uid()
        session.add(
            BankFragment(
                id=frag_id,
                ocr_run_id=run.id,
                document_file_id=doc_file.id,
                document_id=document.id,
                stable_key=f.stable_key,
                revision=f.revision,
                kind=f.kind,
                primary_region_type=f.primary_region_type,
                content_type=f.content_type,
                content_type_status=f.content_type_status,
                page_number=f.page_number,
                ocr_text=f.ocr_text,
                cleaned_text=f.cleaned_text,
                verified_transcript=f.verified_transcript,
                summary_text=f.summary_text,
                verification_status=f.verification_status,
                ocr_correction_json=f.ocr_correction_json,
                source_role=f.source_role,
                notes=f.fragment_notes,
                supersedes_fragment_id=supersedes_id,
                created_at=_now(),
            )
        )
        session.flush()
        frag_id_by_key_rev[(f.stable_key, f.revision)] = frag_id
        for reg in f.regions:
            session.add(
                BankFragmentRegion(
                    id=_uid(),
                    fragment_id=frag_id,
                    ocr_run_id=run.id,
                    page_number=reg.page_number,
                    sort_order=reg.sort_order,
                    region_type=reg.region_type,
                    bbox_left=reg.bbox_left,
                    bbox_top=reg.bbox_top,
                    bbox_width=reg.bbox_width,
                    bbox_height=reg.bbox_height,
                    coord_space="page_image_px",
                    note=reg.note,
                )
            )
    session.flush()

    elig_after = _eligibility_counts_for_run(session, run.id)
    expected = plan.expected_counts()
    return DocumentLoadResult(
        status="inserted",
        slug=slug,
        document_id=document.id,
        file_id=doc_file.id,
        ocr_run_id=run.id,
        counts=expected,
        eligibility_after_read=elig_after,
        dry_run_eligibility=dry_elig,
    )


def _eligibility_counts_for_run(session: Session, run_id: str) -> dict[str, int]:
    frags = session.scalars(
        select(BankFragment).where(BankFragment.ocr_run_id == run_id)
    ).all()
    region_counts: dict[str, int] = {}
    if frags:
        rows = session.execute(
            select(BankFragmentRegion.fragment_id, func.count())
            .where(BankFragmentRegion.fragment_id.in_([f.id for f in frags]))
            .group_by(BankFragmentRegion.fragment_id)
        ).all()
        region_counts = {fid: int(c) for fid, c in rows}
    return _eligibility_from_db_fragments(frags, region_counts)


def _identical_or_conflict_existing_run(
    session: Session,
    *,
    plan: PreparedDocument,
    document: BankDocument,
    doc_file: BankDocumentFile,
    run: BankOcrRun,
    dry_elig: dict[str, int],
) -> DocumentLoadResult:
    expected = plan.expected_counts()
    actual_counts, db_payloads = _read_run_payload(session, run)

    # Pages must already be complete — never repair/resume missing pages.
    pages = session.scalars(
        select(BankOcrPage).where(BankOcrPage.ocr_run_id == run.id)
    ).all()
    page_map = {p.page_number: p for p in pages}
    if actual_counts["pages"] != expected["pages"]:
        raise IncompleteRunError(
            "incomplete_or_partial_ocr_run",
            f"existing OCR run page count {actual_counts['pages']} != "
            f"expected {expected['pages']}; refusing skip/repair",
            document=plan.slug,
        )
    for pp in plan.pages:
        dbp = page_map.get(pp.page_number)
        if dbp is None:
            raise IncompleteRunError(
                "incomplete_or_partial_ocr_run",
                f"missing page {pp.page_number} on existing run",
                document=plan.slug,
            )
        if (
            dbp.width != pp.width
            or dbp.height != pp.height
            or dbp.processing_status != pp.processing_status
            or dbp.visual_verification_status != pp.visual_verification_status
        ):
            raise DocumentConflictError(
                "page_content_conflict",
                f"page {pp.page_number} metadata differs on existing run",
                document=plan.slug,
            )

    planned = [_fragment_payload(f) for f in plan.fragments]
    planned_map = {(p["stable_key"], p["revision"]): p for p in planned}
    db_map = {(p["stable_key"], p["revision"]): p for p in db_payloads}

    # DB rows not in plan → contradictory corpus vs DB
    extra = sorted(set(db_map) - set(planned_map))
    if extra:
        raise DocumentConflictError(
            "fragment_set_conflict",
            "DB has fragment revisions absent from artifacts: "
            + ", ".join(f"{k}@r{r}" for k, r in extra[:10]),
            document=plan.slug,
        )

    conflicts = []
    to_insert: list[NormalizedFragment] = []
    for key, payload in planned_map.items():
        if key in db_map:
            if db_map[key] != payload:
                conflicts.append(f"{key[0]}@r{key[1]}")
        else:
            # New revision / new key under same OCR run
            match = next(
                f
                for f in plan.fragments
                if f.stable_key == key[0] and f.revision == key[1]
            )
            to_insert.append(match)

    if conflicts:
        raise DocumentConflictError(
            "fragment_content_conflict",
            "same fingerprint/revision exists with different content: "
            + ", ".join(conflicts[:10]),
            document=plan.slug,
        )

    if not to_insert:
        # Full identical match (including region counts)
        if actual_counts["regions"] != expected["regions"]:
            raise IncompleteRunError(
                "incomplete_or_partial_ocr_run",
                f"region count {actual_counts['regions']} != expected "
                f"{expected['regions']}; refusing skip/repair",
                document=plan.slug,
            )
        elig_after = _eligibility_counts_for_run(session, run.id)
        return DocumentLoadResult(
            status="identical_skip",
            slug=plan.slug,
            document_id=document.id,
            file_id=doc_file.id,
            ocr_run_id=run.id,
            code="identical_skip",
            detail="same PDF SHA + OCR fingerprint + normalized content",
            counts=actual_counts,
            eligibility_after_read=elig_after,
            dry_run_eligibility=dry_elig,
        )

    # Append only new revisions; resolve supersedes against DB + newly inserted.
    existing_frags = session.scalars(
        select(BankFragment).where(BankFragment.ocr_run_id == run.id)
    ).all()
    frag_id_by_key_rev: dict[tuple[str, int], str] = {
        (f.stable_key, f.revision): f.id for f in existing_frags
    }

    for f in sorted(to_insert, key=lambda x: (x.stable_key, x.revision)):
        supersedes_id = None
        if f.supersedes_stable_key:
            if f.supersedes_stable_key != f.stable_key:
                raise DocumentConflictError(
                    "supersedes_cross_key",
                    f"{f.stable_key!r} supersedes other key {f.supersedes_stable_key!r}",
                    document=plan.slug,
                )
            target_rev = f.supersedes_revision
            if target_rev is None:
                prior = [
                    rev
                    for (k, rev) in frag_id_by_key_rev
                    if k == f.stable_key and rev < f.revision
                ]
                if not prior:
                    raise DocumentConflictError(
                        "supersedes_target_missing",
                        f"no prior revision for {f.stable_key!r} before {f.revision}",
                        document=plan.slug,
                    )
                target_rev = max(prior)
            if target_rev >= f.revision:
                raise DocumentConflictError(
                    "revision_not_monotonic",
                    f"{f.stable_key!r} rev={f.revision} <= supersedes {target_rev}",
                    document=plan.slug,
                )
            supersedes_id = frag_id_by_key_rev.get((f.stable_key, target_rev))
            if supersedes_id is None:
                raise DocumentConflictError(
                    "supersedes_target_missing",
                    f"missing ({f.stable_key!r}, rev={target_rev})",
                    document=plan.slug,
                )

        frag_id = _uid()
        session.add(
            BankFragment(
                id=frag_id,
                ocr_run_id=run.id,
                document_file_id=doc_file.id,
                document_id=document.id,
                stable_key=f.stable_key,
                revision=f.revision,
                kind=f.kind,
                primary_region_type=f.primary_region_type,
                content_type=f.content_type,
                content_type_status=f.content_type_status,
                page_number=f.page_number,
                ocr_text=f.ocr_text,
                cleaned_text=f.cleaned_text,
                verified_transcript=f.verified_transcript,
                summary_text=f.summary_text,
                verification_status=f.verification_status,
                ocr_correction_json=f.ocr_correction_json,
                source_role=f.source_role,
                notes=f.fragment_notes,
                supersedes_fragment_id=supersedes_id,
                created_at=_now(),
            )
        )
        session.flush()
        frag_id_by_key_rev[(f.stable_key, f.revision)] = frag_id
        for reg in f.regions:
            session.add(
                BankFragmentRegion(
                    id=_uid(),
                    fragment_id=frag_id,
                    ocr_run_id=run.id,
                    page_number=reg.page_number,
                    sort_order=reg.sort_order,
                    region_type=reg.region_type,
                    bbox_left=reg.bbox_left,
                    bbox_top=reg.bbox_top,
                    bbox_width=reg.bbox_width,
                    bbox_height=reg.bbox_height,
                    coord_space="page_image_px",
                    note=reg.note,
                )
            )
    session.flush()

    elig_after = _eligibility_counts_for_run(session, run.id)
    new_counts, _ = _read_run_payload(session, run)
    return DocumentLoadResult(
        status="inserted",
        slug=plan.slug,
        document_id=document.id,
        file_id=doc_file.id,
        ocr_run_id=run.id,
        code="revision_appended",
        detail=f"appended {len(to_insert)} fragment revision(s) to existing OCR run",
        counts=new_counts,
        eligibility_after_read=elig_after,
        dry_run_eligibility=dry_elig,
    )
