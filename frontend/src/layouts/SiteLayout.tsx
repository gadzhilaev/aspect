import { useEffect, useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ThemeToggle } from '../components/ui/ThemeToggle'
import { isAgentDemoStand } from '../lib/agentDemo'
import { primaryCompanyCta } from '../lib/setupPath'
import { publicUrl } from '../lib/assets'

const PUBLIC_NAV = [
  { to: '/', label: 'Главная', match: 'home' as const },
  { to: '/news', label: 'Новости', match: 'news' as const },
  { to: '/about', label: 'Как это работает', match: 'path' as const },
]

const AUTH_NAV = [
  { to: '/scenarios', label: 'Сценарии', match: 'scenarios' as const },
  { to: '/notifications', label: 'Уведомления', match: 'path' as const },
]
const DEMO_NAV = [{ to: '/agent-demo', label: 'Демостенд', match: 'demo' as const }]

function isNavActive(
  match: 'home' | 'news' | 'scenarios' | 'path' | 'demo',
  to: string,
  pathname: string,
) {
  if (match === 'home') {
    return pathname === '/'
  }
  if (match === 'news') {
    return pathname === '/news' || pathname.startsWith('/news/')
  }
  if (match === 'scenarios') {
    return pathname === '/scenarios' || pathname.startsWith('/scenarios/')
  }
  if (match === 'demo') {
    return pathname === '/agent-demo' || pathname.startsWith('/agent-demo/')
  }
  const path = to.split('?')[0]
  return pathname === path
}

