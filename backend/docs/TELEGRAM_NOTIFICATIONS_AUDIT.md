# Аудит Telegram-уведомлений (этап ТГ-1)

Дата: **2026-10-24**  
Цель этапа: изучить существующую интеграцию и спланировать **минимальные** личные уведомления  
о новой важной негативной новости, связанной с компанией пользователя.  
**Код / БД / root `.env` / стенды в этом этапе не менялись.** Telegram API не вызывался.

Связанные: `REPORT.md` (§ Telegram), `CASE_PERSONALIZED_FEED.md`, `EVENT_DISCOVERABILITY.md`.

---

## 1. Фактическая реализация

### 1.1 Что реализовано и используется в коде

| Компонент | Где | Назначение |
|-----------|-----|------------|
| Модели | `app/models/notification.py` | `NotificationSubscription`, `TelegramLinkToken`, `NotificationOutbox` |
| Выдача pairing-токена | `issue_link_token` / `POST /api/v1/telegram/link-token` | opaque `token_urlsafe`, хранится **hash**, TTL (`telegram_link_token_ttl_minutes`, default 10), deep link `t.me/<bot>?start=<raw>` |
| Групповой pairing | `POST /api/v1/telegram/groups/link-token` | тот же механизм, `purpose=group`; только owner/admin |
| Webhook бота | `POST /api/v1/telegram/webhook` | проверка `X-Telegram-Bot-Api-Secret-Token` ↔ `TELEGRAM_WEBHOOK_SECRET`; `/start <token>`, `/help`, `/status`, `/mute`, `/unmute`, `/settings`, group confirm |
| Настройки подписки | `GET …/notification-settings`, `PATCH/DELETE …/notification-subscriptions/{id}` | порог, risks/opportunities, quiet hours, отключение |
| Outbox enqueue | `enqueue_impact_notifications` | после `POST …/recompute-impact` |
| Worker | `app/workers/notification_worker.py` | poll outbox → `sendMessage`; без токена → `skipped` |
| Legacy Compose | `docker-compose.yml` | сервис `worker` (цикл каждые 5 с) + env Telegram |
| Health | `GET /health` → `telegram_configured: bool(token)` | без секретов |
| Тесты | `tests/test_acceptance.py` | dedupe outbox, expired token, link flow one-time, API без Telegram |

Конфиг (имена, **без значений**): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_LINK_TOKEN_TTL_MINUTES`, `DEEP_LINK_BASE`.

Схема создаётся через `Base.metadata.create_all` (DX / alembic 001), отдельных revision-файлов только под notification-таблицы нет.

### 1.2 Что является заготовкой / слабо связано с прод-путём

| Элемент | Статус |
|---------|--------|
| Групповые уведомления | Код есть; для цели «личное сообщение» не нужен в ТГ-2 |
| Текст payload с «% выпуска» / «уверенность» | Есть; **не** соответствует политике «не светить финансы по умолчанию» |
| Порог `min_severity` ↔ `impact_score` | Работает как числовой cut-off; семантика «severity» смешана с индексом влияния |
| UI сайта «Уведомления → Telegram» | **Нет** в `web/` (только общие заглушки); API готово |
| Competition Docker (`docker-compose.competition.yml`) | **Нет** worker / Telegram env |
| Ingest → Impact → outbox | `recompute_event_for_ready_companies` **не** вызывает enqueue; только явный `recompute-impact` |
| Polling long-poll | **Не** реализован; только webhook |

### 1.3 Что можно переиспользовать

- Opaque pairing: hash + TTL + `consumed_at` + ACL через `require_company_member` при выдаче токена.
- Таблицы subscription / outbox / unique `dedupe_key`.
- Worker + outbox (at-least-once каркас: pending/retry/sent/failed/skipped).
- Webhook secret header.
- Команды mute/unmute и soft-delete подписки (`is_active=false`, `chat_id=null`).
- Тесты pairing/dedupe как регрессии.

### 1.4 Чего не хватает (пробелы)

1. **Правило «новая важная негативная»** не отделено от «есть Impact и score ≥ порога».  
2. Нет watermark «не слать события старше момента привязки».  
3. Нет повторной проверки membership / `is_active` / mute **перед** send.  
4. Нет обработки `403 bot was blocked` / `429 Too Many Requests` как отдельных статусов.  
5. Нет проверки `chat.type == private` при `/start` (личный канал теоретически можно подтвердить из группы с payload).  
6. Нет явной отвязки из бота (`/unlink`); только API delete / mute.  
7. Конфликт: один `chat_id` на нескольких подписках не уникален; `/status` берёт «первую».  
8. Публичный URL сайта для кнопки: только `DEEP_LINK_BASE` (default `https://kontur.app/e/...`); нет обязательного `PUBLIC_WEB_BASE_URL`, localhost не запрещён конфигом.  
9. Нет UI и нет «тестовой отправки».  
10. Competition-стек без worker — доставка в нём не предусмотрена.  
11. Неопределённый сетевой результат (таймаут после возможного accept Telegram) → риск дубля; exactly-once **не** обещается и не реализован (idempotency key у Telegram не используется).  
12. Webhook отвечает JSON `method: sendMessage` (callback Telegram) **и** worker шлёт отдельно — два пути доставки для разных этапов; для outbox-карточек реально шлёт worker.

