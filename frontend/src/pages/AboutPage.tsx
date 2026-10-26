import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { createProfileCta, primaryCompanyCta } from '../lib/setupPath'

const STEPS = [
  {
    n: '01',
    title: 'Находим сигнал',
    text: 'Официальные источники, рынки, регуляторы и отраслевые новости.',
    icon: 'signal',
  },
  {
    n: '02',
    title: 'Сверяем с вашим контекстом',
    text: 'Страны, продукты, поставщики, рынки, валюты и бизнес-процессы.',
    icon: 'context',
  },
  {
    n: '03',
    title: 'Показываем влияние',
    text: 'Объясняем цепочку, уровень уверенности и долю бизнеса под риском.',
    icon: 'impact',
  },
  {
    n: '04',
    title: 'Помогаем выбрать действие',
    text: 'Сравниваем сценарии и формируем план, который остаётся за руководителем.',
    icon: 'action',
  },
] as const

const PRINCIPLES = [
  {
    title: 'Открытые источники до входа',
    text: 'Рынок можно читать без регистрации — как деловое издание, без привязки к профилю.',
    icon: 'open',
  },
  {
    title: 'Персональный контекст после настройки',
    text: 'Та же новость показывает связь с конкретной компанией: линиями, поставщиками и рынками.',
    icon: 'twin',
  },
  {
    title: 'Решение остаётся за человеком',
    text: 'Аспект объясняет выводы, показывает источники и не принимает решения за руководителя.',
    icon: 'human',
  },
] as const

const ACTIONS = [
  {
    title: 'Перераспределить поставки',
    result: 'Снижает риск остановки',
  },
  {
    title: 'Найти альтернативного поставщика',
    result: 'Требует проверки сроков',
  },
  {
    title: 'Согласовать запас критичных компонентов',
    result: 'Нужна оценка стоимости',
  },
] as const

