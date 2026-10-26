/**
 * Unified finance scenario presentation (stages 5.3–5.4).
 * Mirrors backend finance_scenario_presentation — do not invent basis from labels.
 * Rate and FX tracks use separate copy; never reuse п.п./annual labels for FX money.
 */

export type RatePresentBasis = 'observed' | 'assumed' | 'none' | 'conflict' | 'legacy'
export type PresentTrack = 'rate' | 'fx'

export type FinanceScenarioPresentation = {
  track: PresentTrack
  basis: RatePresentBasis
  legacy: boolean
  delta_pp: number | null
  annual_sensitivity: number | null
  money_period: 'annual' | null
  debt_amount_unit: string
  debt_unit_confirmed_rub: boolean
  fx_pair_line: string | null
  fx_amount_line: string | null
  fx_period_line: string | null
  fx_limitations_line: string | null
  fx_value_change: string | null
  fx_result_currency: string | null
  rate_fact_line: string | null
  what_if_line: string | null
  assumption_badge: string | null
  money_line: string | null
  hold_note: string | null
  unavailable_message: string | null
  historical_note: string | null
  model_version: string | null
  metric_suffix: string | null
  decision_reason: string | null
  decision_horizon: string | null
  expected_effect: string | null
  action_model_note: string | null
  credit_transfer_disclaimer: string | null
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function fmtPp(delta: number): string {
  return `${parseFloat(delta.toPrecision(12))}`
}

function fmtMoneyCcy(value: unknown, ccy: string | null | undefined): string | null {
  let n: number
  if (typeof value === 'number' && Number.isFinite(value)) n = value
  else if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) n = Number(value)
  else return null
  const body = n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const u = (ccy || '').trim().toUpperCase()
  if (!u || u === 'UNSPECIFIED' || u === 'UNKNOWN') return body
  if (u === 'RUB' || u === 'RUR' || u === '₽') return `${body} ₽`
  return `${body} ${u}`
}

export function formatDebtAmountDisplay(value: unknown, unit: string | null | undefined): string | null {
  if (!isFiniteNumber(value)) return null
  const n = value
  const u = (unit || 'unspecified').trim().toUpperCase()
  let body: string
  if (Math.abs(n) >= 1_000_000) {
    body = `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')} млн`
  } else if (Math.abs(n) >= 1_000) {
    body = `${(n / 1_000).toFixed(1).replace(/\.0$/, '')} тыс.`
  } else {
    body = `${Math.round(n)}`
  }
  if (!u || u === 'UNSPECIFIED' || u === 'UNKNOWN') {
    return `${body} (единицы введённой суммы долга)`
  }
  if (u === 'RUB' || u === 'RUR' || u === '₽') return `${body} ₽`
  return `${body} ${u}`
}

function legacyMeta(parameters: Record<string, unknown> | null): {
  basis: RatePresentBasis
  meta: Record<string, unknown>
} {
  if (parameters && parameters.shock_proxy_pp != null) {
    return {
      basis: 'legacy',
      meta: {
        legacy: true,
        shock_proxy_pp: parameters.shock_proxy_pp,
        source: 'legacy_shock_proxy_pp',
      },
    }
  }
  return {
    basis: 'legacy',
    meta: { legacy: true, source: 'legacy_missing' },
  }
}

function isFxRow(
  results: Record<string, unknown>,
  parameters: Record<string, unknown>,
): boolean {
  if (results.track === 'fx' || parameters.track === 'fx') return true
  if (results.fx_change_basis != null) return true
  if (results.fx_value_change != null) return true
  return false
}

