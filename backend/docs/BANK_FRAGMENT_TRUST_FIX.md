# Bank fragment trust fix (Этап 2.6.1)

Дата: 2026-10-21. OCR/QA артефакты не переписывались; визуальная сверка не выполнялась; БД не трогалась.

## Проблема

На этапе 2.6 normalize при отсутствии полей выводил:

- `primary_region_type` → provisional `prose` (`primary_region_type_provisional_prose`);
- `content_type_status` → inferred `confirmed` (`content_type_status_inferred_confirmed`).

Warning не снимал допуск: `compute_fragment_eligibility` получал уже «поднятые» значения → 21/21 AI evidence на реальном корпусе вопреки политике 2.4–2.5.

## Исправление

Единая политика — только `compute_fragment_eligibility` (+ `region_count` в dry-run). Normalize:

| Поле отсутствует | Результат | AI / exact quote |
|------------------|-----------|------------------|
| `primary_region_type` | `unverified` | нет |
| `content_type_status` | `unknown` | нет |

Дополнительно:

- `verification_status=verified` подтверждает сверку **текста**, не тип области и не fact/forecast/interpretation.
- Высокий OCR confidence и spot-check **страницы** не повышают допуск фрагмента.
- Единообразный явный `regions[].region_type` на всех regions фрагмента допускается как детерминированный перенос с warning и указанием источника; в корпусе 2.3 таких случаев нет.
- Подтверждение **не** выводится из факта `verified`.
- Storage vs use: неполные метаданные → warning, `suitable_for_storage=true`, но `suitable_for_ai_evidence` / exact quote только по eligibility.
- Search candidate разрешён для `verified` + `unverified` region type, с явной отметкой `missing_trust_fields`.
- Regions: непустой список ≠ prose; NULL bbox не ошибка и не чинится фиктивными координатами.

Код: `app/services/bank_materials/normalize.py`, отчётные поля в `dry_run.py`. Регрессии: `tests/test_bank_import_dry_run.py` (`test_trust_*`, явный confirmed prose, отсутствие старых warning-кодов).

## Реальный корпус после фикса

| | До | После |
|--|----|-------|
| eligible_search | 21 | 21 |
| eligible_ai_evidence | 21 | **0** |
| eligible_exact_quote | 18 | **0** |
| ok / blocking | True / 0 | True / 0 |

Все 21 фрагмента: missing `primary_region_type` + `content_type_status`; deny `region_type_unverified`. В существующих QA нет явных полей для безопасного переноса — неподтверждённое оставлено неподтверждённым.

Подробная таблица и обновлённые warnings — в [BANK_IMPORT_DRY_RUN.md](BANK_IMPORT_DRY_RUN.md).

**Стоп этапа 2.6.1.**
