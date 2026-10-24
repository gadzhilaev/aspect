from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExposureOut(BaseModel):
    label: str
    value: float
    unit: str


class MetricMeaningOut(BaseModel):
    key: str
    label: str
    value: float | int | None = None
    unit: str | None = None
    meaning: str


class AssessmentExplanationOut(BaseModel):
    """How the shown assessment was produced — Flutter-safe additive field."""

    basis_available: bool
    summary: str
    metrics: list[MetricMeaningOut] = Field(default_factory=list)
    used_event_data: list[str] = Field(default_factory=list)
    used_company_data: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    calculation: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    model_version: str | None = None
    computed_at: str | None = None
    assessment_state: str = "monitoring_only"
    is_demo_event: bool = False
    metric_labels: dict[str, str] = Field(default_factory=dict)
    score_kind: str | None = None
    score_kind_label: str | None = None
    confidence_detail: dict[str, Any] = Field(default_factory=dict)
    demo_score_override: dict[str, Any] | None = None


class ProfileRelevanceMatchOut(BaseModel):
    """One explainable product×theme rule hit (positive status=true only)."""

    rule_id: str
    theme: str
    product_code: str
    product_label: str
    product_status: str
    explanation: str
    event_theme_signals: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ProfileRelevanceProvenanceOut(BaseModel):
    snapshot_id: str | None = None
    version_label: str | None = None
    version_seq: int | None = None
    source_file: str | None = None
    source_row_numbers: list[int] = Field(default_factory=list)
    external_uid: str | None = None


class ProfileRelevanceOut(BaseModel):
    """Case-profile inclusion basis — not an impact calculation."""

    matched: bool
    label: str = "По профилю компании"
    summary: str
    matches: list[ProfileRelevanceMatchOut] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: ProfileRelevanceProvenanceOut | None = None


class EventCardOut(BaseModel):
    id: str
    title: str
    category: str
    priority: str
    impact_score: float | None = Field(
        description=(
            "Known assessment 0…100, or null when unavailable. "
            "Known zero remains 0.0 — never coerce null→0. "
            "For score_kind=case_profile_match this is null (no assessment)."
        ),
    )
    impact_score_available: bool = Field(
        default=True,
        description=(
            "Explicit availability of impact_score. "
            "False ⇒ no assessment (impact_score is null); do not display as zero."
        ),
    )
    urgency: str
    confidence: float
    reason_summary: str
    exposure: ExposureOut | None = None
    claims: dict[str, Any]
    source_count: int
    updated_at: datetime
    status: str
    is_demo: bool = True
    assessment_state: str = "monitoring_only"
    # Additive labels — old clients ignore unknown fields
    metric_labels: dict[str, str] = Field(default_factory=dict)
    # company_calculated | event_severity_signal | case_profile_match | unavailable
    score_kind: str = "company_calculated"
    score_kind_label: str = "Индекс влияния"
    # Additive (6.9): why the card is in the personal feed. Old clients ignore.
    # Values: calculated_impact | event_severity_signal | case_profile
    inclusion_bases: list[str] = Field(default_factory=list)
    profile_relevance: ProfileRelevanceOut | None = None


class EventSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    publisher: str
    url: str | None
    published_at: datetime | None
    source_quality: float
    excerpt: str | None
    is_stub: bool


class RelevanceMatchOut(BaseModel):
    axis: str
    role: str | None = None
    event_value: str
    company_value: str
    node_id: str | None = None
    node_name: str | None = None
    node_type: str | None = None


class RelevanceOut(BaseModel):
    """Why this event is or is not linked to the company — additive, no side effects."""

    event_id: str
    company_id: str
    is_relevant: bool
    level: str
    summary: str
    matched_features: list[RelevanceMatchOut] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    country_roles_considered: list[str] = Field(default_factory=list)
    has_active_impact: bool = False
    assessment_state: str | None = None
    score_kind: str | None = None
    feed_group: str | None = None
    profile_fingerprint: str | None = None


class EventDetailOut(BaseModel):
    id: str
    title: str
    summary: str
    category: str
    event_type: str
    severity: float | None = None
    status: str
    occurred_at: datetime
    effective_from: datetime | None
    impact: EventCardOut | None
    sources: list[EventSourceOut]
    claims: dict[str, Any]
    is_demo: bool
    disclaimer: str = "Демонстрационные данные и оценки"
    relevance: RelevanceOut | None = None


class ImpactPathOut(BaseModel):
    id: str
    path_nodes: list[dict[str, Any]]
    path_edges: list[str]
    exposure_value: float | None
    claim_type: str
    explanation: str
    sort_order: int


class ImpactOut(BaseModel):
    event_id: str
    company_id: str
    impact_score: float
    urgency: str
    confidence: float
    reason_summary: str
    exposure: ExposureOut | None
    score_breakdown: dict[str, Any]
    claims: dict[str, Any]
    paths: list[ImpactPathOut]
    model_version: str
    computed_at: datetime
    assessment_state: str = "monitoring_only"
    finance_setup_href: str | None = None
    disclaimer: str = (
        "impact_score может быть персональным индексом (company_calculated) "
        "или предварительным сигналом события (event_severity_signal) — смотрите score_kind. "
        "Качество данных (confidence) — эвристика, не вероятность. "
        "Доля выпуска — связанность с узлом, не прогноз потерь; null ≠ 0."
    )
    assessment_explanation: AssessmentExplanationOut | None = None
    metric_labels: dict[str, str] = Field(default_factory=dict)
    score_kind: str = "company_calculated"
    score_kind_label: str = "Индекс влияния"


class PersonalFeedEmptyOut(BaseModel):
    """Honest empty-state for «Для вас» — never invents matches."""

    reason: str
    title: str
    detail: str
    primary_href: str | None = None
    primary_label: str | None = None
    secondary_href: str | None = None
    secondary_label: str | None = None


class DashboardOut(BaseModel):
    counters: dict[str, int]
    priority_events: list[EventCardOut]
    digital_twin: dict[str, Any]
    company_name: str
    feed_sort_rule: str = (
        "Groups: company_calculated, then event_severity_signal, then case_profile_match; "
        "within impact groups impact_score DESC; within case_profile_match occurred_at DESC; "
        "tie-break event_id ASC. Bases are not compared by one number. "
        "Cursor: '{group}:{sort_key}:{event_id}'."
    )
    feed_empty: PersonalFeedEmptyOut | None = None


class SimulateIn(BaseModel):
    solution_id: str | None = None
    inventory_days: int = Field(default=14, ge=0, le=365)
    delay_days: int = Field(default=45, ge=0, le=365)
    extra: dict[str, Any] = Field(default_factory=dict)


class SolutionOut(BaseModel):
    id: str
    name: str
    country: str | None
    cost_delta_percent: float
    lead_time_days: int
    risk_percent: float
    compatibility: float
    availability_status: str
    sort_score: float
    sort_breakdown: dict[str, Any]
    is_demo: bool
    notes: str | None


class DecisionIn(BaseModel):
    scenario_id: str
    decision_note: str | None = None
    status: str = "selected"


class ActionItemIn(BaseModel):
    title: str
    assignee_user_id: str | None = None
    due_at: datetime | None = None


class ActionItemPatchIn(BaseModel):
    title: str | None = None
    status: str | None = None
    assignee_user_id: str | None = None
    due_at: datetime | None = None
