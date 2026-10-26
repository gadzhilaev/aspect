export type ThemePreference = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'aspekt.theme'

const PREFS: ThemePreference[] = ['system', 'light', 'dark']

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === 'system' || value === 'light' || value === 'dark'
}

export function readStoredThemePreference(): ThemePreference {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY)
    if (isThemePreference(raw)) return raw
  } catch {
    /* ignore */
  }
  return 'system'
}

export function writeStoredThemePreference(pref: ThemePreference): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, pref)
  } catch {
    /* ignore */
  }
}

export function systemPrefersDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function resolveTheme(pref: ThemePreference): ResolvedTheme {
  if (pref === 'light') return 'light'
  if (pref === 'dark') return 'dark'
  return systemPrefersDark() ? 'dark' : 'light'
}

export function applyTheme(pref: ThemePreference): ResolvedTheme {
  const resolved = resolveTheme(pref)
  const root = document.documentElement
  root.setAttribute('data-theme', resolved)
  root.setAttribute('data-theme-preference', pref)
  return resolved
}

export function cycleThemePreference(current: ThemePreference): ThemePreference {
  const idx = PREFS.indexOf(current)
  return PREFS[(idx + 1) % PREFS.length]
}

export function themePreferenceLabel(pref: ThemePreference): string {
  if (pref === 'light') return 'Светлая тема'
  if (pref === 'dark') return 'Тёмная тема'
  return 'Как в системе'
}

export function themeToggleAriaLabel(pref: ThemePreference): string {
  return `Тема: ${themePreferenceLabel(pref)}. Нажмите, чтобы сменить`
}
