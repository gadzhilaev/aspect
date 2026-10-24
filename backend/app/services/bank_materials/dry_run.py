"""Dry-run validation of bank OCR corpus against schema 007 (no DB writes)."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from app.services.bank_materials.fingerprint import (
    canonicalize_fingerprint,
    fingerprint_hash,
    strip_absolute_tool_paths,
)
from app.services.bank_materials.normalize import (
    NormIssue,
    map_fragment,
    parse_publication,
)
from app.services.bank_materials.paths import PathEscapeError, resolve_under

EXPECTED_PAGE_FILES = (
    ("raw", "page_{n:03d}_raw.txt"),
    ("cleaned", "page_{n:03d}_cleaned.txt"),
    ("tsv", "page_{n:03d}_ocr.tsv"),
    ("words", "page_{n:03d}_words.json"),
    ("meta", "page_{n:03d}_meta.json"),
    ("png", "pages/page_{n:03d}.png"),
)


@dataclass
class IssueRecord:
    severity: str
    code: str
    document: str | None
    page: int | None
    stable_key: str | None
    field: str | None
    detail: str


@dataclass
class DryRunResult:
    ok: bool
    started_at: str
    finished_at: str
    input_dir: str
    pdf_dir: str
    documents: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)
    errors: list[IssueRecord] = field(default_factory=list)
    warnings: list[IssueRecord] = field(default_factory=list)
    blocking_error_count: int = 0
    warning_count: int = 0

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "input_dir": self.input_dir,
            "pdf_dir": self.pdf_dir,
            "blocking_error_count": self.blocking_error_count,
            "warning_count": self.warning_count,
            "totals": self.totals,
            "documents": self.documents,
            "errors": [asdict(e) for e in self.errors],
            "warnings": [asdict(w) for w in self.warnings],
        }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _pdf_page_count(path: Path) -> int:
    reader = PdfReader(str(path), strict=False)
    return len(reader.pages)


def _add_issue(
    bag: list[IssueRecord],
    *,
    severity: str,
    code: str,
    document: str | None = None,
    page: int | None = None,
    stable_key: str | None = None,
    field: str | None = None,
    detail: str,
) -> None:
    bag.append(
        IssueRecord(
            severity=severity,
            code=code,
            document=document,
            page=page,
            stable_key=stable_key,
            field=field,
            detail=detail,
        )
    )


def _from_norm(issue: NormIssue) -> IssueRecord:
    return IssueRecord(
        severity=issue.severity,
        code=issue.code,
        document=issue.document,
        page=issue.page,
        stable_key=issue.stable_key,
        field=issue.field,
        detail=issue.detail,
    )


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def validate_document_dir(
    doc_dir: Path,
    *,
    input_dir: Path,
    pdf_dir: Path,
) -> tuple[dict[str, Any], list[IssueRecord], list[IssueRecord]]:
    """Validate one OCR document directory. Returns summary, errors, warnings."""
    errors: list[IssueRecord] = []
    warnings: list[IssueRecord] = []
    slug = doc_dir.name
    summary: dict[str, Any] = {
        "slug": slug,
        "doc_dir": str(doc_dir),
        "ok": True,
        "pages": 0,
        "fragments": 0,
        "eligibility": Counter(),
        "verification": Counter(),
        "content_types": Counter(),
        "kinds": Counter(),
        "staleness_note": None,
        "publication": None,
        "source_sha256": None,
        "fingerprint_hash": None,
    }

    def err(**kw: Any) -> None:
        _add_issue(errors, severity="error", **kw)
        summary["ok"] = False

    def warn(**kw: Any) -> None:
        _add_issue(warnings, severity="warning", **kw)

    try:
        doc_dir.resolve().relative_to(input_dir.resolve())
    except ValueError:
        err(
            code="doc_dir_escape",
            document=slug,
            field="doc_dir",
            detail=f"{doc_dir} outside input_dir",
        )
        return summary, errors, warnings

    man_path = doc_dir / "manifest.json"
    if not man_path.is_file():
        err(code="missing_manifest", document=slug, field="manifest.json", detail="file missing")
        return summary, errors, warnings

    manifest = _load_json(man_path)
    if not manifest:
        err(code="manifest_unreadable", document=slug, field="manifest.json", detail="invalid JSON")
        return summary, errors, warnings

    source_filename = manifest.get("source_filename") or f"{slug}.pdf"
    source_pdf_rel = manifest.get("source_pdf")
    # Locate PDF under pdf_dir by filename (not by executing any tool path)
    pdf_path = pdf_dir / Path(str(source_filename)).name
    if not pdf_path.is_file() and source_pdf_rel:
        try:
            # Only allow basename from source_pdf under pdf_dir
            pdf_path = resolve_under(pdf_dir, Path(str(source_pdf_rel)).name, field="source_pdf")
        except PathEscapeError as exc:
            err(code="pdf_path_escape", document=slug, field="source_pdf", detail=str(exc))
            return summary, errors, warnings

    if not pdf_path.is_file():
        err(
            code="pdf_missing",
            document=slug,
            field="source_filename",
            detail=f"PDF not found at {pdf_path}",
        )
        return summary, errors, warnings

    try:
        pdf_path.resolve().relative_to(pdf_dir.resolve())
    except ValueError:
        err(
            code="pdf_path_escape",
            document=slug,
            field="source_filename",
            detail=f"{pdf_path} outside pdf_dir",
        )
        return summary, errors, warnings

    actual_sha = _sha256_file(pdf_path)
    declared_sha = manifest.get("source_sha256")
    summary["source_sha256"] = actual_sha
    if not declared_sha:
        err(code="manifest_missing_sha", document=slug, field="source_sha256", detail="missing")
    elif str(declared_sha).lower() != actual_sha.lower():
        err(
            code="pdf_sha_mismatch",
            document=slug,
            field="source_sha256",
            detail=f"declared {declared_sha} != actual {actual_sha}",
        )

    try:
        pdf_pages = _pdf_page_count(pdf_path)
    except Exception as exc:  # noqa: BLE001
        err(code="pdf_unreadable", document=slug, field="pdf", detail=str(exc))
        return summary, errors, warnings

    pages_meta = manifest.get("pages") or []
    if not isinstance(pages_meta, list):
        err(code="pages_not_list", document=slug, field="pages", detail="pages must be a list")
        pages_meta = []

    page_numbers: list[int] = []
    page_dims: dict[int, tuple[int | None, int | None]] = {}
    page_psm_used: list[int | None] = []
    known_pages: set[int] = set()

    for entry in pages_meta:
        if not isinstance(entry, dict):
            err(code="page_entry_invalid", document=slug, field="pages", detail="non-object page")
            continue
        try:
            pnum = int(entry.get("page"))
        except (TypeError, ValueError):
            err(
                code="page_number_invalid",
                document=slug,
                field="pages.page",
                detail=f"invalid {entry.get('page')!r}",
            )
            continue
        if pnum < 1:
            err(
                code="page_number_lt_1",
                document=slug,
                page=pnum,
                field="pages.page",
                detail="page_number must be >= 1",
            )
        if pnum in known_pages:
            err(
                code="duplicate_page_number",
                document=slug,
                page=pnum,
                field="pages.page",
                detail=f"duplicate page {pnum}",
            )
        known_pages.add(pnum)
        page_numbers.append(pnum)

        image = entry.get("image") or {}
        width = image.get("width")
        height = image.get("height")
        try:
            w_i = int(width) if width is not None else None
            h_i = int(height) if height is not None else None
        except (TypeError, ValueError):
            w_i, h_i = None, None
            err(
                code="page_dims_invalid",
                document=slug,
                page=pnum,
                field="image",
                detail=f"bad width/height {width!r}/{height!r}",
            )
        if w_i is not None and w_i <= 0:
            err(code="page_width_non_positive", document=slug, page=pnum, field="image.width", detail=str(w_i))
        if h_i is not None and h_i <= 0:
            err(code="page_height_non_positive", document=slug, page=pnum, field="image.height", detail=str(h_i))
        page_dims[pnum] = (w_i, h_i)

        # Per-page meta + artifacts
        meta_path = doc_dir / f"page_{pnum:03d}_meta.json"
        page_meta = _load_json(meta_path) if meta_path.is_file() else None
        if page_meta is None:
            err(
                code="missing_page_meta",
                document=slug,
                page=pnum,
                field="page_meta",
                detail=f"missing {meta_path.name}",
            )
        else:
            # Confinement: relative paths inside page meta / ocr block
            for key in ("png_path", "embedded_path"):
                img = (page_meta.get("image") or {}) if isinstance(page_meta.get("image"), dict) else {}
                rel = img.get(key) or (image.get(key) if key in image else None)
                if rel:
                    try:
                        resolve_under(doc_dir, str(rel), field=f"page_{pnum}.{key}")
                    except PathEscapeError as exc:
                        err(
                            code="artifact_path_escape",
                            document=slug,
                            page=pnum,
                            field=key,
                            detail=str(exc),
                        )
            ocr_block = page_meta.get("ocr") or {}
            psm_used = ocr_block.get("psm_used")
            try:
                page_psm_used.append(int(psm_used) if psm_used is not None else None)
            except (TypeError, ValueError):
                page_psm_used.append(None)
                warn(
                    code="psm_used_invalid",
                    document=slug,
                    page=pnum,
                    field="ocr.psm_used",
                    detail=f"non-int {psm_used!r}",
                )
            # Do not execute absolute tesseract paths if present in fingerprint
            fp = page_meta.get("fingerprint") or {}
            if isinstance(fp, dict):
                for bad in ("tesseract_binary", "tessdata_dir"):
                    if bad in fp and isinstance(fp[bad], str) and (
                        fp[bad].startswith("/") or (len(fp[bad]) > 1 and fp[bad][1] == ":")
                    ):
                        warn(
                            code="absolute_tool_path_ignored",
                            document=slug,
                            page=pnum,
                            field=f"fingerprint.{bad}",
                            detail="absolute OCR tool path recorded but not executed",
                        )

        for _label, pattern in EXPECTED_PAGE_FILES:
            rel = pattern.format(n=pnum)
            try:
                art = resolve_under(doc_dir, rel, field=rel)
            except PathEscapeError as exc:
                err(code="artifact_path_escape", document=slug, page=pnum, field=rel, detail=str(exc))
                continue
            if not art.is_file():
                # Prefer declared names from page entry when present
                err(
                    code="missing_page_artifact",
                    document=slug,
                    page=pnum,
                    field=rel,
                    detail=f"expected artifact missing: {rel}",
                )

        status = entry.get("processing_status") or entry.get("status")
        if status not in ("ok", "failed", "incomplete"):
            warn(
                code="page_processing_status_unknown",
                document=slug,
                page=pnum,
                field="processing_status",
                detail=f"{status!r}",
            )

    summary["pages"] = len(known_pages)
    declared_count = manifest.get("page_count")
    if declared_count is not None and int(declared_count) != len(known_pages):
        err(
            code="page_count_mismatch_manifest",
            document=slug,
            field="page_count",
            detail=f"manifest page_count={declared_count} vs listed pages={len(known_pages)}",
        )
    if pdf_pages != len(known_pages):
        err(
            code="page_count_mismatch_pdf",
            document=slug,
            field="page_count",
            detail=f"PDF pages={pdf_pages} vs OCR pages={len(known_pages)}",
        )

    # Fingerprint
    fp_raw = manifest.get("fingerprint") or {}
    tess = manifest.get("tesseract") or {}
    merged = {**tess, **fp_raw}
    if "source_sha256" not in merged:
        merged["source_sha256"] = declared_sha or actual_sha
    if "tesseract_version_line" not in merged and "version_line" in tess:
        merged["tesseract_version_line"] = tess["version_line"]
    canonical = canonicalize_fingerprint(merged, page_psm_used=page_psm_used)
    missing_fp = [k for k in ("source_sha256", "lang", "eng_traineddata_sha256", "rus_traineddata_sha256") if not canonical.get(k)]
    for k in missing_fp:
        err(
            code="fingerprint_field_missing",
            document=slug,
            field=k,
            detail="required fingerprint field missing after stripping host paths",
        )
    fh = fingerprint_hash(canonical)
    summary["fingerprint_hash"] = fh
    summary["fingerprint_canonical"] = canonical
    summary["fingerprint_stripped_keys"] = sorted(
        set(merged) - set(strip_absolute_tool_paths(merged))
    )

    # Identity / dates — never use pdf_creation_date as publication
    identity = manifest.get("document_identity") or {}
    if not isinstance(identity, dict):
        identity = {}
        err(code="identity_not_object", document=slug, field="document_identity", detail="expected object")
    pub = parse_publication(identity, document=slug)
    for issue in pub.issues:
        (errors if issue.severity == "error" else warnings).append(_from_norm(issue))
        if issue.severity == "error":
            summary["ok"] = False
    summary["publication"] = {
        "precision": pub.precision,
        "publication_date": pub.publication_date.isoformat() if pub.publication_date else None,
        "publication_year": pub.publication_year,
        "publication_month": pub.publication_month,
        "display": pub.display,
        "status": pub.status,
        "period_covered": identity.get("period_covered"),
        "period_covered_status": identity.get("period_covered_status"),
    }
    summary["staleness_note"] = identity.get("staleness_note")
    # Historical note is expected limitation, not corpus-wide failure
    if identity.get("staleness_note"):
        warn(
            code="historical_material_note",
            document=slug,
            field="staleness_note",
            detail=str(identity["staleness_note"]),
        )

    # Fragments
    frag_path = doc_dir / "fragments.json"
    fragments_out: list[dict[str, Any]] = []
    key_rev_seen: set[tuple[str, int]] = set()
    if not frag_path.is_file():
        warn(
            code="missing_fragments_json",
            document=slug,
            field="fragments.json",
            detail="no fragments file; document has pages only",
        )
    else:
        fr_doc = _load_json(frag_path)
        if not fr_doc:
            err(code="fragments_unreadable", document=slug, field="fragments.json", detail="invalid JSON")
        else:
            raw_frags = fr_doc.get("fragments") or []
            if not isinstance(raw_frags, list):
                err(code="fragments_not_list", document=slug, field="fragments", detail="expected list")
                raw_frags = []
            for raw in raw_frags:
                if not isinstance(raw, dict):
                    err(code="fragment_not_object", document=slug, field="fragments", detail="non-object")
                    continue
                mapped, issues = map_fragment(
                    raw,
                    document=slug,
                    page_dims=page_dims,
                    known_pages=known_pages,
                )
                for issue in issues:
                    (errors if issue.severity == "error" else warnings).append(_from_norm(issue))
                    if issue.severity == "error":
                        summary["ok"] = False
                if mapped is None:
                    continue
                kr = (mapped.stable_key, mapped.revision)
                if kr in key_rev_seen:
                    err(
                        code="duplicate_stable_key_revision",
                        document=slug,
                        page=mapped.page_number,
                        stable_key=mapped.stable_key,
                        field="revision",
                        detail=f"duplicate ({mapped.stable_key!r}, revision={mapped.revision})",
                    )
                key_rev_seen.add(kr)

                # Supersedes reference presence (same-doc check only at dry-run: key exists)
                if mapped.supersedes_stable_key:
                    if mapped.supersedes_stable_key == mapped.stable_key and (
                        mapped.supersedes_revision == mapped.revision
                    ):
                        err(
                            code="supersedes_self",
                            document=slug,
                            stable_key=mapped.stable_key,
                            field="supersedes",
                            detail="supersedes points at same key/revision",
                        )
                    # Cross-key supersedes within file is OK if target exists among fragments
                    # (full chain mono checked by loader). Here only note missing target.
                    targets = {
                        (f.get("id") or f.get("stable_key"), int(f.get("revision", 1)))
                        for f in raw_frags
                        if isinstance(f, dict)
                    }
                    want_rev = mapped.supersedes_revision
                    if want_rev is None:
                        # any revision of that key
                        if not any(t[0] == mapped.supersedes_stable_key for t in targets):
                            err(
                                code="supersedes_target_missing",
                                document=slug,
                                stable_key=mapped.stable_key,
                                field="supersedes",
                                detail=f"no fragment with id {mapped.supersedes_stable_key!r}",
                            )
                    elif (mapped.supersedes_stable_key, want_rev) not in targets:
                        err(
                            code="supersedes_target_missing",
                            document=slug,
                            stable_key=mapped.stable_key,
                            field="supersedes",
                            detail=f"missing ({mapped.supersedes_stable_key!r}, rev={want_rev})",
                        )

                summary["verification"][mapped.verification_status] += 1
                summary["kinds"][mapped.kind] += 1
                if mapped.content_type:
                    summary["content_types"][mapped.content_type] += 1
                el = mapped.eligibility
                if el.get("eligible_exact_quote"):
                    summary["eligibility"]["exact_quote"] += 1
                if el.get("eligible_ai_evidence"):
                    summary["eligibility"]["ai_evidence"] += 1
                if el.get("eligible_search"):
                    summary["eligibility"]["search"] += 1

                fragments_out.append(
                    {
                        "stable_key": mapped.stable_key,
                        "revision": mapped.revision,
                        "kind": mapped.kind,
                        "page": mapped.page_number,
                        "verification_status": mapped.verification_status,
                        "primary_region_type": mapped.primary_region_type,
                        "primary_region_type_source": mapped.primary_region_type_source,
                        "content_type": mapped.content_type,
                        "content_type_status": mapped.content_type_status,
                        "content_type_status_source": mapped.content_type_status_source,
                        "missing_trust_fields": mapped.missing_trust_fields,
                        "region_count": len(mapped.regions),
                        "regions_null_bbox": sum(
                            1
                            for reg in mapped.regions
                            if reg.bbox_left is None
                        ),
                        "eligibility": mapped.eligibility,
                        "suitable_for_storage": mapped.suitable_for_storage,
                        "suitable_for_ai_evidence": mapped.suitable_for_ai_evidence,
                        "suitable_for_exact_quote": mapped.suitable_for_exact_quote,
                        "deny_reasons": list(mapped.eligibility.get("reasons") or []),
                        "mapping_notes": mapped.mapping_notes,
                    }
                )

    summary["fragments"] = len(fragments_out)
    summary["fragment_details"] = fragments_out
    # Counter → dict
    summary["eligibility"] = dict(summary["eligibility"])
    summary["verification"] = dict(summary["verification"])
    summary["content_types"] = dict(summary["content_types"])
    summary["kinds"] = dict(summary["kinds"])
    return summary, errors, warnings


def run_bank_materials_dry_run(
    *,
    input_dir: Path,
    pdf_dir: Path,
) -> DryRunResult:
    started = datetime.now(timezone.utc)
    input_dir = input_dir.resolve()
    pdf_dir = pdf_dir.resolve()
    errors: list[IssueRecord] = []
    warnings: list[IssueRecord] = []
    documents: list[dict[str, Any]] = []

    if not input_dir.is_dir():
        _add_issue(
            errors,
            severity="error",
            code="input_dir_missing",
            field="input_dir",
            detail=str(input_dir),
        )
    if not pdf_dir.is_dir():
        _add_issue(
            errors,
            severity="error",
            code="pdf_dir_missing",
            field="pdf_dir",
            detail=str(pdf_dir),
        )

    doc_dirs: list[Path] = []
    if input_dir.is_dir():
        doc_dirs = sorted(
            p for p in input_dir.iterdir() if p.is_dir() and (p / "manifest.json").is_file()
        )
        if not doc_dirs:
            _add_issue(
                errors,
                severity="error",
                code="no_documents",
                field="input_dir",
                detail="no subdirectories with manifest.json",
            )

    sha_seen: dict[str, str] = {}
    for doc_dir in doc_dirs:
        summary, doc_errs, doc_warns = validate_document_dir(
            doc_dir, input_dir=input_dir, pdf_dir=pdf_dir
        )
        errors.extend(doc_errs)
        warnings.extend(doc_warns)
        sha = summary.get("source_sha256")
        if sha:
            if sha in sha_seen:
                _add_issue(
                    errors,
                    severity="error",
                    code="duplicate_pdf_sha_in_corpus",
                    document=summary["slug"],
                    field="source_sha256",
                    detail=f"same SHA as {sha_seen[sha]}",
                )
                summary["ok"] = False
            else:
                sha_seen[sha] = summary["slug"]
        documents.append(summary)

    finished = datetime.now(timezone.utc)
    totals = {
        "documents": len(documents),
        "documents_ok": sum(1 for d in documents if d.get("ok")),
        "pages": sum(int(d.get("pages") or 0) for d in documents),
        "fragments": sum(int(d.get("fragments") or 0) for d in documents),
        "eligible_search": sum(
            int((d.get("eligibility") or {}).get("search") or 0) for d in documents
        ),
        "eligible_ai_evidence": sum(
            int((d.get("eligibility") or {}).get("ai_evidence") or 0) for d in documents
        ),
        "eligible_exact_quote": sum(
            int((d.get("eligibility") or {}).get("exact_quote") or 0) for d in documents
        ),
        "verification": dict(
            sum((Counter(d.get("verification") or {}) for d in documents), Counter())
        ),
        "content_types": dict(
            sum((Counter(d.get("content_types") or {}) for d in documents), Counter())
        ),
        "kinds": dict(sum((Counter(d.get("kinds") or {}) for d in documents), Counter())),
    }

    result = DryRunResult(
        ok=len(errors) == 0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        input_dir=str(input_dir),
        pdf_dir=str(pdf_dir),
        documents=documents,
        totals=totals,
        errors=errors,
        warnings=warnings,
        blocking_error_count=len(errors),
        warning_count=len(warnings),
    )
    return result


def write_reports(result: DryRunResult, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = report_dir / f"bank_import_dry_run_{stamp}.json"
    md_path = report_dir / f"bank_import_dry_run_{stamp}.md"
    json_path.write_text(
        json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_markdown_report(result), encoding="utf-8")
    # also write stable latest names for convenience
    (report_dir / "bank_import_dry_run_latest.json").write_text(
        json_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (report_dir / "bank_import_dry_run_latest.md").write_text(
        md_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return json_path, md_path


def _markdown_report(result: DryRunResult) -> str:
    lines = [
        "# Bank materials import dry-run",
        "",
        f"- ok: **{result.ok}**",
        f"- started: {result.started_at}",
        f"- finished: {result.finished_at}",
        f"- input_dir: `{result.input_dir}`",
        f"- pdf_dir: `{result.pdf_dir}`",
        f"- blocking errors: {result.blocking_error_count}",
        f"- warnings: {result.warning_count}",
        "",
        "## Totals",
        "",
        "```json",
        json.dumps(result.totals, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Documents",
        "",
    ]
    for d in result.documents:
        lines.append(
            f"- `{d.get('slug')}` ok={d.get('ok')} pages={d.get('pages')} "
            f"fragments={d.get('fragments')} eligibility={d.get('eligibility')} "
            f"pub={d.get('publication')}"
        )
    lines.extend(["", "## Blocking errors", ""])
    if not result.errors:
        lines.append("_none_")
    for e in result.errors:
        lines.append(
            f"- **{e.code}** doc={e.document} page={e.page} key={e.stable_key} "
            f"field={e.field}: {e.detail}"
        )
    lines.extend(["", "## Warnings", ""])
    if not result.warnings:
        lines.append("_none_")
    for w in result.warnings:
        lines.append(
            f"- **{w.code}** doc={w.document} page={w.page} key={w.stable_key} "
            f"field={w.field}: {w.detail}"
        )
    lines.append("")
    return "\n".join(lines)
