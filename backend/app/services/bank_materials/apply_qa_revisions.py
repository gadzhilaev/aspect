"""Apply versioned bank fragment QA revisions to an existing OCR run.

Session-injected; no SessionLocal; no corpus re-import; no new OCR run.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.bank_materials import (
    BankDocument,
    BankDocumentFile,
    BankFragment,
    BankFragmentRegion,
    BankOcrPage,
    BankOcrRun,
)
from app.services.bank_materials.eligibility import compute_fragment_eligibility
from app.services.bank_materials.fragment_revision import list_latest_fragments_for_run
from app.services.bank_materials.load import (
    BankLoadError,
    SchemaNotReadyError,
    assert_bank_schema_ready,
    redact_database_url,
)
from app.services.bank_materials.normalize import map_fragment

ARTIFACT_KIND = "bank_fragment_qa_revisions"
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})


class QaRevisionError(BankLoadError):
    pass


class QaArtifactError(QaRevisionError):
    pass


class QaConflictError(QaRevisionError):
    pass


class QaBindingError(QaRevisionError):
    pass


class QaPartialStateError(QaRevisionError):
    pass


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


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
class QaApplyResult:
    status: str  # applied | identical_skip | dry_run_ok | conflict | error
    artifact_id: str | None = None
    artifact_sha256: str | None = None
    document_slug: str | None = None
    ocr_run_id: str | None = None
    inserted_fragments: int = 0
    inserted_regions: int = 0
    identical_skip: bool = False
    code: str | None = None
    detail: str | None = None
    revisions: list[dict[str, Any]] = field(default_factory=list)
    eligibility_latest: dict[str, int] = field(default_factory=dict)
    counts_after: dict[str, int] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_qa_artifact(path: Path) -> tuple[dict[str, Any], str]:
    """Parse and lightly validate artifact envelope; return (data, sha256)."""
    path = Path(path)
    if not path.is_file():
        raise QaArtifactError("artifact_missing", f"QA artifact not found: {path}")
    raw_bytes = path.read_bytes()
    artifact_sha = hashlib.sha256(raw_bytes).hexdigest()
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QaArtifactError("artifact_unreadable", f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise QaArtifactError("artifact_not_object", "QA artifact must be a JSON object")
    kind = data.get("artifact_kind")
    if kind != ARTIFACT_KIND:
        raise QaArtifactError(
            "artifact_kind_invalid",
            f"expected artifact_kind={ARTIFACT_KIND!r}, got {kind!r}",
        )
    schema_version = data.get("schema_version")
    try:
        sv = int(schema_version)
    except (TypeError, ValueError) as exc:
        raise QaArtifactError(
            "artifact_schema_invalid",
            f"schema_version must be int, got {schema_version!r}",
        ) from exc
    if sv not in SUPPORTED_SCHEMA_VERSIONS:
        raise QaArtifactError(
            "artifact_schema_unsupported",
            f"unsupported schema_version={sv}; supported={sorted(SUPPORTED_SCHEMA_VERSIONS)}",
        )
    if not data.get("artifact_id"):
        raise QaArtifactError("artifact_id_missing", "artifact_id is required")
    if not data.get("document_slug"):
        raise QaArtifactError("document_slug_missing", "document_slug is required")
    session = data.get("verification_session")
    if not isinstance(session, dict):
        raise QaArtifactError(
            "verification_session_missing",
            "verification_session object is required (QA provenance)",
        )
    for key in ("method", "performed_by", "performed_at"):
        if not session.get(key):
            raise QaArtifactError(
                "verification_session_incomplete",
                f"verification_session.{key} is required",
            )
    method = str(session["method"])
    if "human" in method.lower() and "ai" not in method.lower():
        # Soft check: refuse claiming human when method looks like human-only
        pass
    if method == "human_manual" or method.startswith("human_"):
        raise QaArtifactError(
            "verification_method_mislabel",
            "refusing method that claims human manual QA without explicit policy; "
            f"got {method!r}",
        )
    revs = data.get("fragment_revisions")
    if not isinstance(revs, list) or not revs:
        raise QaArtifactError(
            "fragment_revisions_missing",
            "fragment_revisions must be a non-empty list",
        )
    src = data.get("source_pdf") or {}
    ocr = data.get("ocr_binding") or {}
    if not src.get("sha256") or not ocr.get("fingerprint_hash"):
        raise QaArtifactError(
            "binding_missing",
            "source_pdf.sha256 and ocr_binding.fingerprint_hash are required",
        )
    return data, artifact_sha


def _build_ocr_correction_json(
    rev: dict[str, Any],
    *,
    artifact: dict[str, Any],
    artifact_sha256: str,
) -> dict[str, Any]:
    """Persist OCR correction + QA provenance in existing JSON column (no migration).

    Top-level ``from``/``to``/``basis`` remain compatible with the model doc.
    Structured provenance lives under ``qa_provenance`` — additive, not a silent drop.
    """
    corr = rev.get("ocr_correction") if isinstance(rev.get("ocr_correction"), dict) else {}
    session = artifact.get("verification_session") or {}
    out: dict[str, Any] = {}
    if corr.get("from") is not None:
        out["from"] = corr.get("from")
    if corr.get("to") is not None:
        out["to"] = corr.get("to")
    if corr.get("basis") is not None:
        out["basis"] = corr.get("basis")
    out["qa_provenance"] = {
        "artifact_kind": artifact.get("artifact_kind"),
        "artifact_id": artifact.get("artifact_id"),
        "artifact_sha256": artifact_sha256,
        "method": session.get("method"),
        "performed_by": session.get("performed_by"),
        "performed_at": session.get("performed_at"),
        "document_publication_date": session.get("document_publication_date"),
        "document_publication_date_note": session.get("document_publication_date_note"),
        "classification_basis": rev.get("classification_basis"),
        "page_image_provenance": artifact.get("page_image_provenance"),
        "not_human_manual_qa": True,
    }
    return out


def _region_payload(regions: list[BankFragmentRegion]) -> list[tuple]:
    return [
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
    ]


def _planned_region_payload(regions: list[dict[str, Any]]) -> list[tuple]:
    rows = []
    for idx, r in enumerate(regions):
        bbox = r.get("bbox") if isinstance(r.get("bbox"), dict) else None
        rows.append(
            (
                int(r.get("page", r.get("page_number", 0))),
                int(r.get("sort_order", idx)),
                str(r.get("region_type") or "unverified"),
                None if not bbox else int(bbox["left"]),
                None if not bbox else int(bbox["top"]),
                None if not bbox else int(bbox["width"]),
                None if not bbox else int(bbox["height"]),
                str(r["note"]) if r.get("note") is not None else None,
            )
        )
    return sorted(rows, key=lambda x: x[1])


def _fragment_content_tuple(
    *,
    kind: str,
    primary_region_type: str,
    content_type: str | None,
    content_type_status: str,
    page_number: int,
    ocr_text: str | None,
    verified_transcript: str | None,
    summary_text: str | None,
    verification_status: str,
    ocr_correction_json: dict[str, Any] | None,
    regions: list[tuple],
) -> tuple:
    # Provenance compared structurally (artifact sha + method + performer + time)
    prov = (ocr_correction_json or {}).get("qa_provenance") or {}
    prov_key = (
        prov.get("artifact_sha256"),
        prov.get("method"),
        prov.get("performed_by"),
        prov.get("performed_at"),
        prov.get("artifact_id"),
    )
    corr_key = (
        (ocr_correction_json or {}).get("from"),
        (ocr_correction_json or {}).get("to"),
        (ocr_correction_json or {}).get("basis"),
    )
    return (
        kind,
        primary_region_type,
        content_type,
        content_type_status,
        page_number,
        ocr_text,
        verified_transcript,
        summary_text,
        verification_status,
        corr_key,
        prov_key,
        tuple(regions),
    )


def _resolve_run(
    session: Session,
    artifact: dict[str, Any],
) -> tuple[BankDocument, BankDocumentFile, BankOcrRun]:
    slug = str(artifact["document_slug"])
    pdf_sha = str(artifact["source_pdf"]["sha256"]).lower()
    fp = str(artifact["ocr_binding"]["fingerprint_hash"]).lower()

    doc = session.scalar(select(BankDocument).where(BankDocument.slug == slug))
    if doc is None:
        raise QaBindingError(
            "document_not_found",
            f"no bank_documents row for slug={slug!r}",
            document=slug,
        )
    files = session.scalars(
        select(BankDocumentFile).where(BankDocumentFile.document_id == doc.id)
    ).all()
    file = next((f for f in files if f.sha256.lower() == pdf_sha), None)
    if file is None:
        raise QaBindingError(
            "pdf_sha_mismatch",
            f"no file with sha256={pdf_sha[:16]}… under slug={slug!r}",
            document=slug,
        )
    run = session.scalar(
        select(BankOcrRun).where(
            BankOcrRun.document_file_id == file.id,
            BankOcrRun.fingerprint_hash == fp,
        )
    )
    if run is None:
        raise QaBindingError(
            "ocr_fingerprint_mismatch",
            f"no OCR run with fingerprint={fp[:16]}… for file {file.id}",
            document=slug,
        )
    return doc, file, run


def _validate_revision_entries(
    session: Session,
    *,
    artifact: dict[str, Any],
    run: BankOcrRun,
    page_dims: dict[int, tuple[int | None, int | None]],
    known_pages: set[int],
) -> list[dict[str, Any]]:
    """Normalize each revision; raise on structural / graph errors."""
    slug = str(artifact["document_slug"])
    prepared: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int]] = set()

    for rev in artifact["fragment_revisions"]:
        if not isinstance(rev, dict):
            raise QaArtifactError("revision_not_object", "fragment_revisions entry must be object")
        stable_key = rev.get("stable_key")
        if not stable_key or not isinstance(stable_key, str):
            raise QaArtifactError("stable_key_missing", "each revision needs stable_key")
        try:
            revision = int(rev["revision"])
        except (KeyError, TypeError, ValueError) as exc:
            raise QaArtifactError(
                "revision_invalid",
                f"{stable_key}: revision must be int >= 1",
            ) from exc
        if revision < 1:
            raise QaArtifactError("revision_invalid", f"{stable_key}: revision must be >= 1")
        key = (stable_key, revision)
        if key in seen_keys:
            raise QaArtifactError(
                "duplicate_revision_in_artifact",
                f"duplicate ({stable_key!r}, rev={revision}) in artifact",
            )
        seen_keys.add(key)

        ss_key = rev.get("supersedes_stable_key")
        ss_rev = rev.get("supersedes_revision")
        if ss_key != stable_key:
            raise QaArtifactError(
                "supersedes_cross_key",
                f"{stable_key}: supersedes_stable_key must equal stable_key",
            )
        try:
            ss_rev_i = int(ss_rev)
        except (TypeError, ValueError) as exc:
            raise QaArtifactError(
                "supersedes_revision_invalid",
                f"{stable_key}: supersedes_revision required int",
            ) from exc
        if ss_rev_i >= revision:
            raise QaArtifactError(
                "revision_not_monotonic",
                f"{stable_key}: revision {revision} must be > supersedes_revision {ss_rev_i}",
            )

        raw = {
            "id": stable_key,
            "revision": revision,
            "kind": rev.get("kind"),
            "page": rev.get("page"),
            "primary_region_type": rev.get("primary_region_type"),
            "content_type": rev.get("content_type"),
            "content_type_status": rev.get("content_type_status"),
            "verification_status": rev.get("verification_status"),
            "ocr_text": rev.get("ocr_text"),
            "exact_quote": rev.get("verified_transcript"),
            "verified_transcript": rev.get("verified_transcript"),
            "summary": rev.get("summary_text"),
            "summary_text": rev.get("summary_text"),
            "regions": rev.get("regions") or [],
            "supersedes_stable_key": ss_key,
            "supersedes_revision": ss_rev_i,
            "ocr_correction": rev.get("ocr_correction"),
        }
        mapped, issues = map_fragment(
            raw,
            document=slug,
            page_dims=page_dims,
            known_pages=known_pages,
        )
        errors = [i for i in issues if i.severity == "error"]
        if errors or mapped is None:
            detail = "; ".join(f"{i.code}: {i.detail}" for i in errors[:5])
            raise QaArtifactError(
                "revision_normalize_failed",
                f"{stable_key}@r{revision}: {detail or 'normalize returned None'}",
            )
        # Kind / text consistency already checked by map_fragment; require explicit trust fields
        if mapped.primary_region_type == "unverified" or mapped.content_type_status == "unknown":
            # QA artifact must set these explicitly for elevation — missing means artifact incomplete
            if rev.get("primary_region_type") in (None, "") or rev.get("content_type_status") in (
                None,
                "",
            ):
                raise QaArtifactError(
                    "trust_fields_incomplete",
                    f"{stable_key}@r{revision}: QA revision must set primary_region_type "
                    "and content_type_status explicitly",
                )

        pred = session.scalar(
            select(BankFragment).where(
                BankFragment.ocr_run_id == run.id,
                BankFragment.stable_key == stable_key,
                BankFragment.revision == ss_rev_i,
            )
        )
        if pred is None:
            raise QaBindingError(
                "predecessor_missing",
                f"missing predecessor ({stable_key!r}, revision={ss_rev_i}) on run {run.id}",
                document=slug,
            )

        # Cycle / branch: supersedes must point at existing pred; no other fragment may
        # already supersede the same pred unless it is this exact revision being re-applied.
        existing_children = session.scalars(
            select(BankFragment).where(
                BankFragment.ocr_run_id == run.id,
                BankFragment.stable_key == stable_key,
                BankFragment.supersedes_fragment_id == pred.id,
            )
        ).all()
        for child in existing_children:
            if child.revision != revision:
                raise QaConflictError(
                    "supersedes_branch",
                    f"{stable_key}: predecessor rev {ss_rev_i} already superseded by "
                    f"revision {child.revision}; refusing branch",
                    document=slug,
                )

        prepared.append(
            {
                "raw": rev,
                "mapped": mapped,
                "predecessor": pred,
                "supersedes_revision": ss_rev_i,
            }
        )
    return prepared


def apply_qa_revisions(
    session: Session,
    artifact: dict[str, Any],
    *,
    artifact_sha256: str,
    dry_run: bool = False,
) -> QaApplyResult:
    """Apply all revisions in the artifact atomically (caller commits).

    dry_run=True validates and reports without inserting.
    """
    slug = str(artifact["document_slug"])
    doc, file, run = _resolve_run(session, artifact)

    pages = session.scalars(
        select(BankOcrPage).where(BankOcrPage.ocr_run_id == run.id)
    ).all()
    known_pages = {p.page_number for p in pages}
    page_dims = {p.page_number: (p.width, p.height) for p in pages}

    prepared = _validate_revision_entries(
        session,
        artifact=artifact,
        run=run,
        page_dims=page_dims,
        known_pages=known_pages,
    )

    # Classify existing vs new
    existing_states: list[str] = []  # missing | match | conflict
    for item in prepared:
        mapped = item["mapped"]
        existing = session.scalar(
            select(BankFragment).where(
                BankFragment.ocr_run_id == run.id,
                BankFragment.stable_key == mapped.stable_key,
                BankFragment.revision == mapped.revision,
            )
        )
        planned_corr = _build_ocr_correction_json(
            item["raw"], artifact=artifact, artifact_sha256=artifact_sha256
        )
        planned_regions = _planned_region_payload(item["raw"].get("regions") or [])
        planned_tuple = _fragment_content_tuple(
            kind=mapped.kind,
            primary_region_type=mapped.primary_region_type,
            content_type=mapped.content_type,
            content_type_status=mapped.content_type_status,
            page_number=mapped.page_number,
            ocr_text=mapped.ocr_text,
            verified_transcript=mapped.verified_transcript,
            summary_text=mapped.summary_text,
            verification_status=mapped.verification_status,
            ocr_correction_json=planned_corr,
            regions=planned_regions,
        )
        if existing is None:
            existing_states.append("missing")
            item["existing"] = None
            item["planned_corr"] = planned_corr
            continue
        regs = session.scalars(
            select(BankFragmentRegion).where(BankFragmentRegion.fragment_id == existing.id)
        ).all()
        db_tuple = _fragment_content_tuple(
            kind=existing.kind,
            primary_region_type=existing.primary_region_type,
            content_type=existing.content_type,
            content_type_status=existing.content_type_status,
            page_number=existing.page_number,
            ocr_text=existing.ocr_text,
            verified_transcript=existing.verified_transcript,
            summary_text=existing.summary_text,
            verification_status=existing.verification_status,
            ocr_correction_json=existing.ocr_correction_json,
            regions=_region_payload(list(regs)),
        )
        if db_tuple != planned_tuple:
            existing_states.append("conflict")
            raise QaConflictError(
                "revision_content_conflict",
                f"{mapped.stable_key}@r{mapped.revision} exists with different "
                "text/status/regions/provenance; refusing UPDATE",
                document=slug,
            )
        existing_states.append("match")
        item["existing"] = existing
        item["planned_corr"] = planned_corr

    if any(s == "conflict" for s in existing_states):
        raise QaConflictError("revision_content_conflict", "conflict", document=slug)

    n_match = sum(1 for s in existing_states if s == "match")
    n_missing = sum(1 for s in existing_states if s == "missing")
    if n_match and n_missing:
        raise QaPartialStateError(
            "partial_revision_set",
            f"artifact partially applied ({n_match} present, {n_missing} missing); "
            "refusing automatic repair",
            document=slug,
        )

    rev_summaries = []
    for item in prepared:
        m = item["mapped"]
        elig = compute_fragment_eligibility(
            verification_status=m.verification_status,
            kind=m.kind,
            primary_region_type=m.primary_region_type,
            content_type=m.content_type,
            content_type_status=m.content_type_status,
            verified_transcript=m.verified_transcript,
            summary_text=m.summary_text,
            region_count=len(m.regions),
        )
        rev_summaries.append(
            {
                "stable_key": m.stable_key,
                "revision": m.revision,
                "supersedes_revision": item["supersedes_revision"],
                "content_type": m.content_type,
                "region_count": len(m.regions),
                "eligibility": {
                    "search": elig.eligible_search,
                    "ai_evidence": elig.eligible_ai_evidence,
                    "exact_quote": elig.eligible_exact_quote,
                    "reasons": list(elig.reasons),
                },
            }
        )

    if n_match == len(prepared) and n_missing == 0:
        latest_elig = _latest_eligibility_totals(session, run.id)
        return QaApplyResult(
            status="identical_skip" if not dry_run else "dry_run_ok",
            artifact_id=str(artifact["artifact_id"]),
            artifact_sha256=artifact_sha256,
            document_slug=slug,
            ocr_run_id=run.id,
            inserted_fragments=0,
            inserted_regions=0,
            identical_skip=True,
            code="identical_skip",
            detail="all QA revisions already present with matching content/provenance",
            revisions=rev_summaries,
            eligibility_latest=latest_elig,
            counts_after=_table_counts(session),
        )

    if dry_run:
        planned_regions = sum(len(item["mapped"].regions) for item in prepared)
        return QaApplyResult(
            status="dry_run_ok",
            artifact_id=str(artifact["artifact_id"]),
            artifact_sha256=artifact_sha256,
            document_slug=slug,
            ocr_run_id=run.id,
            inserted_fragments=len(prepared),
            inserted_regions=planned_regions,
            identical_skip=False,
            code="dry_run_would_apply",
            detail=f"would insert {len(prepared)} fragments / {planned_regions} regions",
            revisions=rev_summaries,
            eligibility_latest={},
            counts_after=_table_counts(session),
        )

    # Insert all revisions
    inserted_regions = 0
    for item in prepared:
        mapped = item["mapped"]
        pred: BankFragment = item["predecessor"]
        corr = item["planned_corr"]
        frag_id = _uid()
        session.add(
            BankFragment(
                id=frag_id,
                ocr_run_id=run.id,
                document_file_id=file.id,
                document_id=doc.id,
                stable_key=mapped.stable_key,
                revision=mapped.revision,
                kind=mapped.kind,
                primary_region_type=mapped.primary_region_type,
                content_type=mapped.content_type,
                content_type_status=mapped.content_type_status,
                page_number=mapped.page_number,
                ocr_text=mapped.ocr_text,
                cleaned_text=mapped.cleaned_text,
                verified_transcript=mapped.verified_transcript,
                summary_text=mapped.summary_text,
                verification_status=mapped.verification_status,
                ocr_correction_json=corr,
                source_role="bank_material_qa_revision",
                notes=(
                    f"QA artifact {artifact.get('artifact_id')} "
                    f"sha256={artifact_sha256[:16]}…; "
                    f"method={corr['qa_provenance']['method']}; not human manual QA"
                ),
                supersedes_fragment_id=pred.id,
                created_at=_now(),
            )
        )
        session.flush()
        for reg in mapped.regions:
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
            inserted_regions += 1
    session.flush()

    latest_elig = _latest_eligibility_totals(session, run.id)
    return QaApplyResult(
        status="applied",
        artifact_id=str(artifact["artifact_id"]),
        artifact_sha256=artifact_sha256,
        document_slug=slug,
        ocr_run_id=run.id,
        inserted_fragments=len(prepared),
        inserted_regions=inserted_regions,
        identical_skip=False,
        revisions=rev_summaries,
        eligibility_latest=latest_elig,
        counts_after=_table_counts(session),
    )


def _table_counts(session: Session) -> dict[str, int]:
    return {
        "bank_documents": int(
            session.scalar(select(func.count()).select_from(BankDocument)) or 0
        ),
        "bank_document_files": int(
            session.scalar(select(func.count()).select_from(BankDocumentFile)) or 0
        ),
        "bank_ocr_runs": int(
            session.scalar(select(func.count()).select_from(BankOcrRun)) or 0
        ),
        "bank_ocr_pages": int(
            session.scalar(select(func.count()).select_from(BankOcrPage)) or 0
        ),
        "bank_fragments": int(
            session.scalar(select(func.count()).select_from(BankFragment)) or 0
        ),
        "bank_fragment_regions": int(
            session.scalar(select(func.count()).select_from(BankFragmentRegion)) or 0
        ),
    }


def _latest_eligibility_totals(session: Session, ocr_run_id: str) -> dict[str, int]:
    # Only this run's latest keys — caller may also want corpus-wide; keep run-scoped here
    selected = list_latest_fragments_for_run(session, ocr_run_id=ocr_run_id)
    totals = {"logical_fragments": len(selected), "search": 0, "ai_evidence": 0, "exact_quote": 0}
    for s in selected:
        if s.eligibility.eligible_search:
            totals["search"] += 1
        if s.eligibility.eligible_ai_evidence:
            totals["ai_evidence"] += 1
        if s.eligibility.eligible_exact_quote:
            totals["exact_quote"] += 1
    return totals


def corpus_latest_eligibility_totals(session: Session) -> dict[str, int]:
    """Eligibility across all OCR runs, counting each stable_key once at latest revision."""
    frags = session.scalars(select(BankFragment)).all()
    latest: dict[tuple[str, str], BankFragment] = {}
    for f in frags:
        key = (f.ocr_run_id, f.stable_key)
        cur = latest.get(key)
        if cur is None or f.revision > cur.revision:
            latest[key] = f
    totals = {
        "logical_fragments": len(latest),
        "search": 0,
        "ai_evidence": 0,
        "exact_quote": 0,
        "historical_fragment_rows": len(frags),
    }
    from sqlalchemy import func as sa_func

    for f in latest.values():
        n = session.scalar(
            select(sa_func.count())
            .select_from(BankFragmentRegion)
            .where(BankFragmentRegion.fragment_id == f.id)
        )
        elig = compute_fragment_eligibility(
            verification_status=f.verification_status,
            kind=f.kind,
            primary_region_type=f.primary_region_type,
            content_type=f.content_type,
            content_type_status=f.content_type_status,
            verified_transcript=f.verified_transcript,
            summary_text=f.summary_text,
            region_count=int(n or 0),
        )
        if elig.eligible_search:
            totals["search"] += 1
        if elig.eligible_ai_evidence:
            totals["ai_evidence"] += 1
        if elig.eligible_exact_quote:
            totals["exact_quote"] += 1
    return totals


def run_apply_qa_revisions(
    *,
    artifact_path: Path,
    database_url: str,
    dry_run: bool = False,
    report_dir: Path | None = None,
) -> QaApplyResult:
    """Orchestrator: open session, apply or dry-run, commit/rollback."""
    if not database_url or not str(database_url).strip():
        raise QaRevisionError(
            "database_url_required",
            "explicit --database-url is required; refusing DATABASE_URL from environment",
        )
    artifact, artifact_sha = load_qa_artifact(Path(artifact_path))
    engine = _make_engine(database_url)
    try:
        assert_bank_schema_ready(engine)
    except SchemaNotReadyError:
        engine.dispose()
        raise

    SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        with SessionFactory() as session:
            try:
                result = apply_qa_revisions(
                    session,
                    artifact,
                    artifact_sha256=artifact_sha,
                    dry_run=dry_run,
                )
                if dry_run:
                    session.rollback()
                else:
                    session.commit()
                    # refresh corpus-wide eligibility after commit
                    result.eligibility_latest = corpus_latest_eligibility_totals(session)
                    result.counts_after = _table_counts(session)
            except QaRevisionError:
                session.rollback()
                raise
            except Exception:
                session.rollback()
                raise
    finally:
        engine.dispose()

    if report_dir is not None:
        report_dir = Path(report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = report_dir / f"bank_qa_revision_apply_{stamp}.json"
        payload = result.to_json_dict()
        payload["database"] = redact_database_url(database_url)
        payload["dry_run"] = dry_run
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (report_dir / "bank_qa_revision_apply_latest.json").write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return result
