import { apiRequest, ApiError } from './client'
import type {
  BankDocumentDetail,
  BankFragmentDetail,
  EventBankEvidence,
} from './bankMaterialsTypes'
import type {
  AssistantConversation,
  AssistantConversationListItem,
  AssistantMessage,
  DraftDecisionResult,
  PostMessageResult,
  UserCompareScenariosResult,
} from './assistantTypes'
import type {
  ActionItemPatchResult,
  ActionItemStatus,
  DecisionDetail,
} from './decisionTypes'
import { companyContextFromProfile } from '../lib/companyContextFromProfile'
import type {
  CompanyContext,
  CompanyCreateIn,
  CompanyEdge,
  CompanyNode,
  CompanyPatchIn,
  CompanyProfile,
  CompanySummary,
  Dashboard,
  DigitalTwinBuildResult,
  EdgeCreateIn,
  EventDetail,
  EventRelevance,
  Impact,
  Industry,
  IndustryProfile,
  NodeCreateIn,
  NodePatchIn,
  RegistryConfirmResult,
  RegistryLookupResult,
  PublicCategory,
  PublicIngestionStatus,
  PublicNewsDetail,
  PublicNewsPage,
  PublicTrending,
  TokenPair,
  User,
} from './types'

export const authApi = {
  login(email: string, password: string) {
    return apiRequest<TokenPair>('/api/v1/auth/login', {
      method: 'POST',
      body: { email, password },
      auth: false,
    })
  },
  register(email: string, password: string, display_name: string) {
    return apiRequest<{ message: string; details?: { demo_code?: string } }>(
      '/api/v1/auth/register',
      {
        method: 'POST',
        body: { email, password, display_name },
        auth: false,
      },
    )
  },
  verifyEmail(email: string, code: string) {
    return apiRequest<{ message: string }>('/api/v1/auth/verify-email', {
      method: 'POST',
      body: { email, code },
      auth: false,
    })
  },
  me() {
    return apiRequest<User>('/api/v1/users/me')
  },
  preferences(body: NonNullable<User['preferences']>) {
    return apiRequest<User>('/api/v1/users/me/preferences', { method: 'PATCH', body })
  },
  changePassword(current_password: string, new_password: string) {
    return apiRequest<{ message: string }>('/api/v1/users/me/change-password', {
      method: 'POST', body: { current_password, new_password }, retry: false,
    })
  },
  deleteAccount(password: string) {
    return apiRequest<{ message: string }>('/api/v1/users/me', {
      method: 'DELETE', body: { password }, retry: false,
    })
  },
}

export const publicApi = {
  news(params?: { category?: string; event_type?: string; cursor?: string; limit?: number }) {
    const q = new URLSearchParams()
    if (params?.category) q.set('category', params.category)
    if (params?.event_type) q.set('event_type', params.event_type)
    if (params?.cursor) q.set('cursor', params.cursor)
    if (params?.limit) q.set('limit', String(params.limit))
    const qs = q.toString()
    return apiRequest<PublicNewsPage>(`/api/v1/public/news${qs ? `?${qs}` : ''}`, {
      auth: false,
    })
  },
  newsDetail(eventId: string) {
    return apiRequest<PublicNewsDetail>(`/api/v1/public/news/${eventId}`, { auth: false })
  },
  ingestionStatus() {
    return apiRequest<PublicIngestionStatus>('/api/v1/public/ingestion-status', {
      auth: false,
    })
  },
  categories() {
    return apiRequest<PublicCategory[]>('/api/v1/public/categories', { auth: false })
  },
  trending() {
    return apiRequest<PublicTrending>('/api/v1/public/trending', { auth: false })
  },
}

