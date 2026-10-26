import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  applyTheme,
  cycleThemePreference,
  readStoredThemePreference,
  resolveTheme,
  type ResolvedTheme,
  type ThemePreference,
  writeStoredThemePreference,
} from './theme'

type ThemeContextValue = {
  preference: ThemePreference
  resolved: ResolvedTheme
  setPreference: (pref: ThemePreference) => void
  cyclePreference: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    typeof document !== 'undefined'
      ? ((document.documentElement.getAttribute('data-theme-preference') as ThemePreference) ||
          readStoredThemePreference())
      : 'system',
  )
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    typeof document !== 'undefined'
      ? ((document.documentElement.getAttribute('data-theme') as ResolvedTheme) ||
          resolveTheme(preference))
      : 'light',
  )

  const setPreference = useCallback((pref: ThemePreference) => {
    writeStoredThemePreference(pref)
    setPreferenceState(pref)
    setResolved(applyTheme(pref))
  }, [])

  const cyclePreference = useCallback(() => {
    setPreference(cycleThemePreference(preference))
  }, [preference, setPreference])

  useEffect(() => {
    setResolved(applyTheme(preference))
  }, [preference])

  useEffect(() => {
    if (preference !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setResolved(applyTheme('system'))
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [preference])

  const value = useMemo(
    () => ({ preference, resolved, setPreference, cyclePreference }),
    [preference, resolved, setPreference, cyclePreference],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
