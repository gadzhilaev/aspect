# Telegram live connection (этап ТГ-3 / ТГ-3.1) — отчёт

Дата обновления: **2026-10-24**.  
**Актуальный основной стенд (ТГ-5 finish):** UI **:5180** / API **:8020** / `real_news_613` — см. runbook [`TELEGRAM_NEWS_LIVE_E2E.md`](TELEGRAM_NEWS_LIVE_E2E.md) (controlled отключён; авто-news только для подписки «упк»; kinds=`test,news`).  
Ниже — история **legacy** стенда ТГ-3.1 (`:5187` / `:8027` / `telegram_live.db`).  
Контракт ТГ-2: [`TELEGRAM_LINK_AND_TEST.md`](TELEGRAM_LINK_AND_TEST.md).

| Режим | Назначение |
|-------|------------|
| **Polling** (`getUpdates`) | Локальный / DX, когда публичного HTTPS нет |
| **Webhook** (`POST /api/v1/telegram/webhook` + secret) | Размещённый сервер с публичным HTTPS |

Оба режима вызывают **один** обработчик: `app.services.telegram_updates.handle_telegram_update`.  
Взаимоисключающие: polling **не** стартует, если `getWebhookInfo.url` непустой (без авто-`deleteWebhook`).

---

## Статус сейчас (можно жать Connect → Start)

| Компонент | Состояние |
|-----------|-----------|
| UI | **http://127.0.0.1:5187/notifications** → API **http://127.0.0.1:8027** (проверено: Vite client содержит `8027`, не `8003`) |
| Логин | `demo@kontur.app` / `DemoKontur1!` |
| Polling | **Запущен** (`python -m app.workers.telegram_polling`), PID в `data/telegram_live/pids.json` |
| `getWebhookInfo` при старте | url **пустой** → polling разрешён |
| Worker outbox (legacy) | `TELEGRAM_OUTBOX_KINDS=test` |
| Новостной enqueue (legacy) | Выключен; на основном стенде — см. `TELEGRAM_NEWS_LIVE_E2E.md` |
| Агент test-send | **Не** отправляет — только ваша кнопка на сайте |

**Действие пользователя:** «Подключить Telegram» → Start у бота в личном чате → дождаться connected → «Отправить тестовое сообщение».  
Тестовый текст без кнопки-ссылки (публичного сайта нет; localhost в кнопку не подставляется).

Остановка: `data/telegram_live/STOP.txt` (включая polling).

---

## ТГ-3.1 — что сделано в коде

- Общий handler: `app/services/telegram_updates.py`
- HTTP webhook тонкий: secret обязателен → тот же handler
- Polling: `app/workers/telegram_polling.py`
  - проверка `getWebhookInfo` до старта;
  - один процесс (PID lock);
  - offset в `polling_offset.json` **после** успешной обработки;
  - повтор `update_id` в процессе не повторяет side effects;
  - backoff на временные HTTP-ошибки;
  - SIGINT/SIGTERM; без публичных портов;
  - логи без token / pairing / текста сообщений (`httpx` logger → WARNING).
- Тесты (mocked): `tests/test_telegram_polling.py` — conflict webhook, lock, offset, duplicate, transient error, shared webhook path.
- Лаунчер: `scripts/run_telegram_live_polling.ps1`

Pytest: polling + tg2 — **passed**.

---

## История ТГ-3 (туннель)

Cloudflare quick tunnel **не** заработал (DNS SRV / TLS EOF при `happ-xray`). VPN/DNS/firewall **не** менялись; обходы сети прекращены.  
Ранее Auto-review блокировал установку cloudflared до явного разрешения (токен в промпте).

---

## Секреты

Токен только в `data/telegram_live/.env.secrets` (gitignored).  
При первом старте polling httpx INFO один раз записал URL с token в `polling.err.log` — файл **очищен (redacted)**, уровень httpx снижен. Рекомендуется ротация token в BotFather при сомнении.

---

## После ручного test-send

Ожидаемо: outbox `kind=test` → worker → `sent` (accept Bot API ≠ прочтение).  
Затем для продакшена: публичный webhook + worker; авто-новости — отдельный этап.
