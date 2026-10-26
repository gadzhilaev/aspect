/**
 * Pure helpers for discussing news without EventImpact (stage 3.4).
 * calculation_unavailable ≠ monitoring_only; unknown scores must not become 0.
 */

export type AssessmentStateLike =
  | 'supply_chain_ready'
  | 'finance_ready'
  | 'finance_data_required'
  | 'monitoring_only'
  | 'calculation_unavailable'
  | string
  | null
  | undefined

export type ConversationListLike = {
  status: string
  decision_id?: string | null
  has_scenarios?: boolean
  impact_score?: number | null
  confidence?: number | null
  has_impact_calculation?: boolean
  assessment_state?: AssessmentStateLike
}

export type UiConversationStatus = 'action' | 'watch' | 'done' | 'cancelled'

export function isCalculationUnavailable(state: AssessmentStateLike): boolean {
  return state === 'calculation_unavailable'
}

/** Prefer explicit flag; fall back to assessment_state. */
export function hasImpactCalculation(opts: {
  has_impact_calculation?: boolean | null
  assessment_state?: AssessmentStateLike
}): boolean {
  if (typeof opts.has_impact_calculation === 'boolean') {
    return opts.has_impact_calculation
  }
  return !isCalculationUnavailable(opts.assessment_state)
}

/** Active numeric scenario / decision CTAs require a real calculation. */
export function canShowCalculationActions(opts: {
  has_impact_calculation?: boolean | null
  assessment_state?: AssessmentStateLike
}): boolean {
  if (isCalculationUnavailable(opts.assessment_state)) return false
  return hasImpactCalculation(opts)
}

export function discussPath(eventId: string): string {
  return `/events/${encodeURIComponent(eventId)}/assistant`
}

export function newsPath(eventId: string): string {
  return `/news/${encodeURIComponent(eventId)}`
}

/**
 * List-row status. Chat alone never becomes «Решение принято».
 * High impact_score alone does not imply an action plan.
 */
export function conversationUiStatus(item: ConversationListLike): UiConversationStatus {
  if (item.status === 'decision_cancelled') return 'cancelled'
  if (item.status === 'decision_saved' && item.decision_id) return 'done'
  if (
    item.status === 'scenarios_ready' ||
    item.status === 'draft_ready' ||
    item.has_scenarios === true
  ) {
    return 'action'
  }
  return 'watch'
}

export function conversationUiStatusLabel(status: UiConversationStatus): string {
  if (status === 'cancelled') return 'План отменён'
  if (status === 'done') return 'Решение принято'
  if (status === 'action') return 'Нужны действия'
  return 'На контроле'
}

/** Show score/confidence only when a calculation exists and the value is a finite number. */
export function displayMetricNumber(
  value: number | null | undefined,
  opts: { hasCalculation: boolean },
): number | null {
  if (!opts.hasCalculation) return null
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return value
}

export type ImpactSummaryData = {
  impact_score?: unknown
  confidence?: unknown
  reason_summary?: unknown
  score_kind?: unknown
  metric_labels?: Record<string, string>
  assessment_state?: AssessmentStateLike
}

export type ImpactSummaryView =
  | {
      kind: 'scores'
      score: number
      confidencePct: number
      reason: string
      scoreName: string
      scoreHint: string
    }
  | {
      kind: 'unavailable'
      reason: string
      title: string
    }

/**
 * Map impact_summary block data. Known 0 stays 0; missing/null is not coerced to 0.
 */
export function impactSummaryView(data: ImpactSummaryData): ImpactSummaryView {
  const reason = String(data.reason_summary ?? '').trim()
  if (isCalculationUnavailable(data.assessment_state)) {
    return {
      kind: 'unavailable',
      title: 'Расчётная оценка пока недоступна',
      reason:
        reason ||
        'Событие можно обсудить по доступным данным компании и материалам банка. Отсутствие расчёта не означает, что риска нет.',
    }
  }
  const rawScore = data.impact_score
  const rawConf = data.confidence
  const hasScore = typeof rawScore === 'number' && Number.isFinite(rawScore)
  const hasConf = typeof rawConf === 'number' && Number.isFinite(rawConf)
  if (!hasScore) {
    return {
      kind: 'unavailable',
      title: 'Расчётная оценка пока недоступна',
      reason:
        reason ||
        'Численный индекс влияния в этом сообщении отсутствует.',
    }
  }
  const score = Math.round(rawScore)
  const confidencePct = hasConf ? Math.round(rawConf * 100) : 0
  const scoreKind = typeof data.score_kind === 'string' ? data.score_kind : null
  const scoreName =
    data.metric_labels?.impact_score ||
    (scoreKind === 'event_severity_signal' ? 'Сигнал события' : 'Индекс влияния')
  const scoreHint =
    scoreKind === 'event_severity_signal'
      ? `${scoreName} ${score} из 100 — предварительный ориентир по severity, не персональный расчёт.`
      : `${scoreName} ${score} из 100 — приоритет разбора, не процент потерь.`
  return {
    kind: 'scores',
    score,
    confidencePct,
    reason,
    scoreName,
    scoreHint,
  }
}

export function toolUnavailableUserMessage(data: Record<string, unknown>): string {
  const explicit = typeof data.message === 'string' ? data.message.trim() : ''
  if (explicit) return explicit
  const reason = data.unavailable_reason ?? data.assessment_state
  if (reason === 'calculation_unavailable' || data.type === 'tool_unavailable') {
    return (
      'Расчётная оценка пока недоступна. Численные сценарии и решение из расчёта ' +
      'сейчас создать нельзя — можно обсудить событие и данные компании.'
    )
  }
  return 'Это действие сейчас недоступно.'
}

export function isToolUnavailableBlock(data: Record<string, unknown>): boolean {
  return (
    data.type === 'tool_unavailable' ||
    data.unavailable_reason === 'calculation_unavailable' ||
    data.assessment_state === 'calculation_unavailable'
  )
}

export function draftDecisionErrorMessage(err: {
  status?: number
  code?: string
  message?: string
}): string {
  if (err.code === 'CALCULATION_UNAVAILABLE' || err.status === 409) {
    return (
      'Расчётная оценка пока недоступна — подтвердить расчётный сценарий или создать ' +
      'решение из него нельзя.'
    )
  }
  return err.message || 'Не удалось выполнить действие'
}

export function assistantOpenErrorMessage(err: {
  status?: number
  code?: string
  message?: string
}): string {
  if (err.status === 401) return 'Сессия истекла. Войдите снова, чтобы открыть обсуждение.'
  if (err.status === 403) return 'Нет доступа к этой компании или обсуждению.'
  if (err.status === 404) return 'Событие или обсуждение не найдено.'
  return err.message || 'Не удалось открыть обсуждение'
}

/** Copy for the analysis aside when impact is absent. */
export const CALCULATION_UNAVAILABLE_ASIDE = {
  title: 'Расчётная оценка пока недоступна',
  lead:
    'Персональный индекс влияния и уверенность для этой компании по событию ещё не посчитаны.',
  points: [
    'Событие можно обсудить по доступным данным компании и материалам банка.',
    'Это не режим «только мониторинг» и не означает, что риска нет или что событие безопасно.',
    'Численные сценарии и решение из расчёта появятся после появления оценки.',
  ],
} as const
