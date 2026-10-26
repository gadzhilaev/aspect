/**
 * Company hub + section summaries from real profile/context/user data.
 * No demo fallbacks. Internal node_type / case_context keys stay out of UI copy.
 */

import type {
  CaseContext,
  CaseMarkStatus,
  CaseProfile,
  CompanyEdge,
  CompanyNode,
  CompanyProfile,
  CompanySummary,
  User,
} from '../api/types'

/** Minimal industry labels (keep hub module free of relative imports for node:test). */
function industryLabel(industry?: string | null): string | null {
  if (!industry) return null
  const map: Record<string, string> = {
    equipment: 'Производство оборудования',
    manufacturing: 'Производство',
    electronics: 'Электроника',
    trade: 'Торговля',
    logistics: 'Логистика',
    construction: 'Строительство',
    agriculture: 'АПК',
    other: 'Другое',
  }
  return map[industry] ?? industry
}

export type RegistryProvenanceLike = {
  source?: { provider?: string; title?: string; note?: string } | null
  fields_from_registry?: Record<string, string> | null
  fields_overridden_manually?: string[] | null
}

const FIELD_LABELS: Record<string, string> = {
  name: 'Название',
  legal_name: 'Полное наименование',
  tax_id: 'ИНН',
  hq_region: 'Регион',
}

function provenanceSummary(p: RegistryProvenanceLike): {
  title: string
  note: string
  registryFields: string[]
  manualFields: string[]
} {
  const registryFields = Object.keys(p.fields_from_registry || {}).map(
    (f) => FIELD_LABELS[f] || f,
  )
  const manualFields = (p.fields_overridden_manually || []).map((f) => FIELD_LABELS[f] || f)
  return {
    title: p.source?.title || 'Публичные реестровые сведения',
    note:
      p.source?.note ||
      'Публичные сведения из реестра через посредника. Это не прямой запрос в ФНС и не подтверждение полномочий.',
    registryFields,
    manualFields,
  }
}

const PRODUCT_MARK_LABELS: Record<CaseMarkStatus, string> = {
  true: 'Есть в данных',
  false: 'Отмечено отсутствие',
  unknown: 'Нет сведений',
  conflict: 'Данные расходятся',
}

function bankingProductsFromCase(profile: CaseProfile): Array<{
  key: string
  label: string
  status: CaseMarkStatus
  statusLabel: string
}> {
  const rows = (profile.products ?? []).map((p) => ({
    key: p.code,
    label: p.label || p.code,
    status: p.status,
    statusLabel: PRODUCT_MARK_LABELS[p.status],
  }))
  const hasFactoring = rows.some(
    (r) => r.key.toUpperCase() === 'FACTORING' || r.key.toUpperCase() === 'FAC',
  )
  if (!hasFactoring) {
    rows.push({
      key: 'factoring',
      label: 'Факторинг',
      status: profile.factoring.status,
      statusLabel: PRODUCT_MARK_LABELS[profile.factoring.status],
    })
  }
  return rows
}

export type CompanySectionId =
  | 'products'
  | 'markets'
  | 'geography'
  | 'me'
  | 'finance'
  | 'counterparties'

export type HubCardTone = 'accent' | 'surface' | 'inverse' | 'muted'

export type CompanyHubCard = {
  id: CompanySectionId
  title: string
  path: string
  summary: string
  empty: boolean
  tone: HubCardTone
  editHref: string | null
}

const SETUP = '/company/setup'

export const COMPANY_SECTION_META: Record<
  CompanySectionId,
  { title: string; path: string; setupStep: string | null; tone: HubCardTone }
> = {
  products: {
    title: 'Продукты',
    path: '/company/products',
    setupStep: 'chain',
    tone: 'accent',
  },
  markets: {
    title: 'Рынки',
    path: '/company/markets',
    setupStep: 'geo',
    tone: 'surface',
  },
  geography: {
    title: 'География',
    path: '/company/geography',
    setupStep: 'geo',
    tone: 'muted',
  },
  me: {
    title: 'Мои данные',
    path: '/company/me',
    setupStep: null,
    tone: 'inverse',
  },
  finance: {
    title: 'Финансы',
    path: '/company/finance',
    setupStep: 'finance',
    tone: 'surface',
  },
  counterparties: {
    title: 'Контрагенты и связи',
    path: '/company/counterparties',
    setupStep: 'chain',
    tone: 'accent',
  },
}

