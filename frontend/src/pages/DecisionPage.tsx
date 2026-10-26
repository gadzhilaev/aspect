import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { decisionsApi } from '../api/endpoints'
import type { DecisionActionItem, DecisionDetail } from '../api/decisionTypes'
import { StateBlock } from '../components/ui/StateBlock'
import { useAsync } from '../hooks/useAsync'
import { presentFinanceScenario } from '../lib/financeScenarioPresentation'
import { formatDate } from '../lib/format'

const ACTIVE_CONFIRMED = new Set(['selected', 'confirmed', 'accepted', 'done'])

function statusChipClass(status: string): string {
  if (status === 'done') return 'chip chip-opp'
  if (status === 'in_progress') return 'chip chip-risk'
  return 'chip'
}

function ActionRow({
  item,
  busy,
  locked,
  onToggle,
}: {
  item: DecisionActionItem
  busy: boolean
  locked: boolean
  onToggle: (item: DecisionActionItem) => void
}) {
  const done = item.status === 'done'
  return (
    <li className={`decision-action${done ? ' is-done' : ''}${locked ? ' is-locked' : ''}`}>
      <label className="decision-action-check">
        <input
          type="checkbox"
          checked={done}
          disabled={busy || locked}
          onChange={() => onToggle(item)}
          aria-label={
            locked
              ? 'Действие недоступно — план отменён'
              : done
                ? 'Отметить как невыполненное'
                : 'Отметить выполненным'
          }
        />
        <span className="decision-action-box" aria-hidden />
      </label>
      <div className="decision-action-body">
        <div className="decision-action-title">{item.title}</div>
        <div className="decision-action-meta">
          {item.assignee_name ? <span>{item.assignee_name}</span> : null}
          {item.assignee_name && item.due_at ? <span>·</span> : null}
          {item.due_at ? <span>до {formatDate(item.due_at)}</span> : null}
          {!item.assignee_name && !item.due_at ? <span>Срок не задан</span> : null}
        </div>
      </div>
      <span className={statusChipClass(item.status)}>{item.status_label}</span>
    </li>
  )
}

