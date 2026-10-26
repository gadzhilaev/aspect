import type { ReactNode } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { companyApi } from '../api/endpoints'
import { IndustryProfileForm } from '../components/company/IndustryProfileForm'
import type { CaseContext, CompanyProfile } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { StateBlock } from '../components/ui/StateBlock'
import { useAsync } from '../hooks/useAsync'
import {
  COMPANY_SECTION_META,
  buildFinanceView,
  componentNames,
  confirmedEdges,
  edgeLabel,
  facilityNames,
  geographyPlaces,
  marketNames,
  membershipRoleLabel,
  productNames,
  productionLineNames,
  setupHref,
  supplierNames,
  type CompanySectionId,
} from '../lib/companyHub'
import { provenanceFromSettings, provenanceSummary } from '../lib/companyRegistry'

const SECTION_IDS = new Set<string>(Object.keys(COMPANY_SECTION_META))

type Payload = {
  profile: CompanyProfile
  caseContext: CaseContext | null
}

function SectionShell({
  title,
  children,
  editHref,
  editLabel = 'Добавить или изменить',
}: {
  title: string
  children: ReactNode
  editHref: string | null
  editLabel?: string
}) {
  return (
    <div className="company-page">
      <section className="company-hub-shell company-section-page">
        <div className="container">
          <Link className="company-section-back" to="/company">
            ← К компании
          </Link>
          <div className="company-section-page-head">
            <h1>{title}</h1>
            {editHref ? (
              <Link className="btn btn-primary" to={editHref}>
                {editLabel}
              </Link>
            ) : null}
          </div>
          {children}
        </div>
      </section>
    </div>
  )
}

function EmptyBlock({ href, label }: { href: string; label: string }) {
  return (
    <div className="company-section-empty" data-testid="company-section-empty">
      <p>Не заполнено</p>
      <Link className="btn btn-primary" to={href}>
        {label}
      </Link>
    </div>
  )
}

function ListCard({
  title,
  items,
  note,
}: {
  title: string
  items: string[]
  note?: string
}) {
  if (!items.length) return null
  return (
    <article className="company-section-card">
      <h2>{title}</h2>
      {note ? <p className="company-section-note">{note}</p> : null}
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </article>
  )
}

function ProductsBody({ profile }: { profile: CompanyProfile }) {
  const products = productNames(profile.nodes)
  const components = componentNames(profile.nodes)
  const lines = productionLineNames(profile.nodes)
  const href = setupHref('chain')
  if (!products.length && !components.length && !lines.length) {
    return <EmptyBlock href={href} label="Добавить продукцию" />
  }
  return (
    <div className="company-section-stack">
      <ListCard
        title="Продукция"
        items={products}
        note="Только продукция компании. Коды ТН ВЭД сюда не подставляются."
      />
      <ListCard
        title="Компоненты и производство"
        items={[
          ...components.map((c) => `Компонент: ${c}`),
          ...lines.map((l) => `Линия: ${l}`),
        ]}
        note="Отдельно от списка продуктов."
      />
      {!products.length && (components.length || lines.length) ? (
        <p className="company-section-note">
          Продукция ещё не указана — есть только компоненты или линии.
        </p>
      ) : null}
      <Link className="btn btn-secondary" to={href}>
        Изменить в мастере
      </Link>
    </div>
  )
}

function MarketsBody({ profile }: { profile: CompanyProfile }) {
  const markets = marketNames(profile.nodes)
  const href = setupHref('geo')
  if (!markets.length) {
    return <EmptyBlock href={href} label="Указать рынки сбыта" />
  }
  return (
    <div className="company-section-stack">
      <ListCard
        title="Рынки сбыта"
        items={markets}
        note="Не смешиваются со странами поставщиков."
      />
      <Link className="btn btn-secondary" to={href}>
        Изменить в мастере
      </Link>
    </div>
  )
}

