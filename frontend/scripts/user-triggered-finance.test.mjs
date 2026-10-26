/**
 * Stage 6.6 — user-triggered finance scenarios (node:test, real TS via strip-types).
 * CTA → compare-scenarios API, not postMessage; what-if units; company switch reset.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const lib = await import(pathToFileURL(join(root, 'src/lib/userTriggeredFinance.ts')).href)
const {
  FINANCE_CALC_CTA,
  FINANCE_RECALC_CTA,
  SUPPLY_COMPARE_CTA,
  SYSTEM_CALC_TITLE,
  buildCompareRequestBody,
  compareScenariosPath,
  emptyCalcStateAfterCompanySwitch,
  isScenarioCalcChip,
  isSystemCalcMessage,
  pickDefaultScenarioId,
  showFinanceCalcCta,
  showFinanceRecalcCta,
  showSupplyCompareCta,
  unavailableNoticeFromResult,
  validateWhatIfInputs,
} = lib

const chatSrc = readFileSync(join(root, 'src/components/assistant/AssistantChat.tsx'), 'utf8')
const endpointsSrc = readFileSync(join(root, 'src/api/endpoints.ts'), 'utf8')

describe('CTA routes to compare API, not chat message', () => {
  it('scenario chips are intercepted before postMessage', () => {
    assert.equal(isScenarioCalcChip('Рассчитать финансовые сценарии'), true)
    assert.equal(isScenarioCalcChip('Покажи финансовые сценарии'), true)
    assert.equal(isScenarioCalcChip('Покажи три сценария'), true)
    assert.equal(isScenarioCalcChip('Сравнить сценарии'), true)
    assert.equal(isScenarioCalcChip('Что проверить сегодня?'), false)
  })

  it('AssistantChat wires CTA to compareScenarios / runUserCompare', () => {
    assert.match(chatSrc, /assistantApi\.compareScenarios/)
    assert.match(chatSrc, /runUserCompare/)
    assert.match(chatSrc, /FINANCE_CALC_CTA|Рассчитать финансовые сценарии/)
    assert.match(chatSrc, /isScenarioCalcChip\(trimmed\)/)
    assert.doesNotMatch(
      chatSrc,
      /send\(['"]Рассчитать финансовые сценарии['"]/,
    )
  })

  it('endpoints expose POST compare-scenarios (not messages)', () => {
    assert.match(endpointsSrc, /compare-scenarios/)
    assert.equal(
      compareScenariosPath('conv_1'),
      '/api/v1/assistant/conversations/conv_1/compare-scenarios',
    )
    assert.doesNotMatch(compareScenariosPath('conv_1'), /\/messages$/)
  })
})

describe('what-if units', () => {
  it('rate is п.п.; FX is %; bounds enforced', () => {
    const ok = validateWhatIfInputs('1.5', '10')
    assert.equal(ok.ok, true)
    if (ok.ok) {
      assert.equal(ok.ratePp, 1.5)
      assert.equal(ok.fxPct, 10)
    }
    const rateBad = validateWhatIfInputs('abc', '')
    assert.equal(rateBad.ok, false)
    if (!rateBad.ok) assert.match(rateBad.notice, /п\.п\./)

    const fxBad = validateWhatIfInputs('', 'xx')
    assert.equal(fxBad.ok, false)
    if (!fxBad.ok) assert.match(fxBad.notice, /%/)

    const rateBound = validateWhatIfInputs('21', '')
    assert.equal(rateBound.ok, false)
    if (!rateBound.ok) assert.match(rateBound.notice, /20/)

    const body = buildCompareRequestBody({
      clientRequestId: 'r1',
      ratePp: 1.5,
      fxPct: null,
    })
    assert.equal(body.assumed_rate_change_pp, 1.5)
    assert.equal(body.assumed_fx_change_percent, null)
  })
})

describe('loading / error / unavailable', () => {
  it('maps missing_data and empty ok to user notices', () => {
    assert.match(
      unavailableNoticeFromResult({
        status: 'missing_data',
        result: { message: 'Нужен долг и плавающая доля' },
      }) || '',
      /долг|плавающ/i,
    )
    assert.match(
      unavailableNoticeFromResult({ status: 'running' }) || '',
      /выполняется/i,
    )
    assert.match(
      unavailableNoticeFromResult({ status: 'ok', scenario_ids: [] }) || '',
      /нет/i,
    )
    assert.equal(
      unavailableNoticeFromResult({ status: 'ok', scenario_ids: ['s1'] }),
      null,
    )
  })

  it('system calc is not an AI message', () => {
    assert.equal(
      isSystemCalcMessage({ role: 'system', content: SYSTEM_CALC_TITLE }),
      true,
    )
    assert.equal(
      isSystemCalcMessage({ role: 'assistant', content: SYSTEM_CALC_TITLE }),
      false,
    )
    assert.match(chatSrc, /assistant-msg-system-calc|Расчёт по вашему запросу/)
  })
})

describe('CTA visibility and presentation', () => {
  it('finance CTA only on finance tracks; supply CTA on supply_chain_ready', () => {
    assert.equal(
      showFinanceCalcCta({
        calcActionsAllowed: true,
        hasScenarios: false,
        assessmentState: 'finance_ready',
      }),
      true,
    )
    assert.equal(
      showFinanceCalcCta({
        calcActionsAllowed: true,
        hasScenarios: false,
        assessmentState: 'supply_chain_ready',
      }),
      false,
    )
    assert.equal(
      showSupplyCompareCta({
        calcActionsAllowed: true,
        hasScenarios: false,
        assessmentState: 'supply_chain_ready',
      }),
      true,
    )
    assert.equal(
      showFinanceCalcCta({
        calcActionsAllowed: false,
        hasScenarios: false,
        assessmentState: 'finance_ready',
      }),
      false,
    )
    assert.equal(FINANCE_CALC_CTA, 'Рассчитать финансовые сценарии')
    assert.equal(SUPPLY_COMPARE_CTA, 'Сравнить сценарии')
  })

  it('after first calc, recalc what-if path stays available', () => {
    assert.equal(
      showFinanceCalcCta({
        calcActionsAllowed: true,
        hasScenarios: true,
        assessmentState: 'finance_ready',
      }),
      false,
    )
    assert.equal(
      showFinanceRecalcCta({
        calcActionsAllowed: true,
        hasScenarios: true,
        confirmed: false,
        assessmentState: 'finance_ready',
      }),
      true,
    )
    assert.equal(
      showFinanceRecalcCta({
        calcActionsAllowed: true,
        hasScenarios: true,
        confirmed: true,
        assessmentState: 'finance_ready',
      }),
      false,
    )
    assert.equal(FINANCE_RECALC_CTA, 'Рассчитать другой вариант')
    assert.match(chatSrc, /FINANCE_RECALC_CTA|Рассчитать другой вариант/)
    assert.match(chatSrc, /showFinanceRecalcCta/)
  })

  it('default selection prefers baseline scenario_id', () => {
    const picked = pickDefaultScenarioId(
      [
        { kind: 'baseline', scenario_id: 's-base', label: 'Без действий' },
        {
          kind: 'alternative',
          scenario_id: 's-fx',
          action_id: 'reduce_fx_exposure',
          label: 'Снизить валютную экспозицию',
        },
      ],
      ['s-base', 's-fx'],
    )
    assert.equal(picked.scenarioId, 's-base')
  })

  it('results use existing finance presentation helper', () => {
    assert.match(chatSrc, /presentFinanceScenario/)
  })
})

describe('company switch clears foreign results', () => {
  it('reset state empties messages, scenarios, what-if, notices', () => {
    const empty = emptyCalcStateAfterCompanySwitch()
    assert.deepEqual(empty.messages, [])
    assert.equal(empty.hasScenarios, false)
    assert.equal(empty.selectedScenarioId, null)
    assert.equal(empty.decisionId, null)
    assert.equal(empty.whatIfRatePp, '')
    assert.equal(empty.whatIfFxPercent, '')
    assert.equal(empty.calcNotice, null)
    // AssistantChat effect depends on companyId
    assert.match(chatSrc, /\[eventId, companyId\]/)
    assert.match(chatSrc, /setMessages\(\[\]\)/)
    assert.match(chatSrc, /setHasScenarios\(false\)/)
  })
})
