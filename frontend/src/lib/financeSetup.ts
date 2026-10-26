/**
 * Finance setup helpers (stage 5.5): empty ≠ 0, merge PATCH payload, track readiness.
 */

export type FxDirection = 'payment' | 'receipt' | ''

export type FinanceFormSlice = {
  debtAmount: string
  debtCurrency: string
  floatingRateShare: string
  nearTermPayments: string
  fxPurchaseVolume: string
  cashReserveDays: string
  purchaseCurrencies: string
  fxDirection: FxDirection
  fxExposureAmount: string
  fxExposureCurrency: string
  fxQuoteCurrency: string
  fxExposurePeriod: string
  fxRateFrom: string
  /** Legacy volume shown read-only; never auto-copied into fx_exposure_amount */
  legacyFxPurchaseVolume: string | null
}

export const EMPTY_FINANCE_SLICE: FinanceFormSlice = {
  debtAmount: '',
  debtCurrency: '',
  floatingRateShare: '',
  nearTermPayments: '',
  fxPurchaseVolume: '',
  cashReserveDays: '',
  purchaseCurrencies: '',
  fxDirection: '',
  fxExposureAmount: '',
  fxExposureCurrency: '',
  fxQuoteCurrency: '',
  fxExposurePeriod: '',
  fxRateFrom: '',
  legacyFxPurchaseVolume: null,
}

/** Parse decimal form text. Empty → null (unknown). Never Number(''). */
export function parseOptionalNumber(raw: string): number | null {
  const t = raw.trim().replace(',', '.')
  if (!t) return null
  const n = Number(t)
  if (!Number.isFinite(n)) return null
  return n
}

/** Show old volume only when typed FX amount absent. */
export function legacyFxHint(fin: Record<string, unknown>): string | null {
  if (fin.fx_exposure_amount != null && fin.fx_exposure_amount !== '') return null
  if (fin.fx_purchase_volume == null || fin.fx_purchase_volume === '') return null
  return String(fin.fx_purchase_volume)
}

export function financeSliceFromOptional(
  fin: Record<string, unknown>,
  purchaseCurrencies: string[],
): FinanceFormSlice {
  const unit =
    typeof fin.debt_amount_unit === 'string'
      ? fin.debt_amount_unit
      : typeof fin.debt_currency === 'string'
        ? fin.debt_currency
        : ''
  const dirRaw = typeof fin.fx_exposure_direction === 'string' ? fin.fx_exposure_direction : ''
  const dir: FxDirection =
    dirRaw === 'payment' || dirRaw === 'receipt' ? dirRaw : ''

  return {
    debtAmount: fin.debt_amount != null ? String(fin.debt_amount) : '',
    debtCurrency: unit,
    floatingRateShare:
      fin.floating_rate_share_percent != null ? String(fin.floating_rate_share_percent) : '',
    nearTermPayments:
      fin.near_term_payments_90d != null ? String(fin.near_term_payments_90d) : '',
    fxPurchaseVolume:
      fin.fx_purchase_volume != null ? String(fin.fx_purchase_volume) : '',
    cashReserveDays: fin.cash_reserve_days != null ? String(fin.cash_reserve_days) : '',
    purchaseCurrencies: purchaseCurrencies.length ? purchaseCurrencies.join(', ') : '',
    fxDirection: dir,
    fxExposureAmount: fin.fx_exposure_amount != null ? String(fin.fx_exposure_amount) : '',
    fxExposureCurrency:
      typeof fin.fx_exposure_currency === 'string' ? fin.fx_exposure_currency : '',
    fxQuoteCurrency: typeof fin.fx_quote_currency === 'string' ? fin.fx_quote_currency : '',
    fxExposurePeriod:
      typeof fin.fx_exposure_period === 'string' ? fin.fx_exposure_period : '',
    fxRateFrom: fin.fx_rate_from != null ? String(fin.fx_rate_from) : '',
    legacyFxPurchaseVolume: legacyFxHint(fin),
  }
}

export function quoteConventionLabel(exposureCcy: string, quoteCcy: string): string | null {
  const e = exposureCcy.trim().toUpperCase()
  const q = quoteCcy.trim().toUpperCase()
  if (!e || !q) return null
  return `${q} за 1 ${e}`
}

