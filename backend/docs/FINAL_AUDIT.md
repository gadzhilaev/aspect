# Финальный audit — Аспект (kontur_back)

**Дата:** 2026-10-19  
**Репозиторий:** `C:\Users\неважно\Desktop\kontur_back`  
**Итоговый статус:** готово к демо

Аудит без браузера/CDP/скриншотов, без commit/push/deploy, без real news ingestion, без печати секретов.

---

## 1. Итоговый статус

**Готово к демо.**

- Backend, миграции, ACL/idempotency/product states, frontend build и docs/scripts на порту **8003** согласованы.
- Live GigaChat проверен изолированным smoke (OAuth + chat, HTTP 200, без записи в БД, без FastAPI/conversation).
- Mock-путь полностью работает без ключей.

---

## 2. P0 / P1 — найдено и исправлено

| Уровень | Дефект | Исправление |
|---|---|---|
| **P1** | CTA «Сценарии» из impact вёл на `/events/:id/scenarios` — SoftPlaceholder («появятся здесь»), а не на рабочее `/scenarios` | Redirect `EventScenariosRedirect` → `/scenarios?event=…`; ScenariosPage выбирает разговор по `event`; ImpactPanel ссылается напрямую на workspace |
| **P1** | `monitoring_only` не предлагал действие и в aside формулировал «оценка рассчитана» | ImpactPanel: пояснение + CTA «Уточнить контекст» / «К ленте»; aside: корректный текст мониторинга |
| **P1** (docs) | `web/README.md` рекомендовал порт **8001** | Приведён к единому пути **8003** |

Новых P0 (секреты в Git, ACL-дыры, сломанные миграции, падающий pytest/build) не обнаружено.

Узкий тест-контракт: `tests/test_frontend_routes_contract.py`.

---

## 3. Результаты проверок

### A. Репозиторий и безопасность

| Проверка | Результат |
|---|---|
| `.env` / `web/.env` не в Git | **ok** (gitignore) |
| `web/.env` только `VITE_API_BASE_URL` | **ok** |
| `.env.example` без реальных ключей/паролей | **ok** |
| Секреты в исходниках / docs / `web/dist` | **ok** (совпадений не найдено) |
| Provider credentials только server-side | **ok** |
| `ASSISTANT_PROVIDER`: mock / openai / gigachat / live→openai | **ok** |
| `demo_doctor.ps1` — только flags | **ok** |

### B. Backend

| Проверка | Результат |
|---|---|
| `pytest -q` | **92 passed, 1 skipped** |
| Alembic на временной SQLite | **ok** (upgrade head ×2, 23 таблицы, demo DB не затронута; `event_impacts` вместо имени `impacts`) |
| `scripts.ensure_demo` идемпотентен | **ok** (counts стабильны; СеверПром `supply_chain_ready`) |
| OpenAPI: `assessment_state`, `finance_setup_href`, context, assistant, decisions | **ok**; ключей провайдера в схемах нет |
| ACL / idempotency / decision lookup | **ok** (покрыто существующими тестами + smoke) |

### C. Product logic (API + тесты + статика UI)

| Состояние | Результат |
|---|---|
| Supply-chain / China demo | **ok** (`supply_chain_ready`, метрики/путь/сценарии) |
| Finance без контекста → CTA setup → `finance_ready` | **ok** (`test_macro_finance_ux`) |
| `monitoring_only` без фейкового расчёта | **ok** (после фикса) |
| AI provenance labels + dedupe + no mock fallback on error | **ok** (тесты provenance / gigachat / assistant) |

### D. Frontend routes / CTA (статический audit)

Маршруты в `AppRoutes.tsx` присутствуют: `/`, `/news`, `/news/markets|industries|opportunities|for-you`, `/company`, `/company/setup`, `/scenarios`, `/events/:id/impact|assistant`, `/decisions/:id`, `/settings` (заглушка), legacy redirects.

CTA-цепочки (header/footer → login/setup → for-you → news → impact → assistant → scenarios/decision → company edit) согласованы по коду.  
Исправлена dead-ish CTA scenarios (см. §2).

