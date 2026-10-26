import { Link, Navigate } from 'react-router-dom'
import { agentDemoApi } from '../api/endpoints'
import { useAuth } from '../auth/AuthContext'
import { StateBlock } from '../components/ui/StateBlock'
import { useAsync } from '../hooks/useAsync'
import { isAgentDemoStand } from '../lib/agentDemo'

/**
 * Demo-stand entry panel (stage 4.8).
 * Only mounted when VITE_AGENT_DEMO=true — not part of the ordinary product shell.
 */
export function AgentDemoPage() {
  const { user } = useAuth()
  const enabled = isAgentDemoStand() && Boolean(user)
  const { data, error, loading, reload } = useAsync(async () => {
    if (!enabled) {
      throw new Error('Демостенд выключен')
    }
    return agentDemoApi.entry()
  }, [enabled, user?.id])

  if (!isAgentDemoStand()) {
    return <Navigate to="/news" replace />
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: '/agent-demo' }} replace />
  }

  if (loading) {
    return (
      <div className="container page-pad">
        <StateBlock variant="loading" title="Готовим демостенд" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="container page-pad">
        <StateBlock
          variant="error"
          title="Демостенд недоступен"
          description={
            error?.message ||
            'Включите AGENT_DEMO_STAND на backend и убедитесь, что синтетическое событие есть в БД.'
          }
          onRetry={reload}
        />
        <div className="decision-fallback-actions" style={{ marginTop: 16 }}>
          <Link className="btn btn-secondary" to="/news">
            Все новости
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="container page-pad">
      <p className="chip chip-demo" style={{ display: 'inline-block' }}>
        Демостенд · синтетика
      </p>
      <h1 className="page-title">Вход в сценарий агента</h1>
      <p className="page-lead">{data.synthetic_notice}</p>
      <p className="muted" style={{ maxWidth: 640, lineHeight: 1.45 }}>
        {data.prior_answer_notice}
      </p>

      <div className="markets-strip" style={{ marginTop: 24, marginBottom: 24 }}>
        <div className="market-tile">
          <div className="label">Компания</div>
          <div className="value" style={{ fontSize: 18 }}>
            {data.company_name}
          </div>
        </div>
        <div className="market-tile">
          <div className="label">Событие</div>
          <div className="value" style={{ fontSize: 16 }}>
            {data.event_title}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <Link className="btn btn-primary" to={data.news_path}>
          Открыть новость
        </Link>
        <Link className="btn btn-secondary" to={data.assistant_path}>
          Сохранённое обсуждение
        </Link>
        <Link className="btn btn-secondary" to={data.scenarios_path}>
          История в «Сценарии»
        </Link>
        <Link className="btn btn-ghost" to={data.public_news_path}>
          Все новости
        </Link>
      </div>

      <p className="muted" style={{ marginTop: 20, fontSize: 13, maxWidth: 640 }}>
        Банковский PDF открывается из блоков ответа в чате (fragment → оригинал). Переходы ведут на
        обычные маршруты продукта; event ID вводить вручную не нужно.
      </p>
    </div>
  )
}
