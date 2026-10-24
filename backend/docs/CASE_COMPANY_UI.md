# Case context on Company page (Этап 1.13)

Дата: 2026-10-20  
Отображение аддитивного `case_context` на странице «Компания» без замены ручного профиля.

## Изменения

| Файл | Назначение |
|------|------------|
| `web/src/api/types.ts` | TypeScript-типы `CaseContext` и вложенных схем; `case_context?` optional |
| `web/src/lib/caseContextDisplay.ts` | Чистые подписи статусов, продуктов, provenance |
| `web/src/components/company/CaseContextSection.tsx` | Раздел «Данные компании из источника» |
| `web/src/pages/CompanyPage.tsx` | Подключение секции после hero |
| `web/src/styles/company.css` | Сетка, продукты, provenance, mobile |
| `web/scripts/case-context-display.test.mjs` | Лёгкие проверки на `node:test` |
| `web/package.json` | Скрипт `test:case-context` |
| `docs/CASE_COMPANY_UI.md` | Этот отчёт |

Backend, миграции, рабочая БД и `.env` не менялись.  
Реальные снимки не активировались, организации не привязывались.  
Другие страницы не трогались.

## Поведение

- Данные только из `companyApi.context()`; demo-fallback в UI нет.
- Нет `case_context` → секция скрыта, страница работает как раньше.
- Ошибка загрузки контекста → существующий `StateBlock` error + retry (не «данных нет»).
- Ручные `industry_label` / `size_label` / coverage не зависят от кейса.
- При расхождении профиля и источника — явная пометка, без автовыбора.
- Продукты: «Есть в данных» / «Отмечено отсутствие» / «Нет сведений» / «Данные расходятся».
- Факторинг один раз в списке продуктов.
- ФТС: raw страны + «Направление торговли в источнике не указано».
- Выручка в основном блоке: только «Единицы выручки в источнике не уточнены».
- «Откуда данные»: файл, версия набора, номера записей, ограничения; без UUID и абсолютных путей.

### Статусы

| status | UX |
|--------|-----|
| `integration_not_configured` | Спокойный статус: источник не подключён к среде |
| `not_linked` | Нет связанных данных источника |
| `no_active_snapshot` | Набор недоступен |
| `uid_missing_in_snapshot` | Организация нет в текущем наборе; профиль пользователя на месте |
| `profile_absent` | Org есть, подробного профиля нет |
| `profile_available` | Карточки фактов + продукты + provenance |

Пользователю не показываются имена env, `snapshot_id` и советы запустить импорт/привязать U_ID.

## Проверки

```bash
cd web
npm run test:case-context
npm run build
```

Выполнено:

| Проверка | Как |
|----------|-----|
| Все статусы в типах и copy | `node:test` + исходники |
| true/false/unknown/conflict | `node:test` + fixtures |
| Отсутствие `case_context` | секция `return null` |
| Факторинг без дубля | helper `hasFactoringCode` |
| Нет выдуманных ₽ / направления торговли | assert по исходникам |
| Сохранение ручного профиля | optional `case_context`; hero без подмены |
| Snapshot A→B без подмеса A | fixture provenance `snap-b` ≠ `snap-a` |
| Typecheck + production bundle | `npm run build` |

### Не проверено визуально

Браузер, скриншоты и CDP **не** запускались. Не утверждается визуальная проверка светлой/тёмной темы, focus-ring и mobile layout в реальном viewport — только CSS по токенам и правила в коде.

Во frontend нет React Testing Library / vitest; тяжёлый стек не ставился.  
Проверки логики — `node --test` по исходникам и контрактным fixtures.

**Стоп этапа 1.13.**
