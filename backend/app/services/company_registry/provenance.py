"""Provenance for registry-sourced requisites vs. manually entered data.

Stored under company_profile_settings.preferences_json["registry_provenance"].
A field stays "from registry" only until the user edits it — then it moves to
``fields_overridden_manually`` and is no longer presented as registry-verified.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

REGISTRY_PROVENANCE_KEY = "registry_provenance"

# Company attribute → provenance field label (what we can apply from a candidate).
APPLICABLE_FIELDS = ("name", "legal_name", "tax_id", "hq_region")
# Company attributes whose manual change should drop registry provenance.
TRACKED_FIELDS = ("name", "legal_name", "tax_id", "hq_region", "industry", "size_band")


def company_fields_from_candidate(candidate: dict[str, Any]) -> dict[str, str]:
    """Only public requisites we can safely prefill. Address region, not full address.

    Note: industry is intentionally NOT auto-applied (OKVED ≠ industry); it is
    offered as a suggestion for the user to confirm.
    """
    out: dict[str, str] = {}
    name_short = candidate.get("name_short")
    name_full = candidate.get("name_full")
    if name_short:
        out["name"] = str(name_short)
    if name_full:
        out["legal_name"] = str(name_full)
    if candidate.get("inn"):
        out["tax_id"] = str(candidate["inn"])
    if candidate.get("region"):
        out["hq_region"] = str(candidate["region"])
    return out


def build_provenance(
    candidate: dict[str, Any],
    *,
    source: dict[str, Any],
    retrieved_at_iso: str,
    actuality: str | None,
    applied_fields: dict[str, str],
) -> dict[str, Any]:
    return {
        "source": source,
        "retrieved_at": retrieved_at_iso,
        "source_actuality_date": actuality,
        "inn": candidate.get("inn"),
        "org_type": candidate.get("org_type"),
        "status": candidate.get("status"),
        "okved": candidate.get("okved"),
        "okved_name": candidate.get("okved_name"),
        "okved_version": candidate.get("okved_version"),
        "ogrn": candidate.get("ogrn"),
        "kpp": candidate.get("kpp"),
        "branch_type": candidate.get("branch_type"),
        # Snapshot of values we actually wrote, to detect later manual edits.
        "fields_from_registry": dict(applied_fields),
        "fields_overridden_manually": [],
        "verified_scope": "public_requisites",
    }


def note_manual_overrides(
    preferences: dict[str, Any], changes: dict[str, Any]
) -> dict[str, Any]:
    """Given company field changes, move edited registry fields to manual origin.

    ``changes`` maps Company attribute → new value.

    Returns a brand-new preferences dict (deep-copied, no shared nested refs) so
    that assigning it back to a plain JSON column is reliably detected as a change
    by SQLAlchemy (in-place mutation of the loaded dict would NOT be persisted).
    """
    prov = preferences.get(REGISTRY_PROVENANCE_KEY)
    if not isinstance(prov, dict):
        return preferences
    from_registry = prov.get("fields_from_registry")
    if not isinstance(from_registry, dict):
        return preferences

    new_prefs = copy.deepcopy(preferences)
    new_prov = new_prefs[REGISTRY_PROVENANCE_KEY]
    new_from_registry = new_prov["fields_from_registry"]
    overridden = list(new_prov.get("fields_overridden_manually") or [])
    for field, new_value in changes.items():
        if field not in TRACKED_FIELDS:
            continue
        if field in new_from_registry and str(new_from_registry[field]) != str(new_value):
            if field not in overridden:
                overridden.append(field)
            new_from_registry.pop(field, None)
    new_prov["fields_overridden_manually"] = overridden
    new_prov["fields_from_registry"] = new_from_registry
    new_prov["updated_at"] = datetime.now(timezone.utc).isoformat()
    return new_prefs
