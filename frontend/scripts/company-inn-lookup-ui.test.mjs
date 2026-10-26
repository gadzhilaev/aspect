/**
 * Source-level checks for the INN registry lookup flow.
 *
 * NOTE: these assert on .tsx/.ts SOURCE (presence of wiring), NOT a rendered
 * React DOM. Real behaviour of pure helpers is covered by
 * company-registry.test.mjs; DOM-level verification is a manual checklist
 * (see docs/COMPANY_INN_LOOKUP.md).
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const setupSrc = readFileSync(join(root, 'src/pages/CompanySetupPage.tsx'), 'utf8')
const endpointsSrc = readFileSync(join(root, 'src/api/endpoints.ts'), 'utf8')
const companyPageSrc = readFileSync(join(root, 'src/pages/CompanyPage.tsx'), 'utf8')
const typesSrc = readFileSync(join(root, 'src/api/types.ts'), 'utf8')

describe('registry endpoints wiring', () => {
  it('endpoints expose registryLookup + registryConfirm on fixed paths', () => {
    assert.match(endpointsSrc, /registryLookup\(/)
    assert.match(endpointsSrc, /registryConfirm\(/)
    assert.match(endpointsSrc, /\/api\/v1\/company-registry\/lookup/)
    assert.match(endpointsSrc, /\/api\/v1\/company-registry\/confirm/)
  })
  it('types include registry candidate + lookup result', () => {
    assert.match(typesSrc, /RegistryCandidate/)
    assert.match(typesSrc, /RegistryLookupResult/)
    assert.match(typesSrc, /RegistryConfirmResult/)
  })
})

describe('CompanySetupPage INN lookup flow', () => {
  it('has INN field + "Найти компанию" + "Заполнить вручную"', () => {
    assert.match(setupSrc, /setup-inn/)
    assert.match(setupSrc, /Найти компанию/)
    assert.match(setupSrc, /Заполнить вручную/)
    assert.match(setupSrc, /registry-lookup-btn/)
    assert.match(setupSrc, /registry-manual-btn/)
  })

  it('calls lookup/confirm via companyApi (no direct fetch)', () => {
    assert.match(setupSrc, /companyApi\.registryLookup/)
    assert.match(setupSrc, /companyApi\.registryConfirm/)
  })

  it('validates INN client-side before calling (checkInn) with input error state', () => {
    assert.match(setupSrc, /checkInn\(/)
    assert.match(setupSrc, /innError/)
    assert.match(setupSrc, /inn-error/)
  })

  it('guards against stale responses (lookupSeq) and does not search per keystroke', () => {
    assert.match(setupSrc, /lookupSeq/)
    // lookup is triggered by an explicit button onClick, not onChange
    assert.match(setupSrc, /onClick=\{\(\) => void runLookup\(\)\}/)
  })

  it('renders candidate cards, source honesty, and does not auto-pick on multiple', () => {
    assert.match(setupSrc, /registry-candidate/)
    assert.match(setupSrc, /candidateRequisites\(/)
    assert.match(setupSrc, /Использовать эти данные/)
    assert.match(setupSrc, /candidate-use-btn/)
    // explicit multi-candidate message
    assert.match(setupSrc, /candidate_count > 1/)
    assert.match(setupSrc, /Найдено несколько записей/)
    // source note (intermediary, not FNS) + "not the registry update date"
    assert.match(setupSrc, /registry-source/)
    assert.match(setupSrc, /не дата обновления реестра/)
  })

  it('surfaces not_found / not_configured / error states distinctly', () => {
    assert.match(setupSrc, /registry-not-found/)
    assert.match(setupSrc, /registry-not-configured/)
    assert.match(setupSrc, /registry-error/)
  })

  it('shows liquidation/inactive status explicitly', () => {
    assert.match(setupSrc, /isCandidateInactive\(/)
    assert.match(setupSrc, /candidate-inactive/)
  })

  it('OKVED industry is a suggestion, not auto-applied', () => {
    assert.match(setupSrc, /suggestedIndustry/)
    assert.match(setupSrc, /industry-suggestion/)
    assert.match(setupSrc, /ОКВЭД ≠ отрасль/)
  })

  it('tells the user edited fields become manual (provenance note)', () => {
    assert.match(setupSrc, /registry-provenance-note/)
    assert.match(setupSrc, /станет ручным/)
  })

  it('handles opened_existing (open own profile, no duplicate)', () => {
    assert.match(setupSrc, /opened_existing/)
    assert.match(setupSrc, /дубликат не создан/)
  })
})

describe('CompanyPage provenance display', () => {
  it('shows compact provenance, scoped to requisites (not whole company)', () => {
    assert.match(companyPageSrc, /provenanceFromSettings/)
    assert.match(companyPageSrc, /company-hub-provenance/)
    assert.match(companyPageSrc, /Реквизиты/)
    assert.match(companyPageSrc, /header\.provenanceLine/)
  })
  it('profile is required; optional external context has its own error state', () => {
    assert.match(companyPageSrc, /await companyApi\.profile/)
    assert.match(companyPageSrc, /try \{[\s\S]*companyApi\.context[\s\S]*\} catch/)
    assert.match(companyPageSrc, /contextError/)
  })
})
