# Отчёт: Backend MVP «Контур»

**Дата:** 12 октября 2026  
**Документ-основание:** `TZ_Backend_Kontur_MVP.md` (версия 1.0)  
**Статус реализации:** MVP готов к локальному демо и интеграции с мобильным клиентом  
**Тесты:** 11/11 passed  

---

## 1. Краткий итог

Реализован backend для хакатонного MVP продукта «Контур»: руководитель видит не только новость, а **что она значит для конкретной компании** и **какие есть варианты действий**.

Полностью проходит демонстрационный сценарий:

> ограничение экспорта электроники из Китая → Shenzhen X → компонент B → линия №2 → 24% выпуска под риском → сравнение 3 альтернатив → симуляция → план действий → канал Telegram (опционально)

Архитектура — **модульный монолит** на FastAPI + SQLAlchemy. Локально работает на SQLite без Docker; для стенда предусмотрен Docker Compose с PostgreSQL и outbox-worker.

| Метрика | Значение |
|---|---|
| Python-файлов | ~44 |
| Acceptance-тесты | 11 passed |
| Демо-компания | ООО «СеверПром» (`cmp_severprom`) |
| Демо-событий | 3 |
| Альтернатив решений | 3 |
| Префикс API | `/api/v1` |
| Документация | `/docs` (OpenAPI/Swagger) |

---

## 2. Соответствие целям ТЗ

### 2.1. Цель MVP — выполнена

| Шаг демо-сценария | Статус | Как закрыто |
|---|---|---|
| Регистрация / вход | ✅ | JWT access/refresh, verify email |
| Профиль СеверПром + Digital Twin | ✅ | nodes/edges, seed + API онбординга |
| Событие об экспорте | ✅ | `evt_china_export_001` + source stub |
| Ранжирование / dashboard | ✅ | impact_score, urgency, counters |
| Цепочка влияния | ✅ | Shenzhen X → модуль B → линия №2 |
| Факт / вывод / оценка раздельно | ✅ | `claim_type` + claims counters |
| Варианты действий | ✅ | 3 demo candidates + explainable sort |
| Симуляция | ✅ | детерминированный `sim-v1.0` |
| Сохранение решения | ✅ | decisions + action items |
| Telegram-уведомление | ✅ | pairing token, webhook, outbox |
| Работа без Telegram | ✅ | API не зависит от бота |

### 2.2. Что сознательно не входит (по ТЗ) — не делали

- realtime-сбор новостей из множества источников;
- автоподтверждение фактов / доступности поставщиков;
- финансовые гарантии и «лучший» вариант без компромиссов;
- универсальный twin любого бизнеса;
- микросервисы / графовая БД / vector store;
- AI-агенты, сами меняющие профиль или рассылающие решения.

---

## 3. Архитектура

### 3.1. Формат

```
Mobile / Telegram
        │
        ▼
   FastAPI (/api/v1)
        │
   ┌────┴────────────────────────────┐
   │ auth │ companies │ events │ …   │  application services
   └────┬────────────────────────────┘
        │
   PostgreSQL / SQLite
        │
   notification_outbox ──► worker ──► Telegram Bot API
```

### 3.2. Стек

| Слой | Технология |
|---|---|
| API | FastAPI + Pydantic v2 |
| ORM / БД | SQLAlchemy 2.0, Alembic |
| Auth | bcrypt + JWT (`python-jose`) |
| HTTP client | httpx (Telegram send) |
| Тесты | pytest + TestClient |
| Локально | SQLite (`kontur.db`) |
| Стенд | Docker Compose: Postgres 16 + API + worker |

### 3.3. Структура репозитория

