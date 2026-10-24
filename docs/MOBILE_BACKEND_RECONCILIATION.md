# Mobile ↔ Backend reconciliation (2026-10-24)

Задание: восстановить `bank_materials`, сохранить мобильные изменения, убрать ложные состояния, ужесточить user endpoints, зафиксировать аудит по ТЗ.

**Не** объявляется готовность всего проекта к конкурсу.

## Что восстановлено

Из архива `aspekt_bank_materials_patch.zip` (SHA-256 файлов совпали с `MANIFEST.sha256`):

`backend/app/services/bank_materials/` — 13 оригинальных модулей:

`__init__.py`, `access.py`, `apply_qa_revisions.py`, `dry_run.py`, `eligibility.py`, `event_evidence.py`, `fingerprint.py`, `fragment_revision.py`, `load.py`, `normalize.py`, `paths.py`, `prepare.py`, `retrieval.py`

Временные stubs сохранены вне импорта:

`_patch_backup/bank_materials_stubs_*` (в `.gitignore`).

Копия README/manifest патча: `docs/BANK_MATERIALS_PATCH_README.md`, `docs/BANK_MATERIALS_PATCH_MANIFEST.sha256`.

## Какие мобильные изменения сохранены

- `User.preferences_json`, `GET /users/me` → `preferences`
- `PATCH /users/me/preferences`, `POST /users/me/change-password`, `DELETE /users/me` (ужесточены)
- Alembic `012_user_mobile_prefs.py` (`down_revision=011`)
- Flutter API client / auth / onboarding / feed wiring (доработаны честные empty/error)

## Что исправлено в этой сессии

| Область | Изменение |
|--------|-----------|
| Bank materials | Stubs → оригинальный код |
| Schema DX | Удалён silent `ALTER` из `app/main.py` lifespan и `scripts/ensure_demo.py`; ensure_demo требует `alembic upgrade head` |
| Delete account | Body `password`; отказ `SOLE_OWNER` / `HAS_AUDIT_RECORDS`; чистка TG subscriptions/tokens/outbox pending; cascade assistant; компании сохраняются |
| Change password | Явная token_policy (JWT до expiry); пароли не логируются |
| Flutter feed | Нет подмены СеверПром/demo при ошибке API; honest empty/no-company |
| Flutter Telegram | Connected только после `notification-settings.linked` |
| Flutter bank block | Только из API evidence / статус not configured |
| Tests | `tests/test_mobile_user_endpoints.py`; head `012` в `_alembic_util` / `test_bank_schema` |
| Docs / OpenAPI | `README.md`, `docs/MOBILE_API.md`, пересобран `contracts/openapi.json` |

## Команды и результаты проверок

```text
# Patch SHA
ALL_OK (13 module files + README)

# Temp Alembic (рабочий kontur.db не трогали)
DATABASE_URL=sqlite:////tmp/aspect_mig_fresh.db alembic upgrade head
→ 001…012, preferences_json present

DATABASE_URL=sqlite:////tmp/aspect_mig_011.db alembic upgrade 011 && alembic upgrade head
→ 012 idempotent (001 create_all already includes preferences_json from current models)

# Scope without corpus
require_bank_materials_configured → AppError BANK_MATERIALS_NOT_CONFIGURED 503
collect_event_bank_evidence import OK (real module)

# Pytest (selected)
python -m pytest tests/test_mobile_user_endpoints.py \
  tests/test_event_bank_evidence.py tests/test_bank_materials_api.py \
  tests/test_bank_schema.py -q
→ 26 passed, 1 skipped

# Flutter
dart analyze lib → No issues found
```

**Не выполнялось:** live LLM, Telegram send, полный `flutter test`/release APK, изменение рабочего `kontur.db`, webhook.

**NOT_VERIFIED:** agent-loop live с bank citations на полном корпусе; PDF Bearer download e2e на реальном storage; hot-reload UX на устройстве после этих правок (нужен hot restart у пользователя).

