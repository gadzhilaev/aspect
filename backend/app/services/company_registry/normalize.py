"""Normalize a DaData findById/party suggestion into our minimal public requisites.

We keep ONLY public registry requisites. Personal data about managers, founders,
physical persons, phones, emails and finance is intentionally dropped and never
forwarded to the client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# DaData state.status → (machine status, human label, is_active)
_STATUS_MAP: dict[str, tuple[str, str, bool]] = {
    "ACTIVE": ("active", "Действующая", True),
    "LIQUIDATING": ("liquidating", "Ликвидируется", False),
    "LIQUIDATED": ("liquidated", "Ликвидирована", False),
    "BANKRUPT": ("bankrupt", "Банкротство", False),
    "REORGANIZING": ("reorganizing", "В процессе реорганизации", False),
}

# Deterministic OKVED (раздел / первые цифры) → internal industry id.
# Shown as a SUGGESTION only; the user confirms or changes it. OKVED is not a
# product list and this mapping is coarse by design.
_OKVED_INDUSTRY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("26", "27"), "electronics"),
    (("28", "29", "30", "25", "33"), "equipment"),
    (("49", "50", "51", "52", "53"), "logistics"),
    (("45", "46", "47"), "retail"),
    (("05", "06", "19", "35"), "energy"),
)


def _epoch_ms_to_date(value: Any) -> str | None:
    """DaData returns ms since epoch. Return ISO date (UTC) or None."""
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def suggest_industry_from_okved(okved: str | None) -> str | None:
    """Deterministic coarse mapping OKVED → industry id, or None if ambiguous."""
    if not okved:
        return None
    head = okved.strip()[:2]
    if not head:
        return None
    for prefixes, industry in _OKVED_INDUSTRY_RULES:
        if head in prefixes:
            return industry
    return None


@dataclass
class RegistryCandidate:
    candidate_id: str
    org_type: str  # "legal" | "individual" | "unknown"
    inn: str
    kpp: str | None = None
    ogrn: str | None = None
    ogrn_date: str | None = None
    name_short: str | None = None
    name_full: str | None = None
    address: str | None = None
    region: str | None = None
    okved: str | None = None
    okved_name: str | None = None
    okved_version: str | None = None
    status: str | None = None
    status_label: str | None = None
    is_active: bool = False
    branch_type: str | None = None  # "main" | "branch" | None
    suggested_industry: str | None = field(default=None)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "org_type": self.org_type,
            "inn": self.inn,
            "kpp": self.kpp,
            "ogrn": self.ogrn,
            "ogrn_date": self.ogrn_date,
            "name_short": self.name_short,
            "name_full": self.name_full,
            "address": self.address,
            "region": self.region,
            "okved": self.okved,
            "okved_name": self.okved_name,
            "okved_version": self.okved_version,
            "status": self.status,
            "status_label": self.status_label,
            "is_active": self.is_active,
            "branch_type": self.branch_type,
            "suggested_industry": self.suggested_industry,
        }


def _org_type(raw: Any) -> str:
    val = str(raw or "").upper()
    if val == "LEGAL":
        return "legal"
    if val == "INDIVIDUAL":
        return "individual"
    return "unknown"


def _branch_type(raw: Any) -> str | None:
    val = str(raw or "").upper()
    if val == "MAIN":
        return "main"
    if val == "BRANCH":
        return "branch"
    return None


def _okved_name(data: dict[str, Any]) -> str | None:
    code = data.get("okved")
    okveds = data.get("okveds")
    if isinstance(okveds, list):
        # Prefer the main activity; fall back to code match.
        for item in okveds:
            if isinstance(item, dict) and item.get("main") and item.get("name"):
                return str(item["name"])
        for item in okveds:
            if isinstance(item, dict) and item.get("code") == code and item.get("name"):
                return str(item["name"])
    return None


def normalize_suggestion(index: int, suggestion: dict[str, Any]) -> RegistryCandidate | None:
    """Map one DaData suggestion → RegistryCandidate. None if INN missing."""
    data = suggestion.get("data")
    if not isinstance(data, dict):
        return None
    inn = data.get("inn")
    if not isinstance(inn, str) or not inn.strip():
        return None

    name = data.get("name") if isinstance(data.get("name"), dict) else {}
    name_short = None
    name_full = None
    if isinstance(name, dict):
        name_short = name.get("short_with_opf") or name.get("short")
        name_full = name.get("full_with_opf") or name.get("full")
    org_type = _org_type(data.get("type"))
    # For individual entrepreneurs the display name comes from value / fio-less label.
    if not name_short:
        name_short = suggestion.get("value")

    address = None
    region = None
    addr = data.get("address")
    if isinstance(addr, dict):
        address = addr.get("value")
        adata = addr.get("data")
        if isinstance(adata, dict):
            region = adata.get("region_with_type") or adata.get("region")

    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    status_raw = str(state.get("status") or "").upper() if isinstance(state, dict) else ""
    status, status_label, is_active = _STATUS_MAP.get(
        status_raw, ("unknown", "Статус неизвестен", False)
    )

    okved = data.get("okved") if isinstance(data.get("okved"), str) else None

    return RegistryCandidate(
        candidate_id=str(index),
        org_type=org_type,
        inn=inn.strip(),
        kpp=(data.get("kpp") if isinstance(data.get("kpp"), str) else None),
        ogrn=(data.get("ogrn") if isinstance(data.get("ogrn"), str) else None),
        ogrn_date=_epoch_ms_to_date(data.get("ogrn_date")),
        name_short=(str(name_short) if name_short else None),
        name_full=(str(name_full) if name_full else None),
        address=(str(address) if address else None),
        region=(str(region) if region else None),
        okved=okved,
        okved_name=_okved_name(data),
        okved_version=(str(data.get("okved_type")) if data.get("okved_type") else None),
        status=status,
        status_label=status_label,
        is_active=is_active,
        branch_type=_branch_type(data.get("branch_type")),
        suggested_industry=suggest_industry_from_okved(okved),
    )


def source_actuality_date(suggestions: list[dict[str, Any]]) -> str | None:
    """Most recent state.actuality_date across suggestions (true registry date)."""
    best: str | None = None
    for s in suggestions:
        data = s.get("data") if isinstance(s, dict) else None
        state = data.get("state") if isinstance(data, dict) else None
        if not isinstance(state, dict):
            continue
        iso = _epoch_ms_to_date(state.get("actuality_date"))
        if iso and (best is None or iso > best):
            best = iso
    return best
