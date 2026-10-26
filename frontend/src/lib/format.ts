export function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

export function nodeTypeLabel(type?: string): string {
  const map: Record<string, string> = {
    supplier: 'Поставщик',
    component: 'Компонент',
    product: 'Продукт',
    facility: 'Площадка',
    production_line: 'Линия',
    market: 'Рынок',
    currency: 'Валюта',
  }
  return type ? map[type] ?? type : ''
}

export function industryLabel(industry?: string | null): string {
  if (!industry) return '—'
  const map: Record<string, string> = {
    equipment: 'Производство оборудования',
    manufacturing: 'Производство',
    electronics: 'Электроника',
    logistics: 'Логистика',
    retail: 'Ритейл',
    energy: 'Энергетика',
    other: 'Другое',
  }
  return map[industry] ?? industry
}

export function claimLabel(claim: string): string {
  const map: Record<string, string> = {
    confirmed_fact: 'Факт',
    inference: 'Вывод',
    assumption: 'Допущение',
    estimate: 'Оценка',
  }
  return map[claim] ?? 'Оценка'
}
