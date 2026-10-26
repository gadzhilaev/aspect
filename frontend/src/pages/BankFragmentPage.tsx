import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { bankMaterialsApi } from '../api/endpoints'
import type { BankDocumentDetail, BankFragmentDetail } from '../api/bankMaterialsTypes'
import { useAuth } from '../auth/AuthContext'
import { StateBlock } from '../components/ui/StateBlock'
import {
  contentTypeLabel,
  formatPublicationDate,
  pageLabel,
  qaMethodUserCopy,
  textKindCaption,
} from '../lib/bankMaterialsDisplay'
import { downloadBankPdf, pdfErrorUserCopy } from '../lib/bankPdfDownload'

function fragmentErrorCopy(err: unknown): { title: string; description: string } {
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return {
        title: 'Нужна авторизация',
        description: 'Войдите снова, чтобы открыть материал банка.',
      }
    }
    if (err.code === 'BANK_MATERIALS_NOT_CONFIGURED' || err.status === 503) {
      return {
        title: 'Сервис не настроен',
        description: 'Материалы банка в этой среде пока не подключены.',
      }
    }
    if (err.status === 404) {
      return {
        title: 'Материал не найден',
        description: 'Фрагмент недоступен или отсутствует в разрешённом корпусе.',
      }
    }
    return {
      title: 'Не удалось загрузить материал',
      description: err.message || 'Попробуйте позже.',
    }
  }
  return {
    title: 'Не удалось загрузить материал',
    description: err instanceof Error ? err.message : 'Попробуйте позже.',
  }
}