---

## 2. Безопасная привязка (предложение)

Опираться на **уже существующий** протокол; минимальные ужесточения в ТГ-2/ТГ-3.

### 2.1 Поток

1. Авторизованный пользователь на сайте выбирает компанию (уже member).  
2. `POST /telegram/link-token` `{ company_id }` → opaque raw + `https://t.me/<bot>?start=<raw>` (TTL короткий).  
3. Пользователь открывает ссылку на телефоне → Telegram `/start <raw>`.  
4. Webhook: `consume_link_token` → upsert `NotificationSubscription` (`telegram_private`, `connected`, `chat_id`).  
5. Ответ бота: подтверждение без email / company_id / username как секрета.

**Не** назначать membership через Telegram.  
**Не** использовать email, `company_id`, Telegram username как секрет привязки (сейчас не используются — сохранить).

### 2.2 Ограничения привязки

| Тема | Правило |
|------|---------|
| Только личный чат | При `purpose=private` принимать `/start` только если `chat.type == "private"`; иначе отказ |
| Одноразовость / TTL | Уже есть; не ослаблять; при ошибке — новый токен из приложения |
| Повторная привязка | Обновлять `chat_id` той же `(user, company, telegram_private)`; предыдущий chat той же подписки считать заменённым |
| Конфликт | Один Telegram-аккаунт → один активный private chat на пару user×company; при привязке другого user к тому же chat — не «перехватывать» чужую подписку без явной политики (рекомендация ТГ-2: отклонить, если chat_id уже у другого user_id) |
| Отвязка | API `DELETE` + команда `/unlink` (пометить disconnected, очистить chat_id) |
| Доступ к компании | Уже при выдаче токена; перед **отправкой** снова проверить membership + subscription active |
| Отключение уведомлений | `is_active=false` / risks_enabled / mute / quiet hours |
| Блокировка бота | При send 403 → `status=blocked` (или disconnected), прекратить retry |

Группы оставить вне MVP личных уведомлений (код не удалять).

---

## 3. Правила уведомлений

### 3.1 Семантика доступных полей (факт)

| Поле | Что означает | Чего **не** означает |
|------|----------------|----------------------|
| `Event.event_type` (`risk` / `opportunity` / …) | Классификация карточки | Доказанный убыток |
| `Event.severity` (0–100) | Редакционная/эвристическая важность события | Персональный ущерб |
| `Event.is_demo` | Синтетика / демо | |
| `EventImpact.impact_score` | Индекс приоритета разбора для компании | Вероятность / % потерь |
| `EventImpact.confidence` | Эвристика качества данных | Уверенность в прогнозе |
| `EventImpact.exposure_value` | Модельная доля выпуска на узле (если есть) | Факт сорванных поставок |
| `score_kind=company_calculated` | Есть usable twin/path расчёт | |
| `score_kind=event_severity_signal` | Ориентир по severity без персонального расчёта | Критическое воздействие |
| `score_kind=case_profile_match` | LOA/DEP × policy_rate и т.п. | Критическое воздействие / Impact |
| Лента «Для вас» | Impact **или** profile | Не равна «надо пушить в TG» |

