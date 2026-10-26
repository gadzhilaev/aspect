import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { assistantApi } from '../../api/endpoints'
import type { AssistantBlock, AssistantMessage } from '../../api/assistantTypes'
import {
  assistantOpenErrorMessage,
  canShowCalculationActions,
  draftDecisionErrorMessage,
  impactSummaryView,
  isToolUnavailableBlock,
  toolUnavailableUserMessage,
} from '../../lib/assistantWithoutImpact'
import { chooseClientMessageId } from '../../lib/assistantRetry'
import {
  presentFinanceScenario,
  sanitizeDisplayText,
  scenarioLabel,
  scenarioMetricSuffix,
} from '../../lib/scenarioMetrics'
import { SafeMarkdown } from '../../lib/safeMarkdown'
import { financeSetupPath } from '../../lib/setupPath'
import {
  FINANCE_CALC_CTA,
  FINANCE_RECALC_CTA,
  SUPPLY_COMPARE_CTA,
  buildCompareRequestBody,
  isScenarioCalcChip,
  pickDefaultScenarioId,
  showFinanceCalcCta,
  showFinanceRecalcCta,
  showSupplyCompareCta,
  unavailableNoticeFromResult,
  validateWhatIfInputs,
} from '../../lib/userTriggeredFinance'
import { BankEvidenceBlock, type BankEvidenceNavContext } from './BankEvidenceBlock'

type Props = {
  eventId: string
  companyId: string
  variant?: 'panel' | 'fullscreen'
  expanded?: boolean
  onToggleExpand?: () => void
  onClose?: () => void
}

const LABEL_RU: Record<string, string> = {
  company_calc: 'Расчёт компании',
  company_context: 'Контекст компании',
  news_source: 'Источник новости',
  bank_material: 'Материал банка',
  ai_explain: 'AI-объяснение',
  ai_explain_gigachat: 'AI-объяснение · GigaChat',
  ai_explain_hackathon: 'AI-объяснение · hackathon',
  demo_explain: 'Демо-объяснение',
  safety: 'Защита запроса',
  // Legacy stored messages → same human provenance vocabulary
  demo: 'Демо-объяснение',
  estimate: 'Расчёт компании',
}

const HIDDEN_LABEL_KEYS = new Set([
  'openai',
  'gigachat',
  'api_key',
  'assistant_provider',
  'live',
  'mock',
  'compare_scenarios',
  'get_company_impact',
  'simulate_scenario',
  'system',
  'tool',
])

const CLAIM_RU: Record<string, string> = {
  confirmed: 'Подтверждённый факт',
  confirmed_fact: 'Подтверждённый факт',
  inferences: 'Вывод модели',
  inference: 'Вывод модели',
  assumptions: 'Допущение',
  assumption: 'Допущение',
  estimates: 'Оценка',
  estimate: 'Оценка',
}

function labelRu(raw: string): string | null {
  const key = raw.trim()
  if (!key || HIDDEN_LABEL_KEYS.has(key.toLowerCase())) return null
  if (LABEL_RU[key]) return LABEL_RU[key]
  // Never show raw snake_case / technical tokens
  if (/[_A-Z]/.test(key) && key === key.toLowerCase() && key.includes('_')) return null
  if (/^[a-z]+(_[a-z0-9]+)+$/i.test(key) && !LABEL_RU[key]) return null
  return key
}

/** Prefer a single human provenance chip per block. */
const LABEL_PRIORITY = [
  'news_source',
  'bank_material',
  'company_calc',
  'estimate',
  'company_context',
  'ai_explain_hackathon',
  'ai_explain_gigachat',
  'ai_explain',
  'demo_explain',
  'demo',
  'safety',
] as const

function primaryLabel(labels?: string[]): string | null {
  let keys = [...(labels ?? [])]
  if (
    keys.includes('company_calc') ||
    keys.includes('estimate') ||
    keys.includes('news_source') ||
    keys.includes('bank_material')
  ) {
    keys = keys.filter(
      (k) =>
        k !== 'demo_explain' &&
        k !== 'demo' &&
        k !== 'ai_explain' &&
        k !== 'ai_explain_gigachat' &&
        k !== 'ai_explain_hackathon',
    )
  }
  const ranked = LABEL_PRIORITY.map((k) => keys.find((x) => x === k)).filter(Boolean) as string[]
  const pick = ranked[0] ?? keys[0]
  if (!pick) return null
  return labelRu(pick)
}

function Labels({ labels }: { labels?: string[] }) {
  const text = primaryLabel(labels)
  if (!text) return null
  return (
    <div className="assistant-block-labels" aria-label={text}>
      <span className="chip chip-demo">{text}</span>
    </div>
  )
}

function ContentBasis({
  basis,
  model,
}: {
  basis?: string | null
  model?: string | null
}) {
  if (!basis) return null
  let text = labelRu(basis)
  if (!text) return null
  if (basis === 'ai_explain_hackathon' && model) {
    text = `AI-объяснение · hackathon · ${model}`
  }
  return (
    <div className="assistant-block-labels assistant-content-basis" aria-label="На чём основан ответ">
      <span className="assistant-basis-caption">На чём основан ответ</span>
      <span className="chip chip-demo">{text}</span>
    </div>
  )
}

type SourceItem = {
  publisher?: string
  url?: string | null
  published_at?: string | null
  is_stub?: boolean
}

function dedupeSources(sources: SourceItem[]): SourceItem[] {
  const out: SourceItem[] = []
  const seen = new Set<string>()
  for (const s of sources) {
    const url = typeof s.url === 'string' ? s.url.trim() : ''
    const pub = (s.publisher ?? '').trim().toLowerCase()
    const key = url || `${pub}|${s.published_at ?? ''}`
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push(s)
  }
  return out
}

function stableQuickId(text: string): string {
  const norm = text.trim().toLowerCase().replace(/\s+/g, ' ').slice(0, 80)
  return `quick:${norm}`
}

function ScoreRing({ score }: { score: number }) {
  const clamped = Math.min(100, Math.max(0, Math.round(score)))
  const r = 34
  const c = 2 * Math.PI * r
  const offset = c * (1 - clamped / 100)
  return (
    <div className="assistant-score-ring" aria-label={`${clamped} из 100`}>
      <svg width="84" height="84" viewBox="0 0 84 84">
        <circle cx="42" cy="42" r={r} className="assistant-score-ring-track" />
        <circle
          cx="42"
          cy="42"
          r={r}
          className="assistant-score-ring-value"
          strokeDasharray={c}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="assistant-score-ring-label">
        <strong>{clamped}</strong>
        <span>из 100</span>
      </div>
    </div>
  )
}

