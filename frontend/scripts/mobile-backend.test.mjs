import assert from 'node:assert/strict'
import { test } from 'node:test'
import { industryDraft, industryPatch, splitInterests } from '../src/lib/industryProfile.ts'
import { isProfileOnly } from '../src/lib/profileFeed.ts'

const original = {
  activity_role: 'retailer', product_categories: ['Смартфоны'], brands: ['Apple'],
  product_lines: ['iPhone'], sales_markets: ['Россия'], procurement_countries: ['Китай'],
  purchase_currencies: ['CNY'],
}
test('unchanged industry form produces no PATCH', () => {
  assert.deepEqual(industryPatch(original, industryDraft(original)), {})
})
test('only edited field is sent; currencies and other mobile fields are preserved', () => {
  assert.deepEqual(industryPatch(original, { ...industryDraft(original), brands: 'Samsung' }), { brands: ['Samsung'] })
})
test('clearing interests sends an explicit empty array', () => {
  assert.deepEqual(industryPatch(original, { ...industryDraft(original), brands: '' }), { brands: [] })
})
test('normalization removes duplicates without replacing user names', () => {
  assert.deepEqual(splitInterests(' Apple, apple ; Samsung\n  Redmi   Note '), ['Apple', 'Samsung', 'Redmi Note'])
})
test('case and industry matches have no numerical impact UI', () => {
  for (const score_kind of ['industry_profile_match', 'case_profile_match']) assert.equal(isProfileOnly({ score_kind }), true)
  assert.equal(isProfileOnly({ inclusion_bases: ['industry_profile'] }), true)
})
test('combined calculated/profile basis retains impact UI, including known zero', () => {
  assert.equal(isProfileOnly({ score_kind: 'company_calculated', inclusion_bases: ['calculated_impact', 'industry_profile'], impact_score: 0 }), false)
  assert.equal(isProfileOnly({ inclusion_bases: ['event_severity_signal', 'industry_profile'] }), false)
})
