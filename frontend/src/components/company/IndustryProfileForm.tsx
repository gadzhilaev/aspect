import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { companyApi } from '../../api/endpoints'
import type { IndustryProfile } from '../../api/types'
import { INDUSTRY_FIELDS, industryDraft, industryPatch, type IndustryDraft } from '../../lib/industryProfile'

export function IndustryProfileForm({ companyId }: { companyId: string }) {
  const [original, setOriginal] = useState<IndustryProfile | null>(null)
  const [draft, setDraft] = useState<IndustryDraft | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    companyApi.industryProfile(companyId).then(profile => {
      if (active) { setOriginal(profile); setDraft(industryDraft(profile)) }
    }).catch(err => { if (active) setError(err instanceof Error ? err.message : 'Не удалось загрузить интересы') })
    return () => { active = false }
  }, [companyId, attempt])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!original || !draft || busy) return
    const patch = industryPatch(original, draft)
    if (!Object.keys(patch).length) { setMessage('Изменений нет'); return }
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await companyApi.patchIndustryProfile(companyId, patch)
      setOriginal(result); setDraft(industryDraft(result))
      setMessage('Интересы сохранены. Откройте «Для вас», чтобы увидеть доступные совпадения.')
    } catch (err) { setError(err instanceof Error ? err.message : 'Не удалось сохранить интересы') }
    finally { setBusy(false) }
  }
  return <section className="company-section-card integration-form">
    <h2>Интересы для новостной ленты</h2>
    <p className="company-section-note">Укажите, что продаёт или производит компания. По этим данным сервис подбирает уже опубликованные новости. Совпадение по теме не является расчётом ущерба.</p>
    {error && <p role="alert" className="form-error">{error}</p>}
    {!draft ? (error ? <button className="btn btn-secondary" onClick={() => { setError(''); setAttempt(n => n + 1) }}>Повторить загрузку</button> : <p role="status">Загружаем интересы…</p>) :
      <form onSubmit={save}>
        <fieldset disabled={busy}>
          <div className="field"><label htmlFor="industry-role">Деятельность</label>
            <select id="industry-role" value={draft.activity_role} onChange={e => setDraft({ ...draft, activity_role: e.target.value })}>
              <option value="">Не указана</option><option value="retailer">Розничная торговля</option><option value="manufacturer">Производство</option><option value="distributor">Дистрибуция</option><option value="other">Другое</option>
            </select>
          </div>
          {INDUSTRY_FIELDS.map(({ key, label, example }) => <div className="field" key={key}>
            <label htmlFor={`industry-${key}`}>{label}</label>
            <input id={`industry-${key}`} value={draft[key]} placeholder={example} maxLength={2000} onChange={e => setDraft({ ...draft, [key]: e.target.value })} />
          </div>)}
          <p className="company-section-note">Несколько значений — через запятую. Пустое поле очищает ранее указанное значение. Валюты меняются в разделе «Финансы».</p>
          <button className="btn btn-primary" type="submit">{busy ? 'Сохраняем…' : 'Сохранить интересы'}</button>
        </fieldset>
      </form>}
    {message && <p role="status">{message}</p>}
    <Link className="btn btn-secondary" to="/news/for-you">Перейти в ленту «Для вас»</Link>
  </section>
}
