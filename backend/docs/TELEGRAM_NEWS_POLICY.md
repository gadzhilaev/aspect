# Telegram news policy v1 (этап ТГ-4)

Дата: **2026-10-24**  
Предшественники: [`TELEGRAM_NOTIFICATIONS_AUDIT.md`](TELEGRAM_NOTIFICATIONS_AUDIT.md), [`TELEGRAM_LINK_AND_TEST.md`](TELEGRAM_LINK_AND_TEST.md), [`TELEGRAM_LIVE_CONNECTION.md`](TELEGRAM_LIVE_CONNECTION.md), [`NEWS_CLASSIFICATION_FIX.md`](NEWS_CLASSIFICATION_FIX.md), [`NEWS_RECLASSIFICATION_APPLIED.md`](NEWS_RECLASSIFICATION_APPLIED.md).

**Сделано:** единый eligibility + watermark + idempotent enqueue `kind=news` после Impact, повторные проверки / quiet hours на send, серверный флаг (default off), честный UI, тесты на временной БД с mocked Telegram.  
**Не сделано:** реальные send новостей, включение news-worker на стендах, правки root `.env` / исходных БД, commit/push, live LLM.

---

## 1. Политика v1 (что может уйти в личку)

Уведомление **допустимо только если все** условия истинны (сервис `app/services/telegram_news_policy.py` → `evaluate_news_eligibility`):

| # | Условие | Отказ `reason` |
|---|---------|----------------|
| 0 | `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED=true` | `feature_disabled` |
| 1 | Личная подписка `telegram_private`, `connected`, `is_active`, есть `chat_id`, живой membership, `risks_enabled` | `not_private_channel` / `subscription_inactive` / `chat_missing` / `membership_missing` / `risks_disabled` |
| 2 | Событие: не demo, `status=active`, **`event_type=risk`**, **`severity` известна (не null)** | `event_demo` / `event_inactive` / `event_not_risk` / `severity_unknown` |
| 3 | Impact: `status ∈ {action_required, monitor}`, **`score_kind=company_calculated`** | `impact_not_usable` / `score_kind_not_company_calculated` |
| 4 | `impact_score ≥` порог из `min_severity` | `below_threshold` |
| 5 | Новизна относительно watermark (см. §2) | `novelty_*` / `watermark_missing` |
| 6 | Не в mute (на enqueue и на send) | `muted` |

### Порог `min_severity` (без понижения)

Существующая шкала сравнивается с **`impact_score` (0–100, индекс приоритета разбора)**, не с `Event.severity`:

| `min_severity` | минимум `impact_score` |
|----------------|------------------------|
| low | 0 |
| medium | 40 (default) |
| high | 70 |
| critical | 90 |

Формула Impact **не** менялась. Порог **не** снижался ради тестового PASS. Отсутствие подходящих событий — нормальный результат.

### Что v1 **не** покрывает (и не обещает)

- `neutral` / `other`, неизвестная значимость (`severity=null`);
- profile-only (`case_profile_match`);
- severity-only (`event_severity_signal`);
- отсутствие usable Impact / `not_relevant` / `calculation_unavailable`;
- известный `severity=0` сам по себе ≠ критический риск;
- финансовые what-if / ставка / FX без company_calculated risk-пути;
- групповой канал.

Текст в API/UI: `news_policy_note` + `news_notifications_server_enabled`.

---

## 2. Новизна и watermark

### Поле

Миграция **`010_telegram_news_auto_notify`**: `notification_subscriptions.auto_notify_since` (UTC, nullable).

### Когда ставится

| Событие | Поведение |
|---------|-----------|
| Успешный personal bind (`/start` + token) | `auto_notify_since = now` (без backfill архива) |
| Повторное включение (`PATCH is_active: false→true`) | watermark **сдвигается на now** |
| Привязка бота сама по себе | **не** ставит массовую рассылку |

### Часы (разделение)

| Часы | Поле | Роль в новизне |
|------|------|----------------|
| Публикация | `Event.occurred_at` (fallback `effective_from`) | должна быть **≥** watermark |
| Первое поступление в систему | `Event.created_at` | должна быть **≥** watermark |
| Расчёт Impact | `EventImpact.computed_at` | **не** делает старую новость новой |

Все сравнения — timezone-aware UTC (`_aware`).

### Задержанные публикации

Поздний импорт **старой** статьи: `created_at` свежий, но `occurred_at` до watermark → **`novelty_publication_before_watermark`** (отказ).  
Старая новость с только что пересчитанным Impact → отказ по публикации/arrival, не по `computed_at`.

---

