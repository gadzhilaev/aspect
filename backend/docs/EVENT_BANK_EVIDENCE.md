# Event bank evidence (Этап 2.13)

Дата: 2026-10-21  
Read-only подбор **проверенных** банковских фрагментов для конкретного события.  
Без генерации ответа, без изменения impact/confidence/assessment, без UI и без чата.

Рабочая БД, `.env`, запущенные сервисы **не** менялись.  
OCR / LLM / браузер / CDP / скриншоты / commit/push не выполнялись.  
Реальный smoke на копии корпуса **не** заявлялся — только синтетические fixtures.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/services/bank_materials/event_evidence.py` | Построение query, as_of, вызов `retrieve_bank_fragments` |
| `app/schemas/event_bank_evidence.py` | `EventBankEvidenceOut` / item |
| `app/api/v1/events.py` | `GET /events/{event_id}/bank-evidence` |
| `contracts/openapi.json` | Контракт |
| `docs/MOBILE_API.md` | Секция endpoint |
| `tests/test_event_bank_evidence.py` | Синтетические проверки |
| `docs/EVENT_BANK_EVIDENCE.md` | Этот отчёт |

## Контракт сервиса

```python
collect_event_bank_evidence(session, *, event: Event, limit=10) -> EventBankEvidenceOut
```

1. Строит поисковый запрос из `title`, усечённого `summary`, `category`, `event_type`,  
   `match_categories_json` / `match_countries_json` / `match_currencies_json` / `match_materials_json`.  
   Длина ограничена (`MAX_EVENT_QUERY_CHARS=1200`). Сырой `attributes_json` / payload **не** включается.
2. Берёт серверный OCR scope (`BANK_MATERIALS_ALLOWED_OCR_RUN_IDS`) — клиент scope не задаёт.
3. Вызывает `retrieve_bank_fragments(..., mode="evidence", as_of_date=…)`.
4. Latest revision → eligibility; без fallback к unverified / superseded.
5. Мапит hits в typed evidence items со ссылками на API 2.12.

Hardcode по `event_id`, компании, slug документа или `stable_key` **отсутствует**.

## Источник даты события (временная граница)

| Поле | Роль |
|------|------|
| **`Event.occurred_at`** | Дата/время **новости/события** (то же поле, что сортирует public news). Для MVP as_of = календарный день UTC этой метки. |
| `Event.created_at` | Время записи в БД / импорта — **не** используется. |
| `Event.effective_from` | Опциональное окно действия — **не** используется как дата новости. |
| «Сегодня» / now() | **Запрещено** подменять дату новости. |

Режим MVP: **материалы, опубликованные к дате новости** (`publication ≤ as_of` с правилами day/month/unknown из retrieval).

Если `occurred_at` отсутствует / не даёт календарную дату → статус `event_date_unavailable` (фильтр **не** отключается молча).

Дата материала и дата новости возвращаются **отдельно** (`publication_*` на item vs `event_occurred_at` / `as_of_date` на корне).  
Тематическое совпадение **не** означает, что банк комментировал именно эту новость.

## Статусы

HTTP 200 с полем `status` (кроме auth/ACL/not found):

| status | Смысл |
|--------|--------|
| `available` | Есть ≥1 evidence-фрагмент |
| `no_matching_evidence` | Scope настроен, дата есть, совпадений нет (норма) |
| `integration_not_configured` | Пустой серверный whitelist OCR runs |
| `event_date_unavailable` | Нет надёжной даты новости для as_of |

Технические ошибки retrieval / целостности **не** маскируются под «материалы не найдены» (пробрасываются как AppError / исключения выше).

Событие не найдено → **404** `NOT_FOUND`.  
Без Bearer → **401**.  
Опциональный `company_id` без membership → **403**.

## API

```
GET /api/v1/events/{event_id}/bank-evidence
Authorization: Bearer <access>
?company_id=   # optional; membership only; not used for matching
```

- Авторизация обязательна (банковский корпус не публичный), даже если карточка новости доступна в `/public/news`.
- `EventImpact` **не** требуется.
- Компания для тематического подбора **не** обязательна.
- GET не создаёт impact, чат, связь в БД; не меняет `impact_score` / `confidence` / `assessment_state` / симулятор.

### Item fields (кратко)

- ID: document / file / run / fragment + `revision`
- Название, дата публикации + precision (отдельно от даты новости)
- `page_number`
- `text_kind`: `exact_quote` \| `summary` (+ текст)
- `content_type`
- `qa_method`, `source_role` / `source_role_meaning`
- `match_reasons`, `lexical_match_score` (**не** confidence / качество данных)
- `document_href`, `fragment_href`, `content_href` → существующие endpoints 2.12

Не возвращаются: raw OCR, storage keys, абсолютные пути.

### Пример корня ответа

```json
{
  "event_id": "evt_…",
  "status": "available",
  "event_occurred_at": "2026-09-12T12:00:00Z",
  "as_of_date": "2026-09-12",
  "as_of_date_basis": "event.occurred_at",
  "query_preview": "ЦБ сохранил ключевую ставку …",
  "evidence": [],
  "limitations": [
    "mode_evidence_only",
    "as_of_materials_published_by_event_occurred_at",
    "thematic_match_is_not_bank_commentary_on_this_news",
    "lexical_match_score_is_not_confidence_or_data_quality"
  ],
  "empty_reason": null
}
```

## Выполненные проверки

```bash
python -m pytest tests/test_event_bank_evidence.py \
  tests/test_bank_fragment_retrieval.py \
  tests/test_bank_materials_api.py -q
```

**20 passed** (8 + 6 + 6).

| Проверка | Результат |
|----------|-----------|
| Релевантное событие → verified evidence | OK (synthetic) |
| Нерелевантное → `no_matching_evidence` | OK |
| Пустой scope → `integration_not_configured` | OK |
| Нет даты → `event_date_unavailable` | OK |
| Документ после даты новости исключён | OK |
| Month-precision overlaps as_of → исключён (evidence) | OK |
| Unverified / superseded latest не в новых основаниях | OK |
| Событие без EventImpact | OK |
| 401 / 403(membership) / 404 | OK |
| Ссылки на document/fragment/file API | OK |
| GET не меняет counts Event/Fragment | OK |

Демонстрация — на **временной SQLite + fixtures**. Даты реальных документов и рабочая БД не подгонялись.

## Ограничения

- Нет LLM / чата / UI
- Нет персонализации по компании
- Лексический поиск 2.11: не понимание смысла
- Нет заявления о реальном smoke корпуса на этом этапе

**Стоп этапа 2.13.**
