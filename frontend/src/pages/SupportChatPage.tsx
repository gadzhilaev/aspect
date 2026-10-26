import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { supportApi, type SupportMessage } from '../api/endpoints'
import { useAuth } from '../auth/AuthContext'
import { StateBlock } from '../components/ui/StateBlock'

function newClientId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `c_${crypto.randomUUID()}`
  }
  return `c_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

function roleLabel(role: SupportMessage['role']) {
  switch (role) {
    case 'user':
      return 'Вы'
    case 'operator':
      return 'Оператор'
    case 'system':
      return ''
    default:
      return 'Поддержка AI'
  }
}

export function SupportChatPage() {
  const { companyId } = useAuth()
  const [messages, setMessages] = useState<SupportMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const knownIds = useRef<Set<string>>(new Set())

  const scrollEnd = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [])

  const mergeMessages = useCallback((rows: SupportMessage[]) => {
    setMessages((prev) => {
      const map = new Map(prev.map((m) => [m.id, m]))
      for (const row of rows) {
        map.set(row.id, row)
        knownIds.current.add(row.id)
      }
      return Array.from(map.values()).sort((a, b) =>
        a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0,
      )
    })
  }, [])

  const bootstrap = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const thread = await supportApi.getThread(companyId || undefined)
      knownIds.current = new Set(thread.messages.map((m) => m.id))
      setMessages(thread.messages)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось открыть чат')
    } finally {
      setLoading(false)
      requestAnimationFrame(scrollEnd)
    }
  }, [companyId, scrollEnd])

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  useEffect(() => {
    const id = window.setInterval(() => {
      if (busy || loading) return
      void (async () => {
        try {
          const rows = await supportApi.listMessages()
          const fresh = rows.filter((m) => !knownIds.current.has(m.id))
          if (fresh.length === 0) return
          mergeMessages(rows)
          requestAnimationFrame(scrollEnd)
        } catch {
          /* ignore poll errors */
        }
      })()
    }, 2000)
    return () => window.clearInterval(id)
  }, [busy, loading, mergeMessages, scrollEnd])

  async function onSend(e: FormEvent) {
    e.preventDefault()
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    setBusy(true)
    setError(null)
    try {
      const res = await supportApi.postMessage({
        content: text,
        client_message_id: newClientId(),
        company_id: companyId || undefined,
      })
      const next = [res.user_message]
      if (res.support_message) next.push(res.support_message)
      mergeMessages(next)
      requestAnimationFrame(scrollEnd)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отправить')
      setDraft(text)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="container page-pad support-page">
      <p className="page-kicker">
        <Link to="/settings">‹ Настройки</Link>
      </p>
      <h1 className="page-title">Чат поддержки</h1>
      <p className="page-lead">
        Сначала отвечает AI. Если не уверен — подключаем оператора.
      </p>

      {error ? <p role="alert" className="form-error">{error}</p> : null}

      <div className="support-chat">
        <div className="support-chat-log" aria-live="polite">
          {loading ? (
            <StateBlock variant="loading" title="Загрузка" description="Открываем диалог…" />
          ) : messages.length === 0 ? (
            <StateBlock variant="empty" title="Пусто" description="Напишите вопрос ниже." />
          ) : (
            messages.map((m) => {
              const label = roleLabel(m.role)
              if (m.role === 'system') {
                return (
                  <p key={m.id} className="support-system">
                    {m.content}
                  </p>
                )
              }
              const mine = m.role === 'user'
              return (
                <div
                  key={m.id}
                  className={`support-bubble-wrap${mine ? ' is-mine' : ''}`}
                >
                  {label ? <div className="support-sender">{label}</div> : null}
                  <div className={`support-bubble${mine ? ' is-mine' : ''}`}>
                    {m.content}
                  </div>
                </div>
              )
            })
          )}
          <div ref={bottomRef} />
        </div>

        <form className="support-composer" onSubmit={onSend}>
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Напишите вопрос…"
            maxLength={4000}
            disabled={busy || loading}
            aria-label="Сообщение"
          />
          <button className="btn btn-primary" type="submit" disabled={busy || loading || !draft.trim()}>
            Отправить
          </button>
        </form>
      </div>
    </div>
  )
}
