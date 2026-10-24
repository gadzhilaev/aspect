# Telegram: личная привязка и тестовое уведомление (этап ТГ-2)

Дата: **2026-10-24**  
Предшественник: [`TELEGRAM_NOTIFICATIONS_AUDIT.md`](TELEGRAM_NOTIFICATIONS_AUDIT.md) (ТГ-1).

**В этом этапе:** безопасный personal pairing, UI управления, тестовая постановка в существующий outbox/worker.  
**Не делалось:** реальный Telegram API / `setWebhook` / туннель, изменение root `.env` и рабочих стендов, автоматический enqueue новостей, live LLM, commit/push.

---

## 1. Контракт

### 1.1 Привязка (personal)

| Шаг | Поведение |
|-----|-----------|
| Выдача | `POST /api/v1/telegram/link-token` `{ company_id }` — opaque `token_urlsafe`, в БД только **hash**, TTL (`TELEGRAM_LINK_TOKEN_TTL_MINUTES`, default 10), deep link `t.me/<bot>?start=<raw>` |
| Погашение | Webhook `/start <token>` **только** в `chat.type == private`; атомарный `UPDATE … SET consumed_at WHERE consumed_at IS NULL` — конкурентно побеждает один |
| ACL при погашении | Повторная проверка membership; если доступ отозван после выдачи ссылки → отказ, токен уже погашен |
| Конфликт chat | Тот же `chat_id`, уже `connected` у **другого** пользователя → отказ **без** перезаписи. Один пользователь + несколько компаний с одним chat — **разрешено** (нет глобальной UNIQUE на `chat_id`) |
| Идемпотентность webhook | Повтор того же update / уже consumed token → без дубль-привязки |
| Секрет | Заголовок `X-Telegram-Bot-Api-Secret-Token` ↔ `TELEGRAM_WEBHOOK_SECRET` |
| Логи | Без raw token, полного `/start` payload, bot token, Authorization |

### 1.2 Отключение ≠ отвязка

| Операция | Эффект |
|----------|--------|
| Выключить уведомления (`PATCH … is_active=false`) | Привязка и `chat_id` сохраняются; отправка запрещена |
| Отвязать (API `DELETE` подписки / UI «Отвязать») | Для **этой** компании: `disconnected`, `chat_id=null` |
| `/unlink` в боте | **Все** `telegram_private` с этим `chat_id` (все компании чата). Не выбирается «первая» произвольная строка |

Групповой pairing (`purpose=group`) не расширялся и не ломался.

### 1.3 Тестовая отправка

| Правило | Деталь |
|---------|--------|
| Endpoint | `POST /api/v1/telegram/test-send` `{ company_id, client_request_id? }` |
| Получатель / текст | Только сервер: подписка пользователя + фиксированный текст; клиент **не** передаёт `chat_id` и текст |
| Текст | «Тестовое уведомление Аспекта. Telegram подключён. Это проверка доставки, а не предупреждение о новости.» — без финансов |
| ACL | membership + `status=connected` + `chat_id` |
| Частота | Cooldown `TELEGRAM_TEST_SEND_COOLDOWN_SECONDS` (default 60) на новые постановки |
| Идемпотентность | Тот же `client_request_id` → ответ с `idempotent_replay` **до** rate limit |
| Кнопка URL | Только если задан публичный HTTPS (`PUBLIC_WEB_BASE_URL` / совместимый host); **localhost не подставляется** |
| Ответ API | Постановка в очередь (`queued` / статус outbox). **Не** называется доставкой. `delivery: not_claimed` |
| Статус | `GET /api/v1/telegram/outbox/{id}` — `pending` / `retry` / `sent` / `failed` / `blocked` / `skipped` / `uncertain`. `sent` ≠ прочтение |

### 1.4 Worker (перед send)

Повторно: subscription существует, `connected` + `is_active`, `chat_id` совпадает с outbox (после unlink/rebind старая запись **не** уходит старому и **не** переезжает новому), membership, mute.

| Telegram | Поведение |
|----------|-----------|
| 403 blocked | `blocked`, без бесконечных повторов; подписка → `blocked` |
| 429 | `retry` + `retry_after` (ограниченный backoff) |
| Временные ошибки | Ограниченные повторы → `failed` |
| Timeout после возможного accept | `uncertain` — без обещания exactly-once |

