/** Pure display helpers for company case_context (no demo fallbacks). */

import type {
  CaseContextStatus,
  CaseMarkStatus,
  CaseProductMark,
  CaseProfile,
  CaseResolvedField,
  CompanyContext,
} from '../api/types'

export const CASE_STATUS_USER_COPY: Record<CaseContextStatus, string> = {
  integration_not_configured:
    'Сведения из внешнего источника пока не подключены к этой среде.',
  not_linked: 'Для этой компании пока нет связанных данных из внешнего источника.',
  no_active_snapshot: 'Набор данных источника сейчас недоступен.',
  uid_missing_in_snapshot:
    'Связанная организация отсутствует в текущем наборе данных. Показаны только сведения вашего профиля.',
  profile_absent:
    'Организация найдена в источнике, но подробный профиль в текущем наборе отсутствует.',
  profile_available: 'Ниже — сведения из внешнего источника. Они не заменяют ваш профиль.',
}

export const PRODUCT_MARK_LABELS: Record<CaseMarkStatus, string> = {
  true: 'Есть в данных',
  false: 'Отмечено отсутствие',
  unknown: 'Нет сведений',
  conflict: 'Данные расходятся',
}

export const FTS_TRADE_DIRECTION_NOTE = 'Направление торговли в источнике не указано'
export const REVENUE_UNITS_UNKNOWN_NOTE = 'Единицы выручки в источнике не уточнены'

export function caseStatusUserCopy(status: CaseContextStatus): string {
  return CASE_STATUS_USER_COPY[status]
}

export function productMarkLabel(status: CaseMarkStatus): string {
  return PRODUCT_MARK_LABELS[status]
}

export function formatConfirmedText(field: CaseResolvedField): string | null {
  if (field.status !== 'confirmed') return null
  if (field.value === null || field.value === undefined) return null
  if (typeof field.value === 'string') {
    const t = field.value.trim()
    return t || null
  }
  if (typeof field.value === 'number' || typeof field.value === 'boolean') {
    return String(field.value)
  }
  return null
}

export function fieldDisplay(field: CaseResolvedField): { kind: 'value' | 'empty' | 'conflict'; text: string } {
  if (field.status === 'conflict') {
    return { kind: 'conflict', text: 'Данные расходятся' }
  }
  if (field.status === 'absent') {
    return { kind: 'empty', text: 'Нет сведений' }
  }
  const text = formatConfirmedText(field)
  if (!text) return { kind: 'empty', text: 'Нет сведений' }
  return { kind: 'value', text }
}

export function industryFromCase(profile: CaseProfile): string | null {
  const code = formatConfirmedText(profile.okved_code)
  const name = formatConfirmedText(profile.okved_name)
  if (code && name) return `${code} — ${name}`
  if (code) return code
  if (name) return name
  if (profile.okved_code.status === 'conflict' || profile.okved_name.status === 'conflict') {
    return null
  }
  return null
}

export function industryCaseState(profile: CaseProfile): 'value' | 'empty' | 'conflict' {
  if (profile.okved_code.status === 'conflict' || profile.okved_name.status === 'conflict') {
    return 'conflict'
  }
  return industryFromCase(profile) ? 'value' : 'empty'
}

/** Banking products + factoring once (no duplicate factoring row). */
export function bankingProductsForDisplay(profile: CaseProfile): Array<{
  key: string
  label: string
  status: CaseMarkStatus
  statusLabel: string
}> {
  const rows = (profile.products ?? []).map((p: CaseProductMark) => ({
    key: p.code,
    label: p.label || p.code,
    status: p.status,
    statusLabel: productMarkLabel(p.status),
  }))
  const hasFactoringCode = rows.some(
    (r) => r.key.toUpperCase() === 'FACTORING' || r.key.toUpperCase() === 'FAC',
  )
  if (!hasFactoringCode) {
    rows.push({
      key: 'factoring',
      label: 'Факторинг',
      status: profile.factoring.status,
      statusLabel: productMarkLabel(profile.factoring.status),
    })
  }
  return rows
}

export function provenanceLines(profile: CaseProfile): string[] {
  const p = profile.provenance
  const lines: string[] = []
  if (p.source_file) lines.push(`Файл-источник: ${p.source_file}`)
  if (p.version_label) {
    const seq = p.version_seq != null ? ` (версия ${p.version_seq})` : ''
    lines.push(`Набор данных: ${p.version_label}${seq}`)
  } else if (p.version_seq != null) {
    lines.push(`Номер набора: ${p.version_seq}`)
  }
  if (p.source_row_numbers && p.source_row_numbers.length > 0) {
    const rows = p.source_row_numbers.slice(0, 12).join(', ')
    const more = p.source_row_numbers.length > 12 ? '…' : ''
    lines.push(`Исходные записи: ${rows}${more}`)
  }
  lines.push(REVENUE_UNITS_UNKNOWN_NOTE)
  lines.push(FTS_TRADE_DIRECTION_NOTE)
  lines.push('Наличие продукта в данных не означает известную сумму или условия договора.')
  return lines
}

export function manualVsCaseHints(
  data: CompanyContext,
  profile: CaseProfile,
): string[] {
  const hints: string[] = []
  const caseIndustry = industryFromCase(profile)
  if (
    data.industry_label &&
    caseIndustry &&
    data.industry_label.trim().toLowerCase() !== caseIndustry.trim().toLowerCase()
  ) {
    hints.push(
      `Отрасль в профиле: «${data.industry_label}». В источнике: «${caseIndustry}».`,
    )
  }
  const caseRegion = formatConfirmedText(profile.region)
  if (
    data.hq_region &&
    caseRegion &&
    data.hq_region.trim().toLowerCase() !== caseRegion.trim().toLowerCase()
  ) {
    hints.push(`Регион в профиле: «${data.hq_region}». В источнике: «${caseRegion}».`)
  }
  return hints
}