export function rateTrackReady(slice: FinanceFormSlice): boolean {
  return parseOptionalNumber(slice.debtAmount) !== null && parseOptionalNumber(slice.floatingRateShare) !== null
}

export function fxTrackReady(slice: FinanceFormSlice): boolean {
  const amountOk = parseOptionalNumber(slice.fxExposureAmount) !== null
  const ccyOk = Boolean(slice.fxExposureCurrency.trim())
  const quoteOk = Boolean(slice.fxQuoteCurrency.trim())
  const dirOk = slice.fxDirection === 'payment' || slice.fxDirection === 'receipt'
  return amountOk && ccyOk && quoteOk && dirOk
}

export function rateTrackMissing(slice: FinanceFormSlice): string[] {
  const miss: string[] = []
  if (parseOptionalNumber(slice.debtAmount) === null) miss.push('сумма долга')
  if (parseOptionalNumber(slice.floatingRateShare) === null) miss.push('доля плавающей ставки')
  return miss
}

export function fxTrackMissing(slice: FinanceFormSlice): string[] {
  const miss: string[] = []
  if (!(slice.fxDirection === 'payment' || slice.fxDirection === 'receipt')) {
    miss.push('направление')
  }
  if (parseOptionalNumber(slice.fxExposureAmount) === null) miss.push('сумма')
  if (!slice.fxExposureCurrency.trim()) miss.push('валюта суммы')
  if (!slice.fxQuoteCurrency.trim()) miss.push('валюта расчёта')
  return miss
}

/**
 * Build merge PATCH for optional_finance.
 * Every managed key is sent: number/string value, or null to clear.
 * Does not coerce empty → 0. Does not migrate legacy fx_purchase_volume.
 */
export function buildFinancePatch(slice: FinanceFormSlice): {
  purchase_currencies: string[]
  optional_finance: Record<string, unknown>
} {
  const optional_finance: Record<string, unknown> = {}

  const setNum = (key: string, raw: string) => {
    const n = parseOptionalNumber(raw)
    optional_finance[key] = n
  }
  const setStr = (key: string, raw: string) => {
    const t = raw.trim()
    optional_finance[key] = t ? t : null
  }

  setNum('debt_amount', slice.debtAmount)
  const debtCcy = slice.debtCurrency.trim().toUpperCase()
  optional_finance.debt_amount_unit = debtCcy || null
  optional_finance.debt_currency = debtCcy || null
  setNum('floating_rate_share_percent', slice.floatingRateShare)
  setNum('near_term_payments_90d', slice.nearTermPayments)
  setNum('fx_purchase_volume', slice.fxPurchaseVolume)
  setNum('cash_reserve_days', slice.cashReserveDays)

  const dir = slice.fxDirection
  optional_finance.fx_exposure_direction =
    dir === 'payment' || dir === 'receipt' ? dir : null
  setNum('fx_exposure_amount', slice.fxExposureAmount)
  setStr('fx_exposure_currency', slice.fxExposureCurrency.toUpperCase())
  setStr('fx_quote_currency', slice.fxQuoteCurrency.toUpperCase())
  setStr('fx_exposure_period', slice.fxExposurePeriod)
  setNum('fx_rate_from', slice.fxRateFrom)

  const fxStructuralReady = fxTrackReady(slice)
  optional_finance.fx_quote_convention = fxStructuralReady ? 'quote_per_exposure' : null

  const purchase_currencies = slice.purchaseCurrencies
    .split(/[,;]/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)

  return { purchase_currencies, optional_finance }
}

export function fieldErrorMap(details: unknown): Record<string, string> {
  const out: Record<string, string> = {}
  if (!Array.isArray(details)) return out
  for (const item of details) {
    if (!item || typeof item !== 'object') continue
    const field = (item as { field?: unknown }).field
    const reason = (item as { reason?: unknown }).reason
    if (typeof field === 'string') {
      out[field] = typeof reason === 'string' ? reason : 'ошибка'
    }
  }
  return out
}
