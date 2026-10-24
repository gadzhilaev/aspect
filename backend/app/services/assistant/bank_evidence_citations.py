"""Server-side validation of bank evidence citations from the model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CitationReject:
    fragment_id: str | None
    reason: str


@dataclass
class ValidatedCitation:
    fragment_id: str
    revision: int
    text_kind: str
    text: str
    content_type: str | None
    document_title: str | None
    publication_date: str | None
    publication_date_precision: str | None
    page_number: int | None
    source_role: str | None
    qa_method: str | None
    document_href: str | None
    fragment_href: str | None
    content_href: str | None
    section_hint: str | None = None


@dataclass
class CitationValidationResult:
    validated: list[ValidatedCitation] = field(default_factory=list)
    rejected: list[CitationReject] = field(default_factory=list)
    cited_by_model: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejected


def _norm_quote(text: str) -> str:
    return " ".join((text or "").split())


def validate_bank_evidence_citations(
    raw_citations: list[Any] | None,
    *,
    passed_index: dict[str, dict[str, Any]],
) -> CitationValidationResult:
    """Accept only IDs/versions that were actually passed; server fills metadata.

    Validating an ID proves provenance of the link, not that the source supports
    every model claim.
    """
    result = CitationValidationResult()
    if not raw_citations:
        return result

    seen: set[str] = set()
    for item in raw_citations:
        if not isinstance(item, dict):
            result.rejected.append(CitationReject(None, "citation_not_object"))
            continue
        fid = item.get("fragment_id")
        if not isinstance(fid, str) or not fid.strip():
            result.rejected.append(CitationReject(None, "missing_fragment_id"))
            continue
        fid = fid.strip()
        result.cited_by_model.append(fid)
        if fid in seen:
            result.rejected.append(CitationReject(fid, "duplicate_citation"))
            continue
        seen.add(fid)

        passed = passed_index.get(fid)
        if passed is None:
            result.rejected.append(CitationReject(fid, "unknown_or_not_passed_fragment_id"))
            continue

        expected_rev = int(passed.get("revision") or 0)
        raw_rev = item.get("revision")
        if raw_rev is not None:
            try:
                if int(raw_rev) != expected_rev:
                    result.rejected.append(CitationReject(fid, "revision_mismatch"))
                    continue
            except (TypeError, ValueError):
                result.rejected.append(CitationReject(fid, "revision_invalid"))
                continue

        text_kind = str(passed.get("text_kind") or "")
        plain = str(passed.get("text_plain_for_validation") or "").strip()
        claimed_kind = item.get("text_kind")
        if claimed_kind is not None and str(claimed_kind) != text_kind:
            result.rejected.append(CitationReject(fid, "text_kind_mismatch"))
            continue

        quoted = item.get("quoted_text") or item.get("exact_quote")
        if quoted is not None:
            if text_kind != "exact_quote":
                result.rejected.append(
                    CitationReject(fid, "exact_quote_not_allowed_for_summary")
                )
                continue
            if _norm_quote(str(quoted)) != _norm_quote(plain):
                result.rejected.append(CitationReject(fid, "exact_quote_text_mismatch"))
                continue

        section = item.get("section_hint")
        result.validated.append(
            ValidatedCitation(
                fragment_id=fid,
                revision=expected_rev,
                text_kind=text_kind,
                text=plain,
                content_type=passed.get("content_type"),
                document_title=passed.get("document_title"),
                publication_date=passed.get("publication_date"),
                publication_date_precision=passed.get("publication_date_precision"),
                page_number=passed.get("page_number"),
                source_role=passed.get("source_role"),
                qa_method=passed.get("qa_method"),
                document_href=passed.get("document_href"),
                fragment_href=passed.get("fragment_href"),
                content_href=passed.get("content_href"),
                section_hint=str(section) if section else None,
            )
        )
    return result


def validated_to_public_dicts(items: list[ValidatedCitation]) -> list[dict[str, Any]]:
    """Snapshot for message history — pinned revision, no storage paths."""
    out: list[dict[str, Any]] = []
    for v in items:
        out.append(
            {
                "fragment_id": v.fragment_id,
                "revision": v.revision,
                "text_kind": v.text_kind,
                "text": v.text,
                "content_type": v.content_type,
                "document_title": v.document_title,
                "publication_date": v.publication_date,
                "publication_date_precision": v.publication_date_precision,
                "page_number": v.page_number,
                "source_role": v.source_role,
                "qa_method": v.qa_method,
                "document_href": v.document_href,
                "fragment_href": v.fragment_href,
                "content_href": v.content_href,
                "section_hint": v.section_hint,
            }
        )
    return out
