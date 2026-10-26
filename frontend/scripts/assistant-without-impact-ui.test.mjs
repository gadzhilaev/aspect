/**
 * Behaviour tests for discussion-without-impact helpers (stage 3.4).
 * Uses node:test + --experimental-strip-types on the real lib — not string greps of JSX.
 * React render is NOT covered here (no browser / no RTL).
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const libUrl = pathToFileURL(join(root, 'src/lib/assistantWithoutImpact.ts')).href

const {
  canShowCalculationActions,
  conversationUiStatus,
  conversationUiStatusLabel,
  discussPath,
  displayMetricNumber,
  draftDecisionErrorMessage,
  hasImpactCalculation,
  impactSummaryView,
  isCalculationUnavailable,
  isToolUnavailableBlock,
  toolUnavailableUserMessage,
} = await import(libUrl)

describe('assessment states', () => {
  it('treats calculation_unavailable as distinct from monitoring_only', () => {
    assert.equal(isCalculationUnavailable('calculation_unavailable'), true)
    assert.equal(isCalculationUnavailable('monitoring_only'), false)
    assert.equal(hasImpactCalculation({ assessment_state: 'calculation_unavailable' }), false)
    assert.equal(hasImpactCalculation({ assessment_state: 'monitoring_only' }), true)
    assert.equal(
      hasImpactCalculation({
        has_impact_calculation: false,
        assessment_state: 'supply_chain_ready',
      }),
      false,
    )
  })

  it('hides calculation actions without impact calculation', () => {
    assert.equal(
      canShowCalculationActions({ assessment_state: 'calculation_unavailable' }),
      false,
    )
    assert.equal(
      canShowCalculationActions({
        has_impact_calculation: true,
        assessment_state: 'supply_chain_ready',
      }),
      true,
    )
    assert.equal(
      canShowCalculationActions({
        has_impact_calculation: true,
        assessment_state: 'monitoring_only',
      }),
      true,
    )
  })
})

describe('impact_summary mapping', () => {
  it('keeps known score 0 as zero (not unavailable)', () => {
    const view = impactSummaryView({
      impact_score: 0,
      confidence: 0,
      reason_summary: 'Нулевой известный индекс',
      assessment_state: 'supply_chain_ready',
    })
    assert.equal(view.kind, 'scores')
    assert.equal(view.score, 0)
    assert.equal(view.confidencePct, 0)
  })

  it('does not coerce null/missing score to 0', () => {
    const missing = impactSummaryView({
      impact_score: null,
      confidence: null,
      reason_summary: '',
    })
    assert.equal(missing.kind, 'unavailable')

    const undef = impactSummaryView({})
    assert.equal(undef.kind, 'unavailable')
  })

  it('marks calculation_unavailable even if stale numbers are present', () => {
    const view = impactSummaryView({
      impact_score: 40,
      confidence: 0.5,
      assessment_state: 'calculation_unavailable',
    })
    assert.equal(view.kind, 'unavailable')
    assert.match(view.title, /недоступна/i)
  })
})

describe('conversation list status', () => {
  it('does not mark «Решение принято» from chat alone', () => {
    const chatOnly = conversationUiStatus({
      status: 'active',
      decision_id: null,
      has_scenarios: false,
      impact_score: null,
      has_impact_calculation: false,
      assessment_state: 'calculation_unavailable',
    })
    assert.equal(chatOnly, 'watch')
    assert.notEqual(conversationUiStatusLabel(chatOnly), 'Решение принято')
  })

  it('shows decision status only with saved decision_id', () => {
    assert.equal(
      conversationUiStatus({
        status: 'decision_saved',
        decision_id: 'd1',
        has_impact_calculation: false,
      }),
      'done',
    )
    assert.equal(
      conversationUiStatus({
        status: 'decision_saved',
        decision_id: null,
        has_impact_calculation: false,
      }),
      'watch',
    )
  })

  it('does not escalate to action from high score alone', () => {
    assert.equal(
      conversationUiStatus({
        status: 'active',
        impact_score: 90,
        has_scenarios: false,
        has_impact_calculation: true,
      }),
      'watch',
    )
    assert.equal(
      conversationUiStatus({
        status: 'scenarios_ready',
        has_scenarios: true,
        has_impact_calculation: true,
      }),
      'action',
    )
  })

  it('hides metrics without calculation; keeps known zero when calculated', () => {
    assert.equal(
      displayMetricNumber(0, { hasCalculation: true }),
      0,
    )
    assert.equal(
      displayMetricNumber(0, { hasCalculation: false }),
      null,
    )
    assert.equal(
      displayMetricNumber(null, { hasCalculation: true }),
      null,
    )
  })
})

describe('tool_unavailable / 409', () => {
  it('maps tool_unavailable blocks to a clear message', () => {
    assert.equal(isToolUnavailableBlock({ type: 'tool_unavailable' }), true)
    assert.equal(
      isToolUnavailableBlock({ unavailable_reason: 'calculation_unavailable' }),
      true,
    )
    const msg = toolUnavailableUserMessage({
      type: 'tool_unavailable',
      unavailable_reason: 'calculation_unavailable',
    })
    assert.match(msg, /недоступн/i)
    assert.doesNotMatch(msg, /безопасно|риска нет/i)
  })

  it('maps CALCULATION_UNAVAILABLE draft errors without crashing semantics', () => {
    const msg = draftDecisionErrorMessage({
      status: 409,
      code: 'CALCULATION_UNAVAILABLE',
    })
    assert.match(msg, /недоступн/i)
  })
})

describe('company-switch safety contract', () => {
  it('discussion path is event-scoped (stale company answers cleared by chat effect on companyId)', () => {
    // AssistantChat useEffect([eventId, companyId]) clears messages before reopen.
    assert.equal(discussPath('evt_1'), '/events/evt_1/assistant')
    assert.notEqual(discussPath('evt_1'), discussPath('evt_2'))
  })
})
