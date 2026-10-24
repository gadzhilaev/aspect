# Case snapshot activation (Этап 1.10)

Дата: 2026-10-20  
Атомарное переключение `ready` → `active` через `case_active_snapshot`.  
Импорт (`--load`) **сам по себе не активирует** данные.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/services/case_data/activate_snapshot.py` | Сервис + `get_active_snapshot` + `run_activation` |
| `app/jobs/activate_case_snapshot.py` | Отдельный CLI |
| `app/services/case_data/__init__.py` | Экспорт |
| `app/jobs/import_case_data.py` | Уточнение: активация — отдельная команда |
| `tests/test_case_snapshot_activation.py` | Синтетические проверки |
| `docs/CASE_SNAPSHOT_ACTIVATION.md` | Этот отчёт |

Рабочая БД и успешная БД полного импорта (этап 1.9) **не** менялись.  
Реальные CSV повторно не загружались. API/frontend не трогались.

## Интерфейс

```python
from app.services.case_data import run_activation, get_active_snapshot

result = run_activation(
    database_url="sqlite:///…/temp.db",  # явный URL
    slot_key="competition_default",
    snapshot_id="<ready-uuid>",
    expect_no_active=True,                 # XOR
    # expected_active_snapshot_id="<uuid>",
)
# result.outcome: "activated" | "already_active"
# result.previous_snapshot_id, result.current_snapshot_id

ref = get_active_snapshot(session, slot_key="…")
# ActiveSnapshotRef | NoActiveSnapshot
# Для одного разбора сохранить ref.snapshot_id и не перечитывать pointer.
```

### CLI

```bash
python -m app.jobs.activate_case_snapshot \
  --database-url "sqlite:///./path/to/db.db" \
  --slot-key competition_default \
  --snapshot-id <uuid> \
  --expect-no-active
# или:
#   --expected-active-id <current-active-uuid>
```

Обязательны: `--database-url`, `--slot-key`, `--snapshot-id`, и ровно один из  
`--expect-no-active` / `--expected-active-id`.  
Рабочий `DATABASE_URL` / `.env` не подставляются. Секреты в лог не пишутся.

Вывод: `outcome=… slot=… previous=… current=…`

## Предусловия

- Кандидат принадлежит `slot_key`
- `status=ready` (building / failed / retired — отказ; restore retired вне этапа)
- Import run `completed`, все import files `completed`
- `validation_report_json` содержит `final_checks` и `ready_at`
- Счётчики файлов согласованы с manifest в отчёте (если есть)

## Границы транзакции

Одна транзакция (`BEGIN IMMEDIATE` на SQLite; advisory lock на PostgreSQL):

1. Проверка целостности pointer ↔ `status=active`
2. Проверка expected active / expect-no-active
3. Идемпотентный выход, если кандидат уже согласованный active
4. **Сначала** прежний active → `retired` (+ `retired_at`)
5. **Затем** ready → `active` (+ `activated_at`)  
   (порядок учитывает partial UNIQUE «один active на slot»)
6. Upsert `case_active_snapshot` → новый id (`updated_at`)
7. Повторная проверка целостности → COMMIT

При ошибке — полный ROLLBACK. Старые снимки и доменные строки не удаляются.

Первая активация (строки pointer ещё нет): `BEGIN IMMEDIATE` / advisory lock  
сериализют запись; pointer создаётся в той же транзакции.  
`SELECT FOR UPDATE` по отсутствующей строке не используется как единственная защита.

## Защита от гонок

- Клиент обязан передать актуальное ожидание (`expected-active-id` или `expect-no-active`).
- После захвата блокировки ожидание сверяется с БД; иначе `ActivationConflictError`.
- Два конкурирующих переключения с одним и тем же expected: один `activated`, второй conflict (или lock-ошибка СУБД); двух `active` в slot не остаётся.

## Идемпотентность

Повторная активация уже текущего согласованного snapshot → `already_active`,  
**без** обновления `activated_at` / `updated_at`.

Противоречие pointer/status → `ActivationIntegrityError`, без авто-«ремонта».

## Выполненные тесты

```bash
pytest tests/test_case_snapshot_activation.py
```

На временном SQLite (`foreign_keys=ON`, файловая БД для конкуренции):

| Сценарий | Результат |
|----------|-----------|
| Первая активация | OK |
| A → B | OK (A retired, pointer → B) |
| Повтор B → no-op | OK |
| Неверный slot / building / failed | отказ |
| Неполный импорт / нет final_checks | отказ |
| Устаревший expected-active-id | conflict |
| Ошибка между UPDATE → rollback | A снова active, B ready, данные на месте |
| Противоречивые pointer/status | IntegrityError |
| Два concurrent switch | 1 success + 1 conflict; ровно один active |
| CLI с `--expect-no-active` | OK |
| Import CLI не активирует | OK |

**PostgreSQL-конкуренция:** не проверена — `ALEMBIC_POSTGRES_URL` не задан  
(тест `test_postgres_concurrency_not_configured` → skip с явной пометкой).

## Ограничения

- Реальный импорт этапа 1.9 **не** активировался этой командой
- Restore `retired` → active вне объёма
- Продуктовые API ещё не читают active pointer
- Resume импорта не связан с активацией

**Стоп этапа 1.10.**