export const companyApi = {
  industryProfile(companyId: string) {
    return apiRequest<IndustryProfile>(`/api/v1/companies/${encodeURIComponent(companyId)}/industry-profile`)
  },
  patchIndustryProfile(companyId: string, body: Partial<IndustryProfile>) {
    return apiRequest<IndustryProfile>(`/api/v1/companies/${encodeURIComponent(companyId)}/industry-profile`, { method: 'PATCH', body })
  },
  industries() {
    return apiRequest<Industry[]>('/api/v1/industries')
  },
  create(body: CompanyCreateIn) {
    return apiRequest<CompanySummary>('/api/v1/companies', {
      method: 'POST',
      body,
    })
  },
  profile(companyId: string) {
    return apiRequest<CompanyProfile>(`/api/v1/companies/${companyId}/profile`)
  },
  async context(companyId: string) {
    try {
      return await apiRequest<CompanyContext>(`/api/v1/companies/${companyId}/context`)
    } catch (err) {
      // Stale local API without /context — fall back to profile projection.
      if (err instanceof ApiError && (err.status === 404 || err.code === 'NOT_FOUND')) {
        const profile = await apiRequest<CompanyProfile>(
          `/api/v1/companies/${companyId}/profile`,
        )
        return companyContextFromProfile(profile)
      }
      throw err
    }
  },
  patch(companyId: string, body: CompanyPatchIn) {
    return apiRequest<CompanySummary>(`/api/v1/companies/${companyId}`, {
      method: 'PATCH',
      body,
    })
  },
  addNode(companyId: string, body: NodeCreateIn) {
    return apiRequest<CompanyNode>(`/api/v1/companies/${companyId}/nodes`, {
      method: 'POST',
      body,
    })
  },
  patchNode(companyId: string, nodeId: string, body: NodePatchIn) {
    return apiRequest<CompanyNode>(`/api/v1/companies/${companyId}/nodes/${nodeId}`, {
      method: 'PATCH',
      body,
    })
  },
  addEdge(companyId: string, body: EdgeCreateIn) {
    return apiRequest<CompanyEdge>(`/api/v1/companies/${companyId}/edges`, {
      method: 'POST',
      body,
    })
  },
  completeProfile(companyId: string) {
    return apiRequest<CompanyProfile>(`/api/v1/companies/${companyId}/profile/complete`, {
      method: 'POST',
    })
  },
  buildDigitalTwin(companyId: string) {
    return apiRequest<DigitalTwinBuildResult>(
      `/api/v1/companies/${companyId}/digital-twin/build`,
      { method: 'POST' },
    )
  },
  dashboard(companyId: string) {
    return apiRequest<Dashboard>(`/api/v1/companies/${companyId}/dashboard`)
  },
  patchFinance(
    companyId: string,
    body: { purchase_currencies: string[]; optional_finance: Record<string, unknown> },
  ) {
    return apiRequest<{ message: string }>(`/api/v1/companies/${companyId}/finance`, {
      method: 'PATCH',
      body,
    })
  },
  /**
   * Look up public requisites of a REAL company by INN via the external registry.
   * Takes only an INN (not a URL). Creates nothing — returns candidates + a
   * short-lived lookup_id used to confirm. Never call per keystroke.
   */
  registryLookup(inn: string) {
    return apiRequest<RegistryLookupResult>('/api/v1/company-registry/lookup', {
      method: 'POST',
      body: { inn },
    })
  },
  /**
   * Confirm a chosen candidate from a prior lookup. The server trusts the
   * registry origin via lookup_id — the client cannot forge "from registry".
   * Creates the user's OWN working profile (or opens an existing own one).
   */
  registryConfirm(lookupId: string, candidateId: string) {
    return apiRequest<RegistryConfirmResult>('/api/v1/company-registry/confirm', {
      method: 'POST',
      body: { lookup_id: lookupId, candidate_id: candidateId },
    })
  },
}

export const eventsApi = {
  detail(eventId: string, companyId: string) {
    return apiRequest<EventDetail>(
      `/api/v1/events/${eventId}?company_id=${encodeURIComponent(companyId)}`,
    )
  },
  impact(eventId: string, companyId: string) {
    return apiRequest<Impact>(
      `/api/v1/events/${eventId}/impact?company_id=${encodeURIComponent(companyId)}`,
    )
  },
  relevance(eventId: string, companyId: string) {
    return apiRequest<EventRelevance>(
      `/api/v1/events/${eventId}/relevance?company_id=${encodeURIComponent(companyId)}`,
    )
  },
  /** Explicit Impact create/refresh — not called by GET. */
  recomputeImpact(eventId: string, companyId: string) {
    return apiRequest<Impact>(
      `/api/v1/events/${eventId}/recompute-impact?company_id=${encodeURIComponent(companyId)}`,
      { method: 'POST' },
    )
  },
  /**
   * Thematic bank evidence for a news event (Bearer required).
   * Optional company_id is ACL-only — not used for matching.
   */
  bankEvidence(eventId: string, companyId?: string | null) {
    const q =
      companyId != null && companyId !== ''
        ? `?company_id=${encodeURIComponent(companyId)}`
        : ''
    return apiRequest<EventBankEvidence>(
      `/api/v1/events/${encodeURIComponent(eventId)}/bank-evidence${q}`,
    )
  },
}

