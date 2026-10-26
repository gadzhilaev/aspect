/** Types aligned with backend schemas. Public types never include company impact. */

export type ApiErrorBody = {
  error: {
    code: string
    message: string
    details?: Array<{ field?: string; reason?: string }>
  }
}

export type TokenPair = {
  access_token: string
  refresh_token: string
  token_type: string
}

export type UserCompanyRef = {
  company_id: string
  role: string
  name?: string | null
  profile_status?: string | null
}

export type User = {
  id: string
  email: string
  display_name: string
  email_verified_at: string | null
  companies: UserCompanyRef[]
  preferences?: { language?: 'ru' | 'en'; theme_mode?: 'light' | 'dark' | 'system'; registration_complete?: boolean }
}

export type IndustryProfile = {
  activity_role: string
  product_categories: string[]
  brands: string[]
  product_lines: string[]
  sales_markets: string[]
  procurement_countries: string[]
  purchase_currencies: string[]
}

export type PublicNewsCard = {
  id: string
  title: string
  summary: string
  category: string
  category_label: string
  event_type: string
  event_type_label: string
  severity_label: string
  occurred_at: string
  image_url: string
  reading_time_min: number
  is_featured: boolean
  is_demo: boolean
  source_count: number
  primary_publisher?: string | null
  primary_published_at?: string | null
  primary_source_url?: string | null
}

export type PublicNewsSource = {
  publisher: string
  published_at: string | null
  excerpt: string | null
  url?: string | null
  is_stub: boolean
}

export type PublicNewsDetail = PublicNewsCard & {
  effective_from: string | null
  body: string
  sources: PublicNewsSource[]
  related: PublicNewsCard[]
}

export type PublicCategory = {
  id: string
  label: string
  description: string
  count: number
}

export type PublicTrending = {
  featured: PublicNewsCard | null
  now_important: PublicNewsCard[]
  risks: PublicNewsCard[]
  opportunities: PublicNewsCard[]
  markets: PublicNewsCard[]
  by_industry: Record<string, PublicNewsCard[]>
}

export type PublicIngestionStatus = {
  status?: string | null
  sources_checked_at?: string | null
  sources_check_ok?: boolean | null
  last_success_at?: string | null
  next_run_at?: string | null
  interval_seconds?: number | null
  counts?: {
    fetched?: number
    inserted?: number
    duplicates?: number
    published?: number
  } | null
  source_errors?: string[]
}

export type PublicNewsPage = {
  items: PublicNewsCard[]
  next_cursor: string | null
  limit: number
  ingestion?: PublicIngestionStatus | null
}

export type Exposure = {
  label: string
  value: number
  unit: string
}

export type MetricMeaning = {
  key: string
  label: string
  value?: number | null
  unit?: string | null
  meaning: string
}

export type ScoreKind =
  | 'company_calculated'
  | 'event_severity_signal'
  | 'case_profile_match'
  | 'industry_profile_match'
  | 'unavailable'

export type AssessmentExplanation = {
  basis_available: boolean
  summary: string
  metrics: MetricMeaning[]
  used_event_data: string[]
  used_company_data: string[]
  dependencies: string[]
  calculation?: string | null
  assumptions: string[]
  missing_data: string[]
  limitations: string[]
  model_version?: string | null
  computed_at?: string | null
  assessment_state: string
  is_demo_event: boolean
  metric_labels: Record<string, string>
  score_kind?: ScoreKind | string | null
  score_kind_label?: string | null
  confidence_detail?: Record<string, unknown>
  demo_score_override?: Record<string, unknown> | null
}

export type AssessmentState =
  | 'supply_chain_ready'
  | 'finance_data_required'
  | 'finance_ready'
  | 'monitoring_only'

export type ProfileRelevanceMatch = {
  rule_id: string
  theme: string
  product_code: string
  product_label: string
  product_status: string
  explanation: string
  event_theme_signals?: string[]
  limitations?: string[]
}

export type ProfileRelevance = {
  matched: boolean
  label?: string
  summary: string
  matches: ProfileRelevanceMatch[]
  limitations?: string[]
  provenance?: {
    snapshot_id?: string | null
    version_label?: string | null
    version_seq?: number | null
    source_file?: string | null
    source_row_numbers?: number[]
    external_uid?: string | null
  } | null
}

export type EventCard = {
  id: string
  title: string
  category: string
  priority: string
  /** Known 0…100, or null when unavailable. Do not coerce null→0. */
  impact_score: number | null
  /** False ⇒ no assessment; impact_score is null. */
  impact_score_available?: boolean
  urgency: string
  confidence: number
  reason_summary: string
  exposure: Exposure | null
  claims: Record<string, number>
  source_count: number
  updated_at: string
  status: string
  is_demo: boolean
  assessment_state?: AssessmentState | string
  metric_labels?: Record<string, string>
  score_kind?: ScoreKind | string
  score_kind_label?: string
  /** calculated_impact | event_severity_signal | case_profile */
  inclusion_bases?: string[]
  profile_relevance?: ProfileRelevance | null
}

