// Separate sessions when connecting this site to the mobile developer's backend.
const namespace = import.meta.env.VITE_AUTH_NAMESPACE || 'kontur'
const ACCESS_KEY = `${namespace}.access_token`
const REFRESH_KEY = `${namespace}.refresh_token`
const COMPANY_KEY = `${namespace}.company_id`

export const tokenStorage = {
  getAccess(): string | null {
    return localStorage.getItem(ACCESS_KEY)
  },
  getRefresh(): string | null {
    return localStorage.getItem(REFRESH_KEY)
  },
  setTokens(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
  getCompanyId(): string | null {
    return localStorage.getItem(COMPANY_KEY)
  },
  setCompanyId(id: string) {
    localStorage.setItem(COMPANY_KEY, id)
  },
  clearCompanyId() {
    localStorage.removeItem(COMPANY_KEY)
  },
}
