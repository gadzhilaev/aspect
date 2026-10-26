import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { createServer } from 'vite'
import react from '@vitejs/plugin-react'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'

let server, Card, api
const oldFetch = globalThis.fetch
const oldStorage = globalThis.localStorage
const storage = new Map()
before(async () => {
  globalThis.localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: key => storage.delete(key),
  }
  server = await createServer({ configFile: false, plugins: [react()], server: { middlewareMode: true, watch: null }, appType: 'custom' })
  Card = (await server.ssrLoadModule('/src/components/news/ForYouNewsCard.tsx')).ForYouNewsCard
  api = await server.ssrLoadModule('/src/api/endpoints.ts')
})
after(async () => {
  globalThis.fetch = oldFetch
  if (oldStorage === undefined) delete globalThis.localStorage
  else globalThis.localStorage = oldStorage
  await server?.close()
})

function render(overrides) {
  const event = { id: 'test-event', title: 'Новость', category: 'electronics', confidence: 0,
    updated_at: '2026-10-26', reason_summary: 'Совпадает бренд', impact_score: null, ...overrides }
  return renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(Card, { event })))
}
test('render industry match: discussion CTA, no score/confidence/exposure', () => {
  const html = render({ score_kind: 'industry_profile_match', exposure: { value: 24, unit: 'percent' } })
  assert.ok(html.includes('/events/test-event/assistant'))
  assert.ok(!html.includes('/events/test-event/impact'))
  assert.ok(!html.includes('Качество данных'))
  assert.ok(!html.includes('24%'))
})
test('render known zero calculated score: retains impact CTA and zero', () => {
  const html = render({ score_kind: 'company_calculated', impact_score: 0, impact_score_available: true })
  assert.ok(html.includes('/events/test-event/impact'))
  assert.ok(html.includes('Индекс влияния 0'))
})
test('API calls use the existing mobile routes and exact JSON bodies', async () => {
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null })
    return Response.json({})
  }
  await api.companyApi.industryProfile('company a')
  await api.companyApi.patchIndustryProfile('company a', { brands: [] })
  await api.authApi.preferences({ theme_mode: 'dark' })
  await api.authApi.changePassword('current-example', 'new-example')
  await api.authApi.deleteAccount('current-example')
  assert.deepEqual(calls.map(c => [new URL(c.url, 'http://test').pathname, c.method, c.body]), [
    ['/api/v1/companies/company%20a/industry-profile', 'GET', null],
    ['/api/v1/companies/company%20a/industry-profile', 'PATCH', { brands: [] }],
    ['/api/v1/users/me/preferences', 'PATCH', { theme_mode: 'dark' }],
    ['/api/v1/users/me/change-password', 'POST', { current_password: 'current-example', new_password: 'new-example' }],
    ['/api/v1/users/me', 'DELETE', { password: 'current-example' }],
  ])
})
test('wrong account password 401: preserve server error, no automatic refresh/retry', async () => {
  let calls = 0
  globalThis.fetch = async () => {
    calls++
    return Response.json({ error: { code: 'INVALID_CREDENTIALS', message: 'Неверный пароль' } }, { status: 401 })
  }
  await assert.rejects(api.authApi.changePassword('wrong-example', 'new-example'), err => err.code === 'INVALID_CREDENTIALS')
  assert.equal(calls, 1)
})
test('delete refusal stays a failure; never converted to success', async () => {
  globalThis.fetch = async () => Response.json({ error: { code: 'SOLE_OWNER', message: 'Нельзя удалить аккаунт' } }, { status: 409 })
  await assert.rejects(api.authApi.deleteAccount('example'), err => err.code === 'SOLE_OWNER')
})
