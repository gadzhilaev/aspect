export type AssistantBlockType =
  | 'impact_summary'
  | 'claim_list'
  | 'scenario_comparison'
  | 'missing_data'
  | 'action_plan_draft'
  | 'source_list'
  | 'bank_evidence_list'
  | 'case_context_ref'

export type AssistantBlock = {
  type: AssistantBlockType
  title?: string | null
  data: Record<string, unknown>
  labels: string[]
}

export type AssistantMessage = {
  id: string
  role: string
  content: string
  blocks: AssistantBlock[]
  client_message_id: string | null
  created_at: string
}

export type AnswerBasis =
  | 'ai_explain'
  | 'ai_explain_gigachat'
  | 'ai_explain_hackathon'
  | 'demo_explain'

export type AssistantConversation = {
  id: string
  user_id: string
  company_id: string
  event_id: string
  status: string
  created_at: string
  updated_at: string
  suggestion_chips: string[]
  /** Free-text explanation origin — never exposes provider secrets */
  answer_basis?: AnswerBasis
  /** Actual model id when answer_basis is hackathon */
  answer_model?: string | null
  /** Additive 3.2+: calculation_unavailable ≠ monitoring_only */
  assessment_state?: string | null
  has_impact_calculation?: boolean
}

export type ConversationListStatus =
  | 'active'
  | 'scenarios_ready'
  | 'draft_ready'
  | 'decision_saved'
  | 'decision_cancelled'

export type AssistantConversationListItem = {
  id: string
  event_id: string
  event_title: string
  event_category: string
  updated_at: string
  last_message_preview: string
  status: ConversationListStatus
  decision_id: string | null
  /** Null when no usable EventImpact — never treat as 0 */
  impact_score?: number | null
  confidence?: number | null
  has_impact_calculation?: boolean
  assessment_state?: string | null
  has_scenarios?: boolean
  is_demo?: boolean
}

export type PostMessageResult = {
  user_message: AssistantMessage
  assistant_message: AssistantMessage
  reused: boolean
  /** Jury-facing agent steps (also recoverable from bank_evidence diagnostics). */
  analysis_steps?: string[]
}

export type DraftDecisionResult = {
  status: 'draft' | 'confirmed'
  decision_id: string | null
  draft: Record<string, unknown>
  message: AssistantMessage | null
  disclaimer: string
}

export type UserCompareScenariosResult = {
  status: 'ok' | 'missing_data' | 'unavailable' | 'running'
  reused: boolean
  result: Record<string, unknown>
  message: AssistantMessage | null
  scenario_ids: string[]
  decision_created: boolean
  next_step?: string | null
  disclaimer: string
}
