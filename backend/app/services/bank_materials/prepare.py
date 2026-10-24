"""Stage OCR/PDF corpus and build load plans from dry-run validators (no DB)."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.services.bank_materials.dry_run import (
    DryRunResult,
    IssueRecord,
    run_bank_materials_dry_run,
    validate_document_dir,
)
from app.services.bank_materials.fingerprint import (
    canonicalize_fingerprint,
    fingerprint_hash,
)
from app.services.bank_materials.normalize import (
    NormalizedFragment,
    NormalizedPublication,
    map_fragment,
    parse_publication,
)
from app.services.bank_materials.paths import PathEscapeError, resolve_under


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rel_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


@dataclass
class StagedFile:
    relative_path: str
    absolute_path: Path
    sha256: str
    byte_size: int


@dataclass
class StagingManifest:
    staging_root: Path
    ocr_dir: Path
    pdf_dir: Path
    storage_root: Path
    files: dict[str, StagedFile] = field(default_factory=dict)

    def verify_unchanged(self) -> None:
        """Raise if any staged file content changed since staging."""
        for rel, entry in self.files.items():
            if not entry.absolute_path.is_file():
                raise StagingIntegrityError(f"staged file missing: {rel}")
            actual = _sha256_file(entry.absolute_path)
            if actual != entry.sha256:
                raise StagingIntegrityError(
                    f"staged file changed after preflight: {rel} "
                    f"(expected {entry.sha256[:12]}…, got {actual[:12]}…)"
                )
            size = entry.absolute_path.stat().st_size
            if size != entry.byte_size:
                raise StagingIntegrityError(
                    f"staged file size changed: {rel} ({entry.byte_size} → {size})"
                )


class StagingIntegrityError(RuntimeError):
    pass


class PrepareError(RuntimeError):
    pass


@dataclass
class PreparedPage:
    page_number: int
    processing_status: str
    width: int | None
    height: int | None
    image_storage_key: str | None
    raw_text_storage_key: str | None
    cleaned_text_storage_key: str | None
    tsv_storage_key: str | None
    words_storage_key: str | None
    word_count: int | None
    mean_confidence: float | None
    median_confidence: float | None
    psm_used: int | None
    visual_verification_status: str
    content_regions_json: list[Any]
    visual_checks_json: dict[str, Any]
    error: str | None


@dataclass
class PreparedDocument:
    slug: str
    title: str | None
    title_status: str
    publication: NormalizedPublication
    period_covered: str | None
    period_covered_status: str
    topics_json: list[Any]
    topics_status: str
    staleness_note: str | None
    is_current_stance: bool
    document_visual_status: str
    source_sha256: str
    original_filename: str
    page_count: int
    byte_size: int
    pdf_storage_key: str
    fingerprint_hash: str
    fingerprint_canonical: dict[str, Any]
    artifact_root_key: str
    schema_version: int
    tesseract_version_line: str
    lang: str
    psm_default: int
    preserve_interword_spaces: bool
    eng_traineddata_sha256: str
    rus_traineddata_sha256: str
    processing_status: str
    pages_ok_json: list[Any]
    pages_failed_json: list[Any]
    pages: list[PreparedPage]
    fragments: list[NormalizedFragment]
    content_digest: str
    dry_run_eligibility: dict[str, int]

    def expected_counts(self) -> dict[str, int]:
        return {
            "pages": len(self.pages),
            "fragments": len(self.fragments),
            "regions": sum(len(f.regions) for f in self.fragments),
        }


def stage_corpus(
    *,
    input_dir: Path,
    pdf_dir: Path,
    storage_root: Path | None = None,
    staging_parent: Path | None = None,
) -> StagingManifest:
    """Copy OCR dirs + PDFs into a staging tree; record per-file SHA."""
    input_dir = input_dir.resolve()
    pdf_dir = pdf_dir.resolve()
    if not input_dir.is_dir():
        raise PrepareError(f"input_dir missing: {input_dir}")
    if not pdf_dir.is_dir():
        raise PrepareError(f"pdf_dir missing: {pdf_dir}")

    if storage_root is not None:
        storage = Path(storage_root).resolve()
        storage.mkdir(parents=True, exist_ok=True)
        parent = storage
    else:
        parent = Path(staging_parent) if staging_parent else Path(tempfile.gettempdir())
        storage = None

    parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix="bank_import_stage_", dir=str(parent)))
    # Keys resolve under storage_root; when omitted, staging_root is the key root.
    if storage is None:
        storage = staging_root.resolve()
    staged_ocr = staging_root / "ocr"
    staged_pdf = staging_root / "pdf"
    staged_ocr.mkdir(parents=True)
    staged_pdf.mkdir(parents=True)

    files: dict[str, StagedFile] = {}

    def _register(abs_path: Path) -> None:
        rel = _rel_posix(storage, abs_path)
        files[rel] = StagedFile(
            relative_path=rel,
            absolute_path=abs_path,
            sha256=_sha256_file(abs_path),
            byte_size=abs_path.stat().st_size,
        )

    for doc_dir in sorted(p for p in input_dir.iterdir() if p.is_dir()):
        if not (doc_dir / "manifest.json").is_file():
            continue
        dest = staged_ocr / doc_dir.name
        shutil.copytree(doc_dir, dest)
        for path in dest.rglob("*"):
            if path.is_file():
                _register(path)

    for pdf in sorted(pdf_dir.glob("*.pdf")):
        dest = staged_pdf / pdf.name
        shutil.copy2(pdf, dest)
        _register(dest)

    return StagingManifest(
        staging_root=staging_root,
        ocr_dir=staged_ocr,
        pdf_dir=staged_pdf,
        storage_root=storage,
        files=files,
    )


def storage_key_for(storage_root: Path, path: Path) -> str:
    """Opaque relative key under storage_root (never an absolute host path)."""
    try:
        return _rel_posix(storage_root, path)
    except ValueError as exc:
        raise PrepareError(
            f"path {path} is outside storage_root {storage_root}"
        ) from exc


def _page_storage_keys(
    doc_dir: Path,
    page_number: int,
    storage_root: Path,
) -> dict[str, str | None]:
    mapping = {
        "image_storage_key": f"pages/page_{page_number:03d}.png",
        "raw_text_storage_key": f"page_{page_number:03d}_raw.txt",
        "cleaned_text_storage_key": f"page_{page_number:03d}_cleaned.txt",
        "tsv_storage_key": f"page_{page_number:03d}_ocr.tsv",
        "words_storage_key": f"page_{page_number:03d}_words.json",
    }
    out: dict[str, str | None] = {}
    for field_name, rel in mapping.items():
        try:
            abs_path = resolve_under(doc_dir, rel, field=rel)
        except PathEscapeError:
            out[field_name] = None
            continue
        out[field_name] = storage_key_for(storage_root, abs_path) if abs_path.is_file() else None
    return out


def build_prepared_document(
    doc_dir: Path,
    *,
    input_dir: Path,
    pdf_dir: Path,
    storage_root: Path,
) -> tuple[PreparedDocument | None, list[IssueRecord], list[IssueRecord]]:
    """Validate one doc (shared dry-run) and build a DB-ready plan."""
    summary, errors, warnings = validate_document_dir(
        doc_dir, input_dir=input_dir, pdf_dir=pdf_dir
    )
    if errors or not summary.get("ok"):
        return None, errors, warnings

    slug = summary["slug"]
    man = json.loads((doc_dir / "manifest.json").read_text(encoding="utf-8"))
    identity = man.get("document_identity") or {}
    if not isinstance(identity, dict):
        identity = {}

    pub = parse_publication(identity, document=slug)
    title = identity.get("confirmed_title")
    title_status = str(identity.get("confirmed_title_status") or "unknown")
    if title_status not in ("confirmed", "unknown", "filename_hint"):
        title_status = "filename_hint" if title else "unknown"

    period_status = str(identity.get("period_covered_status") or "unknown")
    if period_status not in ("confirmed", "unknown"):
        period_status = "unknown"
    topics = identity.get("topics") if isinstance(identity.get("topics"), list) else []
    topics_status = str(identity.get("topics_status") or "unknown")
    if topics_status not in ("confirmed", "unknown"):
        topics_status = "unknown"

    staleness = identity.get("staleness_note")
    staleness_s = str(staleness) if staleness is not None else None
    # Historical materials are never current stance unless explicitly set true.
    is_current = bool(identity.get("is_current_stance")) if "is_current_stance" in identity else False
    if staleness_s:
        is_current = False

    visual = str(man.get("document_visual_status") or "unverified")
    if visual not in (
        "unverified",
        "partial_spot_check",
        "verified_spot_check",
        "verified",
    ):
        visual = "unverified"

    source_filename = str(man.get("source_filename") or f"{slug}.pdf")
    pdf_path = pdf_dir / Path(source_filename).name
    if not pdf_path.is_file():
        return None, errors, warnings

    pdf_storage_key = storage_key_for(storage_root, pdf_path)
    byte_size = pdf_path.stat().st_size
    source_sha = str(summary["source_sha256"])
    fh = str(summary["fingerprint_hash"])
    canonical = dict(summary.get("fingerprint_canonical") or {})

    pages_meta = man.get("pages") or []
    page_dims: dict[int, tuple[int | None, int | None]] = {}
    known_pages: set[int] = set()
    page_psm_used: list[int | None] = []
    prepared_pages: list[PreparedPage] = []
    pages_ok: list[int] = []
    pages_failed: list[int] = []

    for entry in pages_meta:
        if not isinstance(entry, dict):
            continue
        pnum = int(entry["page"])
        known_pages.add(pnum)
        image = entry.get("image") or {}
        w = image.get("width")
        h = image.get("height")
        w_i = int(w) if w is not None else None
        h_i = int(h) if h is not None else None
        page_dims[pnum] = (w_i, h_i)

        meta_path = doc_dir / f"page_{pnum:03d}_meta.json"
        page_meta = (
            json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
        )
        ocr_block = (page_meta.get("ocr") or {}) if isinstance(page_meta, dict) else {}
        psm_used = ocr_block.get("psm_used")
        try:
            psm_i = int(psm_used) if psm_used is not None else None
        except (TypeError, ValueError):
            psm_i = None
        page_psm_used.append(psm_i)

        keys = _page_storage_keys(doc_dir, pnum, storage_root)
        status = str(entry.get("processing_status") or entry.get("status") or "ok")
        if status not in ("ok", "failed", "incomplete"):
            status = "ok"
        if status == "ok":
            pages_ok.append(pnum)
        else:
            pages_failed.append(pnum)

        vstatus = str(
            (page_meta.get("visual_verification_status") if isinstance(page_meta, dict) else None)
            or "unverified"
        )
        if vstatus not in (
            "unverified",
            "verified_spot_check",
            "verified_partial",
            "verified",
        ):
            vstatus = "unverified"

        regions = page_meta.get("content_regions") if isinstance(page_meta, dict) else None
        checks = page_meta.get("visual_checks") if isinstance(page_meta, dict) else None
        prepared_pages.append(
            PreparedPage(
                page_number=pnum,
                processing_status=status,
                width=w_i,
                height=h_i,
                image_storage_key=keys["image_storage_key"],
                raw_text_storage_key=keys["raw_text_storage_key"],
                cleaned_text_storage_key=keys["cleaned_text_storage_key"],
                tsv_storage_key=keys["tsv_storage_key"],
                words_storage_key=keys["words_storage_key"],
                word_count=(
                    int(ocr_block["word_count"])
                    if ocr_block.get("word_count") is not None
                    else None
                ),
                mean_confidence=(
                    float(ocr_block["mean_confidence"])
                    if ocr_block.get("mean_confidence") is not None
                    else None
                ),
                median_confidence=(
                    float(ocr_block["median_confidence"])
                    if ocr_block.get("median_confidence") is not None
                    else None
                ),
                psm_used=psm_i,
                visual_verification_status=vstatus,
                content_regions_json=list(regions) if isinstance(regions, list) else [],
                visual_checks_json=dict(checks) if isinstance(checks, dict) else {},
                error=str(page_meta["error"])
                if isinstance(page_meta, dict) and page_meta.get("error") is not None
                else None,
            )
        )

    # Recompute fingerprint with page PSM (same as dry-run)
    if not canonical:
        fp_raw = man.get("fingerprint") or {}
        tess = man.get("tesseract") or {}
        merged = {**tess, **fp_raw}
        if "source_sha256" not in merged:
            merged["source_sha256"] = source_sha
        if "tesseract_version_line" not in merged and "version_line" in tess:
            merged["tesseract_version_line"] = tess["version_line"]
        canonical = canonicalize_fingerprint(merged, page_psm_used=page_psm_used)
        fh = fingerprint_hash(canonical)

    fragments: list[NormalizedFragment] = []
    frag_path = doc_dir / "fragments.json"
    if frag_path.is_file():
        fr_doc = json.loads(frag_path.read_text(encoding="utf-8"))
        for raw in fr_doc.get("fragments") or []:
            if not isinstance(raw, dict):
                continue
            mapped, issues = map_fragment(
                raw,
                document=slug,
                page_dims=page_dims,
                known_pages=known_pages,
            )
            for issue in issues:
                rec = IssueRecord(
                    severity=issue.severity,
                    code=issue.code,
                    document=issue.document,
                    page=issue.page,
                    stable_key=issue.stable_key,
                    field=issue.field,
                    detail=issue.detail,
                )
                (errors if issue.severity == "error" else warnings).append(rec)
            if mapped is None or not mapped.suitable_for_storage:
                continue
            fragments.append(mapped)

    if errors:
        return None, errors, warnings

    artifact_root_key = storage_key_for(storage_root, doc_dir)
    tess_line = str(
        canonical.get("tesseract_version_line")
        or (man.get("tesseract") or {}).get("version_line")
        or "unknown"
    )
    lang = str(canonical.get("lang") or "rus+eng")
    psm_default = int(canonical.get("psm") if canonical.get("psm") is not None else 3)
    preserve = bool(canonical.get("preserve_interword_spaces", True))
    eng = str(canonical.get("eng_traineddata_sha256") or "")
    rus = str(canonical.get("rus_traineddata_sha256") or "")
    schema_version = int(canonical.get("schema_version") or man.get("schema_version") or 2)
    proc = str(man.get("processing_status") or "complete")
    if proc not in ("complete", "incomplete"):
        proc = "complete"

    elig = summary.get("eligibility") or {}
    plan = PreparedDocument(
        slug=slug,
        title=str(title) if title is not None else None,
        title_status=title_status,
        publication=pub,
        period_covered=(
            str(identity["period_covered"])
            if identity.get("period_covered") is not None
            else None
        ),
        period_covered_status=period_status,
        topics_json=list(topics),
        topics_status=topics_status,
        staleness_note=staleness_s,
        is_current_stance=is_current,
        document_visual_status=visual,
        source_sha256=source_sha,
        original_filename=Path(source_filename).name,
        page_count=len(prepared_pages),
        byte_size=byte_size,
        pdf_storage_key=pdf_storage_key,
        fingerprint_hash=fh,
        fingerprint_canonical=canonical,
        artifact_root_key=artifact_root_key,
        schema_version=schema_version,
        tesseract_version_line=tess_line[:128],
        lang=lang[:32],
        psm_default=psm_default,
        preserve_interword_spaces=preserve,
        eng_traineddata_sha256=eng,
        rus_traineddata_sha256=rus,
        processing_status=proc,
        pages_ok_json=sorted(pages_ok),
        pages_failed_json=sorted(pages_failed),
        pages=sorted(prepared_pages, key=lambda p: p.page_number),
        fragments=fragments,
        content_digest="",
        dry_run_eligibility={
            "search": int(elig.get("search") or 0),
            "ai_evidence": int(elig.get("ai_evidence") or 0),
            "exact_quote": int(elig.get("exact_quote") or 0),
        },
    )
    plan.content_digest = compute_content_digest(plan)
    return plan, errors, warnings


def compute_content_digest(plan: PreparedDocument) -> str:
    """Stable digest of normalized payload used for identical_skip / conflict."""
    payload = {
        "slug": plan.slug,
        "title": plan.title,
        "title_status": plan.title_status,
        "publication": {
            "precision": plan.publication.precision,
            "publication_date": (
                plan.publication.publication_date.isoformat()
                if plan.publication.publication_date
                else None
            ),
            "publication_year": plan.publication.publication_year,
            "publication_month": plan.publication.publication_month,
            "display": plan.publication.display,
        },
        "period_covered": plan.period_covered,
        "period_covered_status": plan.period_covered_status,
        "topics_json": plan.topics_json,
        "topics_status": plan.topics_status,
        "staleness_note": plan.staleness_note,
        "is_current_stance": plan.is_current_stance,
        "document_visual_status": plan.document_visual_status,
        "source_sha256": plan.source_sha256,
        "fingerprint_hash": plan.fingerprint_hash,
        "fingerprint_canonical": plan.fingerprint_canonical,
        "pages": [
            {
                "page_number": p.page_number,
                "processing_status": p.processing_status,
                "width": p.width,
                "height": p.height,
                "image_storage_key": p.image_storage_key,
                "raw_text_storage_key": p.raw_text_storage_key,
                "cleaned_text_storage_key": p.cleaned_text_storage_key,
                "tsv_storage_key": p.tsv_storage_key,
                "words_storage_key": p.words_storage_key,
                "word_count": p.word_count,
                "mean_confidence": p.mean_confidence,
                "median_confidence": p.median_confidence,
                "psm_used": p.psm_used,
                "visual_verification_status": p.visual_verification_status,
                "content_regions_json": p.content_regions_json,
                "visual_checks_json": p.visual_checks_json,
            }
            for p in plan.pages
        ],
        "fragments": [
            {
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
                "supersedes_stable_key": f.supersedes_stable_key,
                "supersedes_revision": f.supersedes_revision,
                "ocr_correction_json": f.ocr_correction_json,
                "source_role": f.source_role,
                "fragment_notes": f.fragment_notes,
                "regions": [
                    {
                        "page_number": r.page_number,
                        "sort_order": r.sort_order,
                        "region_type": r.region_type,
                        "bbox_left": r.bbox_left,
                        "bbox_top": r.bbox_top,
                        "bbox_width": r.bbox_width,
                        "bbox_height": r.bbox_height,
                        "note": r.note,
                    }
                    for r in f.regions
                ],
            }
            for f in sorted(plan.fragments, key=lambda x: (x.stable_key, x.revision))
        ],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return _sha256_bytes(blob.encode("utf-8"))


def preflight_corpus(
    *,
    input_dir: Path,
    pdf_dir: Path,
) -> DryRunResult:
    """Full-corpus dry-run used before load."""
    return run_bank_materials_dry_run(input_dir=input_dir, pdf_dir=pdf_dir)


def prepared_document_as_dict(plan: PreparedDocument) -> dict[str, Any]:
    """Debug/report helper (no absolute paths)."""
    return {
        "slug": plan.slug,
        "source_sha256": plan.source_sha256,
        "fingerprint_hash": plan.fingerprint_hash,
        "content_digest": plan.content_digest,
        "pdf_storage_key": plan.pdf_storage_key,
        "artifact_root_key": plan.artifact_root_key,
        "counts": plan.expected_counts(),
        "dry_run_eligibility": plan.dry_run_eligibility,
        "publication": asdict(plan.publication)
        if hasattr(plan.publication, "__dataclass_fields__")
        else None,
    }
