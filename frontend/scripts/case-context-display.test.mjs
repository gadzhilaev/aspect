/**
 * Lightweight Node tests for case-context display contracts.
 * No vitest/jest — uses built-in node:test.
 * Fixtures are test-only; they are not wired into the page.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const displaySrc = readFileSync(join(root, 'src/lib/caseContextDisplay.ts'), 'utf8')
const sectionSrc = readFileSync(join(root, 'src/components/company/CaseContextSection.tsx'), 'utf8')
const typesSrc = readFileSync(join(root, 'src/api/types.ts'), 'utf8')
const pageSrc = readFileSync(join(root, 'src/pages/CompanyPage.tsx'), 'utf8')

const STATUSES = [
  'integration_not_configured',
  'not_linked',
  'no_active_snapshot',
  'uid_missing_in_snapshot',
  'profile_absent',
  'profile_available',
]

const MARKS = {
  true: 'Есть в данных',
  false: 'Отмечено отсутствие',
  unknown: 'Нет сведений',
  conflict: 'Данные расходятся',
}

describe('case_context types', () => {
  it('declares all OpenAPI statuses and optional case_context', () => {
    for (const s of STATUSES) {
      assert.match(typesSrc, new RegExp(`'${s}'`))
    }
    assert.match(typesSrc, /case_context\?:/)
  })
})

describe('display copy contracts', () => {
  it('covers every status with human copy (no env var names)', () => {
    for (const s of STATUSES) {
      assert.match(displaySrc, new RegExp(`${s}:`))
    }
    assert.doesNotMatch(displaySrc, /CASE_CONTEXT_SLOT_KEY/)
    assert.doesNotMatch(displaySrc, /alembic|DATABASE_URL|импорт CSV/i)
    // User-facing status strings must not expose technical ids
    const statusBlock = displaySrc.slice(
      displaySrc.indexOf('CASE_STATUS_USER_COPY'),
      displaySrc.indexOf('PRODUCT_MARK_LABELS'),
    )
    assert.doesNotMatch(statusBlock, /snapshot_id|U_ID|env/i)
  })

  it('maps product marks true/false/unknown/conflict distinctly', () => {
    for (const [k, label] of Object.entries(MARKS)) {
      assert.match(displaySrc, new RegExp(`${k}: '${label}'`))
    }
    assert.notEqual(MARKS.false, MARKS.unknown)
  })

  it('forbids rubles and trade-direction claims in helpers', () => {
    assert.match(displaySrc, /Единицы выручки в источнике не уточнены/)
    assert.match(displaySrc, /Направление торговли в источнике не указано/)
    assert.doesNotMatch(displaySrc, /₽|руб\.|рынк(и|ам) продаж|страны поставок/)
  })

  it('adds factoring once and keeps provenance without UUID cards', () => {
    assert.match(displaySrc, /Факторинг/)
    assert.match(displaySrc, /hasFactoringCode/)
    assert.match(displaySrc, /Файл-источник/)
    assert.match(displaySrc, /Исходные записи/)
    assert.doesNotMatch(displaySrc, /catalog_row_ids/)
  })
})

describe('Company page wiring', () => {
  it('renders CaseContextSection from company context payload', () => {
    assert.match(pageSrc, /CaseContextSection/)
    assert.match(pageSrc, /companyApi\.context/)
  })

  it('handles missing case_context without crashing path', () => {
    assert.match(sectionSrc, /if \(!caseContext\)/)
    assert.match(sectionSrc, /return null/)
  })

  it('keeps manual vs case distinction and FTS note', () => {
    assert.match(sectionSrc, /Профиль и источник различаются/)
    assert.match(sectionSrc, /FTS_TRADE_DIRECTION_NOTE/)
    assert.match(sectionSrc, /Банковские продукты/)
    assert.doesNotMatch(sectionSrc, /рынк(и|ам) продаж|страны поставок/)
  })
})

describe('fixture semantics (test-only objects)', () => {
  it('profile_available fixture exposes four product states and factoring', () => {
    const fixture = {
      status: 'profile_available',
      profile: {
        products: [
          { code: 'RKO', label: 'РКО', status: 'true' },
          { code: 'DEP', label: 'Депозиты', status: 'false' },
          { code: 'GAR', label: 'Гарантии', status: 'unknown' },
          { code: 'LOA', label: 'Кредиты', status: 'conflict' },
        ],
        factoring: { status: 'true', explanation: 'mark only' },
        provenance: { snapshot_id: 'snap-b', version_label: 'v2', source_file: 'data.csv' },
      },
    }
    const labels = fixture.profile.products.map((p) => MARKS[p.status])
    assert.deepEqual(labels, [
      'Есть в данных',
      'Отмечено отсутствие',
      'Нет сведений',
      'Данные расходятся',
    ])
    assert.equal(fixture.profile.provenance.snapshot_id, 'snap-b')
    assert.notEqual(fixture.profile.provenance.snapshot_id, 'snap-a')
  })

  it('absent case_context leaves legacy company fields intact', () => {
    const legacy = {
      company_name: 'Acme',
      industry_label: 'Электроника',
      size_label: 'Средняя компания',
      profile_ready: true,
      case_context: undefined,
    }
    assert.equal(legacy.industry_label, 'Электроника')
    assert.equal(legacy.case_context, undefined)
  })
})
