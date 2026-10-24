# Agent-loop demo stand (Этапы 4.7–4.8)

Дата: 2026-10-22  
Назначение: отдельный локальный стенд для ручного прохождения  
вход → синтетическая новость → чат с agent loop → банковский фрагмент → PDF.

Этап **4.8** добавляет discoverability без ручного event ID: empty-state ссылки
на общую ленту и (только на этом стенде) панель `/agent-demo`.  
Подробности: `docs/EVENT_DISCOVERABILITY.md`.

**Не** переключает рабочий backend `:8003` и обычный web `:5173`.  
**Не** запускает новые live LLM-запросы автоматически.  
Root `.env` и `web/.env` **не** перезаписываются.

Исходный live-результат 4.6.2: `docs/ASSISTANT_AGENT_LIVE_RECHECK.md` (источник БД).  
Исходный stopped 4.6: `docs/ASSISTANT_AGENT_LIVE_E2E.md` — не трогался.

---

## 1. Подготовка данных

```powershell
# из корня репозитория
python scripts/prepare_agent_demo_stand.py
```

Что делает:

| Артефакт | Путь |
|----------|------|
| Копия БД (SQLite `backup()`) | `data/agent_demo/agent_demo.db` |
| Storage PDF | `data/agent_demo/storage/.../ALFA-Macro_Insights-Policy_Rate_11Sep.pdf` |
| Профиль процесса backend | `data/agent_demo/stand.env` |
| Указатель API для Vite | `data/agent_demo/web.env` |
| Манифест ID (без ключей) | `data/agent_demo/stand_manifest.json` |

Источник **не** меняется: `data/bank_materials/verification/e2e462/assistant_agent_live_recheck.db`.

### Синтетические данные (не конкурсные)

- Компания «Синтетика Агент Loop 4.6.2», catalog uid `U_460`, marks LOA=true / DEP=false.
- Событие `[СИНТЕТИЧЕСКИЙ ТЕСТ 4.6.2]…`, `occurred_at=2026-09-20`.
- **Нет** `EventImpact` (по дизайну).
- История чата содержит **ранее полученный** ответ этапа 4.6.2 — это не новая генерация 4.7.
- Банковские QA-фрагменты Policy Rate из тестового корпуса.

Актуальные ID всегда берите из `stand_manifest.json` → `resolved` (скрипт читает связи из БД).

---

## 2. Порты стенда (явные)

| Сервис | Порт | Обычный демо |
|--------|------|--------------|
| API | **8017** | 8003 |
| Web | **5177** | 5173 |

Если порт занят — скрипт **отказывается** запускаться (без kill чужих процессов и без смены порта).

---

## 3. Runtime (без секретов в docs)

Из `stand.env` + ключ из root `.env` (только в process env лаунчера):

| Параметр | Значение |
|----------|----------|
| `DATABASE_URL` | sqlite → `data/agent_demo/agent_demo.db` |
| `COMPETITION_MODE` | `true` (этап 6.2 — только hackathon + allow-list + exact URL) |
| `ASSISTANT_AGENT_LOOP` | `true` |
| `ASSISTANT_PROVIDER` | `hackathon` |
| `HACKATHON_MODEL` | `deepseek/deepseek-v4.1-flash` |
| `HACKATHON_BASE_URL` | `https://changellenge.up.railway.app/v1` |
| лимиты loop | 4 HTTP / 3 tools / 1 repair / 90 s |
| `CASE_CONTEXT_SLOT_KEY` | `competition_default` |
| `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS` | из БД (Policy Rate run) |
| `BANK_MATERIALS_STORAGE_ROOT` | `data/agent_demo/storage` |
| `AGENT_DEMO_STAND` | `true` (этап 4.8 — API панели входа) |
| `AGENT_DEMO_EVENT_ID` | из `stand_manifest.json` → `resolved.event_id` |
| `HACKATHON_API_KEY` | **только** root `.env` → process; не в stand-файлах / web / docs |

Frontend process (`run_agent_demo_frontend.ps1` / `web.env`):

| Параметр | Значение |
|----------|----------|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8017` |
| `VITE_AGENT_DEMO` | `true` (маршрут `/agent-demo`; обычный product build без флага) |

Проверка конфигурации:

```powershell
.\scripts\check_agent_demo_config.ps1
```

---

## 4. Запуск и остановка

### Команды пользователя

```powershell
# 1) подготовка (один раз / после обновления 4.6.2 DB)
python scripts/prepare_agent_demo_stand.py

# 2) проверка профиля (без серверов)
.\scripts\check_agent_demo_config.ps1

# 3) HTTP preflight без model HTTP (TestClient, без фоновых процессов)
python scripts/agent_demo_preflight.py

# 4) backend стенда (отдельный терминал)
.\scripts\run_agent_demo_backend.ps1

# 5) frontend стенда (второй терминал)
.\scripts\run_agent_demo_frontend.ps1

