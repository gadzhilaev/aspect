/** Fallback when GET /companies/{id}/context is unavailable (stale API). */

import type {
  CompanyContext,
  CompanyCoverageBlock,
  CompanyMapGroup,
  CompanyNode,
  CompanyProfile,
  CompanyTrackingCategory,
} from '../api/types'
import { industryLabel } from './format'

const SETUP = '/company/setup'

const SIZE_LABELS: Record<string, string> = {
  small: 'Небольшая компания',
  medium: 'Средняя компания',
  large: 'Крупная компания',
  enterprise: 'Крупное предприятие',
}

const GEO_CANON: Record<string, string> = {
  china: 'Китай',
  китай: 'Китай',
  russia: 'Россия',
  россия: 'Россия',
  cis: 'СНГ',
  снг: 'СНГ',
}

function uniq(values: string[], limit = 8): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of values) {
    let text = (raw || '').trim()
    if (!text) continue
    text = GEO_CANON[text.toLowerCase()] ?? text
    const key = text.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(text)
    if (out.length >= limit) break
  }
  return out
}

function joinHuman(values: string[], max = 3): string {
  const items = values.slice(0, max)
  if (items.length === 0) return ''
  if (items.length === 1) return items[0]
  if (items.length === 2) return `${items[0]} и ${items[1]}`
  return `${items.slice(0, -1).join(', ')} и ${items[items.length - 1]}`
}

function byType(nodes: CompanyNode[], type: string): CompanyNode[] {
  return nodes.filter((n) => n.node_type === type)
}

function nodePlaces(node: CompanyNode): string[] {
  const vals: string[] = []
  if (node.country) vals.push(node.country)
  if (node.region) vals.push(node.region)
  const attrs = node.attributes_json
  if (attrs && typeof attrs === 'object') {
    for (const key of ['countries', 'markets'] as const) {
      const raw = (attrs as Record<string, unknown>)[key]
      if (Array.isArray(raw)) vals.push(...raw.map(String))
      else if (typeof raw === 'string' && raw.trim()) vals.push(raw.trim())
    }
  }
  return vals
}

function keyPresent(optional: Record<string, unknown>, key: string): boolean {
  const v = optional[key]
  return v !== null && v !== undefined && v !== ''
}

function financeFilled(optional: Record<string, unknown> | undefined): boolean {
  if (!optional) return false
  const rateOk =
    keyPresent(optional, 'debt_amount') &&
    keyPresent(optional, 'floating_rate_share_percent')
  const fxOk =
    keyPresent(optional, 'fx_exposure_amount') &&
    keyPresent(optional, 'fx_exposure_currency') &&
    keyPresent(optional, 'fx_exposure_direction') &&
    keyPresent(optional, 'fx_quote_currency')
  return rateOk || fxOk
}

