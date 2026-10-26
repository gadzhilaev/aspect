/**
 * Pure helpers for the external company registry (INN lookup) UI.
 *
 * These functions are UI-agnostic and unit-tested. They never call the network.
 * The registry is public register data via an intermediary — NOT a direct FNS
 * request and NOT proof that the user owns the company. Keep labels honest.
 */
import type { RegistryCandidate } from '../api/types'

// ---- client-side INN check (mirrors backend; backend remains authoritative) ----

export type InnReason = 'empty' | 'non_digit' | 'bad_length' | 'bad_checksum'
export type InnCheck = { ok: true; inn: string } | { ok: false; reason: InnReason }

const W10 = [2, 4, 10, 3, 5, 9, 4, 6, 8]
const W11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
const W12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]

function controlDigit(digits: number[], weights: number[]): number {
  let sum = 0
  for (let i = 0; i < weights.length; i += 1) sum += digits[i] * weights[i]
  return (sum % 11) % 10
}

/**
 * Validate an INN string. Keeps leading zeros (INN is a string, not a number).
 * Only trims outer whitespace. 10 digits → legal entity, 12 → individual.
 */
export function checkInn(raw: string): InnCheck {
  const value = (raw ?? '').trim()
  if (!value) return { ok: false, reason: 'empty' }
  if (!/^\d+$/.test(value)) return { ok: false, reason: 'non_digit' }
  if (value.length !== 10 && value.length !== 12) return { ok: false, reason: 'bad_length' }
  const digits = value.split('').map((c) => Number(c))
  if (value.length === 10) {
    if (controlDigit(digits, W10) !== digits[9]) return { ok: false, reason: 'bad_checksum' }
  } else {
    if (controlDigit(digits, W11) !== digits[10]) return { ok: false, reason: 'bad_checksum' }
    if (controlDigit(digits, W12) !== digits[11]) return { ok: false, reason: 'bad_checksum' }
  }
  return { ok: true, inn: value }
}

export const INN_REASON_MESSAGES: Record<InnReason, string> = {
  empty: 'Введите ИНН компании.',
  non_digit: 'ИНН состоит только из цифр.',
  bad_length: 'ИНН содержит 10 цифр (организация) или 12 (ИП / физлицо).',
  bad_checksum: 'Контрольная цифра ИНН не сходится — проверьте номер.',
}

export function innCheckMessage(check: InnCheck): string | null {
  return check.ok ? null : INN_REASON_MESSAGES[check.reason]
}

// ---- error mapping (upstream/our codes → friendly RU, never logs out) ----

export const REGISTRY_ERROR_MESSAGES: Record<string, string> = {
  INVALID_INN: 'Проверьте ИНН: 10 цифр для организации или 12 для ИП.',
  RATE_LIMITED: 'Слишком много запросов к справочнику. Подождите немного и попробуйте снова.',
  REGISTRY_TIMEOUT: 'Справочник не ответил вовремя. Попробуйте позже или заполните вручную.',
  REGISTRY_UNAVAILABLE: 'Справочник временно недоступен. Попробуйте позже или заполните вручную.',
  REGISTRY_AUTH_ERROR:
    'Справочник сейчас недоступен для приложения. Данные можно заполнить вручную.',
  REGISTRY_UPSTREAM_RATE_LIMITED:
    'Справочник ограничил частоту запросов. Попробуйте чуть позже или заполните вручную.',
  REGISTRY_BAD_RESPONSE: 'Справочник вернул некорректный ответ. Можно заполнить вручную.',
  LOOKUP_NOT_FOUND: 'Результат поиска не найден. Выполните поиск заново.',
  LOOKUP_EXPIRED: 'Результат поиска устарел. Выполните поиск заново.',
  CANDIDATE_NOT_FOUND: 'Выбранная организация не найдена в результате поиска. Повторите поиск.',
}

