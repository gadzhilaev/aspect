"""Stub: bank corpus не входит в mobile-пакет — всегда integration_not_configured."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.event import Event
from app.schemas.event_bank_evidence import EventBankEvidenceOut


def collect_event_bank_evidence(
    db: Session,
    *,
    event: Event,
    limit: int = 8,
) -> EventBankEvidenceOut:
    del db, limit  # unused in stub
    return EventBankEvidenceOut(
        event_id=event.id,
        status="integration_not_configured",
        event_occurred_at=getattr(event, "occurred_at", None),
        as_of_date=None,
        as_of_date_basis=None,
        query_preview=None,
        evidence=[],
        limitations=[
            "bank_materials_service_not_shipped_in_mobile_package",
            "corpus_data_excluded_from_distribution",
        ],
        empty_reason="Bank materials corpus is not included in this backend package.",
    )


def build_event_search_query(event: Event) -> str:
    return (getattr(event, "title", None) or event.id or "").strip()
