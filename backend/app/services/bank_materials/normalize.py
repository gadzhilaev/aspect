"""Normalize OCR corpus artifacts into schema-007-shaped records (no DB writes)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services.bank_materials.eligibility import (
    ALLOWED_REGION_TYPES,
    compute_fragment_eligibility,
)

_DAY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


@dataclass
class NormIssue:
    severity: str  # error | warning
    code: str
    document: str | None
    page: int | None
    stable_key: str | None
    field: str | None
    detail: str


@dataclass
class NormalizedPublication:
    precision: str
    publication_date: date | None
    publication_year: int | None
    publication_month: int | None
    display: str | None
    status: str
    issues: list[NormIssue] = field(default_factory=list)


@dataclass
class NormalizedRegion:
    page_number: int
    sort_order: int
    region_type: str
    bbox_left: int | None
    bbox_top: int | None
    bbox_width: int | None
    bbox_height: int | None
    note: str | None


@dataclass
class NormalizedFragment:
    stable_key: str
    revision: int
    kind: str
    primary_region_type: str
    content_type: str | None
    content_type_status: str
    page_number: int
    ocr_text: str | None
    cleaned_text: str | None
    verified_transcript: str | None
    summary_text: str | None
    verification_status: str
    supersedes_stable_key: str | None
    supersedes_revision: int | None
    regions: list[NormalizedRegion]
    eligibility: dict[str, Any]
    mapping_notes: list[str] = field(default_factory=list)
    missing_trust_fields: list[str] = field(default_factory=list)
    primary_region_type_source: str | None = None
    content_type_status_source: str | None = None
    # Storage vs use: incomplete metadata may still be importable.
    suitable_for_storage: bool = True
    suitable_for_ai_evidence: bool = False
    suitable_for_exact_quote: bool = False
    # Preserved separately from transcripts (never invent or promote).
    ocr_correction_json: dict[str, Any] | None = None
    source_role: str | None = None
    fragment_notes: str | None = None


def parse_publication(
    identity: dict[str, Any],
    *,
    document: str,
) -> NormalizedPublication:
    """Map document_identity publication fields → day/month/unknown shape."""
    issues: list[NormIssue] = []
    status = str(identity.get("confirmed_publication_date_status") or "unknown")
    raw = identity.get("confirmed_publication_date")
    display = identity.get("confirmed_publication_date_display")
    display_s = str(display) if display is not None else None

    if status not in ("confirmed", "unknown"):
        issues.append(
            NormIssue(
                "warning",
                "unknown_publication_status",
                document,
                None,
                None,
                "confirmed_publication_date_status",
                f"unexpected status {status!r}; treating as unknown",
            )
        )
        status = "unknown"

    if status == "unknown" or raw in (None, ""):
        return NormalizedPublication(
            precision="unknown",
            publication_date=None,
            publication_year=None,
            publication_month=None,
            display=display_s,
            status="unknown",
            issues=issues,
        )

    raw_s = str(raw).strip()
    m_day = _DAY_RE.match(raw_s)
    if m_day:
        y, mo, d = int(m_day.group(1)), int(m_day.group(2)), int(m_day.group(3))
        try:
            dt = date(y, mo, d)
        except ValueError:
            issues.append(
                NormIssue(
                    "error",
                    "invalid_publication_date",
                    document,
                    None,
                    None,
                    "confirmed_publication_date",
                    f"invalid calendar date {raw_s!r}",
                )
            )
            return NormalizedPublication(
                precision="unknown",
                publication_date=None,
                publication_year=None,
                publication_month=None,
                display=display_s,
                status=status,
                issues=issues,
            )
        if not (1 <= mo <= 12):
            issues.append(
                NormIssue(
                    "error",
                    "publication_month_out_of_range",
                    document,
                    None,
                    None,
                    "confirmed_publication_date",
                    f"month {mo} not in 1..12",
                )
            )
        return NormalizedPublication(
            precision="day",
            publication_date=dt,
            publication_year=y,
            publication_month=mo,
            display=display_s,
            status=status,
            issues=issues,
        )

    m_month = _MONTH_RE.match(raw_s)
    if m_month:
        y, mo = int(m_month.group(1)), int(m_month.group(2))
        if not (1 <= mo <= 12):
            issues.append(
                NormIssue(
                    "error",
                    "publication_month_out_of_range",
                    document,
                    None,
                    None,
                    "confirmed_publication_date",
                    f"month {mo} not in 1..12",
                )
            )
        return NormalizedPublication(
            precision="month",
            publication_date=None,
            publication_year=y,
            publication_month=mo,
            display=display_s,
            status=status,
            issues=issues,
        )

    issues.append(
        NormIssue(
            "error",
            "unparseable_publication_date",
            document,
            None,
            None,
            "confirmed_publication_date",
            f"expected YYYY-MM-DD or YYYY-MM, got {raw_s!r}",
        )
    )
    return NormalizedPublication(
        precision="unknown",
        publication_date=None,
        publication_year=None,
        publication_month=None,
        display=display_s,
        status=status,
        issues=issues,
    )


def _parse_bbox(
    bbox: Any,
    *,
    document: str,
    stable_key: str,
    page: int,
    page_width: int | None,
    page_height: int | None,
) -> tuple[tuple[int | None, int | None, int | None, int | None], list[NormIssue]]:
    issues: list[NormIssue] = []
    if bbox is None:
        return (None, None, None, None), issues
    if not isinstance(bbox, dict):
        issues.append(
            NormIssue(
                "error",
                "bbox_not_object",
                document,
                page,
                stable_key,
                "regions.bbox",
                f"expected object or null, got {type(bbox).__name__}",
            )
        )
        return (None, None, None, None), issues

    keys = ("left", "top", "width", "height")
    present = [k for k in keys if bbox.get(k) is not None]
    if not present:
        return (None, None, None, None), issues
    if len(present) != 4:
        issues.append(
            NormIssue(
                "error",
                "bbox_partial",
                document,
                page,
                stable_key,
                "regions.bbox",
                f"bbox must be all-or-nothing; present keys={present}",
            )
        )
        return (None, None, None, None), issues

    try:
        left = int(bbox["left"])
        top = int(bbox["top"])
        width = int(bbox["width"])
        height = int(bbox["height"])
    except (TypeError, ValueError):
        issues.append(
            NormIssue(
                "error",
                "bbox_non_integer",
                document,
                page,
                stable_key,
                "regions.bbox",
                "bbox values must be integers",
            )
        )
        return (None, None, None, None), issues

    if left < 0 or top < 0 or width <= 0 or height <= 0:
        issues.append(
            NormIssue(
                "error",
                "bbox_geometry_invalid",
                document,
                page,
                stable_key,
                "regions.bbox",
                f"left/top must be >=0 and width/height >0; got {left},{top},{width},{height}",
            )
        )

    if page_width is not None and page_height is not None:
        if left + width > page_width or top + height > page_height:
            issues.append(
                NormIssue(
                    "error",
                    "bbox_outside_page",
                    document,
                    page,
                    stable_key,
                    "regions.bbox",
                    f"bbox extent ({left}+{width},{top}+{height}) exceeds page "
                    f"{page_width}x{page_height}",
                )
            )

    return (left, top, width, height), issues


def map_fragment(
    raw: dict[str, Any],
    *,
    document: str,
    page_dims: dict[int, tuple[int | None, int | None]],
    known_pages: set[int],
) -> tuple[NormalizedFragment | None, list[NormIssue]]:
    """Map one fragments.json entry → normalized fragment + issues."""
    issues: list[NormIssue] = []
    notes: list[str] = []
    stable_key = raw.get("id") or raw.get("stable_key")
    if not stable_key or not isinstance(stable_key, str):
        issues.append(
            NormIssue(
                "error",
                "fragment_missing_stable_key",
                document,
                None,
                None,
                "id",
                "fragment requires string id/stable_key",
            )
        )
        return None, issues

    page = raw.get("page") if raw.get("page") is not None else raw.get("page_number")
    try:
        page_number = int(page)
    except (TypeError, ValueError):
        issues.append(
            NormIssue(
                "error",
                "fragment_bad_page",
                document,
                None,
                stable_key,
                "page",
                f"invalid page {page!r}",
            )
        )
        return None, issues

    if page_number not in known_pages:
        issues.append(
            NormIssue(
                "error",
                "fragment_page_missing",
                document,
                page_number,
                stable_key,
                "page",
                f"page {page_number} not present in OCR pages",
            )
        )

    revision = raw.get("revision", 1)
    try:
        revision_i = int(revision)
        if revision_i < 1:
            raise ValueError
    except (TypeError, ValueError):
        issues.append(
            NormIssue(
                "error",
                "fragment_bad_revision",
                document,
                page_number,
                stable_key,
                "revision",
                f"revision must be int >= 1, got {revision!r}",
            )
        )
        revision_i = 1

    kind = str(raw.get("kind") or "")
    if kind not in ("exact_quote", "summary"):
        issues.append(
            NormIssue(
                "error",
                "fragment_bad_kind",
                document,
                page_number,
                stable_key,
                "kind",
                f"kind must be exact_quote|summary, got {kind!r}",
            )
        )

    # primary_region_type: never invent prose. Missing → unverified (no AI/quote).
    # Only accept an explicit fragment field, or a uniform explicit regions[].region_type
    # already present on the artifact (deterministic transfer with source note).
    mapping_notes: list[str] = []
    missing_trust_fields: list[str] = []
    primary_source: str | None = None
    primary = raw.get("primary_region_type")
    regions_preview = raw.get("regions") if isinstance(raw.get("regions"), list) else []
    if primary is not None and str(primary).strip() != "":
        primary_s = str(primary)
        primary_source = "fragments[].primary_region_type"
        mapping_notes.append("primary_region_type_explicit")
    else:
        typed = [
            str(r.get("region_type"))
            for r in regions_preview
            if isinstance(r, dict) and r.get("region_type") not in (None, "")
        ]
        if (
            regions_preview
            and len(typed) == len(regions_preview)
            and len(set(typed)) == 1
        ):
            primary_s = typed[0]
            primary_source = "fragments[].regions[].region_type (uniform)"
            mapping_notes.append("primary_region_type_from_uniform_explicit_region_type")
            issues.append(
                NormIssue(
                    "warning",
                    "primary_region_type_from_explicit_region_type",
                    document,
                    page_number,
                    stable_key,
                    "primary_region_type",
                    f"omitted on fragment; transferred {primary_s!r} from uniform "
                    f"regions[].region_type (source={primary_source})",
                )
            )
        else:
            primary_s = "unverified"
            primary_source = None
            missing_trust_fields.append("primary_region_type")
            mapping_notes.append("primary_region_type_absent_unverified")
            issues.append(
                NormIssue(
                    "warning",
                    "primary_region_type_missing_treated_as_unverified",
                    document,
                    page_number,
                    stable_key,
                    "primary_region_type",
                    "artifact omits primary_region_type (and has no uniform explicit "
                    "regions[].region_type); treated as unverified — no AI evidence / "
                    "exact quote. verification_status does not imply region type.",
                )
            )
    if primary_s not in ALLOWED_REGION_TYPES:
        issues.append(
            NormIssue(
                "error",
                "primary_region_type_invalid",
                document,
                page_number,
                stable_key,
                "primary_region_type",
                f"invalid type {primary_s!r}",
            )
        )

    content_type = raw.get("content_type")
    content_type_s = str(content_type) if content_type is not None else None
    cts = raw.get("content_type_status")
    verification = str(raw.get("verification_status") or "unverified")
    content_type_status_source: str | None = None
    # Never promote to confirmed from verification_status alone.
    if cts is None or str(cts).strip() == "":
        content_type_status = "unknown"
        missing_trust_fields.append("content_type_status")
        mapping_notes.append("content_type_status_absent_unknown")
        issues.append(
            NormIssue(
                "warning",
                "content_type_status_missing_treated_as_unknown",
                document,
                page_number,
                stable_key,
                "content_type_status",
                "artifact omits content_type_status; treated as unknown — no AI evidence. "
                "verification_status=verified confirms text review, not fact/forecast/"
                "interpretation classification.",
            )
        )
    else:
        content_type_status = str(cts)
        content_type_status_source = "fragments[].content_type_status"
        mapping_notes.append("content_type_status_explicit")

    # Texts — do not invent quotes
    ocr_text = raw.get("ocr_text")
    ocr_text_s = str(ocr_text) if ocr_text is not None else None
    cleaned = raw.get("cleaned_text")
    cleaned_s = str(cleaned) if cleaned is not None else None
    exact = raw.get("exact_quote")
    verified_transcript = raw.get("verified_transcript")
    if verified_transcript is None and exact is not None:
        verified_transcript = exact
        mapping_notes.append("verified_transcript_from_exact_quote_field")
    transcript_s = str(verified_transcript) if verified_transcript is not None else None
    summary = raw.get("summary")
    if summary is None:
        summary = raw.get("summary_text")
    summary_s = str(summary) if summary is not None else None

    if kind == "summary" and transcript_s and not summary_s:
        issues.append(
            NormIssue(
                "error",
                "summary_marked_with_only_transcript",
                document,
                page_number,
                stable_key,
                "kind",
                "kind=summary but summary text empty while transcript present",
            )
        )
    if kind == "exact_quote" and summary_s and not transcript_s:
        issues.append(
            NormIssue(
                "error",
                "exact_quote_marked_as_summary_text_only",
                document,
                page_number,
                stable_key,
                "kind",
                "kind=exact_quote but verified_transcript/exact_quote empty",
            )
        )

    # Mislabel: summary text stored as exact_quote kind without transcript semantics
    if kind == "exact_quote" and not (transcript_s and transcript_s.strip()) and summary_s:
        issues.append(
            NormIssue(
                "error",
                "summary_mislabeled_as_exact_quote",
                document,
                page_number,
                stable_key,
                "kind",
                "summary text present but kind=exact_quote without transcript",
            )
        )

    regions_raw = raw.get("regions")
    if regions_raw is None:
        regions_raw = []
    if not isinstance(regions_raw, list):
        issues.append(
            NormIssue(
                "error",
                "regions_not_list",
                document,
                page_number,
                stable_key,
                "regions",
                "regions must be a list",
            )
        )
        regions_raw = []

    if verification == "verified" and len(regions_raw) == 0:
        issues.append(
            NormIssue(
                "error",
                "verified_without_regions",
                document,
                page_number,
                stable_key,
                "regions",
                "verified fragment requires at least one region",
            )
        )

    regions: list[NormalizedRegion] = []
    pw, ph = page_dims.get(page_number, (None, None))
    for idx, r in enumerate(regions_raw):
        if not isinstance(r, dict):
            issues.append(
                NormIssue(
                    "error",
                    "region_not_object",
                    document,
                    page_number,
                    stable_key,
                    f"regions[{idx}]",
                    "region must be object",
                )
            )
            continue
        rpage = r.get("page", r.get("page_number", page_number))
        try:
            rpage_i = int(rpage)
        except (TypeError, ValueError):
            issues.append(
                NormIssue(
                    "error",
                    "region_bad_page",
                    document,
                    page_number,
                    stable_key,
                    f"regions[{idx}].page",
                    f"invalid {rpage!r}",
                )
            )
            continue
        if rpage_i not in known_pages:
            issues.append(
                NormIssue(
                    "error",
                    "region_page_missing",
                    document,
                    rpage_i,
                    stable_key,
                    f"regions[{idx}].page",
                    f"page {rpage_i} not in OCR pages",
                )
            )
        # Non-empty regions ≠ verified prose. Missing region_type stays unverified
        # unless primary_region_type was explicit on the fragment.
        if r.get("region_type") not in (None, ""):
            rtype = str(r.get("region_type"))
        elif primary_source == "fragments[].primary_region_type":
            rtype = primary_s
            mapping_notes.append(f"region[{idx}]_type_from_explicit_primary")
        else:
            rtype = "unverified"
            mapping_notes.append(f"region[{idx}]_type_absent_unverified")
        if rtype not in ALLOWED_REGION_TYPES:
            issues.append(
                NormIssue(
                    "error",
                    "region_type_invalid",
                    document,
                    rpage_i,
                    stable_key,
                    f"regions[{idx}].region_type",
                    f"invalid {rtype!r}",
                )
            )
            rtype = "unverified"
        rpw, rph = page_dims.get(rpage_i, (None, None))
        (left, top, width, height), bbox_issues = _parse_bbox(
            r.get("bbox"),
            document=document,
            stable_key=stable_key,
            page=rpage_i,
            page_width=rpw,
            page_height=rph,
        )
        issues.extend(bbox_issues)
        regions.append(
            NormalizedRegion(
                page_number=rpage_i,
                sort_order=int(r.get("sort_order", idx)),
                region_type=str(rtype),
                bbox_left=left,
                bbox_top=top,
                bbox_width=width,
                bbox_height=height,
                note=str(r["note"]) if r.get("note") is not None else None,
            )
        )

    # Blocked region types must not be claimed as verified prose eligibility input
    if primary_s in ("table", "chart", "contacts_disclaimer", "mixed") and verification == "verified":
        issues.append(
            NormIssue(
                "warning",
                "verified_non_prose_primary_region",
                document,
                page_number,
                stable_key,
                "primary_region_type",
                f"primary_region_type={primary_s} cannot be analytic verified prose",
            )
        )

    elig = compute_fragment_eligibility(
        verification_status=verification,
        kind=kind if kind in ("exact_quote", "summary") else "exact_quote",
        primary_region_type=primary_s if primary_s in ALLOWED_REGION_TYPES else "unverified",
        content_type=content_type_s,
        content_type_status=content_type_status,
        verified_transcript=transcript_s,
        summary_text=summary_s,
        region_count=len(regions),
    )

    supersedes_id = raw.get("supersedes_fragment_id") or raw.get("supersedes_stable_key")
    supersedes_rev = raw.get("supersedes_revision")
    if supersedes_id is not None and not isinstance(supersedes_id, str):
        issues.append(
            NormIssue(
                "error",
                "bad_supersedes_ref",
                document,
                page_number,
                stable_key,
                "supersedes_fragment_id",
                "supersedes reference must be string stable_key/id when present",
            )
        )
        supersedes_id = None

    ocr_corr = raw.get("ocr_correction") or raw.get("ocr_correction_json")
    ocr_corr_json: dict[str, Any] | None = None
    if isinstance(ocr_corr, dict):
        ocr_corr_json = dict(ocr_corr)
    elif ocr_corr is not None:
        issues.append(
            NormIssue(
                "warning",
                "ocr_correction_not_object",
                document,
                page_number,
                stable_key,
                "ocr_correction",
                "ocr_correction ignored (expected object)",
            )
        )

    source_role_raw = raw.get("source_role")
    source_role_s = str(source_role_raw) if source_role_raw is not None else None
    frag_notes_raw = raw.get("notes")
    frag_notes_s = str(frag_notes_raw) if frag_notes_raw is not None else None

    # Blocking normalize errors still allow reporting; storage suitability excludes
    # structural errors (missing key/page already returned earlier). Incomplete trust
    # metadata does not block storage.
    has_blocking = any(i.severity == "error" for i in issues)
    frag = NormalizedFragment(
        stable_key=stable_key,
        revision=revision_i,
        kind=kind,
        primary_region_type=primary_s if primary_s in ALLOWED_REGION_TYPES else "unverified",
        content_type=content_type_s,
        content_type_status=content_type_status,
        page_number=page_number,
        ocr_text=ocr_text_s,
        cleaned_text=cleaned_s,
        verified_transcript=transcript_s,
        summary_text=summary_s,
        verification_status=verification,
        supersedes_stable_key=str(supersedes_id) if supersedes_id else None,
        supersedes_revision=int(supersedes_rev) if supersedes_rev is not None else None,
        regions=regions,
        eligibility={
            "eligible_search": elig.eligible_search,
            "eligible_ai_evidence": elig.eligible_ai_evidence,
            "eligible_exact_quote": elig.eligible_exact_quote,
            "evidence_as_summary_only": elig.evidence_as_summary_only,
            "reasons": list(elig.reasons),
            "insufficient_verification_for_evidence": not elig.eligible_ai_evidence,
        },
        mapping_notes=mapping_notes + notes,
        missing_trust_fields=list(missing_trust_fields),
        primary_region_type_source=primary_source,
        content_type_status_source=content_type_status_source,
        suitable_for_storage=not has_blocking,
        suitable_for_ai_evidence=elig.eligible_ai_evidence,
        suitable_for_exact_quote=elig.eligible_exact_quote,
        ocr_correction_json=ocr_corr_json,
        source_role=source_role_s,
        fragment_notes=frag_notes_s,
    )
    return frag, issues
