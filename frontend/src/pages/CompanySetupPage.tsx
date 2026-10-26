import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { authApi, companyApi, eventsApi } from '../api/endpoints'
import { discussPath } from '../lib/assistantWithoutImpact'
import type {
  CompanyEdge,
  CompanyNode,
  CompanyProfile,
  DigitalTwinBuildResult,
  Industry,
  NodeCreateIn,
  RegistryCandidate,
  RegistryLookupResult,
} from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { StateBlock } from '../components/ui/StateBlock'
import { industryLabel, nodeTypeLabel } from '../lib/format'
import {
  candidateRequisites,
  candidateTitle,
  checkInn,
  innCheckMessage,
  isCandidateInactive,
  orgTypeLabel,
  registryErrorMessage,
} from '../lib/companyRegistry'
import {
  buildFinancePatch,
  fieldErrorMap,
  financeSliceFromOptional,
  fxTrackMissing,
  fxTrackReady,
  quoteConventionLabel,
  rateTrackMissing,
  rateTrackReady,
  type FinanceFormSlice,
  type FxDirection,
} from '../lib/financeSetup'

const STEPS = [
  { id: 'basics', title: 'Данные компании', lead: 'Название, ИНН, регион и размер.' },
  { id: 'role', title: 'Роль и отрасль', lead: 'Кто вы в компании и что производите.' },
  { id: 'geo', title: 'География', lead: 'Откуда идут поставки и куда продаёте.' },
  {
    id: 'chain',
    title: 'Цепочка поставки',
    lead: 'Поставщик → компонент → линия → продукт → рынок.',
  },
  {
    id: 'finance',
    title: 'Финансы',
    lead: 'Необязательно: кредиты и/или одна валютная операция — независимо.',
  },
  { id: 'review', title: 'Проверка', lead: 'Сохраните профиль и соберите модель влияния.' },
] as const

type StepId = (typeof STEPS)[number]['id']

const SIZE_OPTIONS = [
  { id: 'small', label: 'Малый' },
  { id: 'medium', label: 'Средний' },
  { id: 'large', label: 'Крупный' },
  { id: 'enterprise', label: 'Холдинг' },
]

/** Explicit unknown markers — must not become confirmed twin node names. */
function isUnconfirmedNodeName(name: string): boolean {
  const n = name.trim().toLowerCase().replace(/\s+/g, ' ')
  if (!n) return true
  const exact = new Set([
    'не знаю',
    'неизвестно',
    'не известно',
    'нет данных',
    'нет информации',
    'без данных',
    'unknown',
    'n/a',
    'na',
    'none',
    'null',
    '?',
    '-',
    '—',
    '–',
  ])
  if (exact.has(n)) return true
  return n.startsWith('не знаю') || n.startsWith('unknown')
}

const REQUIRED_TYPES = [
  'product',
  'supplier',
  'component',
  'facility',
  'production_line',
  'market',
] as const

type NodeType = (typeof REQUIRED_TYPES)[number]

type FormState = {
  name: string
  taxId: string
  hqRegion: string
  sizeBand: string
  role: string
  industry: string
  productName: string
  supplyCountries: string
  marketCountries: string
  supplierName: string
  componentName: string
  facilityName: string
  lineName: string
  marketName: string
  lineShare: string
  debtAmount: string
  debtCurrency: string
  floatingRateShare: string
  nearTermPayments: string
  fxPurchaseVolume: string
  cashReserveDays: string
  purchaseCurrencies: string
  fxDirection: FxDirection
  fxExposureAmount: string
  fxExposureCurrency: string
  fxQuoteCurrency: string
  fxExposurePeriod: string
  fxRateFrom: string
  legacyFxPurchaseVolume: string | null
}

const EMPTY_FORM: FormState = {
  name: '',
  taxId: '',
  hqRegion: '',
  sizeBand: 'medium',
  role: '',
  industry: '',
  productName: '',
  supplyCountries: '',
  marketCountries: '',
  supplierName: '',
  componentName: '',
  facilityName: '',
  lineName: '',
  marketName: '',
  // Empty until the user enters a known share — never default a confirmed %.
  lineShare: '',
  debtAmount: '',
  debtCurrency: '',
  floatingRateShare: '',
  nearTermPayments: '',
  fxPurchaseVolume: '',
  cashReserveDays: '',
  purchaseCurrencies: '',
  fxDirection: '',
  fxExposureAmount: '',
  fxExposureCurrency: '',
  fxQuoteCurrency: '',
  fxExposurePeriod: '',
  fxRateFrom: '',
  legacyFxPurchaseVolume: null,
}

function firstNode(nodes: CompanyNode[], type: string): CompanyNode | undefined {
  return nodes.find((n) => n.node_type === type)
}

function firstCountry(value: string): string | null {
  const part = value
    .split(/[,;]/)
    .map((s) => s.trim())
    .find(Boolean)
  return part || null
}

function formFromProfile(profile: CompanyProfile): FormState {
  const { company, nodes, settings } = profile
  const product = firstNode(nodes, 'product')
  const supplier = firstNode(nodes, 'supplier')
  const component = firstNode(nodes, 'component')
  const facility = firstNode(nodes, 'facility')
  const line = firstNode(nodes, 'production_line')
  const market = firstNode(nodes, 'market')
  const roleAttr = product?.attributes_json?.business_role
  const fin =
    settings && typeof settings.optional_finance === 'object' && settings.optional_finance
      ? (settings.optional_finance as Record<string, unknown>)
      : {}
  const currencies = Array.isArray(settings?.purchase_currencies)
    ? (settings.purchase_currencies as string[])
    : []
  const finance = financeSliceFromOptional(fin, currencies)
  return {
    name: company.name ?? '',
    taxId: company.tax_id ?? '',
    hqRegion: company.hq_region ?? '',
    sizeBand: company.size_band ?? 'medium',
    role: typeof roleAttr === 'string' ? roleAttr : '',
    industry: company.industry ?? '',
    productName: product?.name ?? '',
    supplyCountries: supplier?.country ?? '',
    marketCountries: market?.country ?? market?.name ?? '',
    supplierName: supplier?.name ?? '',
    componentName: component?.name ?? '',
    facilityName: facility?.name ?? '',
    lineName: line?.name ?? '',
    marketName: market?.name ?? '',
    lineShare:
      line?.output_share_percent != null ? String(line.output_share_percent) : '',
    ...finance,
  }
}