function CancelDialog({
  open,
  busy,
  error,
  onClose,
  onConfirm,
}: {
  open: boolean
  busy: boolean
  error: string | null
  onClose: () => void
  onConfirm: (reason: string) => void
}) {
  const [reason, setReason] = useState('')

  useEffect(() => {
    if (!open) setReason('')
  }, [open])

  if (!open) return null

  return (
    <div className="decision-dialog-backdrop" role="presentation" onClick={onClose}>
      <div
        className="decision-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="decision-cancel-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="decision-cancel-title">Отменить план?</h2>
        <p>План останется в истории, но больше не будет считаться активным.</p>
        <label className="decision-dialog-field">
          <span>Причина отмены</span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder="Необязательно"
            disabled={busy}
          />
        </label>
        {error ? <div className="form-error">{error}</div> : null}
        <div className="decision-dialog-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>
            Оставить план
          </button>
          <button
            type="button"
            className="btn btn-danger"
            disabled={busy}
            onClick={() => onConfirm(reason.trim())}
          >
            {busy ? 'Отменяем…' : 'Отменить план'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function DecisionPage() {
  const { decisionId = '' } = useParams()
  const { data, error, loading, reload } = useAsync(
    () => decisionsApi.get(decisionId),
    [decisionId],
  )
  const [local, setLocal] = useState<DecisionDetail | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelBusy, setCancelBusy] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)

  useEffect(() => {
    setLocal(null)
    setActionError(null)
    setCancelOpen(false)
    setCancelError(null)
  }, [decisionId])

  const decision = local ?? data
  const cancelled = decision?.status === 'cancelled' || Boolean(decision?.actions_locked)
  const activeConfirmed = decision ? ACTIVE_CONFIRMED.has(decision.status) : false

  async function toggleAction(item: DecisionActionItem) {
    if (!decision || cancelled) return
    setActionError(null)
    setBusyId(item.id)
    const nextStatus = item.status === 'done' ? 'todo' : 'done'
    try {
      const res = await decisionsApi.patchActionItem(item.id, { status: nextStatus })
      setLocal({
        ...decision,
        progress: res.progress,
        action_items: decision.action_items.map((a) =>
          a.id === item.id
            ? {
                id: res.id,
                title: res.title,
                status: res.status,
                status_label: res.status_label,
                assignee_name: res.assignee_name,
                due_at: res.due_at,
              }
            : a,
        ),
      })
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Не удалось обновить действие')
    } finally {
      setBusyId(null)
    }
  }

  async function confirmCancel(reason: string) {
    if (!decision) return
    setCancelError(null)
    setCancelBusy(true)
    try {
      const res = await decisionsApi.cancel(decision.id, reason ? { reason } : {})
      setLocal(res)
      setCancelOpen(false)
    } catch (e) {
      setCancelError(e instanceof Error ? e.message : 'Не удалось отменить план')
    } finally {
      setCancelBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="container page-pad">
        <StateBlock variant="loading" title="Открываем план действий" />
      </div>
    )
  }

  if (error || !decision) {
    const denied = error instanceof ApiError && (error.status === 403 || error.status === 404)
    return (
      <div className="container page-pad">
        <StateBlock
          variant="error"
          title={denied ? 'Решение недоступно' : 'Не удалось открыть решение'}
          description={
            denied
              ? 'Нет доступа к этому решению или оно не найдено.'
              : error?.message
          }
          onRetry={denied ? undefined : reload}
        />
        <div className="decision-fallback-actions">
          <Link className="btn btn-primary" to="/scenarios">
            ← К сценариям
          </Link>
        </div>
      </div>
    )
  }

  if (!activeConfirmed && !cancelled) {
    return (
      <div className="container page-pad">
        <StateBlock
          variant="empty"
          title="Решение ещё не подтверждено"
          description="Вернитесь к обсуждению с Аспектом, выберите сценарий и подтвердите план."
        />
        <div className="decision-fallback-actions">
          {decision.conversation_href ? (
            <Link className="btn btn-primary" to={decision.conversation_href}>
              Открыть обсуждение
            </Link>
          ) : null}
          <Link className="btn btn-secondary" to="/scenarios">
            ← К сценариям
          </Link>
        </div>
      </div>
    )
  }

  const progressRatio =
    decision.progress.total > 0 ? decision.progress.done / decision.progress.total : 0

  return (
    <div className="decision-page">
      <div className="container decision-wrap">
        <Link className="decision-back" to="/scenarios">
          ← К сценариям
        </Link>

        <header className="decision-hero">
          <div className="decision-hero-meta">
            <span className="chip">{decision.event.category_label}</span>
            {decision.event.is_demo ? <span className="chip chip-demo">Демо</span> : null}
            <span className={cancelled ? 'chip' : 'chip chip-opp'}>{decision.status_label}</span>
          </div>
          <p className="decision-event-title">{decision.event.title}</p>
          {decision.event.occurred_at ? (
            <p className="decision-event-date">{formatDate(decision.event.occurred_at)}</p>
          ) : null}

          <h1>{decision.title}</h1>
          <p className="decision-summary">{decision.summary}</p>

          {cancelled ? (
            <div className="decision-cancelled-note">
              {decision.cancelled_at ? (
                <p>
                  Отменён {formatDate(decision.cancelled_at)}
                  {decision.cancel_reason ? ` · ${decision.cancel_reason}` : ''}
                </p>
              ) : decision.cancel_reason ? (
                <p>{decision.cancel_reason}</p>
              ) : (
                <p>План сохранён в истории и больше не считается активным.</p>
              )}
            </div>
          ) : null}
        </header>

        {cancelled ? (
          <div className="decision-cancelled-actions">
            <Link className="btn btn-secondary" to="/scenarios">
              Вернуться к сценариям
            </Link>
            {decision.conversation_href ? (
              <Link className="btn btn-primary" to={decision.conversation_href}>
                Подобрать новый вариант с Аспектом
              </Link>
            ) : (
              <Link className="btn btn-primary" to={`/events/${decision.event.id}/assistant`}>
                Подобрать новый вариант с Аспектом
              </Link>
            )}
          </div>
        ) : null}

        <section className="decision-metrics" aria-label="Результат решения">
          <article className="decision-metric">
            <div className="decision-metric-label">Ожидаемый эффект</div>
            <div className="decision-metric-value">
              {decision.expected_effect ?? 'Расчётный эффект уточняется'}
            </div>
          </article>
          <article className="decision-metric">
            <div className="decision-metric-label">Горизонт</div>
            <div className="decision-metric-value">{decision.horizon ?? 'Ближайшие 14 дней'}</div>
          </article>
          {decision.confidence != null ? (
            <article className="decision-metric">
              <div className="decision-metric-label">Качество исходных данных</div>
              <div className="decision-metric-value">
                {Math.round(decision.confidence * 100)}%
              </div>
            </article>
          ) : null}
          <article className="decision-metric decision-metric-progress">
            <div className="decision-metric-label">Статус выполнения</div>
            <div className="decision-metric-value">{decision.progress.label}</div>
            <div
              className="decision-progress-bar"
              aria-hidden
              style={{ ['--progress-ratio' as string]: String(progressRatio) }}
            >
              <span />
            </div>
          </article>
        </section>

        <section className="decision-section">
          <div className="decision-section-head">
            <h2>План действий</h2>
            <p>
              {cancelled
                ? 'Действия заморожены — план отменён.'
                : 'Отмечайте шаги по мере выполнения — прогресс обновится сразу.'}
            </p>
          </div>

          {actionError ? <div className="form-error">{actionError}</div> : null}

          {decision.action_items.length === 0 ? (
            <div className="decision-empty">
              <h3>Действий пока нет</h3>
              <p>Вернитесь к обсуждению с Аспектом, чтобы уточнить план.</p>
              {decision.conversation_href ? (
                <Link className="btn btn-primary" to={decision.conversation_href}>
                  Открыть обсуждение
                </Link>
              ) : null}
            </div>
          ) : (
            <ul className="decision-actions">
              {decision.action_items.map((item) => (
                <ActionRow
                  key={item.id}
                  item={item}
                  busy={busyId === item.id}
                  locked={cancelled}
                  onToggle={toggleAction}
                />
              ))}
            </ul>
          )}
        </section>

        <section className="decision-section">
          <div className="decision-section-head">
            <h2>Основание решения</h2>
          </div>
          <div className="decision-basis">
            <div>
              <div className="decision-basis-label">Выбранный сценарий</div>
              <div className="decision-basis-value">{decision.scenario.title}</div>
              {decision.scenario.presentation ? (
                <div style={{ marginTop: 8 }}>
                  {(() => {
                    const pres = presentFinanceScenario({
                      presentation: decision.scenario.presentation,
                    })
                    return (
                      <>
                        {pres.assumption_badge ? (
                          <span className="chip" style={{ marginRight: 6 }}>
                            {pres.assumption_badge}
                          </span>
                        ) : null}
                        {pres.legacy ? (
                          <span className="chip chip-demo">Историческая модель</span>
                        ) : null}
                        {pres.rate_fact_line ? (
                          <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
                            {pres.rate_fact_line}
                          </p>
                        ) : null}
                        {pres.what_if_line ? (
                          <p className="muted" style={{ marginTop: 4, fontSize: 13 }}>
                            {pres.what_if_line}
                          </p>
                        ) : null}
                        {pres.money_line ? (
                          <p style={{ marginTop: 4, fontSize: 13 }}>{pres.money_line}</p>
                        ) : null}
                        {pres.historical_note ? (
                          <p className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                            {pres.historical_note}
                          </p>
                        ) : null}
                        {pres.credit_transfer_disclaimer ? (
                          <p className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                            {pres.credit_transfer_disclaimer}
                          </p>
                        ) : null}
                      </>
                    )
                  })()}
                </div>
              ) : null}
            </div>
            <div>
              <div className="decision-basis-label">Почему этот вариант</div>
              <div className="decision-basis-value">{decision.scenario.reason}</div>
            </div>
            <div>
              <div className="decision-basis-label">Связь с новостью</div>
              <div className="decision-basis-value">{decision.event.title}</div>
            </div>
            <div className="decision-basis-links">
              {decision.conversation_href ? (
                <Link className="btn btn-primary" to={decision.conversation_href}>
                  Открыть обсуждение с Аспектом
                </Link>
              ) : null}
              <Link className="btn btn-secondary" to={decision.news_href}>
                Открыть новость
              </Link>
              {activeConfirmed && !cancelled ? (
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    setCancelError(null)
                    setCancelOpen(true)
                  }}
                >
                  Отменить план
                </button>
              ) : null}
            </div>
          </div>
          <p className="decision-disclaimer">{decision.disclaimer}</p>
        </section>
      </div>

      <CancelDialog
        open={cancelOpen}
        busy={cancelBusy}
        error={cancelError}
        onClose={() => {
          if (!cancelBusy) setCancelOpen(false)
        }}
        onConfirm={confirmCancel}
      />
    </div>
  )
}
