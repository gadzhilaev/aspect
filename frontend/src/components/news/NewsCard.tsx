import { Link } from 'react-router-dom'
import type { PublicNewsCard } from '../../api/types'
import { formatDate } from '../../lib/format'

type Props = {
  item: PublicNewsCard
  large?: boolean
}

function toneClass(item: PublicNewsCard): string {
  if (item.event_type === 'opportunity') return 'signal-card-tone-opp'
  if (item.event_type === 'risk') return 'signal-card-tone-risk'
  return 'signal-card-tone-macro'
}

export function NewsCard({ item, large }: Props) {
  const tone =
    item.event_type === 'opportunity'
      ? 'chip-opp'
      : item.event_type === 'risk'
        ? 'chip-risk'
        : ''

  return (
    <Link
      className={`signal-card ${toneClass(item)}${large ? ' large' : ''}`}
      to={`/news/${item.id}`}
    >
      <p className="signal-card-eyebrow">
        <span>{item.event_type_label}</span>
        <span aria-hidden>·</span>
        <span>{formatDate(item.primary_published_at || item.occurred_at)}</span>
      </p>
      <h3 className="signal-card-title">{item.title}</h3>
      <p className="signal-card-why">
        <span>{item.summary}</span>
      </p>
      <div className="signal-card-meta">
        <span className={`chip ${tone}`}>{item.category_label}</span>
        {item.primary_publisher ? <span>{item.primary_publisher}</span> : null}
        <span>{item.reading_time_min} мин</span>
      </div>
      <span className="signal-card-link">Открыть</span>
    </Link>
  )
}
