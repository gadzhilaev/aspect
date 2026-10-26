/**
 * Stage 6.10.1 — one save + one explicit recompute; partial failure retry.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

const setupPathSrc = readFileSync(join(root, 'src/lib/setupPath.ts'), 'utf8')
const setupSrc = readFileSync(join(root, 'src/pages/CompanySetupPage.tsx'), 'utf8')
const endpointsSrc = readFileSync(join(root, 'src/api/endpoints.ts'), 'utf8')
const chatSrc = readFileSync(join(root, 'src/components/assistant/AssistantChat.tsx'), 'utf8')
const newsSrc = readFileSync(join(root, 'src/pages/NewsDetailPage.tsx'), 'utf8')
const impactSrc = readFileSync(join(root, 'src/components/personal/ImpactPanel.tsx'), 'utf8')

describe('financeSetupPath', () => {
  it('exports helper with step=finance and optional event', () => {
    assert.match(setupPathSrc, /export function financeSetupPath/)
    assert.match(setupPathSrc, /step['"]?\s*,\s*['"]finance['"]|step:\s*['"]finance['"]/)
    assert.match(setupPathSrc, /q\.set\(['"]event['"]/)
  })
})

describe('one save → one recompute → discuss', () => {
  it('endpoints expose recomputeImpact', () => {
    assert.match(endpointsSrc, /recompute-impact/)
    assert.match(endpointsSrc, /recomputeImpact\(/)
  })

  it('CompanySetup: patchFinance then single recomputeImpact; navigate to discuss', () => {
    assert.match(setupSrc, /patchFinance/)
    assert.match(setupSrc, /eventsApi\.recomputeImpact/)
    assert.match(setupSrc, /runEventRecompute/)
    assert.match(setupSrc, /discussPath\(/)
    // Partial failure: profile kept, retry without re-save
    assert.match(setupSrc, /recomputePending/)
    assert.match(setupSrc, /Повторить пересчёт/)
    assert.match(setupSrc, /уже сохранён/)
  })

  it('NewsDetail / ImpactPanel / AssistantChat pass event into finance CTA', () => {
    assert.match(newsSrc, /financeSetupPath\(/)
    assert.match(impactSrc, /financeSetupPath\(/)
    assert.match(chatSrc, /financeSetupPath\(/)
  })
})
