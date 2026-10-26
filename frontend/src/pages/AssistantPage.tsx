import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { eventsApi } from '../api/endpoints'
import { AssistantAnalysisAside } from '../components/assistant/AssistantAnalysisAside'
import { AssistantChat } from '../components/assistant/AssistantChat'
import { StateBlock } from '../components/ui/StateBlock'
import { useAuth } from '../auth/AuthContext'
import { useAsync } from '../hooks/useAsync'
import {
  CALCULATION_UNAVAILABLE_ASIDE,
  assistantOpenErrorMessage,
  newsPath,
} from '../lib/assistantWithoutImpact'

/** Full-screen assistant discussion — works with or without EventImpact. */
export function AssistantPage() {
  const { eventId = '' } = useParams()
  const { companyId } = useAuth()

  const { data, error, loading, reload } = useAsync(async () => {
    if (!companyId) throw new Error('Нужна компания')
    let impact = null
    try {
      impact = await eventsApi.impact(eventId, companyId)
    } catch (err: unknown) {
      if (!(err instanceof ApiError && (err.status === 404 || err.status === 403))) {
        throw err
      }
    }
    return { impact }
  }, [eventId, companyId])

  if (!companyId) {
    return (
      <div className="container page-pad">
        <StateBlock
          variant="error"
          title="Нужна компания"
          description="Выберите или создайте профиль компании, чтобы обсудить новость."
        />
        <div style={{ marginTop: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Link className="btn btn-primary" to="/company/setup">
            Настроить компанию
          </Link>
          <Link className="btn btn-secondary" to={newsPath(eventId)}>
            ← К новости
          </Link>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="assistant-stage">
        <div className="assistant-stage-card assistant-stage-card-loading">
          <StateBlock variant="loading" title="Открываем обсуждение" />
        </div>
      </div>
    )
  }

  if (error) {
    const apiErr =
      error instanceof ApiError
        ? error
        : { message: error.message, status: undefined, code: undefined }
    return (
      <div className="assistant-stage">
        <div className="assistant-stage-card assistant-stage-card-loading">
          <StateBlock
            variant="error"
            title="Не удалось открыть обсуждение"
            description={assistantOpenErrorMessage(apiErr)}
            onRetry={reload}
          />
          <div style={{ marginTop: 16 }}>
            <Link className="btn btn-secondary" to={newsPath(eventId)}>
              ← К новости
            </Link>
          </div>
        </div>
      </div>
    )
  }

  const impact = data?.impact ?? null

  return (
    <div className="assistant-stage">
      <div className="assistant-stage-card">
        <div className="assistant-stage-grid">
          <div className="assistant-stage-chat">
            <div className="assistant-stage-back">
              <Link className="assistant-back-link" to={newsPath(eventId)}>
                ← К новости
              </Link>
            </div>
            <AssistantChat eventId={eventId} companyId={companyId} variant="fullscreen" />
          </div>
          {impact ? (
            <AssistantAnalysisAside impact={impact} />
          ) : (
            <aside className="assistant-aside" aria-label="Расчётная оценка">
              <h3 className="assistant-aside-title">{CALCULATION_UNAVAILABLE_ASIDE.title}</h3>
              <p className="assistant-aside-lead">{CALCULATION_UNAVAILABLE_ASIDE.lead}</p>
              <ul className="assistant-aside-meanings">
                {CALCULATION_UNAVAILABLE_ASIDE.points.map((text) => (
                  <li key={text}>
                    <span>{text}</span>
                  </li>
                ))}
              </ul>
            </aside>
          )}
        </div>
      </div>
    </div>
  )
}
