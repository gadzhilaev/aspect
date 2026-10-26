import { useEffect, useId, useRef } from 'react'
import type { AssessmentExplanation } from '../../api/types'

type Props = {
  open: boolean
  onClose: () => void
  explanation: AssessmentExplanation | null | undefined
  companyName: string
}

export function AssessmentExplainDialog({ open, onClose, explanation, companyName }: Props) {
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    previouslyFocused.current = document.activeElement as HTMLElement | null
    const t = window.setTimeout(() => closeRef.current?.focus(), 0)
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(t)
      document.removeEventListener('keydown', onKey)
      previouslyFocused.current?.focus?.()
    }
  }, [open, onClose])

  if (!open || !explanation) return null

  return (
    <div
      className="assessment-explain-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="assessment-explain-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="assessment-explain-head">
          <h2 id={titleId}>Как рассчитано</h2>
          <button
            ref={closeRef}
            type="button"
            className="btn btn-ghost"
            aria-label="Закрыть"
            onClick={onClose}
          >
            Закрыть
          </button>
        </div>

        <p className="assessment-explain-summary">{explanation.summary}</p>
        <p className="muted assessment-explain-meta">
          Компания: {companyName}
          {explanation.is_demo_event ? ' · Демо-событие' : ''}
          {explanation.score_kind_label
            ? ` · ${explanation.score_kind_label}`
            : explanation.score_kind
              ? ` · ${explanation.score_kind}`
              : ''}
          {explanation.model_version ? ` · ${explanation.model_version}` : ''}
          {!explanation.basis_available
            ? ' · Полное основание этой записи не сохранено'
            : null}
        </p>

        <section className="assessment-explain-section">
          <h3>Что означает оценка</h3>
          <ul>
            {explanation.metrics.map((m) => (
              <li key={m.key}>
                <strong>
                  {m.label}
                  {m.value != null
                    ? `: ${m.unit === 'ratio_0_1' ? `${Math.round(Number(m.value) * 100)}%` : m.value}${
                        m.unit === 'percent' ? '%' : m.unit === 'index_0_100' ? ' из 100' : ''
                      }`
                    : ''}
                </strong>
                <span>{m.meaning}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="assessment-explain-section">
          <h3>На каких данных основана</h3>
          {(explanation.used_event_data.length ||
            explanation.used_company_data.length ||
            explanation.dependencies.length) === 0 ? (
            <p className="muted">Конкретный снимок данных для этой записи недоступен.</p>
          ) : (
            <ul>
              {explanation.used_event_data.map((line) => (
                <li key={`e-${line}`}>{line}</li>
              ))}
              {explanation.used_company_data.map((line) => (
                <li key={`c-${line}`}>{line}</li>
              ))}
              {explanation.dependencies.map((line) => (
                <li key={`d-${line}`}>Цепочка: {line}</li>
              ))}
            </ul>
          )}
          {explanation.calculation ? (
            <p className="assessment-explain-calc">{explanation.calculation}</p>
          ) : null}
          {explanation.assumptions.length ? (
            <>
              <h4>Допущения</h4>
              <ul>
                {explanation.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </>
          ) : null}
        </section>

        <section className="assessment-explain-section">
          <h3>Что пока неизвестно</h3>
          {explanation.missing_data.length === 0 && explanation.limitations.length === 0 ? (
            <p className="muted">Явных пробелов в этом снимке не указано.</p>
          ) : (
            <ul>
              {explanation.missing_data.map((m) => (
                <li key={`m-${m}`}>Не хватает: {m}</li>
              ))}
              {explanation.limitations.map((m) => (
                <li key={`l-${m}`}>{m}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
