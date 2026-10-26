import { Link } from 'react-router-dom'
import { publicApi } from '../api/endpoints'
import type { PublicNewsCard } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { StateBlock } from '../components/ui/StateBlock'
import { useAsync } from '../hooks/useAsync'
import { formatDate } from '../lib/format'
import { createProfileCta, primaryCompanyCta } from '../lib/setupPath'
import { publicUrl } from '../lib/assets'

function displaySummary(text: string, isDemo: boolean): string {
  if (!isDemo) return text
  return text
    .replace(/Демонстрационное событие:\s*/gi, '')
    .replace(/Демо-возможность:\s*/gi, '')
    .replace(/Демо-событие:\s*/gi, '')
    .replace(/\s*Данные и источники — заглушки для хакатона\.?/gi, '')
    .replace(/\s*без отдельной админки\.?/gi, '')
    .trim()
}

const STEPS = [
  {
    title: 'Событие',
    text: 'Фиксируем факт из открытых источников и тип рыночного сигнала.',
  },
  {
    title: 'Зависимость',
    text: 'Сопоставляем событие с поставщиками, компонентами и рынками компании.',
  },
  {
    title: 'Воздействие',
    text: 'Оцениваем срочность и уверенность по объяснимой шкале.',
  },
  {
    title: 'Варианты',
    text: 'Показываем сценарии: замещение, запас, перенос или мониторинг.',
  },
] as const

function SignalTeaser({ item, tone }: { item: PublicNewsCard; tone: 'risk' | 'opp' }) {
  return (
    <Link
      className={`signal-card signal-card-tone-${tone === 'opp' ? 'opp' : 'risk'}`}
      to={`/news/${item.id}`}
    >
      <p className="signal-card-eyebrow">
        <span>{item.event_type_label}</span>
        <span aria-hidden>·</span>
        <span>{formatDate(item.occurred_at)}</span>
      </p>
      <h3 className="signal-card-title">{item.title}</h3>
      <p className="signal-card-why">
        <span>{displaySummary(item.summary, item.is_demo)}</span>
      </p>
      <span className="signal-card-link">Открыть</span>
    </Link>
  )
}

function FeatureIcon({ kind }: { kind: 'insight' | 'risk' }) {
  const common = {
    width: 40,
    height: 40,
    viewBox: '0 0 24 24',
    fill: 'none' as const,
    'aria-hidden': true,
  }
  if (kind === 'insight') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2" />
        <path d="M12 8v5M12 16.5v.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  }
  return (
    <svg {...common}>
      <path
        d="M12 4l8 14H4L12 4z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M12 10v4M12 16.5v.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export function HomePage() {
  const { user, companyId } = useAuth()
  const heroCta = primaryCompanyCta(user, companyId)
  const finalCta = createProfileCta(user, companyId)
  const forYouTo = user && companyId ? '/news/for-you' : '/login'
  const { data, error, loading, reload } = useAsync(() => publicApi.trending(), [])

  const risk = data?.risks[0] ?? null
  const opp = data?.opportunities[0] ?? null

  return (
    <div className="home-shell">
      <section className="home-welcome">
        <div className="container home-welcome-inner">
          <div className="home-welcome-copy">
            <div className="home-brand" aria-hidden>
              <img src={publicUrl("logo.svg")} alt="" width={44} height={36} />
              <span>Аспект</span>
            </div>

            <h1>
              Перемены именно для <span className="home-accent">вашего бизнеса</span>
            </h1>
            <p className="home-lead">
              События, которые влияют на вашу компанию. Последствия и варианты действий — в одном
              месте.
            </p>

            <div className="home-welcome-cta">
              <Link className="btn btn-primary" to={heroCta.to}>
                {user ? heroCta.label : 'Создать аккаунт'}
              </Link>
              {!user ? (
                <p className="home-welcome-login">
                  Уже есть аккаунт? <Link to="/login">Войти</Link>
                </p>
              ) : (
                <Link className="btn btn-secondary" to="/news">
                  Смотреть события
                </Link>
              )}
            </div>
          </div>

          <div className="home-feature-pair" aria-label="Возможности Аспекта">
            <Link className="home-feature-card home-feature-card-surface" to={forYouTo}>
              <p className="home-feature-title">Персональные инсайты</p>
              <p className="home-feature-text">
                Сигналы с привязкой к модели вашей компании — без общей «каши» ленты.
              </p>
              <span className="home-feature-icon">
                <FeatureIcon kind="insight" />
              </span>
            </Link>
            <Link className="home-feature-card home-feature-card-accent" to="/news">
              <p className="home-feature-title">Риски и возможности</p>
              <p className="home-feature-text">
                Открытая лента рыночных событий — дальше можно разобрать влияние и сценарии.
              </p>
              <span className="home-feature-icon">
                <FeatureIcon kind="risk" />
              </span>
            </Link>
          </div>
        </div>
      </section>

      <section className="home-section">
        <div className="container">
          <p className="page-kicker">Путь</p>
          <h2 className="home-section-title">От новости к решению</h2>
          <p className="page-lead">Один маршрут: сигнал → ваша компания → оценка → план действий.</p>

          <ol className="home-steps">
            {STEPS.map((step, index) => (
              <li key={step.title} className="home-step">
                <div className="home-step-index">{String(index + 1).padStart(2, '0')}</div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="home-section home-section-soft">
        <div className="container">
          <p className="page-kicker">Примеры</p>
          <h2 className="home-section-title">Риски и возможности</h2>
          <p className="page-lead">Живые материалы из ленты — без выдуманных процентов и демо-подмен.</p>

          {loading ? <StateBlock variant="loading" title="Загружаем примеры" /> : null}
          {error ? (
            <StateBlock
              variant="error"
              title="Не удалось загрузить примеры"
              description={error.message}
              onRetry={reload}
            />
          ) : null}

          {!loading && !error ? (
            <div className="signal-stack signal-grid" style={{ marginTop: 22 }}>
              {risk ? (
                <SignalTeaser item={risk} tone="risk" />
              ) : (
                <div className="surface-panel">
                  <p className="page-meta">Пока нет риск-сигналов в ленте.</p>
                  <Link className="signal-card-link" to="/news">
                    Открыть события
                  </Link>
                </div>
              )}
              {opp ? (
                <SignalTeaser item={opp} tone="opp" />
              ) : (
                <div className="surface-panel">
                  <p className="page-meta">Пока нет возможностей в ленте.</p>
                  <Link className="signal-card-link" to="/news/opportunities">
                    Раздел возможностей
                  </Link>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </section>

      <section className="home-finale">
        <div className="container home-finale-inner">
          <div className="home-finale-copy">
            <img src={publicUrl("logo.svg")} alt="" width={40} height={32} />
            <h2>Покажите Аспекту контекст компании</h2>
            <p>
              Поставщики, продукты, рынки и финансы превращают общую ленту в персональный
              бизнес-радар.
            </p>
          </div>
          <Link className="btn btn-primary" to={finalCta.to}>
            {finalCta.label}
          </Link>
        </div>
      </section>
    </div>
  )
}
