# Банковские материалы на странице новости (этап 6.12)

Дата: 2026-10-23  
Связанные: `EVENT_BANK_EVIDENCE.md`, `BANK_MATERIALS_UI.md`, `BANK_MATERIALS_API.md`,
`COMPETITION_UI_ACCEPTANCE.md`.

Рабочая БД, root `.env`, `:8003` **не** менялись.  
Без live LLM / browser automation / CDP / скриншотов / commit/push.

---

## 1. Диагностика (почему в макете есть, на стенде не было)

| Вопрос | Ответ |
|--------|--------|
| Вызывается ли `bank-evidence` на странице новости? | **Нет** (до этапа). `NewsDetailPage` не обращался к API. |
| Что отдаёт API на UI-стенде `:8018`? | Для `evt_comp_stand_policy_rate_32f5aef5` при Bearer: **`status=available`**, **3** evidence-фрагмента. OCR whitelist в `stand.env` настроен. |
| Без Bearer? | **401** (корпус не публичный). |
| Вердикт | **Отсутствие UI**, не пустая выдача и не «integration_not_configured». |

Проверка на стенде (без LLM):

```powershell
# login competition-demo-a → GET /api/v1/events/{event_id}/bank-evidence
```

---

## 2. Что сделано

| Файл | Назначение |
|------|------------|
| `web/src/api/bankMaterialsTypes.ts` | Типы `EventBankEvidence` / item |
| `web/src/api/endpoints.ts` | `eventsApi.bankEvidence` → `GET /events/{id}/bank-evidence` |
| `web/src/lib/bankMaterialsDisplay.ts` | parse, empty copy, news content-type labels, disclaimer |
| `web/src/components/news/NewsBankAnalytics.tsx` | Блок «Аналитика Альфа-Банка» |
| `web/src/pages/NewsDetailPage.tsx` | Блок **после** «Источники», отдельно от них |
| `web/src/styles/bank-materials.css` | Стили секции (tokens light/dark, узкая ширина) |
| `web/scripts/news-bank-analytics-ui.test.mjs` | Тесты |
| `web/package.json` | `npm run test:news-bank-analytics` |

Новых таблиц, retrieval и LLM **нет**. Только существующий endpoint 2.13 и fragment-страница 2.15.

---

## 3. Поведение карточки

- Название документа, дата с precision (без выдуманного «1-го числа»).
- `exact_quote` → «Точная цитата»; `summary` → «Пересказ».
- Тип: «Факт из материала» / «Интерпретация» / «Прогноз».
- «Посмотреть материал» → `/bank-materials/fragments/{fragment_id}?event=…` (точный ID).
- Disclaimer: тематическая связь ≠ подтверждение всех утверждений новости.
- Не склеиваем фрагменты; `restricted` / пустой текст отбрасываются на клиенте.
- Технические ID / OCR run / `query_preview` пользователю не показываются.

---

## 4. Состояния

| Состояние | UI |
|-----------|-----|
| Гость | Блок **не** рендерится, API **не** вызывается |
| Loading | «Загружаем материалы банка…» |
| `available` + items | Список карточек |
| `no_matching_evidence` / `event_date_unavailable` / `integration_not_configured` | Человеческий empty-copy |
| Ошибка запроса | Сообщение + «Повторить»; новость остаётся читаемой |
| 401/403 на запросе | Подсказка войти (без раскрытия конфигов) |

Ошибка материалов **не** ломает загрузку body новости (`publicApi.newsDetail` независим).

---

## 5. Светлая / тёмная тема и узкая ширина

В CSS используются `var(--color-*)` (как у bank-materials). Media `max-width: 640px` — кнопка на всю ширину.  
**Визуальный** просмотр в браузере в этом этапе **не** заявлялся — только наличие токенов и media-правил в коде / тестах.

---

## 6. Тесты

```powershell
cd web
npm run test:news-bank-analytics
npm run test:bank-materials
npm run build
```

| Проверка | Как |
|----------|-----|
| available / empty / error wiring | fixtures + source contracts |
| Типы fact/forecast/interpretation | `newsContentTypeLabel` |
| Переход по правильному `fragment_id` | `fragmentDetailPath` |
| Нет model HTTP в компоненте | source assert |
| Регрессия chat bank UI | `test:bank-materials` |
| Typecheck + bundle | `npm run build` |

---

## 7. Маршрут ручной проверки на UI-стенде

Сайт: http://127.0.0.1:5178 · API: http://127.0.0.1:8018  
Пароль: `data/competition_stand/ui_acceptance_611/demo_password.local`

1. **Гость.** Открыть новость о ставке без входа → блок «Аналитика Альфа-Банка» отсутствует; источники новости на месте.
2. **Вход.** `competition-demo-a@example.com` → «Для вас» → открыть новость о ставке.
3. Под «Источники» — секция **«Аналитика Альфа-Банка»** с карточками (на стенде API отдаёт 3 фрагмента).
4. Проверить: дата, тип (факт/интерпретация/прогноз), цитата или «Пересказ», disclaimer про тематическую связь.
5. **Посмотреть материал** → экран fragment с тем же текстом; PDF по Bearer.
6. Убедиться, что цифры документа (например 14%) не смешиваются с синтетикой события (16%) в одной «доказательной» фразе.
7. (Опционально) светлая/тёмная тема и узкое окно — глазами.

**Стоп этапа 6.12.**