function ClaimIcon({ kind }: { kind: string }) {
  const k = kind.toLowerCase()
  if (k.includes('confirm')) {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
        <path d="M8 12.5l2.5 2.5L16 9.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  }
  if (k.includes('infer')) {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="7" cy="12" r="2.5" stroke="currentColor" strokeWidth="2" />
        <circle cx="17" cy="7" r="2.5" stroke="currentColor" strokeWidth="2" />
        <circle cx="17" cy="17" r="2.5" stroke="currentColor" strokeWidth="2" />
        <path d="M9.2 11l5-3.2M9.2 13l5 3.2" stroke="currentColor" strokeWidth="2" />
      </svg>
    )
  }
  if (k.includes('assum')) {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M7 4h7l4 4v12a1 1 0 01-1 1H7a1 1 0 01-1-1V5a1 1 0 011-1z"
          stroke="currentColor"
          strokeWidth="2"
        />
        <path d="M14 4v4h4M9 13h6M9 17h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  }
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M5 19V9M10 19V5M15 19v-6M20 19V8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

/** In the side panel these duplicate the left column — hide them. */
const PANEL_SKIP_BLOCKS = new Set(['impact_summary', 'claim_list'])

function BlockView({
  block,
  onSelectScenario,
  selectedScenarioId,
  compact = false,
  bankNav,
  currentAssessmentState = null,
}: {
  block: AssistantBlock
  onSelectScenario?: (scenarioId: string, solutionId?: string | null) => void
  selectedScenarioId?: string | null
  compact?: boolean
  bankNav?: BankEvidenceNavContext
  currentAssessmentState?: string | null
}) {
  const financeHref = financeSetupPath({
    eventId: bankNav?.eventId,
    companyId: bankNav?.companyId,
  })
  if (compact && PANEL_SKIP_BLOCKS.has(block.type)) {
    return null
  }

  if (block.type === 'impact_summary') {
    const d = block.data as Record<string, unknown>
    const view = impactSummaryView({
      impact_score: d.impact_score,
      confidence: d.confidence,
      reason_summary: d.reason_summary,
      score_kind: d.score_kind,
      metric_labels: d.metric_labels as Record<string, string> | undefined,
      assessment_state:
        typeof d.assessment_state === 'string' ? d.assessment_state : undefined,
    })
    if (view.kind === 'unavailable') {
      return (
        <div className="assistant-block assistant-block-missing">
          <div className="assistant-block-title">{view.title}</div>
          <Labels labels={block.labels?.length ? block.labels : ['company_context']} />
          <p>{view.reason}</p>
        </div>
      )
    }
    const metricLabels = d.metric_labels as Record<string, string> | undefined
    return (
      <div className="assistant-block assistant-block-impact">
        <div className="assistant-block-impact-head">
          <div>
            <div className="assistant-block-title-row">
              <span className="assistant-block-doc-icon" aria-hidden>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M7 3h7l4 4v14a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1z"
                    stroke="currentColor"
                    strokeWidth="2"
                  />
                  <path d="M14 3v4h4M9 12h6M9 16h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </span>
              <div className="assistant-block-title">
                {block.title === 'Контекст' || !block.title ? 'Кратко о влиянии' : block.title}
              </div>
            </div>
            <Labels labels={block.labels?.length ? block.labels : ['company_calc']} />
            <p className="assistant-block-impact-reason">{view.reason}</p>
          </div>
          <ScoreRing score={view.score} />
        </div>
        <div className="assistant-confidence-row">
          <span>
            {metricLabels?.confidence || 'Качество данных'} {view.confidencePct}%
          </span>
          <div className="assistant-aside-bar" aria-hidden>
            <span style={{ width: `${Math.min(100, Math.max(0, view.confidencePct))}%` }} />
          </div>
        </div>
        <p className="assistant-block-impact-hint muted">{view.scoreHint}</p>
      </div>
    )
  }

  if (block.type === 'scenario_comparison') {
    const scenarios = (block.data.scenarios as Array<Record<string, unknown>>) ?? []
    const scenarioIds = (block.data.scenario_ids as string[]) ?? []
    const assessmentState =
      typeof block.data.assessment_state === 'string' ? block.data.assessment_state : null
    const source = typeof block.data.source === 'string' ? block.data.source : null
    const packageParams =
      block.data.parameters && typeof block.data.parameters === 'object'
        ? (block.data.parameters as Record<string, unknown>)
        : null
    const packageStatus = typeof block.data.status === 'string' ? block.data.status : null
    const packageMessage = typeof block.data.message === 'string' ? block.data.message : null
    const omittedHypotheses = Array.isArray(packageParams?.omitted_action_hypotheses)
      ? (packageParams!.omitted_action_hypotheses as Array<Record<string, unknown>>)
      : []
    let altCursor = 0
    return (
      <div className="assistant-block">
        <div className="assistant-block-title">{block.title ?? 'Сравнение сценариев'}</div>
        <Labels labels={block.labels?.length ? block.labels : ['company_calc']} />
        {packageStatus === 'unavailable' && packageMessage ? (
          <p className="muted" style={{ marginTop: 8, lineHeight: 1.45 }}>
            {packageMessage}
          </p>
        ) : null}
        <ul className="assistant-scenario-list">
          {scenarios.map((sc, i) => {
            let sid = (sc.scenario_id as string | undefined) ?? null
            if (!sid && sc.kind === 'alternative' && scenarioIds[altCursor]) {
              sid = scenarioIds[altCursor]
              altCursor += 1
            } else if (sc.kind === 'alternative') {
              altCursor += 1
            }
            const solId =
              (sc.solution_id as string | undefined) ??
              ((sc.alternative as Record<string, unknown> | undefined)?.solution_id as
                | string
                | undefined) ??
              null
            const selected = sid && selectedScenarioId === sid
            const metric = scenarioMetricSuffix(sc, assessmentState, source, packageParams)
            const pres = presentFinanceScenario(sc, packageParams)
            const isWhatIf =
              pres.basis === 'assumed' || sc.action_id === 'assumed_rate_shock'
            return (
              <li
                key={i}
                className={selected ? 'assistant-scenario-selected' : undefined}
                data-rate-basis={pres.basis}
                data-what-if={isWhatIf ? 'true' : undefined}
              >
                <div>
                  <strong>{scenarioLabel(sc, i)}</strong>
                  {pres.assumption_badge ? (
                    <span className="chip" style={{ marginLeft: 8 }}>
                      {pres.assumption_badge}
                    </span>
                  ) : null}
                  {pres.legacy ? (
                    <span className="chip chip-demo" style={{ marginLeft: 8 }}>
                      Историческая модель
                    </span>
                  ) : null}
                </div>
                {pres.rate_fact_line ? (
                  <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                    {pres.rate_fact_line}
                  </div>
                ) : null}
                {pres.what_if_line ? (
                  <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                    {pres.what_if_line}
                  </div>
                ) : null}
                {pres.money_line ? (
                  <div style={{ fontSize: 13, marginTop: 4 }}>{pres.money_line}</div>
                ) : null}
                {pres.hold_note ? (
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    {pres.hold_note}
                  </div>
                ) : null}
                {pres.credit_transfer_disclaimer ? (
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    {pres.credit_transfer_disclaimer}
                  </div>
                ) : null}
                {pres.action_model_note ? (
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    {pres.action_model_note}
                  </div>
                ) : null}
                {pres.historical_note && !pres.money_line ? (
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    {pres.historical_note}
                  </div>
                ) : null}
                {!pres.rate_fact_line &&
                !pres.what_if_line &&
                !pres.money_line &&
                metric ? (
                  <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                    {metric}
                  </div>
                ) : null}
                {sid && onSelectScenario ? (
                  <button
                    type="button"
                    className="btn btn-secondary assistant-select-scenario"
                    onClick={() => onSelectScenario(sid, solId)}
                  >
                    {selected ? 'Выбран' : 'Выбрать'}
                  </button>
                ) : null}
              </li>
            )
          })}
        </ul>
        {omittedHypotheses.length ? (
          <div className="muted" style={{ marginTop: 10, fontSize: 13, lineHeight: 1.45 }}>
            {omittedHypotheses.map((h, i) => {
              const note = typeof h.note === 'string' ? h.note : null
              const label = typeof h.label === 'string' ? h.label : 'гипотеза модели'
              return (
                <p key={i} style={{ margin: '4px 0' }}>
                  {note ??
                    `Общая гипотеза «${label}» не включена в расчётные сценарии (нет подтверждённой FX-экспозиции).`}
                </p>
              )
            })}
          </div>
        ) : null}
      </div>
    )
  }

  if (block.type === 'missing_data') {
    const d = block.data as Record<string, unknown>
    const loopIncomplete = d.reason === 'loop_incomplete' || d.not_ai_final === true
    const assessmentState =
      typeof d.assessment_state === 'string' ? d.assessment_state : undefined
    const isFinance = assessmentState === 'finance_data_required'
    const toolUnavailable = isToolUnavailableBlock(d)
    const cta = d.cta as { label?: string; href?: string } | null | undefined
    // Historical opening notice vs current conversation assessment.
    const staleUnavailable =
      !loopIncomplete &&
      assessmentState === 'calculation_unavailable' &&
      Boolean(currentAssessmentState) &&
      currentAssessmentState !== 'calculation_unavailable'
    // Incomplete loop notices are system status — never offer scenario / finance CTAs.
    const href =
      loopIncomplete || staleUnavailable
        ? undefined
        : (cta?.href ?? (isFinance && !toolUnavailable ? financeHref : undefined))
    const label =
      loopIncomplete || staleUnavailable
        ? undefined
        : (cta?.label ??
          (isFinance && !toolUnavailable ? 'Добавить финансовые параметры' : undefined))
    const message = loopIncomplete
      ? typeof d.message === 'string' && d.message
        ? d.message
        : 'Разбор не завершён. Можно отправить вопрос ещё раз.'
      : toolUnavailable
        ? toolUnavailableUserMessage(d)
        : typeof d.message === 'string' && d.message
          ? d.message
          : isFinance
            ? 'Для финансового сравнения добавьте валюту закупок, объём обязательств или горизонт планирования.'
            : 'Недостаточно данных для ответа.'
    const title = loopIncomplete
      ? (block.title ?? 'Разбор не завершён')
      : staleUnavailable
        ? 'Состояние на момент открытия обсуждения'
        : toolUnavailable
          ? 'Расчётная оценка пока недоступна'
          : (block.title ?? 'Недостаточно данных')
    return (
      <div
        className={`assistant-block assistant-block-missing${loopIncomplete ? ' assistant-block-loop-incomplete' : ''}${staleUnavailable ? ' assistant-block-historical' : ''}`}
      >
        <div className="assistant-block-title">{title}</div>
        {!compact && !loopIncomplete ? (
          <Labels labels={block.labels?.length ? block.labels : ['company_context']} />
        ) : null}
        {staleUnavailable ? (
          <p className="muted" style={{ fontSize: 13, marginBottom: 6 }}>
            Историческая запись. Сейчас расчётная оценка уже доступна — смотрите актуальный
            статус выше и блок расчёта ниже.
          </p>
        ) : null}
        <p>{String(message)}</p>
        {href && label ? (
          <div style={{ marginTop: 10 }}>
            <Link className="btn btn-primary" to={href}>
              {label}
            </Link>
          </div>
        ) : null}
      </div>
    )
  }

  if (block.type === 'action_plan_draft') {
    const d = block.data as {
      status?: string
      note?: string
      items?: string[]
      decision_id?: string | null
    }
    const isConfirmed = d.status === 'confirmed' && Boolean(d.decision_id)
    const title =
      block.title ??
      (isConfirmed ? 'Решение сохранено' : 'Черновик решения')
    return (
      <div className="assistant-block">
        <div className="assistant-block-title">{title}</div>
        <Labels labels={block.labels?.length ? block.labels : ['company_calc']} />
        <p>{d.note ?? ''}</p>
        {d.items?.length ? (
          <ul>
            {d.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
        <div className="muted">
          Статус: {isConfirmed ? 'подтверждено и сохранено' : 'черновик'}
        </div>
      </div>
    )
  }

  if (block.type === 'source_list') {
    const sources = dedupeSources((block.data.sources as SourceItem[]) ?? [])
    if (!sources.length) return null
    if (compact) {
      return (
        <div className="assistant-block assistant-block-compact">
          <div className="assistant-block-title">Источники новости</div>
          <Labels labels={['news_source']} />
          <ul className="assistant-source-list assistant-source-list-compact">
            {sources.map((s, i) => {
              const url = typeof s.url === 'string' && /^https?:\/\//i.test(s.url) ? s.url : null
              return (
                <li key={i}>
                  {url ? (
                    <a href={url} target="_blank" rel="noopener noreferrer">
                      {s.publisher ?? 'Источник'}
                    </a>
                  ) : (
                    <span>{s.publisher ?? 'Источник'}</span>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )
    }
    return (
      <div className="assistant-block assistant-block-sources">
        <div className="assistant-block-title">{block.title ?? 'Источники новости'}</div>
        <Labels labels={block.labels?.length ? block.labels : ['news_source']} />
        <ul className="assistant-source-list">
          {sources.map((s, i) => {
            const url = typeof s.url === 'string' && /^https?:\/\//i.test(s.url) ? s.url : null
            const published =
              typeof s.published_at === 'string' && s.published_at
                ? new Date(s.published_at).toLocaleDateString('ru-RU')
                : null
            return (
              <li key={i} className="assistant-source-row">
                <span className="assistant-source-name">{s.publisher ?? 'Источник'}</span>
                {published ? <span className="muted">{published}</span> : null}
                {url ? (
                  <a href={url} target="_blank" rel="noopener noreferrer">
                    Открыть оригинал
                  </a>
                ) : (
                  <span className="muted">ссылка недоступна</span>
                )}
              </li>
            )
          })}
        </ul>
      </div>
    )
  }

  if (block.type === 'bank_evidence_list') {
    return (
      <BankEvidenceBlock
        data={block.data}
        title={block.title}
        LabelsSlot={
          <Labels labels={block.labels?.length ? block.labels : ['bank_material']} />
        }
        nav={bankNav ?? {}}
        compact={compact}
      />
    )
  }

  if (block.type === 'claim_list') {
    const claims = (block.data.claims as Record<string, number>) ?? {}
    const paths = (block.data.paths as Array<{ claim_type?: string; explanation?: string }>) ?? []
    const claimOrder = ['confirmed', 'confirmed_fact', 'inferences', 'inference', 'assumptions', 'assumption', 'estimates', 'estimate']
    const entries = Object.entries(claims).sort(
      ([a], [b]) => claimOrder.indexOf(a) - claimOrder.indexOf(b),
    )
    return (
      <div className="assistant-block assistant-block-claims">
        <div className="assistant-block-title">{block.title ?? 'Основания оценки'}</div>
        <Labels labels={block.labels?.length ? block.labels : ['company_context']} />
        {entries.length ? (
          <div className="assistant-claim-cards">
            {entries.map(([key, value]) => (
              <div className="assistant-claim-card" key={key}>
                <span className="assistant-claim-icon" aria-hidden>
                  <ClaimIcon kind={key} />
                </span>
                <div className="assistant-claim-copy">
                  <div className="assistant-claim-title">
                    {CLAIM_RU[key] ?? key}: {value}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : null}
        {paths.length ? (
          <ul className="assistant-claim-paths">
            {paths.map((p, i) => (
              <li key={i}>
                <strong>{CLAIM_RU[p.claim_type ?? ''] ?? p.claim_type ?? 'Оценка'}</strong>
                {p.explanation ? <span> — {p.explanation}</span> : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    )
  }

  return null
}

function mergeSourceBlocks(blocks: AssistantBlock[]): AssistantBlock[] {
  const sources: SourceItem[] = []
  const rest: AssistantBlock[] = []
  let sourceMeta: AssistantBlock | null = null
  for (const b of blocks) {
    if (b.type === 'source_list') {
      if (!sourceMeta) sourceMeta = b
      const chunk = (b.data.sources as SourceItem[]) ?? []
      sources.push(...chunk)
    } else {
      rest.push(b)
    }
  }
  if (!sourceMeta) return blocks
  const merged: AssistantBlock = {
    ...sourceMeta,
    title: 'Источники новости',
    labels: ['news_source'],
    data: { ...sourceMeta.data, sources: dedupeSources(sources) },
  }
  // Keep sources near the end so calc/context stay first
  return [...rest, merged]
}

function renderBlockGroups(
  messageId: string,
  blocks: AssistantBlock[],
  compact: boolean,
  onSelectScenario?: (scenarioId: string, solutionId?: string | null) => void,
  selectedScenarioId?: string | null,
  bankNav?: BankEvidenceNavContext,
  currentAssessmentState?: string | null,
) {
  const normalized = mergeSourceBlocks(blocks)
  const nodes: ReactNode[] = []
  let i = 0
  while (i < normalized.length) {
    const cur = normalized[i]
    const next = normalized[i + 1]
    if (
      !compact &&
      cur.type === 'impact_summary' &&
      next?.type === 'claim_list'
    ) {
      nodes.push(
        <div className="assistant-report-card" key={`${messageId}-report-${i}`}>
          <BlockView
            block={cur}
            compact={compact}
            onSelectScenario={onSelectScenario}
            selectedScenarioId={selectedScenarioId}
            bankNav={bankNav}
            currentAssessmentState={currentAssessmentState}
          />
          <BlockView
            block={next}
            compact={compact}
            onSelectScenario={onSelectScenario}
            selectedScenarioId={selectedScenarioId}
            bankNav={bankNav}
            currentAssessmentState={currentAssessmentState}
          />
        </div>,
      )
      i += 2
      continue
    }
    nodes.push(
      <BlockView
        key={`${messageId}-${i}`}
        block={cur}
        compact={compact}
        onSelectScenario={onSelectScenario}
        selectedScenarioId={selectedScenarioId}
        bankNav={bankNav}
        currentAssessmentState={currentAssessmentState}
      />,
    )
    i += 1
  }
  return nodes
}

function analysisStepsFromTrace(trace: unknown): string[] {
  if (!trace || typeof trace !== 'object') return []
  const stepsRaw = (trace as { steps?: unknown }).steps
  if (!Array.isArray(stepsRaw)) return []
  const lines: string[] = []
  for (const step of stepsRaw) {
    if (!step || typeof step !== 'object') continue
    const s = step as Record<string, unknown>
    const kind = String(s.kind || 'step')
    const name = String(s.name || s.tool || '').trim()
    const status = String(s.status || '').trim()
    let line = name ? `${kind}: ${name}` : kind
    if (status) line = `${line} (${status})`
    lines.push(line.slice(0, 160))
    if (lines.length >= 20) break
  }
  return lines
}

/** Recover jury steps from message blocks or postMessage.analysis_steps. */
export function analysisStepsForMessage(
  message: AssistantMessage,
  fromApi?: string[] | null,
): string[] {
  if (Array.isArray(fromApi) && fromApi.length) {
    return fromApi.filter((s) => typeof s === 'string' && s.trim()).map((s) => s.trim())
  }
  for (const b of message.blocks ?? []) {
    if (!b || typeof b.data !== 'object' || !b.data) continue
    const data = b.data as Record<string, unknown>
    const diag =
      data.diagnostics && typeof data.diagnostics === 'object'
        ? (data.diagnostics as Record<string, unknown>)
        : null
    const trace = data.loop_trace || diag?.loop_trace
    const steps = analysisStepsFromTrace(trace)
    if (steps.length) return steps
  }
  return []
}

function MessageBubble({
  message,
  onSelectScenario,
  selectedScenarioId,
  compact = false,
  answerBasis = null,
  answerModel = null,
  bankNav,
  currentAssessmentState = null,
  analysisSteps = null,
}: {
  message: AssistantMessage
  onSelectScenario?: (scenarioId: string, solutionId?: string | null) => void
  selectedScenarioId?: string | null
  compact?: boolean
  answerBasis?: string | null
  answerModel?: string | null
  bankNav?: BankEvidenceNavContext
  currentAssessmentState?: string | null
  analysisSteps?: string[] | null
}) {
  const isUser = message.role === 'user'
  const isSystemCalc = message.role === 'system'
  const loopIncomplete = (message.blocks ?? []).some(
    (b) =>
      b.type === 'missing_data' &&
      Boolean(
        (b.data as { reason?: string; not_ai_final?: boolean } | undefined)?.reason ===
          'loop_incomplete' ||
          (b.data as { not_ai_final?: boolean } | undefined)?.not_ai_final,
      ),
  )
  const blocks = (message.blocks ?? []).filter((b) => {
    if (compact && PANEL_SKIP_BLOCKS.has(b.type)) return false
    // Incomplete system notice must not show bank citations or scenario actions.
    if (loopIncomplete && (b.type === 'bank_evidence_list' || b.type === 'scenario_comparison' || b.type === 'action_plan_draft')) {
      return false
    }
    return true
  })
  const hasExplainableText = !isUser && !isSystemCalc && Boolean(message.content?.trim())
  // Caption once per assistant turn; incomplete notices are not AI finals.
  // System calculation blocks are user-triggered — never label as AI.
  const showTextBasis = hasExplainableText && !loopIncomplete
  const steps = !isUser && !isSystemCalc && !loopIncomplete
    ? analysisStepsForMessage(message, analysisSteps)
    : []
  return (
    <article
      className={`assistant-msg assistant-msg-${message.role}${compact ? ' assistant-msg-compact' : ''}${loopIncomplete ? ' assistant-msg-incomplete' : ''}${isSystemCalc ? ' assistant-msg-system-calc' : ''}`}
      aria-label={
        isUser
          ? 'Вы'
          : isSystemCalc
            ? 'Системный расчёт'
            : loopIncomplete
              ? 'Системное уведомление'
              : 'Аспект'
      }
    >
      <div className="assistant-msg-rail">
        <div className="assistant-chat-inner assistant-msg-row">
          {!compact ? (
            <div className="assistant-msg-avatar" aria-hidden>
              {isUser ? 'Вы' : isSystemCalc ? 'Σ' : 'А'}
            </div>
          ) : null}
          <div className="assistant-msg-main">
            {isSystemCalc ? (
              <div className="assistant-system-calc-badge" role="status">
                Расчёт по вашему запросу · не ответ модели
              </div>
            ) : null}
            {showTextBasis ? (
              <ContentBasis basis={answerBasis} model={answerModel} />
            ) : null}
            {message.content && !isSystemCalc ? (
              <div className="assistant-msg-content">
                <SafeMarkdown text={sanitizeDisplayText(message.content)} />
              </div>
            ) : null}
            {message.content && isSystemCalc ? (
              <div className="assistant-msg-content assistant-msg-system-title">
                {sanitizeDisplayText(message.content)}
              </div>
            ) : null}
            {renderBlockGroups(
              message.id,
              blocks,
              compact,
              onSelectScenario,
              selectedScenarioId,
              bankNav,
              currentAssessmentState,
            )}
            {steps.length ? (
              <div className="assistant-block assistant-block-analysis-steps">
                <div className="assistant-block-title">Шаги анализа</div>
                <ul className="assistant-analysis-steps">
                  {steps.map((step, i) => (
                    <li key={`${message.id}-step-${i}`}>{step}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  )
}

function restoreStateFromMessages(msgs: AssistantMessage[]) {
  let hasScenarios = false
  let draftReady = false
  let confirmed = false
  let scenarioId: string | null = null
  let solutionId: string | null = null
  let decisionId: string | null = null

  for (const msg of msgs) {
    const incomplete = (msg.blocks ?? []).some(
      (b) =>
        b.type === 'missing_data' &&
        ((b.data as { reason?: string } | undefined)?.reason === 'loop_incomplete' ||
          (b.data as { not_ai_final?: boolean } | undefined)?.not_ai_final === true),
    )
    if (incomplete) continue
    for (const b of msg.blocks ?? []) {
      if (b.type === 'scenario_comparison') {
        hasScenarios = true
        const ids = (b.data.scenario_ids as string[]) ?? []
        const scenarios = (b.data.scenarios as Array<Record<string, unknown>>) ?? []
        if (!scenarioId) {
          const picked = pickDefaultScenarioId(scenarios, ids)
          if (picked.scenarioId) {
            scenarioId = picked.scenarioId
            solutionId = picked.solutionId
          }
        }
      }
      if (b.type === 'action_plan_draft') {
        const d = b.data as {
          status?: string
          scenario_id?: string
          solution_id?: string
          decision_id?: string | null
        }
        if (d.scenario_id) scenarioId = d.scenario_id
        if (d.solution_id) solutionId = d.solution_id
        if (d.status === 'confirmed' && d.decision_id) {
          confirmed = true
          draftReady = true
          decisionId = d.decision_id
        } else if (d.status === 'draft') {
          draftReady = true
        }
      }
    }
  }
  return { hasScenarios, draftReady, confirmed, scenarioId, solutionId, decisionId }
}

export function AssistantChat({
  eventId,
  companyId,
  variant = 'panel',
  expanded = false,
  onToggleExpand,
  onClose,
}: Props) {
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [chips, setChips] = useState<string[]>([])
  const [messages, setMessages] = useState<AssistantMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryText, setRetryText] = useState<string | null>(null)
  const lastClientIdRef = useRef<string | null>(null)
  const lastFailureCodeRef = useRef<string | null>(null)
  const [hasScenarios, setHasScenarios] = useState(false)
  const [draftReady, setDraftReady] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null)
  const [selectedSolutionId, setSelectedSolutionId] = useState<string | null>(null)
  const [decisionId, setDecisionId] = useState<string | null>(null)
  const [answerBasis, setAnswerBasis] = useState<string>('demo_explain')
  const [answerModel, setAnswerModel] = useState<string | null>(null)
  const [assessmentState, setAssessmentState] = useState<string | null>(null)
  const [hasImpactCalc, setHasImpactCalc] = useState(true)
  const [usedQuickActions, setUsedQuickActions] = useState<Set<string>>(() => new Set())
  const [calculating, setCalculating] = useState(false)
  const [whatIfRatePp, setWhatIfRatePp] = useState('')
  const [whatIfFxPercent, setWhatIfFxPercent] = useState('')
  const [calcNotice, setCalcNotice] = useState<string | null>(null)
  const [stepsByMessageId, setStepsByMessageId] = useState<Record<string, string[]>>({})
  const listRef = useRef<HTMLDivElement>(null)
  const sendingLock = useRef(false)
  const calculateLock = useRef(false)
  /** Last compare client_request_id — reused only on network retry of the same click. */
  const lastCompareRequestRef = useRef<{
    id: string
    ratePp: number | null
    fxPct: number | null
  } | null>(null)
  const inputId = useId()
  const calcActionsAllowed = canShowCalculationActions({
    has_impact_calculation: hasImpactCalc,
    assessment_state: assessmentState,
  })
  const isFinanceTrack =
    assessmentState === 'finance_ready' || assessmentState === 'finance_data_required'
  const isSupplyChainTrack = assessmentState === 'supply_chain_ready'
  const compact = variant === 'panel' && !expanded
  const showFinancePanel = showFinanceCalcCta({
    calcActionsAllowed,
    hasScenarios,
    compact,
    assessmentState,
  })
  const showFinanceRecalc = showFinanceRecalcCta({
    calcActionsAllowed,
    hasScenarios,
    compact,
    confirmed,
    assessmentState,
  })

  function applyRestored(msgs: AssistantMessage[], availableChips?: string[]) {
    const state = restoreStateFromMessages(msgs)
    setHasScenarios(state.hasScenarios)
    setDraftReady(state.draftReady)
    setConfirmed(state.confirmed)
    if (state.scenarioId) setSelectedScenarioId(state.scenarioId)
    if (state.solutionId) setSelectedSolutionId(state.solutionId)
    if (state.decisionId) setDecisionId(state.decisionId)

    const used = new Set<string>()
    const chipPool = availableChips ?? chips
    for (const msg of msgs) {
      if (msg.role !== 'user') continue
      const text = (msg.content || '').trim()
      if (!text) continue
      if (msg.client_message_id?.startsWith('quick:')) {
        used.add(msg.client_message_id)
        used.add(stableQuickId(text))
      }
      for (const chip of chipPool) {
        if (stableQuickId(chip) === stableQuickId(text) || chip.trim() === text) {
          used.add(stableQuickId(chip))
        }
      }
      if (isScenarioCalcChip(text)) {
        used.add(stableQuickId('Покажи три сценария'))
        used.add(stableQuickId('Покажи финансовые сценарии'))
        used.add(stableQuickId(FINANCE_CALC_CTA))
        used.add(stableQuickId(SUPPLY_COMPARE_CTA))
      }
    }
    if (state.hasScenarios) {
      used.add(stableQuickId('Покажи три сценария'))
      used.add(stableQuickId('Покажи финансовые сценарии'))
      used.add(stableQuickId(FINANCE_CALC_CTA))
      used.add(stableQuickId(SUPPLY_COMPARE_CTA))
    }
    setUsedQuickActions(used)
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      // Company / event switch: clear prior company answers before fetch.
      setLoading(true)
      setError(null)
      setUsedQuickActions(new Set())
      setConversationId(null)
      setMessages([])
      setChips([])
      setHasScenarios(false)
      setDraftReady(false)
      setConfirmed(false)
      setSelectedScenarioId(null)
      setSelectedSolutionId(null)
      setDecisionId(null)
      setAssessmentState(null)
      setHasImpactCalc(true)
      setInput('')
      setRetryText(null)
      setCalculating(false)
      setWhatIfRatePp('')
      setWhatIfFxPercent('')
      setCalcNotice(null)
      try {
        const conv = await assistantApi.openConversation(eventId, companyId)
        if (cancelled) return
        setConversationId(conv.id)
        const nextChips = conv.suggestion_chips ?? []
        setChips(nextChips)
        setAnswerBasis(conv.answer_basis ?? 'demo_explain')
        setAnswerModel(conv.answer_model ?? null)
        const state = conv.assessment_state ?? null
        setAssessmentState(state)
        setHasImpactCalc(
          typeof conv.has_impact_calculation === 'boolean'
            ? conv.has_impact_calculation
            : state !== 'calculation_unavailable',
        )
        const msgs = await assistantApi.messages(conv.id)
        if (cancelled) return
        setMessages(msgs)
        applyRestored(msgs, nextChips)
      } catch (e) {
        if (!cancelled) {
          if (e instanceof ApiError) {
            setError(assistantOpenErrorMessage(e))
          } else {
            setError(e instanceof Error ? e.message : 'Не удалось открыть чат')
          }
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [eventId, companyId])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages, sending])

  async function runUserCompare(opts?: { fromChip?: string; retry?: boolean }) {
    if (!conversationId) return
    if (calculateLock.current || calculating || sending) return
    if (opts?.fromChip && usedQuickActions.has(stableQuickId(opts.fromChip))) return

    const whatIf = validateWhatIfInputs(whatIfRatePp, whatIfFxPercent)
    if (!whatIf.ok) {
      setCalcNotice(whatIf.notice)
      return
    }

    calculateLock.current = true
    setCalculating(true)
    setError(null)
    setCalcNotice(null)

    const prev = lastCompareRequestRef.current
    const sameWhatIf =
      prev != null && prev.ratePp === whatIf.ratePp && prev.fxPct === whatIf.fxPct
    // Explicit new calc → new id. Network retry of the same click → reuse id.
    const clientRequestId =
      opts?.retry && sameWhatIf && prev
        ? prev.id
        : `cmp-${conversationId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    lastCompareRequestRef.current = {
      id: clientRequestId,
      ratePp: whatIf.ratePp,
      fxPct: whatIf.fxPct,
    }

    try {
      const res = await assistantApi.compareScenarios(
        conversationId,
        buildCompareRequestBody({
          clientRequestId,
          ratePp: whatIf.ratePp,
          fxPct: whatIf.fxPct,
        }),
      )
      setUsedQuickActions((prevUsed) => {
        const next = new Set(prevUsed)
        if (opts?.fromChip) next.add(stableQuickId(opts.fromChip))
        next.add(stableQuickId(FINANCE_CALC_CTA))
        next.add(stableQuickId(SUPPLY_COMPARE_CTA))
        next.add(stableQuickId('Покажи три сценария'))
        next.add(stableQuickId('Покажи финансовые сценарии'))
        return next
      })
      if (res.message) {
        setMessages((prevMsgs) => {
          const already = prevMsgs.some((m) => m.id === res.message!.id)
          const next = already ? prevMsgs : [...prevMsgs, res.message!]
          applyRestored(next)
          return next
        })
      } else if (res.reused) {
        const msgs = await assistantApi.messages(conversationId)
        setMessages(msgs)
        applyRestored(msgs)
      }
      const notice = unavailableNoticeFromResult(res)
      if (notice) setCalcNotice(notice)
      setRetryText(null)
    } catch (e) {
      const code = e instanceof ApiError ? e.code : null
      if (code === 'USER_COMPARE_REQUEST_CONFLICT') {
        setCalcNotice(
          'Этот запрос уже был с другими параметрами. Запустите новый расчёт с новым допущением.',
        )
        lastCompareRequestRef.current = null
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось выполнить расчёт')
        setRetryText('__compare_retry__')
      }
    } finally {
      calculateLock.current = false
      setCalculating(false)
    }
  }

  async function send(text: string, opts?: { quick?: boolean; retry?: boolean }) {
    const trimmed = text.trim()
    if (!conversationId || !trimmed) return
    // Scenario/finance calculation chips → dedicated API (not model message).
    if (isScenarioCalcChip(trimmed)) {
      await runUserCompare({ fromChip: trimmed })
      return
    }
    if (sendingLock.current || sending) return
    if (opts?.quick && usedQuickActions.has(stableQuickId(trimmed))) return

    sendingLock.current = true
    setSending(true)
    setError(null)
    setRetryText(null)
    const clientId = chooseClientMessageId({
      quick: opts?.quick,
      text: trimmed,
      previousId: lastClientIdRef.current,
      previousFailureCode: lastFailureCodeRef.current,
      isRetry: Boolean(opts?.retry),
      newId: () => `c-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      quickId: stableQuickId,
    })
    lastClientIdRef.current = clientId
    try {
      const res = await assistantApi.postMessage(conversationId, trimmed, clientId)
      lastFailureCodeRef.current = null
      if (opts?.quick) {
        setUsedQuickActions((prev) => new Set(prev).add(stableQuickId(trimmed)))
      }
      const apiSteps = Array.isArray(res.analysis_steps)
        ? res.analysis_steps.filter((s): s is string => typeof s === 'string' && Boolean(s.trim()))
        : []
      if (apiSteps.length && res.assistant_message?.id) {
        setStepsByMessageId((prev) => ({
          ...prev,
          [res.assistant_message.id]: apiSteps.map((s) => s.trim()),
        }))
      }
      // Always reconcile from server when reused — avoids duplicate bubbles after reload/double-click
      if (res.reused) {
        const msgs = await assistantApi.messages(conversationId)
        setMessages(msgs)
        applyRestored(msgs)
      } else {
        setMessages((prev) => {
          const already = prev.some(
            (m) => m.client_message_id && m.client_message_id === res.user_message.client_message_id,
          )
          if (already) {
            applyRestored(prev)
            return prev
          }
          const next = [...prev, res.user_message, res.assistant_message]
          applyRestored(next)
          return next
        })
      }
      setInput('')
    } catch (e) {
      const code = e instanceof ApiError ? e.code : null
      lastFailureCodeRef.current = code
      const msg = e instanceof Error ? e.message : 'Ошибка отправки'
      const providerDown =
        /провайдер временно недоступен|PROVIDER_UNAVAILABLE/i.test(msg) ||
        code === 'PROVIDER_UNAVAILABLE'
      setError(providerDown ? 'AI-провайдер временно недоступен' : msg)
      // Manual retry only — no automatic re-send after timeout / loop stops.
      setRetryText(trimmed)
      // After terminal failure, refresh history so incomplete system notice is visible.
      if (code?.startsWith('ASSISTANT_LOOP_') && conversationId) {
        try {
          const msgs = await assistantApi.messages(conversationId)
          setMessages(msgs)
          applyRestored(msgs)
        } catch {
          /* keep prior messages */
        }
      }
    } finally {
      sendingLock.current = false
      setSending(false)
    }
  }

  async function prepareDraft() {
    if (!conversationId || !selectedScenarioId || confirmed) return
    setSending(true)
    setError(null)
    try {
      const res = await assistantApi.draftDecision(conversationId, {
        scenario_id: selectedScenarioId,
        solution_id: selectedSolutionId,
        confirm: false,
        client_request_id: `draft-${selectedScenarioId}`,
      })
      if (res.message) {
        setMessages((prev) => {
          const next = [...prev, res.message!]
          applyRestored(next)
          return next
        })
      }
      setDraftReady(true)
      if (typeof res.draft.scenario_id === 'string') setSelectedScenarioId(res.draft.scenario_id)
    } catch (e) {
      if (e instanceof ApiError) {
        setError(draftDecisionErrorMessage(e))
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось подготовить черновик')
      }
    } finally {
      setSending(false)
    }
  }

  async function confirmDraft() {
    if (!conversationId || !selectedScenarioId || confirmed) return
    setSending(true)
    setError(null)
    try {
      const res = await assistantApi.draftDecision(conversationId, {
        scenario_id: selectedScenarioId,
        solution_id: selectedSolutionId,
        confirm: true,
        client_request_id: `confirm-${selectedScenarioId}`,
      })
      if (res.message) {
        setMessages((prev) => {
          const next = [...prev, res.message!]
          applyRestored(next)
          return next
        })
      }
      // Success UI only after server-confirmed status + decision id.
      if (res.status === 'confirmed' && res.decision_id) {
        setConfirmed(true)
        setDraftReady(true)
        setDecisionId(res.decision_id)
      } else {
        setError('Сервер не подтвердил сохранение решения')
      }
    } catch (e) {
      if (e instanceof ApiError) {
        setError(draftDecisionErrorMessage(e))
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось сохранить решение')
      }
    } finally {
      setSending(false)
    }
  }

  const chatTitle = !calcActionsAllowed
    ? compact
      ? 'Обсудить событие'
      : 'Обсуждение события'
    : compact
      ? 'Спросить про влияние'
      : 'Обсуждение влияния'
  const chatSub = !calcActionsAllowed
    ? 'Расчётная оценка пока недоступна — можно разобрать событие и данные компании.'
    : 'Слева уже оценка. Здесь — сценарии и план действий.'

  return (
    <section
      className={`assistant-chat assistant-chat-${variant}${expanded ? ' assistant-chat-expanded' : ''}${compact ? ' assistant-chat-compact' : ''}`}
      aria-label="Чат с Аспектом"
    >
      <header className="assistant-chat-header">
        <div className="assistant-chat-inner assistant-chat-header-row">
          <div>
            <div className="assistant-chat-kicker">Аспект</div>
            <h2>{chatTitle}</h2>
            {compact || !calcActionsAllowed ? (
              <p className="assistant-chat-sub">{chatSub}</p>
            ) : null}
          </div>
          <div className="assistant-chat-header-actions">
            {variant === 'panel' && onToggleExpand ? (
              <button type="button" className="btn btn-ghost" onClick={onToggleExpand}>
                {expanded ? 'Свернуть' : 'Шире'}
              </button>
            ) : null}
            {onClose ? (
              <button type="button" className="btn btn-ghost" onClick={onClose}>
                Закрыть
              </button>
            ) : null}
          </div>
        </div>
      </header>

      <div className="assistant-chat-body" ref={listRef}>
        {loading || error ? (
          <div className="assistant-chat-inner">
            {loading ? <div className="muted assistant-status">Открываю разговор…</div> : null}
            {error ? (
              <div className="form-error assistant-provider-error" role="alert">
                <span>{error}</span>
                {retryText && !sending && !calculating ? (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ marginLeft: 12 }}
                    onClick={() => {
                      if (retryText === '__compare_retry__') {
                        void runUserCompare({ retry: true })
                        return
                      }
                      void send(retryText, { retry: true })
                    }}
                  >
                    Повторить
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            message={m}
            compact={compact}
            answerBasis={answerBasis}
            answerModel={answerModel}
            selectedScenarioId={selectedScenarioId}
            currentAssessmentState={assessmentState}
            analysisSteps={stepsByMessageId[m.id] ?? null}
            bankNav={{
              conversationId,
              eventId,
              companyId,
            }}
            onSelectScenario={(sid, sol) => {
              setSelectedScenarioId(sid)
              setSelectedSolutionId(sol ?? null)
            }}
          />
        ))}
        {sending ? (
          <div className={`assistant-msg assistant-msg-assistant${compact ? ' assistant-msg-compact' : ''}`}>
            <div className="assistant-msg-rail">
              <div className="assistant-chat-inner assistant-msg-row">
                {!compact ? (
                  <div className="assistant-msg-avatar" aria-hidden>
                    А
                  </div>
                ) : null}
                <div className="assistant-msg-main">
                  <div className="muted assistant-status">Аспект думает…</div>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      <div className="assistant-chat-dock">
        <div className="assistant-chat-inner">
          {!hasScenarios && chips.length ? (
            <div className="assistant-chips" role="list">
              {chips.map((chip) => {
                const used = usedQuickActions.has(stableQuickId(chip))
                return (
                  <button
                    key={chip}
                    type="button"
                    className={`assistant-chip${used ? ' assistant-chip-used' : ''}`}
                    role="listitem"
                    disabled={sending || calculating || !conversationId || used}
                    aria-disabled={sending || calculating || !conversationId || used}
                    onClick={() => void send(chip, { quick: true })}
                  >
                    {used ? `✓ ${chip}` : chip}
                  </button>
                )
              })}
            </div>
          ) : null}

          <div className="assistant-decision-actions">
            {(showFinancePanel || showFinanceRecalc) && !compact ? (
              <div className="assistant-finance-calc-panel">
                <p className="muted assistant-finance-calc-hint">
                  {showFinanceRecalc
                    ? 'Изменить допущения и рассчитать другой вариант. Предыдущие результаты и решения в этой беседе сохраняются; hold и what-if различаются по основанию.'
                    : 'Без what-if используется проверенное основание события. Допущения не записываются в профиль компании.'}
                </p>
                <div className="assistant-what-if-row">
                  <label className="assistant-what-if-field">
                    <span>What-if ставка (п.п.)</span>
                    <input
                      type="text"
                      inputMode="decimal"
                      placeholder="напр. 1.5"
                      value={whatIfRatePp}
                      disabled={calculating || sending}
                      onChange={(e) => setWhatIfRatePp(e.target.value)}
                    />
                  </label>
                  <label className="assistant-what-if-field">
                    <span>What-if курс (%)</span>
                    <input
                      type="text"
                      inputMode="decimal"
                      placeholder="напр. 10"
                      value={whatIfFxPercent}
                      disabled={calculating || sending}
                      onChange={(e) => setWhatIfFxPercent(e.target.value)}
                    />
                  </label>
                </div>
                <button
                  type="button"
                  className="assistant-action assistant-action-primary"
                  disabled={calculating || sending || !conversationId}
                  onClick={() => void runUserCompare()}
                >
                  {calculating
                    ? 'Расчёт…'
                    : showFinanceRecalc
                      ? FINANCE_RECALC_CTA
                      : FINANCE_CALC_CTA}
                </button>
                {calcNotice ? <p className="muted assistant-calc-notice">{calcNotice}</p> : null}
                {assessmentState === 'finance_data_required' ? (
                  <Link
                    className="assistant-action"
                    to={financeSetupPath({ eventId, companyId })}
                  >
                    Открыть финансовые параметры
                  </Link>
                ) : null}
              </div>
            ) : null}
            {showSupplyCompareCta({
              calcActionsAllowed,
              hasScenarios,
              compact,
              assessmentState,
            }) ? (
              <button
                type="button"
                className="assistant-action"
                disabled={
                  calculating ||
                  sending ||
                  !conversationId ||
                  usedQuickActions.has(stableQuickId(SUPPLY_COMPARE_CTA))
                }
                onClick={() => void runUserCompare({ fromChip: SUPPLY_COMPARE_CTA })}
              >
                {calculating ? 'Расчёт…' : SUPPLY_COMPARE_CTA}
              </button>
            ) : null}
            {calcActionsAllowed &&
            !hasScenarios &&
            !compact &&
            !isFinanceTrack &&
            !isSupplyChainTrack ? (
              <p className="muted assistant-calc-notice">
                Численное сравнение сценариев доступно после usable impact (finance или
                supply-chain). Обсуждение события по-прежнему открыто.
              </p>
            ) : null}
            {calcActionsAllowed && hasScenarios && !confirmed ? (
              <button
                type="button"
                className="assistant-action"
                disabled={sending || !conversationId || !selectedScenarioId}
                onClick={() => void prepareDraft()}
              >
                Черновик решения
              </button>
            ) : null}
            {calcActionsAllowed && !confirmed && draftReady ? (
              <button
                type="button"
                className="assistant-action assistant-action-primary"
                disabled={sending || !conversationId || !selectedScenarioId}
                onClick={() => void confirmDraft()}
              >
                Подтвердить
              </button>
            ) : null}
            {confirmed ? (
              <>
                <span className="assistant-decision-saved">Решение сохранено</span>
                {decisionId ? (
                  <Link className="assistant-action assistant-action-primary" to={`/decisions/${decisionId}`}>
                    План действий
                  </Link>
                ) : null}
              </>
            ) : null}
          </div>

          <form
            className="assistant-composer"
            onSubmit={(e) => {
              e.preventDefault()
              void send(input)
            }}
          >
            <span className="assistant-composer-attach" aria-hidden title="Вложение">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M15.5 7.5l-6.8 6.8a2.5 2.5 0 003.5 3.5l7.6-7.6a4 4 0 00-5.7-5.7L6.3 12.3a5.5 5.5 0 007.8 7.8l6.1-6.1"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <label className="sr-only" htmlFor={inputId}>
              Сообщение
            </label>
            <input
              id={inputId}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                calcActionsAllowed
                  ? 'Спросите про влияние или сценарии'
                  : 'Спросите, что проверить или каких данных не хватает'
              }
              disabled={sending || !conversationId}
              autoComplete="off"
            />
            <button
              type="submit"
              className="assistant-send"
              disabled={sending || !input.trim()}
              aria-label="Отправить"
            >
              ↑
            </button>
          </form>
        </div>
      </div>
    </section>
  )
}
