from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.schemas.company import CompanySummaryOut


class CompanyRegistryLookupIn(BaseModel):
    """ИНН и/или свободный запрос (название). URL запрещены."""

    # Legacy: exact INN lookup.
    inn: str | None = Field(default=None, min_length=1, max_length=32)
    # Preferred: INN or company name (not a URL).
    query: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _require_query(self) -> "CompanyRegistryLookupIn":
        if not (self.query or self.inn):
            raise ValueError("Укажите ИНН или название компании")
        raw = (self.query or self.inn or "").strip()
        lower = raw.lower()
        if lower.startswith("http://") or lower.startswith("https://") or "://" in lower:
            raise ValueError("URL в запросе не допускается")
        return self


class RegistrySourceOut(BaseModel):
    provider: str
    title: str
    note: str


class RegistryCandidateOut(BaseModel):
    candidate_id: str
    org_type: str
    inn: str
    kpp: str | None = None
    ogrn: str | None = None
    ogrn_date: str | None = None
    name_short: str | None = None
    name_full: str | None = None
    address: str | None = None
    region: str | None = None
    city: str | None = None
    okved: str | None = None
    okved_name: str | None = None
    okved_version: str | None = None
    status: str | None = None
    status_label: str | None = None
    is_active: bool = False
    branch_type: str | None = None
    suggested_industry: str | None = None


class CompanyRegistryLookupOut(BaseModel):
    # status: ok | not_found | not_configured (failures are returned as errors)
    status: str
    query_inn: str = ""
    query: str | None = None
    lookup_mode: str | None = None  # inn | name
    lookup_id: str | None = None
    expires_at: str | None = None
    source: RegistrySourceOut | None = None
    retrieved_at: str | None = None
    source_actuality_date: str | None = None
    candidate_count: int = 0
    candidates: list[RegistryCandidateOut] = Field(default_factory=list)
    note: str | None = None


class CompanyRegistryConfirmIn(BaseModel):
    lookup_id: str = Field(min_length=1, max_length=64)
    candidate_id: str = Field(min_length=1, max_length=16)


class CompanyRegistryConfirmOut(BaseModel):
    company: CompanySummaryOut
    created: bool
    opened_existing: bool
    applied_fields: list[str] = Field(default_factory=list)
    suggested_industry: str | None = None
    source: RegistrySourceOut
    note: str
