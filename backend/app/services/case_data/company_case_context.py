"""Read-only case context for a Company linked in a competition slot.

Callers pass an explicit server-chosen ``slot_key``. Product endpoints are not
wired yet. Never writes. Never returns other companies' profiles via group,
payments, or person links.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, CompanyMembership, User
from app.models.case_data import (
    CaseOrg,
    CaseOrgCatalogRow,
    CaseOrgCompanyLink,
    CaseOrgFieldResolution,
    CaseOrgGroup,
    CaseOrgGroupMember,
)
from app.services.case_data.activate_snapshot import (
    ActiveSnapshotRef,
    NoActiveSnapshot,
    get_active_snapshot,
)
from app.services.case_data.resolution import PRODUCT_CODES

ContextStatus = Literal[
    "not_linked",
    "no_active_snapshot",
    "uid_missing_in_snapshot",
    "profile_absent",
    "profile_available",
]

FieldStatus = Literal["confirmed", "conflict", "absent"]
ProductStatus = Literal["true", "false", "unknown", "conflict"]
BoolTriStatus = Literal["true", "false", "unknown", "conflict"]


class CaseContextError(Exception):
    """Base case-context error."""


class CaseContextAccessError(CaseContextError):
    """User is not a member of the company."""


@dataclass(frozen=True, slots=True)
class ManualCompanySlice:
    """Manual twin fields kept separate from case data (never overwritten here)."""

    company_id: str
    name: str
    industry: str | None
    size_band: str | None
    hq_region: str | None
    profile_status: str


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    snapshot_id: str
    source_file: str | None
    source_row_numbers: tuple[int, ...]
    catalog_row_ids: tuple[str, ...]
    variant_count: int


@dataclass(frozen=True, slots=True)
class ResolvedCaseField:
    key: str
    status: FieldStatus
    value: Any | None
    detail: dict[str, Any] | None
    provenance: FieldProvenance | None


@dataclass(frozen=True, slots=True)
class ProductMarkView:
    code: str
    status: ProductStatus


@dataclass(frozen=True, slots=True)
class FactoringView:
    status: BoolTriStatus


@dataclass(frozen=True, slots=True)
class RevenueView:
    """Revenue from case; units unknown — never treat as rubles or size band."""

    status: FieldStatus
    revenue_raw: str | None
    amount: str | None  # raw numeric string when confirmed; not rubles
    unit: str | None  # always None until organisers confirm
    currency: str | None
    limitations: tuple[str, ...]
    provenance: FieldProvenance | None


@dataclass(frozen=True, slots=True)
class LinkInfo:
    id: str
    slot_key: str
    external_uid: str
    company_id: str
    linked_at: datetime
    linked_by: str | None


@dataclass(frozen=True, slots=True)
class GroupView:
    status: FieldStatus
    external_group_id: str | None
    is_conflicted: bool
    detail: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class FtsCountriesView:
    """Raw FTS country string(s); no invented trade direction."""

    status: FieldStatus
    countries_raw: tuple[str, ...]
    note: str
    detail: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class CaseOrgProfileView:
    external_uid: str
    case_org_id: str
    snapshot_id: str
    profile_resolution: str
    industry: ResolvedCaseField  # okved code + name packed
    okved_code: ResolvedCaseField
    okved_name: ResolvedCaseField
    city: ResolvedCaseField
    region: ResolvedCaseField
    workers_fns: ResolvedCaseField
    workers_spark: ResolvedCaseField
    company_age: ResolvedCaseField
    products: tuple[ProductMarkView, ...]
    factoring: FactoringView
    fts_countries: FtsCountriesView
    group: GroupView
    revenue: RevenueView
    conflicts: dict[str, Any]
    absent: dict[str, Any]
    provenance: FieldProvenance


@dataclass(frozen=True, slots=True)
class CaseCompanyContext:
    status: ContextStatus
    slot_key: str
    company_id: str
    user_id: str
    reason: str
    manual: ManualCompanySlice
    link: LinkInfo | None = None
    active_snapshot: ActiveSnapshotRef | None = None
    profile: CaseOrgProfileView | None = None
    # Explicit empty marker when UID gone from new snapshot — do not backfill A.
    missing_external_uid: str | None = None
    read_only: bool = True


def _link_info(link: CaseOrgCompanyLink) -> LinkInfo:
    return LinkInfo(
        id=link.id,
        slot_key=link.slot_key,
        external_uid=link.external_uid,
        company_id=link.company_id,
        linked_at=link.linked_at,
        linked_by=link.linked_by,
    )


def _require_membership(session: Session, *, user_id: str, company_id: str) -> None:
    row = session.scalars(
        select(CompanyMembership).where(
            CompanyMembership.user_id == user_id,
            CompanyMembership.company_id == company_id,
        )
    ).first()
    if row is None:
        raise CaseContextAccessError(
            f"user {user_id!r} is not a member of company {company_id!r}"
        )


def _manual_slice(company: Company) -> ManualCompanySlice:
    return ManualCompanySlice(
        company_id=company.id,
        name=company.name,
        industry=company.industry,
        size_band=company.size_band,
        hq_region=company.hq_region,
        profile_status=company.profile_status,
    )


def _catalog_provenance(
    snapshot_id: str,
    rows: list[CaseOrgCatalogRow],
    *,
    variant_count: int | None = None,
) -> FieldProvenance:
    files = sorted({r.source_file for r in rows})
    source_file = files[0] if len(files) == 1 else (None if not files else ",".join(files))
    return FieldProvenance(
        snapshot_id=snapshot_id,
        source_file=source_file if len(files) <= 1 else ",".join(files),
        source_row_numbers=tuple(sorted(r.source_row_number for r in rows)),
        catalog_row_ids=tuple(r.id for r in rows),
        variant_count=variant_count if variant_count is not None else len(rows),
    )


def _field_from_resolution(
    key: str,
    consensus: dict[str, Any],
    conflict: dict[str, Any],
    absent: dict[str, Any],
    provenance: FieldProvenance | None,
) -> ResolvedCaseField:
    if key in conflict:
        return ResolvedCaseField(
            key=key,
            status="conflict",
            value=None,
            detail=conflict.get(key) if isinstance(conflict.get(key), dict) else {"raw": conflict.get(key)},
            provenance=provenance,
        )
    if key in consensus:
        return ResolvedCaseField(
            key=key,
            status="confirmed",
            value=consensus[key],
            detail=None,
            provenance=provenance,
        )
    detail = absent.get(key) if key in absent else {"reason": "not_in_resolution"}
    return ResolvedCaseField(
        key=key,
        status="absent",
        value=None,
        detail=detail if isinstance(detail, dict) else {"raw": detail},
        provenance=provenance,
    )


def _product_status(
    code: str,
    consensus: dict[str, Any],
    conflict: dict[str, Any],
    absent: dict[str, Any],
) -> ProductStatus:
    products_conflict = conflict.get("products") if isinstance(conflict.get("products"), dict) else {}
    products_absent = absent.get("products") if isinstance(absent.get("products"), dict) else {}
    products_consensus = consensus.get("products") if isinstance(consensus.get("products"), dict) else {}

    if code in products_conflict:
        return "conflict"
    if code in products_consensus:
        val = products_consensus[code]
        if val is True:
            return "true"
        if val is False:
            return "false"
        return "unknown"
    if code in products_absent:
        return "unknown"
    return "unknown"


def _bool_tri(
    key: str,
    consensus: dict[str, Any],
    conflict: dict[str, Any],
    absent: dict[str, Any],
) -> BoolTriStatus:
    if key in conflict:
        return "conflict"
    if key in consensus:
        val = consensus[key]
        if val is True:
            return "true"
        if val is False:
            return "false"
        return "unknown"
    return "unknown"


def _split_fts_raw(raw: str) -> tuple[str, ...]:
    # Keep raw tokens; do not invent import/export direction.
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    return tuple(p for p in parts if p)


def _build_profile(
    session: Session,
    *,
    snapshot_id: str,
    org: CaseOrg,
) -> CaseOrgProfileView:
    resolution = session.scalars(
        select(CaseOrgFieldResolution).where(
            CaseOrgFieldResolution.snapshot_id == snapshot_id,
            CaseOrgFieldResolution.case_org_id == org.id,
        )
    ).first()
    rows = list(
        session.scalars(
            select(CaseOrgCatalogRow)
            .where(
                CaseOrgCatalogRow.snapshot_id == snapshot_id,
                CaseOrgCatalogRow.case_org_id == org.id,
            )
            .order_by(CaseOrgCatalogRow.source_row_number)
        ).all()
    )
    provenance = _catalog_provenance(
        snapshot_id,
        rows,
        variant_count=resolution.variant_count if resolution else len(rows),
    )

    consensus: dict[str, Any] = dict(resolution.consensus_json) if resolution else {}
    conflict: dict[str, Any] = dict(resolution.conflict_json) if resolution else {}
    absent: dict[str, Any] = dict(resolution.absent_json) if resolution else {}
    # Never expose raw_json blobs from catalog rows.
    if "raw_json" in consensus:
        consensus = {k: v for k, v in consensus.items() if k != "raw_json"}

    okved_code = _field_from_resolution(
        "mainokved_code", consensus, conflict, absent, provenance
    )
    okved_name = _field_from_resolution(
        "mainokved_name", consensus, conflict, absent, provenance
    )
    # Combined industry view: only confirmed pieces; conflicts stay unconfirmed.
    industry_value: dict[str, Any] | None = None
    industry_status: FieldStatus = "absent"
    industry_detail: dict[str, Any] | None = None
    if okved_code.status == "conflict" or okved_name.status == "conflict":
        industry_status = "conflict"
        industry_detail = {
            "mainokved_code": okved_code.detail,
            "mainokved_name": okved_name.detail,
        }
    elif okved_code.status == "confirmed" or okved_name.status == "confirmed":
        industry_status = "confirmed"
        industry_value = {}
        if okved_code.status == "confirmed":
            industry_value["code"] = okved_code.value
        if okved_name.status == "confirmed":
            industry_value["name"] = okved_name.value
        if okved_code.status == "absent":
            industry_detail = {"mainokved_code": "absent"}
        if okved_name.status == "absent":
            industry_detail = {**(industry_detail or {}), "mainokved_name": "absent"}
    else:
        industry_status = "absent"
        industry_detail = {"reason": "okved_absent"}

    industry = ResolvedCaseField(
        key="industry",
        status=industry_status,
        value=industry_value,
        detail=industry_detail,
        provenance=provenance,
    )

    products = tuple(
        ProductMarkView(code=code, status=_product_status(code, consensus, conflict, absent))
        for code in PRODUCT_CODES
    )
    factoring = FactoringView(
        status=_bool_tri("factoring_mark", consensus, conflict, absent)
    )

    fts_field = _field_from_resolution(
        "fts_country_name_raw", consensus, conflict, absent, provenance
    )
    if fts_field.status == "confirmed" and isinstance(fts_field.value, str):
        countries = _split_fts_raw(fts_field.value)
    else:
        countries = ()
    fts = FtsCountriesView(
        status=fts_field.status,
        countries_raw=countries,
        note="raw_fts_country_only_no_trade_direction",
        detail=fts_field.detail,
    )

    group_field = _field_from_resolution(
        "group_external_id", consensus, conflict, absent, provenance
    )
    group_conflicted = group_field.status == "conflict"
    if group_field.status == "confirmed" and group_field.value:
        # Confirm group row exists in this snapshot; do not list other members.
        grp = session.scalars(
            select(CaseOrgGroup).where(
                CaseOrgGroup.snapshot_id == snapshot_id,
                CaseOrgGroup.external_group_id == str(group_field.value),
            )
        ).first()
        member_self = None
        if grp is not None:
            member_self = session.scalars(
                select(CaseOrgGroupMember).where(
                    CaseOrgGroupMember.snapshot_id == snapshot_id,
                    CaseOrgGroupMember.group_id == grp.id,
                    CaseOrgGroupMember.case_org_id == org.id,
                )
            ).first()
            if member_self is not None and member_self.is_conflicted_membership:
                group_conflicted = True
        group = GroupView(
            status="conflict" if group_conflicted else "confirmed",
            external_group_id=str(group_field.value),
            is_conflicted=group_conflicted,
            detail=None if not group_conflicted else {"reason": "conflicted_membership"},
        )
    elif group_field.status == "conflict":
        group = GroupView(
            status="conflict",
            external_group_id=None,
            is_conflicted=True,
            detail=group_field.detail,
        )
    else:
        group = GroupView(
            status="absent",
            external_group_id=None,
            is_conflicted=False,
            detail=group_field.detail,
        )

    rev_field = _field_from_resolution("revenue_raw", consensus, conflict, absent, provenance)
    limitations = (
        "revenue_unit_unknown",
        "do_not_treat_as_rub",
        "do_not_infer_size_band_from_revenue",
    )
    revenue = RevenueView(
        status=rev_field.status,
        revenue_raw=str(rev_field.value) if rev_field.status == "confirmed" else None,
        amount=str(rev_field.value) if rev_field.status == "confirmed" else None,
        unit=None,
        currency=None,
        limitations=limitations,
        provenance=provenance,
    )

    # Public conflicts/absent without nested products duplication handled above.
    public_conflicts = {k: v for k, v in conflict.items() if k != "raw_json"}
    public_absent = {k: v for k, v in absent.items() if k != "raw_json"}

    return CaseOrgProfileView(
        external_uid=org.external_uid,
        case_org_id=org.id,
        snapshot_id=snapshot_id,
        profile_resolution=org.profile_resolution,
        industry=industry,
        okved_code=okved_code,
        okved_name=okved_name,
        city=_field_from_resolution("city", consensus, conflict, absent, provenance),
        region=_field_from_resolution("region", consensus, conflict, absent, provenance),
        workers_fns=_field_from_resolution(
            "workers_fns_gradation", consensus, conflict, absent, provenance
        ),
        workers_spark=_field_from_resolution(
            "workers_spark_gradation", consensus, conflict, absent, provenance
        ),
        company_age=_field_from_resolution(
            "company_age_years_gradation", consensus, conflict, absent, provenance
        ),
        products=products,
        factoring=factoring,
        fts_countries=fts,
        group=group,
        revenue=revenue,
        conflicts=public_conflicts,
        absent=public_absent,
        provenance=provenance,
    )


def read_case_company_context(
    session: Session,
    *,
    user: User | str,
    company_id: str,
    slot_key: str,
) -> CaseCompanyContext:
    """Membership-gated read of linked case org for an explicit slot.

    Resolves active ``snapshot_id`` once and uses it for every query in this call.
    Does not write. Does not substitute data from a retired snapshot.
    """
    user_id = user.id if isinstance(user, User) else user
    slot = (slot_key or "").strip()
    if not slot:
        raise CaseContextError("slot_key is required")

    _require_membership(session, user_id=user_id, company_id=company_id)

    company = session.get(Company, company_id)
    if company is None:
        raise CaseContextError(f"company {company_id!r} does not exist")
    manual = _manual_slice(company)

    link = session.scalars(
        select(CaseOrgCompanyLink).where(
            CaseOrgCompanyLink.slot_key == slot,
            CaseOrgCompanyLink.company_id == company_id,
        )
    ).first()
    if link is None:
        return CaseCompanyContext(
            status="not_linked",
            slot_key=slot,
            company_id=company_id,
            user_id=user_id,
            reason="company_not_linked_in_slot",
            manual=manual,
        )

    active = get_active_snapshot(session, slot_key=slot)
    if isinstance(active, NoActiveSnapshot):
        return CaseCompanyContext(
            status="no_active_snapshot",
            slot_key=slot,
            company_id=company_id,
            user_id=user_id,
            reason=active.reason,
            manual=manual,
            link=_link_info(link),
            missing_external_uid=link.external_uid,
        )

    # Freeze snapshot id for the rest of this read.
    snapshot_id = active.snapshot_id

    org = session.scalars(
        select(CaseOrg).where(
            CaseOrg.snapshot_id == snapshot_id,
            CaseOrg.external_uid == link.external_uid,
        )
    ).first()
    if org is None:
        return CaseCompanyContext(
            status="uid_missing_in_snapshot",
            slot_key=slot,
            company_id=company_id,
            user_id=user_id,
            reason="linked_uid_absent_from_active_snapshot",
            manual=manual,
            link=_link_info(link),
            active_snapshot=active,
            missing_external_uid=link.external_uid,
        )

    if not org.has_catalog_profile or org.profile_resolution == "absent":
        return CaseCompanyContext(
            status="profile_absent",
            slot_key=slot,
            company_id=company_id,
            user_id=user_id,
            reason="org_present_without_catalog_profile",
            manual=manual,
            link=_link_info(link),
            active_snapshot=active,
            missing_external_uid=None,
            profile=None,
        )

    profile = _build_profile(session, snapshot_id=snapshot_id, org=org)
    return CaseCompanyContext(
        status="profile_available",
        slot_key=slot,
        company_id=company_id,
        user_id=user_id,
        reason="ok",
        manual=manual,
        link=_link_info(link),
        active_snapshot=active,
        profile=profile,
    )
