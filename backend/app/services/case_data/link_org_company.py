"""Operator binding: case org (U_*) ↔ existing Company via CaseOrgCompanyLink.

Does not create Company, membership, or rewrite manual Company fields.
Does not activate snapshots or import CSV.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Company, CompanyMembership
from app.models.case_data import CaseOrg, CaseOrgCompanyLink
from app.services.case_data.activate_snapshot import (
    NoActiveSnapshot,
    get_active_snapshot,
)
from app.services.case_data.validate import parse_external_uid


class LinkError(Exception):
    """Base link error."""


class LinkPreconditionError(LinkError):
    pass


class LinkConflictError(LinkError):
    """Existing binding conflicts with the requested (slot, uid, company) triple."""


Outcome = Literal["linked", "already_linked"]


@dataclass(frozen=True, slots=True)
class LinkResult:
    outcome: Outcome
    link_id: str
    slot_key: str
    external_uid: str
    company_id: str
    linked_at: datetime
    linked_by: str | None


def link_case_org_to_company(
    session: Session,
    *,
    slot_key: str,
    external_uid: str,
    company_id: str,
    linked_by: str | None = None,
) -> LinkResult:
    """Bind slot_key + external_uid → existing Company. Idempotent for the same triple.

    Preconditions:
    - Company exists
    - slot has an active snapshot
    - U_ID is present in the active catalog with a profile (not payment-only orphan)
    - no conflicting link under UNIQUE(slot, uid) / UNIQUE(slot, company)

    Does not grant membership. Does not auto-rebind.
    """
    slot = (slot_key or "").strip()
    if not slot:
        raise LinkPreconditionError("slot_key is required")

    uid_parsed = parse_external_uid(external_uid)
    if not uid_parsed.ok:
        raise LinkPreconditionError(
            f"invalid external_uid: {external_uid!r} ({uid_parsed.error})"
        )
    uid = str(uid_parsed.value)

    company = session.get(Company, company_id)
    if company is None:
        raise LinkPreconditionError(f"company {company_id!r} does not exist")

    active = get_active_snapshot(session, slot_key=slot)
    if isinstance(active, NoActiveSnapshot):
        raise LinkPreconditionError(
            f"slot {slot!r} has no active snapshot ({active.reason})"
        )
    snapshot_id = active.snapshot_id

    org = session.scalars(
        select(CaseOrg).where(
            CaseOrg.snapshot_id == snapshot_id,
            CaseOrg.external_uid == uid,
        )
    ).first()
    if org is None:
        raise LinkPreconditionError(
            f"external_uid {uid!r} is absent from active snapshot {snapshot_id}"
        )
    if not org.has_catalog_profile:
        raise LinkPreconditionError(
            f"external_uid {uid!r} is a payment/person orphan without catalog profile "
            f"in snapshot {snapshot_id}; linking is refused"
        )

    by_uid = session.scalars(
        select(CaseOrgCompanyLink).where(
            CaseOrgCompanyLink.slot_key == slot,
            CaseOrgCompanyLink.external_uid == uid,
        )
    ).first()
    by_company = session.scalars(
        select(CaseOrgCompanyLink).where(
            CaseOrgCompanyLink.slot_key == slot,
            CaseOrgCompanyLink.company_id == company_id,
        )
    ).first()

    if by_uid is not None and by_company is not None and by_uid.id == by_company.id:
        # Same triple — idempotent no-op (timestamps unchanged).
        return LinkResult(
            outcome="already_linked",
            link_id=by_uid.id,
            slot_key=slot,
            external_uid=uid,
            company_id=company_id,
            linked_at=by_uid.linked_at,
            linked_by=by_uid.linked_by,
        )

    if by_uid is not None and by_uid.company_id != company_id:
        raise LinkConflictError(
            f"external_uid {uid!r} in slot {slot!r} is already linked to "
            f"company {by_uid.company_id!r}"
        )
    if by_company is not None and by_company.external_uid != uid:
        raise LinkConflictError(
            f"company {company_id!r} in slot {slot!r} is already linked to "
            f"external_uid {by_company.external_uid!r}"
        )

    membership_before = session.scalar(
        select(CompanyMembership.id).where(CompanyMembership.company_id == company_id)
    )

    now = datetime.now(timezone.utc)
    link = CaseOrgCompanyLink(
        id=str(uuid.uuid4()),
        slot_key=slot,
        external_uid=uid,
        company_id=company_id,
        linked_at=now,
        linked_by=(linked_by.strip() if linked_by and linked_by.strip() else None),
    )
    try:
        with session.begin_nested():
            session.add(link)
            session.flush()
    except IntegrityError as exc:
        raise LinkConflictError(
            f"conflicting link for slot={slot!r} uid={uid!r} company={company_id!r}"
        ) from exc

    # Linking must never create membership.
    membership_after = session.scalar(
        select(CompanyMembership.id).where(CompanyMembership.company_id == company_id)
    )
    if membership_before is None and membership_after is not None:
        raise LinkError("link unexpectedly created a membership; aborted")

    return LinkResult(
        outcome="linked",
        link_id=link.id,
        slot_key=slot,
        external_uid=uid,
        company_id=company_id,
        linked_at=link.linked_at,
        linked_by=link.linked_by,
    )


def run_link(
    *,
    database_url: str,
    slot_key: str,
    external_uid: str,
    company_id: str,
    linked_by: str | None = None,
) -> LinkResult:
    """CLI entry: open an explicit database URL, link, commit."""
    if not (database_url or "").strip():
        raise LinkPreconditionError("database_url is required")

    engine = create_engine(database_url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False)
    try:
        with SessionLocal() as session:
            result = link_case_org_to_company(
                session,
                slot_key=slot_key,
                external_uid=external_uid,
                company_id=company_id,
                linked_by=linked_by,
            )
            session.commit()
            return result
    finally:
        engine.dispose()
