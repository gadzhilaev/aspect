"""Bank evidence for a concrete Event (read-only, evidence mode only).

Uses retrieve_bank_fragments with server OCR-run scope and as_of = event news date.
Does not generate answers, create links, or change impact/scores.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.event import Event
from app.schemas.event_bank_evidence import (
    EventBankEvidenceItemOut,
    EventBankEvidenceOut,
    EventBankEvidenceStatus,
)
from app.services.bank_materials.access import scope_from_settings
from app.services.bank_materials.retrieval import (
    MAX_QUERY_CHARS,
    FragmentHit,
    retrieve_bank_fragments,
)

DEFAULT_EVIDENCE_LIMIT = 10
# Cap query built from event fields (below retrieval MAX_QUERY_CHARS).
MAX_EVENT_QUERY_CHARS = 1200
MAX_SUMMARY_CHARS = 500

_BASE_LIMITATIONS: tuple[str, ...] = (
    "mode_evidence_only",
    "server_ocr_run_scope",
    "latest_revision_then_eligibility",
    "no_fallback_to_unverified_or_superseded",
    "as_of_materials_published_by_event_occurred_at",
    "thematic_match_is_not_bank_commentary_on_this_news",
    "lexical_match_score_is_not_confidence_or_data_quality",
    "no_llm",
    "read_only_no_impact_or_chat_side_effects",
)


def resolve_event_as_of_date(event: Event) -> tuple[date | None, str | None]:
    """Calendar date for temporal gate: materials published by the news date.

    Field: ``Event.occurred_at`` — when the news/event occurred (also used for public
    news ordering). Not ``created_at`` (import time) and not wall-clock \"today\".
    ``effective_from`` is a separate optional policy window and is not used here.
    """
    occurred = getattr(event, "occurred_at", None)
    if occurred is None:
        return None, None
    if not isinstance(occurred, datetime):
        return None, None
    # Normalize to UTC calendar day when aware; naive treated as already calendar-local.
    if occurred.tzinfo is not None:
        day = occurred.astimezone(timezone.utc).date()
    else:
        day = occurred.date()
    return day, "event.occurred_at"


def _flatten_match_list(raw: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if len(out) >= limit:
            break
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            for key in ("label", "name", "code", "value"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    out.append(val.strip())
                    break
    return out


_SYNTHETIC_BRACKET_RE = re.compile(
    r"\[\s*синтетическ[^\]]*\]",
    re.IGNORECASE,
)


def _strip_synthetic_markers(text: str) -> str:
    """Remove demo bracket tags so they do not leak into lexical bank search."""
    cleaned = _SYNTHETIC_BRACKET_RE.sub(" ", text or "")
    return " ".join(cleaned.split()).strip()


def build_event_search_query(event: Event, *, max_chars: int = MAX_EVENT_QUERY_CHARS) -> str:
    """Build a bounded lexical query from title, summary, and thematic match fields.

    Does not dump ``attributes_json`` wholesale or any raw ingestion payload.
    """
    parts: list[str] = []
    title = _strip_synthetic_markers((event.title or "").strip())
    if title:
        parts.append(title)

    summary = _strip_synthetic_markers((event.summary or "").strip())
    if summary:
        if len(summary) > MAX_SUMMARY_CHARS:
            summary = summary[: MAX_SUMMARY_CHARS - 1].rstrip() + "…"
        parts.append(summary)

    for label, value in (
        ("category", event.category),
        ("type", event.event_type),
    ):
        v = (value or "").strip()
        if v:
            parts.append(v)

    for field_name in (
        "match_categories_json",
        "match_countries_json",
        "match_currencies_json",
        "match_materials_json",
    ):
        tokens = _flatten_match_list(getattr(event, field_name, None))
        if tokens:
            parts.append(" ".join(tokens))

    query = "\n".join(parts)
    query = " ".join(query.split())
    if len(query) > max_chars:
        query = query[: max_chars - 1].rstrip() + "…"
    if len(query) > MAX_QUERY_CHARS:
        query = query[: MAX_QUERY_CHARS - 1].rstrip() + "…"
    return query


def _href_document(document_id: str) -> str:
    return f"/api/v1/bank-materials/documents/{document_id}"


def _href_fragment(fragment_id: str) -> str:
    return f"/api/v1/bank-materials/fragments/{fragment_id}"


def _href_content(file_id: str) -> str:
    return f"/api/v1/bank-materials/files/{file_id}/content"


def _item_from_hit(hit: FragmentHit) -> EventBankEvidenceItemOut | None:
    if hit.text_kind not in ("exact_quote", "summary"):
        return None
    if hit.insufficient_verification or not hit.eligible_ai_evidence:
        return None
    text = (hit.text or "").strip()
    if not text:
        return None
    return EventBankEvidenceItemOut(
        document_id=hit.document_id,
        document_file_id=hit.document_file_id,
        ocr_run_id=hit.ocr_run_id,
        fragment_id=hit.fragment_id,
        stable_key=hit.stable_key,
        revision=hit.revision,
        document_title=hit.document_title,
        document_slug=hit.document_slug,
        publication_date=hit.publication_date,
        publication_year=hit.publication_year,
        publication_month=hit.publication_month,
        publication_date_precision=hit.publication_date_precision,
        publication_date_display=hit.publication_date_display,
        page_number=hit.page_number,
        text_kind=hit.text_kind,  # type: ignore[arg-type]
        text=text,
        content_type=hit.content_type,
        content_type_status=hit.content_type_status,
        source_role=hit.source_role,
        source_role_meaning=hit.source_role_meaning,
        qa_method=hit.qa_method,
        match_reasons=list(hit.match_reasons),
        lexical_match_score=hit.relevance_score,
        date_gate_reasons=list(hit.date_gate_reasons),
        document_href=_href_document(hit.document_id),
        fragment_href=_href_fragment(hit.fragment_id),
        content_href=_href_content(hit.document_file_id),
    )


def collect_event_bank_evidence(
    session: Session,
    *,
    event: Event,
    limit: int = DEFAULT_EVIDENCE_LIMIT,
    settings: Settings | None = None,
) -> EventBankEvidenceOut:
    """Return typed bank evidence for ``event`` (caller loads Event; no writes)."""
    s = settings or get_settings()
    scope = scope_from_settings(s)
    limitations = list(_BASE_LIMITATIONS)

    if not scope.configured:
        return EventBankEvidenceOut(
            event_id=event.id,
            status="integration_not_configured",
            event_occurred_at=event.occurred_at,
            as_of_date=None,
            as_of_date_basis=None,
            query_preview=None,
            evidence=[],
            limitations=limitations + ["bank_materials_allowed_ocr_run_ids_empty"],
            empty_reason="integration_not_configured",
        )

    as_of, basis = resolve_event_as_of_date(event)
    if as_of is None or basis is None:
        return EventBankEvidenceOut(
            event_id=event.id,
            status="event_date_unavailable",
            event_occurred_at=getattr(event, "occurred_at", None),
            as_of_date=None,
            as_of_date_basis=None,
            query_preview=None,
            evidence=[],
            limitations=limitations + ["event_occurred_at_missing_or_unusable"],
            empty_reason="event_date_unavailable",
        )

    query = build_event_search_query(event)
    run_ids = sorted(scope.allowed_ocr_run_ids)  # stable order
    result = retrieve_bank_fragments(
        session,
        query=query,
        ocr_run_ids=run_ids,
        mode="evidence",
        limit=limit,
        as_of_date=as_of,
    )

    items: list[EventBankEvidenceItemOut] = []
    for hit in result.hits:
        item = _item_from_hit(hit)
        if item is not None:
            items.append(item)

    status: EventBankEvidenceStatus
    empty_reason: str | None
    if items:
        status = "available"
        empty_reason = None
    else:
        status = "no_matching_evidence"
        empty_reason = result.empty_reason or "no_matching_fragments_in_scope"

    return EventBankEvidenceOut(
        event_id=event.id,
        status=status,
        event_occurred_at=event.occurred_at,
        as_of_date=as_of,
        as_of_date_basis=basis,
        query_preview=query[:240] + ("…" if len(query) > 240 else ""),
        evidence=items,
        limitations=limitations,
        empty_reason=empty_reason,
    )
