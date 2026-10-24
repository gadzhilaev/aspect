# Case company link & context (Этап 1.11)

Дата: 2026-10-20  
Явная операторская привязка `U_*` → существующая `Company` и read-only чтение контекста активного snapshot.  
Публичные API и frontend **не** подключены.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/services/case_data/link_org_company.py` | Сервис привязки + `run_link` |
| `app/services/case_data/company_case_context.py` | Read-only контекст |
| `app/jobs/link_case_org_company.py` | Операторская CLI |
| `app/services/case_data/__init__.py` | Экспорт |
| `tests/test_case_company_context.py` | Синтетические проверки |
| `docs/CASE_COMPANY_CONTEXT.md` | Этот отчёт |

Рабочая БД и проверочная БД реального импорта **не** менялись.  
Реальные организации автоматически не привязывались.

## Интерфейсы

### Привязка

```python
from app.services.case_data import link_case_org_to_company, run_link

result = run_link(
    database_url="sqlite:///…/temp.db",  # явный URL
    slot_key="competition_default",
    external_uid="U_123",
    company_id="<existing-company-uuid>",
    linked_by="ops@example",             # опционально
)
# result.outcome: "linked" | "already_linked"
```

### CLI

```bash
python -m app.jobs.link_case_org_company \
  --database-url "sqlite:///./path/to/db.db" \
  --slot-key competition_default \
  --external-uid U_123 \
  --company-id <uuid> \
  --linked-by ops@example
```

Обязательны: `--database-url`, `--slot-key`, `--external-uid`, `--company-id`.  
Рабочий `DATABASE_URL` / `.env` не подставляются. Секреты в лог не пишутся.

### Чтение контекста

```python
from app.services.case_data import read_case_company_context

ctx = read_case_company_context(
    session,
    user=user_or_user_id,
    company_id=company_id,
    slot_key="competition_default",  # явно выбран сервером
)
# ctx.status ∈ {
#   not_linked, no_active_snapshot, uid_missing_in_snapshot,
#   profile_absent, profile_available
# }
# Для одного ответа: ctx.active_snapshot.snapshot_id зафиксирован;
# повторно pointer не перечитывается внутри вызова.
```

## Правила доступа и привязки

| Правило | Поведение |
|---------|-----------|
| Company должна существовать | иначе `LinkPreconditionError` |
| Slot с active snapshot | иначе отказ привязки |
| `U_*` в active + `has_catalog_profile` | сирота (только платежи/люди) — отказ |
| Повтор той же тройки | `already_linked`, без смены `linked_at` |
| Другой U для Company / другая Company для U | `LinkConflictError`, без перезаписи |
| Membership | **не** создаётся; привязка прав не даёт |
| Чтение | сначала membership; посторонний → `CaseContextAccessError` |
| Ручные поля Company | не переписываются |
| Смена snapshot того же slot | identity link сохраняется |
| UID исчез в новом snapshot | `uid_missing_in_snapshot`; данные retired **не** подставляются |
| Разные slots | независимы; link не копируется по совпадению U |

Автоматическая перепривязка и пользовательский endpoint выбора организации из кейса **не** реализованы.

## Структура результата (`profile_available`)

- **manual** — `name` / `industry` / `size_band` / `hq_region` Company (отдельно от кейса)
- **industry / OKVED** — только consensus; conflict → не confirmed
- **city / region** — то же
- **размер** — `workers_fns_gradation` / `workers_spark` / age; revenue **не** мапится в size_band
- **products** — `true` / `false` / `unknown` / `conflict` (false ≠ unknown)
- **factoring** — отдельный булев tri-state
- **FTS countries** — raw строки; `note=raw_fts_country_only_no_trade_direction`
- **group** — только `external_group_id` своей организации; чужие профили группы не отдаются
- **revenue** — raw + limitations (`unit`/`currency` = NULL)
- **conflicts / absent** — явные словари resolution
- **provenance** — `snapshot_id`, `source_file`, `source_row_numbers`, `catalog_row_ids`

`raw_json` каталога **не** возвращается.  
Платежи / F–U / чужие компании — вне объёма (следующий этап).

## Выполненные проверки

```bash
pytest tests/test_case_company_context.py
```

На временном SQLite (`foreign_keys=ON`, alembic upgrade head):

| Сценарий | Результат |
|----------|-----------|
| Успешная привязка + повтор без дублей | OK |
| Конфликт U/Company | OK |
| Нет Company / сирота | отказ |
| Membership не растёт от link | OK |
| Участник читает / посторонний отказ | OK |
| Snapshot A→B, link на месте | OK |
| UID нет в B → без данных A | OK |
| Conflict-поля не confirmed | OK |
| false ≠ unknown для продуктов | OK |
| Provenance = активный snapshot | OK |
| Ручные поля Company неизменны | OK |
| Чтение не пишет в БД | OK |
| Разные slots не смешиваются | OK |
| profile_absent / no_active_snapshot | OK |
| CLI link | OK |

## Ограничения

- Продуктовые endpoints / frontend не подключены
- Реальный импорт 1.9 не активировался и организации не привязывались
- Агрегаты связей (платежи, люди) — следующий этап
- Apply case → ручной twin — отдельный явный шаг (не через чат)
- Чтение не создаёт/не чинит identity links

**Стоп этапа 1.11.**
