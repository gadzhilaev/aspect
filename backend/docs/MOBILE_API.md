# Аспект — Mobile API (Flutter)

Базовый URL локально: `http://127.0.0.1:8003`  
Префикс: `/api/v1`  
Формат: JSON · `Accept: application/json` · `Content-Type: application/json`

Полный OpenAPI: `GET /openapi.json` · Swagger: `/docs`

## Auth

| Метод | Путь | Auth |
|---|---|---|
| POST | `/auth/register` | нет |
| POST | `/auth/verify-email` | нет |
| POST | `/auth/login` | нет |
| POST | `/auth/refresh` | нет |
| GET | `/users/me` | Bearer |

## Support chat

| Метод | Путь | Auth |
|---|---|---|
| GET | `/support/thread` | Bearer |
| GET | `/support/thread/messages` | Bearer |
| POST | `/support/thread/messages` | Bearer |
| POST | `/support/thread/close` | Bearer |

`GET /support/thread` — get-or-create открытого диалога (welcome от AI).  
`POST …/messages` body: `{ "content": "…", "client_message_id": "c_…", "company_id": "…" }` →  
user + ответ: сначала FAQ/AI; если AI не уверен — эскалация оператору в Telegram  
(`TELEGRAM_BOT_TOKEN` + `SUPPORT_OPERATOR_CHAT_IDS`). Оператор отвечает  
`/support SUP-XXXXXXXX текст` (нужен polling/webhook бота).  
Роли сообщений: `user` | `support` | `system` | `operator`.  
Поллинг: `GET …/messages?after_id=<last_id>`.

Сроки JWT (серверные defaults, env переопределяет):

| Токен | Default |
|---|---|
| access | `ACCESS_TOKEN_EXPIRE_MINUTES=60` |
| refresh | `REFRESH_TOKEN_EXPIRE_DAYS=14` |

Refresh **есть** в API: body `{ "refresh_token": "<jwt>" }` → новая `TokenPair` (оба токена перевыпускаются). Тип в JWT: `type=access` \| `type=refresh`. Неверный/просроченный refresh → **401** `UNAUTHORIZED`.

**Register** → код на email (в non-production `details.demo_code` при `DEBUG`). Код живёт **1 час**. Повторный email → **409** `CONFLICT`.  
**Verify** до login; без verify login → **403** `EMAIL_NOT_VERIFIED`. Неверный код → **400** `INVALID_CODE`.

**Login request** (синтетический пример)

```json
{ "email": "user@example.com", "password": "<password>" }
```

