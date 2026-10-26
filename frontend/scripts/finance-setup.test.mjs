import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const {
  buildFinancePatch,
  financeSliceFromOptional,
  fxTrackReady,
  parseOptionalNumber,
  quoteConventionLabel,
  rateTrackReady,
} = await import(pathToFileURL(join(root, 'src/lib/financeSetup.ts')).href)

const emptySlice = {
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

describe('finance setup payload', () => {
  it('empty is unknown, 0 is known zero', () => {
    assert.equal(parseOptionalNumber(''), null)
    assert.equal(parseOptionalNumber('  '), null)
    assert.equal(parseOptionalNumber('0'), 0)
    assert.equal(parseOptionalNumber('0.0'), 0)
  })

  it('does not invent RUB currency', () => {
    const slice = financeSliceFromOptional({}, [])
    assert.equal(slice.debtCurrency, '')
    assert.equal(slice.fxQuoteCurrency, '')
    assert.equal(slice.purchaseCurrencies, '')
  })

  it('rate and fx payloads are independent', () => {
    const rateSlice = {
      ...emptySlice,
      debtAmount: '100',
      debtCurrency: 'RUB',
      floatingRateShare: '40',
    }
    const rate = buildFinancePatch(rateSlice)
    assert.equal(rate.optional_finance.debt_amount, 100)
    assert.equal(rate.optional_finance.floating_rate_share_percent, 40)
    assert.equal(rate.optional_finance.fx_exposure_amount, null)
    assert.equal(rateTrackReady(rateSlice), true)

    const fxSlice = {
      ...emptySlice,
      purchaseCurrencies: 'CNY',
      fxDirection: 'payment',
      fxExposureAmount: '1000',
      fxExposureCurrency: 'CNY',
      fxQuoteCurrency: 'RUB',
      fxRateFrom: '12',
    }
    const fx = buildFinancePatch(fxSlice)
    assert.equal(fx.optional_finance.debt_amount, null)
    assert.equal(fx.optional_finance.fx_exposure_amount, 1000)
    assert.equal(fx.optional_finance.fx_quote_convention, 'quote_per_exposure')
    assert.equal(fxTrackReady(fxSlice), true)
  })

  it('legacy volume not migrated into exposure', () => {
    const slice = financeSliceFromOptional({ fx_purchase_volume: 25000000 }, [])
    assert.equal(slice.fxExposureAmount, '')
    assert.equal(slice.legacyFxPurchaseVolume, '25000000')
    const patch = buildFinancePatch(slice)
    assert.equal(patch.optional_finance.fx_exposure_amount, null)
    assert.equal(patch.optional_finance.fx_purchase_volume, 25000000)
  })

  it('quote convention label', () => {
    assert.equal(quoteConventionLabel('CNY', 'RUB'), 'RUB за 1 CNY')
    assert.equal(quoteConventionLabel('', 'RUB'), null)
  })

  it('clear sends null not zero', () => {
    const patch = buildFinancePatch(emptySlice)
    assert.equal(patch.optional_finance.debt_amount, null)
    assert.notEqual(patch.optional_finance.debt_amount, 0)
  })
})
