# Handoff: backend → мобильный разработчик

Дата: **2026-10-24**  
Контракт: `contracts/openapi.json` (сгенерирован из текущего FastAPI) · обзор: [`MOBILE_API.md`](MOBILE_API.md)  
**Flutter-подключение в этом пакете не прогонялось** — ниже контракт API и рекомендуемый порядок экранов.

Базовый URL публичного размещения: **будет задан после размещения**.  
Локально для web/demo часто `:8003` / стенды `:8018` / `:8020` — не путать с продом.

Префикс: `/api/v1`. JSON. `Authorization: Bearer <access_token>` на защищённых маршрутах.

---

## 1. Порядок подключения экранов

1. Splash / session — access JWT; при 401 → `POST /auth/refresh`; снова 401 → login.  
2. Auth — register → verify-email → login.  
3. Company picker — `GET /users/me` → список `companies[]`; иначе create/setup.  
   Онбординг компании: ввод ИНН → `POST /company-registry/lookup` → выбор записи →
   `POST /company-registry/confirm` (создаёт собственный профиль из публичных реквизитов;
   знание ИНН доступ к чужой компании не даёт). Детали: [`COMPANY_INN_LOOKUP.md`](COMPANY_INN_LOOKUP.md).  
4. Home / For you — `GET /companies/{id}/dashboard` (+ optional events list).  
5. Public news hub — `GET /public/news` (+ `ingestion` / `GET /public/ingestion-status`).  
6. Event detail — `GET /events/{id}` (+ relevance, bank-evidence).  
7. Impact — `GET /events/{id}/impact` (**404** = нет usable расчёта, не «оценка 0»).  
8. Assistant — создать/открыть conversation → messages (без обязательного Impact).  
9. Finance setup — `PATCH …/finance` → `POST …/recompute-impact` → `POST …/compare-scenarios`.  
10. Draft → confirm decision.  
11. Bank PDF — fragment → `GET /bank-materials/files/{file_id}/content`.  
12. Notifications (опционально) — settings → link-token → test-send.

---

## 2. Экран → endpoint → состояния

| Экран | Endpoint(s) | Состояния UI |
|-------|-------------|--------------|
| Login | `POST /auth/login` | 401 credentials; 403 email not verified |
| Register / OTP | `POST /auth/register`, `/auth/verify-email` | 409 email exists; 400 bad/expired code |
| Session refresh | `POST /auth/refresh` | 401 invalid refresh |
| Me / companies | `GET /users/me` | empty companies → onboarding |
| Create company | `POST /companies` | 403/422 validation |
| Поиск по ИНН | `POST /company-registry/lookup` → `/confirm` | 400 INVALID_INN; not_found/not_configured; 503/504 источник; 429 rate; confirm 404/410 |
| Company setup | profile, nodes, edges, finance, complete, digital-twin/build | `profile_status` draft\|ready |
| Case context | `GET /companies/{id}/context` | `case_context.status` (see MOBILE_API) |
| For you | `GET …/dashboard`, `GET …/events` | empty feed vs error; `score_kind` groups |
| Public feed | `GET /public/news` | cursor page; empty items OK |
| News freshness | `ingestion` on news **or** `/public/ingestion-status` | success vs partial/failed/running |
| Event | `GET /events/{id}` | 404 |
| Impact | `GET /events/{id}/impact` | 404 = calculation_unavailable path |
| Discuss w/o impact | assistant conversations/messages | `assessment_state`, `has_impact_calculation` |
| Agent errors | `POST …/messages` | `ASSISTANT_LOOP_*` envelope; retry w/ **new** id after stop |
| Compare | `POST …/compare-scenarios` | needs `client_request_id`; 409 conflict |
| Draft/confirm | `POST …/draft-decision` | 409 CALCULATION_UNAVAILABLE; confirm idempotent |
| Bank evidence | `GET /events/{id}/bank-evidence` | available / no_matching / not_configured |
| Bank PDF | `GET /bank-materials/files/{id}/content` | 503 not configured; 404/409 file |
| Telegram | notification-settings, link-token, test-send, outbox | disconnected / connected; server news flag |

---

## 3. Минимальные примеры (синтетика)

### Login

`POST /api/v1/auth/login`

