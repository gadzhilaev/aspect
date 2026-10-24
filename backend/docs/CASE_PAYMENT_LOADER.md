# Payment loader (Этап 1.6)

Дата: 2026-10-20  
Загрузка только платежей в **building** snapshot.  
F–U: `docs/CASE_PERSON_LINK_LOADER.md`. CLI записи, resume и активация — следующие этапы.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/services/case_data/load_payments.py` | Сервис `load_payments` |
| `app/services/case_data/__init__.py` | Экспорт загрузчика |
| `tests/test_case_payment_loader.py` | Проверки на временном SQLite |
| `docs/CASE_PAYMENT_LOADER.md` | Этот отчёт |

Модели, миграции, dry-run CLI, API и frontend **не** менялись.  
Рабочая БД и реальный `data/case/raw` **не** использовались.

## Интерфейс

```python
from app.services.case_data import load_payments

result = load_payments(
    session,                    # явная Session; SessionLocal внутри нет
    snapshot=building_snapshot, # CaseSnapshot.status == "building"
    import_run=run,             # CaseImportRun того же snapshot
    import_file=registered,     # CaseImportFile того же run
    csv_path=Path("..."),       # файл на диске
    batch_size=500,             # > 0; опционально
)
# PaymentLoadResult: skipped, rows_inserted, orgs_created,
# self_pay_rows, snapshot_id, import_run_id, import_file_id
```

Предусловия / ошибки:

| Проверка | Ошибка |
|----------|--------|
| `batch_size < 1` | `PaymentValidationError` |
| `snapshot.status != "building"` | `SnapshotNotBuildingError` |
| run/file не принадлежат snapshot | `ContextMismatchError` |
| SHA-256 файла ≠ `import_file.content_sha256` | `ContentHashMismatchError` |
| роль CSV / колонки / поля (как dry-run) | `PaymentValidationError` (`file`, `record_number`, `field`, `reason`) |
| частичная/противоречивая загрузка | `IncompletePaymentImportError` |

### Идемпотентность

Пропуск (`skipped=True`) **только** если одновременно:

- SHA-256 файла = `import_file.content_sha256`;
- `import_file.status == "completed"`;
- `row_count_loaded` = число data-записей в CSV = числу `case_payments` для `(run, source_file)`.

Пустой файл (только заголовок) допустим: `completed` + `row_count_loaded=0` → повторный вызов skip.

Наличие строк без `completed` или расхождение счётчиков → **`IncompletePaymentImportError`**.  
Загрузчик **не** дописывает, **не** удаляет строки и **не** делает resume.

## Правила записи

Каждая логическая CSV-запись → отдельная строка `case_payments`:

| Поле | Правило |
|------|---------|
| `payer_org_id` / `beneficiary_org_id` | FK на `case_org` того же snapshot |
| `pay_amt_raw` / `pay_cnt_raw` | исходные строки |
| `pay_amt` / `pay_cnt` | только при успешном разборе (как dry-run) |
| `source_file` / `source_row_number` / `row_content_sha256` | provenance |
| `is_self_pay` | `BENEFICIARY == PAYER` |
| `intra_file_dup_rank` | 1, 2, 3… для одинакового content hash **внутри** `(run, source_file)` |
| `amount_unit` / `amount_currency` / `period_label` | всегда NULL |
| `semantics_note` | `payment_aggregate_only` |

`PAY_CNT` — число платежей по исходной строке, не число строк файла.

**Не** суммируются строки, **не** считается подтверждённый оборот, **не** создаются поставки / edges / impact / Company / membership.

### Валидация (как dry-run)

| Поле | Некорректное / отсутствующее |
|------|------------------------------|
| `BENEFICIARY`, `PAYER` | блокирует |
| `PAY_AMT` | блокирует (не пишется с `parse_status=error`) |
| `PAY_CNT` | блокирует (`0`, нечисло → ошибка) |

Диагностика: файл, номер записи, поле, причина — без полной исходной строки.

### Организации-сироты

- Известный `U_*` в snapshot → переиспользуется; профиль **не** меняется.
- Отсутствующий → нейтральная `case_org`: `has_catalog_profile=false`, `profile_resolution=absent`.
- Один `U_*` → одна `case_org` в снимке, в т.ч. через границы batches.

### Повторы

- Все одинаковые строки сохраняются.
- `intra_file_dup_rank` считается через границы batches (пакетный `MAX(rank)` по content hash в БД + порядок внутри batch).
- Для другого `source_file` счётчик отдельный.
- Одна пара с разными `PAY_AMT`/`PAY_CNT` — разные записи (разный content hash), не «конфликт для исправления».

## Память и производительность

- Потоковый `iter_csv_rows`; bulk `INSERT` словарями (без ORM на каждую строку на весь файл).
- `intra_file_dup_rank` не держит неограниченный словарь всех hash файла: max rank запрашивается пакетами из БД.
- Размер SQL `IN` / `INSERT` ограничен (`_MAX_BIND_PARAMS`), с учётом лимитов параметров SQLite.
- Кэш `uid → org_id` растёт с числом **сторон**, не с числом payment content hashes.

### Синтетический прогон 50 000 строк (временный SQLite)

| Метрика | Значение |
|---------|----------|
| Строк | 50 000 |
| `batch_size` | 500 |
| `time.perf_counter` (только `load_payments`) | ≈ 15.5 s |
| `tracemalloc` peak | ≈ 9.1 MiB |

**Оговорки:** `tracemalloc` — не полный process RSS; прогон не проверяет реальный объём (~1.38 млн строк). Измерение в `tests/test_case_payment_loader.py::test_synthetic_50k_timing_and_tracemalloc`.

## Транзакции

- Загрузчик **не** вызывает `commit()` и **не** вызывает `rollback()`.
- Обычный Python exception **не** переводит Session автоматически в failed-состояние; незакоммиченные (в т.ч. уже `flush`) изменения остаются до `rollback()` вызывающего.
- Сценарий: первый batch записан → ошибка следующего ряда → caller `rollback()` → частичных следов нет.
- Resume по `last_row_number` **не** реализован.
- Snapshot не переводится в `ready`/`active`; `case_active_snapshot` не меняется.

## Выполненные проверки

```bash
pytest tests/test_case_payment_loader.py tests/test_case_org_loader.py tests/test_case_dry_run.py
```

Ожидаемо: payment + org + dry-run — все passed (временный SQLite, `foreign_keys=ON`).

Регрессии payment loader:

- оба участника известны / один или оба — сироты;
- self-payment;
- один U_ID в разных batches → одна org;
- дубли внутри batch и через границы;
- одна пара с разными суммами/PAY_CNT;
- Decimal + raw при чтении из БД;
- неверные ID / суммы / PAY_CNT;
- completed→skip, partial→error, hash mismatch;
- запрет active / чужого run;
- ошибка после первого batch + rollback;
- Company / membership / active pointer без изменений;
- пустой CSV → completed 0 → skip;
- синтетика 50k.

## Ограничения

- Нет F–U, CLI записи, activate, resume
- Реальный конкурсный CSV через загрузчик не прогонялся
- Загруженные платежи ≠ готовый / активный snapshot
- Денежные итоги и «подтверждённый оборот» не считаются