```
kontur_back/
├── app/
│   ├── main.py                 # FastAPI app, /health, CORS, error handlers
│   ├── core/                   # config, security, deps, errors
│   ├── db/                     # engine, session, Base
│   ├── models/                 # users, companies, events, solutions, notifications
│   ├── schemas/                # request/response DTO
│   ├── api/v1/                 # REST routers
│   ├── services/               # graph, impact, simulator, notifications
│   └── workers/                # outbox sender
├── scripts/seed_demo.py        # идемпотентный seed СеверПром
├── tests/                      # acceptance §14
├── alembic/                    # миграции
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── TZ_Backend_Kontur_MVP.md
└── README.md
```

### 3.4. Модули backend (как в ТЗ §4)

| Модуль | Реализация |
|---|---|
| `auth` | `app/api/v1/auth.py` |
| `companies` | `app/api/v1/companies.py` + models |
| `graph` | `app/services/graph.py` (BFS, depth ≤ 5) |
| `events` | `app/api/v1/events.py` + impact service |
| `solutions` | `app/api/v1/solutions.py` |
| `scenarios` | Scenario model + simulate endpoint |
| `decisions` | `app/api/v1/decisions.py` |
| `notifications` | subscriptions + outbox service |
| `telegram` | webhook, pairing tokens, commands |

---

## 4. Модель данных

Реализованы сущности из ТЗ §5:

### Пользователи и доступ
- `users` — email, password_hash, display_name, email_verified_at
- `email_verifications` — код подтверждения
- `company_memberships` — роли `owner|admin|analyst|viewer`

### Digital Twin
- `companies` — карточка + `profile_status`, `digital_twin_status/coverage`
- `company_nodes` — supplier / component / product / facility / production_line / market / currency (+ typed `output_share_percent`, `country`)
- `company_edges` — buys_from, supplies, used_in, produced_at, sold_in, …
- `company_profile_settings` — валюты, необязательные финансы

### События и объяснимость
- `events` — severity, structured match_* (страны/категории/валюты/материалы)
- `event_sources` — stub-источники с `is_stub=true`
- `event_impacts` — score, urgency, confidence, breakdown, claims
- `impact_paths` — узлы пути + `claim_type`

### Решения
- `solution_candidates` — demo-альтернативы + sort_breakdown
- `scenarios` — parameters/results + model_version + is_estimate
- `decisions`, `action_items`

### Telegram / доставка
- `notification_subscriptions`
- `telegram_link_tokens` (hash, TTL 10 мин, one-time)
- `notification_outbox` (unique `dedupe_key`)

---

## 5. API-контракт