export type AgentDemoEntry = {
  enabled: boolean
  synthetic_notice: string
  prior_answer_notice: string
  event_id: string
  event_title: string
  is_demo: boolean
  company_id: string
  company_name: string
  conversation_id: string | null
  news_path: string
  assistant_path: string
  scenarios_path: string
  public_news_path: string
}

export const agentDemoApi = {
  entry() {
    return apiRequest<AgentDemoEntry>('/api/v1/agent-demo/entry')
  },
}

export const assistantApi = {
  conversations(companyId: string) {
    return apiRequest<AssistantConversationListItem[]>(
      `/api/v1/assistant/conversations?company_id=${encodeURIComponent(companyId)}`,
    )
  },
  openConversation(eventId: string, companyId: string) {
    return apiRequest<AssistantConversation>(
      `/api/v1/events/${eventId}/assistant/conversations`,
      { method: 'POST', body: { company_id: companyId } },
    )
  },
  getConversation(conversationId: string) {
    return apiRequest<AssistantConversation>(`/api/v1/assistant/conversations/${conversationId}`)
  },
  messages(conversationId: string) {
    return apiRequest<AssistantMessage[]>(
      `/api/v1/assistant/conversations/${conversationId}/messages`,
    )
  },
  postMessage(conversationId: string, content: string, clientMessageId?: string) {
    return apiRequest<PostMessageResult>(
      `/api/v1/assistant/conversations/${conversationId}/messages`,
      {
        method: 'POST',
        body: { content, client_message_id: clientMessageId ?? null },
      },
    )
  },
  draftDecision(
    conversationId: string,
    body: {
      scenario_id?: string | null
      solution_id?: string | null
      note?: string | null
      confirm?: boolean
      client_request_id?: string | null
    },
  ) {
    return apiRequest<DraftDecisionResult>(
      `/api/v1/assistant/conversations/${conversationId}/draft-decision`,
      { method: 'POST', body },
    )
  },
  /** User-triggered scenario calc — no LLM. Stage 6.6. */
  compareScenarios(
    conversationId: string,
    body: {
      client_request_id: string
      assumed_rate_change_pp?: number | null
      assumed_fx_change_percent?: number | null
      inventory_days?: number
      delay_days?: number
    },
  ) {
    return apiRequest<UserCompareScenariosResult>(
      `/api/v1/assistant/conversations/${conversationId}/compare-scenarios`,
      { method: 'POST', body },
    )
  },
}

export const bankMaterialsApi = {
  document(documentId: string) {
    return apiRequest<BankDocumentDetail>(
      `/api/v1/bank-materials/documents/${encodeURIComponent(documentId)}`,
    )
  },
  fragment(fragmentId: string) {
    return apiRequest<BankFragmentDetail>(
      `/api/v1/bank-materials/fragments/${encodeURIComponent(fragmentId)}`,
    )
  },
}

export type TelegramPrivateSettings = {
  id: string | null
  company_id?: string | null
  company_name?: string | null
  status: string
  status_label: string
  linked: boolean
  notifications_enabled: boolean
  chat_bound?: boolean
  chat_title?: string | null
  is_active?: boolean
  verified_at?: string | null
}

export type NotificationSettings = {
  company_id: string
  company_name?: string | null
  scope_note?: string
  news_policy_note?: string
  news_notifications_server_enabled?: boolean
  telegram_private: TelegramPrivateSettings
  telegram_group?: TelegramPrivateSettings
}