`npm run build`: **ok** (tsc + vite).

Горизонтальный overflow: `overflow-x: clip` на корне; осознанный `overflow-x: auto` только в узких местах (assistant sources / mobile nav) — **ok**.

### E. Документация и скрипты

Единый путь на **8003**: README, DEMO_RUNBOOK, MOBILE_API, `run_backend.ps1`, `run_web.ps1`, `demo_doctor.ps1`, `.env.example`, `web/.env.example`, `web/README.md` (исправлен).

README содержит: команды, demo user, golden path 2–3 мин, mock/GigaChat/OpenAI, troubleshooting портов, оговорку что mock без ключа / real AI с ключом.

---

## 4. Текущее состояние AI

| Поле | Значение |
|---|---|
| Provider (doctor) | `gigachat` |
| `key_configured` | `true` |
| Backend health (:8003) | `true` |
| Live GigaChat smoke | **pass** (OAuth ok, chat HTTP 200, non-empty, no mock fallback, `db_writes: 0`) |
| Mock / retry-без-fallback | покрыто тестами |

Для защиты на mock: `ASSISTANT_PROVIDER=mock` в root `.env` — ответы «Демо-объяснение» без сети.

---

## 5. Изменённые файлы (этот audit)

- `web/src/routes/AppRoutes.tsx` — redirect scenarios
- `web/src/pages/ScenariosPage.tsx` — фильтр `?event=`
- `web/src/components/personal/ImpactPanel.tsx` — CTA scenarios + monitoring
- `web/src/components/assistant/AssistantAnalysisAside.tsx` — тексты monitoring/finance
- `web/README.md` — порт 8003
- `README.md`, `docs/DEMO_RUNBOOK.md` — явная оговорка mock без ключа
- `tests/test_frontend_routes_contract.py` — узкий контракт CTA
- `docs/FINAL_AUDIT.md` — этот отчёт

---

## 6. Оставшиеся ограничения

1. **Live AI** зависит от внешнего провайдера (квоты/сеть/OAuth); при сбое — retry, не mock. Live GigaChat на момент audit — **pass**.
2. **Real news ingestion** не запускался в audit (может переписать demo-ленту).
3. Заглушки UI: `/settings`, `/notifications`, список `/decisions` (без id) — SoftPlaceholder; рабочие пути — `/scenarios` и `/decisions/:id`.
4. Docker-compose по-прежнему публикует контейнерный `:8000` — локальное демо ориентировано на host **8003**.
5. Архивные `web/WEB_REPORT.md` / `ASPECT_REPORT.md` и папки скриншотов удалены из репозитория; актуальные отчёты — этот файл, `DEMO_RUNBOOK.md`, `MOBILE_AUDIT.md`.

---

## 7. Чек-лист демонстратора (день защиты)

1. `python -m scripts.ensure_demo`
2. `.\scripts\run_backend.ps1` → health `http://127.0.0.1:8003/health`
3. `cd web; .\run_web.ps1` → `http://127.0.0.1:5173`
4. `.\scripts\demo_doctor.ps1` — `provider` / `key_configured` / health
5. Войти: `demo@kontur.app` / `DemoKontur1!`
6. **Для вас** → Китай / электроника → impact `supply_chain_ready` → Аспект → сценарии → подтвердить решение
7. Макро/ставка без finance → CTA setup finance (показать честность `finance_data_required`)
8. Если live AI нестабилен — переключить `ASSISTANT_PROVIDER=mock`, перезапустить backend; метка «Демо-объяснение»
9. Не запускать ingestion; не показывать `.env` / ключи / doctor не печатает значения секретов
10. Порт занят: `netstat -ano | findstr :8003` — убивать только свой процесс

---

## Доказательная база команд

```text
pytest -q                     → 92 passed, 1 skipped
cd web; npm run build         → ok
alembic upgrade head (temp)   → ok, isolated
python -m scripts.ensure_demo → idempotent, supply_chain_ready
.\scripts\demo_doctor.ps1     → gigachat, key_configured=true, health=true
live GigaChat smoke           → pass, http 200, db_writes 0
```
