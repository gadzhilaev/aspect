"""Server-scoped read access for bank materials API (no search, no writes)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models.bank_materials import (
    BankDocument,
    BankDocumentFile,
    BankFragment,
    BankFragmentRegion,
    BankOcrRun,
)
from app.schemas.bank_materials import (
    BankDocumentOut,
    BankFileRefOut,
    BankFragmentOut,
    BankOcrRunRefOut,
    BankRegionOut,
)
from app.services.bank_materials.eligibility import compute_fragment_eligibility
from app.services.bank_materials.fragment_revision import get_latest_fragment
from app.services.bank_materials.paths import PathEscapeError, resolve_under
from app.services.bank_materials.retrieval import source_role_meaning


@dataclass(frozen=True)
class BankMaterialsScope:
    allowed_ocr_run_ids: frozenset[str]
    storage_root: Path | None

    @property
    def configured(self) -> bool:
        return bool(self.allowed_ocr_run_ids)

    def allows_run(self, ocr_run_id: str) -> bool:
        return ocr_run_id in self.allowed_ocr_run_ids


def scope_from_settings(settings: Settings | None = None) -> BankMaterialsScope:
    s = settings or get_settings()
    return BankMaterialsScope(
        allowed_ocr_run_ids=s.bank_materials_allowed_ocr_run_id_set(),
        storage_root=s.resolved_bank_materials_storage_root(),
    )


def require_bank_materials_configured(scope: BankMaterialsScope) -> None:
    if not scope.configured:
        raise AppError(
            "BANK_MATERIALS_NOT_CONFIGURED",
            "Интеграция банковских материалов не настроена",
            503,
        )


def _not_found() -> AppError:
    return AppError("NOT_FOUND", "Материал не найден", 404)


def _file_content_href(file_id: str) -> str:
    return f"/api/v1/bank-materials/files/{file_id}/content"


def _topics(doc: BankDocument) -> list[str]:
    raw = doc.topics_json if isinstance(doc.topics_json, list) else []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            label = item.get("label") or item.get("name") or item.get("topic")
            if isinstance(label, str) and label.strip():
                out.append(label.strip())
    return out


def _qa_fields(frag: BankFragment) -> tuple[str | None, str | None, str | None]:
    corr = frag.ocr_correction_json if isinstance(frag.ocr_correction_json, dict) else {}
    prov = corr.get("qa_provenance") if isinstance(corr.get("qa_provenance"), dict) else {}
    method = str(prov["method"]) if prov.get("method") else None
    by = str(prov["performed_by"]) if prov.get("performed_by") else None
    at = str(prov["performed_at"]) if prov.get("performed_at") else None
    return method, by, at


def _public_text(frag: BankFragment, *, elig) -> tuple[str, str | None, bool, list[str]]:
    """Return (text_kind, text, restricted, restriction_reasons). Never expose raw OCR as quote."""
    if (
        frag.kind == "exact_quote"
        and elig.eligible_exact_quote
        and frag.verified_transcript
        and frag.verified_transcript.strip()
    ):
        return "exact_quote", frag.verified_transcript, False, []

    if (
        frag.kind == "summary"
        and elig.eligible_ai_evidence
        and frag.summary_text
        and frag.summary_text.strip()
    ):
        return "summary", frag.summary_text, False, []

    if (
        elig.eligible_ai_evidence
        and elig.evidence_as_summary_only
        and frag.summary_text
        and frag.summary_text.strip()
    ):
        return "summary", frag.summary_text, False, []

    reasons = list(elig.reasons) if elig.reasons else ["text_not_publicly_quotable"]
    if not elig.eligible_exact_quote:
        reasons = reasons or ["not_eligible_exact_quote"]
    return "restricted", None, True, reasons


def _region_count(session: Session, fragment_id: str) -> int:
    n = session.scalar(
        select(func.count())
        .select_from(BankFragmentRegion)
        .where(BankFragmentRegion.fragment_id == fragment_id)
    )
    return int(n or 0)


def list_allowed_runs_for_file(
    session: Session, *, file_id: str, scope: BankMaterialsScope
) -> list[BankOcrRun]:
    if not scope.configured:
        return []
    return list(
        session.scalars(
            select(BankOcrRun)
            .where(
                BankOcrRun.document_file_id == file_id,
                BankOcrRun.id.in_(scope.allowed_ocr_run_ids),
            )
            .order_by(BankOcrRun.created_at, BankOcrRun.id)
        ).all()
    )


def document_has_allowed_run(
    session: Session, *, document_id: str, scope: BankMaterialsScope
) -> bool:
    if not scope.configured:
        return False
    row = session.scalar(
        select(BankOcrRun.id)
        .join(BankDocumentFile, BankDocumentFile.id == BankOcrRun.document_file_id)
        .where(
            BankDocumentFile.document_id == document_id,
            BankOcrRun.id.in_(scope.allowed_ocr_run_ids),
        )
        .limit(1)
    )
    return row is not None


def file_has_allowed_run(
    session: Session, *, file_id: str, scope: BankMaterialsScope
) -> bool:
    return bool(list_allowed_runs_for_file(session, file_id=file_id, scope=scope))


def build_document_out(
    session: Session, *, document_id: str, scope: BankMaterialsScope
) -> BankDocumentOut:
    require_bank_materials_configured(scope)
    doc = session.get(BankDocument, document_id)
    if doc is None or not document_has_allowed_run(
        session, document_id=document_id, scope=scope
    ):
        raise _not_found()

    files = session.scalars(
        select(BankDocumentFile)
        .where(BankDocumentFile.document_id == document_id)
        .order_by(BankDocumentFile.imported_at, BankDocumentFile.id)
    ).all()

    file_outs: list[BankFileRefOut] = []
    for f in files:
        runs = list_allowed_runs_for_file(session, file_id=f.id, scope=scope)
        if not runs:
            continue
        file_outs.append(
            BankFileRefOut(
                file_id=f.id,
                original_filename=f.original_filename,
                page_count=f.page_count,
                byte_size=f.byte_size,
                pdf_sha256=f.sha256,
                revision_label=f.revision_label,
                supersedes_file_id=f.supersedes_file_id,
                content_href=_file_content_href(f.id),
                ocr_runs=[
                    BankOcrRunRefOut(
                        ocr_run_id=r.id,
                        fingerprint_hash=r.fingerprint_hash,
                        processing_status=r.processing_status,
                        schema_version=r.schema_version,
                        created_at=r.created_at,
                    )
                    for r in runs
                ],
            )
        )

    if not file_outs:
        raise _not_found()

    return BankDocumentOut(
        document_id=doc.id,
        slug=doc.slug,
        title=doc.title,
        title_status=doc.title_status,
        publication_date=doc.publication_date,
        publication_year=doc.publication_year,
        publication_month=doc.publication_month,
        publication_date_precision=doc.publication_date_precision,
        publication_date_display=doc.publication_date_display,
        period_covered=doc.period_covered,
        period_covered_status=doc.period_covered_status,
        topics=_topics(doc),
        topics_status=doc.topics_status,
        staleness_note=doc.staleness_note,
        is_current_stance=bool(doc.is_current_stance),
        document_visual_status=doc.document_visual_status,
        files=file_outs,
    )


def build_fragment_out(
    session: Session, *, fragment_id: str, scope: BankMaterialsScope
) -> BankFragmentOut:
    require_bank_materials_configured(scope)
    frag = session.get(BankFragment, fragment_id)
    if frag is None or not scope.allows_run(frag.ocr_run_id):
        raise _not_found()

    file = session.get(BankDocumentFile, frag.document_file_id)
    run = session.get(BankOcrRun, frag.ocr_run_id)
    doc = session.get(BankDocument, frag.document_id)
    if file is None or run is None or doc is None:
        raise _not_found()

    region_n = _region_count(session, frag.id)
    elig = compute_fragment_eligibility(
        verification_status=frag.verification_status,
        kind=frag.kind,
        primary_region_type=frag.primary_region_type,
        content_type=frag.content_type,
        content_type_status=frag.content_type_status,
        verified_transcript=frag.verified_transcript,
        summary_text=frag.summary_text,
        region_count=region_n,
    )
    text_kind, text, restricted, restriction_reasons = _public_text(frag, elig=elig)

    latest = get_latest_fragment(
        session, ocr_run_id=frag.ocr_run_id, stable_key=frag.stable_key
    )
    latest_rev = latest.revision if latest is not None else frag.revision
    is_latest = latest is not None and latest.id == frag.id

    regs = session.scalars(
        select(BankFragmentRegion)
        .where(BankFragmentRegion.fragment_id == frag.id)
        .order_by(BankFragmentRegion.sort_order)
    ).all()
    qa_method, qa_by, qa_at = _qa_fields(frag)

    return BankFragmentOut(
        fragment_id=frag.id,
        document_id=frag.document_id,
        document_file_id=frag.document_file_id,
        ocr_run_id=frag.ocr_run_id,
        stable_key=frag.stable_key,
        revision=frag.revision,
        is_latest_revision=is_latest,
        is_superseded=not is_latest,
        supersedes_fragment_id=frag.supersedes_fragment_id,
        latest_revision=latest_rev,
        kind=frag.kind,
        content_type=frag.content_type,
        content_type_status=frag.content_type_status,
        page_number=frag.page_number,
        regions=[
            BankRegionOut(
                page_number=r.page_number,
                sort_order=r.sort_order,
                region_type=r.region_type,
                bbox_left=r.bbox_left,
                bbox_top=r.bbox_top,
                bbox_width=r.bbox_width,
                bbox_height=r.bbox_height,
                note=r.note,
            )
            for r in regs
        ],
        verification_status=frag.verification_status,
        primary_region_type=frag.primary_region_type,
        eligible_search=elig.eligible_search,
        eligible_ai_evidence=elig.eligible_ai_evidence,
        eligible_exact_quote=elig.eligible_exact_quote,
        evidence_as_summary_only=elig.evidence_as_summary_only,
        eligibility_reasons=list(elig.reasons),
        text_kind=text_kind,  # type: ignore[arg-type]
        text=text,
        text_restricted=restricted,
        restriction_reasons=restriction_reasons,
        source_role=frag.source_role,
        source_role_meaning=source_role_meaning(
            frag.source_role, content_type=frag.content_type
        ),
        qa_method=qa_method,
        qa_performed_by=qa_by,
        qa_performed_at=qa_at,
        pdf_sha256=file.sha256,
        ocr_fingerprint_hash=run.fingerprint_hash,
        document_slug=doc.slug,
        document_title=doc.title,
        content_href=_file_content_href(file.id),
    )


def resolve_pdf_path_for_file(
    *,
    file: BankDocumentFile,
    scope: BankMaterialsScope,
) -> Path:
    """Resolve PDF under storage root; never trust client paths."""
    if scope.storage_root is None:
        raise AppError(
            "BANK_FILE_UNAVAILABLE",
            "Оригинал документа недоступен",
            404,
        )
    key = (file.storage_key or "").strip()
    if not key:
        raise AppError(
            "BANK_FILE_UNAVAILABLE",
            "Оригинал документа недоступен",
            404,
        )
    try:
        path = resolve_under(scope.storage_root, key, field="storage_key")
    except PathEscapeError as exc:
        raise AppError(
            "BANK_FILE_UNAVAILABLE",
            "Оригинал документа недоступен",
            404,
        ) from exc

    # Reject symlink escape after resolve (resolve_under already resolve()'d).
    if path.is_symlink():
        # Final target must still be under root
        try:
            path.resolve().relative_to(scope.storage_root.resolve())
        except ValueError as exc:
            raise AppError(
                "BANK_FILE_UNAVAILABLE",
                "Оригинал документа недоступен",
                404,
            ) from exc

    if not path.is_file():
        raise AppError(
            "BANK_FILE_UNAVAILABLE",
            "Оригинал документа недоступен",
            404,
        )
    return path


def verify_pdf_sha256(*, path: Path, expected_sha256: str) -> None:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    digest = h.hexdigest()
    if digest.lower() != (expected_sha256 or "").lower():
        raise AppError(
            "BANK_FILE_INTEGRITY",
            "Нарушена целостность источника",
            409,
        )


def safe_download_filename(original_filename: str) -> str:
    name = Path(original_filename or "document.pdf").name
    name = name.replace("\x00", "").replace('"', "").strip() or "document.pdf"
    if ".." in name or "/" in name or "\\" in name:
        name = "document.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name
