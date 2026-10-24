# Конкурсный runbook для жюри

Один основной маршрут: **competition stand (этап 6.3)**  
подготовка из явных файлов → запуск → вход → событие → (пустое обсуждение / live отдельно) → банковские источники → оригинальный PDF.

Подробности подготовки: `docs/COMPETITION_STAND_BOOTSTRAP.md`.  
Legacy agent-demo из e2e462 (`docs/AGENT_DEMO_RUNBOOK.md`) **не** обязателен.

**Не утверждается:** «≤15 минут на чистой машине» — измерялась только подготовка данных (~17 мин case+bank на этой машине).  
**Не утверждается:** сайт = реальная интеграция / SSO Альфа-Бизнеса.

Root `.env` рабочего демо (`:8003`) **не** переключайте. Стенд использует process env из своего `stand.env`.

---

## 0. Подготовка данных (явные входы)

Нужны локально (не из Git):

| Вход | Пример |
|------|--------|
| 3 CSV | `data/case/raw/` |
| PDF банка | `data/bank_materials/raw/` |
| OCR corpus | `data/bank_materials/ocr/` |
| QA revisions | `data/bank_materials/verification/competition_qa_expanded/` (Policy Rate + Inflation + Consumption; этап 6.7) или только `…/policy_rate_qa/` |

```powershell
python scripts/bootstrap_competition_stand.py --preflight-only `
  --csv-dir data/case/raw `
  --pdf-dir data/bank_materials/raw `
  --ocr-dir data/bank_materials/ocr `
  --qa-dir data/bank_materials/verification/policy_rate_qa `
  --external-uid U_264 --external-uid U_92

python scripts/bootstrap_competition_stand.py `
  --csv-dir data/case/raw `
  --pdf-dir data/bank_materials/raw `
  --ocr-dir data/bank_materials/ocr `
  --qa-dir data/bank_materials/verification/policy_rate_qa `
  --output-dir data/competition_stand/jury_63b `
  --external-uid U_264 --external-uid U_92
```

**Не** копируется verification/e2e DB. **Не** переносится чужая AI-история.  
Пароль: `data/competition_stand/jury_63b/demo_password.local` (не коммитить, не печатать).

Проверка без model HTTP:

```powershell
python scripts/verify_competition_stand.py --stand-dir data/competition_stand/jury_63b
```

---

## 1. Системные требования

| | |
|--|--|
| OS | Windows 10/11 (скрипты); Linux/macOS — те же Python/Node команды |
| Python | **3.12** (зафиксировано: `.python-version` = 3.12.10) |
| Node.js | **≥18.18** (рекомендуется 20/24; `web/.nvmrc`, `web/package.json` → `engines`) |
| OCR / Tesseract | **Не** нужны для запуска готового OCR-корпуса / стенда |
| Повторный OCR | Tesseract + tessdata — только если пересобираете корпус (не runtime) |
| Docker | Опционально; конкурсный стек — `docker-compose.competition.yml` (см. `docs/COMPETITION_DOCKER.md`) |

Подробности clean-env: `docs/CLEAN_ENV_VERIFICATION.md`.  
Docker: `docs/COMPETITION_DOCKER.md` + факт 6.14: `docs/COMPETITION_DOCKER_VERIFICATION.md`  
(Engine OK; **build + fixture smoke PASS**; полный CSV-импорт / live AI в Docker — отдельно).

---

## 2. Установка зависимостей

Используйте **lock-файлы** (не «живой» `pip freeze` с рабочей машины):

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
# Runtime (стенд / API):
pip install --require-hashes -r requirements.lock
# Dev/test (+ pytest, Pillow для синтетических фикстур):
# pip install --require-hashes -r requirements-dev.lock
cd web
npm ci
cd ..
```

Прямые пины: `requirements.in` / `requirements.txt`.  
Пересборка lock (изолированный venv + pip-tools):  
`pip-compile --generate-hashes -o requirements.lock requirements.in`  
`pip-compile --generate-hashes -o requirements-dev.lock requirements-dev.in`  

