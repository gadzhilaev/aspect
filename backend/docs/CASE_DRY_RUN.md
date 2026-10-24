# Case CSV dry-run (Этап 1.4)

Дата: 2026-10-20  
Запись в прикладную БД / snapshot / import-run **не** реализованы.

## Команда

```bash
python -m app.jobs.import_case_data \
  --input-dir data/case/raw \
  --dry-run \
  --report-dir data/case/reports
```

Без `--dry-run` процесс завершается с кодом `2` и сообщением; запись не начинается.  
Dry-run **не** читает `DATABASE_URL` и не создаёт `case_*` строки.

Отчёты: `data/case/reports/case_dry_run_latest.json` и `.md` (каталог в `.gitignore`).

## Изменённые файлы

| Путь | Назначение |
|------|------------|
| `app/services/case_data/validate.py` | Переиспользуемые парсеры U/F/group, bool, money `NUMERIC(20,1)`, `PAY_CNT` |
| `app/services/case_data/csv_io.py` | SHA-256, роль файла по колонкам, потоковый DictReader |
| `app/services/case_data/dry_run.py` | Оркестрация проверок, отчёты, временный scratch-каталог |
| `app/services/case_data/__init__.py` | Экспорт валидаторов |
| `app/jobs/import_case_data.py` | CLI |
| `tests/test_case_dry_run.py` | Юнит/интеграционные тесты dry-run |
| `tests/fixtures/case_dry_run/**` | Синтетические наборы |
| `.gitignore` | `data/case/reports/` |
| `docs/CASE_DRY_RUN.md` | Этот документ |

Модели, миграции, API и frontend не менялись.

## Поведение проверки

- Назначение файлов — по обязательным колонкам (companies / payments / person_links).
- Потоковое чтение; logical `record_number` после заголовка (quoted newline ≠ новая запись).
- Деньги: только `Decimal`, точное попадание в `NUMERIC(20,1)`; float / NaN / overflow / лишняя дробная часть → error.
- Неизвестный bool-флаг → invalid (не `false`).
- Валюта / единицы / период → warning `unknown_*`, без угадывания.
- Сироты и identical payment rows → warnings; импорт ими не блокируется.
- Денежные итоги как «подтверждённый оборот» не считаются.
- Глобальные join-индексы — in-memory + опциональный spill UID-списка во временный каталог (удаляется по завершении).

Коды выхода: `0` — нет blocking errors; `1` — ошибки значений/структуры; `2` — нет `--dry-run` / нет input dir.

## Тесты

`pytest tests/test_case_dry_run.py` — 12 passed:

- корректный набор;
- плохие/пустые флаги;
- money overflow / лишняя точность / nan / `PAY_CNT=0`;
- конфликт UID (warning);
- сироты (warning);
- одинаковые платёжные строки + варианты пары;
- quoted newline = 1 запись;
- CLI без `--dry-run`;
- dry-run не открывает application `SessionLocal`.

## Прогон на реальных файлах (`data/case/raw`)

| Метрика | Значение |
|---------|----------|
| Результат | `ok=True`, `can_proceed_to_load=True`, exit `0` |
| Длительность | ~86 s |
| Peak memory (tracemalloc) | ~458 MB |
| Blocking errors | **0** |

### Файлы

| Файл | Роль | Записей | SHA-256 (prefix) |
|------|------|---------|------------------|
| `df_Uid_data_hack.csv` | companies | 85 525 | `cb48983806ce7ca0…` |
| `df_Uid_payment_hack.csv` | payments | 1 380 585 | `30095f75bead1a1d…` |
| `df_Fid_Uid_link_hack.csv` | person_links | 12 514 | `3d9c718e2a87304f…` |

### Warnings (не блокируют загрузку)

| Тип | Count | Смысл |
|-----|-------|--------|
| `duplicate_company_uid` | 11 | Повторные строки `U_428697` |
| `conflicting_company_uid` | 1 | Конфликт полей у того же UID |
| `payment_party_not_in_catalog` | 114 552 | Уникальные стороны платежей вне справочника |
| `person_link_org_not_in_catalog` | 7 885 | F–U на отсутствующий U |
| `identical_payment_rows` | 1 | Лишнее вхождение identical content |
| `payment_pair_value_variants` | 9 | Одна пара Payer/Beneficiary с разными amt/cnt |
| `unknown_money_units` | 1 | Единицы/валюта неизвестны |
| `unknown_payment_period` | 1 | Период неизвестен |

### Агрегаты платежей (без «оборота»)

- both ends in catalog: 389 396  
- one end in catalog: 991 189  
- neither: 0  
- self-pay rows: 27 406  

Данные не правились; валидация не ослаблялась.

## Можно ли переходить к загрузке

**Да** с точки зрения структурной/value-валидации (нет blocking errors).

Импортёру всё ещё нужно учесть: сироты, конфликт `U_428697`, unknown units/period, identical/variant payment rows, atomic snapshot activate.  
Запись и активация snapshot на этом этапе **не** делались.
