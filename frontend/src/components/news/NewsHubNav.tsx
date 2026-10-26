import { NavLink } from 'react-router-dom'

const TABS = [
  { to: '/news', label: 'Новости', end: true },
  { to: '/news/for-you', label: 'Для вас', end: true },
  { to: '/news/markets', label: 'Рынки', end: true },
  { to: '/news/industries', label: 'Отрасли', end: true },
  { to: '/news/opportunities', label: 'Возможности', end: true },
] as const

export function NewsHubNav() {
  return (
    <nav className="news-hub-nav" aria-label="Разделы новостей">
      {TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) => (isActive ? 'active' : undefined)}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
