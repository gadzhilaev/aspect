import { tokenStorage } from './tokenStorage'
import type { ApiErrorBody, TokenPair } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  code: string
  details: ApiErrorBody['error']['details']

  constructor(status: number, body: ApiErrorBody | null, fallback = 'Ошибка запроса') {
    const message = body?.error?.message ?? fallback
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = body?.error?.code ?? 'HTTP_ERROR'
    this.details = body?.error?.details ?? []
  }
}

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown
  auth?: boolean
  retry?: boolean
}

/** Single in-flight refresh — parallel 401s share one refresh call. */
let refreshPromise: Promise<boolean> | null = null

async function refreshTokens(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refresh = tokenStorage.getRefresh()
      if (!refresh) return false
      try {
        const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ refresh_token: refresh }),
        })
        if (!res.ok) {
          tokenStorage.clear()
          return false
        }
        const data = (await res.json()) as TokenPair
        tokenStorage.setTokens(data.access_token, data.refresh_token)
        return true
      } catch {
        tokenStorage.clear()
        return false
      }
    })().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

async function parseError(res: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null
  try {
    body = (await res.json()) as ApiErrorBody
  } catch {
    body = null
  }
  return new ApiError(res.status, body)
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = true, retry = true, headers, ...rest } = options
  const finalHeaders = new Headers(headers)
  finalHeaders.set('Accept', 'application/json')
  if (body !== undefined) {
    finalHeaders.set('Content-Type', 'application/json')
  }
  if (auth) {
    const access = tokenStorage.getAccess()
    if (access) finalHeaders.set('Authorization', `Bearer ${access}`)
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (res.status === 401 && auth && retry) {
    const ok = await refreshTokens()
    if (ok) {
      return apiRequest<T>(path, { ...options, retry: false })
    }
    tokenStorage.clear()
    throw new ApiError(401, {
      error: { code: 'UNAUTHORIZED', message: 'Сессия истекла. Войдите снова.' },
    })
  }

  if (!res.ok) {
    throw await parseError(res)
  }

  if (res.status === 204) {
    return undefined as T
  }

  return (await res.json()) as T
}

/**
 * Authenticated binary fetch (PDF etc.). Never puts the token in the URL.
 * Rejects JSON/error bodies so callers do not save an error envelope as a file.
 */
export async function apiRequestBlob(
  path: string,
  options: Omit<RequestOptions, 'body'> = {},
): Promise<{ blob: Blob; filename: string | null; contentType: string | null }> {
  const { auth = true, retry = true, headers, ...rest } = options
  const finalHeaders = new Headers(headers)
  finalHeaders.set('Accept', 'application/pdf, application/octet-stream, */*')
  if (auth) {
    const access = tokenStorage.getAccess()
    if (access) finalHeaders.set('Authorization', `Bearer ${access}`)
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: finalHeaders,
  })

  if (res.status === 401 && auth && retry) {
    const ok = await refreshTokens()
    if (ok) {
      return apiRequestBlob(path, { ...options, retry: false })
    }
    tokenStorage.clear()
    throw new ApiError(401, {
      error: { code: 'UNAUTHORIZED', message: 'Сессия истекла. Войдите снова.' },
    })
  }

  if (!res.ok) {
    throw await parseError(res)
  }

  const contentType = res.headers.get('Content-Type')
  if (contentType && /application\/json/i.test(contentType)) {
    throw new ApiError(res.status, {
      error: {
        code: 'UNEXPECTED_JSON',
        message: 'Сервер вернул JSON вместо файла. Загрузка отменена.',
      },
    })
  }

  const blob = await res.blob()
  if (blob.type && /application\/json/i.test(blob.type)) {
    throw new ApiError(res.status, {
      error: {
        code: 'UNEXPECTED_JSON',
        message: 'Сервер вернул JSON вместо файла. Загрузка отменена.',
      },
    })
  }

  const disposition = res.headers.get('Content-Disposition')
  let filename: string | null = null
  if (disposition) {
    const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
    const plain = /filename="?([^";]+)"?/i.exec(disposition)
    const raw = star?.[1] ?? plain?.[1]
    if (raw) {
      try {
        filename = decodeURIComponent(raw.trim())
      } catch {
        filename = raw.trim()
      }
    }
  }

  return { blob, filename, contentType }
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}