export function resolvePresentBasis(
  results: Record<string, unknown> | null | undefined,
  parameters: Record<string, unknown> | null | undefined,
): { basis: RatePresentBasis; meta: Record<string, unknown> } {
  const res = results ?? {}
  const params = parameters ?? {}
  const raw = res.rate_change_basis
  if (
    typeof raw === 'string' &&
    ['observed', 'assumed', 'none', 'conflict'].includes(raw.trim())
  ) {
    const rc = asRecord(params.rate_change) ?? {}
    return { basis: raw.trim() as RatePresentBasis, meta: rc }
  }
  const rc = asRecord(params.rate_change)
  if (rc && typeof rc.basis === 'string' && ['observed', 'assumed', 'none', 'conflict'].includes(rc.basis)) {
    return { basis: rc.basis as RatePresentBasis, meta: rc }
  }
  if (
    res.extra_annual_cost != null ||
    res.annual_rate_sensitivity != null ||
    res.funding_pressure_percent != null ||
    params.kind === 'financial' ||
    params.shock_proxy_pp != null
  ) {
    return legacyMeta(params)
  }
  return { basis: 'none', meta: {} }
}

export function resolveFxPresentBasis(
  results: Record<string, unknown>,
  parameters: Record<string, unknown>,
): { basis: RatePresentBasis; meta: Record<string, unknown> } {
  const raw = results.fx_change_basis
  if (
    typeof raw === 'string' &&
    ['observed', 'assumed', 'none', 'conflict'].includes(raw.trim())
  ) {
    return { basis: raw.trim() as RatePresentBasis, meta: asRecord(parameters.fx_change) ?? {} }
  }
  const fc = asRecord(parameters.fx_change)
  if (fc && typeof fc.basis === 'string' && ['observed', 'assumed', 'none', 'conflict'].includes(fc.basis)) {
    return { basis: fc.basis as RatePresentBasis, meta: fc }
  }
  if (parameters.shock_proxy_pp != null || parameters.fx_purchase_volume != null) {
    return {
      basis: 'legacy',
      meta: { legacy: true, source: 'legacy_fx_or_severity_proxy' },
    }
  }
  return { basis: 'none', meta: {} }
}

function deltaPp(results: Record<string, unknown>, meta: Record<string, unknown>): number | null {
  for (const bag of [results, meta]) {
    for (const key of ['rate_change_delta_pp', 'used_delta_pp', 'delta_pp', 'observed_delta_pp']) {
      if (isFiniteNumber(bag[key])) return bag[key]
    }
  }
  return null
}

function annualOf(results: Record<string, unknown>): number | null {
  if (isFiniteNumber(results.annual_rate_sensitivity)) return results.annual_rate_sensitivity
  if (isFiniteNumber(results.extra_annual_cost)) return results.extra_annual_cost
  return null
}

function debtUnit(results: Record<string, unknown>, parameters: Record<string, unknown>): string {
  for (const bag of [results, parameters]) {
    const raw = bag.debt_amount_unit ?? bag.debt_currency
    if (typeof raw === 'string' && raw.trim()) return raw.trim()
  }
  return 'unspecified'
}

