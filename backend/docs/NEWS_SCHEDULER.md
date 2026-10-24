# Планировщик новостей (heuristic, без LLM)

Дата: **2026-10-24** (финальная сверка источников + Docker smoke)  
Стенд: UI **:5180** / API **:8020** / БД `data/competition_stand/real_news_613/stand.db`  
Связано: [`TELEGRAM_NEWS_LIVE_E2E.md`](TELEGRAM_NEWS_LIVE_E2E.md), [`COMPETITION_JURY_RUNBOOK.md`](COMPETITION_JURY_RUNBOOK.md)

---

## Механизм и интервал

| | |
|--|--|
| Процесс | **Отдельный** `python -m app.workers.news_scheduler` (не цикл внутри FastAPI) |
| Pipeline | `run_ingestion(..., prefer_live_enrich=False, personalize=True)` |
| Enrich | Только **heuristic_v2**; на стенде `COMPETITION_MODE=true` |
| Интервал | **1200 с** (`NEWS_SCHEDULER_INTERVAL_SECONDS`) |
| Single-flight | **OS advisory lock** на файле в общем volume (`InterprocessFileLock`: `fcntl` / `msvcrt`) — **не** PID-liveness |
| После простоя | Один тик после sleep — без догона интервалов |
| Busy | `skipped_busy`; **partial ≠ success** (`last_success_at` только при `success`) |

Конфиг стенда (не root `.env`): `data/competition_stand/real_news_613/news_scheduler.env`  
Статус/locks: `…/news_scheduler_runtime/`

**Ограничение lock:** single-host Compose / общая ФС volume. **Multi-host не поддерживается** (PID namespaces и сетевые ФС без flock не заявляются).

---

## Фактический список источников

### CbrProvider (один раз)

- FX daily XML, key rate HTML, **CBR news RSS** (`https://www.cbr.ru/rss/RssNews`)

### GdeltProvider

- Запросы из `INGESTION_GDELT_QUERIES` (defaults / stand).  
- 429 + `Retry-After` (cap); ошибка → вклад в **partial**, не «зелёный» success.

### RssProvider (whitelist стенда)

Из `stand.env` / compose default (**без** повторного CBR RSS — pipeline вырезает `cbr.ru/rss/*`):

| Feed | Роль |
|------|------|
| `https://www.interfax.ru/rss.asp` | деловая лента (проверена ранее) |
| `https://www.wto.org/library/rss/latest_news_e.xml` | ВТО, primary |
| `https://customs.gov.ru/press/federal/rss` | ФТС, primary |
| `https://ec.europa.eu/commission/presscorner/api/rss?dossier=trade&language=en` | EC **presscorner** (проверенный URL) |

**EC:** параметр `dossier=trade` **не фильтрует** темы — ленту **нельзя** называть торговой; это общая presscorner-выдача. Политика доверия / official gate **не** расширялись; новых источников сверх уже проверенных нет. Vedomosti остаётся в `.env.example` как опция размещения, на основном стенде **не** включена.

Лимиты: HTTP timeout ~20 с, `max_per_feed` / `max_per_query`, `pending_limit=100`, ETag/Last-Modified cache.

Персонализация: только `Company.profile_status=ready` (не 85k case-org).  
Telegram: существующие hooks; на основном стенде авто-news только **упк**.

---

## API и лента

| | |
|--|--|
| `GET /api/v1/public/ingestion-status` | read-only |
| `GET /api/v1/public/news` → `ingestion` | то же |
| UI | «Источники проверялись: …» |

---

## Тесты (локально)

`pytest tests/test_news_scheduler.py` — **14 passed** (locks, partial, dedupe, no model HTTP, CBR overlap skip).

---

## Первый прогон на основном стенде (ранее)

| | |
|--|--|
| `--once` | **partial** (GDELT 429) — `last_success_at=null` |
| Counts | fetched=72, inserted=32, dup=40, published=12 |
| Model HTTP | нет |

---

## Docker smoke (изолированный project)

Файл: `docker-compose.news_scheduler_smoke.yml`  
Project: `kontur_news_sched_smoke` · volume: `kontur_news_sched_smoke_stand`  
**Не** main stand DB, **не** Telegram, fixtures only (`NEWS_SCHEDULER_USE_FIXTURES=1`).

Результат (2026-10-24): **PASS** — отчёт `data/competition_stand/news_scheduler_smoke_out/news_scheduler_smoke_report.json`

| Проверка | Результат |
|----------|-----------|
| API + tick → одна тестовая SQLite на volume | PASS |
| API читает статус из общего `NEWS_SCHEDULER_STATE_DIR` | PASS |
| Concurrent run → `skipped_busy` | PASS |
| Process file-lock между holders | PASS |
| Повтор tick → duplicates, raw стабилен | PASS |
| Persist после recycle engine / API restart | PASS |
| Model HTTP / Telegram | выключены |

```powershell
$env:COMPOSE_PROJECT_NAME="kontur_news_sched_smoke"
docker compose -f docker-compose.news_scheduler_smoke.yml run --rm prepare
docker compose -f docker-compose.news_scheduler_smoke.yml up -d --no-deps api
docker compose -f docker-compose.news_scheduler_smoke.yml run --rm --no-deps smoke
docker compose -f docker-compose.news_scheduler_smoke.yml down -v
```

---

## Рекомендуемый запуск на сервере (один путь)

**Docker Compose competition** (после bootstrap стенда в volume):

1. Image `kontur-competition-api:local` (см. `COMPETITION_DOCKER.md`).  
2. Один project, volume `/stand` общий для **api** и **news_scheduler**.  
3. Env (минимум):

```text
DATABASE_URL=sqlite:////stand/stand.db
COMPETITION_MODE=true
ASSISTANT_PROVIDER=hackathon
NEWS_SCHEDULER_INTERVAL_SECONDS=1200
NEWS_SCHEDULER_STATE_DIR=/stand/news_scheduler_runtime
INGESTION_RSS_FEEDS=<Interfax|WTO|ФТС|EC presscorner — как выше>
TELEGRAM_* — по политике стенда; smoke держит news=false
```

4. Сервисы: `api` + `news_scheduler` (`restart: unless-stopped`) из `docker-compose.competition.yml`.  
5. Не запускайте второй scheduler на том же volume.

Остановка:

```text
docker compose -f docker-compose.competition.yml stop news_scheduler
# или полный стек:
docker compose -f docker-compose.competition.yml down
```

### Windows main stand (ручной процесс)

```text
scripts/stop_main_stand_news_scheduler.ps1
scripts/run_main_stand_news_scheduler.ps1 --once   # опционально
scripts/run_main_stand_news_scheduler.ps1
```

**Нет** автозапуска после reboot Windows без внешней службы/Task Scheduler.

---

## Volumes / env (чеклист)

| | |
|--|--|
| Volume | SQLite stand + `news_scheduler_runtime/` (status, locks, http validators) |
| API | обязан видеть тот же `NEWS_SCHEDULER_STATE_DIR` |
| Scheduler | heuristic only; `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED` не расширять «для smoke» |

---

## Чего нет

- Live LLM в цикле scheduler  
- Multi-host locking  
- Подмена partial→success  
- Двойной опрос CBR news через RssProvider  
- Commit/push / правка root `.env` / пользовательских подписок в этом этапе
