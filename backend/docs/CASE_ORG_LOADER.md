# Company catalog loader (Этап 1.5 / 1.5.1)

Дата: 2026-10-20  
Загрузка только справочника компаний в **building** snapshot.  
Платежи, F–U, активация snapshot и CLI записи — следующие этапы.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/services/case_data/load_org_catalog.py` | Сервис `load_company_catalog` (+ идемпотентность/валидация 1.5.1) |
| `app/services/case_data/resolution.py` | Правила consensus / conflict / absent |
| `app/services/case_data/__init__.py` | Экспорт загрузчика |
| `tests/test_case_org_loader.py` | Проверки на временном SQLite |
| `tests/fixtures/case_org_loader/README.md` | Пояснение к fixtures (CSV пишутся в тестах) |
| `docs/CASE_ORG_LOADER.md` | Этот отчёт |

Модели, миграции, dry-run CLI, API и frontend **не** менялись по поведению.  
Рабочая БД и реальный `data/case/raw` **не** использовались.

## Интерфейс

```python
from app.services.case_data import load_company_catalog

result = load_company_catalog(
    session,                    # явная Session; SessionLocal внутри нет
    snapshot=building_snapshot, # CaseSnapshot.status == "building"
    import_run=run,             # CaseImportRun того же snapshot
    import_file=registered,     # CaseImportFile того же run
    csv_path=Path("..."),       # файл на диске
    batch_size=500,             # опционально
)
# CatalogLoadResult: skipped, rows_inserted, orgs_created,
# orgs_upgraded_from_orphan, groups_created, resolutions_written, ...
```

Предусловия / ошибки:

| Проверка | Ошибка |
|----------|--------|
| `snapshot.status != "building"` | `SnapshotNotBuildingError` |
| run/file не принадлежат snapshot | `ContextMismatchError` |
| SHA-256 файла ≠ `import_file.content_sha256` | `ContentHashMismatchError` |
| роль CSV / колонки / поля (как dry-run) | `CatalogValidationError` (`file`, `record_number`, `field`, `reason`) |
| частичная/противоречивая загрузка | `IncompleteCatalogImportError` |

### Идемпотентность (1.5.1)

Пропуск (`skipped=True`) **только** если одновременно:

- SHA-256 файла = `import_file.content_sha256`;
- `import_file.status == "completed"`;
- `row_count_loaded` = число data-записей в CSV = числу `case_org_catalog_rows` для `(run, source_file)`;
- для ненулевого числа строк: у каждой catalog row есть 6 product marks, у каждого затронутого org — `case_org_field_resolution`.

Пустой файл (только заголовок) допустим: `completed` + `row_count_loaded=0` → повторный вызов skip.

Если строки есть, а `status != completed`, или счётчики/производные данные не сходятся → **`IncompleteCatalogImportError`**.  
Загрузчик **не** дописывает, **не** удаляет строки и **не** делает resume.

## Валидация (согласовано с dry-run)

| Поле | Допустимо отсутствует | Некорректное значение |
|------|----------------------|------------------------|
| `SYNTHETIC_U` | нет | блокирует |
| `REVENUE_COMPANY` | нет | блокирует (не пишется как «успех» с error-amount) |
| `GROUP_ID` | нет | блокирует (не становится NULL) |
| Bool-флаги продуктов / NEGATIVE / FTS / FACTORING | нет | блокирует (не → false/NULL) |
| `ECO_MARK_LABEL`, SPARK workers, `FTS_COUNTRY_NAME` | да (пусто → NULL) | — |

Диагностика ошибки: файл, номер записи, поле, причина — без полной исходной строки.

## Что пишется

На каждую data-строку справочника:

- `case_org` (новая или существующая сирота того же snapshot — ID сохраняется);
- `case_org_catalog_rows` (все варианты UID; `factoring_mark`; `revenue_unit`/`currency` = NULL);
- `case_org_product_marks` (RKO/GAR/LOA/LEA/DEP/ZPP);
- `case_org_groups` + `case_org_group_members` при валидном `GROUP_ID`.

После загрузки — `case_org_field_resolution` и флаги org; при конфликте GROUP_ID — `is_conflicted_membership=True`.

**Не** создаются: Company, membership, nodes, edges, impact, links.  
**Не** меняются: `case_active_snapshot`, `ready`/`active`.

## Транзакции

- Загрузчик **не** вызывает `commit()` и **не** вызывает `rollback()`.
- Обычный Python exception **не** переводит Session автоматически в failed-состояние; незакоммиченные (в т.ч. уже `flush`) изменения остаются до `rollback()` вызывающего.
- Сценарий: первый batch записан → ошибка следующего ряда → caller `rollback()` → частичных следов нет.
- Resume по `last_row_number` **не** реализован.

## Выполненные проверки

`pytest tests/test_case_org_loader.py tests/test_case_dry_run.py`

Ожидаемые регрессии loader (временный SQLite, `foreign_keys=ON`):

- завершённый файл повторно пропускается;
- частичные строки без `completed` → `IncompleteCatalogImportError`;
- `completed` с неверным счётчиком отклоняется;
- неверные bool / GROUP_ID / суммы — как dry-run (block);
- допустимые пустые ECO/SPARK сохраняются;
- ошибка после первого batch + rollback → 0 записей;
- active snapshot / pointer / пользовательские сущности не меняются;
- пустой CSV → completed 0 → skip;
- прежние сценарии (conflict UID, orphan upgrade, products/groups, …).

## Ограничения

- Платежи — отдельный сервис (`docs/CASE_PAYMENT_LOADER.md`); F–U, CLI записи, activate, resume — следующие этапы
- Реальный конкурсный CSV через загрузчик не прогонялся
- Заполненный справочник ≠ готовый snapshot
