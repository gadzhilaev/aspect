/**
 * User-triggered finance / scenario calculation helpers (stage 6.6).
 * CTA calls POST …/compare-scenarios — never a hidden model message.
 */

export const FINANCE_CALC_CTA = 'Рассчитать финансовые сценарии'
export const FINANCE_RECALC_CTA = 'Рассчитать другой вариант'
export const SUPPLY_COMPARE_CTA = 'Сравнить сценарии'
export const SYSTEM_CALC_TITLE = 'Расчёт по вашему запросу'

export const MAX_ABS_RATE_CHANGE_PP = 20
export const MAX_ABS_FX_CHANGE_PERCENT = 100

/** Chips that must route to the compare API, not postMessage. */
export function isScenarioCalcChip(text: string): boolean {
  return /три сценари|финансов(ые|ых)? сценари|сравнить сценари|рассчитать финанс/i.test(
    text.trim(),
  )
}

export function parseOptionalNumber(raw: string): number | null {
  const t = raw.trim().replace(',', '.')
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

export type WhatIfValidation =
  | { ok: true; ratePp: number | null; fxPct: number | null }
  | { ok: false; notice: string }

/** Rate what-if is percentage points (п.п.); FX what-if is percent (%). */
export function validateWhatIfInputs(rateRaw: string, fxRaw: string): WhatIfValidation {
  const ratePp = parseOptionalNumber(rateRaw)
  const fxPct = parseOptionalNumber(fxRaw)
  if (rateRaw.trim() && ratePp === null) {
    return {
      ok: false,
      notice: 'Допущение по ставке: укажите число в процентных пунктах (п.п.), например 1.5',
    }
  }
  if (fxRaw.trim() && fxPct === null) {
    return {
      ok: false,
      notice: 'Допущение по курсу: укажите число в процентах (%), например 10',
    }
  }
  if (ratePp !== null && Math.abs(ratePp) > MAX_ABS_RATE_CHANGE_PP) {
    return {
      ok: false,
      notice: `Допущение по ставке: не больше ±${MAX_ABS_RATE_CHANGE_PP} п.п.`,
    }
  }
  if (fxPct !== null && Math.abs(fxPct) > MAX_ABS_FX_CHANGE_PERCENT) {
    return {
      ok: false,
      notice: `Допущение по курсу: не больше ±${MAX_ABS_FX_CHANGE_PERCENT} %`,
    }
  }
  return { ok: true, ratePp, fxPct }
}

export function buildCompareRequestBody(opts: {
  clientRequestId: string
  ratePp: number | null
  fxPct: number | null
}): {
  client_request_id: string
  assumed_rate_change_pp?: number | null
  assumed_fx_change_percent?: number | null
} {
  return {
    client_request_id: opts.clientRequestId,
    assumed_rate_change_pp: opts.ratePp,
    assumed_fx_change_percent: opts.fxPct,
  }
}

/** Endpoint for user-triggered calc — not /messages. */
export function compareScenariosPath(conversationId: string): string {
  return `/api/v1/assistant/conversations/${conversationId}/compare-scenarios`
}

export function isSystemCalcMessage(msg: {
  role?: string
  content?: string | null
}): boolean {
  return msg.role === 'system' && Boolean(msg.content?.includes(SYSTEM_CALC_TITLE))
}

/** Cleared on company/event switch so foreign results do not linger. */
export type ChatCalcResetState = {
  messages: unknown[]
  hasScenarios: boolean
  selectedScenarioId: string | null
  decisionId: string | null
  calculating: boolean
  whatIfRatePp: string
  whatIfFxPercent: string
  calcNotice: string | null
}

export function emptyCalcStateAfterCompanySwitch(): ChatCalcResetState {
  return {
    messages: [],
    hasScenarios: false,
    selectedScenarioId: null,
    decisionId: null,
    calculating: false,
    whatIfRatePp: '',
    whatIfFxPercent: '',
    calcNotice: null,
  }
}

export function unavailableNoticeFromResult(result: {
  status?: string
  result?: { message?: unknown }
  scenario_ids?: string[]
}): string | null {
  if (result.status === 'missing_data' || result.status === 'unavailable') {
    const msg = result.result?.message
    if (typeof msg === 'string' && msg.trim()) return msg
    return 'Расчёт сейчас недоступен — проверьте параметры или основание события.'
  }
  if (result.status === 'running') {
    return 'Расчёт уже выполняется — подождите немного и повторите.'
  }
  if (result.status === 'ok') {
    const n = result.scenario_ids?.length ?? 0
    if (n === 0) {
      return 'Готовых денежных сценариев нет — проверьте основание события или what-if.'
    }
  }
  return null
}

export function showFinanceCalcCta(opts: {
  calcActionsAllowed: boolean
  hasScenarios: boolean
  compact?: boolean
  assessmentState: string | null
}): boolean {
  // First calc: hide only when compact / not allowed. After scenarios, use recalc path.
  if (!opts.calcActionsAllowed || opts.hasScenarios || opts.compact) return false
  const s = opts.assessmentState
  return s === 'finance_ready' || s === 'finance_data_required'
}

/** Same conversation: change what-if / run another compare without losing prior results. */
export function showFinanceRecalcCta(opts: {
  calcActionsAllowed: boolean
  hasScenarios: boolean
  compact?: boolean
  confirmed?: boolean
  assessmentState: string | null
}): boolean {
  if (!opts.calcActionsAllowed || !opts.hasScenarios || opts.compact || opts.confirmed) {
    return false
  }
  const s = opts.assessmentState
  return s === 'finance_ready' || s === 'finance_data_required'
}

export function showSupplyCompareCta(opts: {
  calcActionsAllowed: boolean
  hasScenarios: boolean
  compact?: boolean
  assessmentState: string | null
}): boolean {
  if (!opts.calcActionsAllowed || opts.hasScenarios || opts.compact) return false
  return opts.assessmentState === 'supply_chain_ready'
}

/** Prefer baseline for auto-select; never invent selection of omitted FX hypothesis. */
export function pickDefaultScenarioId(
  scenarios: Array<Record<string, unknown>>,
  scenarioIds: string[],
): { scenarioId: string | null; solutionId: string | null } {
  const baseline = scenarios.find(
    (s) => s.kind === 'baseline' && typeof s.scenario_id === 'string' && s.scenario_id,
  )
  if (baseline && typeof baseline.scenario_id === 'string') {
    return {
      scenarioId: baseline.scenario_id,
      solutionId: baseline.solution_id ? String(baseline.solution_id) : null,
    }
  }
  const withId = scenarios.find((s) => typeof s.scenario_id === 'string' && s.scenario_id)
  if (withId && typeof withId.scenario_id === 'string') {
    return {
      scenarioId: withId.scenario_id,
      solutionId: withId.solution_id ? String(withId.solution_id) : null,
    }
  }
  if (scenarioIds[0]) return { scenarioId: scenarioIds[0], solutionId: null }
  return { scenarioId: null, solutionId: null }
}