export function registryErrorMessage(
  code: string | undefined,
  fallbackMessage?: string,
): string {
  if (code && REGISTRY_ERROR_MESSAGES[code]) return REGISTRY_ERROR_MESSAGES[code]
  return fallbackMessage || 'Не удалось выполнить поиск. Можно заполнить данные вручную.'
}

// ---- candidate presentation ----

export function orgTypeLabel(orgType: string | null | undefined): string {
  if (orgType === 'individual') return 'ИП / физлицо'
  if (orgType === 'legal') return 'Юрлицо'
  return 'Организация'
}

export function candidateTitle(c: RegistryCandidate): string {
  return c.name_short || c.name_full || `ИНН ${c.inn}`
}

export function isCandidateInactive(c: RegistryCandidate): boolean {
  return c.is_active === false
}

export type Requisite = { key: string; label: string; value: string }

/**
 * Public requisites to show on the candidate card. Missing values are omitted
 * (never invented). For individuals KPP is absent and OGRN is labelled ОГРНИП.
 */
export function candidateRequisites(c: RegistryCandidate): Requisite[] {
  const rows: Requisite[] = []
  rows.push({ key: 'inn', label: 'ИНН', value: c.inn })
  if (c.kpp) rows.push({ key: 'kpp', label: 'КПП', value: c.kpp })
  if (c.ogrn) {
    rows.push({
      key: 'ogrn',
      label: c.org_type === 'individual' ? 'ОГРНИП' : 'ОГРН',
      value: c.ogrn,
    })
  }
  if (c.region) rows.push({ key: 'region', label: 'Регион', value: c.region })
  if (c.okved) {
    rows.push({
      key: 'okved',
      label: 'ОКВЭД',
      value: c.okved_name ? `${c.okved} · ${c.okved_name}` : c.okved,
    })
  }
  return rows
}

/** True when there is more than one candidate (e.g. head office + branches). */
export function hasMultipleCandidates(count: number): boolean {
  return count > 1
}

// ---- provenance (what was taken from the registry vs edited manually) ----

export type RegistryProvenance = {
  source?: { provider?: string; title?: string; note?: string } | null
  fields_from_registry?: Record<string, string> | null
  fields_overridden_manually?: string[] | null
  verified_scope?: string | null
  retrieved_at?: string | null
  source_actuality_date?: string | null
}

const PROVENANCE_FIELD_LABELS: Record<string, string> = {
  name: 'Название',
  legal_name: 'Полное наименование',
  tax_id: 'ИНН',
  hq_region: 'Регион',
}

export function provenanceFieldLabel(field: string): string {
  return PROVENANCE_FIELD_LABELS[field] || field
}

/** Extract registry provenance from a CompanyProfile.settings object (or null). */
export function provenanceFromSettings(
  settings: Record<string, unknown> | null | undefined,
): RegistryProvenance | null {
  if (!settings || typeof settings !== 'object') return null
  const prefs = (settings as Record<string, unknown>).preferences
  if (!prefs || typeof prefs !== 'object') return null
  const prov = (prefs as Record<string, unknown>).registry_provenance
  if (!prov || typeof prov !== 'object') return null
  return prov as RegistryProvenance
}

export type ProvenanceSummary = {
  title: string
  note: string
  registryFields: string[]
  manualFields: string[]
}

/**
 * Human-readable provenance for the company profile. Deliberately scoped:
 * "public requisites", never "the whole company is verified".
 */
export function provenanceSummary(p: RegistryProvenance): ProvenanceSummary {
  const registryFields = Object.keys(p.fields_from_registry || {}).map(provenanceFieldLabel)
  const manualFields = (p.fields_overridden_manually || []).map(provenanceFieldLabel)
  return {
    title: p.source?.title || 'Публичные реестровые сведения',
    note:
      p.source?.note ||
      'Публичные сведения из реестра через посредника. Это не прямой запрос в ФНС и не подтверждение полномочий.',
    registryFields,
    manualFields,
  }
}
