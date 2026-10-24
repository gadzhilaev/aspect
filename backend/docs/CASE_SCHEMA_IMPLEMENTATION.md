# Case schema implementation (Этап 1.3)

Дата: 2026-10-20  
Источник: `docs/CASE_DATA_MODEL.md`  
Импортёр CSV, API, frontend, рабочая БД и реальные файлы кейса **не** задействованы.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/models/case_data.py` | SQLAlchemy-модели `case_*` |
| `app/models/__init__.py` | экспорт моделей (подключение к Alembic metadata) |
| `alembic/versions/006_case_data_layer.py` | миграция создания структур |
| `tests/test_case_schema.py` | проверки upgrade/downgrade/целостности на временных БД |
| `tests/test_alembic_smoke.py` | head = `006`, наличие таблиц case |
| `tests/conftest.py` | безопасный `drop_all` при circular FK (SQLite `PRAGMA foreign_keys=OFF`) |
| `docs/CASE_SCHEMA_IMPLEMENTATION.md` | этот отчёт |

## Миграция

| | |
|--|--|
| Revision ID | `006` |
| Previous head | `005` |
| Downgrade | удаляет только объекты `case_*` этой ревизии |

Миграция:

- создаёт **только** новые таблицы/индексы/ограничения;
- **не** заполняет конкурсными или demo-данными;
- **не** изменяет строки `companies` / `company_memberships`.

## Созданные таблицы

1. `case_snapshots`
2. `case_import_runs` (+ FK `case_snapshots.import_run_id` → runs, batch-alter)
3. `case_active_snapshot`
4. `case_import_files`
5. `case_org`
6. `case_org_catalog_rows`
7. `case_org_product_marks`
8. `case_org_field_resolution`
9. `case_org_groups`
10. `case_org_group_members`
11. `case_payments`
12. `case_persons`
13. `case_person_org_links`
14. `case_org_company_links`

Параллельной пользовательской сущности Company **нет**. Identity — только `case_org_company_links` (не создаёт membership).

## Ключевые ограничения БД

| Правило | Реализация |
|---------|------------|
| Уникальность `U_*` / `F_*` / `GROUP_ID` в снимке | `UNIQUE (snapshot_id, external_uid/fid/group)` |
| Уникальность исходной строки | `UNIQUE (import_run_id, source_file, source_row_number)` на catalog/payments/person links |
| Identity без дублей | `UNIQUE (slot_key, external_uid)`, `UNIQUE (slot_key, company_id)` |
| ≤1 active snapshot на slot | partial unique index `uq_case_snapshots_one_active_per_slot` |
| Указатель того же slot | composite FK `(slot_key, active_snapshot_id)` → `case_snapshots(slot_key, id)` |
| Нет межснимочных ссылок | composite FK `(snapshot_id, …_id)` на org/person/group/catalog/run |
| Деньги | `NUMERIC(20,1)` + `*_raw`; unit/currency/period nullable |
| Одинаковые платежи | разрешены разные `source_row_number` (нет UNIQUE по content-hash) |
| Статусы / product codes | `CHECK` constraints |

`case_snapshots.import_run_id` **nullable** (bootstrap circular FK со runs): в одной транзакции создаётся snapshot → run → update `import_run_id`. Это схема данных, не «атомарное переключение набора».

## Что требует транзакционной / прикладной логики (не миграция)

Миграция **не** реализует:

1. **Атомарное переключение** active snapshot (`building`→`ready`→retire old / activate new / update pointer).
2. **Resume** прерванного импорта (`resume_cursor_json` — только колонка).
3. Согласование «pointer указывает на snapshot со `status=active`» (partial unique + composite FK не проверяют status).
4. **Валидацию CSV** диапазона и числа десятичных знаков до записи: `NUMERIC(20,1)` — тип хранения; на части СУБД возможно округление/поведение вне явной проверки импортёра. Точная проверка — **обязанность будущего импортёра** до INSERT.
5. Identical-skip по SHA-256 файлов.
6. Расчёт `case_org_field_resolution` / consensus.

## Числа

- Хранение: `NUMERIC(20,1)` + обязательный raw.
- Неизвестные `revenue_unit` / `revenue_currency` / `amount_unit` / `amount_currency` / `period_label` остаются NULL в схеме.
- При `parse_status='error'` amount должен быть NULL (enforce импортёром; CHECK на пару status/amount не вводили, чтобы не блокировать гибкость тестов схемы).

## Выполненные проверки

| Проверка | Результат |
|----------|-----------|
| `alembic upgrade head` с нуля (временный SQLite) | OK |
| Upgrade `005`→`006` с сохранением существующего `Company` | OK |
| Downgrade `006`→`005` и повторный upgrade | OK |
| Уникальность external id / identity / source row | OK |
| Запрет pointer на snapshot чужого slot | OK |
| Запрет платежа / person-link на сущности чужого snapshot | OK |
| Один `status=active` на slot (partial unique) | OK |
| Одинаковые `U_*` в разных slots + независимые links | OK |
| Identity link сохраняется при втором snapshot того же slot | OK |
| Две одинаковые платёжные строки (разный `source_row_number`) | OK |
| Unit/currency/period NULL; error parse → amount NULL | OK |
| Identity link не создаёт `CompanyMembership` | OK |
| Alembic smoke head=`006` | OK |
| PostgreSQL (`ALEMBIC_POSTGRES_URL`) | **не проверен** — переменная не задана; тест skipped |

На всех прогонах использовались **только временные** SQLite-файлы / optional `_test` Postgres. Рабочая БД не трогалась.

Команда: `pytest tests/test_case_schema.py tests/test_alembic_smoke.py` → 12 passed, 2 skipped.

## Остаётся на следующие этапы

1. Импортёр CSV (stream, parse Decimal, SHA-256, identical_skip, orphans, conflict resolution).
2. Сервис атомарного activate snapshot.
3. Resume незавершённого run.
4. (Опционально) жёсткий CHECK `parse_status='ok' ↔ amount IS NOT NULL`.
5. Прогон миграции на disposable PostgreSQL `_test`.

**Стоп этапа 1.3:** модели, миграция и проверки структуры готовы; к импорту автоматически не переходим.
