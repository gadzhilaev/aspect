import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { postLoginPath } from '../lib/setupPath'
import { publicUrl } from '../lib/assets'

export function LoginPage() {
  const { user, companyId, loading, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? null

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!loading && user) {
    return <Navigate to={postLoginPath(user, companyId, from)} replace />
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const me = await login(email.trim(), password)
      const cid =
        me.companies.find((c) => c.company_id)?.company_id ??
        me.companies[0]?.company_id ??
        null
      navigate(postLoginPath(me, cid, from), { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось войти')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={onSubmit}>
        <Link className="auth-card-back" to="/">
          ‹ Назад
        </Link>
        <div className="auth-card-brand" aria-hidden>
          <img src={publicUrl("logo.svg")} alt="" width={44} height={36} />
        </div>
        <div>
          <h1>Войти</h1>
          <p className="page-lead" style={{ marginTop: 8 }}>
            После входа те же новости дополняются влиянием на вашу компанию.
          </p>
        </div>
        <div className="field">
          <label htmlFor="login-email">Рабочая почта</label>
          <input
            id="login-email"
            type="email"
            autoComplete="username"
            placeholder="name@company.ru"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">Пароль</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error ? <div className="form-error">{error}</div> : null}
        <button className="btn btn-primary" type="submit" disabled={submitting}>
          {submitting ? 'Входим…' : 'Войти'}
        </button>
        <p className="auth-card-footer">
          Нет аккаунта? <Link to="/register">Зарегистрируйтесь</Link>
        </p>
      </form>
    </div>
  )
}
