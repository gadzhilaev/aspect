import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { companyApi, publicApi } from '../api/endpoints'
import type { PublicNewsCard } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { ForYouNewsCard } from '../components/news/ForYouNewsCard'
import { NewsHubNav } from '../components/news/NewsHubNav'
import { StateBlock } from '../components/ui/StateBlock'
import { useAsync } from '../hooks/useAsync'

export function ForYouPage() {
  const { companyId } = useAuth()
  const { data, error, loading, reload } = useAsync(async () => {
    if (!companyId) throw new Error('Сначала выберите компанию')
    const [dashboard, news] = await Promise.all([
      companyApi.dashboard(companyId),
      publicApi.news({ limit: 50 }),
    ])
    return { dashboard, newsItems: news.items }
  }, [companyId])

  const newsById = useMemo(() => {
    const map = new Map<string, PublicNewsCard>()
    for (const item of data?.newsItems ?? []) {
      map.set(item.id, item)
    }
    return map
  }, [data?.newsItems])

  if (!companyId) {
    return (
      <div className="container page-pad">
        <NewsHubNav />
        <StateBlock
          variant="empty"
          title="Нет компании в профиле"
          description="Создайте профиль компании — и лента сможет показывать совпадения с вашей моделью. Вход в аккаунт сам по себе расчёт влияния не добавляет."
        />
        <div className="decision-fallback-actions">
          <Link className="btn btn-primary" to="/company/setup">
            Настроить под компанию
          </Link>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="container page-pad">
        <NewsHubNav />
        <StateBlock variant="loading" title="Собираем ленту для вас" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="container page-pad">
        <NewsHubNav />
        <StateBlock
          variant="error"
          title="Не удалось загрузить персональную ленту"
          description={error?.message}
          onRetry={reload}
        />
      </div>
    )
  }

  const { dashboard } = data
  const empty = dashboard.feed_empty

  return (
    <div className="container page-pad">
      <NewsHubNav />
      <p className="page-kicker">{dashboard.company_name}</p>
      <h1 className="page-title">Главные новости для вас</h1>
      <p className="page-lead">
        Сигналы с расчётом влияния по модели компании. Основания не смешиваются одним числом.
      </p>

      <p style={{ marginTop: 16 }}>
        <Link className="btn btn-secondary" to="/company/products">
          Настроить продукцию и бренды
        </Link>
      </p>

      <div className="metric-strip" aria-label="Сводка по ленте">
        <div className="metric-tile is-accent">
          <div className="label">Требуют внимания</div>
          <div className="value">{dashboard.counters.action_required ?? 0}</div>
        </div>
        <div className="metric-tile">
          <div className="label">Высокий приоритет</div>
          <div className="value">{dashboard.counters.high_priority ?? 0}</div>
        </div>
        <div className="metric-tile">
          <div className="label">Наблюдение</div>
          <div className="value">{dashboard.counters.monitor ?? 0}</div>
        </div>
        <div className="metric-tile">
          <div className="label">Всего сигналов</div>
          <div className="value">{dashboard.counters.total ?? 0}</div>
        </div>
      </div>

      {dashboard.priority_events.length === 0 ? (
        <>
          <StateBlock
            variant="empty"
            title={empty?.title ?? 'Персональных сигналов пока нет'}
            description={
              empty?.detail ??
              'Среди опубликованных новостей нет совпадений с вашей моделью. Общая лента доступна без персонального расчёта.'
            }
          />
          <div className="decision-fallback-actions" style={{ marginTop: 16 }}>
            <Link className="btn btn-primary" to={empty?.primary_href || '/news'}>
              {empty?.primary_label || 'Все новости'}
            </Link>
            {empty?.secondary_href ? (
              <Link className="btn btn-secondary" to={empty.secondary_href}>
                {empty.secondary_label || 'Профиль'}
              </Link>
            ) : (
              <Link className="btn btn-secondary" to="/scenarios">
                История обсуждений
              </Link>
            )}
          </div>
        </>
      ) : (
        <div className="signal-stack signal-grid">
          {dashboard.priority_events.map((ev) => (
            <ForYouNewsCard key={ev.id} event={ev} news={newsById.get(ev.id)} />
          ))}
        </div>
      )}
    </div>
  )
}