**Login / refresh response**

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer"
}
```

**Обязательный заголовок** на защищённых маршрутах:

```
Authorization: Bearer <access_token>
```

`GET /users/me` возвращает компании пользователя и `preferences`:

```json
{
  "id": "usr_demo_owner",
  "email": "demo@kontur.app",
  "display_name": "Демо Владелец",
  "preferences": { "language": "ru", "theme_mode": "system" },
  "companies": [
    {
      "company_id": "cmp_severprom",
      "role": "owner",
      "name": "СеверПром",
      "profile_status": "ready"
    }
  ]
}
```

`profile_status`: `draft` | `ready` (и др.). При `draft` ведите в company setup.

### Mobile account endpoints

| Метод | Путь | Auth | Примечание |
|---|---|---|---|
| PATCH | `/users/me/preferences` | Bearer | Частичный patch: `language`=`ru\|en`, `theme_mode`=`light\|dark\|system`. Остальные ключи prefs сохраняются. |
| POST | `/users/me/change-password` | Bearer | `current_password`, `new_password` (min 8). JWT не revoke’ятся сервером до expiry — клиент чистит токены. |
| DELETE | `/users/me` | Bearer | Body `{ "password": "..." }`. **409** `SOLE_OWNER` если единственный owner компании. **409** `HAS_AUDIT_RECORDS` если есть decisions/scenarios created_by. Компании других участников не удаляются. |

## ACL

Почти все company/event/decision/assistant вызовы требуют членства в компании (`require_company_member`).

- Чужой `company_id` → **403** `FORBIDDEN`
- Несуществующий ресурс → **404** `NOT_FOUND`
- Без токена / просроченный access → **401** (обновите через `/auth/refresh`)

Всегда передавайте `company_id` своей компании (query или body — как в контракте эндпоинта).

## Bank materials (read-only)

Авторизованный доступ к общему банковскому корпусу в **серверной** области OCR run ID.
Поиск / ассистент / UI на этом этапе не подключены. Контекст компании/события не используется.

| Метод | Путь | Auth |
|---|---|---|
| GET | `/bank-materials/documents/{document_id}` | Bearer |
| GET | `/bank-materials/fragments/{fragment_id}` | Bearer |
| GET | `/bank-materials/files/{file_id}/content` | Bearer |

Сервер: `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS` (comma/pipe) + `BANK_MATERIALS_STORAGE_ROOT`.  
Пустой список run ID → **503** `BANK_MATERIALS_NOT_CONFIGURED`.  
Клиент **не** расширяет scope передачей run/document/file ID вне разрешённой области → **404** `NOT_FOUND`.

Правила текста фрагмента:

- `exact_quote` — только `verified_transcript` при `eligible_exact_quote`;
- `summary` — явный пересказ, не цитата;
- неподтверждённый — `text_kind=restricted`, `text=null`, причины в `restriction_reasons` (raw OCR не отдаётся как цитата).

Историческая revision доступна по точному `fragment_id` с `is_superseded=true` (без тихого redirect на latest).

PDF: `Content-Type: application/pdf`, безопасный `Content-Disposition`.  
Ошибки файла: `BANK_FILE_UNAVAILABLE` (404), `BANK_FILE_INTEGRITY` (409).  
В JSON/ошибках нет абсолютных путей и `storage_key`. GET не пишет в БД.

Подробности: `docs/BANK_MATERIALS_API.md`.

### Bank evidence for an event

| Метод | Путь | Auth |
|---|---|---|
| GET | `/events/{event_id}/bank-evidence` | Bearer |

Тематические **проверенные** банковские фрагменты к новости (`mode=evidence`).  
Не персональный вывод о компании; `EventImpact` не требуется.  
Опциональный `company_id` — только для membership-проверки, не для тематики.

Временная граница: `Event.occurred_at` (дата новости), не «сегодня» и не `created_at`.  
Статусы: `available` \| `no_matching_evidence` \| `integration_not_configured` \| `event_date_unavailable`.  
Совпадение темы ≠ «банк комментировал именно эту новость».  
GET не создаёт impact/чат/связи и не меняет scores.

Подробности: `docs/EVENT_BANK_EVIDENCE.md`.

## Company setup

| Метод | Путь |
|---|---|
| GET | `/industries` |
| POST | `/companies` |
| GET | `/companies/{id}/profile` |
| GET | `/companies/{id}/context` |
| GET | `/companies/search?q=` |
| POST | `/company-registry/lookup` |
| POST | `/company-registry/confirm` |

`GET /companies/search?q=` ищет **только свои** компании пользователя (по названию/ИНН
среди его membership). Это **не** публичный каталог: карточки чужих компаний не раскрываются.
Для публичных реквизитов реальной организации используйте `/company-registry/lookup`.

## Поиск компании по ИНН (внешний справочник)

Поток: пользователь вводит ИНН → `POST /company-registry/lookup` → сервер делает один
запрос к реальному реестру → возвращает кандидатов и короткоживущий `lookup_id` →
пользователь выбирает запись → `POST /company-registry/confirm` сохраняет реквизиты
в **его собственный** профиль компании.

**Источник:** DaData findById/party (публичные сведения ЕГРЮЛ/ЕГРИП ФНС через посредника).
Это **не** прямой запрос в ФНС и **не** подтверждение, что компания принадлежит пользователю.

`POST /company-registry/lookup` — Bearer. Тело: `{ "inn": "7707083893" }` (только ИНН, не URL).
ИНН — строка (ведущие нули сохраняются): 10 цифр — юрлицо, 12 — ИП/физлицо, с проверкой
контрольных разрядов. Ответ (`status` ∈ `ok` | `not_found` | `not_configured`):

```json
{
  "status": "ok",
  "query_inn": "7707083893",
  "lookup_id": "<uuid>",
  "expires_at": "2026-10-24T12:15:00+00:00",
  "source": { "provider": "dadata", "title": "DaData · данные ЕГРЮЛ/ЕГРИП ФНС России",
              "note": "Публичные реестровые сведения через посредника DaData. Это не прямой запрос в ФНС и не подтверждение полномочий." },
  "retrieved_at": "2026-10-24T12:00:00+00:00",
  "source_actuality_date": "2026-02-24",
  "candidate_count": 1,
  "candidates": [
    { "candidate_id": "0", "org_type": "legal", "inn": "7707083893", "kpp": "770701001",
      "ogrn": "1027700132195", "ogrn_date": "2002-09-24", "name_short": "ООО \"ПРИМЕР\"",
      "name_full": "…", "region": "г Москва", "okved": "26.30", "okved_name": "…",
      "status": "active", "status_label": "Действующая", "is_active": true,
      "branch_type": "main", "suggested_industry": "electronics" }
  ],
  "note": null
}
```

- Отсутствующие значения — `null` (КПП у ИП нет, ОГРН у ИП — это ОГРНИП). Поля не выдумываются.
- `retrieved_at` — время **нашего** запроса, **не** дата обновления реестра (`source_actuality_date`).
- `suggested_industry` — грубая подсказка по ОКВЭД, **не** применяется автоматически (ОКВЭД ≠ отрасль).
- `is_active=false` / `status=liquidated|bankrupt|…` показывайте явно (недействующая организация).
- Несколько кандидатов (головная + филиалы) — не выбирайте первого молча, дайте выбрать.

Ошибки lookup (envelope `{ "error": { "code", "message", "details" } }`):

| HTTP | code | Когда |
|---|---|---|
| 400 | `INVALID_INN` | плохой ИНН (`details[0].reason` = `empty`/`non_digit`/`bad_length`/`bad_checksum`) |
| 429 | `RATE_LIMITED` | слишком часто (наш per-user лимит) |
| 504 | `REGISTRY_TIMEOUT` | источник не ответил вовремя |
| 503 | `REGISTRY_UNAVAILABLE` | источник недоступен / 5xx |
| 503 | `REGISTRY_AUTH_ERROR` | проблема ключа у **источника** — **не** разлогинивает пользователя |
| 503 | `REGISTRY_UPSTREAM_RATE_LIMITED` | источник ограничил частоту |
| 502 | `REGISTRY_BAD_RESPONSE` | источник вернул некорректный ответ |

Важно: ошибка источника **не** превращается в «компания не существует» и не отдаёт сырой
ответ/секрет провайдера. `status=not_configured` (ключ не задан) — заполняйте вручную.

`POST /company-registry/confirm` — Bearer. Тело: `{ "lookup_id": "<uuid>", "candidate_id": "0" }`.
Серверное подтверждение: клиент **не** может подделать «получено из справочника», прислав
`provider`/`source` в JSON — доверяется только `lookup_id` (короткоживущий, привязан к пользователю).

```json
{
  "company": { "id": "…", "name": "ООО \"ПРИМЕР\"", "tax_id": "7707083893", "industry": null, "role": "owner", "…": "…" },
  "created": true,
  "opened_existing": false,
  "applied_fields": ["legal_name", "name", "tax_id"],
  "suggested_industry": "electronics",
  "source": { "provider": "dadata", "title": "…", "note": "…" },
  "note": "Создан ваш рабочий профиль по публичным реквизитам. Это не подтверждение владения компанией."
}
```

- `created=true` — создан ваш профиль (membership `owner`). `opened_existing=true` — у вас уже был
  профиль с этим ИНН, открыт он (дубликат не создан). Чужую Company знание ИНН **не** открывает.
- confirm **не** создаёт case-link, Impact, Scenario, Decision и **не** трогает поставщиков/рынки/
  валюты/финансы/цепочки — только реквизиты (`name`, `legal_name`, `tax_id`, `hq_region`).
- Если позже отредактировать поле (`PATCH /companies/{id}`), оно перестаёт считаться «из реестра»
  (переходит в `fields_overridden_manually` в provenance).

Ошибки confirm: `404 LOOKUP_NOT_FOUND` (нет/чужой/протух `lookup_id`), `410 LOOKUP_EXPIRED`,
`404 CANDIDATE_NOT_FOUND`.

Provenance виден в `GET /companies/{id}/profile` → `settings.preferences.registry_provenance`
(`fields_from_registry`, `fields_overridden_manually`, `source`, `verified_scope="public_requisites"`).
Подтверждены только публичные реквизиты — **не** вся компания и **не** полномочия пользователя.

Подробности: `docs/COMPANY_INN_LOOKUP.md`.

`GET /companies/{id}/context` — read-only бизнес-контекст для страницы `/company`
(человеческие лейблы, категории мониторинга, карта влияния, покрытие, пример impact).
Только для участника компании (ACL).

Аддитивное поле `case_context` (конкурсный слой). Старые поля **не** меняются:
ручная отрасль/размер не подменяются данными кейса. `slot_key` задаётся только
сервером (`CASE_CONTEXT_SLOT_KEY`); клиент slot не передаёт. GET не пишет в БД,
не создаёт привязку и не считает impact.

Статусы `case_context.status`:

| status | Смысл |
|---|---|
| `integration_not_configured` | Слот на сервере не задан |
| `not_linked` | Компания не привязана к `U_*` |
| `no_active_snapshot` | Нет активного снимка слота |
| `uid_missing_in_snapshot` | Привязанный U нет в active; данные старого снимка не подставляются |
| `profile_absent` | Org есть, каталожного профиля нет |
| `profile_available` | Профиль доступен (`profile` заполнен) |

Продукты: `true` \| `false` \| `unknown` \| `conflict` (false ≠ unknown).  
Факторинг — отдельное поле `profile.factoring` с `explanation`.  
Выручка: `amount` строкой без потери точности; `unit`/`currency` обычно null; не рубли.  
ФТС: только raw страны, без направления торговли. Группа — только свой `external_group_id`.

Примеры `case_context`:

```json
{
  "status": "profile_available",
  "explanation": "Доступен профиль конкурсной организации из активного снимка. Ручные поля компании не заменяются.",
  "slot_key": "competition_default",
  "external_uid": "U_123",
  "snapshot_id": "…",
  "version_label": "hack-raw-v1",
  "profile": {
    "okved_code": { "key": "mainokved_code", "status": "confirmed", "value": "46.90" },
    "city": { "key": "city", "status": "conflict", "value": null },
    "products": [
      { "code": "RKO", "label": "Расчётно-кассовое обслуживание", "status": "true" },
      { "code": "GAR", "label": "Банковские гарантии", "status": "unknown" }
    ],
    "factoring": {
      "status": "true",
      "explanation": "В каталоге отмечено наличие факторинга. Сумма, ставка и условия договора неизвестны."
    },
    "conflicts": { "city": { "reason": "divergent_values", "values": ["Москва", "Казань"] } }
  }
}
```

```json
{ "status": "not_linked", "explanation": "Компания не привязана к организации конкурсного справочника в этом слоте.", "profile": null }
```

```json
{
  "status": "profile_available",
  "profile": {
    "city": { "status": "conflict", "value": null },
    "okved_code": { "status": "confirmed", "value": "46.90" }
  }
}
```

| PATCH | `/companies/{id}` |
| POST | `/companies/{id}/nodes` |
| PATCH | `/companies/{id}/nodes/{node_id}` |
| POST | `/companies/{id}/edges` |
| PATCH | `/companies/{id}/finance` |
| GET | `/companies/{id}/industry-profile` |
| PATCH | `/companies/{id}/industry-profile` |
| POST | `/companies/{id}/profile/complete` |
| POST | `/companies/{id}/digital-twin/build` |
| GET | `/companies/{id}/dashboard` |

Типичный онбординг: create → patch basics/role/geo → nodes/edges → optional finance → complete → digital-twin/build.

Финансы для макро/FX — готовность **по track** (этап 5.5):

- **Rate:** `debt_amount` + `floating_rate_share_percent` (+ опционально `debt_amount_unit`)
- **FX:** `fx_exposure_amount` + `fx_exposure_currency` + `fx_exposure_direction` + `fx_quote_currency`
- Ликвидность (`near_term_payments_90d`, `fx_purchase_volume`, `cash_reserve_days`) — опционально, не обязательна для FX

`finance_ready` = rate **или** FX профиль готов. Денежный сценарий всё ещё требует основание события / what-if.

`PATCH /companies/{id}/finance`: `optional_finance` **merges** (ключ отсутствует → сохранить; `null`/`""` → очистить знание; `0` → известный ноль).  
Смена FX-пары без явного `fx_rate_from` в том же PATCH очищает сохранённый курс (сервер, не только web).  
Legacy `fx_purchase_volume` без валюты **не** мигрирует в `fx_exposure_amount`.  
Подробности: `docs/FINANCE_SETUP_RATE_FX.md`, E2E: `docs/FINANCE_RATE_FX_E2E.md`.

### Industry profile (electronics v1)

`GET|PATCH /companies/{id}/industry-profile` — бренды, категории, линейки, рынки продаж, география закупок.  
Хранится в `preferences.industry_profile` (не затирает case/registry).  
Лента: `score_kind=industry_profile_match` — тематика без `EventImpact` и без денежного score; Telegram не расширяется.  
См. `docs/INDUSTRY_NEWS_PERSONALIZATION.md`.

## News / For you

**Публично (без auth):**

| Метод | Путь |
|---|---|
| GET | `/public/news` |
| GET | `/public/news/{event_id}` |
| GET | `/public/categories` |
| GET | `/public/trending` |
| GET | `/public/ingestion-status` |

`GET /public/news` — query: `category`, `event_type`, `cursor` (ISO datetime `occurred_at`), `limit` 1…50.  
Ответ: `items`, `next_cursor`, `limit`, опционально `ingestion` (снимок scheduler; без путей БД/секретов).  
`severity` события в публичной карточке — через `severity_label` (строка); числовой severity на карточке публичной ленты не обязателен.  
На `EventDetail` / impact-моделях `severity` может быть **`null`** (неизвестная тяжесть ≠ 0).

`GET /public/ingestion-status` — когда источники последний раз проверялись: `status` (`success`\|`partial`\|`failed`\|`running`\|`skipped_busy`\|null), `sources_checked_at`, `sources_check_ok`, `last_success_at` (только полный success), `counts`, `source_errors` (безопасные коды). **partial/failed не равны успешному обновлению.**

**После входа — персональная лента:**

`GET /companies/{company_id}/dashboard` — счётчики + `priority_events`
(расчёт влияния **и** совпадения с конкурсным профилем без обязательного Impact).

Сортировка персональной ленты (dashboard / `GET .../events` без `status`):

1. группа `company_calculated`;
2. группа `event_severity_signal`;
3. группа `case_profile_match` (связь с профилем, **не** расчёт);
4. внутри impact-групп — `impact_score DESC`; внутри `case_profile_match` — `occurred_at DESC`;
   tie-break `event_id ASC`.

Основания **не** сравниваются одним числом. Поле `feed_sort_rule` описывает правило.  
Cursor: `{group}:{sort_key}:{event_id}` (некорректный → 422).  
Одна новость — один раз; при impact + профиле объяснения профиля аддитивны (`profile_relevance`, `inclusion_bases`).  
Статус `not_relevant` не попадает в ленту по умолчанию (история не удаляется).  
Счётчик `profile_match` — число карточек только по профилю.  
GET ленты / dashboard **не** создаёт Impact / Scenario / Decision (нет lazy recompute).  
Явный пересчёт: `POST /companies/{id}/digital-twin/build`, `POST /events/{id}/recompute-impact`.

Аддитивные / уточнённые поля карточки (`EventCardOut`):

| Поле | Смысл |
|------|--------|
| `impact_score` | `number \| null` — известная оценка (0 — известный ноль); `null` если оценки нет |
| `impact_score_available` | `false` ⇒ нет оценки (`impact_score` null); не показывать как 0 |
| `inclusion_bases` | `calculated_impact` \| `event_severity_signal` \| `case_profile` |
| `profile_relevance` | объяснение + provenance снимка; `null` если нет совпадения |
| `score_kind=case_profile_match` | «По профилю компании»; `impact_score=null`, `available=false` |

Подробности: `docs/CASE_PERSONALIZED_FEED.md`, `docs/CASE_PERSONALIZED_FEED_CONTRACT_FIX.md`.

Web-маршрут: `/news/for-you`.

`GET /events/{event_id}/relevance?company_id=` — объяснение релевантности twin **без** создания `EventImpact` (GET без побочных эффектов).  
Аддитивно также в `EventDetailOut.relevance`.

## Event impact и assessment states

`GET /events/{event_id}/impact?company_id=...`

Ключевые поля `ImpactOut`:

| Поле | Смысл |
|---|---|
| `assessment_state` | Режим оценки |
| `finance_setup_href` | CTA, если нужны финансы |
| `impact_score` | Число 0…100 или `null` (нет оценки). Известный 0 ≠ null. Смысл числа зависит от `score_kind` |
| `score_kind` / `score_kind_label` | `company_calculated` \| `event_severity_signal` \| `case_profile_match` \| `unavailable` |
| `confidence` | Эвристика качества данных 0…1 (не вероятность) |
| `paths` | Цепочка влияния |
| `reason_summary` | Человеческое объяснение |
| `assessment_explanation` | Снимок основания («Как рассчитано») |
| `metric_labels` | Короткие лейблы для UI |

### `score_kind` (аддитивно, рекомендуется для новых клиентов)

| Значение | Лейбл | Ограничение |
|---|---|---|
| `company_calculated` | Индекс влияния | Персональный индекс по twin + доля выпуска |
| `event_severity_signal` | Сигнал события | Placeholder/triage от severity; **не** персональный расчёт и не финэффект |
| `case_profile_match` | По профилю компании | Совпадение темы события с отметкой продукта в case_context; **не** расчёт влияния |
| `unavailable` | Оценка недоступна | Числа нет / неприменимо |

Поле `impact_score` сохранено для совместимости и **сортировки ленты** (`impact_score DESC`). Смешанные kind в одной ленте — triage, не равная обоснованность оценок. Web читает `score_kind` / `metric_labels`.

### exposure

- объект отсутствует / `null` → доля неизвестна или неприменима;
- `value: 0` → известный ноль;
- `value > 0` → известная положительная доля.

### `assessment_state`

| Значение | UI |
|---|---|
| `supply_chain_ready` | Полный разбор + сценарии (`score_kind=company_calculated`) |
| `finance_data_required` | CTA «Настроить финансовый контекст»; `score_kind=event_severity_signal` |
| `finance_ready` | Макро/FX с финансами; `impact_score` — сигнал события, сценарии — отдельно |
| `monitoring_only` | Только мониторинг; число в ленте — сигнал события |
| `calculation_unavailable` | Нет usable `EventImpact` (отсутствует или `not_relevant`); **не** то же, что `monitoring_only`; обсуждение события возможно, численные сценарии — нет |

### Финансовые rate-сценарии (этап 5.2)

Денежная чувствительность к **ключевой ставке** строится только из:

- **observed** Δ п.п. (доверенные `rate_decision_status` + `rate_from`/`rate_to` или надёжный текст решения о сохранении), либо
- явного **assumed** `assumed_rate_change_pp` (what-if).

`severity` **не** является Δ ставки. При отсутствии оснований tool `compare_scenarios` возвращает `missing_data` / пустые `scenarios` (не три фиктивных числа).

В `Scenario.parameters_json` (аддитивно):

| Поле | Смысл |
|---|---|
| `rate_change.basis` | `observed` \| `assumed` \| `none` \| `conflict` |
| `rate_change.observed_delta_pp` / `assumed_delta_pp` / `used_delta_pp` | п.п.; факт и допущение раздельно |
| `debt_amount_unit` | `unspecified` или явная валюта профиля; **не** подразумевать ₽ |
| `shock_proxy_pp` | в новых расчётах `null` (legacy severity-proxy не использовать как observed) |

`results_json` rate-track: `annual_rate_sensitivity`, `rate_change_basis`; near-term severity-proxy отключён.  
`results_json` FX-track (`track=fx`): `fx_change_basis`, `fx_value_change`, пара/направление/период — см. `docs/FX_SCENARIO_BASIS_FIX.md`.  
Старые Scenario без typed basis **не** пересчитываются и **не** помечаются observed.  
Подробности rate: `docs/RATE_SCENARIO_BASIS_FIX.md`.

### Presentation contract (этапы 5.3–5.4)

Аддитивное поле `presentation` на:

- каждой строке `scenario_comparison.scenarios[]`;
- `GET /scenarios/{id}`;
- `DecisionDetail.scenario.presentation`.

| Поле | Смысл |
|---|---|
| `track` | `rate` \| `fx` |
| `basis` | `observed` \| `assumed` \| `none` \| `conflict` \| `legacy` |
| `rate_fact_line` / `what_if_line` / `money_line` | раздельные формулировки (rate ≠ FX copy) |
| `fx_pair_line` / `fx_amount_line` / `fx_period_line` / `fx_value_change` | FX-ветка |
| `assumption_badge` | «Допущение сценария» / прежняя модель |
| `debt_amount_unit` / `debt_unit_confirmed_rub` | rate: ₽ только при подтверждённом RUB |
| `decision_horizon` | rate: условный годовой; FX: период экспозиции или «Период не указан» |
| `historical_note` | legacy без пересчёта |

`PATCH /companies/{id}/finance`: merge `optional_finance` (null очищает; 0 — известный ноль). Setup собирает rate и FX секции независимо.  
Подробности: `docs/FINANCE_SCENARIO_PRESENTATION.md`, `docs/FX_SCENARIO_BASIS_FIX.md`, `docs/FINANCE_SETUP_RATE_FX.md`.

Демо: `evt_china_export_001` + `cmp_severprom` → `supply_chain_ready` (единая формула, без скрытого ×3.5).

## Assistant

| Метод | Путь |
|---|---|
| POST | `/events/{event_id}/assistant/conversations?company_id=` |
| GET | `/assistant/conversations?company_id=` |
| GET | `/assistant/conversations/{id}` |
| GET | `/assistant/conversations/{id}/messages` |
| POST | `/assistant/conversations/{id}/messages` |
| POST | `/assistant/conversations/{id}/compare-scenarios` |
| POST | `/assistant/conversations/{id}/draft-decision` |

**Пользовательский расчёт сценариев (этап 6.6):**  
`POST …/compare-scenarios` — явный запуск finance/supply без LLM и без write-tools agent loop.  
Обязателен `client_request_id` (повтор с теми же параметрами → reused; с другими → 409  
`USER_COMPARE_REQUEST_CONFLICT`). What-if: `assumed_rate_change_pp` (п.п.),  
`assumed_fx_change_percent` (%). Decision **не** создаётся — далее draft-decision.  
Ответ может содержать system-сообщение «Расчёт по вашему запросу» (не AI).  
Подробности: `docs/USER_TRIGGERED_FINANCE_SCENARIOS.md`.

Обсуждение **не** требует `EventImpact` (этап 3.2). Аддитивные поля:

- `AssistantConversationOut.assessment_state`, `has_impact_calculation`
- `AssistantConversationListItem.has_impact_calculation`, `assessment_state`
- `impact_score` / `confidence` в списке остаются nullable: при отсутствии расчёта — `null` (не `0`). Известный ноль в расчёте по-прежнему `0`.

При `calculation_unavailable` draft-decision → HTTP 409 `CALCULATION_UNAVAILABLE`.  
Подробности: `docs/ASSISTANT_WITHOUT_IMPACT.md`.

Сообщения содержат `blocks` (сценарии, action_plan_draft, источники и т.д.).

Типы блоков: `impact_summary` | `claim_list` | `scenario_comparison` | `missing_data` |
`action_plan_draft` | `source_list` | `bank_evidence_list` | `case_context_ref`.

`bank_evidence_list` — тематические материалы банка к событию обсуждения (этап 2.14):
только **проверенные** фрагменты, прошедшие серверную валидацию цитат; label `bank_material`.
Старые клиенты могут игнорировать неизвестный тип. Подробности: `docs/ASSISTANT_BANK_EVIDENCE.md`.

`case_context_ref` — минимальная привязка ответа к конкурсному контексту компании (этап 3.1):
`snapshot_id`, статус, источник; без полного профиля. Label `company_context`.
Подробности: `docs/ASSISTANT_CASE_CONTEXT.md`.

**Draft / confirm**

```json
{
  "scenario_id": "<uuid>",
  "solution_id": "sol_thailand_a",
  "note": "Снизить риск остановки Линии №2",
  "confirm": false,
  "client_request_id": "draft-..."
}
```

`confirm: true` создаёт `Decision` + action items (идемпотентно по ключу). В ответе: `status`, `decision_id`.

Провайдер на сервере: `ASSISTANT_PROVIDER=mock|openai|gigachat|hackathon` (`live` — устаревший alias для `openai`).  
Ключи OpenAI / GigaChat / hackathon **не** отдавать в мобильное приложение и не класть в клиентский env.  
`answer_basis` может быть `ai_explain_hackathon`; опционально `answer_model` — фактический model id.

Опционально (серверный флаг, default off): `ASSISTANT_AGENT_LOOP=true` включает многошаговый
read-only цикл **только** с `ASSISTANT_PROVIDER=hackathon`. Контракт ответа при успехе тот же
(`PostMessageOut`); незавершённый разбор — ошибка envelope (`ASSISTANT_LOOP_*`), не successful
final. Повтор того же `client_message_id` после stop снова отдаёт ошибку (`details.reused`),
не 200-final. Тот же id + другой текст → `ASSISTANT_MESSAGE_ID_CONFLICT`.
Подробности: `docs/ASSISTANT_AGENT_API_INTEGRATION.md`, `docs/ASSISTANT_AGENT_REPLAY_FIX.md`.

## Scenarios / solutions

| Метод | Путь |
|---|---|
| GET | `/events/{event_id}/solutions?company_id=` |
| POST | `/events/{event_id}/simulate?company_id=` |
| GET | `/scenarios/{scenario_id}` |

Симулятор детерминирован (`model_version`). Список обсуждений со статусом решения — через assistant conversations list (web: `/scenarios`).

## Decisions и action items

| Метод | Путь |
|---|---|
| GET | `/decisions/{decision_id}` |
| GET | `/events/{event_id}/decision?company_id=` |
| POST | `/decisions` |
| POST | `/decisions/{id}/cancel` |
| POST | `/decisions/{id}/action-items` |
| PATCH | `/action-items/{id}` |

`GET /events/{event_id}/decision` возвращает только **активное подтверждённое** решение
(`status` ∈ `selected|confirmed|accepted|done`), сортировка `created_at DESC, id DESC`.
Черновики и **отменённые** (`cancelled`) не отдаются (404) — карточка события/impact
ведёт к ассистенту/сценариям, а не на неактивный план.

**Отмена плана** (`POST /decisions/{id}/cancel`):

```json
{ "reason": "опционально" }
```

Статус становится `cancelled` (`status_label`: «План отменён»). Decision / action items /
история assistant **не удаляются**. Повторная отмена идемпотентна. PATCH action item
после отмены — `409`.

**PATCH action item**

```json
{ "status": "done" }
```

Допустимые статусы: `todo` | `in_progress` | `done`.

Ответ включает `progress: { done, total, label }` и человеческие `status_label` («Запланировано», «В работе», «Выполнено»).

Detail решения содержит: title, summary, expected_effect, horizon, confidence, event, scenario, action_items, `news_href`, `conversation_href` — без сырого JSON для UI.

## Telegram (pairing / test / settings)

| Метод | Путь | Auth |
|---|---|---|
| GET | `/companies/{company_id}/notification-settings` | Bearer |
| POST | `/telegram/link-token` | Bearer |
| POST | `/telegram/groups/link-token` | Bearer |
| POST | `/telegram/test-send` | Bearer |
| GET | `/telegram/outbox/{outbox_id}` | Bearer |
| PATCH | `/notification-subscriptions/{subscription_id}` | Bearer |
| DELETE | `/notification-subscriptions/{subscription_id}` | Bearer |
| POST | `/telegram/webhook` | secret header (бот, не мобильный UI) |

Personal bind: `link-token` → deep-link `/start <token>` в боте → polling или webhook на сервере.  
`test-send` — очередь `kind=test`, cooldown на подписку; идемпотентность через `client_request_id` (если передан).  
Авто-news (`kind=news`) — серверный флаг + eligibility/watermark; клиент **не** шлёт произвольный текст в Telegram.  
В ответе settings: `news_notifications_server_enabled`, `news_policy_note`.  
Публичная кнопка «Открыть разбор» требует `PUBLIC_WEB_BASE_URL` (HTTPS); localhost в кнопку не подставляется.

Подробности: `docs/TELEGRAM_LINK_AND_TEST.md`, `docs/TELEGRAM_NEWS_POLICY.md`, `docs/TELEGRAM_NEWS_LIVE_E2E.md`.

## Ошибки

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Нет доступа к этой компании",
    "details": []
  }
}
```

Типичные HTTP: **401** auth, **403** membership / email, **404** нет ресурса / нет usable Impact, **409** конфликт идемпотентности / integrity, **422** валидация / плохой cursor, **503** интеграция не сконфигурирована (банк, иногда assistant).

## Demo identifiers (локальный seed, не прод)

| Что | Значение |
|---|---|
| User | `demo@kontur.app` (пароль — только локальный seed / `demo_password.local`, не в клиентский билд) |
| Company | `cmp_severprom` |
| China event | `evt_china_export_001` |

Секреты и токены в репозиторий и клиентские билды не класть. Live AI — только server-side env.  
Подключение Flutter к этому backend **в данном пакете не прогонялось** — см. `docs/MOBILE_BACKEND_HANDOFF.md`.