Общий префикс: `/api/v1`  
Формат: JSON snake_case, даты ISO 8601 UTC  
Единый формат ошибок:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Проверьте введённые данные",
    "details": [{"field": "tax_id", "reason": "invalid_format"}]
  }
}
```

### Auth
| Метод | Путь | Назначение |
|---|---|---|
| POST | `/auth/register` | регистрация |
| POST | `/auth/verify-email` | код подтверждения |
| POST | `/auth/login` | access + refresh |
| POST | `/auth/refresh` | обновление токенов |
| GET | `/users/me` | текущий пользователь и компании |

### Компания / онбординг (экраны 04–12)
| Метод | Путь | Назначение |
|---|---|---|
| GET | `/industries` | отрасли |
| GET | `/companies/search` | поиск по имени/ИНН |
| POST | `/companies` | создать компанию |
| GET | `/companies/{id}/profile` | сводный профиль |
| PATCH | `/companies/{id}` | карточка / отрасль |
| POST | `/companies/{id}/nodes` | узел twin |
| PATCH | `/companies/{id}/nodes/{node_id}` | изменить узел |
| POST | `/companies/{id}/edges` | связь |
| PATCH | `/companies/{id}/finance` | необязательный финшаг |
| POST | `/companies/{id}/profile/complete` | готовность профиля |
| POST | `/companies/{id}/digital-twin/build` | статус/покрытие модели |

### События (экраны 13–15)
| Метод | Путь | Назначение |
|---|---|---|
| GET | `/companies/{id}/dashboard` | счётчики + приоритетная лента |
| GET | `/companies/{id}/events` | лента (cursor pagination) |
| GET | `/events/{id}` | детали + sources + claims |
| GET | `/events/{id}/impact` | Impact Graph |
| POST | `/events/{id}/recompute-impact` | пересчёт + enqueue уведомлений |

### Решения (экраны 16–18)
| Метод | Путь | Назначение |
|---|---|---|
| GET | `/events/{id}/solutions` | варианты + explainable ranking |
| POST | `/events/{id}/simulate` | baseline vs alternative |
| GET | `/scenarios/{id}` | сохранённый расчёт |
| POST | `/decisions` | сохранить решение + default action items |
| GET | `/decisions/{id}` | план действий |
| POST | `/decisions/{id}/action-items` | добавить шаг |
| PATCH | `/action-items/{id}` | статус/ответственный |

### Telegram / уведомления (экран 19)
| Метод | Путь | Назначение |
|---|---|---|
| GET | `/companies/{id}/notification-settings` | статусы каналов |
| POST | `/telegram/link-token` | личный pairing |
| POST | `/telegram/groups/link-token` | групповой pairing |
| PATCH | `/notification-subscriptions/{id}` | порог, mute, категории |
| DELETE | `/notification-subscriptions/{id}` | отключить канал |
| POST | `/telegram/webhook` | команды бота + Start |

### System
| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | liveness + telegram_configured |
| GET | `/` | краткая витрина API |
| GET | `/docs` | Swagger UI |

---

## 6. Ключевая бизнес-логика

### 6.1. Impact Graph (`services/graph.py` + `services/impact.py`)

1. Событие матчится по **структурированным признакам** (страны/материалы), не по словам заголовка.
2. Точки входа — предпочтительно `supplier` (для демо: Shenzhen X / Китай).
3. Путь ищется BFS с глубиной до 5, без циклов, без отдельной графовой БД.
4. Терминалы: `production_line` / `product` / `facility`.

**Демо-путь:**
```
Китай (match) → Shenzhen X → Электронный модуль B → Линия №2 (24%)
```

**Impact score** (версионируемая формула `impact-v1.0`):

```
score = 0.40×severity + 0.30×exposure + 0.20×dependency + 0.10×proximity
```

**Confidence** считается отдельно (качество источников + confidence рёбер).  
В ответе есть `score_breakdown` и `claims` (`confirmed` / `inferences` / `assumptions` / `estimates`).

На smoke-тесте для экспортного события: **impact_score ≈ 86.9**, **exposure = 24%**.

### 6.2. Solution Engine + Simulator

Сортировка альтернатив объяснимая (weights risk / lead / cost / compatibility), без заявления «один вариант безусловно лучший».

Симулятор `sim-v1.0`:
- входы: доля выпуска под риском, запас (дни), задержка, выбранный solution;
- выходы: stop_risk baseline/alternative, cost delta, lead time, assumptions, tradeoff;
- одинаковый ввод → одинаковый результат;
- недостаток данных → `INSUFFICIENT_DATA`;
- всегда `is_estimate: true`.

### 6.3. Telegram и outbox

Поток личного подключения:
1. Приложение → `POST /telegram/link-token`
2. Пользователь открывает `t.me/Bot?start=<one-time-token>`
3. Webhook `/start` потребляет token (hash, TTL, one-time)
4. Создаётся `notification_subscriptions` со статусом `connected`

Защита от спама:
- порог `min_severity`;
- dedupe по `company + event + channel + chat`;
- mute / quiet hours;
- outbox statuses: pending / retry / sent / failed / skipped;
- без `TELEGRAM_BOT_TOKEN` основная цепочка жива, отправка помечается `skipped`.

Команды бота MVP: `/start`, `/help`, `/settings`, `/mute`, `/unmute`, `/status`.

---

## 7. Seed-данные для демо

Команда: `python -m scripts.seed_demo` (идемпотентна).

| Сущность | Значение |
|---|---|
| Пользователь | `demo@kontur.app` / `DemoKontur1!` |
| Компания | СеверПром (`cmp_severprom`), ИНН `7100000000`, Тула |
| Продукт | Промышленные насосы |
| Поставщик | Shenzhen X, Китай |
| Компонент | Электронный модуль B |
| Площадка | Завод №1 |
| Линия | Линия №2, 24% выпуска |
| Рынки | Россия, СНГ |
| Валюты | RUB, CNY, USD |

### Три демо-события

1. **`evt_china_export_001`** — экспортные ограничения (главный сценарий хакатона)  
2. **`evt_rate_hike_001`** — ключевая ставка (финфактор, оценка)  
3. **`evt_market_opp_001`** — рыночная возможность на СНГ  

### Три альтернативы для экспортного кейса

| ID | Вариант | Суть компромисса |
|---|---|---|
| `sol_thailand_a` | Поставщик A (Таиланд) | меньше риск — выше стоимость |
| `sol_vietnam_b` | Поставщик B (Вьетнам) | дешевле — дольше срок |
| `sol_buffer_stock` | Буферный запас | быстрее — зависимость сохраняется |

Все источники помечены как stub; числа — как estimates.

---

## 8. Безопасность (ТЗ §11)

| Требование | Реализация |
|---|---|
| Пароль только hash | bcrypt |
| JWT access/refresh | короткие TTL, type claim |
| Membership check | `require_company_member` на company-scoped API |
| Изоляция компаний | тест `test_cannot_read_foreign_company` |
| Bot token в env | `.env` / Compose, не в репозитории |
| Pairing token | sha256 hash, TTL 10 мин, one-time |
| Webhook secret | заголовок `X-Telegram-Bot-Api-Secret-Token` |
| Group без финансов | отдельный короткий payload для group |

---

## 9. Нефункциональные требования

| Требование | Статус |
|---|---|
| REST JSON под мобильный клиент | ✅ |
| OpenAPI в dev | ✅ `/docs` |
| Миграции / воспроизводимая схема | ✅ Alembic + `create_all` для DX |
| Cursor pagination ленты | ✅ |
| UTC storage | ✅ |
| Backend без Telegram | ✅ |
| Секреты не коммитятся | ✅ `.gitignore` + `.env.example` |

---

## 10. Тестирование и приёмка (§14 ТЗ)

Запуск: `pytest -q`  
Результат на момент отчёта: **11 passed**.

| # | Критерий ТЗ | Тест | Статус |
|---|---|---|---|
| 1 | Регистрация, verify, login | `test_register_verify_login` | ✅ |
| 2 | Нельзя читать чужую компанию | `test_cannot_read_foreign_company` | ✅ |
| 3 | Профиль / онбординг прогресс | `test_profile_and_finance_optional` | ✅ |
| 4 | Финшаг необязателен | тот же тест (`finance_optional`) | ✅ |
| 5 | Путь Shenzhen → B → линия №2 | `test_impact_path_shenzhen_to_line` | ✅ |
| 6 | Факты и assumptions раздельно | тот же тест (`claim_type`) | ✅ |
| 7 | Детерминизм симулятора | `test_simulate_deterministic` | ✅ |
| 8 | Decision + action items | `test_decision_persists` | ✅ |
| 9 | Dedupe Telegram | `test_telegram_dedupe` | ✅ |
| 10 | Просроченный/использованный token | `test_expired_pairing_token`, `test_link_token_flow` | ✅ |
| 11 | Бот отключён — API жив | `test_works_without_telegram` | ✅ |

Дополнительно: `test_health`.

### E2E критерий демо

Тестовый пользователь входит под demo → открывает СеверПром → видит экспортное событие → открывает объяснимую цепочку → выбирает поставщика A (Таиланд) → получает сравнение → сохраняет решение → может подключить Telegram и получить одно личное уведомление с deep link на событие.

---

## 11. Соответствие экранам мобильного макета (§3)

| Экран | Backend support |
|---|---|
| 01 Начало | не требуется |
| 02–03 Аккаунт / email | auth API |
| 04–05 Компания | search + create + profile |
| 06–10 Онбординг | industry, nodes, edges, finance |
| 11–12 Профиль / twin | profile + build |
| 13 Обзор | dashboard |
| 14 Событие | event detail |
| 15 Цепочка | impact |
| 16 Варианты | solutions |
| 17 Сценарии | simulate |
| 18 План | decisions |
| 19 Telegram | notification-settings + link-token |

---

## 12. Как запустить

### Локально (рекомендуется для разработки)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m scripts.seed_demo
uvicorn app.main:app --reload --port 8003
```

