# Competition jury pack — итог этапов 6.2–6.3

Дата: 2026-10-22  
Ограничения: без изменения root `.env` / рабочей БД / процессов `:8003`; без live LLM, браузера, CDP, повторного OCR, commit/push.

---

## 1. Что сделано

### Конкурсный профиль

- Настройка `COMPETITION_MODE` (`app/core/config.py`, `.env.example`).
- Модуль `app/services/competition_profile.py`: структурная проверка URL (scheme/host/port/path, без userinfo/query/fragment), allow-list модели, отказ OpenAI/GigaChat/mock до HTTP.
- Guards: `get_provider`, `LiveAssistantProvider`, `GigaChatProvider`, `MockAssistantProvider`, `live_enrich`, `build_hackathon_loop_provider`, `HackathonProvider` / `HackathonLoopProvider`.
- Redirect: клиент по умолчанию `follow_redirects=False`; 3xx → ошибка без переноса `Authorization` на другой host.
- Heuristic enrichment остаётся доступным (`prefer_live=False` / `--heuristic-enrich`).
- Обычный режим (`COMPETITION_MODE=false`) сохранён.
- Стенд: `COMPETITION_MODE=true` + относительные пути в `stand.env` / `prepare_agent_demo_stand.py`.

### THIRD_PARTY_NOTICES

- Файл в корне: инвентаризация backend/frontend, OCR, gateway/моделей, CSV/PDF, шрифтов/иконок, Docker-образов.
- Лицензии — из metadata/LICENSE/lock где удалось; иначе «условия требуют уточнения».
- Явно: это **не** юридический аудит.

### Единый runbook

- `docs/COMPETITION_JURY_RUNBOOK.md` + короткий вход в `README.md`.
- Основной маршрут: agent-demo `:8017`/`:5177`.

### Тесты (mocked HTTP)

- `tests/test_competition_profile.py` — 22 passed (без сети к LLM).

---

## 2. Проверки, которые выполнялись

| Проверка | Результат |
|----------|-----------|
| Конкурсный режим + корректные hackathon settings | Settings / `assert_competition_llm_config` OK |
| OpenAI / GigaChat / mock отклоняются | `COMPETITION_LLM_FORBIDDEN` / ValidationError |
| Неверный model / base URL | отклонение до HTTP |
| `live_enrich` в competition | отказ, transport не вызывался |
| Redirect | один hop на gateway, key не ушёл на `evil.example` |
| Heuristic enrich | работает при competition |
| Обычный mock без competition | совместимость |
| Пути скриптов runbook (наличие файлов) | `prepare` / `run_*` / `stop` / `check` / `preflight` существуют |
| Чистая установка pip/npm / Docker build | **не** выполнялись в 6.2 |
| Live LLM / ingestion в рабочую БД | **не** выполнялись |

---

## 3. Компоненты с неизвестными / неполными условиями

См. §K в `THIRD_PARTY_NOTICES`, кратко:

- `psycopg2-binary` (не был в inventory-venv)
- Organizers gateway + underlying model weights
- Styrene corporate fonts (не в репо)
- Docker base image ToS
- Competition raw CSV/PDF redistribution
- Часть `@types/*` / транзитивных npm

---

## 4. Переносимость и блокеры

| Критерий | Состояние |
|----------|-----------|
| Документация notices | Есть (`THIRD_PARTY_NOTICES`) |
| Политика провайдеров в коде | Есть (`COMPETITION_MODE`) |
| Единый runbook | Есть |
| **Подготовка данных из явных файлов (6.3)** | **Пройдена** на этой машине: `docs/COMPETITION_STAND_BOOTSTRAP.md`, стенд `data/competition_stand/jury_63b` |
| **Чистый запуск машины жюри (pip/npm/Docker)** | **Не пройден / не заявлялся** в 6.2–6.3 |
| Docker полный конкурсный стек | **Нет** — compose = db+api(:8000)+worker |
| Python lockfile | **Есть** (`requirements.lock` / `requirements-dev.lock`); install из lock на Windows — 6.4 |
| npm lockfile | Есть (`web/package-lock.json`); `npm ci`+build в temp — 6.4 |

### Этап 6.3 (данные)

`scripts/bootstrap_competition_stand.py` строит новую SQLite из CSV+PDF+OCR+QA без e2e DB.  
Verify TestClient без model HTTP — ok; relocate каталога — ok.  
Оставшиеся блокеры сдачи: Docker **build/smoke** (конфиг 6.5 есть, CLI не было), полный импорт в Docker, другая машина.

---

## 5. Связанные файлы

| Файл | Роль |
|------|------|
| `app/services/competition_profile.py` | Политика |
| `THIRD_PARTY_NOTICES` | Инвентаризация |
| `docs/COMPETITION_JURY_RUNBOOK.md` | Запуск для жюри (после 6.3 — без e2e462) |
| `docs/COMPETITION_STAND_BOOTSTRAP.md` | Явные входы / bootstrap / verify |
| `docs/COMPETITION_REQUIREMENTS_STATUS.md` | Статусы критериев |
| `tests/test_competition_profile.py` | Mocked competition mode |
| `tests/test_competition_stand_bootstrap.py` | Fixture + pack/preflight |
