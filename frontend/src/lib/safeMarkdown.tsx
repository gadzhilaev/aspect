import type { ReactNode } from 'react'
import { parseBlocks, parseInline, type MdInline } from './safeMarkdownLogic'

function renderInlineNodes(nodes: MdInline[], keyPrefix: string): ReactNode[] {
  return nodes.map((n, i) => {
    const k = `${keyPrefix}-${i}`
    if (n.kind === 'text') return <span key={k}>{n.text}</span>
    if (n.kind === 'code')
      return (
        <code key={k} className="assistant-md-code">
          {n.text}
        </code>
      )
    if (n.kind === 'strong') return <strong key={k}>{n.text}</strong>
    if (n.kind === 'em') return <em key={k}>{n.text}</em>
    const external = !n.href.startsWith('/')
    return (
      <a
        key={k}
        href={n.href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
      >
        {n.text}
      </a>
    )
  })
}

export function SafeMarkdown({ text }: { text: string }) {
  if (!text) return null
  const blocks = parseBlocks(text)
  return (
    <div className="assistant-md">
      {blocks.map((b, bi) => {
        const key = `b-${bi}`
        if (b.kind === 'ul') {
          return (
            <ul key={key} className="assistant-md-list">
              {b.items.map((item, idx) => (
                <li key={`${key}-li-${idx}`}>
                  {renderInlineNodes(parseInline(item), `${key}-li-${idx}`)}
                </li>
              ))}
            </ul>
          )
        }
        if (b.kind === 'ol') {
          return (
            <ol key={key} className="assistant-md-list">
              {b.items.map((item, idx) => (
                <li key={`${key}-ol-${idx}`}>
                  {renderInlineNodes(parseInline(item), `${key}-ol-${idx}`)}
                </li>
              ))}
            </ol>
          )
        }
        if (b.kind !== 'p' && b.kind !== 'heading') return null
        const cls = b.kind === 'heading' ? 'assistant-md-heading' : 'assistant-md-p'
        return (
          <p key={key} className={cls}>
            {b.lines.map((ln: string, idx: number) => (
              <span key={`${key}-ln-${idx}`}>
                {idx > 0 ? <br /> : null}
                {renderInlineNodes(parseInline(ln), `${key}-ln-${idx}`)}
              </span>
            ))}
          </p>
        )
      })}
    </div>
  )
}