function presentFxScenario(
  sc: Record<string, unknown>,
  params: Record<string, unknown>,
  version: string | null,
): FinanceScenarioPresentation {
  const { basis, meta } = resolveFxPresentBasis(sc, params)
  const expCcy = typeof sc.fx_exposure_currency === 'string' ? sc.fx_exposure_currency : null
  const quoteCcy =
    (typeof sc.fx_quote_currency === 'string' ? sc.fx_quote_currency : null) ??
    (typeof sc.fx_result_currency === 'string' ? sc.fx_result_currency : null)
  const amount = sc.fx_exposure_amount
  const direction = sc.fx_exposure_direction
  const rateFrom = sc.fx_rate_from
  const rateTo = sc.fx_rate_to
  let valueChange: unknown = sc.fx_value_change
  const meaningLabel =
    typeof sc.fx_value_change_meaning_label === 'string' ? sc.fx_value_change_meaning_label : null
  let periodLabel =
    typeof sc.fx_period_label === 'string' && sc.fx_period_label.trim()
      ? sc.fx_period_label
      : typeof sc.fx_period === 'string' && sc.fx_period.trim()
        ? sc.fx_period
        : 'Период не указан'

  const pair_line =
    expCcy && quoteCcy
      ? `Пара ${quoteCcy}/${expCcy}: единиц ${quoteCcy} за 1 ${expCcy} (quote_per_exposure)`
      : null

  let rate_fact_line: string | null = null
  let what_if_line: string | null = null
  let assumption_badge: string | null = null
  let money_line: string | null = null
  let unavailable_message: string | null = null
  let historical_note: string | null = null

  if (basis === 'conflict') {
    unavailable_message = 'Исходные данные о курсе противоречат друг другу'
    valueChange = null
  } else if (basis === 'none') {
    unavailable_message = 'Недостаточно данных для FX-расчёта'
    valueChange = null
  } else if (basis === 'legacy') {
    historical_note = 'Историческая FX/severity-оценка; не является observed курсом'
    assumption_badge = 'Допущение прежней модели'
    valueChange = null
  } else if (basis === 'assumed') {
    assumption_badge = 'Допущение сценария'
    const pct = meta.assumed_change_percent ?? sc.assumed_fx_change_percent
    what_if_line =
      pct != null ? `Что если курс изменится на ${pct}%` : 'What-if изменения курса (допущение сценария)'
    if (rateFrom != null && rateTo != null) {
      what_if_line = `${what_if_line}: ${rateFrom} → ${rateTo} ${quoteCcy || ''}/${expCcy || ''}`.trim()
    }
  } else if (basis === 'observed') {
    rate_fact_line =
      rateFrom != null && rateTo != null
        ? `Курс ${quoteCcy || '?'}/${expCcy || '?'}: ${rateFrom} → ${rateTo}`
        : 'Observed изменение курса учтено'
  }

  let amount_line: string | null = null
  if (amount != null && expCcy) {
    const dirRu =
      direction === 'payment' ? 'платёж' : direction === 'receipt' ? 'поступление' : 'экспозиция'
    amount_line = `Сумма (${dirRu}): ${amount} ${expCcy}`
  }

  if ((basis === 'observed' || basis === 'assumed') && valueChange != null) {
    const money = fmtMoneyCcy(valueChange, quoteCcy)
    if (money) money_line = `${meaningLabel || 'Изменение эквивалента'}: ${money}`
  }

  const period_line = `Период: ${periodLabel}`
  const suffixParts = [
    assumption_badge,
    pair_line,
    rate_fact_line,
    what_if_line,
    amount_line,
    money_line,
    money_line || unavailable_message ? period_line : null,
    unavailable_message,
    basis === 'legacy' ? historical_note : null,
  ].filter((x): x is string => Boolean(x && x.trim()))

  return {
    track: 'fx',
    basis,
    legacy: basis === 'legacy',
    delta_pp: null,
    annual_sensitivity: null,
    money_period: null,
    debt_amount_unit: 'n/a',
    debt_unit_confirmed_rub: false,
    fx_pair_line: pair_line,
    fx_amount_line: amount_line,
    fx_period_line: period_line,
    fx_limitations_line: null,
    fx_value_change: valueChange != null ? String(valueChange) : null,
    fx_result_currency: quoteCcy,
    rate_fact_line,
    what_if_line,
    assumption_badge,
    money_line,
    hold_note: null,
    unavailable_message,
    historical_note,
    model_version: version,
    metric_suffix: suffixParts.length ? suffixParts.join(' · ') : null,
    decision_reason: null,
    decision_horizon: money_line ? period_line : null,
    expected_effect: money_line || unavailable_message || historical_note,
    action_model_note: null,
    credit_transfer_disclaimer:
      basis === 'observed' && money_line
        ? 'Observed рыночный курс не является доказанным курсом исполнения договора'
        : null,
  }
}

