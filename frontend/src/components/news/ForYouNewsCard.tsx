import { Link } from 'react-router-dom'
import type { EventCard, PublicNewsCard } from '../../api/types'
import { formatDate } from '../../lib/format'
import { isProfileOnly } from '../../lib/profileFeed'

type Props = {
  event: EventCard
  news?: PublicNewsCard | null
}

function scoreAvailable(event: EventCard): boolean {
  if (event.impact_score_available === false) return false
  if (isProfileOnly(event)) return false
  return typeof event.impact_score === 'number' && Number.isFinite(event.impact_score)
}

function impactLabel(event: EventCard): string {
  if (isProfileOnly(event) || event.impact_score_available === false) {
    return event.score_kind_label || event.metric_labels?.impact_score || 'По профилю компании'
  }
  const state = event.assessment_state
  if (state === 'finance_data_required') return 'Нужны финансы'
  if (state === 'monitoring_only') return 'Мониторинг'
  const kind = event.score_kind
  const name =
    event.metric_labels?.impact_score ||
    event.score_kind_label ||
    (kind === 'event_severity_signal' ? 'Сигнал события' : 'Индекс влияния')
  if (!scoreAvailable(event)) return name
  return `${name} ${Math.round(event.impact_score as number)}`
}

function profileExplanation(event: EventCard): string | null {
  const pr = event.profile_relevance
  if (!pr?.matched) return null
  if (pr.summary) return pr.summary
  const first = pr.matches?.[0]
  return first?.explanation || null
}

function toneClass(event: EventCard, news?: PublicNewsCard | null): string {
  if (news?.event_type === 'opportunity') return 'signal-card-tone-opp'
  const score = scoreAvailable(event) ? (event.impact_score as number) : null
  if (score != null && score >= 70) return 'signal-card-tone-high'
  if (score != null && score >= 40) return 'signal-card-tone-medium'
  if (news?.event_type === 'risk' || event.priority === 'high' || event.urgency === 'high') {
    return 'signal-card-tone-risk'
  }
  return 'signal-card-tone-macro'
}

function alertText(event: EventCard, news?: PublicNewsCard | null): string | null {
  const isRisk =
    news?.event_type === 'risk' || event.priority === 'high' || event.urgency === 'high'
  if (!isRisk) return null
  const text = (event.reason_summary || news?.summary || '').trim()
  if (!text) return null
  // Keep short for the callout; full text remains in lead
  return text.length > 140 ? `${text.slice(0, 137)}…` : text
}

export function ForYouNewsCard({ event, news }: Props) {
  const profileOnly = isProfileOnly(event)
  const profileText = profileExplanation(event)
  const summary = news?.summary || event.reason_summary
  const date = news?.primary_published_at || news?.occurred_at || event.updated_at
  const alert = alertText(event, news)
  const tone = toneClass(event, news)

  return (
    <article className={`signal-card ${tone}`}>
      <p className="signal-card-eyebrow">
        <span>{impactLabel(event)}</span>
        <span aria-hidden>·</span>
        <span>{formatDate(date)}</span>
      </p>
      <h3 className="signal-card-title">
        <Link to={`/news/${event.id}`}>{event.title}</Link>
      </h3>
      {profileText ? (
        <p className="signal-card-why">
          Почему вам: <span>{profileText}</span>
        </p>
      ) : summary ? (
        <p className="signal-card-why">
          <span>{summary}</span>
        </p>
      ) : null}
      {alert ? (
        <div className="signal-card-alert" role="note">
          <span className="signal-card-alert-mark" aria-hidden>
            !
          </span>
          <span>{alert}</span>
        </div>
      ) : null}
      <div className="signal-card-meta">
        {news?.category_label ? <span className="chip">{news.category_label}</span> : null}
        {event.profile_relevance?.matched ? (
          <span className="chip">По профилю компании</span>
        ) : null}
        {!profileOnly && event.exposure ? (
          <span>
            {event.exposure.label}: {event.exposure.value}
            {event.exposure.unit === 'percent' ? '%' : ''}
          </span>
        ) : null}
      </div>
      <div className="signal-card-actions">
        <Link className="signal-card-link" to={`/news/${event.id}`}>
          Открыть новость
        </Link>
        {profileOnly ? (
          <Link className="signal-card-link" to={`/events/${event.id}/assistant`}>
            Обсудить с Аспектом
          </Link>
        ) : (
          <Link className="signal-card-link" to={`/events/${event.id}/impact`}>
            Открыть влияние
          </Link>
        )}
      </div>
    </article>
  )
}
