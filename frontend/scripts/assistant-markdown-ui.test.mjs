/**
 * Safe Markdown logic — no live LLM, no React/TSX loader.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const libUrl = pathToFileURL(join(root, 'src/lib/safeMarkdownLogic.ts')).href
const { isSafeHref, parseBlocks, parseInline } = await import(libUrl)

describe('safeMarkdownLogic', () => {
  it('parses paragraphs, bold and lists', () => {
    const blocks = parseBlocks('**Короткий ответ**\n\n- пункт один\n- пункт два\n\nОбычный абзац.')
    assert.equal(blocks[0].kind, 'p')
    assert.deepEqual(
      parseInline(blocks[0].lines[0]).map((n) => n.kind),
      ['strong'],
    )
    assert.equal(blocks[1].kind, 'ul')
    assert.equal(blocks[1].items[0], 'пункт один')
    assert.equal(blocks[2].kind, 'p')
  })

  it('allows https and relative links; blocks javascript:', () => {
    assert.equal(isSafeHref('https://example.com/a'), true)
    assert.equal(isSafeHref('/news/x'), true)
    assert.equal(isSafeHref('javascript:alert(1)'), false)
    const bad = parseInline('[x](javascript:alert(1))')
    assert.equal(bad[0].kind, 'text')
    const ok = parseInline('[ok](https://example.com/a)')
    assert.equal(ok[0].kind, 'link')
    assert.equal(ok[0].href, 'https://example.com/a')
  })

  it('keeps raw angle brackets as text (no HTML execution path)', () => {
    const nodes = parseInline('Hello <script>alert(1)</script>')
    assert.equal(nodes.every((n) => n.kind === 'text'), true)
    assert.match(nodes.map((n) => n.text).join(''), /<script>/)
  })
})
