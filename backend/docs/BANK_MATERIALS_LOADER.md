# Bank materials loader (Этап 2.7)

Дата: 2026-10-21  
Рабочая БД и стенд 1.14 **не** трогались. Реальные 9 документов **не** загружались (это этап 2.8).  
Поиск, RAG, API, UI, OCR и ассистент не менялись.

Опирается на: `BANK_MATERIALS_MODEL.md`, `BANK_SCHEMA_IMPLEMENTATION.md`, `BANK_IMPORT_DRY_RUN.md`, `BANK_FRAGMENT_TRUST_FIX.md`.

## Сервис и CLI

| Компонент | Назначение |
|-----------|------------|
| `app/services/bank_materials/prepare.py` | Staging-копии корпуса, SHA файлов, `PreparedDocument` из тех же валидаторов dry-run / `map_fragment` |
| `app/services/bank_materials/load.py` | `load_bank_document(session, plan)` + оркестратор `run_bank_materials_load` |
| `app/jobs/import_bank_materials.py` | `--dry-run` **или** `--load` (взаимоисключающие) |

```bash
# только проверка (без БД)
python -m app.jobs.import_bank_materials --dry-run \
  --input-dir data/bank_materials/ocr \
  --pdf-dir data/bank_materials/raw

# загрузка в явную тестовую БД
python -m app.jobs.import_bank_materials --load \
  --database-url "sqlite:///./tmp_bank_test.db" \
  --input-dir ... --pdf-dir ... \
  --storage-root ...   # опционально; иначе ключи относительно staging
```

Правила CLI:

- `--load` **требует** явный `--database-url`. `DATABASE_URL` из окружения **не** подставляется.
- Миграции **не** применяются. Нет таблиц `bank_*` → `schema_not_ready`, exit 2.
- Перед записью — полный preflight (`run_bank_materials_dry_run`) по **staged** копии.
- Между preflight и записью повторно проверяется неизменность SHA staged-файлов.

Сервис загрузки принимает уже открытую `Session` (`load_bank_document`).  
`SessionLocal` / скрытое подключение к рабочей БД не используются. Engine создаётся только в оркестраторе из переданного URL.

## Транзакционные границы

1. Preflight всего корпуса (без записи в целевую БД).
2. Для **каждого** документа: `BEGIN` → insert tree → `COMMIT` **или** `ROLLBACK`.
3. Ошибка одного документа не откатывает уже закоммиченные документы.
4. Итоговый отчёт (`bank_import_load_latest.json`) явно показывает `partial_success`, счётчики `inserted` / `identical_skip` / `failed`.

Цепочка в одной транзакции документа:

`bank_documents` → `bank_document_files` → `bank_ocr_runs` → `bank_ocr_pages` → `bank_fragments` → `bank_fragment_regions`.

## Повторы и конфликты

| Ситуация | Результат |
|----------|-----------|
| Тот же PDF SHA + OCR fingerprint + совпадающие страницы/фрагменты/регионы | `identical_skip` (только после проверки полноты и содержимого) |
| Run есть, но не хватает страниц / регионы не сходятся | `incomplete_or_partial_ocr_run` — **без** repair/resume |
| Тот же `(stable_key, revision)`, другой текст/метаданные | `fragment_content_conflict` — без UPDATE и без silent skip |
| Явная `revision+1` + корректный `supersedes` | новая строка; предыдущая сохраняется (`revision_appended`) |
| Новый OCR fingerprint | новый `bank_ocr_runs`; старый run остаётся |
| Тот же SHA у другого `slug` | `sha_slug_conflict` |
| `slug` есть, другие даты/title/… | `document_metadata_conflict` — метаданные документа не обновляются молча |
| Цикл / немонотонный supersedes | `supersedes_cycle` / `revision_not_monotonic` |

Документы **не** сливаются по похожим названиям.

## Storage keys

- Ключи — **относительные** пути под явно заданным `--storage-root` (или корнем staging).
- PDF/PNG **не** пишутся как BLOB в БД.
- Абсолютные пути host **не** сохраняются как публичные ссылки.
- Загрузка идёт из staged-копий; байты артефактов в БД не дублируются.

## Доверие

- В БД пишутся только статусы из нормализации (`unverified` / `unknown` при отсутствии полей).
- Нет повышения `verified` → `prose`/`confirmed`.
- Eligibility — только `compute_fragment_eligibility` после повторного чтения из БД; должно совпасть с dry-run.
- `ocr_text`, `verified_transcript`, `summary_text`, `ocr_correction_json` хранятся раздельно; summary не становится цитатой.

Для **текущего** реального корпуса (этап 2.8) ожидается: search=21, AI=0, exact quote=0. В 2.7 это подтверждено синтетикой без trust-полей.

## Тесты (выполнены)

```bash
python -m pytest tests/test_bank_materials_loader.py \
  tests/test_bank_import_dry_run.py tests/test_bank_schema.py -q
```

**40 passed, 1 skipped** (PostgreSQL smoke без URL).

Покрытие на временном SQLite (`PRAGMA foreign_keys=ON`):

- успешная загрузка документа;
- повтор → `identical_skip`, число строк не растёт;
- конфликт содержимого под прежней revision;
- новая revision с сохранением предыдущей;
- новый OCR run при смене fingerprint;
- частичный run не даёт skip;
- rollback при конфликте метаданных после уже загруженного документа;
- даты day / month / unknown;
- NULL bbox сохраняется;
- нет повышения доверия после чтения из БД;
- CLI `--load` без `--database-url` → exit 2;
- preflight failure блокирует запись.

## Ограничения этапа

1. Реальный прогон 9 PDF — этап **2.8**, не 2.7.
2. Автоматический repair/resume частичных run — нет.
3. Поиск / RAG / API / UI — нет.
4. Object storage upload — нет; только opaque keys на staged/local root.
5. Commit/push не делались.

**Стоп этапа 2.7.**
