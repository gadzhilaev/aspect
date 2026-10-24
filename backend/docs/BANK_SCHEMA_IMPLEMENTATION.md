# Bank materials schema implementation (Этап 2.5)

Дата: 2026-10-21  
Источник: `docs/BANK_MATERIALS_MODEL.md` (уточнения 2.5)  
Импортёр PDF/OCR, поиск, RAG, API, UI, рабочая БД и стенд 1.14 **не** задействованы.  
`AGENTS.md` в репозитории отсутствует.

## Изменённые / новые файлы

| Файл | Назначение |
|------|------------|
| `docs/BANK_MATERIALS_MODEL.md` | Устранены противоречия: `revision`, composite FK, eligibility без колонок |
| `app/models/bank_materials.py` | SQLAlchemy-модели шести таблиц |
| `app/models/__init__.py` | экспорт моделей |
| `app/services/bank_materials/eligibility.py` | `compute_fragment_eligibility` |
| `app/services/bank_materials/__init__.py` | пакет |
| `alembic/versions/007_bank_materials.py` | миграция |
| `tests/test_bank_schema.py` | upgrade/downgrade/целостность/eligibility на temp SQLite |
| `tests/test_alembic_smoke.py` | head = `007`, наличие `bank_*` |
| `tests/test_case_schema.py` | ожидание head `007` |
| `docs/BANK_SCHEMA_IMPLEMENTATION.md` | этот отчёт |

## Миграция

| | |
|--|--|
| Revision ID | `007` |
| Previous head | `006` |
| Downgrade | удаляет только `bank_*` этой ревизии |

Миграция:

- создаёт **только** новые таблицы/индексы/ограничения;
- **не** импортирует PDF/OCR и не сидирует корпус;
- **не** меняет `companies`, `case_*`, новости, ассистента.

Self-referential FK (`supersedes_*`) заданы **внутри** `create_table` (SQLite не поддерживает `ALTER ADD CONSTRAINT`).

## Созданные таблицы

1. `bank_documents`
2. `bank_document_files`
3. `bank_ocr_runs`
4. `bank_ocr_pages`
5. `bank_fragments`
6. `bank_fragment_regions`

## Ограничения БД

| Правило | Реализация |
|---------|------------|
| Уникальный PDF | `UNIQUE (sha256)` |
| Уникальный OCR run | `UNIQUE (document_file_id, fingerprint_hash)` |
| Ревизия фрагмента | `UNIQUE (ocr_run_id, stable_key, revision)` |
| `supersedes_file_id` внутри одного document | composite FK `(document_id, supersedes_file_id)` + CHECK not self |
| `supersedes_fragment_id` тот же run+stable_key | composite FK + CHECK not self |
| Fragment → page того же run | FK `(ocr_run_id, page_number)` → pages |
| Fragment → file/document цепочки | composite FK через run и file |
| Region → fragment того же run + page того же run | composite FK |
| Даты day/month/unknown | CHECK формы nullability; month 1–12 |
| BBox all-or-nothing | CHECK; left/top ≥ 0; width/height > 0 |
| `page_number` / размеры страницы | ≥ 1 / > 0 |
| Region / primary types | prose, table, chart, contacts_disclaimer, mixed, unverified |

`pdf_creation_date` — только metadata; publication date живёт на `bank_documents`.

## Прикладная логика (не CHECK)

| Правило | Где |
|---------|-----|
| `revision` монотонно растёт; нет циклов supersedes | импортёр |
| year/month совпадают с календарным `publication_date` при `day` | импортёр (portable; без dialect EXTRACT в CHECK) |
| bbox внутри width×height страницы | валидатор импорта (**не** DB CHECK по другой таблице) |
| Eligibility search / AI / quote | `compute_fragment_eligibility` — **не** колонки БД |
| Spot-check страницы ≠ verified fragments | политика eligibility + документация |
| OCR confidence не повышает допуск | функция игнорирует `mean_confidence` |

## Eligibility (решение по хранению)

Колонок `eligible_*` **нет**. Источник истины — чистая функция без БД/LLM.  
Противоречивые kind/тексты и non-prose region types блокируют evidence/quote.

## Результаты тестов (реально выполнены)

Команда:

```bash
python -m pytest tests/test_bank_schema.py tests/test_alembic_smoke.py -q
```

| Результат | |
|-----------|--|
| Passed | 10 |
| Skipped | 2 (PostgreSQL: `ALEMBIC_POSTGRES_URL` не задан) |
| Failed | 0 |

Покрыто на **временном SQLite** (`PRAGMA foreign_keys=ON`):

- upgrade с нуля → head `007`;
- upgrade с `006` с сохранением `Company`;
- downgrade `007`→`006` и re-upgrade;
- уникальность SHA PDF и OCR fingerprint;
- две ревизии фрагмента со сохранением старого текста + запрет дубля revision;
- запрет несогласованных document/run/page/supersedes ссылок;
- CHECK дат (month без day; month∉1–12) и bbox shape;
- матрица eligibility (summary, needs_reverification, high confidence без verification, table).

**PostgreSQL:** не проверен (нет отдельной `_test` БД / `ALEMBIC_POSTGRES_URL` в этом прогоне). Smoke-тест готов к запуску при наличии disposable DB.

## Оставшиеся ограничения

1. Импортёр корпуса, поиск, RAG, API, ACL — не реализованы.
2. Попадание bbox в размеры страницы — только будущий валидатор.
3. Монотонность `revision` / ацикличность supersedes — не триггеры БД.
4. Согласование calendar year/month с `publication_date` — не dialect-portable CHECK.
5. Рабочая БД / стенд 1.14 этой миграцией не трогались.

**Стоп этапа 2.5.**
