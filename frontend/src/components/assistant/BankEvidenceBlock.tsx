import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { BankEvidenceListData, BankUsedFragment } from '../../api/bankMaterialsTypes'
import {
  contentTypeLabel,
  emptyBankEvidenceUserCopy,
  formatPublicationDate,
  fragmentDetailPath,
  pageLabel,
  parseBankEvidenceListData,
  previewText,
  textKindCaption,
} from '../../lib/bankMaterialsDisplay'

export type BankEvidenceNavContext = {
  conversationId?: string | null
  eventId?: string | null
  companyId?: string | null
}

function BankEvidenceCard({
  item,
  nav,
  compact,
}: {
  item: BankUsedFragment
  nav: BankEvidenceNavContext
  compact?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const { preview, truncated } = previewText(item.text, compact ? 120 : 180)
  const kind = textKindCaption(item.text_kind)
  const page = pageLabel(item.page_number)
  const pub = formatPublicationDate({
    publication_date: item.publication_date,
    publication_date_precision: item.publication_date_precision,
  })
  const href = fragmentDetailPath(item.fragment_id, {
    conversationId: nav.conversationId,
    eventId: nav.eventId,
    companyId: nav.companyId,
  })

  return (
    <li className="bank-evidence-card">
      <div className="bank-evidence-card-eyebrow">Материал банка</div>
      <div className="bank-evidence-card-title">
        {item.document_title?.trim() || 'Документ банка'}
      </div>
      <div className="bank-evidence-card-meta muted">
        <span>{pub}</span>
        {page ? <span>· {page}</span> : null}
      </div>
      <div className="bank-evidence-card-type">{contentTypeLabel(item.content_type)}</div>
      {kind ? <div className="bank-evidence-card-kind muted">{kind}</div> : null}
      {item.text ? (
        <div className={`bank-evidence-card-text${item.text_kind === 'exact_quote' ? ' is-quote' : ''}`}>
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

type Props = {
  data: unknown
  title?: string | null
  labels?: string[]
  LabelsSlot?: ReactNode
  nav: BankEvidenceNavContext
  compact?: boolean
}

export function BankEvidenceBlock({ data, title, LabelsSlot, nav, compact }: Props) {
  const parsed: BankEvidenceListData | null = parseBankEvidenceListData(data)
  if (!parsed) return null

  const used = parsed.used
  const emptyCopy = emptyBankEvidenceUserCopy(parsed.status)

  if (!used.length) {
    if (!emptyCopy) return null
    return (
      <div className="assistant-block assistant-block-bank-evidence">
        <div className="assistant-block-title">{title ?? 'Материалы банка'}</div>
        {LabelsSlot}
        <p className="bank-evidence-empty muted">{emptyCopy}</p>
      </div>
    )
  }

  return (
    <div className="assistant-block assistant-block-bank-evidence">
      <div className="assistant-block-title">{title ?? 'Материалы банка'}</div>
      {LabelsSlot}
      <ul className={`bank-evidence-list${compact ? ' bank-evidence-list-compact' : ''}`}>
        {used.map((item) => (
          <BankEvidenceCard
            key={`${item.fragment_id}:${item.revision}`}
            item={item}
            nav={nav}
            compact={compact}
          />
        ))}
      </ul>
    </div>
  )
}
