/**
 * Adapter/data contract tests for bank materials UI (этап 2.15).
 * No vitest — node:test. No browser / CDP / visual checks.
 * Pure display helpers loaded via --experimental-strip-types.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

const {
  formatPublicationDate,
  parseBankEvidenceListData,
  emptyBankEvidenceUserCopy,
  contentTypeLabel,
  textKindCaption,
  previewText,
  fragmentDetailPath,
  qaMethodUserCopy,
} = await import('../src/lib/bankMaterialsDisplay.ts')

const chatSrc = readFileSync(join(root, 'src/components/assistant/AssistantChat.tsx'), 'utf8')
const blockSrc = readFileSync(join(root, 'src/components/assistant/BankEvidenceBlock.tsx'), 'utf8')
const pageSrc = readFileSync(join(root, 'src/pages/BankFragmentPage.tsx'), 'utf8')
const routesSrc = readFileSync(join(root, 'src/routes/AppRoutes.tsx'), 'utf8')
const clientSrc = readFileSync(join(root, 'src/api/client.ts'), 'utf8')
const pdfSrc = readFileSync(join(root, 'src/lib/bankPdfDownload.ts'), 'utf8')
const typesSrc = readFileSync(join(root, 'src/api/assistantTypes.ts'), 'utf8')
const bankTypesSrc = readFileSync(join(root, 'src/api/bankMaterialsTypes.ts'), 'utf8')
const endpointsSrc = readFileSync(join(root, 'src/api/endpoints.ts'), 'utf8')

describe('types & routes', () => {
  it('declares bank_evidence_list block type', () => {
    assert.match(typesSrc, /'bank_evidence_list'/)
    assert.match(bankTypesSrc, /BankUsedFragment/)
    assert.match(bankTypesSrc, /BankEvidenceListData/)
  })

  it('registers fragment route under ProtectedRoute', () => {
    assert.match(routesSrc, /bank-materials\/fragments\/:fragmentId/)
    assert.match(routesSrc, /BankFragmentPage/)
    assert.match(routesSrc, /ProtectedRoute/)
  })

  it('wires bankMaterialsApi paths', () => {
    assert.match(endpointsSrc, /bankMaterialsApi/)
    assert.match(endpointsSrc, /\/api\/v1\/bank-materials\/fragments\//)
    assert.match(endpointsSrc, /\/api\/v1\/bank-materials\/documents\//)
  })
})

describe('fixtures: bank_evidence_list parsing', () => {
  it('old message without block → parse returns null / chat ignores missing', () => {
    assert.equal(parseBankEvidenceListData(undefined), null)
    assert.equal(parseBankEvidenceListData(null), null)
    assert.match(chatSrc, /block\.type === 'bank_evidence_list'/)
    // Unknown types still fall through to null without crashing other blocks
    assert.match(chatSrc, /return null/)
  })

  it('used with exact quote and summary', () => {
    const data = parseBankEvidenceListData({
      status: 'available',
      used: [
        {
          fragment_id: 'f1',
          revision: 2,
          text_kind: 'exact_quote',
          text: 'Цитата банка про ставку',
          content_type: 'fact',
          document_title: 'Macro Insights',
          publication_date: '2026-09-11',
          publication_date_precision: 'day',
          page_number: 3,
        },
        {
          fragment_id: 'f2',
          revision: 1,
          text_kind: 'summary',
          text: 'Пересказ прогноза инфляции',
          content_type: 'forecast',
          document_title: 'FI Strategy',
          publication_date: '2026-07',
          publication_date_precision: 'month',
          page_number: 5,
        },
      ],
      diagnostics: {
        retrieved_ids: ['x'],
        passed_to_provider_ids: ['f1', 'f2', 'f3'],
        cited_by_model: ['f1'],
      },
    })
    assert.ok(data)
    assert.equal(data.used.length, 2)
    assert.equal(data.used[0].text_kind, 'exact_quote')
    assert.equal(data.used[0].revision, 2)
    assert.equal(data.used[1].text_kind, 'summary')
    assert.equal(textKindCaption('summary'), 'Пересказ')
    assert.equal(textKindCaption('exact_quote'), 'Точная цитата')
    assert.equal(contentTypeLabel('fact'), 'Факт из материала')
    assert.equal(contentTypeLabel('forecast'), 'Прогноз банка')
    assert.equal(contentTypeLabel('interpretation'), 'Оценка банка')
    assert.equal(contentTypeLabel('weird_enum'), 'Материал банка')
    // Cards render only used — diagnostics not in card UI
    assert.doesNotMatch(blockSrc, /retrieved_ids|passed_to_provider|cited_by_model|diagnostics/)
  })

  it('used empty + available → no empty list (null copy)', () => {
    const data = parseBankEvidenceListData({ status: 'available', used: [], available: true })
    assert.ok(data)
    assert.equal(data.used.length, 0)
    assert.equal(emptyBankEvidenceUserCopy('available'), null)
  })

  it('fetch_error → compact human message', () => {
    assert.equal(
      emptyBankEvidenceUserCopy('fetch_error'),
      'Материалы банка временно недоступны',
    )
  })

  it('unknown content_type stays friendly', () => {
    assert.equal(contentTypeLabel('recommendation_for_company'), 'Материал банка')
    assert.doesNotMatch(blockSrc, /рекомендац/i)
  })
})

describe('publication date precision', () => {
  it('month precision does not invent day 1', () => {
    const s = formatPublicationDate({
      publication_date: '2026-07-01',
      publication_date_precision: 'month',
      publication_year: 2026,
      publication_month: 7,
    })
    assert.match(s, /июль/i)
    assert.match(s, /2026/)
    assert.doesNotMatch(s, /\b1\b/)
    assert.doesNotMatch(s, /01/)
  })

  it('day precision keeps calendar day', () => {
    const s = formatPublicationDate({
      publication_date: '2026-09-11',
      publication_date_precision: 'day',
    })
    assert.equal(s, '11 сентября 2026')
  })

  it('display field preferred when present', () => {
    assert.equal(
      formatPublicationDate({
        publication_date_display: 'сентябрь 2026',
        publication_date_precision: 'month',
      }),
      'сентябрь 2026',
    )
  })
})

describe('quote preview expand (no fake continuous splice)', () => {
  it('marks truncation and keeps full text available via expand UI', () => {
    const long = 'А'.repeat(250)
    const { preview, truncated } = previewText(long, 180)
    assert.equal(truncated, true)
    assert.ok(preview.length < long.length)
    assert.match(blockSrc, /Показать полностью/)
    assert.doesNotMatch(blockSrc, /\[\.\.\.\]|\u2026\s*\+/)
  })
})

describe('fragment page contracts', () => {
  it('loads exact fragment id then document; no latest-revision redirect', () => {
    assert.match(pageSrc, /bankMaterialsApi\.fragment\(fragmentId\)/)
    assert.match(pageSrc, /bankMaterialsApi\.document\(frag\.document_id\)/)
    assert.doesNotMatch(pageSrc, /latest_revision\s*[?=]/)
    assert.doesNotMatch(pageSrc, /max\(.*revision/)
  })

  it('superseded + restricted + QA copy', () => {
    assert.match(pageSrc, /предыдущая версия фрагмента/)
    assert.match(pageSrc, /text_restricted|restricted/)
    assert.doesNotMatch(pageSrc, /raw OCR|raw_ocr/i)
    assert.equal(
      qaMethodUserCopy('ai_vision'),
      'Сверено AI по изображению документа',
    )
    assert.match(pageSrc, /Сверено AI|qaMethodUserCopy/)
    assert.doesNotMatch(pageSrc, /человеческ(ая|ой) проверк/i)
    assert.doesNotMatch(pageSrc, /pdf_sha256|ocr_fingerprint/)
  })

  it('fragment path helper keeps nav query without tokens', () => {
    const p = fragmentDetailPath('abc-1', {
      conversationId: 'c1',
      eventId: 'e1',
      companyId: 'co1',
    })
    assert.match(p, /^\/bank-materials\/fragments\/abc-1\?/)
    assert.doesNotMatch(p, /access_token|Bearer|refresh/i)
  })
})

describe('PDF auth download', () => {
  it('uses Bearer via apiRequestBlob — not window.open / query token', () => {
    assert.match(clientSrc, /export async function apiRequestBlob/)
    assert.match(clientSrc, /Authorization.*Bearer/)
    assert.match(clientSrc, /UNEXPECTED_JSON|application\/json/)
    assert.match(pdfSrc, /downloadBankPdf/)
    assert.match(pdfSrc, /apiRequestBlob/)
    assert.match(pdfSrc, /URL\.createObjectURL/)
    assert.match(pdfSrc, /revokeObjectURL/)
    assert.doesNotMatch(pdfSrc, /window\.open\s*\(/)
    assert.doesNotMatch(pdfSrc, /access_token=/)
    assert.match(pageSrc, /downloadBankPdf/)
    assert.doesNotMatch(pageSrc, /window\.open\s*\(/)
  })
})

describe('chat separation & history snapshot', () => {
  it('keeps news sources and bank materials as separate blocks', () => {
    assert.match(chatSrc, /Источники новости/)
    assert.match(blockSrc, /Материал банка/)
    assert.match(chatSrc, /bank_evidence_list/)
    // History uses stored text — no refetch of used cards from API
    assert.doesNotMatch(blockSrc, /bankMaterialsApi/)
  })
})