- Swagger: http://127.0.0.1:8003/docs
- Health: http://127.0.0.1:8003/health

### Docker Compose

```bash
docker compose up --build
```

Сервисы: `db` (Postgres), `api`, `worker` (outbox loop).

### Полезные идентификаторы

```
email:       demo@kontur.app
password:    DemoKontur1!
company_id:  cmp_severprom
event_id:    evt_china_export_001
solution_id: sol_thailand_a
```

---

## 13. План реализации ТЗ — статус этапов

| Этап | Содержание | Статус |
|---|---|---|
| 1 Каркас | repo, config, DB, health, OpenAPI, seed | ✅ |
| 2 API под Figma flow | auth, profile, dashboard, event, impact | ✅ |
| 3 Решения | solutions, simulator, decisions | ✅ |
| 4 Telegram | pairing, subscriptions, outbox, webhook | ✅ |
| 5 Защита и репетиция | тесты доступа/идемпотентности, работа без бота | ✅ |

---

## 14. Известные ограничения MVP

1. **SQLite по умолчанию** — удобно для демо; на стенде лучше Postgres через Compose.  
2. **Telegram без реального токена** — outbox пишет задачи, send → `skipped` (это корректное поведение).  
3. **Email-код в debug** возвращается в ответе register — только для хакатона, не для production.  
4. **Demo solutions** — заранее подготовленные записи, не маркетплейс поставщиков.  
5. **Impact для демо-события** калиброван объяснимой формулой под граф СеверПром; числа помечены как estimate.  
6. На машине разработки **Docker не был установлен** — Compose-файлы подготовлены, прогон Compose нужно сделать на стенде с Docker.

