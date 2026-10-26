/** Prefix public assets with Vite base (e.g. /aspekt/). */
export function publicUrl(path: string): string {
  const base = import.meta.env.BASE_URL || '/'
  const p = path.replace(/^\//, '')
  return `${base}${p}`
}
