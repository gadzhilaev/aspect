"""Consensus / conflict / absent resolution for case org catalog variants."""

from __future__ import annotations

from typing import Any

# Typed catalog fields used for resolution (not raw_json).
RESOLUTION_FIELDS: tuple[str, ...] = (
    "org_type",
    "okfs_name",
    "company_age_years_gradation",
    "eco_mark_label",
    "mainokved_code",
    "mainokved_name",
    "negative_mark",
    "workers_fns_gradation",
    "workers_spark_gradation",
    "cl_type",
    "fts_flag",
    "fts_country_name_raw",
    "factoring_mark",
    "revenue_raw",
    "group_external_id",
    "city",
    "region",
)

PRODUCT_CODES: tuple[str, ...] = ("RKO", "GAR", "LOA", "LEA", "DEP", "ZPP")


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def resolve_field_variants(values: list[Any]) -> tuple[str, Any | None, dict[str, Any] | None]:
    """Classify one field across variants.

    Returns (bucket, consensus_value_or_None, conflict_or_absent_payload).
    bucket ∈ {'consensus', 'conflict', 'absent'}.
    """
    present = [v for v in values if _is_present(v)]
    if not present:
        return "absent", None, {"reason": "all_empty"}

    if len(present) < len(values):
        # Some variants empty → incomplete coverage (even if non-empty agree).
        uniq = []
        for v in present:
            if v not in uniq:
                uniq.append(v)
        return (
            "absent",
            None,
            {"reason": "incomplete_coverage", "non_empty_values": uniq},
        )

    uniq: list[Any] = []
    for v in present:
        if v not in uniq:
            uniq.append(v)
    if len(uniq) == 1:
        return "consensus", uniq[0], None
    return "conflict", None, {"reason": "divergent_values", "values": uniq}


def resolve_catalog_variants(
    variant_rows: list[dict[str, Any]],
    *,
    product_marks_by_row: list[dict[str, bool | None]] | None = None,
) -> dict[str, Any]:
    """Build consensus/conflict/absent for catalog field dicts + optional products.

    ``variant_rows`` — one dict per catalog variant (keys from RESOLUTION_FIELDS).
    ``product_marks_by_row`` — parallel list of {product_code: mark|None}.
    """
    if not variant_rows:
        raise ValueError("variant_rows must be non-empty")

    consensus: dict[str, Any] = {}
    conflict: dict[str, Any] = {}
    absent: dict[str, Any] = {}

    for field in RESOLUTION_FIELDS:
        values = [row.get(field) for row in variant_rows]
        bucket, cval, payload = resolve_field_variants(values)
        if bucket == "consensus":
            consensus[field] = cval
        elif bucket == "conflict":
            conflict[field] = payload
        else:
            absent[field] = payload

    products_consensus: dict[str, bool] = {}
    products_conflict: dict[str, Any] = {}
    products_absent: dict[str, Any] = {}
    if product_marks_by_row is not None:
        if len(product_marks_by_row) != len(variant_rows):
            raise ValueError("product_marks_by_row length mismatch")
        for code in PRODUCT_CODES:
            marks = [pm.get(code) for pm in product_marks_by_row]
            bucket, cval, payload = resolve_field_variants(marks)
            if bucket == "consensus":
                products_consensus[code] = bool(cval)
            elif bucket == "conflict":
                products_conflict[code] = payload
            else:
                products_absent[code] = payload

    variant_count = len(variant_rows)
    if conflict or products_conflict:
        profile_resolution = "conflict"
    elif variant_count == 1:
        profile_resolution = "single"
    else:
        profile_resolution = "consensus"

    if products_consensus or products_conflict or products_absent:
        if products_consensus:
            consensus["products"] = products_consensus
        if products_conflict:
            conflict["products"] = products_conflict
        if products_absent:
            absent["products"] = products_absent

    # Group membership: conflicted if distinct non-empty group ids across variants.
    group_ids = [
        row.get("group_external_id")
        for row in variant_rows
        if _is_present(row.get("group_external_id"))
    ]
    distinct_groups = list(dict.fromkeys(group_ids))
    group_membership_conflicted = len(distinct_groups) > 1
    if group_membership_conflicted and "group_external_id" not in conflict:
        # ensure group field reflected as conflict when multiple present values differ
        # (resolve_field_variants already handles this when all present)
        pass

    return {
        "consensus_json": consensus,
        "conflict_json": conflict,
        "absent_json": absent,
        "variant_count": variant_count,
        "confirmed_field_count": len(consensus),
        "profile_resolution": profile_resolution,
        "group_membership_conflicted": group_membership_conflicted,
        "distinct_group_ids": distinct_groups,
    }