export type EventSource = {
  id: string
  publisher: string
  url: string | null
  published_at: string | null
  source_quality: number
  excerpt: string | null
  is_stub: boolean
}

export type RelevanceMatch = {
  axis: string
  role?: string | null
  event_value: string
  company_value: string
  node_id?: string | null
  node_name?: string | null
  node_type?: string | null
}

export type EventRelevance = {
  event_id: string
  company_id: string
  is_relevant: boolean
  level: string
  summary: string
  matched_features: RelevanceMatch[]
  missing_data: string[]
  limitations: string[]
  country_roles_considered: string[]
  has_active_impact: boolean
  assessment_state?: string | null
  score_kind?: string | null
  feed_group?: string | null
  profile_fingerprint?: string | null
}

export type EventDetail = {
  id: string
  title: string
  summary: string
  category: string
  event_type: string
  severity: number
  status: string
  occurred_at: string
  effective_from: string | null
  impact: EventCard | null
  sources: EventSource[]
  claims: Record<string, number>
  is_demo: boolean
  disclaimer: string
  relevance?: EventRelevance | null
}

export type ImpactPath = {
  id: string
  path_nodes: Array<{
    id?: string
    name?: string
    node_type?: string
    output_share_percent?: number | null
    country?: string | null
  }>
  path_edges: string[]
  exposure_value: number | null
  claim_type: string
  explanation: string
  sort_order: number
}

export type Impact = {
  event_id: string
  company_id: string
  impact_score: number
  urgency: string
  confidence: number
  reason_summary: string
  exposure: Exposure | null
  score_breakdown: Record<string, unknown>
  claims: Record<string, number>
  paths: ImpactPath[]
  model_version: string
  computed_at: string
  assessment_state?: AssessmentState | string
  finance_setup_href?: string | null
  disclaimer: string
  assessment_explanation?: AssessmentExplanation | null
  metric_labels?: Record<string, string>
  score_kind?: ScoreKind | string
  score_kind_label?: string
}

export type PersonalFeedEmpty = {
  reason: string
  title: string
  detail: string
  primary_href?: string | null
  primary_label?: string | null
  secondary_href?: string | null
  secondary_label?: string | null
}

export type Dashboard = {
  counters: Record<string, number | undefined>
  priority_events: EventCard[]
  digital_twin: Record<string, unknown>
  company_name: string
  feed_empty?: PersonalFeedEmpty | null
}

export type CompanySummary = {
  id: string
  name: string
  legal_name: string | null
  tax_id: string | null
  industry: string | null
  size_band: string | null
  hq_region: string | null
  profile_status: string
  digital_twin_status: string
  digital_twin_coverage: number
  is_demo: boolean
  role: string | null
}

export type CompanyTrackingCategory = {
  key: string
  title: string
  values: string[]
  explanation: string
  filled: boolean
  cta_label?: string | null
  cta_href?: string | null
}

export type CompanyMapGroup = {
  key: string
  title: string
  count: number
  items: string[]
  explanation: string
}

export type CompanyCoverageBlock = {
  key: string
  title: string
  filled: boolean
  summary: string
  cta_label?: string | null
  cta_href?: string | null
}

export type CompanyContextExample = {
  available: boolean
  event_id?: string | null
  public_title?: string | null
  public_summary?: string | null
  impact_score?: number | null
  confidence_percent?: number | null
  link_label?: string | null
  impact_href?: string | null
}

/** Matches OpenAPI CaseContextOut / nested schemas (additive, optional on older servers). */
export type CaseFieldStatus = 'confirmed' | 'conflict' | 'absent'
export type CaseMarkStatus = 'true' | 'false' | 'unknown' | 'conflict'
export type CaseContextStatus =
  | 'integration_not_configured'
  | 'not_linked'
  | 'no_active_snapshot'
  | 'uid_missing_in_snapshot'
  | 'profile_absent'
  | 'profile_available'

export type CaseResolvedField = {
  key: string
  status: CaseFieldStatus
  value?: unknown
  detail?: Record<string, unknown> | null
}

export type CaseProductMark = {
  code: string
  label: string
  status: CaseMarkStatus
}

export type CaseFactoring = {
  status: CaseMarkStatus
  explanation: string
}

export type CaseFtsGeography = {
  status: CaseFieldStatus
  countries_raw?: string[]
  interpretation_note?: string
  detail?: Record<string, unknown> | null
}

export type CaseGroup = {
  status: CaseFieldStatus
  external_group_id?: string | null
  is_conflicted?: boolean
  detail?: Record<string, unknown> | null
}

export type CaseRevenue = {
  status: CaseFieldStatus
  revenue_raw?: string | null
  amount?: string | null
  unit?: string | null
  currency?: string | null
  limitations?: string[]
}

export type CaseProvenance = {
  snapshot_id: string
  version_label?: string | null
  version_seq?: number | null
  source_file?: string | null
  source_row_numbers?: number[]
  catalog_row_ids?: string[]
  variant_count?: number
}

