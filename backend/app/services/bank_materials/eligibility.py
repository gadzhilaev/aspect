"""Conservative fragment eligibility for search / AI evidence / exact quote.

Pure function: no DB queries, no LLM. Stored eligible_* columns are intentionally absent;
callers must compute flags at read time.
"""

from __future__ import annotations

from dataclasses import dataclass

ALLOWED_REGION_TYPES = frozenset(
    {
        "prose",
        "table",
        "chart",
        "contacts_disclaimer",
        "mixed",
        "unverified",
    }
)
ANALYTIC_BLOCKED_REGION_TYPES = frozenset(
    {
        "table",
        "chart",
        "contacts_disclaimer",
        "mixed",
    }
)
SEARCHABLE_STATUSES = frozenset({"verified", "unverified", "needs_reverification"})


@dataclass(frozen=True)
class FragmentEligibility:
    eligible_search: bool
    eligible_ai_evidence: bool
    eligible_exact_quote: bool
    """True when AI evidence is allowed only as an explicit summary, never as a quote."""
    evidence_as_summary_only: bool
    reasons: tuple[str, ...]


def _nonempty(text: str | None) -> bool:
    return bool(text and text.strip())


def compute_fragment_eligibility(
    *,
    verification_status: str,
    kind: str,
    primary_region_type: str,
    content_type: str | None,
    content_type_status: str,
    verified_transcript: str | None,
    summary_text: str | None,
    region_count: int = 0,
    page_visual_verification_status: str | None = None,
    mean_confidence: float | None = None,
) -> FragmentEligibility:
    """Return eligibility flags for one fragment revision.

    ``page_visual_verification_status`` and ``mean_confidence`` are accepted so callers
    can pass page OCR metrics without accidentally treating them as verification.
    They never raise search / evidence / quote eligibility.

    ``region_count`` must be the number of fragment regions. An empty region list
    never unlocks AI evidence or exact quote (search may still be allowed for prose).
    """
    del page_visual_verification_status, mean_confidence  # explicitly unused

    reasons: list[str] = []
    if region_count < 0:
        reasons.append("region_count_negative")
        return FragmentEligibility(
            eligible_search=False,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    if primary_region_type not in ALLOWED_REGION_TYPES:
        reasons.append("unknown_primary_region_type")
        return FragmentEligibility(
            eligible_search=False,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    if primary_region_type in ANALYTIC_BLOCKED_REGION_TYPES:
        reasons.append(f"region_type_blocked:{primary_region_type}")
        return FragmentEligibility(
            eligible_search=False,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    # prose or unverified region type — search candidates only unless fully verified prose
    if primary_region_type == "unverified":
        reasons.append("region_type_unverified")
        search = verification_status in SEARCHABLE_STATUSES
        if not search:
            reasons.append(f"verification_status_not_searchable:{verification_status}")
        return FragmentEligibility(
            eligible_search=search,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    # primary_region_type == prose
    if verification_status not in SEARCHABLE_STATUSES:
        reasons.append(f"verification_status_unknown:{verification_status}")
        return FragmentEligibility(
            eligible_search=False,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    if kind not in ("exact_quote", "summary"):
        reasons.append(f"kind_unknown:{kind}")
        return FragmentEligibility(
            eligible_search=True,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    contradictory = False
    if kind == "exact_quote" and not _nonempty(verified_transcript):
        reasons.append("exact_quote_missing_verified_transcript")
        contradictory = True
    if kind == "summary" and not _nonempty(summary_text):
        reasons.append("summary_missing_summary_text")
        contradictory = True
    if kind == "exact_quote" and _nonempty(summary_text) and not _nonempty(verified_transcript):
        reasons.append("exact_quote_has_summary_without_transcript")
        contradictory = True
    if kind == "summary" and _nonempty(verified_transcript) and not _nonempty(summary_text):
        reasons.append("summary_has_transcript_without_summary_text")
        contradictory = True

    if verification_status in ("unverified", "needs_reverification"):
        reasons.append(f"verification_status:{verification_status}")
        return FragmentEligibility(
            eligible_search=True,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    # verified
    if contradictory:
        reasons.append("contradictory_inputs_block_evidence_and_quote")
        return FragmentEligibility(
            eligible_search=True,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    if region_count < 1:
        reasons.append("verified_without_regions_blocks_evidence_and_quote")
        return FragmentEligibility(
            eligible_search=True,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    if content_type_status != "confirmed":
        reasons.append(f"content_type_status_not_confirmed:{content_type_status}")
        return FragmentEligibility(
            eligible_search=True,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    if content_type not in ("fact", "forecast", "interpretation"):
        reasons.append(f"content_type_missing_or_unknown:{content_type!r}")
        return FragmentEligibility(
            eligible_search=True,
            eligible_ai_evidence=False,
            eligible_exact_quote=False,
            evidence_as_summary_only=False,
            reasons=tuple(reasons),
        )

    if kind == "summary":
        reasons.append("verified_summary_evidence_as_summary_only")
        return FragmentEligibility(
            eligible_search=True,
            eligible_ai_evidence=True,
            eligible_exact_quote=False,
            evidence_as_summary_only=True,
            reasons=tuple(reasons),
        )

    # kind == exact_quote, verified, confirmed content_type, nonempty transcript, has regions
    reasons.append("verified_exact_quote")
    return FragmentEligibility(
        eligible_search=True,
        eligible_ai_evidence=True,
        eligible_exact_quote=True,
        evidence_as_summary_only=False,
        reasons=tuple(reasons),
    )