/** Prefer server presentation when present; otherwise build locally from fields. */
export function presentFinanceScenario(
  sc: Record<string, unknown>,
  parameters?: Record<string, unknown> | null,
  modelVersion?: string | null,
): FinanceScenarioPresentation {
  const embedded = asRecord(sc.presentation)
  if (embedded && typeof embedded.basis === 'string') {
    return normalizePresentation(embedded)
  }

  const params =
    parameters ??
    asRecord(sc.parameters) ??
    {}
  const version =
    modelVersion ??
    (typeof sc.model_version === 'string'
      ? sc.model_version
      : typeof params.model_version === 'string'
        ? params.model_version
        : null)

  if (isFxRow(sc, params)) {
    return presentFxScenario(sc, params, version)
  }

  const { basis, meta } = resolvePresentBasis(sc, params)
  const delta = deltaPp(sc, meta)
  let annual = annualOf(sc)
  const unit = debtUnit(sc, params)
  const rubConfirmed = ['RUB', 'RUR', '₽'].includes(unit.trim().toUpperCase())

  let rate_fact_line: string | null = null
  let what_if_line: string | null = null
  let assumption_badge: string | null = null
  let money_line: string | null = null
  let unavailable_message: string | null = null
  let historical_note: string | null = null
  let hold_note: string | null = null

  if (basis === 'conflict') {
    unavailable_message = 'Исходные данные о ставке противоречат друг другу'
    annual = null
  } else if (basis === 'none') {
    unavailable_message = 'Недостаточно данных для расчёта изменения расходов'
    annual = null
  } else if (basis === 'legacy') {
    historical_note =
      meta.shock_proxy_pp != null
        ? 'Историческая оценка прежней модели (shock_proxy_pp); не является observed изменением ставки'
        : 'Историческая оценка: основание расчёта не сохранено'
    if (meta.shock_proxy_pp != null) assumption_badge = 'Допущение прежней модели'
    if (isFiniteNumber(annual)) {
      const money = formatDebtAmountDisplay(annual, 'unspecified')
      if (money) money_line = `Историческая условная оценка ~${money}`
    }
  } else if (basis === 'assumed') {
    assumption_badge = 'Допущение сценария'
    what_if_line =
      delta != null
        ? `Что если ставка изменится на ${fmtPp(delta)} п.п.`
        : 'Что если ставка изменится (величина не сохранена)'
    if (isFiniteNumber(annual)) {
      const money = formatDebtAmountDisplay(annual, unit)
      if (money) {
        if (annual < 0) money_line = `Снижение условной годовой нагрузки ~${money}`
        else if (annual === 0) {
          money_line = `Условная годовая чувствительность 0 (${money}) — нет эффекта от изменения ставки в этой модели`
        } else {
          money_line = `Условная годовая чувствительность при переносе изменения на плавающую часть долга ~${money}`
        }
      }
    }
  } else if (basis === 'observed') {
    if (delta != null && Math.abs(delta) < 1e-12) {
      rate_fact_line = 'Ключевая ставка не изменилась'
      hold_note =
        'Нулевой rate-результат означает отсутствие эффекта именно от изменения ставки в этой модели, а не отсутствие всех финансовых рисков'
    } else if (delta != null) {
      rate_fact_line = `Ключевая ставка изменилась на ${fmtPp(delta)} п.п.`
    } else {
      rate_fact_line = 'Ключевая ставка: observed-изменение учтено'
    }
    if (isFiniteNumber(annual)) {
      const money = formatDebtAmountDisplay(annual, unit)
      if (money) {
        if (annual < 0) money_line = `Снижение условной годовой нагрузки ~${money}`
        else if (annual === 0) {
          money_line = `Условная годовая чувствительность 0 (${money}) — нет эффекта от изменения ставки в этой модели`
        } else {
          money_line = `Условная годовая чувствительность при переносе изменения на плавающую часть долга ~${money}`
        }
      }
    }
  }

  const suffixParts = [
    assumption_badge,
    rate_fact_line,
    what_if_line,
    money_line,
    unavailable_message,
    basis === 'legacy' && !money_line ? historical_note : null,
  ].filter((x): x is string => Boolean(x && x.trim()))

  return {
    track: 'rate',
    basis,
    legacy: basis === 'legacy',
    delta_pp: delta,
    annual_sensitivity: annual,
    money_period: money_line ? 'annual' : null,
    debt_amount_unit: unit,
    debt_unit_confirmed_rub: rubConfirmed,
    fx_pair_line: null,
    fx_amount_line: null,
    fx_period_line: null,
    fx_limitations_line: null,
    fx_value_change: null,
    fx_result_currency: null,
    rate_fact_line,
    what_if_line,
    assumption_badge,
    money_line,
    hold_note,
    unavailable_message,
    historical_note,
    model_version: version,
    metric_suffix: suffixParts.length ? suffixParts.join(' · ') : null,
    decision_reason: null,
    decision_horizon:
      basis === 'none' || basis === 'conflict'
        ? null
        : 'Условный годовой горизонт чувствительности (не эффект за 90 дней)',
    expected_effect: null,
    action_model_note: null,
    credit_transfer_disclaimer:
      basis === 'observed' && money_line
        ? 'Наличие observed изменения ключевой ставки не делает расчёт фактическим изменением условий конкретного кредита'
        : null,
  }
}