# 6) остановка только :8017 / :5177 этого стенда
.\scripts\stop_agent_demo.ps1
```

Адреса:

- API health: http://127.0.0.1:8017/health  
- Сайт: http://127.0.0.1:5177  

Возврат к обычному демо: остановите стенд (`stop_agent_demo.ps1`), запускайте как раньше `.\scripts\run_backend.ps1` + `web\run_web.ps1` на `:8003` / `:5173`.

---

## 5. Demo-вход

| | |
|--|--|
| Email | см. `stand_manifest.json` → `resolved.email` (пример: `e2e462_…@example.com`) |
| Password | `E2eAgent462!` |

Пароль — тестовый seed 4.6.2, не production secret.

---

## 6. Выполненные проверки (этап 4.7)

Preflight: `data/agent_demo/preflight_report.json` — **ok**, `model_http_attempts=0`.

Проверено HTTP/TestClient:

- health;
- login + membership (company context `profile_available`);
- карточка события с `company_id` (без impact);
- чтение сохранённого финала + `bank_evidence_list`;
- fragment + PDF: Bearer 200, без Bearer 401, SHA PDF совпал;
- frontend `VITE_API_BASE_URL` → `http://127.0.0.1:8017`;
- runtime: provider=hackathon, loop=true, model/base_url без ключа;
- ключ: `key_configured` отдельно от «live уже проверен в 4.6.2».

**Не** делалось в 4.7: новый вопрос в чат, live LLM, браузер/CDP/скриншоты, OCR.

### Диагностика провайдера

| Утверждение | Статус |
|-------------|--------|
| Ключ настроен в root `.env` | да/нет по `key_configured` |
| Endpoint gateway известен | `HACKATHON_BASE_URL` в runtime |
| Live-генерация ранее проверена | да — этап 4.6.2 |
| Новая live-проверка в 4.7 | **нет** |

---

## 7. Ручной маршрут кликами (без ручного event ID)

Визуальная проверка UI **не** объявляется пройденной.  
Путь ниже — ожидаемая навигация; HTTP/API для тех же сущностей проверены TestClient.

### Предпочтительный путь (панель демостенда, этап 4.8)

1. Откройте http://127.0.0.1:5177/login  
2. Войдите email/password из `stand_manifest.json` → `resolved.email` / `E2eAgent462!`.  
3. После входа откроется **Демостенд** (`/agent-demo`) — синтетика явно помечена.  
4. Нажмите **«Открыть новость»** → карточка `/news/{event_id}` (без ввода ID).  
5. На карточке **«Обсудить с Аспектом»** → `/events/{event_id}/assistant`  
   **или** с панели: **«Сохранённое обсуждение»** / **«История в Сценарии»**.  
6. В чате — сохранённая история 4.6.2 (вопрос + финал). Это **ранее полученный** ответ, не новая генерация.  
7. В блоках ответа: банковский материал → страница fragment → оригинал PDF (сессия/Bearer).  
8. **По желанию** новый вопрос в чате = live LLM (до 4 model HTTP). Не оценивайте ₽ без тарифа.

### Альтернатива без панели (общая лента / поиск / история)

1. После логина: **Новости** в шапке → `/news`  
   (или из пустой «Для вас»: кнопка **«Все новости»**).  
2. На стенде в БД одно active-событие — синтетическая карточка в общей ленте.  
   Либо поиск в шапке: `СИНТЕТИЧЕСКИЙ` → `/news?q=…`.  
3. Открыть карточку → **«Обсудить с Аспектом»**.  
4. Либо **Сценарии** → сохранённое обсуждение (без фиктивного impact score) → продолжить / открыть новость → PDF из блоков.

«Для вас» остаётся пустой **намеренно** (нет EventImpact) — это не путь к синтетике.

---

## 8. Таблица статуса

| Что | Готово в коде | Проверено HTTP | Проверено live ранее | Ещё ручная проверка |
|-----|:-------------:|:--------------:|:--------------------:|:-------------------:|
| Копия БД 4.6.2 + storage/SHA | ✓ | ✓ | — | — |
| Профиль loop+hackathon+slot+OCR | ✓ | ✓ | — | — |
| Порты 8017/5177, отказ при занятости | ✓ | — | — | при запуске |
| Login / membership / case context | ✓ | ✓ | — | UI |
| Карточка синтетического события | ✓ | ✓ | — | UI |
| Сохранённый финал + bank_evidence_list | ✓ | ✓ | 4.6.2 | UI |
| Fragment / PDF + ACL | ✓ | ✓ | 4.6.2 | UI |
| Agent loop tool→final | ✓ | — | **4.6.2** | новый вопрос опционально |
| Discoverability без ручного ID (4.8) | ✓ | ✓ | — | UI |
| Панель `/agent-demo` (только stand env) | ✓ | ✓ | — | UI |
| Внешний вид сайта / навигация | — | — | — | **да** |

---

## 9. Ограничения

- Один успешный 4.6.2 ≠ стабильность продукта.
- Синтетика ≠ реальные конкурсные компании/новости.
- Исторический ответ в БД ≠ новая генерация при открытии.
- Новый чат-запрос тратит бюджет gateway.
- Обычный `kontur.db` / `:8003` / root `.env` / `web/.env` этим стендом не меняются.
- `VITE_AGENT_DEMO` / `AGENT_DEMO_STAND` не включать в обычный product demo.
- Остановка: только процессы, похожие на стенд на `:8017` / `:5177`.
