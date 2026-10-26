import { Link } from 'react-router-dom'
import { companyApi } from '../api/endpoints'
import type { CaseContext, CompanyContext, CompanyProfile } from '../api/types'
import { CaseContextSection } from '../components/company/CaseContextSection'
import { useAuth } from '../auth/AuthContext'
import { StateBlock } from '../components/ui/StateBlock'
import { useAsync } from '../hooks/useAsync'
import {
  buildCompanyHeader,
  buildHubCards,
  type CompanyHubCard,
  type HubCardTone,
} from '../lib/companyHub'
import { provenanceFromSettings } from '../lib/companyRegistry'
import { publicUrl } from '../lib/assets'

type HubPayload = {
  profile: CompanyProfile
  caseContext: CaseContext | null
  context: CompanyContext | null
  contextError: string | null
}

function HubIcon({ id }: { id: CompanyHubCard['id'] }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    fill: 'none' as const,
    'aria-hidden': true,
  }
  if (id === 'products') {
    return (
      <svg {...common}>
        <path d="M4 8l8-4 8 4v9l-8 4-8-4V8z" stroke="currentColor" strokeWidth="2" />
        <path d="M12 12v9M4 8l8 4 8-4" stroke="currentColor" strokeWidth="2" />
      </svg>
    )
  }
  if (id === 'markets') {
    return (
      <svg {...common}>
        <path
          d="M4 18V9l4-3h8l4 3v9"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        <path d="M9 18v-5h6v5" stroke="currentColor" strokeWidth="2" />
      </svg>
    )
  }
  if (id === 'geography') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2" />
        <path
          d="M4 12h16M12 4c2.5 2.5 3.5 5.5 3.5 8S14.5 17.5 12 20c-2.5-2.5-3.5-5.5-3.5-8S9.5 6.5 12 4z"
          stroke="currentColor"
          strokeWidth="2"
        />
      </svg>
    )
  }
  if (id === 'me') {
    return (
      <svg {...common}>
        <circle cx="12" cy="9" r="3.5" stroke="currentColor" strokeWidth="2" />
        <path
          d="M5 19c1.5-3 4-4.5 7-4.5S17.5 16 19 19"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    )
  }
  if (id === 'finance') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2" />
        <path
          d="M12 7v10M9.5 9.5c.6-.8 1.5-1.2 2.5-1.2 1.5 0 2.5.8 2.5 2s-1 2-2.5 2H11c-1.5 0-2.5.8-2.5 2s1 2 2.5 2c1 0 1.9-.4 2.5-1.2"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    )
  }
  return (
    <svg {...common}>
      <path
        d="M8 7h8M8 12h8M8 17h5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <rect x="4" y="4" width="16" height="16" rx="3" stroke="currentColor" strokeWidth="2" />
    </svg>
  )
}

function toneClass(tone: HubCardTone): string {
  return `company-hub-card company-hub-card-${tone}`
}

function HubGrid({ cards }: { cards: CompanyHubCard[] }) {
  return (
    <div className="company-hub-grid" data-testid="company-hub-grid">
      {cards.map((card) => (
        <Link
          key={card.id}
          className={toneClass(card.tone)}
          to={card.path}
          data-testid={`company-hub-card-${card.id}`}
          data-empty={card.empty ? 'true' : 'false'}
        >
          <div className="company-hub-card-top">
            <span className="company-hub-card-icon">
              <HubIcon id={card.id} />
            </span>
            <span className="company-hub-card-arrow" aria-hidden>
              ↗
            </span>
          </div>
          <h3 className="company-hub-card-title">{card.title}</h3>
          <p className={`company-hub-card-summary${card.empty ? ' is-empty' : ''}`}>
            {card.summary}
          </p>
        </Link>
      ))}
    </div>
  )
}

function GuestOrNoCompany({
  title,
  lead,
  primaryTo,
  primaryLabel,
  secondaryTo,
  secondaryLabel,
}: {
  title: string
  lead: string
  primaryTo: string
  primaryLabel: string
  secondaryTo?: string
  secondaryLabel?: string
}) {
  return (
    <div className="company-page">
      <section className="company-hub-shell">
        <div className="container">
          <p className="company-hub-kicker">Компания</p>
          <h1 className="company-hub-page-title">{title}</h1>
          <p className="company-hub-lead">{lead}</p>
          <div className="company-hub-actions">
            <Link className="btn btn-primary" to={primaryTo}>
              {primaryLabel}
            </Link>
            {secondaryTo && secondaryLabel ? (
              <Link className="btn btn-secondary" to={secondaryTo}>
                {secondaryLabel}
              </Link>
            ) : null}
          </div>
        </div>
      </section>
    </div>
  )
}

