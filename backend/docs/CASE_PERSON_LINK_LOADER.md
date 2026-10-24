# Person–org link loader (Этап 1.7)

Дата: 2026-10-20  
Загрузка связей `F_*`↔`U_*` в **building** snapshot.  
CLI записи, resume и активация — следующие этапы.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/services/case_data/load_person_org_links.py` | Сервис `load_person_org_links` |
| `app/services/case_data/__init__.py` | Экспорт загрузчика |
| `tests/test_case_person_link_loader.py` | Проверки на временном SQLite |
| `docs/CASE_PERSON_LINK_LOADER.md` | Этот отчёт |

Модели, миграции, dry-run CLI, API и frontend **не** менялись.  
Рабочая БД и реальный `data/case/raw` **не** использовались.

## Интерфейс

```python
from app.services.case_data import load_person_org_links

result = load_person_org_links(
    session,                    # явная Session; SessionLocal внутри нет
    snapshot=building_snapshot, # CaseSnapshot.status == "building"
    import_run=run,             # CaseImportRun того же snapshot
    import_file=registered,     # CaseImportFile того же run
    csv_path=Path("..."),       # файл на диске
    batch_size=500,             # > 0; опционально
)
# PersonLinkLoadResult: skipped, rows_inserted, persons_created,
# orgs_created, snapshot_id, import_run_id, import_file_id
```

Предусловия / ошибки:

| Проверка | Ошибка |
|----------|--------|
| `batch_size < 1` | `PersonLinkValidationError` |
| `snapshot.status != "building"` | `SnapshotNotBuildingError` |
| run/file не принадлежат snapshot | `ContextMismatchError` |
| SHA-256 файла ≠ `import_file.content_sha256` | `ContentHashMismatchError` |
| роль CSV / колонки / поля (как dry-run) | `PersonLinkValidationError` |
| частичная/противоречивая загрузка | `IncompletePersonLinkImportError` |

### Идемпотентность

Пропуск (`skipped=True`) **только** если одновременно:

- SHA-256 файла = `import_file.content_sha256`;
- `import_file.status == "completed"`;
- `row_count_loaded` = число data-записей в CSV = числу `case_person_org_links` для `(run, source_file)`.

Пустой файл допустим: `completed` + 0 rows → skip.  
Частичное/противоречивое состояние → ошибка (без resume/дописывания/удаления).  
Повторный skip **не** переписывает `org_had_catalog_at_import`.

## Правила записи

На каждую логическую CSV-запись:

| Действие | Правило |
|----------|---------|
| `case_person` | upsert по `(snapshot_id, SYNTHETIC_F)` |
| `case_org` | существующая или сирота (`has_catalog_profile=false`, `profile_resolution=absent`) |
| `case_person_org_link` | отдельная строка; `relation_kind=unspecified` |
| `CITY_NAME` / `RC_NAME` | как в строке; пусто → NULL; **не** сводить к первому/последнему |
| `org_had_catalog_at_import` | снимок `has_catalog_profile` **в момент** загрузки связи |

Не угадываются должность, владение или тип отношений.  
География человека не пишется в поля компании.  
Одинаковые исходные строки сохраняются отдельно (нет дедупа по паре F–U).  
Один F ↔ много U и один U ↔ много F — норма.

### Валидация (как dry-run)

| Поле | Правило |
|------|---------|
| `SYNTHETIC_F` | обязателен, формат `F_\d+`; иначе блок |
| `SYNTHETIC_U` | обязателен, формат `U_\d+`; иначе блок |
| `CITY_NAME`, `RC_NAME` | пустые допустимы |

Диагностика: файл, номер записи, поле, причина.

### Исторический признак профиля

Если позже справочник дополнили и `case_org.has_catalog_profile` стал `true`, ранее сохранённый `org_had_catalog_at_import` **остаётся** прежним.

## Пакетная обработка

- Потоковый CSV; bulk INSERT словарями.
- Person/org кэшируются и переиспользуются через границы batches.
- Нет SELECT на каждую связь; пакетные `IN` / INSERT с лимитом bind-параметров.
- Commit/rollback у вызывающего; active pointer и `ready`/`active` не меняются.

## Транзакции

- Загрузчик не вызывает `commit()` / `rollback()`.
- Обычный exception не переводит Session в failed-состояние сам по себе.
- Ошибка после первого batch + caller `rollback()` → частичных следов нет.

## Выполненные проверки

```bash
pytest tests/test_case_person_link_loader.py \
       tests/test_case_org_loader.py \
       tests/test_case_payment_loader.py \
       tests/test_case_dry_run.py
```

Регрессии person-link (временный SQLite, `foreign_keys=ON`): обычная связь; 1→N / N→1; сирота; reuse через batches; одинаковые строки; география по строкам; неверные ID / пустая гео; completed→skip / partial→error / hash mismatch; запрет active; batch+rollback; исторический `org_had_catalog_at_import`; нет User/Company/membership.

Повторный замер 50k платежей не выполнялся (код payment loader не менялся).

## Ограничения

- Нет CLI записи, activate, resume
- Реальный конкурсный CSV не прогонялся
- Загруженные связи ≠ готовый / активный snapshot
