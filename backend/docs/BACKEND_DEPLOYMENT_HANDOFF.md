# Handoff: backend → размещение

Дата: **2026-10-24**  
Основа: `docker-compose.competition.yml`, [`COMPETITION_JURY_RUNBOOK.md`](COMPETITION_JURY_RUNBOOK.md), [`NEWS_SCHEDULER.md`](NEWS_SCHEDULER.md), [`FINAL_COMPOSE_VERIFICATION.md`](FINAL_COMPOSE_VERIFICATION.md)

Публичный URL API/сайта: **будет задан после размещения**.  
Ключи в образ / frontend / этот документ **не** класть.

**Незакоммиченный код ≠ зафиксированный релиз.**

---

## 1. Что входит в Compose-поставку

| Сервис | В Compose | Как включить |
|--------|-----------|--------------|
| `bootstrap` | profile `bootstrap` | one-shot подготовка stand volume |
| `api` | да (default) | FastAPI / uvicorn `:8000` |
| `web` | да (default) | nginx static frontend |
| `news_scheduler` | да (default) | heuristic ingest каждые 1200 с |
| `telegram_worker` | profile **`telegram`** | `python -m app.workers.notification_worker` (loop в entrypoint) |
| `telegram_polling` | profile **`telegram`** | `python -m app.workers.telegram_polling` |
| Telegram **webhook** | код в API | публичный HTTPS + secret; **не** отдельный compose-сервис |

Default `up` **не** поднимает Telegram. Нужны runtime secrets + `--profile telegram`.

### Polling XOR webhook

- `TELEGRAM_INGRESS_MODE=polling` (default для profile) → `telegram_polling` + `telegram_worker`.  
- `TELEGRAM_INGRESS_MODE=webhook` → **не** запускайте `telegram_polling` (entrypoint exit 3); worker можно оставить для outbox; webhook принимает API.  
- Runtime: `telegram_polling` отказывается, если Bot API `getWebhookInfo.url` непустой (не вызывает `deleteWebhook`).  
- Один bot token → **один** polling **или** активный webhook, не оба.

Host-скрипты main stand (`scripts/run_main_stand_telegram_*.ps1`) — **другая** БД (`real_news_613`); не смешивать с competition volume.

---

## 2. Поддерживаемая среда

- **Single-host** Docker Compose, **SQLite** на общем named volume.  
- File-lock scheduler / polling lock — **не** multi-host / не NFS без flock.  
- **PostgreSQL в этом Compose-пути не проверен** (опциональные pytest skip без `ALEMBIC_POSTGRES_URL`).  
- Images: `kontur-competition-api:local`, `kontur-competition-web:local`.  
- `APP_ENV` ∈ `development` \| `test` \| `production`. Конкурсный профиль: `COMPETITION_MODE=true`.

---

## 3. Миграции

До работы API / worker / polling / scheduler на постоянной БД:

```text
alembic upgrade head
```

Актуальный head: **010** (`auto_notify_since`). Bootstrap / entrypoint-api ожидают готовый `/stand/stand.db`.  
Изолированная проверка: `scripts/prepare_telegram_compose_smoke_stand.py` (upgrade → 010).

---

## 4. Постоянные данные (volumes)

| Путь в контейнере | Содержимое |
|-------------------|------------|
| `/stand/stand.db` | SQLite (API + scheduler + outbox + polling handlers) |
| `/stand/storage` | bank PDF / OCR storage |
| `/stand/news_scheduler_runtime/` | scheduler status JSON, locks |
| `/stand/telegram_runtime/` | polling offset + process lock |
| `/stand/stand.env`, `stand_status.json` | bootstrap metadata |

Имя volume: `kontur_competition_stand_data` (`COMPETITION_STAND_VOLUME`).

---

## 5. Env / секреты (имена без значений)

Секреты — **только runtime** (shell / compose env_file / orchestrator secrets). Не в Dockerfile, не в frontend, не в Git.

