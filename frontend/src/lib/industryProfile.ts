import type { IndustryProfile } from '../api/types'

export const INDUSTRY_FIELDS = [
  { key: 'product_categories', label: 'Категории продукции', example: 'Смартфоны, электроника' },
  { key: 'brands', label: 'Бренды', example: 'Apple, Samsung' },
  { key: 'product_lines', label: 'Линейки продуктов', example: 'iPhone, Galaxy' },
  { key: 'sales_markets', label: 'Рынки сбыта', example: 'Россия, Казахстан' },
  { key: 'procurement_countries', label: 'Страны закупок', example: 'Китай' },
] as const
export type IndustryDraft = Record<typeof INDUSTRY_FIELDS[number]['key'] | 'activity_role', string>

export function industryDraft(profile: IndustryProfile): IndustryDraft {
  return {
    activity_role: profile.activity_role,
    product_categories: profile.product_categories.join(', '),
    brands: profile.brands.join(', '),
    product_lines: profile.product_lines.join(', '),
    sales_markets: profile.sales_markets.join(', '),
    procurement_countries: profile.procurement_countries.join(', '),
  }
}

export function splitInterests(value: string): string[] {
  const seen = new Set<string>()
  return value.split(/[,;\n]/).map(s => s.trim().replace(/\s+/g, ' ')).filter(s => {
    if (!s || seen.has(s.toLowerCase())) return false
    seen.add(s.toLowerCase())
    return true
  })
}

/** Send only edited fields; never overwrite currencies managed by finance setup. */
export function industryPatch(original: IndustryProfile, draft: IndustryDraft): Partial<IndustryProfile> {
  const patch: Partial<IndustryProfile> = {}
  if (original.activity_role !== draft.activity_role) patch.activity_role = draft.activity_role
  for (const { key } of INDUSTRY_FIELDS) {
    const values = splitInterests(draft[key])
    if (JSON.stringify(original[key]) !== JSON.stringify(values)) patch[key] = values
  }
  return patch
}
