import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  notificationsApi,
  type NotificationSettings,
  type TelegramOutboxStatus,
} from '../api/endpoints'
import { useAuth } from '../auth/AuthContext'
import { StateBlock } from '../components/ui/StateBlock'

function newRequestId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `tg-test-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function statusLabel(status: string | undefined) {
  switch (status) {
    case 'pending':
    case 'retry':
      return 'В очереди'
    case 'sent':
      return 'Отправлено ботом (прочтение не подтверждено)'
    case 'failed':
      return 'Ошибка отправки'
    case 'skipped':
      return 'Пропущено'
    case 'blocked':
      return 'Бот заблокирован'
    case 'uncertain':
      return 'Неопределённый результат (таймаут)'
    default:
      return status || '—'
  }
}

function TelegramMark({ state }: { state: 'idle' | 'waiting' | 'linked' }) {
  return (
    <div
      className={`notif-status-mark${
        state === 'linked' ? ' is-linked' : state === 'waiting' ? ' is-waiting' : ''
      }`}
      aria-hidden
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
        <path
          d="M21 5L3.5 11.5 9 13.5 11 20l3-5.5L20 8.5"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <path d="M9 13.5L20 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  )
}

export function NotificationsPage() {
  const { user, companyId, setCompanyId } = useAuth()
  const [settings, setSettings] = useState<NotificationSettings | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [linkInfo, setLinkInfo] = useState<{ deep_link: string; expires_at: string } | null>(
    null,
  )
  const [waiting, setWaiting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [testNote, setTestNote] = useState<string | null>(null)
  const [outbox, setOutbox] = useState<TelegramOutboxStatus | null>(null)
  const pollRef = useRef<number | null>(null)

  const companies = user?.companies ?? []
  const activeId = companyId || companies[0]?.company_id || null

  const load = useCallback(async () => {
    if (!activeId) {
      setSettings(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await notificationsApi.settings(activeId)
      setSettings(data)
    } catch (err) {
      setSettings(null)
      setError(err instanceof Error ? err.message : 'Не удалось загрузить настройки')
    } finally {
      setLoading(false)
    }
  }, [activeId])

  useEffect(() => {
    setLinkInfo(null)
    setWaiting(false)
    setTestNote(null)
    setOutbox(null)
    void load()
  }, [load, activeId])

  useEffect(() => {
    if (!waiting || !activeId) return
    const id = window.setInterval(() => {
      void load()
    }, 2500)
    return () => window.clearInterval(id)
  }, [waiting, activeId, load])

  useEffect(() => {
    if (waiting && settings?.telegram_private?.linked) {
      setWaiting(false)
      setLinkInfo(null)
    }
  }, [waiting, settings])

  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [])

  async function onConnect() {
    if (!activeId) return
    setBusy(true)
    setError(null)
    try {
      const res = await notificationsApi.linkToken(activeId)
      setLinkInfo({ deep_link: res.deep_link, expires_at: res.expires_at })
      setWaiting(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать ссылку')
    } finally {
      setBusy(false)
    }
  }

  async function onToggleNotifications(enabled: boolean) {
    const subId = settings?.telegram_private?.id
    if (!subId) return
    setBusy(true)
    try {
      await notificationsApi.patchSubscription(subId, { is_active: enabled })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось обновить')
    } finally {
      setBusy(false)
    }
  }

  async function onUnlink() {
    const subId = settings?.telegram_private?.id
    if (!subId) return
    if (!window.confirm('Отвязать Telegram для этой компании?')) return
    setBusy(true)
    try {
      await notificationsApi.unlink(subId)
      setLinkInfo(null)
      setWaiting(false)
      setOutbox(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось отвязать')
    } finally {
      setBusy(false)
    }
  }

  async function onTestSend() {
    if (!activeId) return
    setBusy(true)
    setTestNote(null)
    setOutbox(null)
    const reqId = newRequestId()
    try {
      const res = await notificationsApi.testSend(activeId, reqId)
      setTestNote(
        res.message ||
          (res.queued
            ? 'Сообщение поставлено в очередь — это ещё не доставка.'
            : 'Повтор того же запроса — новая постановка не создана.'),
      )
      if (res.outbox_id) {
        const poll = async () => {
          try {
            const st = await notificationsApi.outboxStatus(res.outbox_id!)
            setOutbox(st)
            if (st.status === 'pending' || st.status === 'retry' || st.status === 'uncertain') {
              return
            }
            if (pollRef.current) {
              window.clearInterval(pollRef.current)
              pollRef.current = null
            }
          } catch {
            /* ignore transient */
          }
        }
        await poll()
        if (pollRef.current) window.clearInterval(pollRef.current)
        pollRef.current = window.setInterval(poll, 2000)
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setTestNote('Слишком часто. Подождите минуту и повторите.')
      } else {
        setError(err instanceof Error ? err.message : 'Тестовая отправка не удалась')
      }
    } finally {
      setBusy(false)
    }
  }

  if (!user) {
    return (
      <div className="container notif-shell">
        <p className="page-kicker">Аккаунт</p>
        <h1 className="page-title">Уведомления</h1>
        <StateBlock
          variant="empty"
          title="Нужен вход"
          description="Войдите, чтобы управлять Telegram-уведомлениями."
        />
        <div className="notif-actions" style={{ marginTop: 16 }}>
          <Link className="btn btn-primary" to="/login">
            Войти
          </Link>
        </div>
      </div>
    )
  }

  if (!activeId) {
    return (
      <div className="container notif-shell">
        <Link className="notif-back" to="/settings">
          ‹ К настройкам
        </Link>
        <p className="page-kicker">Аккаунт</p>
        <h1 className="page-title">Уведомления</h1>
        <StateBlock
          variant="empty"
          title="Нет компании"
          description="Создайте или выберите компанию — Telegram привязывается к конкретной компании."
        />
        <div className="notif-actions" style={{ marginTop: 16 }}>
          <Link className="btn btn-primary" to="/company/setup">
            К профилю компании
          </Link>
        </div>
      </div>
    )
  }

  const tg = settings?.telegram_private
  const linked = Boolean(tg?.linked)
  const enabled = Boolean(tg?.notifications_enabled)
  const markState = linked ? 'linked' : waiting ? 'waiting' : 'idle'
  const headline = !linked
    ? waiting
      ? 'Ожидание подключения…'
      : 'Telegram не подключён'
    : enabled
      ? 'Уведомления включены'
      : 'Подключён · уведомления выключены'
  const badgeClass = !linked
    ? waiting
      ? 'is-wait'
      : 'is-off'
    : enabled
      ? 'is-on'
      : 'is-off'
  const badgeText = !linked
    ? waiting
      ? 'Ждём Start в боте'
      : 'Не подключён'
    : enabled
      ? 'Активно'
      : 'Выключено'

  return (
    <div className="container notif-shell">
      <Link className="notif-back" to="/settings">
        ‹ К настройкам
      </Link>
      <p className="page-kicker">Аккаунт</p>
      <h1 className="page-title">Уведомления</h1>
      <p className="page-lead">
        Личный Telegram для выбранной компании. Привязка и тест доступны всегда.
      </p>

      <div className="notif-layout">
        <div className="notif-main">
          <div className="surface-panel notif-panel">
            <label className="label" htmlFor="tg-company">
              Компания
            </label>
            <div className="field">
              <select
                id="tg-company"
                value={activeId}
                onChange={(e) => setCompanyId(e.target.value)}
              >
                {companies.map((c) => (
                  <option key={c.company_id} value={c.company_id}>
                    {c.name || c.company_id}
                  </option>
                ))}
              </select>
            </div>
            <p className="notif-note">
              {settings?.scope_note ||
                'Настройки действуют только для выбранной компании и вашего аккаунта.'}
            </p>
          </div>

          {loading ? <StateBlock variant="loading" title="Загружаем статус" /> : null}
          {error ? (
            <StateBlock
              variant="error"
              title="Ошибка"
              description={error}
              onRetry={() => void load()}
            />
          ) : null}

          {!loading && tg ? (
            <div className="notif-status-card">
              <div className="notif-status-top">
                <TelegramMark state={markState} />
                <div className="notif-status-copy">
                  <h2>{headline}</h2>
                  <span className={`notif-status-badge ${badgeClass}`}>{badgeText}</span>
                </div>
              </div>

              <p className="notif-meta-line">
                {tg.status_label}
                {tg.chat_title ? ` · ${tg.chat_title}` : ''}
              </p>

              <div className="notif-actions">
                {!linked ? (
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busy}
                    onClick={() => void onConnect()}
                  >
                    Подключить Telegram
                  </button>
                ) : null}
                {linked ? (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={busy}
                      onClick={() => void onToggleNotifications(!enabled)}
                    >
                      {enabled ? 'Выключить уведомления' : 'Включить уведомления'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy || !enabled}
                      onClick={() => void onTestSend()}
                    >
                      Тестовое сообщение
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      disabled={busy}
                      onClick={() => void onUnlink()}
                    >
                      Отвязать
                    </button>
                  </>
                ) : null}
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={busy}
                  onClick={() => void load()}
                >
                  Обновить статус
                </button>
              </div>

              {linkInfo ? (
                <div className="notif-link-box">
                  <p>
                    Откройте ссылку на телефоне и нажмите Start в <strong>личном</strong> чате с
                    ботом. Само открытие ссылки не подтверждает привязку.
                  </p>
                  <a
                    className="btn btn-primary"
                    href={linkInfo.deep_link}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Открыть бота
                  </a>
                  <p className="notif-note">
                    Ссылка действует до {new Date(linkInfo.expires_at).toLocaleString()}
                  </p>
                </div>
              ) : null}

              {waiting && !linked ? (
                <p className="notif-note">
                  Ждём подтверждение от бота… Можно обновить статус вручную.
                </p>
              ) : null}

              {testNote ? <p className="notif-meta-line">{testNote}</p> : null}
              {outbox ? (
                <p className="notif-note">
                  Очередь: {statusLabel(outbox.status)}
                  {outbox.message ? ` — ${outbox.message}` : ''}
                </p>
              ) : null}

              <p className="notif-note">
                Выключение сохраняет привязку. Отвязка удаляет связь для этой компании. Команда
                /unlink в боте отвязывает все компании этого чата.
              </p>
            </div>
          ) : null}
        </div>

        <aside className="notif-aside" aria-label="Справка и переходы">
          <div className="surface-panel notif-panel">
            <p className="label">Как подключить</p>
            <ol className="notif-steps">
              <li>Выберите компанию слева.</li>
              <li>Нажмите «Подключить Telegram».</li>
              <li>Откройте ссылку на телефоне и нажмите Start в личном чате с ботом.</li>
            </ol>
          </div>

          {settings?.news_policy_note || settings ? (
            <div className="notif-policy">
              <p className="label" style={{ marginBottom: 8 }}>
                Политика рассылки
              </p>
              <p>
                {settings?.news_policy_note ||
                  'Автоуведомления о новостях на сервере по умолчанию выключены.'}
                {settings?.news_notifications_server_enabled
                  ? ' Серверный флаг: включён.'
                  : ' Серверный флаг: выключен.'}{' '}
                В v1 при включении уходят только риск-события с актуальным расчётом влияния выше
                порога.
              </p>
            </div>
          ) : null}

          <div className="surface-panel notif-panel">
            <p className="label">Ещё</p>
            <div className="notif-footer-links">
              <Link to="/settings">Настройки аккаунта</Link>
              <Link to="/company">Компания</Link>
              <Link to="/news/for-you">Лента для вас</Link>
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