`web/package-lock.json` — для `npm ci`.  
Ключ `HACKATHON_API_KEY` — только root `.env` → process (для **опционального** live).

---

## 3. Конкурсный профиль

В `stand.env`: `COMPETITION_MODE=true` → только hackathon + allow-list + exact gateway URL.  
OpenAI/GigaChat/mock и live enrich запрещены до HTTP.  
Офлайн-демо (`mock` без competition) — не «успешный live».

---

## 4. Запуск стенда

### 4.1 Ручная проверка UI (этап 6.11) — предпочтительно

Изолированная копия с 7 AI-eligible фрагментами и **чистым** стартом
(нет Impact / Scenario / Decision / ручных финансов):

```powershell
python scripts/prepare_competition_ui_stand.py
.\scripts\run_competition_ui_backend.ps1    # :8018
.\scripts\run_competition_ui_frontend.ps1   # :5178
```

| | |
|--|--|
| Сайт | http://127.0.0.1:5178 |
| API | http://127.0.0.1:8018/health |
| Login | `competition-demo-a@example.com` |
| Пароль | `data/competition_stand/ui_acceptance_611/demo_password.local` |
| Чеклист | `docs/COMPETITION_UI_ACCEPTANCE.md` |
| Остановка | `.\scripts\stop_competition_ui_stand.ps1` (только 8018/5178) |

Не использует завершённый E2E 6.10 как «чистое начало». Root `.env` / `:8003` не трогает.

### 4.2 Запуск из `jury_63b` (исходный bootstrap)

Порты по умолчанию: **API 8018**, **Web 5178** (не `:8003`).

```powershell
# загрузить jury_63b/stand.env в process, затем:
python -m uvicorn app.main:app --host 127.0.0.1 --port 8018
cd web
$env:VITE_API_BASE_URL="http://127.0.0.1:8018"
$env:VITE_AGENT_DEMO="true"
npm run dev -- --host 127.0.0.1 --port 5178
```

Login: email из `stand_manifest.json`; пароль из `demo_password.local`.  
Диагностика без ключа: `provider` / `key_configured` (секрет не печатать).

---

## 5. Маршрут пользователя (факт API / UI)

Полный сквозной путь (лента → банк → финансы → сценарии → подтверждённое решение)
проверен TestClient на копии стенда: `docs/COMPETITION_FULL_FLOW_E2E.md`
(отчёт `data/bank_materials/verification/e2e610/…`). **UI E2E браузером не заявляется.**

### 5.1 Без финансовых данных

1. Login → компания «Демо-компания A · U_…» (конкурсный U_ID) → `case_context`.  
2. Лента «Для вас»: синтетическое событие ставки по **`case_profile_match`**
   (не Impact; ID не подставлять вместо обнаружения).  
3. Карточка → «Обсудить с Аспектом». Состояние: `calculation_unavailable`.  
4. Вопрос в чате = **live** agent loop (до 4 model HTTP) **или** просмотр без live.  
5. Bank evidence / pinned revision → fragment → PDF (Bearer) + SHA.

### 5.2 Переход к расчёту и решению

6. CTA финансов → `/company/setup?step=finance&event={eventId}`.  
7. Ручные долг / валюта / доля плавающей ставки (не из LOA / выручки / платежей).  
8. «Сохранить и пересчитать оценку» → `PATCH …/finance` (профиль) → **один**
   `POST …/recompute-impact` (это событие) → возврат в обсуждение.  
   Если профиль сохранён, а пересчёт нет — «Повторить пересчёт» без повторного save.  
   GET Impact не создаёт данные. Подробности: `docs/FINANCE_RECOMPUTE_FLOW_FIX.md`.  