export function BankFragmentPage() {
  const { fragmentId = '' } = useParams()
  const [search] = useSearchParams()
  const { user } = useAuth()

  const conversationId = search.get('conversation')
  const eventId = search.get('event')

  const [fragment, setFragment] = useState<BankFragmentDetail | null>(null)
  const [document, setDocument] = useState<BankDocumentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const [reloadTick, setReloadTick] = useState(0)
  const [pdfBusy, setPdfBusy] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setFragment(null)
    setDocument(null)
    setError(null)
    setPdfError(null)
    if (!fragmentId || !user) {
      setLoading(false)
      if (!user) {
        setError(
          new ApiError(401, {
            error: { code: 'UNAUTHORIZED', message: 'Требуется вход' },
          }),
        )
      }
      return
    }
    ;(async () => {
      setLoading(true)
      try {
        const frag = await bankMaterialsApi.fragment(fragmentId)
        if (cancelled) return
        setFragment(frag)
        try {
          const doc = await bankMaterialsApi.document(frag.document_id)
          if (!cancelled) setDocument(doc)
        } catch {
          // Document is supplementary — fragment still usable
          if (!cancelled) setDocument(null)
        }
      } catch (e) {
        if (!cancelled) setError(e)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [fragmentId, user, reloadTick])

  async function onDownloadPdf() {
    if (!fragment?.content_href) {
      setPdfError('Оригинал документа недоступен')
      return
    }
    setPdfBusy(true)
    setPdfError(null)
    try {
      const nameBase =
        (document?.title || fragment.document_title || 'bank-material')
          .replace(/[^\w\u0400-\u04FF\-]+/g, '_')
          .slice(0, 80) || 'bank-material'
      await downloadBankPdf(fragment.content_href, `${nameBase}.pdf`)
    } catch (e) {
      setPdfError(pdfErrorUserCopy(e))
    } finally {
      setPdfBusy(false)
    }
  }

  const backHref = eventId
    ? `/events/${encodeURIComponent(eventId)}/assistant`
    : conversationId
      ? '/scenarios'
      : '/news/for-you'

  if (loading) {
    return (
      <div className="container page-pad bank-fragment-page">
        <StateBlock variant="loading" title="Открываем материал банка" />
      </div>
    )
  }

  if (error || !fragment) {
    const copy = fragmentErrorCopy(error ?? new Error('not found'))
    return (
      <div className="container page-pad bank-fragment-page">
        <Link to={backHref} className="btn btn-secondary bank-fragment-back">
          ← К обсуждению
        </Link>
        <StateBlock
          variant="error"
          title={copy.title}
          description={copy.description}
          onRetry={user ? () => setReloadTick((t) => t + 1) : undefined}
        />
      </div>
    )
  }

  const pub = formatPublicationDate({
    publication_date: document?.publication_date ?? null,
    publication_date_precision: document?.publication_date_precision,
    publication_date_display: document?.publication_date_display,
    publication_year: document?.publication_year,
    publication_month: document?.publication_month,
  })
  const page = pageLabel(fragment.page_number)
  const kind = textKindCaption(fragment.text_kind)
  const qa = qaMethodUserCopy(fragment.qa_method)
  const restricted = fragment.text_restricted || fragment.text_kind === 'restricted'
  const title = document?.title || fragment.document_title || 'Материал банка'

  return (
    <div className="container page-pad bank-fragment-page">
      <Link to={backHref} className="btn btn-secondary bank-fragment-back">
        ← К обсуждению
      </Link>

      <header className="bank-fragment-hero">
        <p className="bank-fragment-eyebrow">Материал банка</p>
        <h1 className="page-title bank-fragment-title">{title}</h1>
        <p className="muted bank-fragment-pub">{pub}</p>
        {fragment.is_superseded ? (
          <p className="bank-fragment-superseded" role="status">
            В этом ответе использована предыдущая версия фрагмента
          </p>
        ) : null}
      </header>

      <section className="bank-fragment-main">
        <div className="bank-fragment-type">{contentTypeLabel(fragment.content_type)}</div>
        {page ? <div className="muted bank-fragment-page-no">{page}</div> : null}
        {kind ? <div className="muted bank-fragment-kind">{kind}</div> : null}

        {restricted ? (
          <div className="bank-fragment-restricted" role="status">
            <p>Текст этого фрагмента ограничен для просмотра.</p>
            <p className="muted">
              Сырой OCR и непроверенный текст не показываются. Метаданные материала доступны ниже.
            </p>
          </div>
        ) : fragment.text ? (
          <blockquote
            className={`bank-fragment-text${fragment.text_kind === 'exact_quote' ? ' is-quote' : ''}`}
          >
            {fragment.text}
          </blockquote>
        ) : (
          <p className="muted">Текст фрагмента недоступен.</p>
        )}

        {qa ? <p className="bank-fragment-qa muted">{qa}</p> : null}
      </section>

      <section className="bank-fragment-about" aria-labelledby="bank-about-heading">
        <h2 id="bank-about-heading" className="bank-fragment-about-title">
          Об источнике
        </h2>
        <dl className="bank-fragment-about-list">
          <div>
            <dt>Документ</dt>
            <dd>{title}</dd>
          </div>
          <div>
            <dt>Публикация</dt>
            <dd>{pub}</dd>
          </div>
          {document?.period_covered ? (
            <div>
              <dt>Период в материале</dt>
              <dd>{document.period_covered}</dd>
            </div>
          ) : null}
          {document?.staleness_note ? (
            <div>
              <dt>Актуальность</dt>
              <dd>{document.staleness_note}</dd>
            </div>
          ) : null}
          {document?.topics?.length ? (
            <div>
              <dt>Темы</dt>
              <dd>{document.topics.join(', ')}</dd>
            </div>
          ) : null}
        </dl>
        <p className="muted bank-fragment-disclaimer">
          Это материал банка, а не рекомендация для вашей компании.
        </p>
      </section>

      <div className="bank-fragment-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={pdfBusy || !fragment.content_href}
          onClick={() => void onDownloadPdf()}
        >
          {pdfBusy ? 'Скачиваем…' : 'Открыть оригинальный PDF'}
        </button>
        {pdfError ? <p className="bank-fragment-pdf-error">{pdfError}</p> : null}
        {!fragment.content_href ? (
          <p className="muted">Ссылка на оригинал недоступна.</p>
        ) : null}
      </div>

    </div>
  )
}
