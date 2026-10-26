/** Typed scenario metrics for assistant / impact UI — never render None/null/NaN. */

import {
  isFinanceScenarioRow,
  presentFinanceScenario,
} from './financeScenarioPresentation'

export type AssessmentState =
  | 'supply_chain_ready'
  | 'finance_ready'
  | 'finance_data_required'
  | 'monitoring_only'
  | string

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export function scenarioLabel(sc: Record<string, unknown>, index: number): string {
  const alt = asRecord(sc.alternative)
  const base = asRecord(sc.baseline)
  const candidates = [
    sc.solution_name,
    sc.label,
    alt?.label,
    alt?.name,
    base?.label,
    base?.name,
  ]
  for (const c of candidates) {
    if (typeof c === 'string' && c.trim()) return c.trim()
  }
  if (sc.kind === 'baseline') return 'Без действий'
  return `Сценарий ${index + 1}`
}

export function isFinanceScenario(
  sc: Record<string, unknown>,
  assessmentState?: string | null,
  source?: string | null,
): boolean {
  return isFinanceScenarioRow(sc, assessmentState, source)
}

function stopRisk(sc: Record<string, unknown>): number | null {
  const alt = asRecord(sc.alternative)
  const base = asRecord(sc.baseline)
  for (const bag of [alt, sc, base]) {
    if (bag && isFiniteNumber(bag.stop_risk_percent)) return bag.stop_risk_percent
  }
  return null
}

function formatPct(value: number | null, digits = 1): string | null {
  if (value == null || !Number.isFinite(value)) return null
  const text = value.toFixed(digits).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')
  return `${text}%`
}

/**
 * Secondary metric fragment after the label, or null to hide the metric.
 * Finance rows use the unified 5.3 presentation adapter (not funding_pressure defaults).
 */
export function scenarioMetricSuffix(
  sc: Record<string, unknown>,
  assessmentState?: string | null,
  source?: string | null,
  parameters?: Record<string, unknown> | null,
): string | null {
  if (isFinanceScenario(sc, assessmentState, source)) {
    // Never resurrect disabled near-term / FX / funding from nulls
    if (
      sc.funding_pressure_status === 'unavailable_severity_proxy_removed' ||
      sc.near_term_pressure_status === 'unavailable_mixed_fx_deferred' ||
      sc.near_term_pressure_status === 'unavailable_not_severity_proxy' ||
      sc.near_term_pressure_status === 'unavailable_not_applicable_to_fx'
    ) {
      /* intentional: ignore legacy pressure fields */
    }
    const pres = presentFinanceScenario(sc, parameters ?? asRecord(sc.parameters))
    return pres.metric_suffix
  }
  const stop = formatPct(stopRisk(sc))
  if (stop) return `модельная оценка риска остановки ${stop}`
  const alt = asRecord(sc.alternative)
  const lead = sc.lead_time_days ?? alt?.lead_time_days
  if (isFiniteNumber(lead) && lead > 0) return `срок поставки ~${Math.round(lead)} дн.`
  return null
}

export { presentFinanceScenario } from './financeScenarioPresentation'

const TECH_EMPTY = /\b(None|null|undefined|NaN)\s*%?/gi

/** Clean historical assistant text that may contain None%. */
export function sanitizeDisplayText(text: string): string {
  if (!text) return text
  let out = text.replace(
    /риск остановки\s*(None|null|undefined|NaN)\s*%?/gi,
    'финансовый сценарий без риска остановки',
  )
  out = out.replace(TECH_EMPTY, '')
  out = out.replace(/\s{2,}/g, ' ')
  out = out.replace(/\s+([,.;:])/g, '$1')
  return out.trim()
}