9. CTA **«Рассчитать финансовые сценарии»** → `POST …/compare-scenarios` (без LLM).  
10. Выбор сценария → черновик → **Подтвердить**. Без confirm решение не accepted.  
11. DecisionDetail; после повторного входа — история и решение.

Просмотр без live: API/verify без model HTTP. Scripted transport в 6.10 ≠ качество live-модели.

---

## 6. Синтетика vs конкурсные данные

| Синтетика / демо | Конкурсные |
|------------------|------------|
| User, membership, display label компании, событие | CSV каталог, PDF/OCR, QA (Policy Rate + Inflation + Consumption, 7 AI-eligible), marks конкурсного U_* |

AI evidence: Policy Rate (+ QA 6.7). Write-tools **не** в agent loop.  
Финансовый расчёт — явный user `compare-scenarios` (6.6 / 6.10).  
См. `docs/USER_TRIGGERED_FINANCE_SCENARIOS.md`, `docs/COMPETITION_FULL_FLOW_E2E.md`.

---

## 7. Docker (конкурсный стек)

Отдельно от legacy `docker-compose.yml` (Postgres + worker):

- Compose: `docker-compose.competition.yml`  
  - default: **api** + **web** + **news_scheduler** + profile `bootstrap`  
  - optional profile **`telegram`**: `telegram_worker` + `telegram_polling` (существующие модули; токен только runtime)
- Volume: **single-host SQLite** `/stand`  
- Linux lock: `requirements-linux.lock`  
- Docs: `docs/COMPETITION_DOCKER.md`, `docs/BACKEND_DEPLOYMENT_HANDOFF.md`, `docs/FINAL_COMPOSE_VERIFICATION.md`  
- Планировщик: `docs/NEWS_SCHEDULER.md`

| Проверка | Результат |
|----------|-----------|
| Image build API+web (после TG entrypoints) | **PASS** 2026-10-24 |
| Telegram Compose smoke (мок, отдельный volume) | **PASS** (`scripts/run_telegram_compose_smoke.ps1`) |
| Полный импорт реальных CSV в Docker | **Не** выполнялся |
| Live LLM / live Telegram в Docker smoke | **Не** вызывались |
| PostgreSQL path | **Не** проверен |

### 7.1 Базовый серверный путь

```powershell
docker compose -f docker-compose.competition.yml build api web
# после bootstrap volume (нужны внешние CSV/PDF/OCR/QA):
docker compose -f docker-compose.competition.yml up -d api web news_scheduler
curl -fsS http://127.0.0.1:8019/health
docker compose -f docker-compose.competition.yml stop news_scheduler
docker compose -f docker-compose.competition.yml down
```

- Interval scheduler **1200 с**, heuristic only; lock — **single-host**.  
- Внешние CSV/PDF/OCR/QA **не** в Git — без них полный jury bootstrap не стартует.  
- `PUBLIC_WEB_BASE_URL` / HTTPS — **будут заданы после размещения**.  
- Секреты: runtime env / env_file (не образ).

### 7.2 Опциональный Telegram (profile `telegram`)

```powershell
# Только при настроенном токене. Не включать параллельно с активным webhook.
$env:TELEGRAM_BOT_TOKEN = "<runtime-secret>"
$env:TELEGRAM_INGRESS_MODE = "polling"   # или webhook — тогда НЕ поднимайте telegram_polling
$env:TELEGRAM_OUTBOX_KINDS = "test,news"
$env:TELEGRAM_NEWS_NOTIFICATIONS_ENABLED = "false"  # включать осознанно
docker compose -f docker-compose.competition.yml --profile telegram up -d telegram_worker telegram_polling

docker compose -f docker-compose.competition.yml --profile telegram stop telegram_worker telegram_polling
```

Изолированная проверка (мок Bot API, отдельный project/volume, **не** main stand):

```powershell
.\scripts\run_telegram_compose_smoke.ps1
```

Native запуск (§4) остаётся путём без Docker; Docker — воспроизводимый стек после smoke.
