import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const {
  checkInn,
  innCheckMessage,
  registryErrorMessage,
  candidateTitle,
  candidateRequisites,
  isCandidateInactive,
  orgTypeLabel,
  provenanceFromSettings,
  provenanceSummary,
} = await import(pathToFileURL(join(root, 'src/lib/companyRegistry.ts')).href)

function legalCandidate(over = {}) {
  return {
    candidate_id: '0',
    org_type: 'legal',
    inn: '7707083893',
    kpp: '770701001',
    ogrn: '1027700132195',
    ogrn_date: '2002-09-24',
    name_short: 'ООО "ПРИМЕР"',
    name_full: 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРИМЕР"',
    address: 'г Москва',
    region: 'г Москва',
    okved: '26.30',
    okved_name: 'Производство оборудования',
    okved_version: '2014',
    status: 'active',
    status_label: 'Действующая',
    is_active: true,
    branch_type: 'main',
    suggested_industry: 'electronics',
    ...over,
  }
}

describe('checkInn', () => {
  it('accepts valid 10-digit legal INN', () => {
    assert.deepEqual(checkInn('7707083893'), { ok: true, inn: '7707083893' })
  })
  it('accepts valid 12-digit individual INN', () => {
    assert.deepEqual(checkInn('500100732259'), { ok: true, inn: '500100732259' })
  })
  it('preserves leading zeros (string, not number)', () => {
    assert.deepEqual(checkInn('0040000007'), { ok: true, inn: '0040000007' })
  })
  it('trims outer whitespace only', () => {
    assert.deepEqual(checkInn('  7707083893 '), { ok: true, inn: '7707083893' })
  })
  it('rejects empty', () => {
    assert.deepEqual(checkInn('   '), { ok: false, reason: 'empty' })
  })
  it('rejects non-digit', () => {
    assert.deepEqual(checkInn('77A7083893'), { ok: false, reason: 'non_digit' })
    assert.deepEqual(checkInn('7707 083893'), { ok: false, reason: 'non_digit' })
  })
  it('rejects bad length', () => {
    assert.deepEqual(checkInn('12345'), { ok: false, reason: 'bad_length' })
    assert.deepEqual(checkInn('12345678901'), { ok: false, reason: 'bad_length' })
  })
  it('rejects bad checksum (10 and 12 digit)', () => {
    assert.deepEqual(checkInn('7707083894'), { ok: false, reason: 'bad_checksum' })
    assert.deepEqual(checkInn('500100732250'), { ok: false, reason: 'bad_checksum' })
  })
  it('innCheckMessage: ok → null, errors → message', () => {
    assert.equal(innCheckMessage({ ok: true, inn: '7707083893' }), null)
    assert.match(innCheckMessage({ ok: false, reason: 'bad_checksum' }), /контрольн/i)
  })
})

describe('registryErrorMessage', () => {
  it('maps known codes without leaking raw provider text', () => {
    assert.match(registryErrorMessage('REGISTRY_TIMEOUT'), /вовремя|позже/i)
    assert.match(registryErrorMessage('REGISTRY_AUTH_ERROR'), /вручную|недоступ/i)
    assert.match(registryErrorMessage('LOOKUP_EXPIRED'), /заново|устар/i)
  })
  it('falls back to provided message, then generic', () => {
    assert.equal(registryErrorMessage('UNKNOWN_X', 'friendly'), 'friendly')
    assert.match(registryErrorMessage(undefined), /вручную/i)
  })
})

describe('candidate presentation', () => {
  it('title prefers short name, falls back to INN', () => {
    assert.equal(candidateTitle(legalCandidate()), 'ООО "ПРИМЕР"')
    assert.equal(
      candidateTitle(legalCandidate({ name_short: null, name_full: null })),
      'ИНН 7707083893',
    )
  })
  it('legal requisites include КПП and ОГРН', () => {
    const rows = candidateRequisites(legalCandidate())
    const keys = rows.map((r) => r.key)
    assert.ok(keys.includes('kpp'))
    const ogrn = rows.find((r) => r.key === 'ogrn')
    assert.equal(ogrn.label, 'ОГРН')
  })
  it('individual has no КПП and ОГРНИП label', () => {
    const rows = candidateRequisites(
      legalCandidate({ org_type: 'individual', kpp: null, ogrn: '304500116000157' }),
    )
    assert.ok(!rows.some((r) => r.key === 'kpp'))
    assert.equal(rows.find((r) => r.key === 'ogrn').label, 'ОГРНИП')
  })
  it('omits missing values instead of inventing them', () => {
    const rows = candidateRequisites(
      legalCandidate({ kpp: null, ogrn: null, region: null, okved: null }),
    )
    assert.deepEqual(rows.map((r) => r.key), ['inn'])
  })
  it('inactive flag and org labels', () => {
    assert.equal(isCandidateInactive(legalCandidate({ is_active: false })), true)
    assert.equal(isCandidateInactive(legalCandidate()), false)
    assert.equal(orgTypeLabel('individual'), 'ИП / физлицо')
    assert.equal(orgTypeLabel('legal'), 'Юрлицо')
  })
})

describe('provenance', () => {
  const settings = {
    preferences: {
      registry_provenance: {
        source: { provider: 'dadata', title: 'DaData · ЕГРЮЛ', note: 'не прямой запрос в ФНС' },
        fields_from_registry: { name: 'ООО X', tax_id: '7707083893' },
        fields_overridden_manually: ['name'],
        verified_scope: 'public_requisites',
      },
    },
  }
  it('extracts provenance from settings', () => {
    const p = provenanceFromSettings(settings)
    assert.ok(p)
    assert.equal(p.verified_scope, 'public_requisites')
  })
  it('returns null when absent', () => {
    assert.equal(provenanceFromSettings({ preferences: {} }), null)
    assert.equal(provenanceFromSettings(null), null)
  })
  it('summary maps field keys to RU labels, scoped to requisites', () => {
    const s = provenanceSummary(provenanceFromSettings(settings))
    assert.ok(s.registryFields.includes('ИНН'))
    assert.ok(s.manualFields.includes('Название'))
    assert.match(s.note, /ФНС|реестр/i)
  })
})