function GeographyBody({ profile }: { profile: CompanyProfile }) {
  const geo = geographyPlaces(profile.company, profile.nodes)
  const facilities = facilityNames(profile.nodes)
  const href = setupHref('geo')
  const hasAny = Boolean(geo.hq || geo.facilities.length || geo.other.length || facilities.length)
  if (!hasAny) {
    return <EmptyBlock href={href} label="Указать географию" />
  }
  return (
    <div className="company-section-stack">
      {geo.hq ? (
        <article className="company-section-card">
          <h2>Регистрация / штаб-квартира</h2>
          <p>{geo.hq}</p>
        </article>
      ) : null}
      <ListCard title="Производственные площадки" items={geo.facilities.length ? geo.facilities : facilities} />
      <ListCard
        title="Другие географические сведения"
        items={geo.other}
        note="Страны и регионы узлов профиля, кроме рынков сбыта."
      />
      <Link className="btn btn-secondary" to={href}>
        Изменить в мастере
      </Link>
    </div>
  )
}

function MeBody({
  profile,
  userEmail,
  displayName,
  membershipRole,
}: {
  profile: CompanyProfile
  userEmail: string
  displayName: string
  membershipRole: string | null
}) {
  const roleFromProduct = profile.nodes
    .filter((n) => n.node_type === 'product')
    .map((n) => {
      const v = n.attributes_json?.business_role
      return typeof v === 'string' ? v.trim() : ''
    })
    .find(Boolean)

  const accessLabel = membershipRoleLabel(membershipRole)

  return (
    <div className="company-section-stack">
      <article className="company-section-card">
        <h2>Пользователь</h2>
        <dl className="company-section-dl">
          <div>
            <dt>Имя</dt>
            <dd>{displayName || '—'}</dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd>{userEmail || '—'}</dd>
          </div>
        </dl>
      </article>
      <article className="company-section-card">
        <h2>Бизнес-роль</h2>
        <p>{roleFromProduct || 'Не указана'}</p>
        <p className="company-section-note">
          Бизнес-роль задаётся в профиле компании и не равна правам доступа.
        </p>
        <Link className="btn btn-secondary" to={setupHref('role')}>
          Изменить роль в мастере
        </Link>
      </article>
      <article className="company-section-card">
        <h2>Доступ к компании</h2>
        <p>{accessLabel || 'Не указан'}</p>
        <Link className="btn btn-secondary" to="/settings">Настройки аккаунта и пароль</Link>
      </article>
    </div>
  )
}