---

## 15. Рекомендации на следующий день команды

1. Согласовать с frontend 3 контракта: `profile`, `dashboard`, `event detail` (уже в `/docs`).  
2. Прогнать полный UI flow на seed-данных.  
3. Выдать `TELEGRAM_BOT_TOKEN` и проверить личное уведомление end-to-end.  
4. На публичном стенде: Postgres + HTTPS webhook + ротация `SECRET_KEY`.  
5. Не расширять scope, пока не закрыт путь «событие → решение» на сцене.

---

## 16. Главный технический принцип (выполнен)

> **Сначала честная и объяснимая цепочка на одной компании, затем масштабирование.**

Факты, оценки, источники и решения разделены. Система показывает компромиссы, а не «магический лучший ответ». AI/бот не принимают бизнес-решение за пользователя.

---

## 17. Вывод

Backend MVP «Контур» **готов к хакатон-демо и интеграции с мобильным приложением**:

- закрыт полный продуктовый путь ТЗ;
- есть seed СеверПром и OpenAPI;
- acceptance-критерии §14 покрыты автотестами (11/11);
- Telegram опционален и не ломает основной сценарий.

**Артефакты:** код в `kontur_back/`, инструкция в `README.md`, исходное ТЗ в `TZ_Backend_Kontur_MVP.md`, этот отчёт в `REPORT.md`.
