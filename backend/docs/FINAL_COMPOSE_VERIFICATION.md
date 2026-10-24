# Final Compose verification — Telegram in competition stack

Дата: **2026-10-24**  
Цель: опциональные `telegram_worker` / `telegram_polling` в competition Compose без новых механизмов доставки; изолированный smoke с mocked Telegram.  
**Не** трогались: рабочие БД, root `.env`, main-stand polling/worker PIDs, live bot.  
**Commit/push не выполнялись.**

---

## 1. Что добавлено

| Артефакт | Назначение |
|----------|------------|
| `docker-compose.competition.yml` profile `telegram` | `telegram_worker`, `telegram_polling` на том же volume `/stand` |
| `docker/competition/entrypoint-telegram-worker.sh` | loop `python -m app.workers.notification_worker`; refuse без token |
| `docker/competition/entrypoint-telegram-polling.sh` | `python -m app.workers.telegram_polling`; refuse без token / при `TELEGRAM_INGRESS_MODE=webhook` |
| `docker-compose.telegram_compose_smoke.yml` | отдельный project `kontur_tg_compose_smoke` + volume |
| `scripts/prepare_telegram_compose_smoke_stand.py` | `alembic upgrade head` → **010** |
| `scripts/smoke_telegram_compose.py` | mocked outbox/polling checks |
| `scripts/run_telegram_compose_smoke_incontainer.py` | prepare → gates → api → scheduler once → smoke |
| `scripts/run_telegram_compose_smoke.ps1` | host runner |

Default `compose up` **не** включает Telegram. Нужны `--profile telegram` + `TELEGRAM_BOT_TOKEN`.

---

## 2. Сборка образов

```text
docker compose -f docker-compose.competition.yml build api web
→ kontur-competition-api:local  PASS
→ kontur-competition-web:local  PASS
```

Токены в образ не попадали.

---

## 3. Изолированный smoke (мок)

```powershell
.\scripts\run_telegram_compose_smoke.ps1
# telegram_compose_smoke_exit=0
```

Лог: `data/competition_stand/handoff_reports/telegram_compose_smoke.txt` (gitignore).

| Check | Result |
|-------|--------|
| Миграции до **010** до сервисов | PASS |
| Worker/polling entrypoints на той же `DATABASE_URL=sqlite:////stand/stand.db` | PASS (compose + smoke seed) |
| Outbox `sent` после mocked send; статус после dispose/restart session | PASS |
| Duplicate `update_id` — без повторного handle | PASS |
| Disconnect subscription → outbox `skipped`, без HTTP post | PASS |
| `TELEGRAM_INGRESS_MODE=webhook` → polling rc=3; empty token → worker rc=2 | PASS |
| `assert_polling_allowed` при непустом webhook URL | PASS |
| Scheduler `--once --fixtures` + telegram_runtime на одном volume | PASS |
| Live Telegram / live LLM | **не** вызывались |

---

## 4. Связанные регрессии (pytest)

```text
tests/test_telegram_polling.py
tests/test_telegram_worker_kinds.py
tests/test_telegram_tg2.py
tests/test_telegram_news_policy.py
tests/test_acceptance.py::test_telegram_dedupe
→ 46 passed
```

Полный backend pytest **не** перезапускался: изменения — Compose/entrypoints/smoke-скрипты и docs; общий application path (кроме уже проверенных worker/polling модулей) не менялся. Предыдущий зелёный полный прогон: **698 passed / 4 skipped** (`BACKEND_REGRESSION_FIX.md`).

---

## 5. Команды размещения (кратко)

См. актуальные [`BACKEND_DEPLOYMENT_HANDOFF.md`](BACKEND_DEPLOYMENT_HANDOFF.md) и §7 [`COMPETITION_JURY_RUNBOOK.md`](COMPETITION_JURY_RUNBOOK.md).

Явно:

- **Single-host SQLite** volume.  
- **PostgreSQL не проверен.**  
- Внешние **CSV/PDF/OCR/QA** обязательны для полного bootstrap (вне Git).  
- **HTTPS** + `PUBLIC_WEB_BASE_URL` — будут заданы после размещения.  
- Секреты — runtime env (`TELEGRAM_BOT_TOKEN`, `SECRET_KEY`, `HACKATHON_API_KEY`), не образ.  
- Backup / stop / update — §7–8 deployment handoff.

---

## 6. Ограничения

- Profile telegram без token → контейнеры падают/отказываются (намеренно).  
- Polling XOR webhook.  
- Smoke не поднимает long-running live getUpdates к api.telegram.org.  
- Main stand (`real_news_613`) не использовался.  
- Незакоммиченное дерево ≠ релиз.