export function setupHref(step: string | null): string {
  if (!step) return SETUP
  return `${SETUP}?step=${encodeURIComponent(step)}`
}

function byType(nodes: CompanyNode[], type: string): CompanyNode[] {
  return nodes.filter((n) => n.node_type === type)
}

function uniq(values: string[], limit = 12): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of values) {
    const text = (raw || '').trim()
    if (!text) continue
    const key = text.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(text)
    if (out.length >= limit) break
  }
  return out
}

function joinDot(values: string[], max = 3): string {
  const items = values.slice(0, max)
  if (!items.length) return ''
  const more = values.length > max ? ` · +${values.length - max}` : ''
  return items.join(' · ') + more
}

function attrString(node: CompanyNode, key: string): string | null {
  const v = node.attributes_json?.[key]
  if (typeof v === 'string' && v.trim()) return v.trim()
  return null
}

/** Products only — never components, never HS/OKVED codes as products. */
export function productNames(nodes: CompanyNode[]): string[] {
  return uniq(byType(nodes, 'product').map((n) => n.name))
}

export function componentNames(nodes: CompanyNode[]): string[] {
  return uniq(byType(nodes, 'component').map((n) => n.name))
}

export function marketNames(nodes: CompanyNode[]): string[] {
  return uniq(byType(nodes, 'market').map((n) => n.name))
}

export function supplierNames(nodes: CompanyNode[]): string[] {
  return uniq(byType(nodes, 'supplier').map((n) => n.name))
}

export function facilityNames(nodes: CompanyNode[]): string[] {
  return uniq(byType(nodes, 'facility').map((n) => n.name))
}

export function productionLineNames(nodes: CompanyNode[]): string[] {
  return uniq(byType(nodes, 'production_line').map((n) => n.name))
}

/** Supplier / facility countries — not sales markets. */
export function geographyPlaces(company: CompanySummary, nodes: CompanyNode[]): {
  hq: string | null
  facilities: string[]
  other: string[]
} {
  const hq = company.hq_region?.trim() || null
  const facilities = uniq(
    byType(nodes, 'facility').flatMap((n) => {
      const parts = [n.name]
      if (n.region) parts.push(n.region)
      if (n.country) parts.push(n.country)
      return [parts.filter(Boolean).join(', ')]
    }),
  )
  const other = uniq(
    nodes
      .filter((n) => n.node_type !== 'market' && n.node_type !== 'facility')
      .flatMap((n) => {
        const vals: string[] = []
        if (n.country) vals.push(n.country)
        if (n.region && n.node_type !== 'supplier') vals.push(n.region)
        return vals
      })
      .filter((v) => !hq || v.toLowerCase() !== hq.toLowerCase()),
  )
  return { hq, facilities, other }
}

export function confirmedEdges(edges: CompanyEdge[]): CompanyEdge[] {
  return edges.filter((e) => {
    const src = (e.source_type || '').toLowerCase()
    // Exclude payment-only case links from “supply” narrative when flagged
    const rel = (e.relation_type || '').toLowerCase()
    if (rel.includes('payment') || rel.includes('pay')) return false
    if (src === 'payment' || src === 'case_payment') return false
    return true
  })
}

export function optionalFinance(
  settings: Record<string, unknown>,
): Record<string, unknown> {
  const raw = settings.optional_finance
  return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
}

export function purchaseCurrencies(settings: Record<string, unknown>): string[] {
  const raw = settings.purchase_currencies
  if (!Array.isArray(raw)) return []
  return uniq(raw.map((c) => String(c).toUpperCase()))
}

/** Format a finance scalar: missing → null (unknown); 0 stays "0". */
export function formatFinanceScalar(value: unknown, suffix = ''): string | null {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'number' && Number.isFinite(value)) {
    return `${value}${suffix}`
  }
  const t = String(value).trim()
  if (!t) return null
  return `${t}${suffix}`
}

export function markStatusLabel(status: CaseMarkStatus): string {
  return PRODUCT_MARK_LABELS[status]
}