```json
{ "email": "user@example.com", "password": "<password>" }
```

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer"
}
```

Defaults TTL: access **60 min**, refresh **14 days** (env).

### Refresh

`POST /api/v1/auth/refresh` — `{ "refresh_token": "<jwt>" }` → новая пара.

### Public news page

`GET /api/v1/public/news?limit=20`

```json
{
  "items": [],
  "next_cursor": null,
  "limit": 20,
  "ingestion": {
    "status": "partial",
    "sources_checked_at": "2026-10-24T12:00:00Z",
    "sources_check_ok": false,
    "last_success_at": null,
    "counts": { "fetched": 0, "inserted": 0, "duplicates": 0, "published": 0 },
    "source_errors": ["gdelt:query:http_429"]
  }
}
```

### Impact missing vs zero

- **404** на `/impact` → нет usable Impact (обсуждение всё равно можно открыть).  
- `impact_score: 0` + `impact_score_available: true` на карточке ленты → **известный ноль**.  
- `impact_score: null` + `available: false` → оценки нет (не рисовать «0»).  
- `score_kind=case_profile_match` → «по профилю», не персональный индекс.

### Post message (idempotent)

```json
{
  "content": "Как это влияет на поставки?",
  "client_message_id": "msg-client-001"
}
```

Тот же id + тот же текст после ошибки loop → снова ошибка с `details.reused`, **не** silent 200-final.  
Тот же id + другой текст → conflict. Новый пользовательский retry → **новый** `client_message_id`.

### Compare scenarios

```json
{
  "client_request_id": "cmp-001",
  "assumed_rate_change_pp": 1.0
}
```

Повтор тех же параметров → reused; другие параметры + тот же id → **409**.

---

## 4. HTTP / сеть

| Код | Действие клиента |
|-----|------------------|
| 401 | refresh; если fail → login |
| 403 | показать запрет (membership / email) |
| 404 | empty/not found UI (Impact 404 ≠ crash) |
| 409 | не ретраить слепо тем же телом; показать конфликт / reused |
| 422 | исправить ввод / cursor |
| 503 | «интеграция не настроена» (банк и т.п.) |
| timeout / network | ретрай **безопасных GET**; для POST с id — только тот же idempotency key, не новый дубль решения |

---

## 5. Повторы без дублей

| Операция | Ключ |
|----------|------|
| Assistant message | `client_message_id` |
| Compare scenarios | `client_request_id` |
| Draft / confirm decision | `client_request_id` |
| Telegram test-send | `client_request_id` (если передаёте) |

Не создавать второе decision/confirm при повторе того же ключа.  
Agent-loop stop → следующий ручной retry с **новым** message id.

---

## 6. Пусто / неизвестно / ошибка

| Ситуация | Как отличить |
|----------|----------------|
| Пустая лента | `200` + `items: []` / empty dashboard reason |
| Нет оценки | `impact_score` null / `available=false` / Impact **404** |
| Известный ноль | numeric `0` + available |
| Ошибка | envelope `error.code` + HTTP ≥400 |
| News check partial | `ingestion.status=partial`, `last_success_at` может быть null |

---

## 7. Несовместимости для старого Flutter-клиента

1. Смешивать `case_profile_match` / `event_severity_signal` с `company_calculated` как одно «влияние».  
2. Показывать `null` score как `0`.  
3. Считать Impact 404 фатальным блоком чата.  
4. Игнорировать `client_*_id` (риск дублей).  
5. Ждать successful final после agent-loop stop на том же `client_message_id`.  
6. Подставлять localhost в Telegram deep-open URL.  
7. Считать `ingestion.status=partial` «лента обновлена успешно».  
8. Расширять bank scope клиентскими run/file id.  
9. Передавать `slot_key` case_context с клиента.  
10. Ожидать Telegram auto-news без серверного флага/eligibility.

---

## 8. Что читать дальше

- [`MOBILE_API.md`](MOBILE_API.md) — таблицы методов  
- `contracts/openapi.json` — машинный контракт  
- Assistant / finance / bank / telegram docs по ссылкам из MOBILE_API  
- [`BACKEND_DEPLOYMENT_HANDOFF.md`](BACKEND_DEPLOYMENT_HANDOFF.md) — размещение  