export function SiteLayout() {
  const { user, companyId, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const navigate = useNavigate()
  const location = useLocation()

  function onSearch(e: FormEvent) {
    e.preventDefault()
    const query = q.trim()
    navigate(query ? `/news?q=${encodeURIComponent(query)}` : '/news')
    setOpen(false)
  }

  const companyCta = primaryCompanyCta(user, companyId)
  const isAssistantRoute = /\/events\/[^/]+\/assistant\/?$/.test(location.pathname)

  useEffect(() => {
    setOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!open) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open])

  return (
    <div className={`site${isAssistantRoute ? ' site-assistant-mode' : ''}`}>
      <header className="site-header">
        <div className="container header-inner">
          <Link className="logo" to="/" aria-label="Аспект — на главную">
            <img className="logo-mark" src={publicUrl("logo.svg")} alt="" width={28} height={24} />
            <span className="logo-wordmark">Аспект</span>
          </Link>

          <nav className="nav-desktop" aria-label="Основная навигация">
            {PUBLIC_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={() =>
                  isNavActive(item.match, item.to, location.pathname) ? 'active' : undefined
                }
              >
                {item.label}
              </NavLink>
            ))}
            {user
              ? AUTH_NAV.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={() =>
                      isNavActive(item.match, item.to, location.pathname) ? 'active' : undefined
                    }
                  >
                    {item.label}
                  </NavLink>
                ))
              : null}
            {user && isAgentDemoStand()
              ? DEMO_NAV.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={() =>
                      isNavActive(item.match, item.to, location.pathname) ? 'active' : undefined
                    }
                  >
                    {item.label}
                  </NavLink>
                ))
              : null}
          </nav>

          <div className="header-actions">
            <form className="search-wrap" onSubmit={onSearch} role="search">
              <label className="sr-only" htmlFor="site-search">
                Поиск новостей
              </label>
              <input
                id="site-search"
                type="search"
                placeholder="Поиск"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </form>

            <ThemeToggle className="theme-toggle-desktop" />

            {user ? (
              <>
                <Link className="account-pill" to={companyId ? '/company' : '/news/for-you'}>
                  {companyId ? 'Профиль' : 'Аккаунт'}
                </Link>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    logout()
                    navigate('/')
                  }}
                >
                  Выйти
                </button>
              </>
            ) : (
              <Link className="btn btn-ghost" to="/login">
                Войти
              </Link>
            )}

            <Link className="btn btn-primary" to={companyCta.to}>
              <span className="cta-full">{companyCta.label}</span>
              <span className="cta-short">{companyCta.shortLabel}</span>
            </Link>

            <button
              type="button"
              className="menu-toggle"
              aria-expanded={open}
              aria-controls="mobile-nav"
              aria-label={open ? 'Закрыть меню' : 'Открыть меню'}
              onClick={() => setOpen((v) => !v)}
            >
              ☰
            </button>
          </div>
        </div>

        <div
          id="mobile-nav"
          className={`container mobile-nav${open ? ' open' : ''}`}
          hidden={!open}
        >
          {PUBLIC_NAV.map((item) => (
            <Link key={item.to} to={item.to} onClick={() => setOpen(false)}>
              {item.label}
            </Link>
          ))}
          {user ? (
            <>
              {AUTH_NAV.map((item) => (
                <Link key={item.to} to={item.to} onClick={() => setOpen(false)}>
                  {item.label}
                </Link>
              ))}
              {isAgentDemoStand()
                ? DEMO_NAV.map((item) => (
                    <Link key={item.to} to={item.to} onClick={() => setOpen(false)}>
                      {item.label}
                    </Link>
                  ))
                : null}
              <Link to="/news/for-you" onClick={() => setOpen(false)}>
                Для вас
              </Link>
              <Link to="/company" onClick={() => setOpen(false)}>
                Компания
              </Link>
              <button
                type="button"
                className="btn btn-ghost mobile-logout"
                onClick={() => {
                  logout()
                  setOpen(false)
                  navigate('/')
                }}
              >
                Выйти
              </button>
            </>
          ) : (
            <Link to="/login" onClick={() => setOpen(false)}>
              Войти
            </Link>
          )}
          <Link
            className="btn btn-primary mobile-cta"
            to={companyCta.to}
            onClick={() => setOpen(false)}
          >
            {companyCta.label}
          </Link>
          <div className="mobile-theme-row">
            <span className="mobile-theme-label">Тема оформления</span>
            <ThemeToggle />
          </div>
          <form className="mobile-search-form" onSubmit={onSearch}>
            <label className="sr-only" htmlFor="mobile-search">
              Поиск
            </label>
            <input
              id="mobile-search"
              className="mobile-search"
              type="search"
              placeholder="Поиск новостей"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </form>
        </div>
      </header>

      <main className="site-main">
        <Outlet />
      </main>

      <footer className="site-footer">
        <div className="container">
          <div className="footer-grid">
            <div>
              <div className="footer-brand">
                <img src={publicUrl("logo.svg")} alt="" width={28} height={24} />
                <span>АСПЕКТ</span>
              </div>
              <p className="footer-lead">
                Бизнес-радар: новостное событие превращается в объяснимую цепочку влияния на вашу
                компанию.
              </p>
            </div>
            <div>
              <h4>Разделы</h4>
              <Link to="/">Главная</Link>
              <Link to="/news">Новости</Link>
              <Link to="/news/for-you">Для вас</Link>
              <Link to="/news/markets">Рынки</Link>
              <Link to="/news/industries">Отрасли</Link>
              <Link to="/news/opportunities">Возможности</Link>
            </div>
            <div>
              <h4>Продукт</h4>
              <Link to="/about">Как это работает</Link>
              <Link to={companyCta.to}>{companyCta.label}</Link>
              {user ? (
                <Link to="/company">Компания</Link>
              ) : (
                <Link to="/login">Войти</Link>
              )}
            </div>
            <div>
              <h4>После входа</h4>
              <Link to="/news/for-you">Лента для вас</Link>
              <Link to="/scenarios">Сценарии</Link>
              <Link to="/company">Компания</Link>
              <Link to="/settings">Настройки</Link>
            </div>
          </div>
          <div className="footer-copy">© {new Date().getFullYear()} Аспект</div>
        </div>
      </footer>
    </div>
  )
}
