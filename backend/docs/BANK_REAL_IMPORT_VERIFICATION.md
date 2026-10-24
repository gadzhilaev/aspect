# Bank materials real import verification (Этап 2.8)

Дата: 2026-10-21  
Прогон: **только SQLite**. PostgreSQL не проверялся.  
Рабочая БД, БД конкурсных компаний и стенд 1.14 **не** использовались.  
`.env`, порты и запущенные сервисы не менялись.  
Исходные PDF/OCR артефакты не изменялись. Commit/push не делались.

## Проверочная БД и команды

| | |
|--|--|
| БД | `data/bank_materials/verification/bank_real_import_20261021T124200.db` |
| URL (миграции / 1-й load) | `sqlite:///<abs>/data/bank_materials/verification/bank_real_import_20261021T124200.db` |
| URL (2-й load) | `sqlite:///data/bank_materials/verification/bank_real_import_20261021T124200.db` (относительный, без проблем кодировки shell) |
| PDF | `data/bank_materials/raw/` |
| OCR | `data/bank_materials/ocr/` |
| Отчёты | `data/bank_materials/verification/reports_run{1,2}/` (gitignore) |
| Независимые проверки | `data/bank_materials/verification/independent_checks_run1.json`, `content_snapshot_run1.json`, `rerun_compare.json` |

Каталог `data/bank_materials/verification/` добавлен в `.gitignore`.

Миграции (только на эту БД; `.env` не правился — временный `DATABASE_URL` в процессе alembic, затем сброс):

```bash
# DATABASE_URL=<verification sqlite url>
python -m alembic upgrade head
```

Импорт:

```bash
python -m app.jobs.import_bank_materials --load \
  --database-url "sqlite:///data/bank_materials/verification/bank_real_import_20261021T124200.db" \
  --input-dir data/bank_materials/ocr \
  --pdf-dir data/bank_materials/raw \
  --report-dir data/bank_materials/verification/reports_run1 \
  --storage-root data/bank_materials/verification/storage_run1
```

Штатный staging + preflight; доверие не повышалось.

## Первый запуск

| Метрика | Значение |
|---------|----------|
| status / ok | `loaded` / True |
| inserted | **9** |
| identical_skip | 0 |
| failed | 0 |
| время | **~11.1 s** |
| eligibility (loader) | search=21, AI=0, exact_quote=0 |
| preflight errors | 0 |
| preflight warnings | 171 |

### По документам (все `inserted`)

| document | elig search/AI/quote |
|----------|----------------------|
| ALFA-7M26 | 2 / 0 / 0 |
| ALFA-consumption | 2 / 0 / 0 |
| ALFA-Macro_Insights-Policy_Rate_11Sep | 4 / 0 / 0 |
| ALFA-macro_stat1H26 | 2 / 0 / 0 |
| ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021 | 2 / 0 / 0 |
| FI_Strategy_3Q26_22072026 | 3 / 0 / 0 |
| Gold_digest_August26 | 2 / 0 / 0 |
| Inflation_tracker_02 | 2 / 0 / 0 |
| Бонд_Бриф_14092026 | 2 / 0 / 0 |

### Warnings (preflight, не blocking)

| code | count |
|------|------:|
| `absolute_tool_path_ignored` | 128 |
| `primary_region_type_missing_treated_as_unverified` | 21 |
| `content_type_status_missing_treated_as_unknown` | 21 |
| `historical_material_note` | 1 |

Blocking errors: **нет**.

## Счётчики таблиц (после 1-го load)

Сверено с входными планами `PreparedDocument` (не с «желаемыми» цифрами):

| Таблица | Строк | План / ожидание корпуса |
|--------|------:|-------------------------|
| `bank_documents` | 9 | 9 документов |
| `bank_document_files` | 9 | 9 PDF SHA |
| `bank_ocr_runs` | 9 | 9 fingerprint |
| `bank_ocr_pages` | 64 | 64 страницы |
| `bank_fragments` | 21 | 21 фрагмент |
| `bank_fragment_regions` | **23** | **23** по планам (у FI cover / Gold cover по 2 region) |

## Независимая проверка (новая Session)

Скрипт: `data/bank_materials/verification/run_independent_checks.py`  
Результат: **ALL_PASSED True** (`independent_checks_run1.json`).

| Проверка | Результат |
|----------|-----------|
| SHA файлов = исходные PDF | PASS |
| pages/fragments/regions → правильные run/file/document | PASS |
| нет orphan / лишних записей | PASS |
| `stable_key`/`revision` = вход | PASS |
| OCR / transcript / summary раздельно и без изменений | PASS |
| NULL bbox сохранены | PASS |
| Gold: `precision=month`, `publication_date=NULL`, year=2026 month=8 | PASS |
| Steels: date=2021-04-15, `is_current_stance=false`, есть `staleness_note` | PASS |
| нет повышения unverified→prose / unknown→confirmed | PASS (21× unverified, 21× unknown) |
| eligibility из БД той же функцией | search=**21**, AI=**0**, quote=**0** |
| `PRAGMA foreign_key_check` | пусто |
| `PRAGMA integrity_check` | `ok` |

## Повторный запуск

Та же команда `--load` на ту же БД (`reports_run2`).

| Метрика | Значение |
|---------|----------|
| inserted | **0** |
| identical_skip | **9** (все документы) |
| failed | 0 |
| прирост строк (6 таблиц) | **0** |
| eligibility | search=21, AI=0, quote=0 |

Сравнение содержимого со снимком после 1-го load (`compare_rerun.py` / `rerun_compare.json`):

- ID документов, files, runs, fragments, regions — **без изменений**;
- тексты, revisions, provenance — **без изменений**;
- не только счётчики строк.

## Дефекты и исправления

**Дефектов загрузчика на реальном корпусе не обнаружено.**  
Код загрузчика / схему / OCR-артефакты не правили.

Замечание среды (не баг импорта): абсолютный `sqlite:///` URL с кириллицей в пути пользователя может ломаться при передаче через PowerShell encoding; для 2-го прогона использован относительный URL от корня репозитория. Сама БД и данные целы.

## Оставшиеся ограничения

1. Проверка только на **SQLite**; PostgreSQL в 2.8 не заявлялся и не гонялся.
2. AI evidence / exact quote = 0, пока в артефактах нет явных `primary_region_type=prose` и `content_type_status=confirmed` (политика 2.6.1).
3. Object storage / публикация файлов / поиск / RAG / API / UI — вне этапа.
4. Проверочная БД и staging лежат локально под `verification/` и не предназначены для Git.

**Стоп этапа 2.8.**