export type FinanceHubView = {
  bankProducts: Array<{ key: string; label: string; statusLabel: string; status: CaseMarkStatus }>
  bankSourceNote: string | null
  manual: Array<{ label: string; value: string }>
  hasAny: boolean
  summary: string
}

export function buildFinanceView(
  settings: Record<string, unknown>,
  caseContext: CaseContext | null | undefined,
): FinanceHubView {
  const fin = optionalFinance(settings)
  const currencies = purchaseCurrencies(settings)

  const manual: Array<{ label: string; value: string }> = []
  const debt = formatFinanceScalar(fin.debt_amount)
  if (debt != null) {
    const unit =
      typeof fin.debt_amount_unit === 'string'
        ? fin.debt_amount_unit
        : typeof fin.debt_currency === 'string'
          ? fin.debt_currency
          : ''
    manual.push({
      label: 'Сумма долга (вручную)',
      value: unit ? `${debt} ${unit}` : debt,
    })
  }
  const floatShare = formatFinanceScalar(fin.floating_rate_share_percent, '%')
  if (floatShare != null) {
    manual.push({ label: 'Доля плавающей ставки', value: floatShare })
  }
  const near = formatFinanceScalar(fin.near_term_payments_90d)
  if (near != null) {
    manual.push({ label: 'Платежи на 90 дней', value: near })
  }
  const fxAmt = formatFinanceScalar(fin.fx_exposure_amount)
  if (fxAmt != null) {
    const ccy =
      typeof fin.fx_exposure_currency === 'string' ? fin.fx_exposure_currency : ''
    const dir =
      typeof fin.fx_exposure_direction === 'string' ? fin.fx_exposure_direction : ''
    const dirRu =
      dir === 'payment' ? 'платёж' : dir === 'receipt' ? 'поступление' : dir
    manual.push({
      label: 'Валютная операция (вручную)',
      value: [fxAmt, ccy, dirRu].filter(Boolean).join(' · '),
    })
  }
  if (currencies.length) {
    manual.push({ label: 'Валюты закупок', value: currencies.join(', ') })
  }

  let bankProducts: FinanceHubView['bankProducts'] = []
  let bankSourceNote: string | null = null
  if (caseContext?.status === 'profile_available' && caseContext.profile) {
    bankProducts = bankingProductsFromCase(caseContext.profile)
    bankSourceNote =
      'Банковские продукты — из подключённого источника. Наличие продукта ≠ известная сумма долга.'
  } else if (caseContext && caseContext.status !== 'profile_available') {
    bankSourceNote =
      'Банковские продукты из внешнего источника сейчас недоступны для этой компании.'
  }

  const knownBank = bankProducts.filter((p) => p.status === 'true' || p.status === 'false')
  const hasAny = manual.length > 0 || knownBank.length > 0 || bankProducts.length > 0

  let summary = 'Не заполнено'
  if (manual.length && knownBank.length) {
    summary = `${manual.length} ручн. · ${knownBank.length} из источника`
  } else if (manual.length) {
    summary = joinDot(
      manual.map((m) => m.value).filter(Boolean),
      2,
    ) || 'Параметры заданы'
  } else if (knownBank.length) {
    summary = joinDot(
      knownBank.filter((p) => p.status === 'true').map((p) => p.label),
      2,
    ) || 'Есть отметки источника'
  } else if (bankProducts.length) {
    summary = 'Только неизвестные отметки источника'
  }

  return { bankProducts, bankSourceNote, manual, hasAny, summary }
}

