import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Impact } from '../../api/types'
import { claimLabel, nodeTypeLabel } from '../../lib/format'
import { sanitizeDisplayText } from '../../lib/scenarioMetrics'
import { financeSetupPath } from '../../lib/setupPath'
import { AssessmentExplainDialog } from './AssessmentExplainDialog'

type Props = {
  companyName: string
  impact: Impact
  eventId: string
  /** Confirmed decision for this event, if any */
  decisionId?: string | null
  /** Hide CTA buttons when already on the impact page */
  showActions?: boolean
}

function labelsOf(impact: Impact) {
  const fromApi = impact.metric_labels || impact.assessment_explanation?.metric_labels || {}
  const scoreKind = impact.score_kind || impact.assessment_explanation?.score_kind
  const defaultImpact =
    scoreKind === 'event_severity_signal'
      ? 'Сигнал события'
      : impact.score_kind_label || 'Индекс влияния'
  return {
    impact: fromApi.impact_score || defaultImpact,
    confidence: fromApi.confidence || 'Качество данных',
    exposure: impact.exposure?.label || fromApi.exposure || 'Доля выпуска, связанная с узлом',
  }
}

function HowCalculatedLink({ onOpen }: { onOpen: () => void }) {
  return (
    <button type="button" className="assessment-how-link" onClick={onOpen}>
      Как рассчитано
    </button>
  )
}

