import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { authApi } from '../api/endpoints'
import { useAuth } from '../auth/AuthContext'
import { publicUrl } from '../lib/assets'

export function RegisterPage() {
  const { user, loading, login } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [step, setStep] = useState<'register' | 'verify'>('register')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hint, setHint] = useState<string | null>(null)

  if (!loading && user) return <Navigate to="/news/for-you" replace />

  async function onRegister(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const res = await authApi.register(email.trim(), password, name.trim())
      if (res.details?.demo_code) {
        setCode(res.details.demo_code)
        setHint(`Код подтверждения: ${res.details.demo_code}`)
      }
      setStep('verify')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось зарегистрироваться')
    } finally {
      setSubmitting(false)
    }
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await authApi.verifyEmail(email.trim(), code.trim())
      await login(email.trim(), password)
      navigate('/company/setup', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось подтвердить почту')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-shell">
      {step === 'register' ? (
        <form className="auth-card" onSubmit={onRegister}>
          <Link className="auth-card-back" to="/login">
            ‹ Назад
          </Link>
          <div className="auth-card-brand" aria-hidden>
            <img src={publicUrl("logo.svg")} alt="" width={44} height={36} />
          </div>
          <div>
            <h1>Создайте аккаунт</h1>
            <p className="page-lead" style={{ marginTop: 8 }}>
              Рабочая почта подойдёт лучше всего. Затем добавьте компанию — и новости станут
              персональными.
            </p>
          </div>
          <div className="field">
            <label htmlFor="reg-name">ФИО</label>
            <input
              id="reg-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="reg-email">Рабочая почта</label>
            <input
              id="reg-email"
              type="email"
              placeholder="name@company.ru"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="reg-password">Пароль</label>
            <input
              id="reg-password"
              type="password"
              minLength={8}
              placeholder="Не менее 8 символов"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error ? <div className="form-error">{error}</div> : null}
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? 'Создаём…' : 'Продолжить'}
          </button>
          <p className="auth-card-footer">
            Уже есть аккаунт? <Link to="/login">Войти</Link>
          </p>
        </form>
      ) : (
        <form className="auth-card" onSubmit={onVerify}>
          <button
            type="button"
            className="auth-card-back"
            onClick={() => {
              setStep('register')
              setError(null)
            }}
          >
            ‹ Назад
          </button>
          <div className="auth-card-brand" aria-hidden>
            <img src={publicUrl("logo.svg")} alt="" width={44} height={36} />
          </div>
          <div>
            <h1>Подтверждение</h1>
            <p className="page-lead" style={{ marginTop: 8 }}>
              Мы отправили код на почту {email}
            </p>
            {hint ? <p className="page-meta">{hint}</p> : null}
          </div>
          <div className="field">
            <label htmlFor="reg-code">Код из письма</label>
            <input
              id="reg-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              inputMode="numeric"
              autoComplete="one-time-code"
            />
          </div>
          {error ? <div className="form-error">{error}</div> : null}
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? 'Проверяем…' : 'Подтвердить'}
          </button>
        </form>
      )}
    </div>
  )
}