export function buildHubCards(input: {
  profile: CompanyProfile
  user: User
  caseContext?: CaseContext | null
}): CompanyHubCard[] {
  const { profile, user, caseContext } = input
  const { company, nodes, edges, settings } = profile
  const products = productNames(nodes)
  const components = componentNames(nodes)
  const markets = marketNames(nodes)
  const geo = geographyPlaces(company, nodes)
  const suppliers = supplierNames(nodes)
  const links = confirmedEdges(edges)
  const finance = buildFinanceView(settings, caseContext)

  const businessRole =
    byType(nodes, 'product')
      .map((n) => attrString(n, 'business_role'))
      .find(Boolean) || null

  const meBits = [
    businessRole,
    user.display_name?.trim() || null,
    user.email?.trim() || null,
  ].filter(Boolean) as string[]

  const geoBits = [
    geo.hq,
    ...geo.facilities.slice(0, 2),
    ...geo.other.slice(0, 2),
  ].filter(Boolean) as string[]

  const productSummaryParts = [...products]
  // Components listed separately in section; hub shows products first
  const productSummary =
    productSummaryParts.length > 0
      ? joinDot(productSummaryParts, 2)
      : components.length
        ? 'Есть компоненты, продуктов нет'
        : 'Не заполнено'

  const counterpartySummary =
    suppliers.length || links.length
      ? [
          suppliers.length ? `${suppliers.length} поставщик(ов)` : null,
          links.length ? `${links.length} связей` : null,
        ]
          .filter(Boolean)
          .join(' · ')
      : 'Не заполнено'

  const order: CompanySectionId[] = [
    'products',
    'markets',
    'geography',
    'me',
    'finance',
    'counterparties',
  ]

  const summaries: Record<CompanySectionId, { summary: string; empty: boolean }> = {
    products: {
      summary: productSummary,
      empty: products.length === 0 && components.length === 0,
    },
    markets: {
      summary: markets.length ? joinDot(markets, 3) : 'Не заполнено',
      empty: markets.length === 0,
    },
    geography: {
      summary: geoBits.length ? joinDot(geoBits, 3) : 'Не заполнено',
      empty: geoBits.length === 0,
    },
    me: {
      summary: meBits.length ? joinDot(meBits, 3) : 'Не заполнено',
      empty: meBits.length === 0,
    },
    finance: {
      summary: finance.hasAny ? finance.summary : 'Не заполнено',
      empty: !finance.hasAny,
    },
    counterparties: {
      summary: counterpartySummary,
      empty: suppliers.length === 0 && links.length === 0,
    },
  }

  return order.map((id) => {
    const meta = COMPANY_SECTION_META[id]
    const { summary, empty } = summaries[id]
    return {
      id,
      title: meta.title,
      path: meta.path,
      summary: empty ? 'Не заполнено' : summary,
      empty,
      tone: meta.tone,
      editHref: meta.setupStep ? setupHref(meta.setupStep) : null,
    }
  })
}

export type CompanyHeaderView = {
  name: string
  industry: string | null
  inn: string | null
  provenanceLine: string | null
  companies: Array<{ id: string; name: string }>
}

export function buildCompanyHeader(
  company: CompanySummary,
  user: User,
  provenance: RegistryProvenanceLike | null,
): CompanyHeaderView {
  const summary = provenance ? provenanceSummary(provenance) : null
  let provenanceLine: string | null = null
  if (summary && (summary.registryFields.length || summary.manualFields.length)) {
    const bits: string[] = []
    if (summary.registryFields.length) {
      bits.push(`из реестра: ${summary.registryFields.join(', ')}`)
    }
    if (summary.manualFields.length) {
      bits.push(`изменено вручную: ${summary.manualFields.join(', ')}`)
    }
    provenanceLine = `${bits.join('; ')}. ${summary.note}`
  }

  return {
    name: company.name,
    industry: industryLabel(company.industry),
    inn: company.tax_id?.trim() || null,
    provenanceLine,
    companies: user.companies.map((c) => ({
      id: c.company_id,
      name: c.name?.trim() || c.company_id,
    })),
  }
}

export function edgeLabel(
  edge: CompanyEdge,
  nodesById: Map<string, CompanyNode>,
): string {
  const from = nodesById.get(edge.from_node_id)?.name ?? '…'
  const to = nodesById.get(edge.to_node_id)?.name ?? '…'
  const rel = edge.relation_type?.trim() || 'связь'
  return `${from} → ${to} (${rel})`
}

export function membershipRoleLabel(role: string | null | undefined): string | null {
  if (!role) return null
  const r = role.trim().toLowerCase()
  if (r === 'owner') return 'Владелец профиля'
  if (r === 'admin') return 'Администратор'
  if (r === 'member') return 'Участник'
  if (r === 'viewer') return 'Наблюдатель'
  return role.trim()
}