export type TelegramLinkTokenResult = {
  token: string
  deep_link: string
  expires_at: string
  company_id?: string
  instructions?: string
}

export type TelegramTestSendResult = {
  ok: boolean
  queued?: boolean
  idempotent_replay?: boolean
  outbox_id?: string
  status?: string
  delivery?: string
  message?: string
}

export type TelegramOutboxStatus = {
  outbox_id: string
  status: string
  kind?: string
  attempts?: number
  delivery?: string
  message?: string
}

export const notificationsApi = {
  settings(companyId: string) {
    return apiRequest<NotificationSettings>(
      `/api/v1/companies/${encodeURIComponent(companyId)}/notification-settings`,
    )
  },
  linkToken(companyId: string) {
    return apiRequest<TelegramLinkTokenResult>('/api/v1/telegram/link-token', {
      method: 'POST',
      body: { company_id: companyId },
    })
  },
  testSend(companyId: string, clientRequestId: string) {
    return apiRequest<TelegramTestSendResult>('/api/v1/telegram/test-send', {
      method: 'POST',
      body: { company_id: companyId, client_request_id: clientRequestId },
    })
  },
  outboxStatus(outboxId: string) {
    return apiRequest<TelegramOutboxStatus>(
      `/api/v1/telegram/outbox/${encodeURIComponent(outboxId)}`,
    )
  },
  patchSubscription(
    subscriptionId: string,
    body: { is_active?: boolean; min_severity?: string },
  ) {
    return apiRequest<TelegramPrivateSettings>(
      `/api/v1/notification-subscriptions/${encodeURIComponent(subscriptionId)}`,
      { method: 'PATCH', body },
    )
  },
  unlink(subscriptionId: string) {
    return apiRequest<{ message: string; operation?: string }>(
      `/api/v1/notification-subscriptions/${encodeURIComponent(subscriptionId)}`,
      { method: 'DELETE' },
    )
  },
}

export type SupportMessage = {
  id: string
  role: 'user' | 'support' | 'system' | 'operator'
  content: string
  client_message_id?: string | null
  created_at: string
}

export type SupportThread = {
  id: string
  status: 'open' | 'closed' | 'waiting_operator' | 'with_operator'
  handler?: 'ai' | 'operator'
  subject?: string | null
  company_id?: string | null
  ticket?: string | null
  created_at: string
  updated_at: string
  messages: SupportMessage[]
}

export type SupportPostResult = {
  user_message: SupportMessage
  support_message: SupportMessage | null
  reused: boolean
}

export const supportApi = {
  getThread(companyId?: string) {
    const q = companyId ? `?company_id=${encodeURIComponent(companyId)}` : ''
    return apiRequest<SupportThread>(`/api/v1/support/thread${q}`)
  },
  listMessages(afterId?: string) {
    const q = afterId ? `?after_id=${encodeURIComponent(afterId)}` : ''
    return apiRequest<SupportMessage[]>(`/api/v1/support/thread/messages${q}`)
  },
  postMessage(body: {
    content: string
    client_message_id?: string
    company_id?: string
  }) {
    return apiRequest<SupportPostResult>('/api/v1/support/thread/messages', {
      method: 'POST',
      body,
    })
  },
  closeThread() {
    return apiRequest<SupportThread>('/api/v1/support/thread/close', {
      method: 'POST',
      body: {},
    })
  },
}

export const decisionsApi = {
  get(decisionId: string) {
    return apiRequest<DecisionDetail>(`/api/v1/decisions/${decisionId}`)
  },
  forEvent(eventId: string, companyId: string) {
    return apiRequest<DecisionDetail>(
      `/api/v1/events/${eventId}/decision?company_id=${encodeURIComponent(companyId)}`,
    )
  },
  cancel(decisionId: string, body?: { reason?: string | null }) {
    return apiRequest<DecisionDetail>(`/api/v1/decisions/${decisionId}/cancel`, {
      method: 'POST',
      body: body ?? {},
    })
  },
  patchActionItem(actionItemId: string, body: { status?: ActionItemStatus }) {
    return apiRequest<ActionItemPatchResult>(`/api/v1/action-items/${actionItemId}`, {
      method: 'PATCH',
      body,
    })
  },
}