Без bot token в конфиге → `skipped` (безопасно для DX).

Доставка — **at-least-once** каркас; exactly-once не обещается.

---

## 2. Что изменено

| Область | Файлы / артефакты |
|---------|-------------------|
| Миграция | `alembic/versions/008_telegram_outbox_subscription.py` — `notification_outbox.subscription_id`, `kind` |
| Модели / сервис | `app/models/notification.py`, `app/services/notifications.py` |
| Webhook / API | `app/api/v1/telegram.py`, `app/api/v1/notifications.py` |
| Worker | `app/workers/notification_worker.py` |
| Конфиг | `app/core/config.py`, `.env.example` (`PUBLIC_WEB_BASE_URL`, `TELEGRAM_TEST_SEND_COOLDOWN_SECONDS`) |
| UI | `web/src/pages/NotificationsPage.tsx`, `endpoints.ts`, маршрут `/notifications`, пункт в `SiteLayout` |
| Тесты | `tests/test_telegram_tg2.py` (+ регрессии acceptance pairing/dedupe) |

Автоматический `enqueue_impact_notifications` / обработка «старого» news outbox **не** включались как продуктовый путь ТГ-2.

---

## 3. UI

Страница **Уведомления** (`/notifications`):

- выбор компании (явная область действия);
- не подключён / ссылка «Подключить Telegram» / ожидание с поллом серверного статуса;
- подключён + вкл/выкл уведомлений;
- «Отправить тестовое сообщение» + отображение queued/sent/failed/…;
- «Отвязать»;
- смена компании сбрасывает локальное ожидание/outbox-состояние.

Открытие deep link **не** считается подтверждением — только `GET …/notification-settings`.

---

## 4. Проверки (выполнено)

Временная БД, mocked Telegram HTTP (`tests/test_telegram_tg2.py`):

- TTL, одноразовость, повтор webhook;
- private vs group для personal `/start`;
- отзыв membership между выдачей и погашением;
- конфликт разных пользователей на один `chat_id`;
- один пользователь — несколько компаний;
- ACL test-send;
- rate limit + идемпотентность `client_request_id`;
- unlink / rebind при pending outbox (skip по `chat_mismatch`);
- 403 / 429 / timeout (uncertain);
- `npm run build` (web) — OK.

Команда: `python -m pytest tests/test_telegram_tg2.py` (+ связанные acceptance link/dedupe/expired).

---

## 5. Ограничения этапа

- Реальный Bot API / `setWebhook` / публичный туннель **не** вызывались.
- Root `.env`, рабочие БД и запущенные стенды **не** менялись.
- Новостной auto-enqueue и правила «важная негативная новость» **не** включены.
- Без токена воркер помечает outbox `skipped` — это ожидаемо для локального DX.
- Успешный `sendMessage` не доказывает прочтение.

---

## 6. Инструкция: подключить настоящего бота (после ТГ-2)

Не выполнять в рамках этого этапа — чеклист на следующий ops-шаг:

1. Создать бота у `@BotFather`, получить token и username.
2. Выставить в **отдельном** env стенда (не обязательно root hackathon `.env`):  
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_SECRET` (случайный),  
   опционально `PUBLIC_WEB_BASE_URL=https://<публичный-host>` (не localhost).
3. Прогнать миграции, включая `008`.
4. Поднять API с публичным HTTPS и worker (`notification_worker` / compose `worker`).
5. Один раз: `setWebhook` на `https://<host>/api/v1/telegram/webhook` с тем же secret header.
6. В UI: привязка → «тестовое сообщение» → убедиться в статусе outbox `sent` в личном чате.
7. Только после этого — включать правила автоматических новостных уведомлений (следующий этап).

---

## 7. Оставшиеся шаги (после ТГ-2)

1. **Публичный webhook + worker** на реальном HTTPS-стенде.  
2. **Одна реальная тестовая отправка** через UI/API (проверка end-to-end).  
3. **Правила автоматических новостных уведомлений** (enqueue по политике «важная негативная», watermark привязки, без лишних финансов в тексте) — отдельный этап; не смешивать с pairing/test.

**Этап ТГ-2 завершён. Остановка.**
