"""Bank materials services (eligibility, dry-run, load, QA revisions)."""

from app.services.bank_materials.eligibility import (
    FragmentEligibility,
    compute_fragment_eligibility,
)
from app.services.bank_materials.dry_run import (
    DryRunResult,
    run_bank_materials_dry_run,
    write_reports,
)
from app.services.bank_materials.load import (
    BankLoadError,
    CorpusLoadResult,
    DocumentLoadResult,
    assert_bank_schema_ready,
    load_bank_document,
    run_bank_materials_load,
)
from app.services.bank_materials.apply_qa_revisions import (
    QaApplyResult,
    apply_qa_revisions,
    load_qa_artifact,
    run_apply_qa_revisions,
)
from app.services.bank_materials.fragment_revision import (
    SelectedFragment,
    get_fragment_by_id,
    get_latest_fragment,
    select_latest_with_eligibility,
)
from app.services.bank_materials.retrieval import (
    FragmentHit,
    RetrievalResult,
    retrieve_bank_fragments,
)
from app.services.bank_materials.access import (
    BankMaterialsScope,
    build_document_out,
    build_fragment_out,
    scope_from_settings,
)
from app.services.bank_materials.event_evidence import (
    build_event_search_query,
    collect_event_bank_evidence,
    resolve_event_as_of_date,
)

__all__ = [
    "FragmentEligibility",
    "compute_fragment_eligibility",
    "DryRunResult",
    "run_bank_materials_dry_run",
    "write_reports",
    "BankLoadError",
    "CorpusLoadResult",
    "DocumentLoadResult",
    "assert_bank_schema_ready",
    "load_bank_document",
    "run_bank_materials_load",
    "QaApplyResult",
    "apply_qa_revisions",
    "load_qa_artifact",
    "run_apply_qa_revisions",
    "SelectedFragment",
    "get_fragment_by_id",
    "get_latest_fragment",
    "select_latest_with_eligibility",
    "FragmentHit",
    "RetrievalResult",
    "retrieve_bank_fragments",
    "BankMaterialsScope",
    "build_document_out",
    "build_fragment_out",
    "scope_from_settings",
    "build_event_search_query",
    "collect_event_bank_evidence",
    "resolve_event_as_of_date",
]