Текущий enqueue: любой Impact с `impact_score ≥ thresholds[min_severity]` и risks/opportunities flags — **слишком широко** и семантически смешивает порог с «severity».

### 3.2 Минимальное объяснимое правило (предложение v1)

Отправлять в личку **только если все** условия истинны:

1. **Новизна для подписки:** `Event.created_at >= subscription.verified_at`  
   (или `Impact.computed_at >= verified_at` при первом появлении Impact после привязки).  
   При подключении **не** ретроактивно слать архив ленты.
2. **Связь с компанией подтверждена Impact’ом:** существует `EventImpact` для `(event, company)` со `status ∈ {action_required, monitor}` и в breakdown/basis **`score_kind == company_calculated`**.  
   - `case_profile_match` → **только лента**, не TG.  
   - `event_severity_signal` / `calculation_unavailable` → **только лента**.
3. **Негативное направление (прокси):** `Event.event_type == "risk"` (и `risks_enabled`).  
   Отдельного поля «negative_effect_proven» **нет** — это честный пробел; `risk` ≠ доказанный негативный эффект, но это единственный стабильный прокси без LLM.
4. **Достаточное основание высокой важности:**  
   `impact_score >= S` где S — настройка подписки (default соответствует нынешнему `high` → 70),  
   **и** в тексте основания явно говорить «индекс приоритета разбора», не «высокий риск потерь».  
   Не использовать `Event.severity` единолично как критерий пуша.
5. `Event.status == active`, не слать при `is_demo=true` вне явно включённого demo-режима уведомлений.
6. Подписка: `telegram_private`, `connected`, `is_active`, не в mute/quiet hours; membership жив.

**Без LLM** на каждое уведомление.

### 3.3 Что остаётся только в ленте

- Profile-only (`case_profile_match`), в т.ч. синтетика ставки без Impact.  
- Opportunity (если не включены отдельно — по умолчанию для «негативных» не пушить).  
- Severity-only сигнал без company_calculated.  
- События без Impact / `not_relevant`.  
- Старые события до `verified_at`.  
- Демо-события (по умолчанию).

### 3.4 Прямо о нехватке полей

Для формулировки «доказанный негативный эффект на компанию» **полей недостаточно**:  
нет validated loss, нет direction-of-impact enum, нет human-confirmed severity.  
v1 сознательно использует **прокси** (`risk` + `company_calculated` + высокий индекс приоритета) и обязан честно подписывать основание в сообщении.

Не выдумывать новый порог «ради готовности» сверх существующей шкалы `min_severity` / score 0–100.

---

## 4. Доставка

### 4.1 Очередь / outbox (уже есть → уточнить)

Сохранить `notification_outbox`:

| Свойство | Как |
|----------|-----|
| Анти-дубль постановки | Unique `dedupe_key` = `company:event:channel:chat` (уже); при смене правил добавить версию ключа `v2:` |
| Повторы | Уже exponential backoff, max attempts; добавить ветки для 429 (Retry-After) и 403 blocked |
| Перед send | Re-read subscription + membership; иначе `skipped` |
| Журнал | `status`, `attempts`, `last_error` (обрезать, без токенов и без полного текста новости в error) |
| Семантика доставки | **At-least-once**; при timeout после POST — `retry` с тем же dedupe; не обещать exactly-once |

Enqueue вызывать не только из ручного recompute, но из того места, где появляется **новый** company_calculated Impact для risk-события (ingest/recompute path) — отдельным маленьким этапом после ТГ-2; до этого — тестовая постановка вручную.

### 4.2 Webhook vs polling

| | Webhook (сейчас) | Polling |
|--|------------------|---------|
| Pairing / команды | Уже реализовано | Нужен новый loop |
| Публичный HTTPS | Нужен для Telegram → API | Не нужен для входящих |
| Competition / локальный Docker | Без туннеля webhook не достать | Удобнее для dev |
| Outbox send | Исходящий HTTPS к `api.telegram.org` (worker) | То же |