## 3. Интеграция enqueue

Единая функция: `enqueue_impact_notifications` (теперь TG-4 policy, `kind=news`).

Вызывается **в той же транзакции**, что и сохранение Impact (rollback убирает outbox):

- `POST …/recompute-impact` (`app/api/v1/events.py`) — как раньше, перед `commit`;
- `recompute_event_for_ready_companies` (ingestion personalize);
- `recompute_events_for_company`;
- refresh macro/FX после `PATCH …/finance`.

Не вызывается модель / LLM. Не добавляет записи через GET.

### Идемпотентность

`dedupe_key = news:v1:{subscription_id}:{event_id}` + UniqueConstraint.  
Повтор ingestion/recompute / concurrent flush → `IntegrityError` → без второй строки.

---

## 4. Отправка (worker)

Перед send (`subscription_allows_send`):

- подписка / chat совпадение / membership / mute (как ТГ-2);
- для `kind=news`: флаг, Impact+Event ещё eligible (смена типа после постановки → `skipped`);
- **тихие часы** (`quiet_hours_json`: `{start,end}` HH:MM в `subscription.timezone`): статус остаётся `pending`, `next_attempt_at` = конец окна; запись **не** теряется. Перед отложенной отправкой проверка повторяется.

403 / 429 / timeout — без изменений относительно ТГ-2.

### Текст

- компания, заголовок, основание («индекс влияния N/100 — приоритет разбора, не вероятность и не процент потерь»), источник;
- кнопка «Открыть разбор» **только** при публичном HTTPS (`PUBLIC_WEB_BASE_URL`); localhost не подставляется;
- без сумм долга и чувствительных finance-параметров.

---

## 5. Управление

| Рычаг | Значение |
|-------|----------|
| `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED` | default **false** (`.env.example` закомментирован) |
| Основной стенд (`real_news_613`) | process overlay: `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED=true`, `TELEGRAM_OUTBOX_KINDS=test,news`; авто-news **только** для уже привязанной подписки «упк» + watermark включения — [`TELEGRAM_NEWS_LIVE_E2E.md`](TELEGRAM_NEWS_LIVE_E2E.md) |
| Legacy TG-3.1 (`telegram_live`) | historically `TELEGRAM_OUTBOX_KINDS=test`; news не шлёт |
| Root `.env` / stand DB | **не** менялись |
| UI `/notifications` | честное описание узкой политики v1 + серверный флаг |

---

## 6. Проверки

`python -m pytest tests/test_telegram_news_policy.py tests/test_telegram_tg2.py` → **31 passed** (временная БД, mocked Telegram).

Покрыто: eligible risk; neutral/demo/severity-only/profile-like/null/zeros; старая новость + новый Impact; поздний импорт; connect/re-enable без backfill; повтор enqueue + IntegrityError + rollback; membership revoke (с restore) / mute / unlink; quiet hours defer; reclassify после постановки; отсутствие Scenario/Decision side effects; settings policy fields.

`npm run build` (web) — OK.

Синтетические события только в тестах (`evt_synth_tg4_*`); профиль «упк» и live-новости стендов не подгонялись.

---

## 7. Ограничения / следующий шаг

- Настоящие новостные сообщения **не** отправлялись.
- News-worker на `:8027` / `:8020` **не** включался.
- Отдельный контролируемый прогон одного news-уведомления и подключение Telegram к основному стенду — **вне** этого этапа (по запросу).

### Причины отказа (справочник)

`feature_disabled`, `not_private_channel`, `subscription_inactive`, `chat_missing`, `risks_disabled`, `membership_missing`, `company_mismatch`, `muted`, `event_demo`, `event_inactive`, `event_not_risk`, `impact_not_usable`, `score_kind_not_company_calculated`, `below_threshold`, `watermark_missing`, `publication_time_unknown`, `arrival_time_unknown`, `novelty_publication_before_watermark`, `novelty_arrival_before_watermark`, `quiet_hours` (defer), `news_ineligible:*` (send), `chat_mismatch`, …

### Файлы

- `alembic/versions/010_telegram_news_auto_notify.py`
- `app/services/telegram_news_policy.py`
- `app/services/notifications.py`, `app/workers/notification_worker.py`
- `app/services/impact.py`, `app/api/v1/notifications.py`, `app/api/v1/companies.py`
- `app/models/notification.py`, `app/core/config.py`, `.env.example`
- `web/src/pages/NotificationsPage.tsx`, `web/src/api/endpoints.ts`
- `tests/test_telegram_news_policy.py` (+ правки isolation в `test_telegram_tg2.py`, `conftest.py`)
