# Backend release checklist (pre-commit handoff)

Дата проверки: **2026-10-24**  
Ветка: `main` (tip remote при handoff: `5f768ea`).  
**Не называть текущее рабочее дерево зафиксированным релизом** — commit/push ещё не делались.

Связанные отчёты: [`BACKEND_REGRESSION_FIX.md`](BACKEND_REGRESSION_FIX.md), [`FINAL_COMPOSE_VERIFICATION.md`](FINAL_COMPOSE_VERIFICATION.md).

---

## Что проверено

| Пункт | Результат |
|-------|-----------|
| OpenAPI / MOBILE handoff | Актуален с предыдущего этапа |
| Backend pytest (regression fix) | **698 passed**, **4 skipped**, **0 failed** |
| Telegram-related pytest после Compose | **46 passed** (polling/worker/tg2/policy/dedupe) |
| Competition images build (api+web) | **PASS** (с TG entrypoints) |
| Telegram Compose smoke (мок, отдельный volume) | **PASS** (`run_telegram_compose_smoke.ps1`) |
| Live LLM / live Telegram | **Не** вызывались |
| Git hygiene | секреты/БД/стенды gitignored |

---

## Compose-поставка (факт)

Default: `api` + `web` + `news_scheduler`.  
Optional profile **`telegram`**: `telegram_worker` + `telegram_polling` (существующие модули; token runtime-only).  
Polling XOR webhook. Без token Telegram **не** стартует автоматически.

Команды: [`BACKEND_DEPLOYMENT_HANDOFF.md`](BACKEND_DEPLOYMENT_HANDOFF.md) §8, jury runbook §7.

---

## Skipped (полный pytest)

Все 4 — нет `ALEMBIC_POSTGRES_URL` (Postgres path **не** проверен).

---

## Что остаётся перед публичным размещением

1. Явный **git commit** (без секретов/data stands).  
2. Публичный HTTPS URL + `PUBLIC_WEB_BASE_URL` + CORS.  
3. Runtime secrets: `SECRET_KEY`, `HACKATHON_API_KEY` (если live), `TELEGRAM_BOT_TOKEN`.  
4. Выбор ingress: polling (profile telegram) **или** webhook на API.  
5. `alembic upgrade head` на постоянной БД; backup volume.  
6. Внешние CSV/PDF/OCR/QA для jury bootstrap.  
7. Опционально Postgres smoke.

---

## Известные ограничения

- Single-host SQLite; Postgres не проверен.  
- Незакоммиченный код ≠ релиз.  
- Flutter E2E не прогонялся.  
- Публичный адрес: **будет задан после размещения**.

---

## Рекомендуемый smoke после размещения

1. `GET /health`  
2. `GET /openapi.json`  
3. register/verify/login  
4. public news + ingestion status  
5. company → dashboard → assistant  
6. (если TG profile) link-token / test-send; один polling XOR webhook  
7. scheduler: не `failed` длительно  

---

## Файлы для передачи

**Mobile:** `contracts/openapi.json`, `docs/MOBILE_API.md`, `docs/MOBILE_BACKEND_HANDOFF.md`  

**Размещение:** `docs/BACKEND_DEPLOYMENT_HANDOFF.md`, `docs/BACKEND_RELEASE_CHECKLIST.md`, `docs/BACKEND_REGRESSION_FIX.md`, `docs/FINAL_COMPOSE_VERIFICATION.md`, `docker-compose.competition.yml`, `docker-compose.telegram_compose_smoke.yml`, `docker/competition/entrypoint-*.sh`, `docs/NEWS_SCHEDULER.md`, `docs/COMPETITION_JURY_RUNBOOK.md`
