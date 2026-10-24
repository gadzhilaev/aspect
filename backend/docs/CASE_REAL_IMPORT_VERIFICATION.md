# Real case import verification (Этап 1.9)

Дата: 2026-10-20  
Полный проверочный импорт реальных CSV из `data/case/raw/` в **изолированную** SQLite-БД.  
Активация snapshot и подключение к сайту **не** выполнялись.

## Путь проверочной БД

Успешный прогон:

`data/case/verification/case_verify_20261020T121608Z.db`  
(абсолютный путь на машине проверки сохранён в `data/case/verification/latest_db_path.txt`)

Каталог `data/case/verification/` добавлен в `.gitignore` (БД и технические отчёты не в Git).

След первой неудачной попытки (сохранён, не очищался):

`data/case/verification/case_verify_20261020T150934Z.db`  
+ `data/case/verification/failure_attempt1.json`

## Команда (без секретов)

Миграция (отдельно; URL через `DATABASE_URL` только для процесса Alembic — так читает `alembic/env.py` → `get_settings().database_url`):

```bash
# DATABASE_URL=<sqlite-url-of-verification-db>
python scripts/prepare_case_verify_db.py
```

Импорт (явный `--database-url`, без неявного рабочего `DATABASE_URL`):

```bash
python -m app.jobs.import_case_data \
  --load \
  --input-dir data/case/raw \
  --slot-key competition_default \
  --version-label hack-raw-v2 \
  --database-url "sqlite:///C:/…/data/case/verification/case_verify_20261020T121608Z.db" \
  --report-dir data/case/verification/reports/import_hack_raw_v2 \
  --batch-size 2000
```

На практике прогон шёл через `scripts/run_case_real_import.py` с теми же параметрами.  
В лог писался только редактированный URL (`sqlite:/C:/…`, без пароля).

Исходные CSV **не** изменялись. `create_all` / seed / activate не запускались.

## Head миграции

| | |
|--|--|
| Alembic head | `006` |
| Revision в проверочной БД | `006` |
| `case_snapshots` | присутствует |

## Итоговые статусы и счётчики

| Поле | Значение |
|------|----------|
| `snapshot_id` | `d8fa5477-058e-47c2-9c88-030a20ea92fe` |
| `import_run_id` | `2675bc78-92f6-40d4-9c2f-9dc0b976485d` |
| snapshot status | `ready` |
| run status | `completed` |
| files | 3 × `completed` |

### Manifest (= фактические CSV)

| Роль | Файл | Записей | SHA-256 |
|------|------|---------|---------|
| companies | `df_Uid_data_hack.csv` | 85 525 | `cb48983806ce7ca0…6da4a983` |
| payments | `df_Uid_payment_hack.csv` | 1 380 585 | `30095f75bead1a1d…458a1cab3` |
| person_links | `df_Fid_Uid_link_hack.csv` | 12 514 | `3d9c718e2a87304f…086a1b58` |

Счётчики совпали с ориентирами прошлого dry-run; hashes совпали с файлами на диске (файлы с dry-run не менялись).

### Доменные строки в БД

| Таблица | COUNT |
|--------|------:|
| `case_org_catalog_rows` | 85 525 |
| `case_payments` | 1 380 585 |
| `case_person_org_links` | 12 514 |
| `case_org` | 204 708 |
| `case_org_product_marks` | 513 150 (= 85 525 × 6) |
| `case_org_field_resolution` | 85 514 (уникальные org с профилем; меньше строк из‑за multi-row UID) |
| `case_persons` | 11 120 |
| `case_org` orphans (`has_catalog_profile=false`, `absent`) | 119 194 |

## Независимые проверки (SQL)

Скрипт: `scripts/verify_case_real_import.py` → `data/case/verification/independent_verify.json`.  
Результат: **все проверки ok=true**.

| Проверка | Результат |
|----------|-----------|
| snapshot=`ready`, run=`completed`, 3 файла `completed` | OK |
| counts = manifest = CSV | OK |
| SHA-256 disk = DB = manifest | OK |
| ссылки только нужного snapshot | OK |
| `PRAGMA foreign_key_check` | 0 нарушений |
| сироты без выдуманного профиля | OK |
| `U_428697`: 12 вариантов, `profile_resolution=conflict` | OK |
| identical payment rows: ranks `[1, 2]` | OK |
| F–U `relation_kind=unspecified` | OK |
| unit/currency/period = NULL | OK |
| Company / User / membership / identity links = 0 | OK |
| `case_active_snapshot` для slot = отсутствует | OK |

### Денежная точность (CSV → Decimal → БД)

Полные исходные строки в отчёт не включались.

| Проба | Результат |
|-------|-----------|
| Max `PAY_AMT` | raw `1118581311000.0`, amount совпал с `parse_money_numeric_20_1` |
| Revenue rows 1, 1000, 50000, 85525 | raw сохранён; amount = Decimal из CSV |

## Повторный запуск

Та же БД, `version-label=hack-raw-v2-rerun` (тот же набор SHA):

- status: **`identical_skip`**
- тот же `snapshot_id`
- Δ COUNT по всем `case_*` таблицам: **0**

Артефакт: `data/case/verification/identical_skip_verify.json`.

## Время, память, размер

### Время (`time.perf_counter`, успешный прогон)

| Стадия | Сек |
|--------|----:|
| Preflight (dry-run) | ≈ 84 |
| companies | 718.6 |
| payments | 181.8 |
| person_links | 1.8 |
| **Всего (pipeline)** | **≈ 1006** (~16.8 мин) |

### Размер БД

≈ **1 810 628 608** байт (~1.69 GiB) после успешного импорта.

### Память

| Способ | Значение |
|--------|----------|
| `GetProcessMemoryInfo` PeakWorkingSetSize в конце скрипта | **не получен** (`null`) |
| Наблюдение `Get-Process` WorkingSet во время payments | ≈ **1 034 022 912** байт (~986 MiB) |

Это **не** tracemalloc и **не** утверждается как полный OS RSS.  
Пик RSS достоверно end-to-end не измерен.  
Результат SQLite **не** экстраполируется на PostgreSQL.

## Ошибки и исправления

### Попытка 1

БД: `case_verify_20261020T150934Z.db` (сохранена).  
После ~80k companies: `sqlite3.OperationalError: too many SQL variables` на  
`UPDATE case_org … WHERE id IN (…)` по ~85k id.

### Исправление кода

В `load_org_catalog.py` (и финальной проверке pipeline) крупные `IN` / bulk INSERT резолюций нарезаны чанками.  
Регрессия: `tests/test_case_org_loader.py::test_large_org_in_lists_are_chunked` (passed).

### Попытка 2

Новая БД `case_verify_20261020T121608Z.db`, `version-label=hack-raw-v2` → **ready**.

Дополнительно: редкое stderr-логирование стадий/прогресса строк (без изменения логики загрузки и без вывода исходных строк).

## Ограничения

- Snapshot **не** активирован; active pointer не создавался.
- Company / membership / identity links / impact / AI не создавались.
- Resume не использовался.
- Проверка только на SQLite; production Postgres не гонялся.
- Первый failed-снимок оставлен для диагностики рядом с успешным.

**Стоп этапа 1.9:** полный проверочный импорт и независимая верификация завершены; активация — отдельный этап.
