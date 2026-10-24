"""Persist / consume external lookup results for server-trusted confirmation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CompanyRegistryLookup
from app.services.company_registry.provider import LookupOutcome


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def create_lookup(db: Session, *, user_id: str, inn: str, outcome: LookupOutcome) -> CompanyRegistryLookup:
    """Store the normalized candidates for later confirmation. Caller commits."""
    settings = get_settings()
    raw_ttl = getattr(settings, "company_registry_lookup_ttl_seconds", 900)
    ttl = int(raw_ttl) if raw_ttl is not None else 900
    now = datetime.now(timezone.utc)
    retrieved = (
        datetime.fromtimestamp(outcome.retrieved_at, tz=timezone.utc)
        if outcome.retrieved_at
        else now
    )
    row = CompanyRegistryLookup(
        id=str(uuid4()),
        user_id=user_id,
        inn=inn,
        candidates_json=[c.to_public_dict() for c in outcome.candidates],
        source_actuality_date=outcome.source_actuality_date,
        retrieved_at=retrieved,
        expires_at=now + timedelta(seconds=ttl),
    )
    db.add(row)
    db.flush()
    return row


def get_candidate(
    db: Session, *, user_id: str, lookup_id: str, candidate_id: str
) -> tuple[dict[str, Any] | None, str]:
    """Return (candidate_dict, reason).

    reason is one of: ok | lookup_not_found | lookup_expired | candidate_not_found.
    A lookup owned by another user is reported as lookup_not_found (no leakage).
    """
    row = db.get(CompanyRegistryLookup, lookup_id)
    if row is None or row.user_id != user_id:
        return None, "lookup_not_found"
    if _aware(row.expires_at) < datetime.now(timezone.utc):
        return None, "lookup_expired"
    for cand in row.candidates_json or []:
        if isinstance(cand, dict) and str(cand.get("candidate_id")) == str(candidate_id):
            return cand, "ok"
    return None, "candidate_not_found"
