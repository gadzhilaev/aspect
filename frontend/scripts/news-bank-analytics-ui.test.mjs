/**
 * Stage 6.12 — bank analytics on news detail page.
 * No browser / CDP / visual / live LLM. node:test + strip-types.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

const {
  parseEventBankEvidence,
  emptyNewsBankEvidenceCopy,
  newsContentTypeLabel,
  fragmentDetailPath,
  formatPublicationDate,
  NEWS_BANK_THEMATIC_DISCLAIMER,
  textKindCaption,
} = await import('../src/lib/bankMaterialsDisplay.ts')

const pageSrc = readFileSync(join(root, 'src/pages/NewsDetailPage.tsx'), 'utf8')
const compSrc = readFileSync(join(root, 'src/components/news/NewsBankAnalytics.tsx'), 'utf8')
const endpointsSrc = readFileSync(join(root, 'src/api/endpoints.ts'), 'utf8')
const cssSrc = readFileSync(join(root, 'src/styles/bank-materials.css'), 'utf8')

describe('wiring: news page uses bank-evidence API', () => {
  it('NewsDetailPage mounts NewsBankAnalytics after sources, Bearer-gated', () => {
    assert.match(pageSrc, /enabled=\{Boolean\(user\)\}/)
    assert.match(pageSrc, /Источники/)
    // JSX usage (not the import line) must follow the sources section.
    const sourcesIdx = pageSrc.indexOf('article-section-title">Источники')
    const bankJsxIdx = pageSrc.indexOf('<NewsBankAnalytics')
    assert.ok(sourcesIdx >= 0, 'sources heading present')
    assert.ok(bankJsxIdx > sourcesIdx, 'bank block after sources')
  })

  it('eventsApi.bankEvidence hits GET /events/{id}/bank-evidence', () => {
    assert.match(endpointsSrc, /bankEvidence/)
    assert.match(endpointsSrc, /\/bank-evidence/)
    assert.doesNotMatch(endpointsSrc, /bank-evidence.*messages/)
  })

  it('component calls eventsApi.bankEvidence and links fragment by id', () => {
    assert.match(compSrc, /eventsApi\.bankEvidence/)
    assert.match(compSrc, /fragmentDetailPath\(item\.fragment_id/)
    assert.match(compSrc, /Посмотреть материал/)
    assert.match(compSrc, /Аналитика Альфа-Банка/)
    assert.doesNotMatch(compSrc, /fetch\(|openai|gigachat|hackathon/i)
  })

  it('CSS covers news block with theme tokens and narrow width', () => {
    assert.match(cssSrc, /\.news-bank-analytics/)
    assert.match(cssSrc, /var\(--color-/)
    assert.match(cssSrc, /max-width:\s*640px/)
  })
})

describe('parse + empty states', () => {
  const sample = {
    event_id: 'evt_rate',
    status: 'available',
    event_occurred_at: '2026-09-12T12:00:00Z',
    as_of_date: '2026-09-12',
    as_of_date_basis: 'event.occurred_at',
    query_preview: 'ставка',
    limitations: ['thematic_match_is_not_bank_commentary_on_this_news'],
    empty_reason: null,
    evidence: [
      {
        fragment_id: 'frag-exact-1',
        revision: 1,
        document_id: 'doc-1',
        document_title: 'Ключевая ставка',
        document_slug: 'policy-rate',
        publication_date: '2026-09-11',
        publication_year: 2026,
        publication_month: 9,
        publication_date_precision: 'day',
        publication_date_display: null,
        page_number: 2,
        text_kind: 'exact_quote',
        text: 'Ключевая ставка сохранена на уровне 14%.',
        content_type: 'fact',
        content_type_status: 'confirmed',
        source_role: null,
        source_role_meaning: '',
        qa_method: 'ai_vision',
        document_href: '/api/v1/bank-materials/documents/doc-1',
        fragment_href: '/api/v1/bank-materials/fragments/frag-exact-1',
        content_href: '/api/v1/bank-materials/files/f1/content',
      },
      {
        fragment_id: 'frag-sum-2',
        revision: 1,
        document_id: 'doc-1',
        document_title: 'Ключевая ставка',
        document_slug: 'policy-rate',
        publication_date: '2026-09-11',
        publication_year: 2026,
        publication_month: 9,
        publication_date_precision: 'day',
        publication_date_display: null,
        page_number: 3,
        text_kind: 'summary',
        text: 'Банк ожидает снижения ставки во втором полугодии.',
        content_type: 'forecast',
        content_type_status: 'confirmed',
        source_role: null,
        source_role_meaning: '',
        qa_method: null,
        document_href: '/api/v1/bank-materials/documents/doc-1',
        fragment_href: '/api/v1/bank-materials/fragments/frag-sum-2',
        content_href: '/api/v1/bank-materials/files/f1/content',
      },
    ],
  }

  it('parses available evidence without inventing a merged quote', () => {
    const parsed = parseEventBankEvidence(sample)
    assert.equal(parsed?.status, 'available')
    assert.equal(parsed?.evidence.length, 2)
    assert.equal(parsed?.evidence[0].fragment_id, 'frag-exact-1')
    assert.equal(parsed?.evidence[0].text_kind, 'exact_quote')
    assert.match(parsed?.evidence[0].text || '', /14%/)
    assert.equal(parsed?.evidence[1].text_kind, 'summary')
    // Two separate texts — not concatenated into one fake quote
    assert.notEqual(
      `${parsed?.evidence[0].text}${parsed?.evidence[1].text}`,
      parsed?.evidence[0].text,
    )
  })

  it('skips restricted / empty / unknown text_kind rows', () => {
    const parsed = parseEventBankEvidence({
      ...sample,
      evidence: [
        { ...sample.evidence[0], text_kind: 'restricted', text: 'raw ocr leak' },
        { ...sample.evidence[0], fragment_id: 'ok', text_kind: 'exact_quote', text: 'ok' },
        { fragment_id: 'empty', text_kind: 'exact_quote', text: '  ' },
      ],
    })
    assert.equal(parsed?.evidence.length, 1)
    assert.equal(parsed?.evidence[0].fragment_id, 'ok')
  })

  it('empty status copy for news', () => {
    assert.match(emptyNewsBankEvidenceCopy('no_matching_evidence') || '', /нет/i)
    assert.match(emptyNewsBankEvidenceCopy('integration_not_configured') || '', /не подключен/i)
    assert.match(emptyNewsBankEvidenceCopy('event_date_unavailable') || '', /дат/i)
    assert.equal(emptyNewsBankEvidenceCopy('available'), null)
  })

  it('news content-type labels match product copy', () => {
    assert.equal(newsContentTypeLabel('fact'), 'Факт из материала')
    assert.equal(newsContentTypeLabel('interpretation'), 'Интерпретация')
    assert.equal(newsContentTypeLabel('forecast'), 'Прогноз')
    assert.equal(textKindCaption('exact_quote'), 'Точная цитата')
    assert.equal(textKindCaption('summary'), 'Пересказ')
  })

  it('fragment path uses exact fragment_id', () => {
    const href = fragmentDetailPath('frag-exact-1', { eventId: 'evt_rate', companyId: 'c1' })
    assert.match(href, /\/bank-materials\/fragments\/frag-exact-1/)
    assert.match(href, /event=evt_rate/)
    assert.doesNotMatch(href, /frag-sum-2/)
  })

  it('preserves publication date precision (no invented day 1)', () => {
    const month = formatPublicationDate({
      publication_date: '2026-09',
      publication_date_precision: 'month',
      publication_year: 2026,
      publication_month: 9,
    })
    assert.match(month, /сентябрь/i)
    assert.doesNotMatch(month, /^1 /)
  })

  it('thematic disclaimer is present for users', () => {
    assert.match(NEWS_BANK_THEMATIC_DISCLAIMER, /не подтверждают/i)
    assert.match(compSrc, /NEWS_BANK_THEMATIC_DISCLAIMER/)
  })
})

describe('UI states in component source', () => {
  it('covers loading, empty, error+retry, guest skip', () => {
    assert.match(compSrc, /Загружаем материалы банка/)
    assert.match(compSrc, /Повторить/)
    assert.match(compSrc, /if \(!enabled\) return null/)
    assert.match(compSrc, /emptyNewsBankEvidenceCopy/)
  })

  it('does not show technical OCR run / query_preview to users', () => {
    assert.doesNotMatch(compSrc, /query_preview|ocr_run_id|lexical_match/)
    assert.doesNotMatch(compSrc, /16%\s*\+|смешать|синтетическ/i)
  })
})
