import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const {
  buildFinanceView,
  buildHubCards,
  buildCompanyHeader,
  formatFinanceScalar,
  productNames,
  marketNames,
  confirmedEdges,
  geographyPlaces,
} = await import(pathToFileURL(join(root, 'src/lib/companyHub.ts')).href)

function baseCompany(over = {}) {
  return {
    id: 'cmp_1',
    name: 'ООО Тест',
    legal_name: null,
    tax_id: '7707083893',
    industry: 'manufacturing',
    size_band: 'medium',
    hq_region: 'Тула',
    profile_status: 'ready',
    digital_twin_status: 'none',
    digital_twin_coverage: 0,
    is_demo: false,
    role: 'owner',
    ...over,
  }
}

function profile(over = {}) {
  return {
    company: baseCompany(over.company),
    nodes: over.nodes ?? [],
    edges: over.edges ?? [],
    settings: over.settings ?? {},
    warnings: [],
    completeness: {},
  }
}

const user = {
  id: 'u1',
  email: 'a@b.c',
  display_name: 'Анна',
  email_verified_at: '2026-01-01',
  companies: [
    { company_id: 'cmp_1', role: 'owner', name: 'ООО Тест' },
    { company_id: 'cmp_2', role: 'member', name: 'Другая' },
  ],
}

describe('formatFinanceScalar', () => {
  it('keeps known zero', () => {
    assert.equal(formatFinanceScalar(0), '0')
    assert.equal(formatFinanceScalar('0'), '0')
  })
  it('treats empty as unknown', () => {
    assert.equal(formatFinanceScalar(null), null)
    assert.equal(formatFinanceScalar(undefined), null)
    assert.equal(formatFinanceScalar(''), null)
  })
})

describe('node splits', () => {
  const nodes = [
    {
      id: '1',
      node_type: 'product',
      name: 'Станок',
      attributes_json: {},
      status: 'active',
      output_share_percent: null,
      country: null,
      region: null,
    },
    {
      id: '2',
      node_type: 'component',
      name: 'Модуль',
      attributes_json: {},
      status: 'active',
      output_share_percent: null,
      country: null,
      region: null,
    },
    {
      id: '3',
      node_type: 'market',
      name: 'Казахстан',
      attributes_json: {},
      status: 'active',
      output_share_percent: null,
      country: null,
      region: null,
    },
    {
      id: '4',
      node_type: 'supplier',
      name: 'Shenzhen X',
      attributes_json: {},
      status: 'active',
      output_share_percent: null,
      country: 'Китай',
      region: null,
    },
    {
      id: '5',
      node_type: 'facility',
      name: 'Площадка 1',
      attributes_json: {},
      status: 'active',
      output_share_percent: null,
      country: null,
      region: 'Москва',
    },
  ]

  it('does not mix products with components', () => {
    assert.deepEqual(productNames(nodes), ['Станок'])
  })

  it('keeps markets separate from supplier countries', () => {
    assert.deepEqual(marketNames(nodes), ['Казахстан'])
    const geo = geographyPlaces(baseCompany(), nodes)
    assert.equal(geo.hq, 'Тула')
    assert.ok(geo.facilities.some((f) => f.includes('Площадка')))
  })

  it('filters payment edges out of counterparties links', () => {
    const edges = [
      {
        id: 'e1',
        from_node_id: '4',
        relation_type: 'supplies',
        to_node_id: '2',
        attributes_json: {},
        confidence: 1,
        source_type: 'manual',
      },
      {
        id: 'e2',
        from_node_id: '4',
        relation_type: 'payment',
        to_node_id: '1',
        attributes_json: {},
        confidence: 1,
        source_type: 'case_payment',
      },
    ]
    assert.equal(confirmedEdges(edges).length, 1)
    assert.equal(confirmedEdges(edges)[0].id, 'e1')
  })
})