export type CaseProfile = {
  external_uid: string
  profile_resolution: string
  okved_code: CaseResolvedField
  okved_name: CaseResolvedField
  city: CaseResolvedField
  region: CaseResolvedField
  workers_fns: CaseResolvedField
  workers_spark: CaseResolvedField
  company_age: CaseResolvedField
  products?: CaseProductMark[]
  factoring: CaseFactoring
  fts_geography: CaseFtsGeography
  group: CaseGroup
  revenue: CaseRevenue
  conflicts?: Record<string, unknown>
  absent?: Record<string, unknown>
  provenance: CaseProvenance
}

export type CaseContext = {
  status: CaseContextStatus
  explanation: string
  slot_key?: string | null
  external_uid?: string | null
  snapshot_id?: string | null
  version_label?: string | null
  version_seq?: number | null
  profile?: CaseProfile | null
  read_only?: boolean
}

export type CompanyContext = {
  company_name: string
  industry_label: string | null
  business_role: string | null
  size_label: string | null
  hq_region: string | null
  profile_ready: boolean
  status_label: string
  setup_cta_label: string
  setup_href: string
  is_demo: boolean
  tracking: CompanyTrackingCategory[]
  tracking_gaps: CompanyTrackingCategory[]
  map_groups: CompanyMapGroup[]
  coverage_blocks: CompanyCoverageBlock[]
  coverage_filled: number
  coverage_total: number
  example: CompanyContextExample | null
  /** Absent on older API responses — page must still render. */
  case_context?: CaseContext | null
}

export type CompanyNode = {
  id: string
  node_type: string
  name: string
  attributes_json: Record<string, unknown>
  status: string
  output_share_percent: number | null
  country: string | null
  region: string | null
}

export type CompanyEdge = {
  id: string
  from_node_id: string
  relation_type: string
  to_node_id: string
  attributes_json: Record<string, unknown>
  confidence: number
  source_type: string
}

export type CompanyProfile = {
  company: CompanySummary
  nodes: CompanyNode[]
  edges: CompanyEdge[]
  settings: Record<string, unknown>
  warnings: string[]
  completeness: {
    checks?: Record<string, boolean>
    required_done?: number
    required_total?: number
    percent?: number
    finance_optional?: boolean
  }
}

export type Industry = {
  id: string
  name: string
}

/**
 * External company registry (public requisites by INN).
 * This is NOT our internal company directory, and NOT a direct FNS request —
 * it is public register data via an intermediary (see `source.note`).
 */
export type RegistrySource = {
  provider: string
  title: string
  note: string
}

export type RegistryCandidate = {
  candidate_id: string
  /** 'legal' | 'individual' (syntactic INN kind / registry type) */
  org_type: string
  inn: string
  kpp: string | null
  ogrn: string | null
  ogrn_date: string | null
  name_short: string | null
  name_full: string | null
  address: string | null
  region: string | null
  okved: string | null
  okved_name: string | null
  okved_version: string | null
  /** active | liquidating | liquidated | bankrupt | reorganizing | unknown */
  status: string | null
  status_label: string | null
  is_active: boolean
  /** 'main' | 'branch' */
  branch_type: string | null
  /** Coarse industry SUGGESTION from OKVED — not auto-applied. */
  suggested_industry: string | null
}

/** status: 'ok' | 'not_found' | 'not_configured'. Upstream failures come as ApiError. */
export type RegistryLookupResult = {
  status: 'ok' | 'not_found' | 'not_configured' | string
  query_inn: string
  lookup_id: string | null
  expires_at: string | null
  source: RegistrySource | null
  retrieved_at: string | null
  source_actuality_date: string | null
  candidate_count: number
  candidates: RegistryCandidate[]
  note: string | null
}

export type RegistryConfirmResult = {
  company: CompanySummary
  created: boolean
  opened_existing: boolean
  applied_fields: string[]
  suggested_industry: string | null
  source: RegistrySource
  note: string
}

export type CompanyCreateIn = {
  name: string
  legal_name?: string | null
  tax_id?: string | null
  industry?: string | null
  size_band?: string | null
  hq_region?: string | null
}

export type CompanyPatchIn = {
  name?: string | null
  legal_name?: string | null
  tax_id?: string | null
  industry?: string | null
  size_band?: string | null
  hq_region?: string | null
}

export type NodeCreateIn = {
  node_type: string
  name: string
  attributes_json?: Record<string, unknown>
  status?: string
  output_share_percent?: number | null
  country?: string | null
  region?: string | null
}

export type NodePatchIn = {
  name?: string | null
  attributes_json?: Record<string, unknown> | null
  status?: string | null
  output_share_percent?: number | null
  country?: string | null
  region?: string | null
}

export type EdgeCreateIn = {
  from_node_id: string
  relation_type: string
  to_node_id: string
  attributes_json?: Record<string, unknown>
  confidence?: number
  source_type?: string
}

export type DigitalTwinBuildResult = {
  status: string
  nodes: number
  edges: number
  coverage_percent: number
  impacts_computed?: number
  message: string
}
