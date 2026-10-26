/**
 * Stage 4.8 — discoverability UI wiring (no browser / no React render).
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const src = (rel) => readFileSync(join(root, 'src', rel), 'utf8')

describe('empty states link to public news', () => {
  it('ForYouPage empty state has «Все новости» → /news', () => {
    const page = src('pages/ForYouPage.tsx')
    assert.match(page, /Все новости/)
    // Server may supply feed_empty.primary_href; fallback remains public /news.
    assert.match(page, /primary_href \|\| '\/news'/)
    assert.match(page, /Персональных сигналов пока нет/)
  })

  it('ScenariosPage empty state offers /news and /news/for-you', () => {
    const page = src('pages/ScenariosPage.tsx')
    assert.match(page, /to="\/news"/)
    assert.match(page, /to="\/news\/for-you"/)
    assert.match(page, /Все новости/)
  })
})

describe('agent demo stand is env-gated', () => {
  it('agentDemo helper reads VITE_AGENT_DEMO', () => {
    const lib = src('lib/agentDemo.ts')
    assert.match(lib, /VITE_AGENT_DEMO/)
    assert.match(lib, /\/agent-demo/)
  })

  it('AppRoutes mounts /agent-demo only when isAgentDemoStand()', () => {
    const routes = src('routes/AppRoutes.tsx')
    assert.match(routes, /isAgentDemoStand\(\)/)
    assert.match(routes, /path="agent-demo"/)
    assert.match(routes, /AgentDemoPage/)
  })

  it('AgentDemoPage uses existing product paths from API', () => {
    const page = src('pages/AgentDemoPage.tsx')
    assert.match(page, /agentDemoApi\.entry/)
    assert.match(page, /data\.news_path/)
    assert.match(page, /data\.assistant_path/)
    assert.match(page, /data\.scenarios_path/)
    assert.match(page, /синтетика/i)
  })

  it('postLoginPath lands on demo home when stand flag is on', () => {
    const setup = src('lib/setupPath.ts')
    assert.match(setup, /isAgentDemoStand\(\)/)
    assert.match(setup, /agentDemoHomePath\(\)/)
  })
})
