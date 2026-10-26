/**
 * Stage 5.3 — finance scenario presentation (node:test, real TS via strip-types).
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const mod = await import(
  pathToFileURL(join(root, 'src/lib/financeScenarioPresentation.ts')).href
)
const {
  formatDebtAmountDisplay,
  presentFinanceScenario,
  resolvePresentBasis,
  isFinanceScenarioRow,
} = mod

describe('finance presentation fixtures', () => {
  it('observed hike', () => {
    const pres = presentFinanceScenario({
      rate_change_basis: 'observed',
      rate_change_delta_pp: 1,
      annual_rate_sensitivity: 400000,
      debt_amount_unit: 'unspecified',
    })
    assert.equal(pres.basis, 'observed')
    assert.match(pres.rate_fact_line, /Ключевая ставка изменилась на 1 п\.п\./)
    assert.match(pres.money_line, /Условная годовая чувствительность/)
    assert.equal(pres.money_line.includes('₽'), false)
    assert.match(pres.money_line, /единицы введённой суммы долга/)
  })

  it('observed hold known zero', () => {
    const pres = presentFinanceScenario({
      rate_change_basis: 'observed',
      rate_change_delta_pp: 0,
      annual_rate_sensitivity: 0,
      debt_amount_unit: 'unspecified',
    })
    assert.match(pres.rate_fact_line, /не изменилась/)
    assert.match(pres.hold_note, /всех финансовых рисков/)
  })

  it('rate cut negative label', () => {
    const pres = presentFinanceScenario({
      rate_change_basis: 'observed',
      rate_change_delta_pp: -1,
      annual_rate_sensitivity: -400000,
      debt_amount_unit: 'RUB',
    })
    assert.match(pres.money_line, /Снижение условной годовой нагрузки/)
    assert.equal(pres.money_line.toLowerCase().includes('дополнительн'), false)
    assert.match(pres.money_line, /₽/)
  })

  it('explicit assumed shock', () => {
    const pres = presentFinanceScenario({
      rate_change_basis: 'assumed',
      rate_change_delta_pp: 1.5,
      annual_rate_sensitivity: 100,
      action_id: 'assumed_rate_shock',
    })
    assert.equal(pres.assumption_badge, 'Допущение сценария')
    assert.match(pres.what_if_line, /Что если ставка изменится на 1\.5 п\.п\./)
  })

  it('none and conflict', () => {
    const none = presentFinanceScenario({ rate_change_basis: 'none', extra_annual_cost: 9 })
    assert.match(none.unavailable_message, /Недостаточно данных/)
    assert.equal(none.money_line, null)

    const conflict = presentFinanceScenario({
      rate_change_basis: 'conflict',
      extra_annual_cost: 9,
    })
    assert.match(conflict.unavailable_message, /противореч/)
    assert.equal(conflict.money_line, null)
  })

  it('units unspecified vs RUB', () => {
    assert.match(formatDebtAmountDisplay(1e6, 'unspecified'), /единицы введённой суммы долга/)
    assert.equal(formatDebtAmountDisplay(1e6, 'unspecified').includes('₽'), false)
    assert.match(formatDebtAmountDisplay(1e6, 'RUB'), /₽/)
  })

  it('legacy proxy and missing basis', () => {
    const proxy = presentFinanceScenario(
      { extra_annual_cost: 50, label: 'Без действий' },
      { shock_proxy_pp: 1.2, kind: 'financial' },
    )
    assert.equal(proxy.basis, 'legacy')
    assert.match(proxy.historical_note, /прежней модели|не является observed/i)

    const { basis } = resolvePresentBasis({}, {})
    assert.ok(basis === 'none' || basis === 'legacy')
  })

  it('observed baseline plus what-if stay distinct', () => {
    const base = presentFinanceScenario({
      rate_change_basis: 'observed',
      rate_change_delta_pp: 0,
      annual_rate_sensitivity: 0,
    })
    const whatIf = presentFinanceScenario({
      rate_change_basis: 'assumed',
      rate_change_delta_pp: 1.5,
      annual_rate_sensitivity: 100,
      action_id: 'assumed_rate_shock',
    })
    assert.equal(base.basis, 'observed')
    assert.equal(whatIf.basis, 'assumed')
    assert.notEqual(base.rate_fact_line, whatIf.what_if_line)
  })

  it('null disabled metrics not resurrected in suffix', () => {
    const sc = {
      rate_change_basis: 'observed',
      rate_change_delta_pp: 1,
      annual_rate_sensitivity: 10,
      near_term_pressure: null,
      near_term_pressure_status: 'unavailable_not_severity_proxy',
      funding_pressure_percent: null,
      funding_pressure_status: 'unavailable_severity_proxy_removed',
      debt_amount_unit: 'unspecified',
    }
    assert.equal(isFinanceScenarioRow(sc, 'finance_ready', 'financial_calculation'), true)
    const suffix = presentFinanceScenario(sc).metric_suffix
    assert.ok(suffix)
    assert.equal(suffix.includes('давление финансирования'), false)
    assert.equal(/эффект за 90|около 90/.test(suffix), false)
    assert.equal(suffix.includes('None'), false)
  })

  it('does not infer basis from label', () => {
    const { basis } = resolvePresentBasis(
      {
        label: 'Ключевая ставка повышена факт',
        rate_change_basis: 'assumed',
        rate_change_delta_pp: 2,
      },
      {},
    )
    assert.equal(basis, 'assumed')
  })

  it('prefers server presentation object', () => {
    const pres = presentFinanceScenario({
      rate_change_basis: 'observed',
      presentation: {
        basis: 'assumed',
        assumption_badge: 'Допущение сценария',
        what_if_line: 'Что если ставка изменится на 3 п.п.',
        money_line: null,
        legacy: false,
      },
    })
    assert.equal(pres.basis, 'assumed')
    assert.match(pres.what_if_line, /3 п\.п\./)
  })

  it('FX track does not reuse rate annual copy', () => {
    const pres = presentFinanceScenario({
      track: 'fx',
      fx_change_basis: 'observed',
      fx_exposure_amount: '1000',
      fx_exposure_currency: 'CNY',
      fx_exposure_direction: 'payment',
      fx_quote_currency: 'RUB',
      fx_rate_from: '12',
      fx_rate_to: '13',
      fx_value_change: '1000.00',
      fx_value_change_meaning_label: 'Рост стоимости платежа',
      fx_period_label: 'Период не указан',
    })
    assert.equal(pres.track, 'fx')
    assert.equal(pres.delta_pp, null)
    assert.equal(pres.annual_sensitivity, null)
    assert.equal(pres.money_period, null)
    assert.match(pres.money_line || '', /платежа/)
    assert.equal((pres.money_line || '').includes('п.п'), false)
    assert.equal((pres.money_line || '').includes('плавающ'), false)
    assert.match(pres.fx_pair_line || '', /RUB\/CNY/)
    assert.match(pres.fx_period_line || '', /Период не указан/)
  })

  it('FX conflict has no fake money metrics', () => {
    const pres = presentFinanceScenario({
      track: 'fx',
      fx_change_basis: 'conflict',
      fx_value_change: '999',
    })
    assert.equal(pres.basis, 'conflict')
    assert.equal(pres.money_line, null)
    assert.match(pres.unavailable_message || '', /курс/)
  })
})
