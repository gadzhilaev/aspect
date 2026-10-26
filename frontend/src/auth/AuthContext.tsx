import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { authApi } from '../api/endpoints'
import { ApiError } from '../api/client'
import { tokenStorage } from '../api/tokenStorage'
import type { User } from '../api/types'
import { useTheme } from '../theme/ThemeContext'

type AuthState = {
  user: User | null
  companyId: string | null
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  logout: () => void
  setCompanyId: (id: string) => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

function pickCompanyId(user: User): string | null {
  const stored = tokenStorage.getCompanyId()
  const ids = user.companies.map((c) => c.company_id)
  if (stored && ids.includes(stored)) return stored
  return ids[0] ?? null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { setPreference } = useTheme()
  const [user, setUser] = useState<User | null>(null)
  const [companyId, setCompanyIdState] = useState<string | null>(tokenStorage.getCompanyId())
  const [loading, setLoading] = useState(true)

  const refreshUser = useCallback(async () => {
    if (!tokenStorage.getAccess()) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const me = await authApi.me()
      setUser(me)
      const cid = pickCompanyId(me)
      setCompanyIdState(cid)
      if (cid) tokenStorage.setCompanyId(cid)
      else tokenStorage.clearCompanyId()
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        tokenStorage.clear()
        setUser(null)
        setCompanyIdState(null)
        tokenStorage.clearCompanyId()
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshUser()
  }, [refreshUser])

  useEffect(() => {
    const saved = user?.preferences?.theme_mode
    if (saved === 'system' || saved === 'dark' || saved === 'light') setPreference(saved)
  }, [user?.id, user?.preferences?.theme_mode, setPreference])

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await authApi.login(email, password)
    tokenStorage.setTokens(tokens.access_token, tokens.refresh_token)
    setLoading(true)
    try {
      let me = await authApi.me()
      if (me.companies.some(c => c.profile_status === 'ready') && !me.preferences?.registration_complete) {
        me = await authApi.preferences({ registration_complete: true })
      }
      setUser(me)
      const cid = pickCompanyId(me)
      setCompanyIdState(cid)
      if (cid) tokenStorage.setCompanyId(cid)
      else tokenStorage.clearCompanyId()
      return me
    } catch (err) {
      tokenStorage.clear(); tokenStorage.clearCompanyId()
      setUser(null); setCompanyIdState(null)
      throw err
    } finally { setLoading(false) }
  }, [])

  const logout = useCallback(() => {
    tokenStorage.clear()
    tokenStorage.clearCompanyId()
    setUser(null)
    setCompanyIdState(null)
  }, [])

  const setCompanyId = useCallback((id: string) => {
    tokenStorage.setCompanyId(id)
    setCompanyIdState(id)
  }, [])

  const value = useMemo(
    () => ({ user, companyId, loading, login, logout, setCompanyId, refreshUser }),
    [user, companyId, loading, login, logout, setCompanyId, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
