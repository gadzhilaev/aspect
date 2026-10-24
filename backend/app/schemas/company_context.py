"""UI-shaped company business-context payload — no internal codes in labels."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CaseContextStatus = Literal[
    "integration_not_configured",
    "not_linked",
    "no_active_snapshot",
    "uid_missing_in_snapshot",
    "profile_absent",
    "profile_available",
]

CaseFieldStatus = Literal["confirmed", "conflict", "absent"]
CaseMarkStatus = Literal["true", "false", "unknown", "conflict"]


class TrackingCategoryOut(BaseModel):
    key: str
    title: str
    values: list[str] = Field(default_factory=list)
    explanation: str
    filled: bool = True
    cta_label: str | None = None
    cta_href: str | None = None


class MapGroupOut(BaseModel):
    key: str
    title: str
    count: int
    items: list[str] = Field(default_factory=list)
    explanation: str


class CoverageBlockOut(BaseModel):
    key: str
    title: str
    filled: bool
    summary: str
    cta_label: str | None = None
    cta_href: str | None = None


class ContextExampleOut(BaseModel):
    available: bool = False
    event_id: str | None = None
    public_title: str | None = None
    public_summary: str | None = None
    impact_score: int | None = None
    confidence_percent: int | None = None
    link_label: str | None = None
    impact_href: str | None = None


class CaseResolvedFieldOut(BaseModel):
    key: str
    status: CaseFieldStatus
    value: Any | None = None
    detail: dict[str, Any] | None = None


class CaseProductMarkOut(BaseModel):
    code: str
    label: str
    status: CaseMarkStatus


class CaseFactoringOut(BaseModel):
    """Catalog factoring mark — not a loan amount or contract terms."""

    status: CaseMarkStatus
    explanation: str


class CaseFtsGeographyOut(BaseModel):
    status: CaseFieldStatus
    countries_raw: list[str] = Field(default_factory=list)
    interpretation_note: str = (
        "Сырые названия стран ФТС из каталога; направление торговли не выводится."
    )
    detail: dict[str, Any] | None = None


class CaseGroupOut(BaseModel):
    """Own group id only — never other members' profiles."""

    status: CaseFieldStatus
    external_group_id: str | None = None
    is_conflicted: bool = False
    detail: dict[str, Any] | None = None


class CaseRevenueOut(BaseModel):
    status: CaseFieldStatus
    revenue_raw: str | None = None
    amount: str | None = Field(
        default=None,
        description="Exact numeric string when confirmed; not rubles",
    )
    unit: str | None = None
    currency: str | None = None
    limitations: list[str] = Field(default_factory=list)


class CaseProvenanceOut(BaseModel):
    snapshot_id: str
    version_label: str | None = None
    version_seq: int | None = None
    source_file: str | None = None
    source_row_numbers: list[int] = Field(default_factory=list)
    catalog_row_ids: list[str] = Field(default_factory=list)
    variant_count: int = 0


class CaseProfileOut(BaseModel):
    external_uid: str
    profile_resolution: str
    okved_code: CaseResolvedFieldOut
    okved_name: CaseResolvedFieldOut
    city: CaseResolvedFieldOut
    region: CaseResolvedFieldOut
    workers_fns: CaseResolvedFieldOut
    workers_spark: CaseResolvedFieldOut
    company_age: CaseResolvedFieldOut
    products: list[CaseProductMarkOut] = Field(default_factory=list)
    factoring: CaseFactoringOut
    fts_geography: CaseFtsGeographyOut
    group: CaseGroupOut
    revenue: CaseRevenueOut
    conflicts: dict[str, Any] = Field(default_factory=dict)
    absent: dict[str, Any] = Field(default_factory=dict)
    provenance: CaseProvenanceOut


class CaseContextOut(BaseModel):
    """Additive competition-case block. Does not replace manual twin fields."""

    status: CaseContextStatus
    explanation: str
    slot_key: str | None = None
    external_uid: str | None = None
    snapshot_id: str | None = None
    version_label: str | None = None
    version_seq: int | None = None
    profile: CaseProfileOut | None = None
    read_only: bool = True


class CompanyContextOut(BaseModel):
    company_name: str
    industry_label: str | None = None
    business_role: str | None = None
    size_label: str | None = None
    hq_region: str | None = None
    profile_ready: bool
    status_label: str
    setup_cta_label: str
    setup_href: str
    is_demo: bool = False
    tracking: list[TrackingCategoryOut] = Field(default_factory=list)
    tracking_gaps: list[TrackingCategoryOut] = Field(default_factory=list)
    map_groups: list[MapGroupOut] = Field(default_factory=list)
    coverage_blocks: list[CoverageBlockOut] = Field(default_factory=list)
    coverage_filled: int = 0
    coverage_total: int = 0
    example: ContextExampleOut | None = None
    case_context: CaseContextOut
