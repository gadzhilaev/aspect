import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { companyApi, decisionsApi, eventsApi, publicApi } from '../api/endpoints'
import { AssistantChat } from '../components/assistant/AssistantChat'
import { ImpactPanel } from '../components/personal/ImpactPanel'
import { StateBlock } from '../components/ui/StateBlock'
import { useAuth } from '../auth/AuthContext'
import { useAsync } from '../hooks/useAsync'

export function ImpactPage() {
  const { eventId = '' } = useParams()
  const { companyId } = useAuth()
  const navigate = useNavigate()
  const [chatOpen, setChatOpen] = useState(true)
  const [expanded, setExpanded] = useState(false)

  const { data, error, loading, reload } = useAsync(async () => {
    if (!companyId) throw new Error('Нужна компания')
    const [news, impact, profile, detail, decision] = await Promise.all([
      publicApi.newsDetail(eventId),
      eventsApi.impact(eventId, companyId),
      companyApi.profile(companyId),
      eventsApi.detail(eventId, companyId),
      decisionsApi.forEvent(eventId, companyId).catch((err: unknown) => {
        if (err instanceof ApiError && (err.status === 404 || err.status === 403)) return null
        throw err
      }),
    ])
    return {
      news,
      impact,
      companyName: profile.company.name,
      detail,
      decisionId: decision?.id ?? null,
    }
  }, [eventId, companyId])

  if (loading) {
    return (
      <div className="container page-pad">
        <StateBlock variant="loading" title="Готовим разбор" />
      </div>
    )
  }

  if (error || !data || !companyId) {
    return (
      <div className="container page-pad">
        <StateBlock
          variant="error"
          title="Разбор недоступен"
          description={error?.message}
          onRetry={reload}
        />
      </div>
    )
  }

  return (
    <div className="container page-pad">
      <Link to={`/news/${eventId}`} className="btn btn-secondary" style={{ marginBottom: 16 }}>
        ← К новости
      </Link>

      <div className="impact-layout">
        <div className="impact-main">
          <h1 className="page-title">{data.news.title}</h1>
          <p className="page-lead">{data.news.summary}</p>

          {data.news.is_demo ? <span className="chip chip-demo">Демо-сценарий</span> : null}

          <div className="impact-assist-launch">
            <button
              type="button"
              className="btn btn-primary assistant-desktop-only"
              onClick={() => setChatOpen(true)}
            >
              Обсудить варианты с Аспектом
            </button>
            <button
              type="button"
              className="btn btn-primary assistant-mobile-only"
              onClick={() => navigate(`/events/${eventId}/assistant`)}
            >
              Обсудить варианты с Аспектом
            </button>
          </div>

          <ImpactPanel
            companyName={data.companyName}
            impact={data.impact}
            eventId={eventId}
            decisionId={data.decisionId}
            showActions={false}
          />

          {data.detail.sources?.length ? (
            <section className="aside-card" style={{ marginTop: 20, position: 'static' }}>
              <h3 style={{ fontSize: 16, marginBottom: 8 }}>Источники</h3>
              <ul className="assistant-source-list">
                {data.detail.sources.map((s) => {
                  const url =
                    typeof s.url === 'string' && /^https?:\/\//i.test(s.url) ? s.url : null
                  return (
                    <li key={s.id}>
                      <div className="assistant-source-name">{s.publisher}</div>
                      <div className="muted">
                        {s.is_stub ? 'Демо' : 'Источник'}
                        {s.published_at
                          ? ` · ${new Date(s.published_at).toLocaleDateString('ru-RU')}`
                          : ''}
                        {url ? (
                          <>
                            {' · '}
                            <a href={url} target="_blank" rel="noopener noreferrer">
                              Оригинал
                            </a>
                          </>
                        ) : null}
                      </div>
                    </li>
                  )
                })}
              </ul>
            </section>
          ) : null}
        </div>

        {chatOpen ? (
          <div className="assistant-chat-panel assistant-desktop-only">
            <AssistantChat
              eventId={eventId}
              companyId={companyId}
              variant="panel"
              expanded={expanded}
              onToggleExpand={() => setExpanded((v) => !v)}
              onClose={() => {
                setExpanded(false)
                setChatOpen(false)
              }}
            />
          </div>
        ) : null}
      </div>
    </div>
  )
}
