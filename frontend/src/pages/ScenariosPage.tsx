import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { assistantApi } from '../api/endpoints'
import type { AssistantConversationListItem } from '../api/assistantTypes'
import { useAuth } from '../auth/AuthContext'
import { StateBlock } from '../components/ui/StateBlock'
import { useAsync } from '../hooks/useAsync'
import {
  conversationUiStatus,
  conversationUiStatusLabel,
  displayMetricNumber,
  hasImpactCalculation,
  type UiConversationStatus,
} from '../lib/assistantWithoutImpact'
import { formatDate } from '../lib/format'
import { sanitizeDisplayText } from '../lib/scenarioMetrics'

const CATEGORY_LABEL: Record<string, string> = {
  geopolitics: 'Геополитика',
  macro: 'Макроэкономика',
  market: 'Рынки',
  electronics: 'Электроника',
  equipment: 'Оборудование',
  logistics: 'Логистика',
  energy: 'Энергетика',
}

type GroupKey = 'today' | 'week' | 'earlier'

const GROUP_TITLE: Record<GroupKey, string> = {
  today: 'Сегодня',
  week: 'На этой неделе',
  earlier: 'Ранее',
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function groupKey(iso: string, now = new Date()): GroupKey {
  const updated = new Date(iso)
  if (Number.isNaN(updated.getTime())) return 'earlier'
  const today = startOfDay(now)
  const day = startOfDay(updated)
  const diffDays = Math.round((today.getTime() - day.getTime()) / 86_400_000)
  if (diffDays <= 0) return 'today'
  if (diffDays < 7) return 'week'
  return 'earlier'
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  if (startOfDay(d).getTime() === startOfDay(now).getTime()) {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  return formatDate(iso)
}

function uiStatusClass(status: UiConversationStatus): string {
  if (status === 'done') return 'chip chip-opp'
  if (status === 'action') return 'chip chip-risk'
  return 'chip'
}

function groupItems(items: AssistantConversationListItem[]) {
  const buckets: Record<GroupKey, AssistantConversationListItem[]> = {
    today: [],
    week: [],
    earlier: [],
  }
  for (const item of items) {
    buckets[groupKey(item.updated_at)].push(item)
  }
  return (['today', 'week', 'earlier'] as const)
    .filter((k) => buckets[k].length > 0)
    .map((k) => ({
      key: k,
      title: GROUP_TITLE[k],
      items: buckets[k],
    }))
}

function rowToneClass(item: AssistantConversationListItem): string {
  const status = conversationUiStatus(item)
  if (status === 'done') return 'is-tone-done'
  if (status === 'action') return 'is-tone-action'
  const hasCalc = hasImpactCalculation(item)
  const score = displayMetricNumber(item.impact_score, { hasCalculation: hasCalc })
  if (score != null && score >= 70) return 'is-tone-high'
  if (score != null && score >= 40) return 'is-tone-medium'
  if (item.event_category === 'electronics' || item.event_category === 'market') {
    return 'is-tone-opp'
  }
  return ''
}

function ConversationRow({
  item,
  selected,
  onSelect,
}: {
  item: AssistantConversationListItem
  selected: boolean
  onSelect: () => void
}) {
  const status = conversationUiStatus(item)
  const hasCalc = hasImpactCalculation(item)
  const score = displayMetricNumber(item.impact_score, { hasCalculation: hasCalc })
  const tone = rowToneClass(item)
  return (
    <button
      type="button"
      className={`scenarios-row${selected ? ' is-selected' : ''}${tone ? ` ${tone}` : ''}`}
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
    >
      <div className="scenarios-row-meta">
        <span className="chip">{CATEGORY_LABEL[item.event_category] ?? item.event_category}</span>
        <span className={uiStatusClass(status)}>{conversationUiStatusLabel(status)}</span>
        {item.is_demo ? <span className="chip chip-demo">Демо</span> : null}
      </div>
      <div className="scenarios-row-title">{item.event_title}</div>
      <div className="scenarios-row-footer">
        <time dateTime={item.updated_at}>{formatTime(item.updated_at)}</time>
        {score != null ? (
          <span className="scenarios-row-impact">Индекс влияния {Math.round(score)}</span>
        ) : !hasCalc ? (
          <span className="scenarios-row-impact muted">Без расчётной оценки</span>
        ) : null}
      </div>
    </button>
  )
}

function DetailPane({
  item,
  onBack,
}: {
  item: AssistantConversationListItem
  onBack?: () => void
}) {
  const status = conversationUiStatus(item)
  const hasCalc = hasImpactCalculation(item)
  const score = displayMetricNumber(item.impact_score, { hasCalculation: hasCalc })
  const confidence = displayMetricNumber(item.confidence, { hasCalculation: hasCalc })
  return (
    <div className="scenarios-detail">
      {onBack ? (
        <button type="button" className="btn btn-ghost scenarios-mobile-back" onClick={onBack}>
          ← К списку
        </button>
      ) : null}

      <div className="scenarios-detail-meta">
        <span className="chip">{CATEGORY_LABEL[item.event_category] ?? item.event_category}</span>
        <span className={uiStatusClass(status)}>{conversationUiStatusLabel(status)}</span>
        {item.is_demo ? <span className="chip chip-demo">Демо</span> : null}
      </div>
      <h2 className="scenarios-detail-title">{item.event_title}</h2>
      <p className="scenarios-detail-time">
        Последнее сообщение · <time dateTime={item.updated_at}>{formatTime(item.updated_at)}</time>
      </p>

      <div className="scenarios-detail-stats">
        {score != null ? (
          <div className="scenarios-stat">
            <div className="lbl">Индекс влияния</div>
            <div className="val">{Math.round(score)}</div>
          </div>
        ) : (
          <div className="scenarios-stat">
            <div className="lbl">Расчётная оценка</div>
            <div className="val" style={{ fontSize: 16 }}>
              {hasCalc ? '—' : 'Пока недоступна'}
            </div>
          </div>
        )}
        {confidence != null ? (
          <div className="scenarios-stat">
            <div className="lbl">Качество данных</div>
            <div className="val">{Math.round(confidence * 100)}%</div>
          </div>
        ) : null}
        <div className="scenarios-stat">
          <div className="lbl">Сценарии</div>
          <div className="val">
            {item.has_scenarios || item.status === 'scenarios_ready' || item.status === 'draft_ready'
              ? 'Есть'
              : 'Пока нет'}
          </div>
        </div>
      </div>

      {item.last_message_preview ? (
        <blockquote className="scenarios-detail-preview">
          <div className="scenarios-detail-preview-label">Из обсуждения</div>
          <p>{sanitizeDisplayText(item.last_message_preview)}</p>
        </blockquote>
      ) : (
        <p className="scenarios-detail-empty-preview">Обсуждение только начато.</p>
      )}

      {status === 'done' && item.decision_id ? (
        <div className="scenarios-decision-banner">
          <div>
            <strong>Решение принято</strong>
            <p>План действий сохранён и доступен для команды.</p>
          </div>
          <Link className="btn btn-secondary" to={`/decisions/${item.decision_id}`}>
            Открыть план действий
          </Link>
        </div>
      ) : null}

      {status === 'cancelled' && item.decision_id ? (
        <div className="scenarios-decision-banner scenarios-decision-banner-muted">
          <div>
            <strong>План отменён</strong>
            <p>Запись сохранена в истории и больше не считается активным решением.</p>
          </div>
          <Link className="btn btn-secondary" to={`/decisions/${item.decision_id}`}>
            Открыть в истории
          </Link>
        </div>
      ) : null}

      <div className="scenarios-detail-actions">
        <Link className="btn btn-primary" to={`/events/${item.event_id}/assistant`}>
          {status === 'cancelled' ? 'Подобрать новый вариант' : 'Продолжить обсуждение'}
        </Link>
        <Link className="btn btn-secondary" to={`/news/${item.event_id}`}>
          Открыть новость
        </Link>
      </div>
    </div>
  )
}

export function ScenariosPage() {
  const { companyId } = useAuth()
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [mobileDetail, setMobileDetail] = useState(false)
  const selectedId = params.get('id')
  const eventFilter = params.get('event')

  const { data, error, loading, reload } = useAsync(() => {
    if (!companyId) return Promise.reject(new Error('Сначала выберите компанию'))
    return assistantApi.conversations(companyId)
  }, [companyId])

  const items = data ?? []
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter((item) => item.event_title.toLowerCase().includes(q))
  }, [items, query])

  const groups = useMemo(() => groupItems(filtered), [filtered])

  const selected = useMemo(() => {
    if (!filtered.length) return null
    if (selectedId) {
      return filtered.find((i) => i.id === selectedId) ?? filtered[0]
    }
    if (eventFilter) {
      return filtered.find((i) => i.event_id === eventFilter) ?? filtered[0]
    }
    return filtered[0]
  }, [filtered, selectedId, eventFilter])

  useEffect(() => {
    if (!selected) return
    if (selectedId === selected.id) return
    // Desktop keeps a selection synced to URL; mobile stays on list until tap.
    if (typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches) {
      return
    }
    const next = new URLSearchParams(params)
    next.set('id', selected.id)
    if (eventFilter) next.delete('event')
    setParams(next, { replace: true })
  }, [selected, selectedId, eventFilter, params, setParams])

  function selectItem(id: string) {
    const next = new URLSearchParams(params)
    next.set('id', id)
    setParams(next)
    setMobileDetail(true)
  }

  function backToList() {
    setMobileDetail(false)
  }

  if (!companyId) {
    return (
      <div className="container page-pad">
        <StateBlock
          variant="empty"
          title="Нет компании в профиле"
          description="Настройте контекст компании — затем разборы появятся здесь."
        />
        <div style={{ marginTop: 16 }}>
          <Link className="btn btn-primary" to="/company/setup">
            Настроить под компанию
          </Link>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="container page-pad">
        <StateBlock variant="loading" title="Загружаем сценарии" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="container page-pad">
        <StateBlock
          variant="error"
          title="Не удалось загрузить сценарии"
          description={error.message}
          onRetry={reload}
        />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="scenarios-shell">
        <div className="container scenarios-empty-page">
          <p className="scenarios-kicker">Сценарии</p>
          <h1>Сценарии</h1>
          <p className="scenarios-lead">Диалоги по важным событиям</p>
          <div className="scenarios-empty-card">
            <h2>Пока нет обсуждений</h2>
            <p>
              Откройте опубликованную новость в общей ленте или в «Для вас» и обсудите её с
              Аспектом — здесь появится история, привязанная к этой новости.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
              <Link className="btn btn-primary" to="/news">
                Все новости
              </Link>
              <Link className="btn btn-secondary" to="/news/for-you">
                Лента для вас
              </Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const workspaceMode = mobileDetail ? 'is-detail' : 'is-list'

  return (
    <div className="scenarios-shell">
      <div className={`container scenarios-workspace ${workspaceMode}`}>
        <aside className="scenarios-sidebar" aria-label="История обсуждений">
          <div className="scenarios-sidebar-head">
            <p className="scenarios-kicker">Сценарии</p>
            <h1>Сценарии</h1>
            <p className="scenarios-lead">Диалоги по важным событиям</p>
            <label className="scenarios-search">
              <span className="sr-only">Поиск по событиям</span>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Поиск по событиям"
                autoComplete="off"
              />
            </label>
          </div>

          {filtered.length === 0 ? (
            <div className="scenarios-sidebar-empty">
              Ничего не найдено по запросу «{query.trim()}»
            </div>
          ) : (
            <div className="scenarios-sidebar-list">
              {groups.map((group) => (
                <section key={group.key} className="scenarios-group">
                  <h2 className="scenarios-group-title">{group.title}</h2>
                  <div className="scenarios-rows">
                    {group.items.map((item) => (
                      <ConversationRow
                        key={item.id}
                        item={item}
                        selected={selected?.id === item.id}
                        onSelect={() => selectItem(item.id)}
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </aside>

        <section className="scenarios-main" aria-label="Выбранное обсуждение">
          {selected ? (
            <DetailPane item={selected} onBack={backToList} />
          ) : (
            <div className="scenarios-main-placeholder">Выберите обсуждение слева</div>
          )}
        </section>
      </div>
    </div>
  )
}
