# Case import pipeline (Этап 1.8)

Дата: 2026-10-20  
Единый процесс: preflight (dry-run) → загрузка трёх файлов → `ready`.  
**Активация** и **resume** не реализованы.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/services/case_data/import_pipeline.py` | Оркестратор `run_case_import` |
| `app/jobs/import_case_data.py` | CLI `--dry-run` / `--load` |
| `app/services/case_data/__init__.py` | Экспорт |
| `tests/test_case_import_pipeline.py` | Интеграционные тесты |
| `docs/CASE_IMPORT_PIPELINE.md` | Этот отчёт |

Модели, миграции, API, frontend и поведение dry-run-валидации **не** менялись.  
Рабочая БД и реальный `data/case/raw` **не** использовались.

## Команды

### Dry-run (без БД)

```bash
python -m app.jobs.import_case_data \
  --dry-run \
  --input-dir path/to/csvs \
  --report-dir data/case/reports
```

Не читает `DATABASE_URL` / `SessionLocal`.

### Load (явная целевая БД)

```bash
python -m app.jobs.import_case_data \
  --load \
  --input-dir path/to/csvs \
  --slot-key competition_default \
  --version-label hack-raw-v1 \
  --database-url "sqlite:///./case_import_test.db" \
  --report-dir data/case/reports \
  --batch-size 500
```

Обязательны: `--input-dir`, `--slot-key`, `--version-label`, `--database-url`.  
Рабочий `DATABASE_URL` **никогда** не подставляется.  
`--dry-run` и `--load` взаимоисключающие.  
В лог пишется только редактированный URL (пароль → `***`).

Миграции — **отдельная** операция (`alembic upgrade head`). Импорт не вызывает `create_all` и не мигрирует схему; при отсутствии head / `case_snapshots` — отказ.

## Стадии и транзакции

1. **Stage + preflight (без записи в целевую БД)**  
   - ровно один CSV на роль companies / payments / person_links;  
   - копии во временный staging; SHA-256 и счётчики — по **staged** байтам;  
   - существующий `run_dry_run` по staging;  
   - блокирующие ошибки → `preflight_failed`, в БД ничего нет.

2. **Identical skip / version-label** (чтение БД)  
   - если в том же `slot_key` есть `ready`/`active` с тем же `role→SHA-256` → `identical_skip`, без новых строк;  
   - `failed`/`building` не считаются успехом;  
   - занятый `version-label` другим содержимым → отказ;  
   - разные slots не смешиваются.

3. **Метаданные** (отдельный commit)  
   `case_snapshots(building)` + `case_import_runs(running)` + три `case_import_files(pending)`.

4. **Загрузка файлов** (по одной транзакции на файл)  
   Порядок: компании → платежи → связи людей.  
   Перед каждым загрузчиком повторно сверяется SHA staged-файла с manifest.  
   Успех: commit (строки + `import_file.status=completed`).  
   Ошибка: rollback текущего файла; отдельной транзакцией snapshot/run → `failed`; ранее completed файлы остаются.

5. **Финальная проверка → ready** (одна транзакция)  
   Счётчики = manifest; product marks / resolutions; платежи и links в том же snapshot.  
   Успех: `snapshot=ready`, `run=completed`, `built_at`, `validation_report_json` (manifest + checks).  
   Ошибка проверки: snapshot/run → `failed` (не `ready`).

`ready` = готов к **отдельной** активации, не «уже на сайте». Active pointer не меняется.

## Повторы и ошибки

| Ситуация | Результат |
|----------|-----------|
| Повтор с теми же SHA в slot | `identical_skip`, тот же snapshot |
| Preflight fail | 0 строк в БД |
| Ошибка загрузчика файла N | файл N откатан; 1..N-1 сохранены; snapshot `failed` |
| Ошибка финальной проверки | не `ready`; доменные строки остаются |
| Файл изменён после preflight | hash mismatch → `failed` |
| Коллизия `version_label` / parallel insert | понятный отказ, без перезаписи |

Resume и дописывание `failed`/`building` **не** реализованы: каждый `--load` — новая попытка (кроме identical_skip).

## Выполненные проверки

```bash
pytest tests/test_case_import_pipeline.py \
       tests/test_case_org_loader.py \
       tests/test_case_payment_loader.py \
       tests/test_case_person_link_loader.py \
       tests/test_case_dry_run.py
```

На временном SQLite (`foreign_keys=ON`, синтетика):

- полный импорт → `ready`;
- повтор → identical_skip без новых snapshot;
- preflight → нет записей;
- ошибка платежей после batch → каталог сохранён, платежи 0, snapshot failed, active pointer прежний;
- ошибка финальной проверки → не ready;
- tamper после preflight → fail;
- конфликт version-label;
- независимость slots;
- CLI без `--database-url` → отказ;
- dry-run не трогает application DB;
- нет Company / membership / identity links.

Benchmark 50k payments не повторялся.

## Ограничения

- Нет activate / resume / CLI записи в рабочую БД по умолчанию  
- Реальный конкурсный набор на этом этапе не загружался  
- `ready` ≠ видимый продукт без отдельной активации  
