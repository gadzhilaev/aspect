/** Bank analytics cards on the news detail page (stage 6.12). Bearer-only. */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { eventsApi } from '../../api/endpoints'
import type { EventBankEvidenceItem } from '../../api/bankMaterialsTypes'
import { useAsync } from '../../hooks/useAsync'
import {
  NEWS_BANK_THEMATIC_DISCLAIMER,
  emptyNewsBankEvidenceCopy,
  formatPublicationDate,
  fragmentDetailPath,
  newsContentTypeLabel,
  pageLabel,
  parseEventBankEvidence,
  previewText,
  textKindCaption,
} from '../../lib/bankMaterialsDisplay'

type Props = {
  eventId: string
  /** When set, passed as ACL-only company_id (not used for matching). */
  companyId?: string | null
  /** Guest / no token: do not call protected API. */
  enabled: boolean
}

function NewsBankCard({
  item,
  eventId,
  companyId,
}: {
  item: EventBankEvidenceItem
  eventId: string
  companyId?: string | null
}) {
  const [expanded, setExpanded] = useState(false)
  const { preview, truncated } = previewText(item.text, 200)
  const kind = textKindCaption(item.text_kind)
  const page = pageLabel(item.page_number)
  const pub = formatPublicationDate({
    publication_date: item.publication_date,
    publication_date_precision: item.publication_date_precision,
    publication_date_display: item.publication_date_display,
    publication_year: item.publication_year,
    publication_month: item.publication_month,
  })
  const href = fragmentDetailPath(item.fragment_id, { eventId, companyId })

  return (
    <li className="bank-evidence-card news-bank-card">
      <div className="bank-evidence-card-eyebrow">Аналитика Альфа-Банка</div>
      <div className="bank-evidence-card-title">
        {item.document_title?.trim() || 'Документ банка'}
      </div>
      <div className="bank-evidence-card-meta muted">
        <span>{pub}</span>
        {page ? <span>· {page}</span> : null}
      </div>
      <div className="bank-evidence-card-type">{newsContentTypeLabel(item.content_type)}</div>
      {kind ? <div className="bank-evidence-card-kind muted">{kind}</div> : null}
      {item.text ? (
        <div
          className={`bank-evidence-card-text${item.text_kind === 'exact_quote' ? ' is-quote' : ''}`}
        >
          {expanded || !truncated ? item.text : preview}
          {truncated ? (
            <button
              type="button"
              className="bank-evidence-expand"
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? 'Свернуть' : 'Показать полностью'}
            </button>
          ) : null}
        </div>
      ) : null}
      <div className="bank-evidence-card-actions">
        <Link className="btn btn-secondary bank-evidence-open" to={href}>
          Посмотреть материал
        </Link>
      </div>
    </li>
  )
}

export function NewsBankAnalytics({ eventId, companyId, enabled }: Props) {
  const load = useAsync(async () => {
    if (!enabled || !eventId) return null
    return eventsApi.bankEvidence(eventId, companyId)
  }, [enabled, eventId, companyId])

  if (!enabled) return null

  if (load.loading) {
    return (
      <section className="article-section news-bank-analytics" aria-busy="true">
        <h2 className="article-section-title">Аналитика Альфа-Банка</h2>
        <p className="muted news-bank-analytics-status">Загружаем материалы банка…</p>
      </section>
    )
  }

  if (load.error) {
    const unauthorized =
      load.error instanceof ApiError && (load.error.status === 401 || load.error.status === 403)
    return (
      <section className="article-section news-bank-analytics" aria-live="polite">
        <h2 className="article-section-title">Аналитика Альфа-Банка</h2>
        <p className="muted news-bank-analytics-status">
          {unauthorized
            ? 'Чтобы увидеть материалы банка, войдите в аккаунт.'
            : 'Не удалось загрузить материалы банка.'}
        </p>
        {!unauthorized ? (
          <button type="button" className="btn btn-secondary" onClick={load.reload}>
            Повторить
          </button>
        ) : null}
      </section>
    )
  }

  const parsed = parseEventBankEvidence(load.data)
  if (!parsed) {
    return (
      <section className="article-section news-bank-analytics" aria-live="polite">
        <h2 className="article-section-title">Аналитика Альфа-Банка</h2>
        <p className="muted news-bank-analytics-status">
          Не удалось разобрать ответ по материалам банка.
        </p>
        <button type="button" className="btn btn-secondary" onClick={load.reload}>
          Повторить
        </button>
      </section>
    )
  }

  const emptyCopy = emptyNewsBankEvidenceCopy(parsed.status)
  const items = parsed.evidence

  if (!items.length) {
    return (
      <section className="article-section news-bank-analytics" aria-live="polite">
        <h2 className="article-section-title">Аналитика Альфа-Банка</h2>
        <p className="muted news-bank-analytics-status">
          {emptyCopy ?? 'Подходящих проверенных материалов банка для этой новости нет'}
        </p>
        <p className="muted news-bank-analytics-disclaimer">{NEWS_BANK_THEMATIC_DISCLAIMER}</p>
      </section>
    )
  }

  return (
    <section className="article-section news-bank-analytics" aria-label="Аналитика Альфа-Банка">
      <h2 className="article-section-title">Аналитика Альфа-Банка</h2>
      <p className="muted news-bank-analytics-disclaimer">{NEWS_BANK_THEMATIC_DISCLAIMER}</p>
      <ul className="bank-evidence-list news-bank-list">
        {items.map((item) => (
          <NewsBankCard
            key={`${item.fragment_id}:${item.revision}`}
            item={item}
            eventId={eventId}
            companyId={companyId}
          />
        ))}
      </ul>
    </section>
  )
}