export function ImpactPanel({
  companyName,
  impact,
  eventId,
  decisionId = null,
  showActions = true,
}: Props) {
  const [explainOpen, setExplainOpen] = useState(false)
  const state = impact.assessment_state || 'monitoring_only'
  const labels = labelsOf(impact)
  const explanation = impact.assessment_explanation
  const fullPath =
    impact.paths
      .slice()
      .sort((a, b) => b.sort_order - a.sort_order)
      .find((p) => (p.path_nodes?.length ?? 0) > 1) ?? impact.paths[0]

  const dialog = (
    <AssessmentExplainDialog
      open={explainOpen}
      onClose={() => setExplainOpen(false)}
      explanation={explanation}
      companyName={companyName}
    />
  )

  if (state === 'finance_data_required') {
    return (
      <>
        <aside className="impact-panel" aria-label="Влияние на вашу компанию">
          <div className="chip chip-risk">Для {companyName}</div>
          <h3>Как это касается вас</h3>
          <p className="impact-panel-lead">{sanitizeDisplayText(impact.reason_summary)}</p>

          <div className="metrics">
            <div className="metric metric-span">
              <div className="lbl">Оценка влияния</div>
              <div className="val metric-val-lg">Нужны финансовые параметры</div>
            </div>
          </div>

          {explanation ? <HowCalculatedLink onOpen={() => setExplainOpen(true)} /> : null}

          <div className="impact-panel-actions">
            {showActions ? (
              <Link className="btn btn-secondary" to={`/events/${eventId}/assistant`}>
                Обсудить с Аспектом
              </Link>
            ) : null}
            <Link className="btn btn-primary" to={financeSetupPath({ eventId })}>
              Настроить финансовый контекст
            </Link>
          </div>
        </aside>
        {dialog}
      </>
    )
  }

  if (state === 'monitoring_only') {
    return (
      <>
        <aside className="impact-panel" aria-label="Влияние на вашу компанию">
          <div className="chip">Для {companyName}</div>
          <h3>Как это касается вас</h3>
          <p className="impact-panel-lead">{sanitizeDisplayText(impact.reason_summary)}</p>
          <div className="metrics">
            <div className="metric metric-span">
              <div className="lbl">Статус</div>
              <div className="val metric-val-lg">Только мониторинг</div>
            </div>
          </div>
          <p className="impact-panel-lead impact-panel-lead-gap">
            Отсутствие найденной цепочки не означает, что риска нет — модель пока не связала
            событие с долей выпуска. Уточните контекст компании или следите за обновлениями.
          </p>
          {explanation ? <HowCalculatedLink onOpen={() => setExplainOpen(true)} /> : null}
          <div className="impact-panel-actions">
            {showActions ? (
              <Link className="btn btn-primary" to={`/events/${eventId}/assistant`}>
                Обсудить с Аспектом
              </Link>
            ) : null}
            <Link className="btn btn-secondary" to="/company/setup">
              Уточнить контекст компании
            </Link>
            <Link className="btn btn-ghost" to="/news/for-you">
              К ленте «Для вас»
            </Link>
          </div>
        </aside>
        {dialog}
      </>
    )
  }

  if (state === 'finance_ready') {
    return (
      <>
        <aside className="impact-panel" aria-label="Влияние на вашу компанию">
          <div className="chip chip-risk">Для {companyName}</div>
          <h3>Как это касается вас</h3>
          <p className="impact-panel-lead">{sanitizeDisplayText(impact.reason_summary)}</p>
          <div className="chip chip-demo">Сигнал события · не полный индекс</div>
          <div className="metrics">
            <div className="metric">
              <div className="lbl">{labels.impact}</div>
              <div className="val">{Math.round(impact.impact_score)}</div>
            </div>
            <div className="metric">
              <div className="lbl">{labels.confidence}</div>
              <div className="val">{Math.round(impact.confidence * 100)}%</div>
            </div>
          </div>
          <p className="impact-panel-lead impact-panel-lead-gap">
            Число выше — предварительный ориентир по серьёзности события. Финансовый эффект
            считается отдельными сценариями, а не этим полем.
          </p>
          {explanation ? <HowCalculatedLink onOpen={() => setExplainOpen(true)} /> : null}
          {showActions || decisionId ? (
            <div className="impact-panel-actions">
              {showActions ? (
                <>
                  <Link className="btn btn-primary" to={`/events/${eventId}/assistant`}>
                    Обсудить с Аспектом
                  </Link>
                  <Link className="btn btn-secondary" to={`/events/${eventId}/impact`}>
                    Разобрать событие
                  </Link>
                </>
              ) : null}
              {decisionId ? (
                <Link className="btn btn-secondary" to={`/decisions/${decisionId}`}>
                  Открыть решение
                </Link>
              ) : null}
            </div>
          ) : null}
        </aside>
        {dialog}
      </>
    )
  }

  return (
    <>
      <aside className="impact-panel" aria-label="Влияние на вашу компанию">
        <div className="chip chip-risk">Для {companyName}</div>
        <h3>Как это касается вас</h3>
        <p className="impact-panel-lead">{sanitizeDisplayText(impact.reason_summary)}</p>

        <div className="metrics">
          <div className="metric">
            <div className="lbl">{labels.impact}</div>
            <div className="val">{Math.round(impact.impact_score)}</div>
          </div>
          <div className="metric">
            <div className="lbl">{labels.confidence}</div>
            <div className="val">{Math.round(impact.confidence * 100)}%</div>
          </div>
          <div className="metric">
            <div className="lbl">{labels.exposure}</div>
            <div className="val">
              {impact.exposure != null && typeof impact.exposure.value === 'number'
                ? `${impact.exposure.value}${impact.exposure.unit === 'percent' ? '%' : ''}`
                : '—'}
            </div>
          </div>
        </div>

        {explanation ? <HowCalculatedLink onOpen={() => setExplainOpen(true)} /> : null}

        {fullPath && (fullPath.path_nodes?.length ?? 0) > 0 ? (
          <>
            <div className="impact-panel-section-title">Цепочка влияния</div>
            <div className="path-list">
              {fullPath.path_nodes.map((node, idx) => (
                <div className="path-item" key={`${node.id ?? node.name}-${idx}`}>
                  <div className="path-dot" />
                  <div>
                    <div className="path-node-name">{node.name}</div>
                    <div className="path-node-meta">
                      {nodeTypeLabel(node.node_type)}
                      {node.output_share_percent != null
                        ? ` · ${node.output_share_percent}% выпуска`
                        : ''}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="chip">{claimLabel(fullPath.claim_type)}</div>
          </>
        ) : null}

        {showActions || decisionId ? (
          <div className="impact-panel-actions">
            {showActions ? (
              <>
                <Link className="btn btn-primary" to={`/events/${eventId}/assistant`}>
                  Обсудить с Аспектом
                </Link>
                <Link className="btn btn-secondary" to={`/events/${eventId}/impact`}>
                  Разобрать событие
                </Link>
                <Link className="btn btn-ghost" to={`/scenarios?event=${eventId}`}>
                  Сценарии
                </Link>
              </>
            ) : null}
            {decisionId ? (
              <Link
                className={showActions ? 'btn btn-ghost' : 'btn btn-primary'}
                to={`/decisions/${decisionId}`}
              >
                Открыть решение
              </Link>
            ) : null}
          </div>
        ) : null}
      </aside>
      {dialog}
    </>
  )
}