```text
COMPETITION_MODE=true
ASSISTANT_PROVIDER=hackathon
HACKATHON_BASE_URL=
HACKATHON_MODEL=
HACKATHON_API_KEY=              # runtime; offline допускается пустым
DADATA_API_KEY=                # runtime; поиск компании по ИНН. Пусто → not_configured,
                               # ручной ввод работает. ТОЛЬКО в сервис api (не web/scheduler/telegram).
                               # Не в VITE_*/frontend. См. docs/COMPANY_INN_LOOKUP.md
SECRET_KEY=                    # COMPETITION_SECRET_KEY в compose
DATABASE_URL=sqlite:////stand/stand.db
BANK_MATERIALS_STORAGE_ROOT=/stand/storage
NEWS_SCHEDULER_STATE_DIR=/stand/news_scheduler_runtime
NEWS_SCHEDULER_INTERVAL_SECONDS=1200
INGESTION_RSS_FEEDS=
PUBLIC_WEB_BASE_URL=           # https://… origin; иначе кнопки TG без deep-link
CORS_ORIGINS=

# Telegram (profile telegram) — не включать без токена
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_WEBHOOK_SECRET=       # если webhook ingress
TELEGRAM_INGRESS_MODE=polling  # или webhook
TELEGRAM_WEBHOOK_ACTIVE=false  # true → polling entrypoint refuse
TELEGRAM_OUTBOX_KINDS=test,news
TELEGRAM_NEWS_NOTIFICATIONS_ENABLED=false
TELEGRAM_POLLING_STATE_DIR=/stand/telegram_runtime
TELEGRAM_WORKER_INTERVAL_SECONDS=5
```

Внешние входы **вне Git** (обязательны для полного jury bootstrap): CSV case, PDF, OCR corpus, QA revisions — см. jury runbook §0.

---

## 6. HTTPS и PUBLIC_WEB_BASE_URL

- Публичный сайт/API: TLS на edge — **будет задан после размещения**.  
- `PUBLIC_WEB_BASE_URL` — только `https://…` для кнопок в Telegram.  
- Без него карточки могут уходить без кнопки «Открыть разбор» (ожидаемо на локальных стендах).

---

## 7. Резервное копирование и восстановление

```text
# 1) остановить пишущие процессы
docker compose -f docker-compose.competition.yml stop news_scheduler
docker compose -f docker-compose.competition.yml --profile telegram stop telegram_worker telegram_polling

# 2) скопировать volume (минимум stand.db, storage/, news_scheduler_runtime/, telegram_runtime/)
docker run --rm -v ${COMPETITION_STAND_VOLUME:-kontur_competition_stand_data}:/stand -v ${PWD}/backup:/backup alpine \
  tar -C /stand -czf /backup/stand-$(date +%Y%m%dT%H%M%SZ).tgz .

# 3) зафиксировать image tag / git SHA после будущего commit
```

Восстановление: вернуть файлы volume → при необходимости `alembic upgrade head` → `up -d`.

---

## 8. Запуск / health / стоп / обновление

```text
# build
docker compose -f docker-compose.competition.yml build api web

# после bootstrap volume
docker compose -f docker-compose.competition.yml up -d api web news_scheduler

# опционально Telegram (нужен TELEGRAM_BOT_TOKEN; ingress=polling)
TELEGRAM_BOT_TOKEN=… TELEGRAM_INGRESS_MODE=polling \
  docker compose -f docker-compose.competition.yml --profile telegram up -d telegram_worker telegram_polling

# health
curl -fsS http://127.0.0.1:${COMPETITION_API_HOST_PORT:-8019}/health

# стоп Telegram
docker compose -f docker-compose.competition.yml --profile telegram stop telegram_worker telegram_polling

# стоп scheduler
docker compose -f docker-compose.competition.yml stop news_scheduler

# стоп стека
docker compose -f docker-compose.competition.yml --profile telegram down
```

Обновление: backup → build новых images → migrate → up.  
Изолированный TG smoke (мок, отдельный volume): `scripts/run_telegram_compose_smoke.ps1` → [`FINAL_COMPOSE_VERIFICATION.md`](FINAL_COMPOSE_VERIFICATION.md).  
Scheduler smoke: `docker-compose.news_scheduler_smoke.yml`.

---

## 9. Доступ разработчика к БД

Мобильному / frontend разработчику **не** нужен прямой доступ к SQLite.  
Достаточно API base URL + учётки стенда (пароли вне Git: `demo_password.local`).

---

## 10. Конкурсные файлы вне Git

- CSV case, PDF / OCR / QA  
- `data/competition_stand/*` runtime, пароли, `.env.secrets`, логи  
- Host Telegram secrets (`data/telegram_live/.env.secrets`) — не для competition image  

В Git: код, compose, alembic, contracts, docs, `.env.example`.

---

## 11. Известные ограничения

- Single-host SQLite; Postgres path не проверен.  
- Telegram не стартует без profile + token.  
- Polling XOR webhook.  
- Live LLM только при runtime key; ingest — heuristic.  
- Публичный адрес / TLS — после размещения.  
- Код handoff **может быть незакоммичен** — не называть релизом до commit.
