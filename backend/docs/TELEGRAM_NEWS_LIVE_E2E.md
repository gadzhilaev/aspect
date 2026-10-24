# Telegram на основном стенде — live E2E (ТГ-5 → finish)

Дата: **2026-10-24** (controlled-тест завершён и отключён; авто-news включены только для «упк»)  
Стенд: UI **http://127.0.0.1:5180** → API **http://127.0.0.1:8020** → БД `data/competition_stand/real_news_613/stand.db`  
Политика: [`TELEGRAM_NEWS_POLICY.md`](TELEGRAM_NEWS_POLICY.md)  
Runbook процессов: этот файл §6 + [`TELEGRAM_LIVE_CONNECTION.md`](TELEGRAM_LIVE_CONNECTION.md) (legacy TG-3.1 стенд 5187/8027)

---

## 1. Preflight (код vs обещания)

| Обещание | Статус |
|----------|--------|
| `severity=null` исключается из auto-news | `severity_unknown` в `evaluate_news_eligibility` + `tests/test_telegram_news_policy.py` |
| Dedupe outbox не откатывает Impact | `begin_nested()` savepoint; `test_dedupe_conflict_does_not_rollback_impact` |
| Перед send — повторная eligibility | `subscription_allows_send` для `kind=news` |

---

## 2. Controlled-тест (ТГ-5) — **завершён и отключён**

| | |
|--|--|
| Тип | Синтетическая fixture (`is_demo=true`) — **не** доказательство production-отбора |
| Event | `evt_tg5_controlled_4d76030b9e` |
| Outbox | `25070fab-a967-461b-9563-d24057583012` → **`status=sent`**, `attempts=1` (история; **повторно не отправлять**) |
| Режим | был `TELEGRAM_NEWS_CONTROLLED_PAIR=subscription:event` только на prepare/send |
| Сейчас | **`TELEGRAM_NEWS_CONTROLLED_PAIR=`** (пусто). Файл `telegram_runtime/controlled_pair.env` только фиксирует отключение |
| Preview / result | `telegram_runtime/controlled_preview.json`, `controlled_send_result.json` |
| Кнопка «Открыть разбор» | **нет** — нет рабочего публичного HTTPS сайта для локального стенда (`PUBLIC_WEB_BASE_URL` пуст) |
| Получение в ЛС | подтверждено пользователем |

После отключения demo-события снова отклоняются политикой (`event_demo`).

---

## 3. Автоматические news-уведомления (основной стенд)

### Кому

| | |
|--|--|
| Компания | **упк** (`b76ead25-eaf9-4eea-89f0-70b7bbb0acb0`) |
| Подписка | `6c3814b2-2d0f-4b23-8ba3-7b12aecf72f3` (`telegram_private`, `connected`, `is_active=true`) |
| Другие подписки | на стенде **нет** других private; **автоматически не включались** |

### Политика / порог (не понижался)

| Правило | Значение |
|---------|----------|
| Серверный флаг | `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED=true` (только `telegram_process.env`, **не** root `.env`) |
| Worker kinds | `TELEGRAM_OUTBOX_KINDS=test,news` |
| Порог подписки | `min_severity=medium` (impact_score; Event.severity=null → отказ) |
| Тип события | active `risk`, не demo |
| Impact | usable + `score_kind=company_calculated` |
| Новизна | `occurred_at`/`effective_from` **и** `created_at` ≥ `auto_notify_since` |
| Не новизна | `Impact.computed_at` / время пересчёта **не** подменяют watermark |
| Demo | `event_demo` |
| Quiet hours | defer `next_attempt_at` |
| Публичная кнопка в карточке | **отсутствует** до настройки HTTPS сайта |

### Watermark включения

| | |
|--|--|
| `auto_notify_since` | **2026-10-24T11:45:10.310233Z** (момент включения авто-news) |
| Смысл | события/архив **до** watermark не уходят в Telegram |
| Dry-run до enable | `telegram_runtime/dry_run_before_enable.json` — `eligible_count=0`, demo → `event_demo`, sends=0 |
| Dry-run после | `telegram_runtime/dry_run_after_enable.json` — то же; watermark фактический |
| Verify hooks | `telegram_runtime/enable_verify.json` |

### Enqueue hooks (без искусственной eligible-новости)

| Путь | Вызов |
|------|--------|
| Ingestion personalize | `recompute_event_for_ready_companies` → `enqueue_impact_notifications` |
| Явный recompute | `recompute_events_for_company` → `enqueue_impact_notifications` |

На момент включения подходящих non-demo risk Impact для «упк» **не было** — pending outbox news = 0 (ожидаемо).

### Обновление новостей на стенде

**По расписанию (1200 с)** — отдельный процесс `app.workers.news_scheduler` (heuristic, без LLM).  
Конфиг: `news_scheduler.env`; runbook: [`NEWS_SCHEDULER.md`](NEWS_SCHEDULER.md).  
Ранее лента также наполнялась разовыми verification/ingest скриптами.

---

## 4. Процессы (после finish)

| | |
|--|--|
| Config | `data/competition_stand/real_news_613/telegram_process.env` |
| Secrets | `data/telegram_live/.env.secrets` (runtime only) |
| API :8020 | `scripts/run_main_stand_api_with_telegram.ps1` — news_auto=true |
| Polling | **1×** `scripts/run_main_stand_telegram_polling.ps1` |
| Worker | **1×** `scripts/run_main_stand_telegram_worker.ps1` — kinds=`test,news` |
| PIDs | `data/competition_stand/real_news_613/telegram_runtime/pids.json` |
| Legacy TG-3.1 (5187/8027) | не основной путь; см. `TELEGRAM_LIVE_CONNECTION.md` |

---

## 5. Backup / миграция

| | |
|--|--|
| Backup | `data/competition_stand/real_news_613/backups/stand_pre_tg5_20261024T111229Z.db` |
| Alembic | **010** (`auto_notify_since`) |

---

## 6. Runbook: отключить уведомления / остановить worker и polling

### Выключить авто-news (оставить pairing/test)

1. В `telegram_process.env`: `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED=false` и/или `TELEGRAM_OUTBOX_KINDS=test`.
2. Перезапустить API `:8020` (`run_main_stand_api_with_telegram.ps1`) и worker (`run_main_stand_telegram_worker.ps1`), чтобы подтянуть env.
3. Опционально: UI → пауза / `is_active=false` на подписке «упк» (сдвиг watermark при повторном включении — см. policy).

### Остановить Telegram-процессы основного стенда

```text
scripts/stop_main_stand_telegram.ps1
```

Останавливает main polling + notification worker (и сиротские `telegram_polling` / `notification_worker`).  
API `:8020` этим скриптом **не** гасится — остановите uvicorn отдельно, если нужно.

### Вернуть legacy TG-3.1 polling (другая БД)

```text
scripts/stop_main_stand_telegram.ps1
scripts/run_telegram_live_polling.ps1
```

Не держите два polling на одном bot token.

### Не делать

- Не включать controlled-pair снова для «проверки».
- Не переотправлять outbox `25070fab-…`.
- Не понижать `min_severity` ради отправки.
- Не править root `.env` ради стенда; не commit/push секретов.

---

## 7. Ограничения

- Синтетический TG-5 ≠ production-отбор реальных новостей.
- Live LLM / туннели / commit/push в этом этапе — нет.
- Публичная deep-link кнопка — после HTTPS сайта.
