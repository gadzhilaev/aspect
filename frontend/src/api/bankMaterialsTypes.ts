/** Typed contracts for bank materials API + assistant bank_evidence_list. */

export type BankTextKind = 'exact_quote' | 'summary' | 'restricted'

export type BankContentType = 'fact' | 'forecast' | 'interpretation'

export type BankEvidenceBlockStatus =
  | 'available'
  | 'no_matching_evidence'
  | 'integration_not_configured'
  | 'event_date_unavailable'
  | 'fetch_error'
  | string

/** GET /events/{id}/bank-evidence (stage 2.13 / news page 6.12). */
export type EventBankEvidenceStatus =
  | 'available'
  | 'no_matching_evidence'
  | 'integration_not_configured'
  | 'event_date_unavailable'
  | string

export type EventBankEvidenceItem = {
  fragment_id: string
  revision: number
  document_id: string
  document_title: string | null
  document_slug: string
  publication_date: string | null
  publication_year: number | null
  publication_month: number | null
  publication_date_precision: string
  publication_date_display: string | null
  page_number: number
  text_kind: BankTextKind | string
  text: string
  content_type: BankContentType | string | null
  content_type_status: string
  source_role: string | null
  source_role_meaning: string
  qa_method: string | null
  document_href: string
  fragment_href: string
  content_href: string
}

export type EventBankEvidence = {
  event_id: string
  status: EventBankEvidenceStatus
  event_occurred_at: string | null
  as_of_date: string | null
  as_of_date_basis: string | null
  query_preview: string | null
  evidence: EventBankEvidenceItem[]
  limitations: string[]
  empty_reason: string | null
}

export type BankUsedFragment = {
  fragment_id: string
  revision: number
  text_kind: BankTextKind | string
  text: string
  content_type: BankContentType | string | null
  document_title: string | null
  publication_date: string | null
  publication_date_precision: string | null
  page_number: number | null
  source_role: string | null
  qa_method: string | null
  document_href: string | null
  fragment_href: string | null
  content_href: string | null
  section_hint?: string | null
}

export type BankEvidenceListData = {
  status: BankEvidenceBlockStatus
  available?: boolean
  event_occurred_at?: string | null
  as_of_date?: string | null
  as_of_date_basis?: string | null
  used: BankUsedFragment[]
  diagnostics?: Record<string, unknown>
  limitations?: string[]
  provenance_note?: string
  fetch_error?: { code?: string; message?: string } | null
}

export type BankRegion = {
  page_number: number
  sort_order: number
  region_type: string
  bbox_left: number | null
  bbox_top: number | null
  bbox_width: number | null
  bbox_height: number | null
  note: string | null
}

export type BankFragmentDetail = {
  fragment_id: string
  document_id: string
  document_file_id: string
  ocr_run_id: string
  stable_key: string
  revision: number
  is_latest_revision: boolean
  is_superseded: boolean
  supersedes_fragment_id: string | null
  latest_revision: number
  kind: string
  content_type: string | null
  content_type_status: string
  page_number: number
  regions: BankRegion[]
  verification_status: string
  primary_region_type: string
  eligible_search: boolean
  eligible_ai_evidence: boolean
  eligible_exact_quote: boolean
  evidence_as_summary_only: boolean
  eligibility_reasons: string[]
  text_kind: BankTextKind
  text: string | null
  text_restricted: boolean
  restriction_reasons: string[]
  source_role: string | null
  source_role_meaning: string
  qa_method: string | null
  qa_performed_by: string | null
  qa_performed_at: string | null
  pdf_sha256: string
  ocr_fingerprint_hash: string
  document_slug: string
  document_title: string | null
  content_href: string
}

export type BankFileRef = {
  file_id: string
  original_filename: string
  page_count: number
  byte_size: number
  pdf_sha256: string
  revision_label: string | null
  supersedes_file_id: string | null
  content_href: string
  ocr_runs: Array<{
    ocr_run_id: string
    fingerprint_hash: string
    processing_status: string
    schema_version: number
    created_at: string | null
  }>
}

export type BankDocumentDetail = {
  document_id: string
  slug: string
  title: string | null
  title_status: string
  publication_date: string | null
  publication_year: number | null
  publication_month: number | null
  publication_date_precision: string
  publication_date_display: string | null
  period_covered: string | null
  period_covered_status: string
  topics: string[]
  topics_status: string
  staleness_note: string | null
  is_current_stance: boolean
  document_visual_status: string
  files: BankFileRef[]
}
