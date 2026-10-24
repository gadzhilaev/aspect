# Bank materials read-only API (Этап 2.12)

Дата: 2026-10-21  
Авторизованный read-only API метаданных документа, фрагмента и оригинального PDF.  
Поиск к ассистенту **не** подключался; UI не менялся.

Рабочая БД, стенд 1.14, `.env`, запущенные сервисы **не** менялись.  
OCR / LLM / браузер / CDP / скриншоты / commit/push не выполнялись.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/core/config.py` | `bank_materials_allowed_ocr_run_ids`, `bank_materials_storage_root` |
| `app/services/bank_materials/access.py` | Scope, builders, PDF resolve + SHA |
| `app/schemas/bank_materials.py` | `BankDocumentOut`, `BankFragmentOut`, … |
| `app/api/v1/bank_materials.py` | Три GET endpoint |
| `app/api/v1/router.py` | Регистрация роутера |
| `.env.example` | Документация env (без реальных ID) |
| `contracts/openapi.json` | Обновлённый контракт |
| `docs/MOBILE_API.md` | Секция Bank materials |
| `tests/test_bank_materials_api.py` | HTTP-тесты на temp SQLite |
| `docs/BANK_MATERIALS_API.md` | Этот отчёт |

## Серверная конфигурация

```bash
# .env.example — раскомментировать при настройке стенда
# BANK_MATERIALS_ALLOWED_OCR_RUN_IDS=<ocr-run-uuid>|<ocr-run-uuid>
# BANK_MATERIALS_STORAGE_ROOT=data/bank_materials/storage
```

| Параметр | Смысл |
|----------|--------|
| `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS` | Явный whitelist OCR run ID (comma или pipe). **Пусто** → интеграция не настроена. |
| `BANK_MATERIALS_STORAGE_ROOT` | Корень, под которым резолвятся `storage_key` PDF. |

Правила:

- Клиент **не** задаёт и **не** расширяет область через run / document / file ID.
- Весь корпус автоматически **не** открывается.
- Редакция **не** выбирается по `max(created_at)`.
- Отдельной RBAC «bank_materials:read» в проекте нет: для MVP достаточно `get_current_user` + серверный scope.
- Контекст компании/события на этом этапе не используется.

## Маршруты

Базовый префикс: `/api/v1` · Auth: Bearer access token.

| Метод | Путь | Ответ |
|-------|------|--------|
| GET | `/bank-materials/documents/{document_id}` | `BankDocumentOut` |
| GET | `/bank-materials/fragments/{fragment_id}` | `BankFragmentOut` |
| GET | `/bank-materials/files/{file_id}/content` | `application/pdf` |

Поискового HTTP endpoint нет.

### Document detail

- Название + `title_status`
- Дата публикации + `publication_date_precision` (+ year/month/display)
- `period_covered` / `period_covered_status` отдельно
- `staleness_note`, `is_current_stance` (без повышения статуса)
- Только **разрешённые** файлы и OCR runs (может быть несколько — без выдуманной «единственной текущей»)
- `content_href` → API path оригинала (`/api/v1/bank-materials/files/{file_id}/content`)

### Fragment detail

- Точная версия: `stable_key`, `revision`, `is_latest_revision`, `is_superseded`, `latest_revision`
- Связь: document / file / run / pages / regions
- `content_type` + status
- Eligibility + reasons; `qa_method` отдельно от `source_role` / `source_role_meaning`
- `pdf_sha256`, `ocr_fingerprint_hash`
- Текст:
  - `exact_quote` — только `verified_transcript` при `eligible_exact_quote`
  - `summary` — явный пересказ
  - `restricted` — метаданные + `restriction_reasons`, **без** raw OCR как цитаты
- Старая revision по точному ID остаётся доступна как история (`is_superseded=true`), без тихого redirect

### PDF

1. Auth + серверный scope (file имеет хотя бы один allowed OCR run).
2. `storage_key` резолвится только под `BANK_MATERIALS_STORAGE_ROOT` (`resolve_under` — без path traversal / symlink escape).
3. Проверка SHA256 файла на диске vs `bank_document_files.sha256`.
4. `Content-Type: application/pdf`, `Content-Disposition: attachment` с безопасным basename.
5. Не StaticFiles; абсолютные пути / storage keys не в JSON и не в ошибках.

## Ошибки

Формат проекта: `{ "error": { "code", "message", "details": [] } }`.

| HTTP | code | Когда |
|------|------|--------|
| 401 | `UNAUTHORIZED` | Нет / невалидный Bearer |
| 503 | `BANK_MATERIALS_NOT_CONFIGURED` | Пустой whitelist OCR run ID |
| 404 | `NOT_FOUND` | Объект отсутствует **или** вне серверного scope |
| 404 | `BANK_FILE_UNAVAILABLE` | Файл отсутствует / storage не задан / path escape |
| 409 | `BANK_FILE_INTEGRITY` | SHA на диске ≠ сохранённому provenance |

Обычное отсутствие материала → 404, не 500.  
GET не создаёт записи, не меняет статусы и не выполняет QA.

## Примеры ответов

**Document (фрагмент):**

```json
{
  "document_id": "<uuid>",
  "slug": "sample-doc",
  "title": "…",
  "title_status": "confirmed",
  "publication_date": "2026-09-11",
  "publication_date_precision": "day",
  "period_covered": null,
  "period_covered_status": "unknown",
  "staleness_note": null,
  "is_current_stance": false,
  "files": [
    {
      "file_id": "<uuid>",
      "original_filename": "sample-doc.pdf",
      "pdf_sha256": "<hex>",
      "content_href": "/api/v1/bank-materials/files/<uuid>/content",
      "ocr_runs": [
        {
          "ocr_run_id": "<uuid>",
          "fingerprint_hash": "<hex>",
          "processing_status": "complete",
          "schema_version": 1
        }
      ]
    }
  ]
}
```

**Fragment restricted (неподтверждённый):**

```json
{
  "fragment_id": "<uuid>",
  "stable_key": "unverified_frag",
  "revision": 1,
  "is_latest_revision": true,
  "is_superseded": false,
  "text_kind": "restricted",
  "text": null,
  "text_restricted": true,
  "restriction_reasons": ["region_type_unverified"],
  "eligible_exact_quote": false,
  "qa_method": null,
  "source_role": null
}
```

## Тесты

```bash
python -m pytest tests/test_bank_materials_api.py -q
```

**6 passed.** Покрыто:

| Проверка | Результат |
|----------|-----------|
| Без авторизации → 401 | OK |
| Разрешённый document / quote / summary / restricted | OK |
| Объект вне scope / чужой file|fragment ID → 404 | OK |
| Пустая конфигурация → 503 | OK |
| Старая revision доступна как superseded | OK |
| PDF content-type + attachment | OK |
| Missing file / SHA mismatch / path traversal | OK |
| Нет абсолютных путей в ответах | OK |
| GET не меняет counts documents/fragments | OK |

Синтетические файлы и temp SQLite; реальные банковские PDF для тестов не требуются.

## Ограничения

- Нет HTTP search / list corpus
- Нет интеграции с ассистентом и UI
- Нет отдельной RBAC-роли сверх authentication + server scope
- Нет signed URL / CDN; только авторизованный API path
- Публичные внешние ссылки на источники банка не выдумываются

**Стоп этапа 2.12.**
