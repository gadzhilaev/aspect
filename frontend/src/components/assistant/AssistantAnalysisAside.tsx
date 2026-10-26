import type { Impact } from '../../api/types'

type Props = {
  impact: Impact
}

function IconBars() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 19V10M10 19V5M16 19v-7M22 19V8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function IconShield() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3l7 3v5c0 4.5-3 8.2-7 9.5C8 19.2 5 15.5 5 11V6l7-3z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconGrid() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="4" y="4" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
    </svg>
  )
}

function IconLink() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M10 14a5 5 0 007.07 0l2.12-2.12a5 5 0 00-7.07-7.07L11 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M14 10a5 5 0 00-7.07 0L4.8 12.12a5 5 0 007.07 7.07L13 18"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}

function IconAlert() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
      <path d="M12 8v5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="16.5" r="1" fill="currentColor" />
    </svg>
  )
}

function meaningsFor(impact: Impact): Array<{ icon: 'grid' | 'link' | 'alert'; text: string }> {
  const state = impact.assessment_state || 'monitoring_only'
  const hasPaths = (impact.paths?.length ?? 0) > 0

  const second =
    state === 'finance_data_required'
      ? 'Для точной оценки нужны финансовые параметры компании.'
      : hasPaths
        ? 'Влияние оценивается по цепочке зависимостей.'
        : 'Влияние оценивается по доступному контексту компании.'

  const third =
    state === 'monitoring_only'
      ? 'Полный расчёт по цепочке для этого сигнала недоступен — режим мониторинга.'
      : state === 'finance_data_required'
        ? 'После заполнения финансов появится расчётная оценка.'
        : 'Оценка построена на доступных данных компании.'

  return [
    { icon: 'grid', text: impact.reason_summary || 'Сигнал обработан в контексте компании.' },
    { icon: 'link', text: second },
    { icon: 'alert', text: third },
  ]
}

export function AssistantAnalysisAside({ impact }: Props) {
  const state = impact.assessment_state || 'monitoring_only'
  const score = Math.round(impact.impact_score)
  const confidencePct = Math.round(impact.confidence * 100)
  const hidePreciseScore = state === 'finance_data_required' || state === 'monitoring_only'
  const scoreKind = impact.score_kind || impact.assessment_explanation?.score_kind
  const scoreLabel =
    impact.metric_labels?.impact_score ||
    impact.score_kind_label ||
    (scoreKind === 'event_severity_signal' ? 'Сигнал события' : 'Индекс влияния')
  const meanings = meaningsFor(impact)

  return (
    <aside className="assistant-aside" aria-label="Итоги анализа">
      <h3 className="assistant-aside-title">Итоги анализа</h3>

      <div className="assistant-aside-metrics">
        <div className="assistant-aside-metric">
          <div className="assistant-aside-metric-icon" aria-hidden>
            <IconBars />
          </div>
          <div className="assistant-aside-metric-body">
            <div className="assistant-aside-metric-label">{scoreLabel}</div>
            <div className="assistant-aside-metric-value">
              {hidePreciseScore
                ? state === 'finance_data_required'
                  ? 'Нужны параметры'
                  : 'Мониторинг'
                : `${score} из 100`}
            </div>
            {!hidePreciseScore ? (
              <div className="assistant-aside-bar" aria-hidden>
                <span style={{ width: `${Math.min(100, Math.max(0, score))}%` }} />
              </div>
            ) : null}
          </div>
        </div>

        <div className="assistant-aside-metric">
          <div className="assistant-aside-metric-icon" aria-hidden>
            <IconShield />
          </div>
          <div className="assistant-aside-metric-body">
            <div className="assistant-aside-metric-label">Качество данных</div>
            <div className="assistant-aside-metric-value">{confidencePct}%</div>
            <div className="assistant-aside-bar" aria-hidden>
              <span style={{ width: `${Math.min(100, Math.max(0, confidencePct))}%` }} />
            </div>
          </div>
        </div>
      </div>

      <h3 className="assistant-aside-title assistant-aside-title-secondary">Что это значит</h3>
      <ul className="assistant-aside-meanings">
        {meanings.map((m) => (
          <li key={m.text}>
            <span className="assistant-aside-meaning-icon" aria-hidden>
              {m.icon === 'grid' ? <IconGrid /> : null}
              {m.icon === 'link' ? <IconLink /> : null}
              {m.icon === 'alert' ? <IconAlert /> : null}
            </span>
            <span>{m.text}</span>
          </li>
        ))}
      </ul>
    </aside>
  )
}
