import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/endpoints'
import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../theme/ThemeContext'
import type { ThemePreference } from '../theme/theme'

export function AccountSettingsPage() {
  const { user, refreshUser, logout } = useAuth()
  const { preference, setPreference } = useTheme()
  const navigate = useNavigate()
  const [theme, setTheme] = useState<ThemePreference>(user?.preferences?.theme_mode ?? preference)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [deletePassword, setDeletePassword] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function perform(action: () => Promise<void>) {
    if (busy) return
    setBusy(true); setError(''); setMessage('')
    try { await action() }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось выполнить запрос') }
    finally { setBusy(false) }
  }
  function saveTheme(e: FormEvent) {
    e.preventDefault()
    void perform(async () => {
      await authApi.preferences({ theme_mode: theme })
      setPreference(theme)
      await refreshUser()
      setMessage('Тема сохранена в аккаунте.')
    })
  }
  function changePassword(e: FormEvent) {
    e.preventDefault()
    if (next !== repeat) { setError('Новые пароли не совпадают'); return }
    void perform(async () => {
      await authApi.changePassword(current, next)
      setCurrent(''); setNext(''); setRepeat('')
      logout(); navigate('/login', { replace: true })
    })
  }
  function deleteAccount(e: FormEvent) {
    e.preventDefault()
    if (!confirmed) return
    void perform(async () => {
      await authApi.deleteAccount(deletePassword)
      setDeletePassword('')
      logout(); navigate('/register', { replace: true })
    })
  }
  return <div className="container page-pad integration-form">
    <p className="page-kicker">Аккаунт</p>
    <h1 className="page-title">Настройки</h1>
    <p className="page-lead">{user?.display_name} · {user?.email}</p>
    <p style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 10 }}>
      <Link className="btn btn-secondary" to="/support">Чат поддержки</Link>
      <Link className="btn btn-secondary" to="/notifications">Уведомления в Telegram</Link>
    </p>
    {error && <p role="alert" className="form-error">{error}</p>}
    {message && <p role="status">{message}</p>}
    <div className="company-section-stack">
      <form className="company-section-card" onSubmit={saveTheme}>
        <h2>Оформление</h2>
        <fieldset disabled={busy}>
          <div className="field"><label htmlFor="account-theme">Тема аккаунта</label>
            <select id="account-theme" value={theme} onChange={e => setTheme(e.target.value as ThemePreference)}>
              <option value="system">Как в системе</option><option value="light">Светлая</option><option value="dark">Тёмная</option>
            </select></div>
          <button className="btn btn-primary" type="submit">Сохранить тему</button>
        </fieldset>
      </form>
      <form className="company-section-card" onSubmit={changePassword}>
        <h2>Смена пароля</h2>
        <p>После смены потребуется войти на этом устройстве заново. Другие выданные сессии действуют до истечения срока.</p>
        <fieldset disabled={busy}>
          <div className="field"><label htmlFor="current-password">Текущий пароль</label><input id="current-password" type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} maxLength={128} required /></div>
          <div className="field"><label htmlFor="new-password">Новый пароль</label><input id="new-password" type="password" autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} minLength={8} maxLength={128} required /></div>
          <div className="field"><label htmlFor="repeat-password">Повторите новый пароль</label><input id="repeat-password" type="password" autoComplete="new-password" value={repeat} onChange={e => setRepeat(e.target.value)} minLength={8} maxLength={128} required /></div>
          <button className="btn btn-primary" type="submit">Изменить пароль и выйти</button>
        </fieldset>
      </form>
      <form className="company-section-card" onSubmit={deleteAccount}>
        <h2>Удаление аккаунта</h2>
        <p>Компании не удаляются. Сервер откажет в удалении, если вы единственный владелец компании или у вас есть сохранённые сценарии и решения.</p>
        <fieldset disabled={busy}>
          <div className="field"><label htmlFor="delete-password">Подтвердите текущим паролем</label><input id="delete-password" type="password" autoComplete="current-password" value={deletePassword} onChange={e => setDeletePassword(e.target.value)} maxLength={128} required /></div>
          <label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} required /> Хочу удалить свой аккаунт</label>
          <button className="btn btn-secondary" type="submit" disabled={!confirmed}>Удалить аккаунт</button>
        </fieldset>
      </form>
    </div>
  </div>
}
