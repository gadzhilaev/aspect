# Bank Materials Patch — исходный код сервиса (не корпус документов)

## Важно

Это **патч исходного кода** Python-модуля `bank_materials`, а **не** банковский корпус
(PDF, OCR, verification DB, storage). Передача этого архива **сама по себе не подключает**
банковский корпус и **не гарантирует** доступность материалов в API/UI.

Без настроенных:

- БД со схемой банковских материалов (миграции, в т.ч. `007_bank_materials`);
- `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS` / server-side OCR run scope;
- `BANK_MATERIALS_STORAGE_ROOT` (или эквивалент storage root);
- загруженного OCR/PDF корпуса и при необходимости QA-ревизий;

интеграция останется в состоянии «не настроена» (`integration_not_configured` /
`BANK_MATERIALS_NOT_CONFIGURED`). Это **ожидаемое** поведение реального кода при пустом
scope, а не признак stub-заглушки.

## Назначение модуля

Сервисный слой банковской аналитики / bank materials:

- eligibility фрагментов и date gates;
- dry-run и prepare/normalize корпуса перед load;
- load документов/фрагментов/OCR runs в БД;
- apply QA revisions;
- retrieval фрагментов;
- scoped read-access для API (`access`);
- сбор bank evidence для событий (`event_evidence`).

Файлы в архиве:

```
backend/app/services/bank_materials/
  __init__.py
  access.py
  apply_qa_revisions.py
  dry_run.py
  eligibility.py
  event_evidence.py
  fingerprint.py
  fragment_revision.py
  load.py
  normalize.py
  paths.py
  prepare.py
  retrieval.py
```

## Как заменить временные stubs

1. Сделайте бэкап текущего `backend/app/services/bank_materials/` на мобильной ветке.
2. Распакуйте архив в корень репозитория (или скопируйте только папку
   `backend/app/services/bank_materials/`), **перезаписав stubs этого модуля**.
3. **Не** затирайте мобильные изменения вне этого модуля:
   - auth / preferences (роуты, схемы, клиентские настройки);
   - миграцию **012** (и любые последующие мобильные миграции) — этот патч **не включает**
     alembic-версии и не должен их перезаписывать.
4. Убедитесь, что соседние зависимости (models/schemas/api/config) уже согласованы
   с этим сервисом; при расхождении подтяните их отдельно, не смешивая с auth/012.
5. Настройте env/scope и загрузите корпус отдельным процессом (import job / stand),
   иначе API будет корректно отвечать «интеграция не настроена».

## Соседние модули и зависимости (не входят в этот архив)

Сервисный код импортирует и опирается на:

| Область | Пути / пакеты |
|--------|----------------|
| Models | `app.models.bank_materials` (`BankDocument`, `BankFragment`, `BankOcrRun`, …), `app.models.event.Event` |
| Schemas | `app.schemas.bank_materials`, `app.schemas.event_bank_evidence` |
| API | `app.api.v1.bank_materials`, вызов evidence из `app.api.v1.events` |
| Config / errors | `app.core.config` (`bank_materials_allowed_ocr_run_ids`, `bank_materials_storage_root`), `app.core.errors.AppError` |
| Jobs / scripts | `app.jobs.import_bank_materials`, OCR/stand bootstrap scripts |
| Миграция схемы | `alembic/versions/007_bank_materials.py` |
| Внешние пакеты | `sqlalchemy`, `pypdf` (dry-run PDF page count) |

Runtime-данные корпуса обычно лежат вне модуля, например:

- `data/bank_materials/raw/` — PDF;
- `data/bank_materials/ocr/` — OCR;
- `data/bank_materials/verification/` — QA / стенды / `.db`.

Они **намеренно исключены** из архива.

## Что исключено из архива

- `__pycache__/`, `*.pyc`
- `.env`, секреты, credentials
- БД (`.db`, sqlite и т.п.)
- PDF, OCR, изображения страниц, verification/runtime storage
- alembic-миграции, API/models/schemas (соседний код — подключать отдельно при необходимости)

## Manifest

См. `MANIFEST.sha256` в корне архива: относительные пути и SHA-256 исходных файлов модуля
и README.

## Проверка после распаковки

Сверьте список и хеши из `MANIFEST.sha256` с распакованными файлами. Убедитесь, что
в дереве нет `__pycache__`, `.env`, `.db`, `.pdf`, OCR-артефактов.