function StepIcon({ kind }: { kind: (typeof STEPS)[number]['icon'] }) {
  if (kind === 'signal') {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M4 12h3l2-5 3 10 2-5h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (kind === 'context') {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
        <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  }
  if (kind === 'impact') {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M5 19V9M10 19V5M15 19v-7M20 19V8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  }
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M5 12h10M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function PrincipleIcon({ kind }: { kind: (typeof PRINCIPLES)[number]['icon'] }) {
  if (kind === 'open') {
    return (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
        <path d="M4 7h11a3 3 0 013 3v8H7a3 3 0 01-3-3V7z" stroke="currentColor" strokeWidth="2" />
        <path d="M15 7V5a2 2 0 012-2h3v10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  }
  if (kind === 'twin') {
    return (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
        <rect x="3" y="4" width="8" height="16" rx="2" stroke="currentColor" strokeWidth="2" />
        <rect x="13" y="4" width="8" height="16" rx="2" stroke="currentColor" strokeWidth="2" />
        <path d="M7 9h0M7 13h0M17 9h0M17 13h0" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
    )
  }
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="8" r="3.5" stroke="currentColor" strokeWidth="2" />
      <path d="M5 20c1.5-3.5 4-5 7-5s5.5 1.5 7 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function SignalPathVisual() {
  return (
    <div className="about-path" aria-hidden>
      <svg className="about-path-svg" viewBox="0 0 440 420" role="presentation">
        <defs>
          <linearGradient id="aboutPathLine" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="rgba(239,49,36,0.75)" />
            <stop offset="70%" stopColor="rgba(255,255,255,0.28)" />
            <stop offset="100%" stopColor="rgba(22,132,91,0.7)" />
          </linearGradient>
        </defs>
        <path
          className="about-path-connector"
          d="M72 78 C 140 78, 160 150, 220 168 C 280 186, 300 250, 368 292"
          fill="none"
          stroke="url(#aboutPathLine)"
          strokeWidth="2"
          strokeDasharray="5 7"
        />
        <circle className="about-path-pulse" cx="72" cy="78" r="18" />
        <circle className="about-path-pulse about-path-pulse-delayed" cx="72" cy="78" r="18" />
      </svg>

      <div className="about-path-node about-path-node-1">
        <div className="about-path-dot about-path-dot-signal" />
        <div className="about-path-card">
          <div className="about-path-label">Новость</div>
          <div className="about-path-text">Китай ограничивает экспорт</div>
        </div>
      </div>

      <div className="about-path-node about-path-node-2">
        <div className="about-path-dot" />
        <div className="about-path-card">
          <div className="about-path-label">Ваша компания</div>
          <div className="about-path-text">Линия №2 · 24% выпуска</div>
        </div>
      </div>

      <div className="about-path-node about-path-node-3">
        <div className="about-path-dot" />
        <div className="about-path-card">
          <div className="about-path-label">Сценарии</div>
          <div className="about-path-text">3 варианта действий</div>
        </div>
      </div>

      <div className="about-path-node about-path-node-4">
        <div className="about-path-dot about-path-dot-opp" />
        <div className="about-path-card about-path-card-opp">
          <div className="about-path-label">Решение</div>
          <div className="about-path-text">План на сегодня</div>
        </div>
      </div>
    </div>
  )
}

export function AboutPage() {
  const { user, companyId } = useAuth()
  const heroCta = primaryCompanyCta(user, companyId)
  const finalCta = createProfileCta(user, companyId)
  const hasCompany = Boolean(companyId)

  return (
    <div className="about-page">
      <section className="about-hero">
        <div className="container about-hero-grid">
          <div className="about-hero-copy">
            <p className="about-kicker">Аспект · Business Intelligence</p>
            <h1>Рынок меняется. Вы понимаете, что делать.</h1>
            <p className="about-hero-lead">
              Аспект превращает рыночные сигналы в объяснимые сценарии именно для вашей компании.
            </p>
            <div className="about-hero-cta">
              <Link className="btn btn-primary" to={heroCta.to}>
                {heroCta.label}
              </Link>
              <a className="about-anchor-link" href="#about-path">
                Посмотреть путь сигнала ↓
              </a>
            </div>
          </div>
          <div className="about-hero-visual">
            <SignalPathVisual />
          </div>
        </div>
      </section>

      <section className="about-section" id="about-path">
        <div className="container">
          <div className="about-section-head">
            <p className="about-section-kicker">Путь сигнала</p>
            <h2>Как работает Аспект</h2>
            <p>
              Сигнал рынка → контекст вашей компании → оценка влияния → сценарии и решение.
            </p>
          </div>

          <div className="about-steps">
            {STEPS.map((step, i) => (
              <article key={step.n} className="about-step">
                {i < STEPS.length - 1 ? <span className="about-step-line" aria-hidden /> : null}
                <div className="about-step-top">
                  <span className="about-step-num">{step.n}</span>
                  <span className="about-step-icon">
                    <StepIcon kind={step.icon} />
                  </span>
                </div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="about-section about-section-example">
        <div className="container">
          <div className="about-section-head">
            <p className="about-section-kicker">Пример</p>
            <h2>Одна новость — понятный путь до действия</h2>
          </div>

          <div className="about-example-grid">
            <article className="about-example-card about-example-signal">
              <span className="chip chip-risk">Высокое влияние</span>
              <h3>Китай ограничивает экспорт электроники</h3>
              <p>Ограничение касается компонентов для Линии №2</p>
              <div className="about-example-metrics">
                <div>
                  <div className="lbl">Влияние</div>
                  <div className="val">87/100</div>
                </div>
                <div>
                  <div className="lbl">Уверенность</div>
                  <div className="val">85%</div>
                </div>
                <div>
                  <div className="lbl">Под риском</div>
                  <div className="val">24%</div>
                </div>
              </div>
            </article>

            <article className="about-example-card about-example-actions">
              <h3>Что можно сделать сейчас</h3>
              <ul>
                {ACTIONS.map((a) => (
                  <li key={a.title}>
                    <div className="about-action-title">{a.title}</div>
                    <div className="about-action-result">{a.result}</div>
                  </li>
                ))}
              </ul>
            </article>
          </div>
        </div>
      </section>

      <section className="about-section">
        <div className="container">
          <div className="about-section-head">
            <p className="about-section-kicker">Принципы</p>
            <h2>Как мы работаем с решениями</h2>
          </div>
          <div className="about-principles">
            {PRINCIPLES.map((p) => (
              <article key={p.title} className="about-principle">
                <div className="about-principle-icon">
                  <PrincipleIcon kind={p.icon} />
                </div>
                <h3>{p.title}</h3>
                <p>{p.text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="about-final">
        <div className="container about-final-inner">
          <div>
            <h2>
              {hasCompany ? 'Контекст компании уже подключён' : 'Начните с контекста компании'}
            </h2>
            <p>
              {hasCompany
                ? 'Откройте персональную ленту — те же новости с оценкой влияния на ваш бизнес.'
                : 'Несколько минут настройки — и новости начнут говорить о вашем бизнесе.'}
            </p>
          </div>
          <div className="about-final-cta">
            <Link className="btn btn-primary" to={finalCta.to}>
              {finalCta.label}
            </Link>
            <Link className="about-anchor-link about-anchor-link-light" to="/news">
              Смотреть новости
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}
