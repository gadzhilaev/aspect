/** Pure display helpers for bank evidence UI (no React). */

import type {
  BankContentType,
  BankEvidenceBlockStatus,
  BankEvidenceListData,
  BankUsedFragment,
  EventBankEvidence,
  EventBankEvidenceItem,
  EventBankEvidenceStatus,
} from '../api/bankMaterialsTypes'

const MONTH_RU = [
  '',
  'январь',
  'февраль',
  'март',
  'апрель',
  'май',
  'июнь',
  'июль',
  'август',
  'сентябрь',
  'октябрь',
  'ноябрь',
  'декабрь',
]

const MONTH_RU_GENITIVE = [
  '',
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
]

export const CONTENT_TYPE_LABEL: Record<string, string> = {
  fact: 'Факт из материала',
  forecast: 'Прогноз банка',
  interpretation: 'Оценка банка',
}

/** News-page labels (stage 6.12) — keep chat labels above unchanged. */
export const NEWS_CONTENT_TYPE_LABEL: Record<string, string> = {
  fact: 'Факт из материала',
  forecast: 'Прогноз',
  interpretation: 'Интерпретация',
}

export function contentTypeLabel(contentType: string | null | undefined): string {
  if (!contentType) return 'Материал банка'
  return CONTENT_TYPE_LABEL[contentType] ?? 'Материал банка'
}

export function newsContentTypeLabel(contentType: string | null | undefined): string {
  if (!contentType) return 'Материал банка'
  return NEWS_CONTENT_TYPE_LABEL[contentType] ?? 'Материал банка'
}

export function textKindCaption(textKind: string | null | undefined): string | null {
  if (textKind === 'summary') return 'Пересказ'
  if (textKind === 'exact_quote') return 'Точная цитата'
  return null
}

/**
 * Human publication date. Month precision must NOT invent day 1.
 */
export function formatPublicationDate(opts: {
  publication_date?: string | null
  publication_date_precision?: string | null
  publication_date_display?: string | null
  publication_year?: number | null
  publication_month?: number | null
}): string {
  const precision = opts.publication_date_precision || 'unknown'
  if (opts.publication_date_display?.trim()) {
    return opts.publication_date_display.trim()
  }
  if (precision === 'day' && opts.publication_date) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(opts.publication_date)
    if (m) {
      const year = Number(m[1])
      const month = Number(m[2])
      const day = Number(m[3])
      if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
        return `${day} ${MONTH_RU_GENITIVE[month]} ${year}`
      }
    }
  }
  if (precision === 'month') {
    const y = opts.publication_year
    const m = opts.publication_month
    if (typeof y === 'number' && typeof m === 'number' && m >= 1 && m <= 12) {
      return `${MONTH_RU[m]} ${y}`
    }
    // Fallback: ISO YYYY-MM only — never coerce to day 1 of month
    if (opts.publication_date && /^\d{4}-\d{2}/.test(opts.publication_date)) {
      const [ys, ms] = opts.publication_date.split('-')
      const mi = Number(ms)
      if (MONTH_RU[mi]) return `${MONTH_RU[mi]} ${ys}`
    }
    return 'месяц публикации уточняется'
  }
  if (precision === 'unknown') {
    return 'дата публикации не указана'
  }
  if (opts.publication_date) {
    const d = new Date(opts.publication_date)
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString('ru-RU')
    }
  }
  return 'дата публикации не указана'
}

export function pageLabel(page: number | null | undefined): string | null {
  if (typeof page !== 'number' || page < 1) return null
  return `стр. ${page}`
}

export function qaMethodUserCopy(method: string | null | undefined): string | null {
  if (!method) return null
  const m = method.toLowerCase()
  if (m.includes('ai_vision') || m.includes('vision') || m.includes('ai')) {
    return 'Сверено AI по изображению документа'
  }
  return 'Способ сверки указан в метаданных материала'
}