function nodeIdsFromProfile(nodes: CompanyNode[]): Partial<Record<NodeType, string>> {
  const ids: Partial<Record<NodeType, string>> = {}
  for (const type of REQUIRED_TYPES) {
    const n = firstNode(nodes, type)
    if (n) ids[type] = n.id
  }
  return ids
}

export function CompanySetupPage() {
  const { companyId, setCompanyId, refreshUser } = useAuth()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [nodeIds, setNodeIds] = useState<Partial<Record<NodeType, string>>>({})
  const [edges, setEdges] = useState<CompanyEdge[]>([])
  const [industries, setIndustries] = useState<Industry[]>([])
  const [activeCompanyId, setActiveCompanyId] = useState<string | null>(companyId)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [warnings, setWarnings] = useState<string[]>([])
  const [completeness, setCompleteness] = useState<CompanyProfile['completeness'] | null>(null)
  const [buildResult, setBuildResult] = useState<DigitalTwinBuildResult | null>(null)
  const [finished, setFinished] = useState(false)
  /** Profile PATCH ok, but POST recompute-impact failed — retry without re-saving. */
  const [recomputePending, setRecomputePending] = useState<{
    companyId: string
    eventId: string
  } | null>(null)
  const [recomputation, setRecomputation] = useState(false)
  const fxPairRef = useRef<string>('')

  // --- External registry lookup (public requisites by INN) ---
  const [lookupState, setLookupState] = useState<'idle' | 'loading' | 'done'>('idle')
  const [lookupResult, setLookupResult] = useState<RegistryLookupResult | null>(null)
  const [lookupError, setLookupError] = useState<string | null>(null)
  const [innError, setInnError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [suggestedIndustry, setSuggestedIndustry] = useState<string | null>(null)
  const [registrySourceNote, setRegistrySourceNote] = useState<string | null>(null)
  // Monotonic guard: ignore responses from superseded lookups (fast retyping).
  const lookupSeq = useRef(0)

  function resetLookupResult() {
    setLookupResult(null)
    setLookupError(null)
    setInnError(null)
    setLookupState('idle')
  }

  async function runLookup() {
    setInnError(null)
    setLookupError(null)
    const check = checkInn(form.taxId)
    if (!check.ok) {
      setInnError(innCheckMessage(check))
      setLookupResult(null)
      setLookupState('idle')
      return
    }
    const seq = (lookupSeq.current += 1)
    setLookupState('loading')
    setLookupResult(null)
    try {
      const res = await companyApi.registryLookup(check.inn)
      if (seq !== lookupSeq.current) return
      setLookupResult(res)
      setLookupState('done')
    } catch (err) {
      if (seq !== lookupSeq.current) return
      const code = err instanceof ApiError ? err.code : undefined
      const msg = err instanceof ApiError ? err.message : undefined
      setLookupError(registryErrorMessage(code, msg))
      setLookupResult(null)
      setLookupState('done')
    }
  }

  async function applyCandidate(cand: RegistryCandidate) {
    if (!lookupResult?.lookup_id) return
    setConfirming(cand.candidate_id)
    setLookupError(null)
    try {
      const res = await companyApi.registryConfirm(lookupResult.lookup_id, cand.candidate_id)
      setActiveCompanyId(res.company.id)
      setCompanyId(res.company.id)
      await refreshUser()
      // Reload the profile so saved requisites + provenance are reflected 1:1.
      const profile = await companyApi.profile(res.company.id)
      const next = formFromProfile(profile)
      setForm(next)
      fxPairRef.current = `${next.fxExposureCurrency}|${next.fxQuoteCurrency}`
      setNodeIds(nodeIdsFromProfile(profile.nodes))
      setEdges(profile.edges)
      setWarnings(profile.warnings)
      setCompleteness(profile.completeness)
      setSuggestedIndustry(res.suggested_industry)
      setRegistrySourceNote(res.source?.note ?? null)
      resetLookupResult()
      setStatus(
        res.opened_existing
          ? 'У вас уже был профиль с этим ИНН — открыт существующий, дубликат не создан.'
          : res.note,
      )
    } catch (err) {
      const code = err instanceof ApiError ? err.code : undefined
      const msg = err instanceof ApiError ? err.message : undefined
      setLookupError(registryErrorMessage(code, msg))
    } finally {
      setConfirming(null)
    }
  }

  useEffect(() => {
    const stepParam = searchParams.get('step')
    if (stepParam) {
      const idx = STEPS.findIndex((s) => s.id === stepParam)
      if (idx >= 0) setStep(idx)
    }
  }, [searchParams])

  useEffect(() => {
    let cancelled = false
    async function boot() {
      setLoading(true)
      setError(null)
      setFieldErrors({})
      setStatus(null)
      setFinished(false)
      setBuildResult(null)
      try {
        const inds = await companyApi.industries()
        if (!cancelled) setIndustries(inds)
        if (companyId) {
          const profile = await companyApi.profile(companyId)
          if (cancelled) return
          setActiveCompanyId(companyId)
          const next = formFromProfile(profile)
          setForm(next)
          fxPairRef.current = `${next.fxExposureCurrency}|${next.fxQuoteCurrency}`
          setNodeIds(nodeIdsFromProfile(profile.nodes))
          setEdges(profile.edges)
          setWarnings(profile.warnings)
          setCompleteness(profile.completeness)
        } else {
          setActiveCompanyId(null)
          setForm(EMPTY_FORM)
          setNodeIds({})
          setEdges([])
          fxPairRef.current = ''
        }
      } catch (err) {
        if (!cancelled) {
          setForm(EMPTY_FORM)
          setError(err instanceof ApiError ? err.message : 'Не удалось загрузить мастер')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void boot()
    return () => {
      cancelled = true
    }
  }, [companyId])

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => {
      const next = { ...prev, [key]: value }
      if (key === 'fxExposureCurrency' || key === 'fxQuoteCurrency') {
        const pair = `${next.fxExposureCurrency}|${next.fxQuoteCurrency}`
        if (fxPairRef.current && fxPairRef.current !== pair && next.fxRateFrom) {
          next.fxRateFrom = ''
        }
        fxPairRef.current = pair
      }
      return next
    })
  }

  function clearFinanceField(key: keyof FormState) {
    if (key === 'fxDirection') update('fxDirection', '' as FxDirection)
    else if (key === 'legacyFxPurchaseVolume') update('legacyFxPurchaseVolume', null)
    else update(key, '' as FormState[typeof key])
  }

  function financeSliceOf(f: FormState): FinanceFormSlice {
    return {
      debtAmount: f.debtAmount,
      debtCurrency: f.debtCurrency,
      floatingRateShare: f.floatingRateShare,
      nearTermPayments: f.nearTermPayments,
      fxPurchaseVolume: f.fxPurchaseVolume,
      cashReserveDays: f.cashReserveDays,
      purchaseCurrencies: f.purchaseCurrencies,
      fxDirection: f.fxDirection,
      fxExposureAmount: f.fxExposureAmount,
      fxExposureCurrency: f.fxExposureCurrency,
      fxQuoteCurrency: f.fxQuoteCurrency,
      fxExposurePeriod: f.fxExposurePeriod,
      fxRateFrom: f.fxRateFrom,
      legacyFxPurchaseVolume: f.legacyFxPurchaseVolume,
    }
  }

  async function ensureCompany(): Promise<string> {
    if (activeCompanyId) {
      await companyApi.patch(activeCompanyId, {
        name: form.name.trim(),
        tax_id: form.taxId.trim() || null,
        hq_region: form.hqRegion.trim() || null,
        size_band: form.sizeBand || null,
        industry: form.industry || null,
      })
      return activeCompanyId
    }
    const created = await companyApi.create({
      name: form.name.trim(),
      tax_id: form.taxId.trim() || null,
      hq_region: form.hqRegion.trim() || null,
      size_band: form.sizeBand || null,
      industry: form.industry || null,
    })
    setActiveCompanyId(created.id)
    setCompanyId(created.id)
    await refreshUser()
    return created.id
  }

  async function upsertNode(
    cid: string,
    type: NodeType,
    payload: Omit<NodeCreateIn, 'node_type'>,
  ): Promise<CompanyNode> {
    const existingId = nodeIds[type]
    if (existingId) {
      return companyApi.patchNode(cid, existingId, payload)
    }
    const created = await companyApi.addNode(cid, { ...payload, node_type: type })
    setNodeIds((prev) => ({ ...prev, [type]: created.id }))
    return created
  }

  async function ensureEdge(
    cid: string,
    fromId: string,
    relation: string,
    toId: string,
    currentEdges: CompanyEdge[],
  ): Promise<CompanyEdge[]> {
    const found = currentEdges.find(
      (e) =>
        e.from_node_id === fromId && e.to_node_id === toId && e.relation_type === relation,
    )
    if (found) return currentEdges
    const created = await companyApi.addEdge(cid, {
      from_node_id: fromId,
      to_node_id: toId,
      relation_type: relation,
      confidence: 0.9,
      source_type: 'user',
    })
    const next = [...currentEdges, created]
    setEdges(next)
    return next
  }

  async function saveBasics(): Promise<string> {
    if (!form.name.trim()) throw new Error('Укажите название компании')
    const cid = await ensureCompany()
    setStatus('Данные компании сохранены')
    return cid
  }

  async function saveRole(): Promise<string> {
    if (!form.industry) throw new Error('Выберите отрасль')
    if (!form.productName.trim()) throw new Error('Укажите продукцию')
    const cid = await ensureCompany()
    await companyApi.patch(cid, { industry: form.industry })
    await upsertNode(cid, 'product', {
      name: form.productName.trim(),
      attributes_json: {
        business_role: form.role.trim() || undefined,
      },
    })
    setStatus('Роль, отрасль и продукция сохранены')
    return cid
  }

  async function saveGeo(): Promise<string> {
    const supply = firstCountry(form.supplyCountries)
    const marketCountry = firstCountry(form.marketCountries)
    if (!supply) throw new Error('Укажите хотя бы одну страну поставок')
    if (!marketCountry) throw new Error('Укажите рынки сбыта')
    const cid = await ensureCompany()
    const facilityRegion = form.hqRegion.trim() || 'Россия'
    if (!form.supplierName.trim()) {
      setForm((prev) => ({ ...prev, supplierName: `Поставщик (${supply})` }))
    }
    if (!form.marketName.trim()) {
      setForm((prev) => ({ ...prev, marketName: marketCountry }))
    }
    if (!form.facilityName.trim()) {
      setForm((prev) => ({ ...prev, facilityName: `Площадка · ${facilityRegion}` }))
    }
    await upsertNode(cid, 'supplier', {
      name: form.supplierName.trim() || `Поставщик (${supply})`,
      country: supply,
      attributes_json: {
        countries: form.supplyCountries
          .split(/[,;]/)
          .map((s) => s.trim())
          .filter(Boolean),
      },
    })
    await upsertNode(cid, 'market', {
      name: form.marketName.trim() || marketCountry,
      country: marketCountry,
      attributes_json: {
        markets: form.marketCountries
          .split(/[,;]/)
          .map((s) => s.trim())
          .filter(Boolean),
      },
    })
    await upsertNode(cid, 'facility', {
      name: form.facilityName.trim() || `Площадка · ${facilityRegion}`,
      country: 'Россия',
      region: facilityRegion,
    })
    setStatus('География сохранена')
    return cid
  }

  async function saveChain(): Promise<{ cid: string; ids: Record<NodeType, string> }> {
    if (!form.supplierName.trim()) throw new Error('Укажите поставщика')
    if (!form.componentName.trim()) throw new Error('Укажите компонент')
    if (!form.facilityName.trim()) throw new Error('Укажите площадку')
    if (!form.lineName.trim()) throw new Error('Укажите линию производства')
    if (!form.productName.trim()) throw new Error('Укажите продукт')
    if (!form.marketName.trim()) throw new Error('Укажите рынок')
    const named = [
      form.supplierName,
      form.componentName,
      form.facilityName,
      form.lineName,
      form.productName,
      form.marketName,
    ]
    if (named.some((n) => isUnconfirmedNodeName(n))) {
      throw new Error(
        'В цепочке нельзя сохранять «Не знаю» или пустой ответ как название узла. ' +
          'Укажите реальные названия или пока не сохраняйте этот шаг.',
      )
    }
    const share = Number(form.lineShare.replace(',', '.'))
    if (!Number.isFinite(share) || share <= 0 || share > 100) {
      throw new Error('Доля выпуска линии — число от 1 до 100 (пустое значение не подходит)')
    }

    const cid = await ensureCompany()
    const supply = firstCountry(form.supplyCountries) || 'Китай'
    const marketCountry = firstCountry(form.marketCountries) || form.marketName.trim()
    const facilityRegion = form.hqRegion.trim() || 'Россия'

    const supplier = await upsertNode(cid, 'supplier', {
      name: form.supplierName.trim(),
      country: supply,
    })
    const component = await upsertNode(cid, 'component', {
      name: form.componentName.trim(),
    })
    const facility = await upsertNode(cid, 'facility', {
      name: form.facilityName.trim(),
      country: 'Россия',
      region: facilityRegion,
    })
    const line = await upsertNode(cid, 'production_line', {
      name: form.lineName.trim(),
      output_share_percent: share,
    })
    const product = await upsertNode(cid, 'product', {
      name: form.productName.trim(),
      attributes_json: {
        business_role: form.role.trim() || undefined,
      },
    })
    const market = await upsertNode(cid, 'market', {
      name: form.marketName.trim(),
      country: marketCountry,
    })

    let edgeList = edges
    edgeList = await ensureEdge(cid, supplier.id, 'supplies', component.id, edgeList)
    edgeList = await ensureEdge(cid, component.id, 'used_in', line.id, edgeList)
    edgeList = await ensureEdge(cid, line.id, 'produced_at', facility.id, edgeList)
    edgeList = await ensureEdge(cid, product.id, 'produced_at', facility.id, edgeList)
    edgeList = await ensureEdge(cid, product.id, 'sold_in', market.id, edgeList)
    edgeList = await ensureEdge(cid, product.id, 'buys_from', supplier.id, edgeList)

    const ids: Record<NodeType, string> = {
      supplier: supplier.id,
      component: component.id,
      facility: facility.id,
      production_line: line.id,
      product: product.id,
      market: market.id,
    }
    setNodeIds(ids)
    setStatus('Цепочка поставки сохранена')
    return { cid, ids }
  }

  async function refreshCompleteness(cid: string) {
    const profile = await companyApi.profile(cid)
    setWarnings(profile.warnings)
    setCompleteness(profile.completeness)
    setNodeIds(nodeIdsFromProfile(profile.nodes))
    setEdges(profile.edges)
    return profile
  }

  async function runEventRecompute(cid: string, eventId: string): Promise<void> {
    setRecomputation(true)
    try {
      await eventsApi.recomputeImpact(eventId, cid)
      setRecomputePending(null)
      setError(null)
      setStatus(
        'Оценка влияния по событию пересчитана. Денежный сценарий появится после расчёта сценариев (основание события или явный what-if).',
      )
      navigate(discussPath(eventId))
    } catch (err) {
      setRecomputePending({ companyId: cid, eventId })
      const msg =
        err instanceof ApiError || err instanceof Error
          ? err.message
          : 'Не удалось пересчитать оценку'
      setError(
        `Финансовый профиль уже сохранён, но пересчёт оценки не удался: ${msg}. Можно повторить пересчёт без повторного сохранения профиля.`,
      )
      throw err
    } finally {
      setRecomputation(false)
    }
  }

  async function saveFinance(): Promise<string> {
    const cid = await ensureCompany()
    const body = buildFinancePatch(financeSliceOf(form))
    const eventId = searchParams.get('event')
    try {
      // Save only — refreshes existing Impact rows; does not create for this event.
      await companyApi.patchFinance(cid, body)
      setFieldErrors({})
      setRecomputePending(null)
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(fieldErrorMap(err.details))
      }
      throw err
    }
    if (eventId) {
      // One explicit recompute for the CTA event (not a second pass inside PATCH).
      await runEventRecompute(cid, eventId)
    } else {
      setStatus(
        'Финансовый профиль сохранён. Это не означает, что денежный сценарий уже доступен — для расчёта нужны также основания события или явный what-if.',
      )
    }
    return cid
  }

  async function finishSetup(): Promise<string> {
    const { cid } = await saveChain()
    await refreshCompleteness(cid)
    const profile = await companyApi.completeProfile(cid)
    setWarnings(profile.warnings)
    setCompleteness(profile.completeness)
    const built = await companyApi.buildDigitalTwin(cid)
    setBuildResult(built)
    await authApi.preferences({ registration_complete: true })
    setFinished(true)
    setStatus(built.message)
    await refreshUser()
    return cid
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setStatus(null)
    try {
      const current = STEPS[step].id as StepId
      let cid: string
      if (current === 'basics') cid = await saveBasics()
      else if (current === 'role') cid = await saveRole()
      else if (current === 'geo') cid = await saveGeo()
      else if (current === 'chain') cid = (await saveChain()).cid
      else if (current === 'finance') {
        cid = await saveFinance()
        // With ?event=: save → one recompute → navigate to discussion (no next wizard step).
        if (searchParams.get('event')) return
      } else cid = await finishSetup()

      if (current !== 'review') {
        await refreshCompleteness(cid)
        setStep((s) => Math.min(s + 1, STEPS.length - 1))
      }
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="container page-pad">
        <StateBlock variant="loading" title="Открываем мастер настройки" />
      </div>
    )
  }

  if (finished && buildResult) {
    return (
      <div className="container page-pad setup-page">
        <div className="setup-done">
          <p className="setup-kicker">Контекст готов</p>
          <h1 className="page-title">Модель влияния собрана</h1>
          <p className="page-lead">
            Покрытие Digital Twin — {buildResult.coverage_percent}%. В «Для вас» попадут только
            опубликованные новости с пересечением вашей цепочки или финансового профиля —
            пустая персональная лента при этом нормальна. Вход в аккаунт сам по себе карточки
            влияния не добавляет.
          </p>
          <div className="setup-done-metrics">
            <div className="market-tile">
              <div className="label">Покрытие</div>
              <div className="value">{buildResult.coverage_percent}%</div>
            </div>
            <div className="market-tile">
              <div className="label">Узлы</div>
              <div className="value">{buildResult.nodes}</div>
            </div>
            <div className="market-tile">
              <div className="label">Связи</div>
              <div className="value">{buildResult.edges}</div>
            </div>
            {typeof buildResult.impacts_computed === 'number' ? (
              <div className="market-tile">
                <div className="label">Совпадений сейчас</div>
                <div className="value">{buildResult.impacts_computed}</div>
              </div>
            ) : null}
          </div>
          <div className="setup-actions">
            <Link className="btn btn-primary" to="/news/for-you">
              Перейти к персональной ленте
            </Link>
            <Link className="btn btn-secondary" to="/company">
              Открыть профиль
            </Link>
          </div>
        </div>
      </div>
    )
  }

  const current = STEPS[step]

  return (
    <div className="container page-pad setup-page">
      <p className="setup-kicker">Настройка под компанию</p>
      <h1 className="page-title">{current.title}</h1>
      <p className="page-lead">{current.lead}</p>

      <ol className="setup-progress" aria-label="Шаги мастера">
        {STEPS.map((s, idx) => (
          <li
            key={s.id}
            className={
              idx === step ? 'is-current' : idx < step ? 'is-done' : undefined
            }
          >
            <span className="setup-progress-num">{idx + 1}</span>
            <span className="setup-progress-label">{s.title}</span>
          </li>
        ))}
      </ol>

      {completeness?.percent != null ? (
        <p className="setup-completeness muted">
          Заполнено обязательных полей: {completeness.required_done ?? 0} из{' '}
          {completeness.required_total ?? REQUIRED_TYPES.length + 1} · {completeness.percent}%
        </p>
      ) : null}

      <form className="setup-card" onSubmit={onSubmit}>
        {current.id === 'basics' ? (
          <div className="setup-fields">
            <div
              className="aside-card registry-lookup"
              style={{ position: 'static', marginBottom: 12 }}
            >
              <h2 style={{ fontSize: '1rem', margin: '0 0 4px' }}>
                Найти компанию по ИНН в реестре
              </h2>
              <p className="muted" style={{ margin: '0 0 8px' }}>
                Введите ИНН — подтянем публичные реквизиты организации из реестра. Это
                предзаполнение, а не подтверждение, что компания принадлежит вам.
              </p>
              <div className="field">
                <label htmlFor="setup-inn">ИНН</label>
                <input
                  id="setup-inn"
                  value={form.taxId}
                  onChange={(e) => {
                    update('taxId', e.target.value)
                    resetLookupResult()
                  }}
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="10 цифр (организация) или 12 (ИП)"
                  aria-invalid={Boolean(innError)}
                />
                {innError ? (
                  <p className="form-error" data-testid="inn-error" style={{ marginTop: 4 }}>
                    {innError}
                  </p>
                ) : null}
              </div>
              <div className="setup-actions" style={{ marginTop: 0 }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  data-testid="registry-lookup-btn"
                  disabled={lookupState === 'loading' || Boolean(confirming)}
                  onClick={() => void runLookup()}
                >
                  {lookupState === 'loading' ? 'Ищем…' : 'Найти компанию'}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  data-testid="registry-manual-btn"
                  onClick={() => resetLookupResult()}
                >
                  Заполнить вручную
                </button>
              </div>

              {lookupState === 'loading' ? (
                <p className="muted" style={{ marginTop: 8 }}>
                  Запрашиваем справочник…
                </p>
              ) : null}

              {lookupError ? (
                <div className="form-error" data-testid="registry-error" style={{ marginTop: 8 }}>
                  {lookupError}
                </div>
              ) : null}

              {lookupResult && lookupState === 'done' ? (
                <div className="registry-result" data-testid="registry-result" style={{ marginTop: 10 }}>
                  {lookupResult.status === 'not_configured' ? (
                    <p className="muted" data-testid="registry-not-configured">
                      {lookupResult.note ||
                        'Поиск по реестру не подключён на этом сервере. Заполните данные вручную ниже.'}
                    </p>
                  ) : null}
                  {lookupResult.status === 'not_found' ? (
                    <p className="muted" data-testid="registry-not-found">
                      {lookupResult.note ||
                        'По этому ИНН организация в реестре не найдена. Проверьте номер или заполните вручную.'}
                    </p>
                  ) : null}
                  {lookupResult.status === 'ok' ? (
                    <>
                      {lookupResult.candidate_count > 1 ? (
                        <p className="muted" style={{ margin: '0 0 8px' }}>
                          Найдено несколько записей (например, головная организация и филиалы).
                          Выберите подходящую — ничего не подставляем автоматически.
                        </p>
                      ) : null}
                      {lookupResult.candidates.map((cand) => (
                        <div
                          key={cand.candidate_id}
                          className="registry-candidate"
                          data-testid="registry-candidate"
                          style={{
                            border: '1px solid var(--border, #d8dee9)',
                            borderRadius: 8,
                            padding: 10,
                            marginBottom: 8,
                          }}
                        >
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                            <strong>{candidateTitle(cand)}</strong>
                            <span className="muted">{orgTypeLabel(cand.org_type)}</span>
                            {cand.branch_type === 'branch' ? (
                              <span className="badge" data-testid="candidate-branch">
                                Филиал
                              </span>
                            ) : null}
                            {isCandidateInactive(cand) ? (
                              <span className="form-error" data-testid="candidate-inactive">
                                {cand.status_label || 'Недействующая'}
                              </span>
                            ) : null}
                          </div>
                          <dl className="registry-requisites" style={{ margin: '8px 0' }}>
                            {candidateRequisites(cand).map((r) => (
                              <div key={r.key} style={{ display: 'flex', gap: 6 }}>
                                <dt className="muted" style={{ minWidth: 72 }}>
                                  {r.label}
                                </dt>
                                <dd style={{ margin: 0 }}>{r.value}</dd>
                              </div>
                            ))}
                          </dl>
                          <button
                            type="button"
                            className="btn btn-primary"
                            data-testid="candidate-use-btn"
                            disabled={Boolean(confirming)}
                            onClick={() => void applyCandidate(cand)}
                          >
                            {confirming === cand.candidate_id
                              ? 'Сохраняем…'
                              : 'Использовать эти данные'}
                          </button>
                        </div>
                      ))}
                      {lookupResult.source ? (
                        <p className="muted" data-testid="registry-source" style={{ marginTop: 4 }}>
                          Источник: {lookupResult.source.title}. {lookupResult.source.note}
                          {lookupResult.source_actuality_date
                            ? ` Актуальность реестра: ${lookupResult.source_actuality_date}.`
                            : ''}
                          {lookupResult.retrieved_at
                            ? ` Запрос выполнен: ${lookupResult.retrieved_at} (это не дата обновления реестра).`
                            : ''}
                        </p>
                      ) : null}
                    </>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className="field">
              <label htmlFor="setup-name">Название компании</label>
              <input
                id="setup-name"
                value={form.name}
                onChange={(e) => update('name', e.target.value)}
                required
                autoComplete="organization"
              />
            </div>
            <div className="field">
              <label htmlFor="setup-region">Регион штаб-квартиры</label>
              <input
                id="setup-region"
                value={form.hqRegion}
                onChange={(e) => update('hqRegion', e.target.value)}
                placeholder="Например, Тула"
              />
            </div>
            <div className="field">
              <label htmlFor="setup-size">Размер компании</label>
              <select
                id="setup-size"
                value={form.sizeBand}
                onChange={(e) => update('sizeBand', e.target.value)}
              >
                {SIZE_OPTIONS.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            {registrySourceNote ? (
              <p className="muted" data-testid="registry-provenance-note">
                Реквизиты предзаполнены из реестра ({registrySourceNote}) Любое поле, которое вы
                измените, станет ручным и перестанет считаться «из реестра».
              </p>
            ) : null}
          </div>
        ) : null}

        {current.id === 'role' ? (
          <div className="setup-fields">
            <div className="field">
              <label htmlFor="setup-role">Ваша роль</label>
              <input
                id="setup-role"
                value={form.role}
                onChange={(e) => update('role', e.target.value)}
                placeholder="Директор по закупкам, владелец…"
              />
            </div>
            <div className="field">
              <label htmlFor="setup-industry">Отрасль</label>
              <select
                id="setup-industry"
                value={form.industry}
                onChange={(e) => update('industry', e.target.value)}
                required
              >
                <option value="">Выберите отрасль</option>
                {industries.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </select>
              {suggestedIndustry && suggestedIndustry !== form.industry ? (
                <p className="muted" data-testid="industry-suggestion" style={{ marginTop: 6 }}>
                  Справочник предполагает отрасль «{industryLabel(suggestedIndustry)}» по ОКВЭД.
                  ОКВЭД ≠ отрасль — подтвердите вручную.{' '}
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ marginLeft: 6 }}
                    onClick={() => update('industry', suggestedIndustry)}
                  >
                    Подставить
                  </button>
                </p>
              ) : null}
            </div>
            <div className="field">
              <label htmlFor="setup-product">Основная продукция</label>
              <input
                id="setup-product"
                value={form.productName}
                onChange={(e) => update('productName', e.target.value)}
                required
                placeholder="Например, промышленные насосы"
              />
            </div>
          </div>
        ) : null}

        {current.id === 'geo' ? (
          <div className="setup-fields">
            <div className="field">
              <label htmlFor="setup-supply">Страны поставок</label>
              <input
                id="setup-supply"
                value={form.supplyCountries}
                onChange={(e) => update('supplyCountries', e.target.value)}
                placeholder="Китай, Вьетнам"
                required
              />
              <span className="field-hint">Через запятую. Первая страна станет основной.</span>
            </div>
            <div className="field">
              <label htmlFor="setup-markets">Рынки сбыта</label>
              <input
                id="setup-markets"
                value={form.marketCountries}
                onChange={(e) => update('marketCountries', e.target.value)}
                placeholder="Россия, СНГ"
                required
              />
              <span className="field-hint">Через запятую. Первый рынок — основной.</span>
            </div>
          </div>
        ) : null}

        {current.id === 'chain' ? (
          <div className="setup-fields">
            <div className="setup-chain-preview" aria-hidden>
              <span>Поставщик</span>
              <span>→</span>
              <span>Компонент</span>
              <span>→</span>
              <span>Линия</span>
              <span>→</span>
              <span>Продукт</span>
              <span>→</span>
              <span>Рынок</span>
            </div>
            <div className="field">
              <label htmlFor="setup-supplier">Поставщик</label>
              <input
                id="setup-supplier"
                value={form.supplierName}
                onChange={(e) => update('supplierName', e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="setup-component">Компонент</label>
              <input
                id="setup-component"
                value={form.componentName}
                onChange={(e) => update('componentName', e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="setup-facility">Площадка / завод</label>
              <input
                id="setup-facility"
                value={form.facilityName}
                onChange={(e) => update('facilityName', e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="setup-line">Линия производства</label>
              <input
                id="setup-line"
                value={form.lineName}
                onChange={(e) => update('lineName', e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="setup-share">Доля выпуска линии, %</label>
              <input
                id="setup-share"
                value={form.lineShare}
                onChange={(e) => update('lineShare', e.target.value)}
                inputMode="decimal"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="setup-product-chain">Продукт</label>
              <input
                id="setup-product-chain"
                value={form.productName}
                onChange={(e) => update('productName', e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="setup-market-name">Рынок</label>
              <input
                id="setup-market-name"
                value={form.marketName}
                onChange={(e) => update('marketName', e.target.value)}
                required
              />
            </div>
          </div>
        ) : null}

        {current.id === 'finance' ? (
          <div className="setup-fields">
            <p className="muted" style={{ marginBottom: 8 }}>
              Шаг необязательный. Секции независимы: достаточно кредитов или одной валютной
              операции. Пустое поле — неизвестно; введённый 0 — известный ноль. Сохранение
              профиля не равно успешному расчёту сценария.
            </p>

            {(() => {
              const slice = financeSliceOf(form)
              const rateOk = rateTrackReady(slice)
              const fxOk = fxTrackReady(slice)
              const quoteHint = quoteConventionLabel(
                form.fxExposureCurrency,
                form.fxQuoteCurrency,
              )
              return (
                <>
                  <div className="aside-card" style={{ position: 'static', marginBottom: 12 }}>
                    <h2 style={{ fontSize: '1rem', margin: '0 0 8px' }}>Готовность профиля</h2>
                    <p style={{ margin: '0 0 4px' }}>
                      <strong>Кредиты:</strong>{' '}
                      {rateOk
                        ? 'параметры долга заполнены'
                        : `не хватает: ${rateTrackMissing(slice).join(', ') || '—'}`}
                    </p>
                    <p style={{ margin: '0 0 4px' }}>
                      <strong>Валютная операция:</strong>{' '}
                      {fxOk
                        ? 'экспозиция заполнена'
                        : `не хватает: ${fxTrackMissing(slice).join(', ') || '—'}`}
                    </p>
                    {fxOk && !form.fxRateFrom.trim() ? (
                      <p className="muted" style={{ margin: '8px 0 0' }}>
                        Исходный курс не указан: профиль можно сохранить, но для денежного
                        FX-сценария понадобится курс/основание события или what-if.
                      </p>
                    ) : null}
                    <p className="muted" style={{ margin: '8px 0 0' }}>
                      MVP: одна валютная операция/экспозиция, не портфель валют.
                    </p>
                  </div>

                  <fieldset className="setup-fieldset" style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend style={{ fontWeight: 600, marginBottom: 8 }}>Кредиты</legend>
                    <div className="field">
                      <label htmlFor="setup-debt">Сумма долга</label>
                      <input
                        id="setup-debt"
                        value={form.debtAmount}
                        onChange={(e) => update('debtAmount', e.target.value)}
                        inputMode="decimal"
                        placeholder="Пусто = неизвестно"
                        aria-invalid={Boolean(fieldErrors.debt_amount)}
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('debtAmount')}
                      >
                        Не знаю
                      </button>
                      {fieldErrors.debt_amount ? (
                        <p className="form-error" style={{ marginTop: 4 }}>
                          {fieldErrors.debt_amount}
                        </p>
                      ) : null}
                    </div>
                    <div className="field">
                      <label htmlFor="setup-debt-ccy">Валюта суммы долга</label>
                      <input
                        id="setup-debt-ccy"
                        value={form.debtCurrency}
                        onChange={(e) => update('debtCurrency', e.target.value.toUpperCase())}
                        placeholder="Например CNY — не подставляется как RUB"
                        aria-invalid={Boolean(fieldErrors.debt_amount_unit)}
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('debtCurrency')}
                      >
                        Не знаю
                      </button>
                    </div>
                    <div className="field">
                      <label htmlFor="setup-float">Доля долга с плавающей ставкой, %</label>
                      <input
                        id="setup-float"
                        value={form.floatingRateShare}
                        onChange={(e) => update('floatingRateShare', e.target.value)}
                        inputMode="decimal"
                        placeholder="Пусто = неизвестно; 0 = известный ноль"
                        aria-invalid={Boolean(fieldErrors.floating_rate_share_percent)}
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('floatingRateShare')}
                      >
                        Не знаю
                      </button>
                      {fieldErrors.floating_rate_share_percent ? (
                        <p className="form-error" style={{ marginTop: 4 }}>
                          {fieldErrors.floating_rate_share_percent}
                        </p>
                      ) : null}
                    </div>
                  </fieldset>

                  <fieldset
                    className="setup-fieldset"
                    style={{ border: 0, padding: 0, margin: '16px 0 0' }}
                  >
                    <legend style={{ fontWeight: 600, marginBottom: 8 }}>
                      Валютные платежи и поступления
                    </legend>
                    {form.legacyFxPurchaseVolume ? (
                      <p className="muted" style={{ marginBottom: 8 }}>
                        Ранее был указан объём без валюты ({form.legacyFxPurchaseVolume}). Укажите
                        заново сумму с валютой и направлением — старое значение не переносится
                        автоматически.
                      </p>
                    ) : null}
                    <div className="field">
                      <label htmlFor="setup-fx-dir">Направление</label>
                      <select
                        id="setup-fx-dir"
                        value={form.fxDirection}
                        onChange={(e) =>
                          update('fxDirection', e.target.value as FxDirection)
                        }
                      >
                        <option value="">Не указано</option>
                        <option value="payment">Платёж</option>
                        <option value="receipt">Поступление</option>
                      </select>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('fxDirection')}
                      >
                        Не знаю
                      </button>
                    </div>
                    <div className="field">
                      <label htmlFor="setup-fx-amt">Сумма</label>
                      <input
                        id="setup-fx-amt"
                        value={form.fxExposureAmount}
                        onChange={(e) => update('fxExposureAmount', e.target.value)}
                        inputMode="decimal"
                        placeholder="Пусто = неизвестно"
                        aria-invalid={Boolean(fieldErrors.fx_exposure_amount)}
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('fxExposureAmount')}
                      >
                        Не знаю
                      </button>
                      {fieldErrors.fx_exposure_amount ? (
                        <p className="form-error" style={{ marginTop: 4 }}>
                          {fieldErrors.fx_exposure_amount}
                        </p>
                      ) : null}
                    </div>
                    <div className="field">
                      <label htmlFor="setup-fx-ccy">Валюта суммы</label>
                      <input
                        id="setup-fx-ccy"
                        value={form.fxExposureCurrency}
                        onChange={(e) =>
                          update('fxExposureCurrency', e.target.value.toUpperCase())
                        }
                        placeholder="CNY"
                        aria-invalid={Boolean(fieldErrors.fx_exposure_currency)}
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('fxExposureCurrency')}
                      >
                        Не знаю
                      </button>
                    </div>
                    <div className="field">
                      <label htmlFor="setup-fx-quote">Валюта расчёта</label>
                      <input
                        id="setup-fx-quote"
                        value={form.fxQuoteCurrency}
                        onChange={(e) =>
                          update('fxQuoteCurrency', e.target.value.toUpperCase())
                        }
                        placeholder="RUB"
                        aria-invalid={Boolean(fieldErrors.fx_quote_currency)}
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('fxQuoteCurrency')}
                      >
                        Не знаю
                      </button>
                    </div>
                    {quoteHint ? (
                      <p className="muted" style={{ marginTop: -4 }}>
                        Котировка: {quoteHint} (единиц валюты расчёта за 1 единицу валюты суммы).
                        Введённый курс — параметр профиля, не observed рыночное изменение.
                      </p>
                    ) : null}
                    <div className="field">
                      <label htmlFor="setup-fx-period">Период суммы (опционально)</label>
                      <input
                        id="setup-fx-period"
                        value={form.fxExposurePeriod}
                        onChange={(e) => update('fxExposurePeriod', e.target.value)}
                        placeholder="Например, Q3 2026"
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('fxExposurePeriod')}
                      >
                        Не знаю
                      </button>
                    </div>
                    <div className="field">
                      <label htmlFor="setup-fx-rate">
                        Исходный курс{quoteHint ? ` (${quoteHint})` : ''} — опционально
                      </label>
                      <input
                        id="setup-fx-rate"
                        value={form.fxRateFrom}
                        onChange={(e) => update('fxRateFrom', e.target.value)}
                        inputMode="decimal"
                        placeholder="Не сохраняется как observed события"
                        aria-invalid={Boolean(fieldErrors.fx_rate_from)}
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('fxRateFrom')}
                      >
                        Не знаю
                      </button>
                      {fieldErrors.fx_rate_from ? (
                        <p className="form-error" style={{ marginTop: 4 }}>
                          {fieldErrors.fx_rate_from}
                        </p>
                      ) : null}
                    </div>
                  </fieldset>

                  <fieldset
                    className="setup-fieldset"
                    style={{ border: 0, padding: 0, margin: '16px 0 0' }}
                  >
                    <legend style={{ fontWeight: 600, marginBottom: 8 }}>
                      Дополнительно (ликвидность)
                    </legend>
                    <p className="muted" style={{ marginBottom: 8 }}>
                      Не обязательны для независимого FX-расчёта.
                    </p>
                    <div className="field">
                      <label htmlFor="setup-pay90">Ближайшие платежи, 90 дней</label>
                      <input
                        id="setup-pay90"
                        value={form.nearTermPayments}
                        onChange={(e) => update('nearTermPayments', e.target.value)}
                        inputMode="decimal"
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('nearTermPayments')}
                      >
                        Не знаю
                      </button>
                    </div>
                    <div className="field">
                      <label htmlFor="setup-fx-legacy">Объём закупок в валютах (legacy)</label>
                      <input
                        id="setup-fx-legacy"
                        value={form.fxPurchaseVolume}
                        onChange={(e) => update('fxPurchaseVolume', e.target.value)}
                        inputMode="decimal"
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('fxPurchaseVolume')}
                      >
                        Не знаю
                      </button>
                    </div>
                    <div className="field">
                      <label htmlFor="setup-cash">Горизонт денежных резервов, дни</label>
                      <input
                        id="setup-cash"
                        value={form.cashReserveDays}
                        onChange={(e) => update('cashReserveDays', e.target.value)}
                        inputMode="decimal"
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginTop: 6 }}
                        onClick={() => clearFinanceField('cashReserveDays')}
                      >
                        Не знаю
                      </button>
                    </div>
                    <div className="field">
                      <label htmlFor="setup-ccy">Валюты закупок (список)</label>
                      <input
                        id="setup-ccy"
                        value={form.purchaseCurrencies}
                        onChange={(e) => update('purchaseCurrencies', e.target.value)}
                        placeholder="Например CNY, USD — пусто не становится RUB"
                      />
                    </div>
                  </fieldset>
                </>
              )
            })()}
          </div>
        ) : null}

        {current.id === 'review' ? (
          <div className="setup-review">
            <div className="aside-card" style={{ position: 'static' }}>
              <h2>Карточка</h2>
              <p>
                <strong>Компания:</strong> {form.name || '—'}
              </p>
              <p>
                <strong>ИНН:</strong> {form.taxId || '—'}
              </p>
              <p>
                <strong>Регион:</strong> {form.hqRegion || '—'}
              </p>
              <p>
                <strong>Отрасль:</strong> {industryLabel(form.industry)}
              </p>
              <p>
                <strong>Роль:</strong> {form.role || '—'}
              </p>
            </div>
            <div className="aside-card" style={{ position: 'static' }}>
              <h2>Цепочка</h2>
              <ul className="setup-review-chain">
                {(
                  [
                    ['supplier', form.supplierName],
                    ['component', form.componentName],
                    ['facility', form.facilityName],
                    ['production_line', `${form.lineName} · ${form.lineShare}%`],
                    ['product', form.productName],
                    ['market', form.marketName],
                  ] as const
                ).map(([type, name]) => (
                  <li key={type}>
                    <span className="muted">{nodeTypeLabel(type)}</span>
                    <strong>{name || '—'}</strong>
                  </li>
                ))}
              </ul>
            </div>
            {warnings.length > 0 ? (
              <div className="aside-card setup-warnings" style={{ position: 'static' }}>
                <h2>Замечания</h2>
                <ul>
                  {warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="muted">Критических пробелов нет — можно завершить настройку.</p>
            )}
          </div>
        ) : null}

        {status ? <p className="setup-status">{status}</p> : null}
        {error ? <div className="form-error">{error}</div> : null}
        {recomputePending ? (
          <div className="setup-actions" style={{ marginBottom: 12 }}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={recomputation || saving}
              onClick={() => {
                void runEventRecompute(
                  recomputePending.companyId,
                  recomputePending.eventId,
                ).catch(() => {
                  /* error already surfaced */
                })
              }}
            >
              {recomputation ? 'Пересчёт…' : 'Повторить пересчёт оценки'}
            </button>
            <Link
              className="btn btn-secondary"
              to={discussPath(recomputePending.eventId)}
            >
              Вернуться к обсуждению
            </Link>
          </div>
        ) : null}

        <div className="setup-actions">
          {step > 0 ? (
            <button
              type="button"
              className="btn btn-secondary"
              disabled={saving || recomputation}
              onClick={() => {
                setError(null)
                setStatus(null)
                setStep((s) => Math.max(0, s - 1))
              }}
            >
              Назад
            </button>
          ) : (
            <Link className="btn btn-secondary" to={activeCompanyId ? '/company' : '/news/for-you'}>
              Отмена
            </Link>
          )}
          <button
            type="submit"
            className="btn btn-primary"
            disabled={saving || recomputation}
          >
            {saving || recomputation
              ? recomputation
                ? 'Пересчёт…'
                : 'Сохраняем…'
              : current.id === 'review'
                ? 'Завершить и собрать модель'
                : current.id === 'finance'
                  ? searchParams.get('event')
                    ? 'Сохранить и пересчитать оценку'
                    : 'Сохранить финансы'
                  : 'Сохранить и дальше'}
          </button>
          {current.id === 'finance' ? (
            <button
              type="button"
              className="btn btn-secondary"
              disabled={saving}
              onClick={() => {
                setError(null)
                setStatus(null)
                setStep((s) => Math.min(s + 1, STEPS.length - 1))
              }}
            >
              Пропустить
            </button>
          ) : null}
        </div>
      </form>
    </div>
  )
}