export function companyContextFromProfile(profile: CompanyProfile): CompanyContext {
  const { company, nodes, edges, settings } = profile
  const ready = company.profile_status === 'ready'
  const product = byType(nodes, 'product')[0]
  const businessRole =
    typeof product?.attributes_json?.business_role === 'string'
      ? product.attributes_json.business_role.trim()
      : null

  const countries = uniq(nodes.flatMap(nodePlaces))
  const products = uniq([
    ...byType(nodes, 'product').map((n) => n.name),
    ...byType(nodes, 'component').map((n) => n.name),
  ])
  const markets = uniq(byType(nodes, 'market').map((n) => n.name))
  const suppliers = uniq(byType(nodes, 'supplier').map((n) => n.name))
  const facilities = uniq(byType(nodes, 'facility').map((n) => n.name))
  const lines = uniq(byType(nodes, 'production_line').map((n) => n.name))

  const purchase = Array.isArray(settings.purchase_currencies)
    ? (settings.purchase_currencies as string[])
    : []
  const optional =
    settings.optional_finance && typeof settings.optional_finance === 'object'
      ? (settings.optional_finance as Record<string, unknown>)
      : {}
  const hasFinance = financeFilled(optional)
  const currencies = uniq([
    ...purchase.map((c) => String(c).toUpperCase()),
    ...byType(nodes, 'currency').map((n) => n.name.toUpperCase()),
  ])

  const tracking: CompanyTrackingCategory[] = []
  const gaps: CompanyTrackingCategory[] = []

  if (countries.length) {
    tracking.push({
      key: 'geo',
      title: 'Страны и регионы',
      values: countries.slice(0, 6),
      explanation: `${joinHuman(countries)} — экспортные ограничения, логистика и спрос на этих рынках.`,
      filled: true,
    })
  } else {
    gaps.push({
      key: 'geo',
      title: 'Страны и регионы',
      values: [],
      explanation: 'Добавьте географию — тогда Аспект отфильтрует сигналы по вашим рынкам.',
      filled: false,
      cta_label: 'Указать страны',
      cta_href: `${SETUP}?step=geo`,
    })
  }

  if (products.length) {
    tracking.push({
      key: 'products',
      title: 'Продукты и компоненты',
      values: products.slice(0, 6),
      explanation: `${joinHuman(products)} — новости о поставках и производственных ограничениях становятся персональными.`,
      filled: true,
    })
  } else {
    gaps.push({
      key: 'products',
      title: 'Продукты и компоненты',
      values: [],
      explanation: 'Без продукта или критичного компонента сложно оценить риск остановки.',
      filled: false,
      cta_label: 'Добавить критичный компонент',
      cta_href: `${SETUP}?step=chain`,
    })
  }

  if (markets.length) {
    tracking.push({
      key: 'markets',
      title: 'Рынки присутствия',
      values: markets.slice(0, 6),
      explanation: `${joinHuman(markets)} — спрос и импортные условия на этих рынках попадают в ленту «Для вас».`,
      filled: true,
    })
  } else {
    gaps.push({
      key: 'markets',
      title: 'Рынки присутствия',
      values: [],
      explanation: 'Укажите рынки сбыта — Аспект свяжет с ними релевантные сигналы.',
      filled: false,
      cta_label: 'Указать рынки',
      cta_href: `${SETUP}?step=geo`,
    })
  }

  if (hasFinance || currencies.length) {
    tracking.push({
      key: 'finance',
      title: 'Валюты и финансы',
      values: currencies.slice(0, 6),
      explanation: hasFinance
        ? 'Ставка и валюта влияют на стоимость финансирования — Аспект считает это по вашим параметрам.'
        : 'Валюты закупок помогают отслеживать курсовые и платёжные сигналы.',
      filled: true,
    })
  } else {
    gaps.push({
      key: 'finance',
      title: 'Валюты и финансы',
      values: [],
      explanation: 'Для макро- и FX-сценариев нужны валюты и параметры финансирования.',
      filled: false,
      cta_label: 'Добавить финансовые параметры',
      cta_href: `${SETUP}?step=finance`,
    })
  }

  if (suppliers.length) {
    tracking.push({
      key: 'suppliers',
      title: 'Поставщики и цепочки',
      values: suppliers.slice(0, 6),
      explanation: `${joinHuman(suppliers)} — сбои у поставщиков оцениваются через вашу цепочку.`,
      filled: true,
    })
  } else {
    gaps.push({
      key: 'suppliers',
      title: 'Поставщики и цепочки',
      values: [],
      explanation: 'Добавьте поставщика — тогда ограничения экспорта свяжутся с вашей линией.',
      filled: false,
      cta_label: 'Проверить цепочку поставок',
      cta_href: `${SETUP}?step=chain`,
    })
  }

  const map_groups: CompanyMapGroup[] = []
  const supplyItems = uniq([...suppliers, ...byType(nodes, 'component').map((n) => n.name)])
  if (supplyItems.length) {
    map_groups.push({
      key: 'supplies',
      title: 'Поставки',
      count: supplyItems.length,
      items: supplyItems.slice(0, 4),
      explanation:
        'Через поставки Аспект связывает новости о странах и компонентах с риском для вашей линии.',
    })
  }
  const productionItems = uniq([
    ...facilities,
    ...lines,
    ...byType(nodes, 'product').map((n) => n.name),
  ])
  if (productionItems.length) {
    map_groups.push({
      key: 'production',
      title: 'Производство',
      count: productionItems.length,
      items: productionItems.slice(0, 4),
      explanation:
        'Производственный контур показывает, какая площадка и линия затронуты сигналом.',
    })
  }
  if (markets.length) {
    map_groups.push({
      key: 'markets',
      title: 'Рынки',
      count: markets.length,
      items: markets.slice(0, 4),
      explanation: 'Рынки присутствия делают релевантными новости о спросе и импорте.',
    })
  }
  if (hasFinance || currencies.length) {
    map_groups.push({
      key: 'finance',
      title: 'Финансы',
      count: currencies.length || 1,
      items: (currencies.slice(0, 4).length ? currencies.slice(0, 4) : ['Финансовый контекст']),
      explanation: 'Финансовый контур переводит ставки и валюту в расчётные сценарии.',
    })
  }

  const coverage_blocks: CompanyCoverageBlock[] = [
    {
      key: 'industry',
      title: 'Отрасль',
      filled: Boolean(company.industry),
      summary: company.industry ? industryLabel(company.industry) : 'Отрасль ещё не выбрана',
      cta_label: company.industry ? null : 'Указать отрасль',
      cta_href: company.industry ? null : `${SETUP}?step=role`,
    },
    {
      key: 'geo',
      title: 'География',
      filled: countries.length > 0,
      summary: countries.length ? joinHuman(countries) : 'Страны и регионы не заданы',
      cta_label: countries.length ? null : 'Указать страны',
      cta_href: countries.length ? null : `${SETUP}?step=geo`,
    },
    {
      key: 'products',
      title: 'Продукты и компоненты',
      filled: products.length > 0,
      summary: products.length ? joinHuman(products) : 'Нет продукта или критичного компонента',
      cta_label: products.length ? null : 'Добавить критичный компонент',
      cta_href: products.length ? null : `${SETUP}?step=chain`,
    },
    {
      key: 'markets',
      title: 'Рынки',
      filled: markets.length > 0,
      summary: markets.length ? joinHuman(markets) : 'Рынки присутствия не указаны',
      cta_label: markets.length ? null : 'Указать рынки',
      cta_href: markets.length ? null : `${SETUP}?step=geo`,
    },
    {
      key: 'chain',
      title: 'Цепочка поставок',
      filled: suppliers.length > 0 && edges.length > 0,
      summary:
        suppliers.length > 0 && edges.length > 0
          ? `${suppliers.length} поставщик(ов), ${edges.length} связей`
          : 'Цепочка неполная — нет поставщика или связей',
      cta_label: suppliers.length > 0 && edges.length > 0 ? null : 'Проверить цепочку поставок',
      cta_href: suppliers.length > 0 && edges.length > 0 ? null : `${SETUP}?step=chain`,
    },
    {
      key: 'finance',
      title: 'Финансы',
      filled: hasFinance,
      summary: hasFinance
        ? joinHuman(currencies) || 'Финансовые параметры заполнены'
        : currencies.length
          ? 'Валюты есть, но не хватает параметров финансирования'
          : 'Финансовые параметры не заполнены',
      cta_label: hasFinance ? null : 'Добавить финансовые параметры',
      cta_href: hasFinance ? null : `${SETUP}?step=finance`,
    },
  ]

  const coverage_filled = coverage_blocks.filter((b) => b.filled).length

  return {
    company_name: company.name,
    industry_label: company.industry ? industryLabel(company.industry) : null,
    business_role: businessRole || null,
    size_label: company.size_band ? SIZE_LABELS[company.size_band] ?? null : null,
    hq_region: company.hq_region,
    profile_ready: ready,
    status_label: ready ? 'Контекст настроен' : 'Нужно завершить настройку',
    setup_cta_label: ready ? 'Изменить контекст' : 'Продолжить настройку',
    setup_href: ready ? SETUP : `${SETUP}?step=basics`,
    is_demo: company.is_demo,
    tracking,
    tracking_gaps: gaps,
    map_groups,
    coverage_blocks,
    coverage_filled,
    coverage_total: coverage_blocks.length,
    example: null,
  }
}
