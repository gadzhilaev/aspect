/**
 * Pure helpers for SafeMarkdown (testable without React/TSX loader).
 */

export function isSafeHref(href: string): boolean {
  const t = href.trim().toLowerCase()
  return t.startsWith('https://') || t.startsWith('http://') || t.startsWith('/')
}

export type MdInline =
  | { kind: 'text'; text: string }
  | { kind: 'code'; text: string }
  | { kind: 'strong'; text: string }
  | { kind: 'em'; text: string }
  | { kind: 'link'; text: string; href: string }

export function parseInline(text: string): MdInline[] {
  const nodes: MdInline[] = []
  const re =
    /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[[^\]]+\]\([^)]+\))/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      nodes.push({ kind: 'text', text: text.slice(last, m.index) })
    }
    const token = m[0]
    if (token.startsWith('`')) {
      nodes.push({ kind: 'code', text: token.slice(1, -1) })
    } else if (token.startsWith('**')) {
      nodes.push({ kind: 'strong', text: token.slice(2, -2) })
    } else if (token.startsWith('*')) {
      nodes.push({ kind: 'em', text: token.slice(1, -1) })
    } else if (token.startsWith('[')) {
      const lm = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token)
      if (lm && isSafeHref(lm[2])) {
        nodes.push({ kind: 'link', text: lm[1], href: lm[2] })
      } else {
        nodes.push({ kind: 'text', text: token })
      }
    } else {
      nodes.push({ kind: 'text', text: token })
    }
    last = m.index + token.length
  }
  if (last < text.length) {
    nodes.push({ kind: 'text', text: text.slice(last) })
  }
  return nodes
}

export type MdBlock =
  | { kind: 'p' | 'heading'; lines: string[] }
  | { kind: 'ul' | 'ol'; items: string[] }

function isUl(line: string): boolean {
  return /^\s*[-*]\s+/.test(line)
}
function isOl(line: string): boolean {
  return /^\s*\d+\.\s+/.test(line)
}

export function parseBlocks(text: string): MdBlock[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: MdBlock[] = []
  let buf: string[] = []

  const flush = () => {
    if (!buf.length) return
    if (buf.every(isUl)) {
      blocks.push({
        kind: 'ul',
        items: buf.map((ln) => ln.replace(/^\s*[-*]\s+/, '')),
      })
    } else if (buf.every(isOl)) {
      blocks.push({
        kind: 'ol',
        items: buf.map((ln) => ln.replace(/^\s*\d+\.\s+/, '')),
      })
    } else if (buf.length === 1 && /^#{1,3}\s+/.test(buf[0] ?? '')) {
      blocks.push({
        kind: 'heading',
        lines: [(buf[0] ?? '').replace(/^#{1,3}\s+/, '')],
      })
    } else {
      blocks.push({ kind: 'p', lines: [...buf] })
    }
    buf = []
  }

  for (const line of lines) {
    if (line.trim() === '') {
      flush()
      continue
    }
    if (buf.length) {
      const prevList = isUl(buf[0] ?? '') || isOl(buf[0] ?? '')
      const curList = isUl(line) || isOl(line)
      if (prevList !== curList) flush()
      else if (prevList && isUl(buf[0] ?? '') !== isUl(line)) flush()
    }
    buf.push(line)
  }
  flush()
  return blocks
}