function FinanceBody({
  profile,
  caseContext,
}: {
  profile: CompanyProfile
  caseContext: CaseContext | null
}) {
  const view = buildFinanceView(profile.settings, caseContext)
  const href = setupHref('finance')
  if (!view.hasAny) {
    return <EmptyBlock href={href} label="Заполнить финансы" />
  }
  return (
    <div className="company-section-stack">
      {view.bankProducts.length ? (
        <article className="company-section-card">
          <h2>Банковские продукты (источник)</h2>
          {view.bankSourceNote ? (
            <p className="company-section-note">{view.bankSourceNote}</p>
          ) : null}
          <ul className="company-finance-marks">
            {view.bankProducts.map((p) => (
              <li key={p.key}>
                <span>{p.label}</span>
                <strong data-status={p.status}>{p.statusLabel}</strong>
              </li>
            ))}
          </ul>
        </article>
      ) : view.bankSourceNote ? (
        <article className="company-section-card">
          <h2>Банковские продукты</h2>
          <p className="company-section-note">{view.bankSourceNote}</p>
        </article>
      ) : null}

      {view.manual.length ? (
        <article className="company-section-card">
          <h2>Ручные параметры</h2>
          <p className="company-section-note">
            Кредит и валютная операция из вашего ввода. Известный ноль показывается как 0, а не
            «неизвестно».
          </p>
          <dl className="company-section-dl">
            {view.manual.map((row) => (
              <div key={row.label}>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        </article>
      ) : null}

      <Link className="btn btn-primary" to={href}>
        Изменить финансы
      </Link>
    </div>
  )
}

function CounterpartiesBody({ profile }: { profile: CompanyProfile }) {
  const suppliers = supplierNames(profile.nodes)
  const edges = confirmedEdges(profile.edges)
  const byId = new Map(profile.nodes.map((n) => [n.id, n]))
  const href = setupHref('chain')
  const provenance = provenanceFromSettings(profile.settings)
  const prov = provenance ? provenanceSummary(provenance) : null

  if (!suppliers.length && !edges.length) {
    return <EmptyBlock href={href} label="Добавить контрагентов" />
  }

  return (
    <div className="company-section-stack">
      <ListCard
        title="Поставщики (профиль)"
        items={suppliers}
        note="Ручной профиль компании. Платёжные связи источника сюда не подставляются как поставка."
      />
      {edges.length ? (
        <article className="company-section-card">
          <h2>Подтверждённые связи</h2>
          <ul>
            {edges.map((e) => (
              <li key={e.id}>{edgeLabel(e, byId)}</li>
            ))}
          </ul>
        </article>
      ) : null}
      {prov?.registryFields.length ? (
        <p className="company-section-note">
          Реквизиты из реестра: {prov.registryFields.join(', ')}. Это не список конкурсных
          контрагентов — такого перечня API не отдаёт.
        </p>
      ) : (
        <p className="company-section-note">
          Полный список конкурсных контрагентов API не предоставляет — показаны только доступные
          поставщики и связи профиля.
        </p>
      )}
      <Link className="btn btn-secondary" to={href}>
        Изменить цепочку
      </Link>
    </div>
  )
}

export function CompanySectionPage() {
  const { sectionId } = useParams<{ sectionId: string }>()
  const { user, companyId, loading: authLoading } = useAuth()

  const { data, error, loading, reload } = useAsync(async (): Promise<Payload | null> => {
    if (!companyId) return null
    const profile = await companyApi.profile(companyId)
    let caseContext: CaseContext | null = null
    try {
      const ctx = await companyApi.context(companyId)
      caseContext = ctx.case_context ?? null
    } catch {
      caseContext = null
    }
    return { profile, caseContext }
  }, [companyId])

  if (!sectionId || !SECTION_IDS.has(sectionId)) {
    return <Navigate to="/company" replace />
  }
  const section = sectionId as CompanySectionId
  const meta = COMPANY_SECTION_META[section]

  if (authLoading) {
    return (
      <div className="container page-pad">
        <StateBlock variant="loading" title="Загружаем профиль" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (!companyId) {
    return (
      <SectionShell title={meta.title} editHref="/company/setup">
        <EmptyBlock href="/company/setup" label="Создать компанию" />
      </SectionShell>
    )
  }

  if (loading) {
    return (
      <div className="container page-pad">
        <StateBlock variant="loading" title={`Загружаем: ${meta.title}`} />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="container page-pad">
        <StateBlock
          variant="error"
          title="Не удалось загрузить раздел"
          description={error?.message || 'Попробуйте ещё раз.'}
          onRetry={reload}
        />
      </div>
    )
  }

  const membershipRole =
    user.companies.find((c) => c.company_id === companyId)?.role ?? null

  let body: ReactNode = null
  if (section === 'products') body = <ProductsBody profile={data.profile} />
  else if (section === 'markets') body = <MarketsBody profile={data.profile} />
  else if (section === 'geography') body = <GeographyBody profile={data.profile} />
  else if (section === 'me') {
    body = (
      <MeBody
        profile={data.profile}
        userEmail={user.email}
        displayName={user.display_name}
        membershipRole={membershipRole}
      />
    )
  } else if (section === 'finance') {
    body = <FinanceBody profile={data.profile} caseContext={data.caseContext} />
  } else if (section === 'counterparties') {
    body = <CounterpartiesBody profile={data.profile} />
  }

  return (
    <SectionShell
      title={meta.title}
      editHref={section === 'me' ? null : meta.setupStep ? setupHref(meta.setupStep) : null}
      editLabel="Редактировать"
    >
      {body}
      {section === 'products' ? <IndustryProfileForm key={companyId} companyId={companyId} /> : null}
    </SectionShell>
  )
}