## Оставшиеся подтверждённые дефекты / gaps

### A. Реальные дефекты мобильного приложения

- Таб «Сценарии», finance/counterparties screens — локальные моки; API simulator/decisions не подключены.
- Alfa Business demo — честный макет входа, не SSO банка (допустимо по уточнению, но должно оставаться явно «демо»).
- Push: только OS permission, без device token / FCM.
- «На чём основан вывод» (`conclusion_basis_screen`) — всё ещё статический текст, не `assessment_explanation` API.
- После смены пароля клиент должен сам чистить JWT (серверного denylist нет).

### B. Недостающие файлы переданного backend-пакета (ранее)

- Было: отсутствовал `app/services/bank_materials/*` → **восстановлено патчем**.
- По-прежнему нет в mobile ZIP: `docker-compose*.yml`, тяжёлые `data/bank_materials`, case CSV стенды (импортёры есть).

### C. Отсутствующие данные/настройки стенда

Для живого bank evidence / PDF:

- `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS`
- `BANK_MATERIALS_STORAGE_ROOT`
- OCR/PDF/verification corpus под storage root
- при необходимости QA revisions

Для конкурсного ассистента:

- `ASSISTANT_PROVIDER=hackathon` (+ ключ/URL/model allow-list)
- `COMPETITION_MODE=true` при сдаче жюри

Для case-персонализации «как в CSV кейса»:

- case snapshot import + `CASE_CONTEXT_SLOT_KEY` / activate

### D. Уже существующие функции backend, не подключённые на стенде/UI

- Decisions / solutions / financial simulator / compare-scenarios
- Company `getProfile` / `getContext` / `patchFinance` (клиентские методы есть, UI finance не дергает)
- News scheduler / ingestion jobs
- Full bank retrieval/load jobs

### E. Доп. пожелания, не обязательные по ТЗ

- Нативная реклама продуктов банка
- Отдельный quality dashboard (достаточно метрик/процесса в docs)
- Реальный банковский SSO

## Diff для merge с основным backend

Исходный monorepo baseline **не зафиксирован** отдельным git remote в этом репозитории Aspect — точный diff «пакет ↔ upstream kontur_back» **не установлен**.

Практический diff для переноса в основной backend (файлы этой сессии):

- `app/services/bank_materials/**` (из патча)
- `app/api/v1/auth.py`, `app/schemas/auth.py`
- `app/main.py` (без silent ALTER)
- `scripts/ensure_demo.py`
- `alembic/versions/012_user_mobile_prefs.py`
- `tests/test_mobile_user_endpoints.py`, `tests/_alembic_util.py`, `tests/test_bank_schema.py` (head 012)
- `contracts/openapi.json`, `docs/MOBILE_API.md`, `README.md`

## Что запросить у владельца проекта для конкурсного стенда

1. Bank corpus: PDF + OCR runs + verification DB / storage layout + разрешённые OCR run IDs  
2. Case CSV (`df_Uid_*`, links, payments) + слот/activate инструкции  
3. Hackathon API key + подтверждённый `HACKATHON_BASE_URL` / model  
4. (Опционально) `docker-compose.competition.yml` и фронт web, если жюри идёт через compose  
5. Политика удаления sole-owner компании (сейчас API **отказывает**, не архивирует)

## Классификация аудита ТЗ (уточнение)

| Finding | Bucket |
|--------|--------|
| Mock подмена ленты при ошибке | **A** — исправлено |
| Bank stubs | **B** — исправлено кодом; корпус остаётся **C** |
| CSV/PDF отсутствуют в ZIP | **C**, не отсутствие импортёра (**D**) |
| ASSISTANT_PROVIDER=mock на стенде | **C** (код провайдеров есть) |
| Scenarios UI без API | **A** / **D** |
| Alfa demo vs SSO | **E** (SSO не требуется) |
| Нативная реклама | **E** |
| Quality metrics process | **E**/docs; dashboard не обязателен |