export function emptyBankEvidenceUserCopy(
  status: BankEvidenceBlockStatus | undefined,
): string | null {
  switch (status) {
    case 'fetch_error':
      return 'Материалы банка временно недоступны'
    case 'integration_not_configured':
      return 'Материалы банка в этой среде пока не подключены'
    case 'event_date_unavailable':
      return 'Не удалось надёжно определить дату новости для отбора материалов банка'
    case 'no_matching_evidence':
      return 'Подходящих проверенных материалов банка для этого ответа нет'
    case 'available':
      // available with empty used = model did not cite
      return null
    default:
      return null
  }
}

export function parseBankEvidenceListData(raw: unknown): BankEvidenceListData | null {
  if (!raw || typeof raw !== 'object') return null
  const d = raw as Record<string, unknown>
  const usedRaw = Array.isArray(d.used) ? d.used : []
  const used: BankUsedFragment[] = []
  for (const item of usedRaw) {
    if (!item || typeof item !== 'object') continue
    const u = item as Record<string, unknown>
    const fragment_id = typeof u.fragment_id === 'string' ? u.fragment_id : null
    if (!fragment_id) continue
    const revision = typeof u.revision === 'number' ? u.revision : Number(u.revision)
    used.push({
      fragment_id,
      revision: Number.isFinite(revision) ? revision : 0,
      text_kind: typeof u.text_kind === 'string' ? u.text_kind : 'summary',
      text: typeof u.text === 'string' ? u.text : '',
      content_type:
        typeof u.content_type === 'string' ? (u.content_type as BankContentType) : null,
      document_title: typeof u.document_title === 'string' ? u.document_title : null,
      publication_date: typeof u.publication_date === 'string' ? u.publication_date : null,
      publication_date_precision:
        typeof u.publication_date_precision === 'string'
          ? u.publication_date_precision
          : null,
      page_number: typeof u.page_number === 'number' ? u.page_number : null,
      source_role: typeof u.source_role === 'string' ? u.source_role : null,
      qa_method: typeof u.qa_method === 'string' ? u.qa_method : null,
      document_href: typeof u.document_href === 'string' ? u.document_href : null,
      fragment_href: typeof u.fragment_href === 'string' ? u.fragment_href : null,
      content_href: typeof u.content_href === 'string' ? u.content_href : null,
      section_hint: typeof u.section_hint === 'string' ? u.section_hint : null,
    })
  }
  return {
    status: typeof d.status === 'string' ? d.status : 'available',
    available: Boolean(d.available),
    event_occurred_at: typeof d.event_occurred_at === 'string' ? d.event_occurred_at : null,
    as_of_date: typeof d.as_of_date === 'string' ? d.as_of_date : null,
    as_of_date_basis: typeof d.as_of_date_basis === 'string' ? d.as_of_date_basis : null,
    used,
    diagnostics:
      d.diagnostics && typeof d.diagnostics === 'object'
        ? (d.diagnostics as Record<string, unknown>)
        : undefined,
    limitations: Array.isArray(d.limitations)
      ? d.limitations.filter((x): x is string => typeof x === 'string')
      : undefined,
    provenance_note: typeof d.provenance_note === 'string' ? d.provenance_note : undefined,
    fetch_error:
      d.fetch_error && typeof d.fetch_error === 'object'
        ? (d.fetch_error as { code?: string; message?: string })
        : null,
  }
}

/** Preview for cards — truncate without inventing a continuous quote join. */
export function previewText(text: string, max = 180): { preview: string; truncated: boolean } {
  const t = (text || '').trim()
  if (t.length <= max) return { preview: t, truncated: false }
  return { preview: t.slice(0, max).trimEnd() + '…', truncated: true }
}

export function fragmentDetailPath(
  fragmentId: string,
  opts?: {
    conversationId?: string | null
    eventId?: string | null
    companyId?: string | null
  },
): string {
  const q = new URLSearchParams()
  if (opts?.conversationId) q.set('conversation', opts.conversationId)
  if (opts?.eventId) q.set('event', opts.eventId)
  if (opts?.companyId) q.set('company', opts.companyId)
  const qs = q.toString()
  return `/bank-materials/fragments/${encodeURIComponent(fragmentId)}${qs ? `?${qs}` : ''}`
}

