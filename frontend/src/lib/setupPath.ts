/** Shared CTA targets for company onboarding / post-setup navigation. */

import { agentDemoHomePath, isAgentDemoStand } from './agentDemo'

export type CompanyCta = {
  to: string
  label: string
  shortLabel: string
}

export type SetupUserLike = {
  companies?: Array<{
    company_id: string
    profile_status?: string | null
  }>
} | null

function profileStatusFor(
  user: SetupUserLike,
  companyId?: string | null,
): string | null {
  if (!user?.companies?.length || !companyId) return null
  const row = user.companies.find((c) => c.company_id === companyId)
  return row?.profile_status ?? null
}

function isProfileReady(status: string | null | undefined): boolean {
  return status === 'ready'
}

/** Destination for setup-style CTAs. */
export function companySetupPath(
  user: SetupUserLike | unknown,
  companyId?: string | null,
): string {
  if (!user) return '/register'
  if (!companyId) return '/company/setup'
  const status = profileStatusFor(user as SetupUserLike, companyId)
  if (status && !isProfileReady(status)) return '/company/setup'
  return '/news/for-you'
}

/**
 * Finance step CTA. When `eventId` is set, setup can call POST …/recompute-impact
 * after PATCH …/finance (usable Impact is not created by GET or by finance alone).
 */
export function financeSetupPath(opts?: {
  eventId?: string | null
  companyId?: string | null
}): string {
  const q = new URLSearchParams({ step: 'finance' })
  if (opts?.eventId) q.set('event', opts.eventId)
  if (opts?.companyId) q.set('companyId', opts.companyId)
  return `/company/setup?${q.toString()}`
}

/** Header / primary red button. */
export function primaryCompanyCta(
  user: SetupUserLike | unknown,
  companyId?: string | null,
): CompanyCta {
  if (!user) {
    return {
      to: '/register',
      label: 'Настроить под компанию',
      shortLabel: 'Настроить',
    }
  }
  if (!companyId) {
    return {
      to: '/company/setup',
      label: 'Настроить под компанию',
      shortLabel: 'Настроить',
    }
  }
  const status = profileStatusFor(user as SetupUserLike, companyId)
  if (status && !isProfileReady(status)) {
    return {
      to: '/company/setup',
      label: 'Продолжить настройку',
      shortLabel: 'Настройка',
    }
  }
  return {
    to: '/news/for-you',
    label: 'Лента для вас',
    shortLabel: 'Для вас',
  }
}

/** Final-band “create profile” style CTAs. */
export function createProfileCta(
  user: SetupUserLike | unknown,
  companyId?: string | null,
): CompanyCta {
  if (!user) {
    return {
      to: '/register',
      label: 'Создать профиль компании',
      shortLabel: 'Создать профиль',
    }
  }
  if (!companyId) {
    return {
      to: '/company/setup',
      label: 'Создать профиль компании',
      shortLabel: 'Создать профиль',
    }
  }
  const status = profileStatusFor(user as SetupUserLike, companyId)
  if (status && !isProfileReady(status)) {
    return {
      to: '/company/setup',
      label: 'Продолжить настройку профиля',
      shortLabel: 'Настройка',
    }
  }
  return {
    to: '/news/for-you',
    label: 'Открыть ленту для вас',
    shortLabel: 'Для вас',
  }
}

/** Post-login landing: setup if no/incomplete company, else personal feed. */
export function postLoginPath(
  user: SetupUserLike | unknown,
  companyId?: string | null,
  preferred?: string | null,
): string {
  if (!companyId) return '/company/setup'
  const status = profileStatusFor(user as SetupUserLike, companyId)
  if (status && !isProfileReady(status)) return '/company/setup'
  if (preferred && preferred !== '/login' && preferred !== '/register') return preferred
  if (isAgentDemoStand()) return agentDemoHomePath()
  return '/news/for-you'
}
