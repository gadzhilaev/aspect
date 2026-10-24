"""Select fragment revisions for evidence (no search/API)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.bank_materials import BankFragment, BankFragmentRegion
from app.services.bank_materials.eligibility import (
    FragmentEligibility,
    compute_fragment_eligibility,
)


@dataclass(frozen=True)
class SelectedFragment:
    fragment: BankFragment
    region_count: int
    eligibility: FragmentEligibility
    """True when this is the latest revision for (ocr_run_id, stable_key)."""
    is_latest: bool


def get_fragment_by_id(session: Session, fragment_id: str) -> BankFragment | None:
    """Historical lookup by primary key (any revision)."""
    return session.get(BankFragment, fragment_id)


def get_latest_fragment(
    session: Session,
    *,
    ocr_run_id: str,
    stable_key: str,
) -> BankFragment | None:
    """Return the highest revision for (ocr_run_id, stable_key), or None."""
    return session.scalar(
        select(BankFragment)
        .where(
            BankFragment.ocr_run_id == ocr_run_id,
            BankFragment.stable_key == stable_key,
        )
        .order_by(BankFragment.revision.desc())
        .limit(1)
    )


def _region_count(session: Session, fragment_id: str) -> int:
    n = session.scalar(
        select(func.count())
        .select_from(BankFragmentRegion)
        .where(BankFragmentRegion.fragment_id == fragment_id)
    )
    return int(n or 0)


def select_latest_with_eligibility(
    session: Session,
    *,
    ocr_run_id: str,
    stable_key: str,
) -> SelectedFragment | None:
    """Pick latest revision first, then compute eligibility.

    If the latest revision is not AI-eligible, callers must **not** fall back
    to an older eligible revision. Use ``get_fragment_by_id`` for history only.
    """
    frag = get_latest_fragment(session, ocr_run_id=ocr_run_id, stable_key=stable_key)
    if frag is None:
        return None
    region_count_i = _region_count(session, frag.id)
    elig = compute_fragment_eligibility(
        verification_status=frag.verification_status,
        kind=frag.kind,
        primary_region_type=frag.primary_region_type,
        content_type=frag.content_type,
        content_type_status=frag.content_type_status,
        verified_transcript=frag.verified_transcript,
        summary_text=frag.summary_text,
        region_count=region_count_i,
    )
    return SelectedFragment(
        fragment=frag,
        region_count=region_count_i,
        eligibility=elig,
        is_latest=True,
    )


def list_latest_fragments_for_run(
    session: Session,
    *,
    ocr_run_id: str,
) -> list[SelectedFragment]:
    """All logical fragments in a run, each at its latest revision only."""
    frags = session.scalars(
        select(BankFragment).where(BankFragment.ocr_run_id == ocr_run_id)
    ).all()
    by_key: dict[str, BankFragment] = {}
    for f in frags:
        cur = by_key.get(f.stable_key)
        if cur is None or f.revision > cur.revision:
            by_key[f.stable_key] = f
    out: list[SelectedFragment] = []
    for f in sorted(by_key.values(), key=lambda x: x.stable_key):
        region_count_i = _region_count(session, f.id)
        elig = compute_fragment_eligibility(
            verification_status=f.verification_status,
            kind=f.kind,
            primary_region_type=f.primary_region_type,
            content_type=f.content_type,
            content_type_status=f.content_type_status,
            verified_transcript=f.verified_transcript,
            summary_text=f.summary_text,
            region_count=region_count_i,
        )
        out.append(
            SelectedFragment(
                fragment=f,
                region_count=region_count_i,
                eligibility=elig,
                is_latest=True,
            )
        )
    return out