export function emptyNewsBankEvidenceCopy(
  status: EventBankEvidenceStatus | undefined,
): string | null {
  switch (status) {
    case 'integration_not_configured':
      return 'Аналитика банка в этой среде пока не подключена'
    case 'event_date_unavailable':
      return 'Не удалось надёжно определить дату новости для отбора материалов банка'
    case 'no_matching_evidence':
      return 'Подходящих проверенных материалов банка для этой новости нет'
    case 'available':
      return null
    default:
      return null
  }
}

export const NEWS_BANK_THEMATIC_DISCLAIMER =
  'Тематически связанные материалы банка. Они не подтверждают все утверждения новости и не заменяют её источники.'

/** Parse GET /events/{id}/bank-evidence — only server evidence items, no invented joins. */
export function parseEventBankEvidence(raw: unknown): EventBankEvidence | null {
  if (!raw || typeof raw !== 'object') return null
  const d = raw as Record<string, unknown>
  const event_id = typeof d.event_id === 'string' ? d.event_id : ''
  if (!event_id) return null
  const evidenceRaw = Array.isArray(d.evidence) ? d.evidence : []
  const evidence: EventBankEvidenceItem[] = []
  for (const item of evidenceRaw) {
    if (!item || typeof item !== 'object') continue
    const u = item as Record<string, unknown>
    const fragment_id = typeof u.fragment_id === 'string' ? u.fragment_id : null
    if (!fragment_id) continue
    const text = typeof u.text === 'string' ? u.text : ''
    const text_kind = typeof u.text_kind === 'string' ? u.text_kind : ''
    // Never treat empty / unknown kind as a quote; skip unusable rows.
    if (!text.trim() || (text_kind !== 'exact_quote' && text_kind !== 'summary')) continue
    const revision = typeof u.revision === 'number' ? u.revision : Number(u.revision)
    const page = typeof u.page_number === 'number' ? u.page_number : Number(u.page_number)
    evidence.push({
      fragment_id,
      revision: Number.isFinite(revision) ? revision : 0,
      document_id: typeof u.document_id === 'string' ? u.document_id : '',
      document_title: typeof u.document_title === 'string' ? u.document_title : null,
      document_slug: typeof u.document_slug === 'string' ? u.document_slug : '',
      publication_date: typeof u.publication_date === 'string' ? u.publication_date : null,
      publication_year: typeof u.publication_year === 'number' ? u.publication_year : null,
      publication_month: typeof u.publication_month === 'number' ? u.publication_month : null,
      publication_date_precision:
        typeof u.publication_date_precision === 'string' ? u.publication_date_precision : 'unknown',
      publication_date_display:
        typeof u.publication_date_display === 'string' ? u.publication_date_display : null,
      page_number: Number.isFinite(page) ? page : 0,
      text_kind,
      text,
      content_type:
        typeof u.content_type === 'string' ? (u.content_type as BankContentType) : null,
      content_type_status:
        typeof u.content_type_status === 'string' ? u.content_type_status : 'unknown',
      source_role: typeof u.source_role === 'string' ? u.source_role : null,
      source_role_meaning:
        typeof u.source_role_meaning === 'string' ? u.source_role_meaning : '',
      qa_method: typeof u.qa_method === 'string' ? u.qa_method : null,
      document_href: typeof u.document_href === 'string' ? u.document_href : '',
      fragment_href: typeof u.fragment_href === 'string' ? u.fragment_href : '',
      content_href: typeof u.content_href === 'string' ? u.content_href : '',
    })
  }
  return {
    event_id,
    status: typeof d.status === 'string' ? d.status : 'no_matching_evidence',
    event_occurred_at: typeof d.event_occurred_at === 'string' ? d.event_occurred_at : null,
    as_of_date: typeof d.as_of_date === 'string' ? d.as_of_date : null,
    as_of_date_basis: typeof d.as_of_date_basis === 'string' ? d.as_of_date_basis : null,
    query_preview: typeof d.query_preview === 'string' ? d.query_preview : null,
    evidence,
    limitations: Array.isArray(d.limitations)
      ? d.limitations.filter((x): x is string => typeof x === 'string')
      : [],
    empty_reason: typeof d.empty_reason === 'string' ? d.empty_reason : null,
  }
}
