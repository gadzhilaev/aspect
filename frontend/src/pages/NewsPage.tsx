import { useMemo } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { publicApi } from '../api/endpoints'
import { NewsCard } from '../components/news/NewsCard'
import { NewsHubNav } from '../components/news/NewsHubNav'
import { StateBlock } from '../components/ui/StateBlock'
import { useAsync } from '../hooks/useAsync'

export function NewsPage() {
  const location = useLocation()
  const isMarkets = location.pathname === '/news/markets'
  const [params, setParams] = useSearchParams()
  const category = isMarkets ? 'macro' : (params.get('category') ?? undefined)
  const q = (params.get('q') ?? '').trim().toLowerCase()

  const { data, error, loading, reload } = useAsync(
    () => publicApi.news({ category, limit: 30 }),
    [category],
  )
  const cats = useAsync(() => publicApi.categories(), [])

  const items = useMemo(() => {
    const list = data?.items ?? []
    if (!q) return list
    return list.filter(
      (i) =>
        i.title.toLowerCase().includes(q) ||
        i.summary.toLowerCase().includes(q) ||
        i.category_label.toLowerCase().includes(q),
    )
  }, [data, q])

  const title = isMarkets ? 'Рынки' : 'Новости'
  const lead = isMarkets
    ? 'Макроэкономика, валюты и рыночные сигналы — в одной ленте.'
    : 'Публичная лента сигналов. После входа к материалу добавится влияние на вашу компанию.'

  const sourcesCheckedLabel = (() => {
    const at = data?.ingestion?.sources_checked_at
    if (!at) return null
    try {
      const d = new Date(at)
      if (Number.isNaN(d.getTime())) return null
      return d.toLocaleString('ru-RU', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return null
    }
  })()
  const sourcesOk = data?.ingestion?.sources_check_ok

  return (
    <div className="container page-pad">
      <NewsHubNav />
      <p className="page-kicker">{isMarkets ? 'Рынки' : 'События'}</p>
      <h1 className="page-title">{title}</h1>
      <p className="page-lead">{lead}</p>
      {sourcesCheckedLabel ? (
        <p className="page-meta">
          Источники проверялись: {sourcesCheckedLabel}
          {sourcesOk === false ? ' (с замечаниями)' : null}
        </p>
      ) : null}

      {!isMarkets ? (
        <div className="filter-pills" role="tablist" aria-label="Категории">
          <button
            type="button"
            role="tab"
            aria-selected={!category}
            className={`filter-pill${!category ? ' is-active' : ''}`}
            onClick={() => {
              const next = new URLSearchParams(params)
              next.delete('category')
              setParams(next)
            }}
          >
            Все
          </button>
          {(cats.data ?? []).map((c) => (
            <button
              key={c.id}
              type="button"
              role="tab"
              aria-selected={category === c.id}
              className={`filter-pill${category === c.id ? ' is-active' : ''}`}
              onClick={() => {
                const next = new URLSearchParams(params)
                next.set('category', c.id)
                setParams(next)
              }}
            >
              {c.label}
            </button>
          ))}
        </div>
      ) : null}

      {loading ? <StateBlock variant="loading" title="Загружаем новости" /> : null}
      {!loading && error ? (
        <StateBlock
          variant="error"
          title="Не удалось загрузить ленту"
          description={error.message}
          onRetry={reload}
        />
      ) : null}
      {!loading && !error && items.length === 0 ? (
        <StateBlock
          variant="empty"
          title="Ничего не найдено"
          description={q ? 'Попробуйте другой запрос' : 'В этой категории пока пусто'}
        />
      ) : null}
      {!loading && !error && items.length > 0 ? (
        <div className="signal-stack signal-grid">
          {items.map((item) => (
            <NewsCard key={item.id} item={item} />
          ))}
        </div>
      ) : null}
    </div>
  )
}
