from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = None
    tax_id: str | None = None
    industry: str | None = None
    size_band: str | None = None
    hq_region: str | None = None


class CompanyPatchIn(BaseModel):
    name: str | None = None
    legal_name: str | None = None
    tax_id: str | None = None
    industry: str | None = None
    size_band: str | None = None
    hq_region: str | None = None


class NodeCreateIn(BaseModel):
    node_type: str
    name: str
    attributes_json: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    output_share_percent: float | None = None
    country: str | None = None
    region: str | None = None


class NodePatchIn(BaseModel):
    name: str | None = None
    attributes_json: dict[str, Any] | None = None
    status: str | None = None
    output_share_percent: float | None = None
    country: str | None = None
    region: str | None = None


class EdgeCreateIn(BaseModel):
    from_node_id: str
    relation_type: str
    to_node_id: str
    attributes_json: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.8
    source_type: str = "user"


class FinancePatchIn(BaseModel):
    """Partial finance update.

    ``optional_finance`` is merged into stored JSON:
    - key absent → keep previous;
    - key: null or \"\" → clear knowledge (not write 0);
    - key: value (including 0) → set known value.
    """

    purchase_currencies: list[str] = Field(default_factory=list)
    optional_finance: dict[str, Any] = Field(default_factory=dict)


class CompanySummaryOut(BaseModel):
    id: str
    name: str
    legal_name: str | None
    tax_id: str | None
    industry: str | None
    size_band: str | None
    hq_region: str | None
    profile_status: str
    digital_twin_status: str
    digital_twin_coverage: float
    is_demo: bool
    role: str | None = None


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    node_type: str
    name: str
    attributes_json: dict[str, Any]
    status: str
    output_share_percent: float | None
    country: str | None
    region: str | None


class EdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    from_node_id: str
    relation_type: str
    to_node_id: str
    attributes_json: dict[str, Any]
    confidence: float
    source_type: str


class ProfileOut(BaseModel):
    company: CompanySummaryOut
    nodes: list[NodeOut]
    edges: list[EdgeOut]
    settings: dict[str, Any]
    warnings: list[str]
    completeness: dict[str, Any]
