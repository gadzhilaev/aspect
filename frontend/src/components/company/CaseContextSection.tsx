import type { CaseContext, CaseProfile, CompanyContext } from '../../api/types'
import {
  CASE_STATUS_USER_COPY,
  FTS_TRADE_DIRECTION_NOTE,
  REVENUE_UNITS_UNKNOWN_NOTE,
  bankingProductsForDisplay,
  caseStatusUserCopy,
  fieldDisplay,
  industryCaseState,
  industryFromCase,
  manualVsCaseHints,
  provenanceLines,
} from '../../lib/caseContextDisplay'

function FactRow({
  label,
  value,
  tone = 'default',
}: {
  label: string
  value: string
  tone?: 'default' | 'muted' | 'warn'
}) {
  return (
    <div className={`company-case-fact company-case-fact-${tone}`}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function ProfileFacts({
  data,
  profile,
}: {
  data: CompanyContext
  profile: CaseProfile
}) {
  const industryState = industryCaseState(profile)
  const industryText =
    industryState === 'conflict'
      ? 'Данные расходятся'
      : industryFromCase(profile) ?? 'Нет сведений'
  const region = fieldDisplay(profile.region)
  const city = fieldDisplay(profile.city)
  const workersFns = fieldDisplay(profile.workers_fns)
  const workersSpark = fieldDisplay(profile.workers_spark)
  const age = fieldDisplay(profile.company_age)
  const products = bankingProductsForDisplay(profile)
  const fts = profile.fts_geography
  const group = profile.group
  const hints = manualVsCaseHints(data, profile)

  let ftsValue = 'Нет сведений'
  let ftsTone: 'default' | 'muted' | 'warn' = 'muted'
  if (fts.status === 'conflict') {
    ftsValue = 'Данные расходятся'
    ftsTone = 'warn'
  } else if (fts.status === 'confirmed' && (fts.countries_raw?.length ?? 0) > 0) {
    ftsValue = fts.countries_raw!.join(', ')
    ftsTone = 'default'
  }

  let groupValue = 'Нет сведений'
  let groupTone: 'default' | 'muted' | 'warn' = 'muted'
  if (group.status === 'conflict' || group.is_conflicted) {
    groupValue = 'Данные расходятся'
    groupTone = 'warn'
  } else if (group.status === 'confirmed' && group.external_group_id) {
    groupValue = group.external_group_id
    groupTone = 'default'
  }

  return (
    <>
      {hints.length ? (
        <div className="company-case-diff" role="note">
          <p className="company-case-diff-title">Профиль и источник различаются</p>
          <ul>
            {hints.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
          <p className="company-case-diff-note">
            Ни одно значение не выбрано автоматически как единственно верное.
          </p>
        </div>
      ) : null}

      <dl className="company-case-grid">
        <FactRow
          label="Отрасль и ОКВЭД"
          value={industryText}
          tone={industryState === 'value' ? 'default' : industryState === 'conflict' ? 'warn' : 'muted'}
        />
        <FactRow
          label="Регион регистрации"
          value={region.text}
          tone={region.kind === 'value' ? 'default' : region.kind === 'conflict' ? 'warn' : 'muted'}
        />
        <FactRow
          label="Город регистрации"
          value={city.text}
          tone={city.kind === 'value' ? 'default' : city.kind === 'conflict' ? 'warn' : 'muted'}
        />
        <FactRow
          label="Численность (ФНС)"
          value={workersFns.text}
          tone={
            workersFns.kind === 'value' ? 'default' : workersFns.kind === 'conflict' ? 'warn' : 'muted'
          }
        />
        <FactRow
          label="Численность (Spark)"
          value={workersSpark.text}
          tone={
            workersSpark.kind === 'value'
              ? 'default'
              : workersSpark.kind === 'conflict'
                ? 'warn'
                : 'muted'
          }
        />
        <FactRow
          label="Возраст компании"
          value={age.text}
          tone={age.kind === 'value' ? 'default' : age.kind === 'conflict' ? 'warn' : 'muted'}
        />
      </dl>

      <div className="company-case-block">
        <h3>Банковские продукты</h3>
        <p className="company-case-block-note">
          Отметка в источнике не означает известную сумму, ставку или условия договора.
        </p>
        <ul className="company-case-products">
          {products.map((p) => (
            <li key={p.key} className={`company-case-product company-case-product-${p.status}`}>
              <span className="company-case-product-name">{p.label}</span>
              <span className="company-case-product-status">{p.statusLabel}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="company-case-block">
        <h3>География по данным ФТС</h3>
        <p className="company-case-block-note">{FTS_TRADE_DIRECTION_NOTE}</p>
        <p className={`company-case-fts company-case-fts-${ftsTone}`}>{ftsValue}</p>
      </div>

      {group.status === 'confirmed' && group.external_group_id && !group.is_conflicted ? (
        <div className="company-case-block">
          <h3>Группа компаний</h3>
          <p className={`company-case-fts company-case-fts-${groupTone}`}>{groupValue}</p>
          <p className="company-case-block-note">Показан только идентификатор группы из источника.</p>
        </div>
      ) : group.status === 'conflict' || group.is_conflicted ? (
        <div className="company-case-block">
          <h3>Группа компаний</h3>
          <p className="company-case-fts company-case-fts-warn">Данные расходятся</p>
        </div>
      ) : null}

      <div className="company-case-block">
        <h3>Выручка</h3>
        <p className="company-case-block-note">{REVENUE_UNITS_UNKNOWN_NOTE}</p>
      </div>

      <details className="company-case-provenance">
        <summary>Откуда данные</summary>
        <ul>
          {provenanceLines(profile).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </details>
    </>
  )
}

export function CaseContextSection({ data }: { data: CompanyContext }) {
  const caseContext: CaseContext | null | undefined = data.case_context

  if (!caseContext) {
    return null
  }

  const status = caseContext.status
  const showProfile = status === 'profile_available' && caseContext.profile

  return (
    <section className="company-section company-section-case" aria-labelledby="company-case-title">
      <div className="container company-shell">
        <div className="company-section-head">
          <div>
            <p className="company-section-kicker">Внешний источник</p>
            <h2 id="company-case-title">Данные компании из источника</h2>
          </div>
          <p className="company-section-lead">
            {status === 'profile_available'
              ? caseStatusUserCopy(status)
              : 'Сведения из внешнего справочника показываются отдельно от вашего профиля.'}
          </p>
        </div>

        {status !== 'profile_available' ? (
          <div className="company-case-status" role="status">
            <p>{CASE_STATUS_USER_COPY[status]}</p>
          </div>
        ) : null}

        {showProfile && caseContext.profile ? (
          <ProfileFacts data={data} profile={caseContext.profile} />
        ) : null}
      </div>
    </section>
  )
}