function normalizePresentation(raw: Record<string, unknown>): FinanceScenarioPresentation {
  const basis = (typeof raw.basis === 'string' ? raw.basis : 'none') as RatePresentBasis
  const track: PresentTrack = raw.track === 'fx' ? 'fx' : 'rate'
  return {
    track,
    basis,
    legacy: Boolean(raw.legacy) || basis === 'legacy',
    delta_pp: isFiniteNumber(raw.delta_pp) ? raw.delta_pp : null,
    annual_sensitivity: isFiniteNumber(raw.annual_sensitivity) ? raw.annual_sensitivity : null,
    money_period: raw.money_period === 'annual' ? 'annual' : null,
    debt_amount_unit: typeof raw.debt_amount_unit === 'string' ? raw.debt_amount_unit : 'unspecified',
    debt_unit_confirmed_rub: Boolean(raw.debt_unit_confirmed_rub),
    fx_pair_line: typeof raw.fx_pair_line === 'string' ? raw.fx_pair_line : null,
    fx_amount_line: typeof raw.fx_amount_line === 'string' ? raw.fx_amount_line : null,
    fx_period_line: typeof raw.fx_period_line === 'string' ? raw.fx_period_line : null,
    fx_limitations_line: typeof raw.fx_limitations_line === 'string' ? raw.fx_limitations_line : null,
    fx_value_change: typeof raw.fx_value_change === 'string' ? raw.fx_value_change : null,
    fx_result_currency: typeof raw.fx_result_currency === 'string' ? raw.fx_result_currency : null,
    rate_fact_line: typeof raw.rate_fact_line === 'string' ? raw.rate_fact_line : null,
    what_if_line: typeof raw.what_if_line === 'string' ? raw.what_if_line : null,
    assumption_badge: typeof raw.assumption_badge === 'string' ? raw.assumption_badge : null,
    money_line: typeof raw.money_line === 'string' ? raw.money_line : null,
    hold_note: typeof raw.hold_note === 'string' ? raw.hold_note : null,
    unavailable_message:
      typeof raw.unavailable_message === 'string' ? raw.unavailable_message : null,
    historical_note: typeof raw.historical_note === 'string' ? raw.historical_note : null,
    model_version: typeof raw.model_version === 'string' ? raw.model_version : null,
    metric_suffix: typeof raw.metric_suffix === 'string' ? raw.metric_suffix : null,
    decision_reason: typeof raw.decision_reason === 'string' ? raw.decision_reason : null,
    decision_horizon: typeof raw.decision_horizon === 'string' ? raw.decision_horizon : null,
    expected_effect: typeof raw.expected_effect === 'string' ? raw.expected_effect : null,
    action_model_note: typeof raw.action_model_note === 'string' ? raw.action_model_note : null,
    credit_transfer_disclaimer:
      typeof raw.credit_transfer_disclaimer === 'string' ? raw.credit_transfer_disclaimer : null,
  }
}

export function isFinanceScenarioRow(
  sc: Record<string, unknown>,
  assessmentState?: string | null,
  source?: string | null,
): boolean {
  if (assessmentState === 'finance_ready') return true
  if (source === 'financial_calculation') return true
  if (sc.rate_change_basis != null) return true
  if (sc.fx_change_basis != null || sc.track === 'fx') return true
  if (asRecord(sc.presentation)?.basis) return true
  if (isFiniteNumber(sc.annual_rate_sensitivity)) return true
  if (isFiniteNumber(sc.funding_pressure_percent)) return true
  return false
}