**Рекомендация:**  
- **Не** плодить второй механизм команд: оставить **webhook** для `/start` и команд.  
- Worker outbox — как сейчас (исходящий Bot API).  
- Для локального/Docker без публичного URL: в ТГ-2 документировать ngrok/cloudflared **или** опциональный тонкий `getUpdates` **только** как dev-профиль, не параллельный прод-путь.  
- В competition compose worker сейчас отсутствует — при подключении TG добавить один-shot/sidecar worker, не второй outbox.

---

## 5. Сообщение (минимальный шаблон)

```
Новость для «{company_name}»

{event.title}

Почему важно: приоритет разбора по данным компании (индекс {impact_score:.0f}/100).
Это не прогноз потерь.

Источник: {primary_publisher}
```

Кнопка: **«Открыть разбор»** → `{PUBLIC_WEB_BASE_URL}/news/{event_id}`  
(или `/news/{id}?company={company_id}` — уточнить по фронту).

Правила текста:

- Не включать суммы долга, % плавающей ставки, exposure %, «уверенность» как вероятность.  
- `localhost` / `127.0.0.1` **не** считать рабочей ссылкой для телефона: для send требовать настроенный публичный `PUBLIC_WEB_BASE_URL` (или валидный https `DEEP_LINK_BASE`); иначе outbox → `skipped` с явной причиной.  
- Mute callback можно сохранить.

---

## 6. Предлагаемые API / таблицы / конфиг (дельта к существующему)

**Таблицы:** новых не обязательно для ТГ-2; опционально позже:

- `subscription.last_notified_event_at` / watermark;  
- outbox `status=blocked`;  
- unique `(chat_id)` where active private — миграция осторожно.

**API (ТГ-2):**

- Уже: link-token, settings, patch, delete.  
- Добавить: `POST /telegram/test-notification` (member, rate-limited) — ставит **одну** безопасную карточку в outbox или шлёт сразу через тот же worker path.  
- Бот: `/unlink`; отказ non-private на `/start`.

**Конфиг:**

- `PUBLIC_WEB_BASE_URL` (обязателен для реальной кнопки);  
- существующие Telegram vars;  
- не класть токен в image layers / frontend.

---

## 7. Следующий этап ТГ-2 (небольшой)

1. UI: кнопка «Подключить Telegram» → link-token → показать deep link (без печати raw в логах).  
2. Ужесточить webhook: только `private` для personal purpose; конфликт chat_id.  
3. Команда `/unlink` + проверка, что delete API отражается.  
4. Тестовая отправка одному пользователю (без массового бэкфилла).  
5. Worker: 403→blocked, 429→retry; re-check ACL перед send.  
6. Сообщение по шаблону §5 + публичный URL.  
7. Регрессии: pairing, dedupe, test-send без токена → skipped.  
8. **Не** в ТГ-2: группы, LLM, полный ingest→notify pipeline, competition worker (можно задокументировать follow-up).

---

## 8. Данные, которые потребуются от пользователя / ops

| Нужно | Зачем |
|-------|--------|
| `TELEGRAM_BOT_TOKEN` | Исходящие сообщения + (опционально) setWebhook |
| `TELEGRAM_BOT_USERNAME` | Deep link `t.me/...` |
| `TELEGRAM_WEBHOOK_SECRET` | Заголовок webhook (сильный random, не default из example) |
| Публичный HTTPS URL API | `setWebhook` на `/api/v1/telegram/webhook` |
| `PUBLIC_WEB_BASE_URL` (https, не localhost) | Кнопка «Открыть разбор» на телефоне |
| Подтверждение: бот создан у BotFather, privacy mode ок для private | |

Для чистой проверки привязки без пуша достаточно webhook + username; для тестовой доставки — ещё token и worker.

---

## 9. Краткий вердикт

Каркас **уже есть** (pairing, subscription, outbox, worker, webhook) и его нужно **сузить и довести**, а не писать второй движок.  
Главный пробел продукта — **правило отбора** (сейчас по сути «есть Impact и score»), честность текста и публичный URL; главный пробел ops — worker/webhook вне competition-стека и отсутствие UI.

**Стоп после этого отчёта (ТГ-1).** Реализация — с этапа ТГ-2.
