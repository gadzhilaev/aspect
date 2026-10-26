import { Link } from 'react-router-dom'
import { publicApi } from '../api/endpoints'
import { NewsCard } from '../components/news/NewsCard'
import { NewsHubNav } from '../components/news/NewsHubNav'
import { StateBlock } from '../components/ui/StateBlock'
import { useAsync } from '../hooks/useAsync'

export function IndustriesPage() {
  const cats = useAsync(() => publicApi.categories(), [])
  const news = useAsync(() => publicApi.news({ limit: 12 }), [])

  return (
    <div className="container page-pad">
      <NewsHubNav />
      <p className="page-kicker">События</p>
      <h1 className="page-title">Отрасли</h1>
      <p className="page-lead">Подборки по направлениям бизнеса — без корпоративных данных.</p>
      {cats.loading ? <StateBlock variant="loading" title="Загружаем отрасли" /> : null}
      {cats.error ? (
        <StateBlock variant="error" title="Ошибка" description={cats.error.message} onRetry={cats.reload} />
      ) : null}
      <div className="cards-3" style={{ marginBottom: 28 }}>
        {(cats.data ?? []).map((c) => (
          <Link key={c.id} className="market-tile" to={`/news?category=${c.id}`}>
            <div className="label">{c.count} материалов</div>
            <div className="value" style={{ fontSize: 22 }}>
              {c.label}
            </div>
            <p style={{ marginTop: 8, color: 'var(--muted)', fontSize: 14 }}>{c.description}</p>
          </Link>
        ))}
      </div>
      {!news.loading && news.data ? (
        <div className="cards-3">
          {news.data.items.slice(0, 3).map((item) => (
            <NewsCard key={item.id} item={item} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function OpportunitiesPage() {
  const { data, error, loading, reload } = useAsync(
    () => publicApi.news({ event_type: 'opportunity', limit: 20 }),
    [],
  )

  return (
    <div className="container page-pad">
      <NewsHubNav />
      <p className="page-kicker">События</p>
      <h1 className="page-title">Возможности</h1>
      <p className="page-lead">Сигналы роста и рыночных окон.</p>
      {loading ? <StateBlock variant="loading" title="Загружаем возможности" /> : null}
      {error ? (
        <StateBlock variant="error" title="Ошибка" description={error.message} onRetry={reload} />
      ) : null}
      {!loading && data && data.items.length === 0 ? (
        <StateBlock variant="empty" title="Пока нет возможностей" />
      ) : null}
      {!loading && data && data.items.length > 0 ? (
        <div className="signal-stack signal-grid">
          {data.items.map((item) => (
            <NewsCard key={item.id} item={item} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function SoftPlaceholder({
  title,
  lead,
}: {
  title: string
  lead: string
}) {
  return (
    <div className="container page-pad">
      <p className="page-kicker">Аспект</p>
      <h1 className="page-title">{title}</h1>
      <p className="page-lead">{lead}</p>
      <div className="surface-panel" style={{ maxWidth: 560, marginTop: 20 }}>
        <p style={{ lineHeight: 1.5, marginBottom: 14 }}>
          Раздел уже в навигации. Полный сценарий сравнения и каналы уведомлений появятся в
          следующих итерациях — без смены характера сайта.
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Link className="btn btn-primary" to="/news/for-you">
            К ленте для вас
          </Link>
          <Link className="btn btn-secondary" to="/news">
            К новостям
          </Link>
        </div>
      </div>
    </div>
  )
}
