# Finance setup for rate/FX (этап 5.5)

Пользователь указывает параметры долга и/или одной валютной операции, сохраняет их через обычный API и получает корректную доступность соответствующего track. Без фиктивного заполнения чужих полей.

## Проблема до 5.5

Симулятор 5.4 уже считал чистый FX без долга, но `has_finance_context` / `finance_ready` требовали **пять** legacy-ключей. `compare_scenarios` входил в финансовый путь только при `finance_ready` → FX-only профиль оставался на `finance_data_required` и не доходил до simulator через обычный API.

## Gates (разделение по track)

| Уровень | Rate | FX |
|---------|------|-----|
| Профиль достаточен | `debt_amount` + `floating_rate_share_percent` (0 = известный ноль) | `fx_exposure_amount` + `fx_exposure_currency` + `fx_exposure_direction` + `fx_quote_currency` |
| Основание события / what-if | observed/assumed Δ ставки | observed/assumed курсы (или % without money) |
| Денежный результат | оба условия | оба условия |

`has_finance_context` = rate **или** FX профиль готов → `finance_ready` для macro/FX-событий.

Заполненный профиль **не** гарантирует расчёт без основания события: `compare_scenarios` вернёт `missing_data` / unavailable scenarios.

Supply-chain gates и read-only agent loop не расширялись; write-tools в цикл не добавлялись.

Путь: setup → `PATCH /companies/{id}/finance` → профиль → `assessment_state` → `compare_scenarios` → `simulate_financial_scenarios` (rate и/или FX track).

## Поля формы (optional finance step)

### Кредиты
- `debt_amount`, `debt_amount_unit` / `debt_currency`, `floating_rate_share_percent`

### Валютные платежи и поступления (MVP: одна операция)
- `fx_exposure_direction` (`payment`|`receipt`)
- `fx_exposure_amount`, `fx_exposure_currency`, `fx_quote_currency`
- `fx_exposure_period` (опционально)
- `fx_rate_from` (опционально; **не** observed события)
- `fx_quote_convention` = `quote_per_exposure` при готовом структурном блоке

### Ликвидность (не обязательна для FX)
- `near_term_payments_90d`, `fx_purchase_volume` (legacy), `cash_reserve_days`
- `purchase_currencies` (список; пустой не становится RUB)

Котировка в UI: «RUB за 1 CNY». Смена пары очищает `fx_rate_from`.

`assumed_fx_change_percent` — параметр сценария, **не** поле профиля.

## PATCH-семантика

`optional_finance` **merges** в stored JSON:

| В PATCH | Эффект |
|---------|--------|
| ключ отсутствует | сохранить прежнее |
| `null` или `""` | удалить знание (не записать 0) |
| число/строка, включая `0` | известное значение |

`purchase_currencies` — полная замена списка.

При смене валютной пары (`fx_exposure_currency` / `fx_quote_currency`), если PATCH **не** передаёт явно `fx_rate_from`/`fx_rate_to`, сервер удаляет сохранённые курсы (защита клиентов без web-формы).

Валидация: `app/services/finance_validation.py`.

## Legacy

- Старые значения показываются без выдуманных единиц.
- `fx_purchase_volume` **не** мигрирует в `fx_exposure_amount`.
- При неоднозначности UI предлагает заново указать сумму с валютой и направлением; legacy-ключ не удаляется молча.

## UX

- Готовность раздельно: кредиты / валютная операция / чего не хватает.
- Нет «процента качества» по числу полей.
- «Сохранено» = профиль, не успех расчёта сценария.
- Пусто ≠ 0; «Не знаю» → clear (`null`).
- Ошибки API рядом с полями; ввод сохраняется при отказе.
- Смена компании сбрасывает форму (без переноса данных).

## Проверки

- `tests/test_finance_setup_rate_fx.py` — gates, merge/clear, API FX-only / rate-only, ACL, unknown basis.
- `web/scripts/finance-setup.test.mjs` — пусто/0, payload, legacy, котировка.
- Регрессии rate/FX presentation + `npm run build`.

Формулы 5.2 / 5.4 не менялись.