export function CompanyPage() {
  const { user, companyId, setCompanyId, loading: authLoading } = useAuth()

  const { data, error, loading, reload } = useAsync(async (): Promise<HubPayload | null> => {
    if (!companyId) return null
    const profile = await companyApi.profile(companyId)
    let caseContext: CaseContext | null = null
    let context: CompanyContext | null = null
    let contextError: string | null = null
    try {
      const ctx = await companyApi.context(companyId)
      context = ctx
      caseContext = ctx.case_context ?? null
    } catch (err) {
      contextError = err instanceof Error ? err.message : 'Не удалось загрузить сведения из источника'
    }
    return { profile, caseContext, context, contextError }
  }, [companyId])

  if (authLoading) {
    return (
      <div className="container page-pad">
        <StateBlock variant="loading" title="Загружаем профиль" />
      </div>
    )
  }

  if (!user) {
    return (
      <GuestOrNoCompany
        title="Компания — контекст Аспекта"
        lead="Войдите, чтобы видеть и настраивать профиль компании. Без входа персональный контекст недоступен."
        primaryTo="/register"
        primaryLabel="Создать профиль"
        secondaryTo="/login"
        secondaryLabel="Войти"
      />
    )
  }

  if (!companyId) {
    return (
      <GuestOrNoCompany
        title="Выберите или создайте компанию"
        lead="Без выбранной компании разделы контекста пусты. Создайте профиль или подключите компанию."
        primaryTo="/company/setup"
        primaryLabel="Начать настройку"
      />
    )
  }

  if (loading) {
    return (
      <div className="container page-pad">
        <StateBlock variant="loading" title="Загружаем компанию" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="container page-pad">
        <StateBlock
          variant="error"
          title="Не удалось загрузить компанию"
          description={error?.message || 'Проверьте соединение и попробуйте ещё раз.'}
          onRetry={reload}
        />
      </div>
    )
  }

  const provenance = provenanceFromSettings(data.profile.settings)
  const header = buildCompanyHeader(data.profile.company, user, provenance)
  const cards = buildHubCards({
    profile: data.profile,
    user,
    caseContext: data.caseContext,
  })

  return (
    <div className="company-page" data-testid="company-hub">
      <section className="company-hub-shell">
        <div className="container">
          <p className="company-hub-kicker">Ваша компания</p>
          <h1 className="company-hub-page-title">Контекст для персонализации</h1>

          <article className="company-hub-identity" data-testid="company-hub-identity">
            <div className="company-hub-identity-main">
              <div className="company-hub-identity-mark" aria-hidden>
                <img src={publicUrl("logo.svg")} alt="" width={36} height={31} />
              </div>
              <div className="company-hub-identity-copy">
                <h2 className="company-hub-company-name">{header.name}</h2>
                {header.industry ? (
                  <p className="company-hub-industry">{header.industry}</p>
                ) : null}
              </div>
            </div>

            <dl className="company-hub-meta">
              {header.inn ? (
                <div>
                  <dt>ИНН</dt>
                  <dd data-testid="company-hub-inn">{header.inn}</dd>
                </div>
              ) : null}
              {header.provenanceLine ? (
                <div className="company-hub-meta-wide">
                  <dt>Реквизиты</dt>
                  <dd data-testid="company-hub-provenance">{header.provenanceLine}</dd>
                </div>
              ) : (
                <div className="company-hub-meta-wide">
                  <dt>Реквизиты</dt>
                  <dd className="is-muted">Публичный источник не отмечен</dd>
                </div>
              )}
            </dl>

            {header.companies.length > 1 ? (
              <label className="company-hub-switcher">
                <span>Компания</span>
                <select
                  value={companyId}
                  onChange={(e) => setCompanyId(e.target.value)}
                  data-testid="company-hub-switcher"
                >
                  {header.companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </article>

          <div className="company-hub-context-head">
            <h2>Ваш контекст</h2>
            <Link className="btn btn-secondary" to="/company/setup">
              Изменить в мастере
            </Link>
          </div>

          <HubGrid cards={cards} />
        </div>
      </section>
      {data.context ? <CaseContextSection data={data.context} /> : null}
      {data.contextError ? <div className="container"><StateBlock variant="error" title="Сведения из источника недоступны" description={data.contextError} onRetry={reload} /></div> : null}
    </div>
  )
}
