import { apiRequestBlob, ApiError } from '../api/client'

/** Turn API path or absolute same-origin URL into a path for apiRequestBlob. */
export function contentHrefToApiPath(contentHref: string): string {
  const raw = contentHref.trim()
  if (!raw) throw new ApiError(400, { error: { code: 'BAD_HREF', message: 'Ссылка на файл пуста' } })
  if (raw.startsWith('/api/')) return raw
  if (raw.startsWith('/')) return raw
  try {
    const u = new URL(raw)
    return `${u.pathname}${u.search}`
  } catch {
    throw new ApiError(400, {
      error: { code: 'BAD_HREF', message: 'Некорректная ссылка на файл' },
    })
  }
}

/**
 * Download PDF via Bearer-authenticated fetch + Blob.
 * Avoids opening the API URL in a new tab (Authorization would be lost).
 * Does not put the token in query/hash.
 * Revokes the object URL after the download click.
 */
export async function downloadBankPdf(
  contentHref: string,
  fallbackName = 'bank-material.pdf',
): Promise<void> {
  const path = contentHrefToApiPath(contentHref)
  const { blob, filename } = await apiRequestBlob(path)
  const name = filename && filename.toLowerCase().endsWith('.pdf') ? filename : fallbackName
  const url = URL.createObjectURL(blob)
  try {
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.rel = 'noopener'
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    a.remove()
  } finally {
    // Defer revoke so the browser can start the download
    window.setTimeout(() => URL.revokeObjectURL(url), 2_000)
  }
}

export function pdfErrorUserCopy(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return 'Войдите снова, чтобы скачать оригинал'
    if (err.code === 'BANK_MATERIALS_NOT_CONFIGURED' || err.status === 503) {
      return 'Материалы банка в этой среде пока не подключены'
    }
    if (err.code === 'BANK_FILE_UNAVAILABLE') {
      return 'Оригинал документа сейчас недоступен'
    }
    if (err.code === 'BANK_FILE_INTEGRITY' || err.status === 409) {
      return 'Файл не прошёл проверку целостности — скачивание отменено'
    }
    if (err.status === 404) return 'Оригинал документа не найден'
    if (err.code === 'UNEXPECTED_JSON') return err.message
    return err.message || 'Не удалось скачать PDF'
  }
  if (err instanceof Error) return err.message
  return 'Не удалось скачать PDF'
}
