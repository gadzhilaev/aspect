# FX scenario basis fix (этап 5.4)

Убраны severity-proxy деньги из **новых** FX-результатов. Денежный FX считается только при известных единицах и основаниях. Формулы rate (5.2) и supply-chain не менялись.

## Контракт (MVP, одна валютная пара)

| Поле | Смысл |
|------|--------|
| `fx_exposure_amount` | Сумма экспозиции `V` (включая известный 0) |
| `fx_exposure_currency` | Валюта суммы (ISO), напр. `CNY` |
| `fx_exposure_direction` | `payment` \| `receipt` |
| `fx_exposure_period` | Период суммы или отсутствует → «Период не указан» |
| `fx_quote_currency` | Валюта расчёта, напр. `RUB` |
| `fx_quote_convention` | Только `quote_per_exposure`: единиц quote за 1 exposure |
| `fx_rate_from` / `fx_rate_to` | Курсы в соглашении котировки |
| `fx_change.basis` | `observed` \| `assumed` \| `none` \| `conflict` |
| `source` | Источник курса / явного допущения |
| `model_version` | суффикс `finance-fx-v1` (пакет: `…-finance-rate-v2+fx-v1`) |

Котировка однозначна: **единиц валюты расчёта за 1 единицу валюты экспозиции** (RUB за 1 CNY). Направление пары **не** угадывается по severity или заголовку новости.

Несколько валют без полных данных **не** суммируются.

## Происхождение курсов

| Вход | Результат |
|------|-----------|
| `attributes.fx_rate_decision` со `status` ∈ trusted (`observed`, `market_observed`, …) + `rate_from`/`rate_to` | `observed` |
| `fx_from`/`fx_to` **без** trusted status | `none` (не observed) |
| Прогноз банка / `claimed_fx_delta` / severity | не observed, не Δ курса |
| Явный `assumed_fx_change_percent` + известный `rate_from` | `assumed`, `rate_to = rate_from × (1 + %/100)` |
| What-if % без `rate_from` | качественный % без денежного эффекта в quote |
| Противоречие пары / from-to vs delta / невалидный курс | `conflict` |
| Legacy `fx_purchase_volume` без валюты | **не** становится `V` и не ₽ |

`optional_finance.fx_rate_*` сами по себе не повышают статус до observed.

## Формулы и единицы

Для суммы `V` и курса `R` (quote за 1 exposure):

```
baseline_value = V × R_from
scenario_value = V × R_to
value_change   = V × (R_to − R_from)
```

Смысл результата:

- `payment` → изменение **стоимости платежа** (не «фактический убыток» без данных);
- `receipt` → изменение **эквивалента поступления** (не «прибыль»).

Даже `observed` рыночный курс даёт **условную чувствительность**, не доказанный курс исполнения договора.

Арифметика: `Decimal`, округление денег `ROUND_HALF_UP` до `0.01`; курсы квантуются до `0.000001`. Курсы должны быть конечными и `> 0`. Неизвестное **не** превращается в 0.

Ограничения (всегда в `limitations`, если нет данных): комиссии, хеджирование, налоги, даты исполнения не учтены.

## Готовность rate vs FX

| Track | Нужно для денег |
|-------|-----------------|
| rate (5.2) | `debt_amount`, `floating_rate_share_percent` + observed/assumed Δ ставки |
| fx (5.4) | typed exposure (amount+currency+direction+quote) + observed/assumed курсы |

На этапе 5.4 `has_finance_context` / `finance_ready` ещё требовали пять legacy keys (блокировали API-путь для чистого FX). **Исправлено в 5.5:** готовность по track (rate или FX). Чистый FX-расчёт в симуляторе **не** требует долга и плавающей доли.

## Отображение

Presentation-контракт расширен веткой `track: "fx"` (`finance_scenario_presentation` / `financeScenarioPresentation.ts`).

Показывается: пара и направление котировки; observed или what-if; сумма и валюта; изменение стоимости платежа / эквивалента поступления; валюта результата; период или «Период не указан»; ограничения.

Rate-подписи (п.п., годовая чувствительность долга) **не** переиспользуются для FX. Горизонт 90 дней / год **не** приписывается без основания (для FX — только период экспозиции).

`none` / `conflict` — без фиктивных денежных метрик. Legacy сценарии не пересчитываются; severity-proxy не объявляется observed.

## Совместимость

- Старые профили с `fx_purchase_volume` читаются; без typed FX → `fx calculation unavailable`.
- Сохранённые Scenario с `shock_proxy_pp` → legacy presentation, не observed.
- Альтернатива `reduce_fx_exposure` в rate-track остаётся модельным условием rate; денежный FX — отдельные строки `track=fx`.

## Поля для следующего этапа (setup UI)

Форма должна уметь отправлять (без defaults из конкурсных платежей / страны ФТС):

1. `fx_exposure_amount`
2. `fx_exposure_currency`
3. `fx_exposure_direction` (`payment`|`receipt`)
4. `fx_exposure_period` (опционально)
5. `fx_quote_currency`
6. `fx_quote_convention` = `quote_per_exposure`
7. Опционально профиль `fx_rate_from` (не заменяет event observed)
8. Для what-if инструмента: `assumed_fx_change_percent`

Серверная валидация: `app/services/finance_validation.py` → `PATCH …/finance`.

## Проверки

См. `tests/test_fx_scenario_basis.py`, регрессии `test_rate_scenario_basis.py`, presentation BE/FE fixtures, `npm run build`.
