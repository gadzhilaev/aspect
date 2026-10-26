import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { companyApi, decisionsApi, eventsApi, publicApi } from '../api/endpoints'
import { NewsBankAnalytics } from '../components/news/NewsBankAnalytics'
import { NewsCard } from '../components/news/NewsCard'
import { ImpactPanel } from '../components/personal/ImpactPanel'
import { StateBlock } from '../components/ui/StateBlock'
import { useAuth } from '../auth/AuthContext'
import { useAsync } from '../hooks/useAsync'
import { formatDate } from '../lib/format'
import { financeSetupPath } from '../lib/setupPath'

export function NewsDetailPage() {
  const { eventId = '' } = useParams()
  const { user, companyId } = useAuth()

  const news = useAsync(() => publicApi.newsDetail(eventId), [eventId])
  const personal = useAsync(async () => {
    if (!user || !companyId || !eventId) return null
    const [profile, decision, relevance] = await Promise.all([
      companyApi.profile(companyId),
      decisionsApi.forEvent(eventId, companyId).catch((err: unknown) => {
        if (err instanceof ApiError && (err.status === 404 || err.status === 403)) return null
        throw err
      }),
      eventsApi.relevance(eventId, companyId),
    ])
    let impact = null
    try {
      impact = await eventsApi.impact(eventId, companyId)
    } catch (err: unknown) {
      if (!(err instanceof ApiError && (err.status === 404 || err.status === 403))) throw err
    }
    return {
      impact,
      relevance,
      companyName: profile.company.name,
      decisionId: decision?.id ?? null,
    }
  }, [user, companyId, eventId])

  if (news.loading) {
    return (
      <div className="container page-pad">
        <StateBlock variant="loading" title="Открываем материал" />
      </div>
    )
  }

  if (news.error || !news.data) {
    return (
      <div className="container page-pad">
        <StateBlock
          variant="error"
          title="Материал недоступен"
          description={news.error?.message}
          onRetry={news.reload}
        />
      </div>
    )
  }

  const item = news.data

  const backTo = user && companyId ? '/news/for-you' : '/news'

  return (
    <div className="container page-pad">
      <Link to={backTo} className="auth-card-back" style={{ marginBottom: 12 }}>
        ‹ К новостям
      </Link>

      <div className="article-hero">
        <img src={item.image_url} alt="" />
        <div>
          <div className="story-meta">
            <span className="chip">{item.category_label}</span>
            <span
              className={`chip${
                item.event_type === 'risk'
                  ? ' chip-risk'
                  : item.event_type === 'opportunity'
                    ? ' chip-opp'
                    : ''
              }`}
            >
              {item.event_type_label}
            </span>
          </div>
          <h1 className="page-title" style={{ marginTop: 12 }}>
            {item.title}
          </h1>
          <p className="page-lead">{item.summary}</p>
          <div className="story-meta" style={{ color: 'var(--muted)' }}>
            {item.primary_publisher ? <span>{item.primary_publisher}</span> : null}
            {item.primary_publisher ? <span>·</span> : null}
            <span>{formatDate(item.primary_published_at || item.occurred_at)}</span>
            <span>·</span>
            <span>{item.reading_time_min} мин чтения</span>
            <span>·</span>
            <span>{item.severity_label}</span>
          </div>
        </div>
      </div>

      <div className="article-body">
        <div>
          <article className="prose">{item.body}</article>

          <section className="article-section">
            <h2 className="article-section-title">Источники</h2>
            {item.sources.length === 0 ? (
              <p className="muted">Источники появятся позже</p>
            ) : (
              <div className="rail">
                {item.sources.map((s, idx) => (
                  <div key={`${s.publisher}-${idx}`} className="aside-card" style={{ position: 'static' }}>
                    <div className="source-publisher">{s.publisher}</div>
                    {s.published_at ? (
                      <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                        {formatDate(s.published_at)}
                      </div>
                    ) : null}
                    {s.excerpt ? <p className="source-excerpt">{s.excerpt}</p> : null}
                    {s.url ? (
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="btn btn-ghost"
                        style={{ marginTop: 8, padding: 0 }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        Открыть оригинал →
                      </a>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Bank corpus is Bearer-only — guests do not call protected API. */}
          <NewsBankAnalytics eventId={eventId} companyId={companyId} enabled={Boolean(user)} />

          {item.related.length > 0 ? (
            <section className="article-section">
              <h2 className="article-section-title">Читайте также</h2>
              <div className="cards-3">
                {item.related.map((r) => (
                  <NewsCard key={r.id} item={r} />
                ))}
              </div>
            </section>
          ) : null}
        </div>

        <div>
          {user && companyId ? (
            personal.loading ? (
              <StateBlock variant="loading" title="Считаем влияние" />
            ) : personal.error ? (
              <div className="aside-card">
                <h3 style={{ fontFamily: 'var(--font-ui)', fontSize: 18 }}>Для вашей компании</h3>
                <p style={{ color: 'var(--muted)', margin: '8px 0 14px', lineHeight: 1.45 }}>
                  Не удалось загрузить персональный контекст. Обновите страницу или профиль.
                </p>
                <Link className="btn btn-secondary" to="/news/for-you">
                  К персональной ленте
                </Link>
              </div>
            ) : personal.data?.impact ? (
              <ImpactPanel
                companyName={personal.data.companyName}
                impact={personal.data.impact}
                eventId={eventId}
                decisionId={personal.data.decisionId}
              />
            ) : (
              <div className="aside-card" aria-label="Обсуждение без расчётной оценки">
                <div className="chip">Для {personal.data?.companyName ?? 'вашей компании'}</div>
                <h3 style={{ fontFamily: 'var(--font-ui)', fontSize: 18, marginTop: 8 }}>
                  Расчётная оценка пока недоступна
                </h3>
                <p style={{ margin: '8px 0 12px', lineHeight: 1.45 }}>
                  {personal.data?.relevance?.summary ||
                    'Персональный индекс влияния для этой компании по событию ещё не посчитан. Событие можно обсудить по доступным данным компании и материалам банка.'}
                </p>
                {personal.data?.relevance?.limitations?.length ? (
                  <ul style={{ margin: '0 0 12px', paddingLeft: 18, color: 'var(--muted)' }}>
                    {personal.data.relevance.limitations.slice(0, 3).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                ) : null}
                <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                  Обсудить можно, но установленное влияние на компанию не обещается. Отсутствие
                  расчёта не означает, что риска нет или что событие безопасно.
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  <Link className="btn btn-primary" to={`/events/${eventId}/assistant`}>
                    Обсудить с Аспектом
                  </Link>
                  <Link
                    className="btn btn-secondary"
                    to={financeSetupPath({ eventId, companyId })}
                  >
                    Настроить финансы для расчёта
                  </Link>
                </div>
              </div>
            )
          ) : user && !companyId ? (
            <div className="aside-card">
              <h3 style={{ fontFamily: 'var(--font-ui)', fontSize: 18 }}>Нужна компания</h3>
              <p style={{ color: 'var(--muted)', margin: '8px 0 14px', lineHeight: 1.45 }}>
                Чтобы обсудить новость в контексте вашего бизнеса, выберите или создайте профиль
                компании.
              </p>
              <Link
                className="btn btn-primary"
                to="/company/setup"
                state={{ from: `/news/${eventId}` }}
              >
                Настроить компанию
              </Link>
            </div>
          ) : (
            <div className="aside-card">
              <h3 style={{ fontFamily: 'var(--font-ui)', fontSize: 18 }}>
                Обсудите новость в контексте компании
              </h3>
              <p style={{ color: 'var(--muted)', margin: '8px 0 14px', lineHeight: 1.45 }}>
                Войдите и выберите компанию — можно обсудить событие даже без готовой расчётной
                оценки. Установленное влияние без расчёта не обещается.
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                <Link
                  className="btn btn-primary"
                  to="/login"
                  state={{ from: `/news/${eventId}` }}
                >
                  Войти
                </Link>
                <Link
                  className="btn btn-secondary"
                  to="/register"
                  state={{ from: `/news/${eventId}` }}
                >
                  Создать профиль
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
