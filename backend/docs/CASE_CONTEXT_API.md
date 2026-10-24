# Case context in company API (Этап 1.12)

Дата: 2026-10-20  
Аддитивный блок `case_context` в `GET /api/v1/companies/{company_id}/context`.  
Старый ответ сохранён; frontend не менялся; пользовательской привязки U_ID нет.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/schemas/company_context.py` | Типизированные схемы `CaseContextOut` и вложенных моделей |
| `app/services/company_context.py` | `build_case_context_block` + вызов `read_case_company_context` |
| `app/api/v1/companies.py` | Передача авторизованного `user` в `build_company_context` |
| `app/core/config.py` | `case_context_slot_key` |
| `.env.example` | Документация `CASE_CONTEXT_SLOT_KEY` (рабочий `.env` не трогали) |
| `contracts/openapi.json` | Обновлённый контракт |
| `docs/MOBILE_API.md` | Статусы, примеры, правила отображения |
| `tests/test_case_context_api.py` | HTTP-тесты на временной SQLite |
| `tests/test_company_context.py` | Проверка аддитивности на демо-контексте |
| `docs/CASE_CONTEXT_API.md` | Этот отчёт |

Рабочая БД и реальный импорт не менялись; организации не активировались и не привязывались.

## Настройка

```bash
# .env.example — раскомментировать при необходимости
CASE_CONTEXT_SLOT_KEY=competition_default
```

- Пустое / отсутствующее значение → `case_context.status = integration_not_configured`.
- Slot **не** принимается из query/body.
- Настройка **не** запускает импорт, привязку или активацию.
- Автовыбора «первого найденного slot» нет.

## Контракт

`CompanyContextOut` сохраняет все прежние поля и добавляет обязательный `case_context: CaseContextOut`.

```text
case_context.status ∈
  integration_not_configured | not_linked | no_active_snapshot |
  uid_missing_in_snapshot | profile_absent | profile_available
```

При `profile_available` заполнены:

- поля профиля (OKVED, город/регион, размерные градации) со статусами confirmed/conflict/absent;
- `products[]` с `true|false|unknown|conflict`;
- `factoring` + однозначный `explanation`;
- `fts_geography` (raw страны, без направления торговли);
- `group` (только свой `external_group_id`);
- `revenue` (строковый amount, unit/currency null, limitations);
- `conflicts` / `absent`;
- `provenance` (snapshot_id, version_label/seq, source_file basename, row numbers).

Ручные `industry_label` / `size_label` / `hq_region` **не** перезаписываются кейсом.  
`profile_ready`, coverage, пример impact, граф twin — без изменений от кейса.

Не возвращается: `raw_json`, локальные пути, чужие профили, секреты.

Обычные статусы кейса — HTTP 200 с пояснением.  
`ActivationIntegrityError` / внутренние ошибки кейса → 500 (`CASE_INTEGRITY` / `CASE_CONTEXT_ERROR`), не маскируются под «данных нет».  
Посторонний пользователь → 403. GET не пишет в БД.

## Выполненные проверки

```bash
pytest tests/test_case_context_api.py tests/test_company_context.py
```

| Проверка | Результат |
|----------|-----------|
| Старые поля сохранены | OK |
| `integration_not_configured` | OK |
| `not_linked` | OK |
| `no_active_snapshot` | OK |
| `profile_available` + conflicts/absent | OK |
| `uid_missing_in_snapshot` без backfill | OK |
| false ≠ unknown; факторинг | OK |
| Участник OK / посторонний 403 | OK |
| Смена snapshot → provenance | OK |
| raw_json / чужие профили отсутствуют | OK |
| GET не меняет link/membership/Company | OK |
| Существующие `test_company_context*` | OK (10 passed суммарно с API) |

## Ограничения

- Frontend не обновлён
- Нет пользовательского endpoint привязки
- Платежи / связи людей в `case_context` не входят
- Реальный импорт 1.9 не активировался и не привязывался через этот этап

**Стоп этапа 1.12.**