describe('buildHubCards', () => {
  it('shows empty copy for blank company sections', () => {
    const cards = buildHubCards({
      profile: profile({ company: { hq_region: null } }),
      user,
    })
    assert.equal(cards.length, 6)
    const byId = Object.fromEntries(cards.map((c) => [c.id, c]))
    for (const id of ['products', 'markets', 'geography', 'finance', 'counterparties']) {
      assert.equal(byId[id].empty, true, id)
      assert.equal(byId[id].summary, 'Не заполнено', id)
    }
    // «Мои данные» заполняются из текущего пользователя, не из demo-профиля компании
    assert.equal(byId.me.empty, false)
    assert.ok(!/СеверПром/i.test(byId.me.summary))
  })

  it('summarises filled sections without demo substitution', () => {
    const cards = buildHubCards({
      profile: profile({
        nodes: [
          {
            id: 'p1',
            node_type: 'product',
            name: 'Оборудование',
            attributes_json: { business_role: 'Директор' },
            status: 'active',
            output_share_percent: null,
            country: null,
            region: null,
          },
          {
            id: 'm1',
            node_type: 'market',
            name: 'Россия',
            attributes_json: {},
            status: 'active',
            output_share_percent: null,
            country: null,
            region: null,
          },
        ],
        settings: { optional_finance: { debt_amount: 0, debt_currency: 'RUB' } },
      }),
      user,
    })
    const byId = Object.fromEntries(cards.map((c) => [c.id, c]))
    assert.equal(byId.products.empty, false)
    assert.match(byId.products.summary, /Оборудование/)
    assert.equal(byId.markets.empty, false)
    assert.equal(byId.finance.empty, false)
    assert.match(byId.finance.summary, /0/)
    assert.ok(!cards.some((c) => /СеверПром/i.test(c.summary)))
  })
})

describe('buildFinanceView bank marks', () => {
  it('maps four mark states to text', () => {
    const view = buildFinanceView(
      {},
      {
        status: 'profile_available',
        explanation: '',
        profile: {
          external_uid: 'u',
          profile_resolution: 'ok',
          okved_code: { key: 'okved_code', status: 'absent' },
          okved_name: { key: 'okved_name', status: 'absent' },
          city: { key: 'city', status: 'absent' },
          region: { key: 'region', status: 'absent' },
          workers_fns: { key: 'workers_fns', status: 'absent' },
          workers_spark: { key: 'workers_spark', status: 'absent' },
          company_age: { key: 'company_age', status: 'absent' },
          products: [
            { code: 'A', label: 'Продукт A', status: 'true' },
            { code: 'B', label: 'Продукт B', status: 'false' },
            { code: 'C', label: 'Продукт C', status: 'unknown' },
            { code: 'D', label: 'Продукт D', status: 'conflict' },
          ],
          factoring: { status: 'unknown', explanation: '' },
          fts_geography: { status: 'absent' },
          group: { status: 'absent' },
          revenue: { status: 'absent' },
          provenance: { snapshot_id: 's1' },
        },
        read_only: true,
      },
    )
    const labels = Object.fromEntries(view.bankProducts.map((p) => [p.key, p.statusLabel]))
    assert.equal(labels.A, 'Есть в данных')
    assert.equal(labels.B, 'Отмечено отсутствие')
    assert.equal(labels.C, 'Нет сведений')
    assert.equal(labels.D, 'Данные расходятся')
  })
})

describe('header', () => {
  it('exposes inn and multi-company switch list without size fluff', () => {
    const header = buildCompanyHeader(baseCompany(), user, {
      fields_from_registry: { tax_id: '7707083893' },
      fields_overridden_manually: ['name'],
      source: {
        title: 'Публичный реестр',
        note: 'Публичные сведения, не подтверждение полномочий.',
      },
    })
    assert.equal(header.inn, '7707083893')
    assert.equal(header.companies.length, 2)
    assert.ok(header.provenanceLine)
    assert.ok(!/сотрудник/i.test(JSON.stringify(header)))
  })
})
