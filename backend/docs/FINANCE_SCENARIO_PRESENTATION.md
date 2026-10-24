# Единый контракт отображения финансовых rate-сценариев (Этап 5.3)

Дата: 2026-10-22  
Формулы 5.2 **не** менялись. FX — этап 5.4.

---

## 1. Контракт

Единый адаптер:

| Слой | Модуль |
|------|--------|
| Backend | `app/services/finance_scenario_presentation.py` |
| Frontend | `web/src/lib/financeScenarioPresentation.ts` |
| Metric lines | `scenario_display` → вызывает presentation |
| UI lists | `scenarioMetrics.scenarioMetricSuffix` → presentation |

**Основание (`basis`) берётся только из полей** `results.rate_change_basis` / `parameters.rate_change` / legacy markers — **не** из названия сценария и не из величины числа.

Значения: `observed` | `assumed` | `none` | `conflict` | `legacy`.

### Доставка до клиента

| Путь | Что добавлено |
|------|----------------|
| `compare_scenarios` tool result | `parameters`, `model_version`, `scenarios[].presentation` |
| `scenario_comparison` block | те же поля в `data` |
| `GET /scenarios/{id}` | `presentation` (вычисляется при чтении, БД не переписывается) |
| `DecisionDetail.scenario` | `presentation`, `model_version` (аддитивно) |

`parameters.rate_change`, `debt_amount_unit`, `model_version` проходят через Scenario.parameters_json с этапа 5.2; presentation строится поверх них.

---

## 2. Формулировки

| basis | Факт / условие | Деньги |
|-------|----------------|--------|
| observed (Δ≠0) | «Ключевая ставка изменилась на … п.п.» | «Условная годовая чувствительность при переносе…» |
| observed (Δ=0) | «Ключевая ставка не изменилась» + hold_note | нулевая чувствительность ≠ «нет всех рисков» |
| assumed | «Что если ставка изменится на … п.п.» + badge «Допущение сценария» | условная чувствительность |
| none | «Недостаточно данных для расчёта изменения расходов» | нет числа |
| conflict | «Исходные данные о ставке противоречат друг другу» | нет числа |
| legacy | historical_note; badge «Допущение прежней модели» при shock_proxy_pp | историческая оценка без ₽/observed |

Отрицательный результат: «Снижение условной годовой нагрузки».  
Альтернативы хедж/рефинанс: `action_model_note` — коэффициенты модели, не гарантия.  
Observed + деньги: `credit_transfer_disclaimer` — не фактическое изменение кредита.

Horizon для finance: «Условный годовой горизонт чувствительности (не эффект за 90 дней)».

---

## 3. Единицы и периоды

- ₽ только при `debt_amount_unit` ∈ {RUB, RUR, ₽} → `debt_unit_confirmed_rub=true`.
- Иначе: «единицы введённой суммы долга».
- Годовой результат не подписывается как 90 дней.
- п.п. не смешиваются с % потерь; индекс funding не воскрешается из null.
- null/unknown ≠ 0; известный 0 сохраняется.

### PATCH finance и единица долга

`FinancePatchIn.optional_finance` — свободный `dict`. Simulator читает `debt_amount_unit` / `debt_currency` / `currency`.  
**Ограничение:** web setup **не** собирает эти ключи → в типичном профиле unit=`unspecified`. Не вводили RUB default и не расширяли setup в 5.3.

---

## 4. Затронутые экраны / потребители

| Потребитель | Изменение |
|-------------|-----------|
| Backend metric / chat enrichment | presentation lines |
| AssistantChat `scenario_comparison` | badge, fact / what-if / money раздельно; unavailable message |
| DecisionPage | chips + строки presentation у основания |
| Decision API reason / horizon / expected_effect | из presentation |
| GET scenario | presentation |
| prompts | правило 16 о basis |
| ScenariosPage | без отдельной трактовки basis (список обсуждений) |

Observed baseline и отдельный what-if в одном блоке визуально различаются (`basis`, badge, data-what-if).

---

## 5. Legacy

- БД Scenario **не** пересчитывается.
- `shock_proxy_pp` → legacy assumed прежней модели, не observed.
- Нет основания → «Историческая оценка: основание расчёта не сохранено».
- Исторический текст сообщений чата не переписывается; структурированные карточки могут показать пометку «Историческая модель» при чтении presentation.
- Открытие старого decision не падает и не подменяет результат новым расчётом формул.

---

## 6. Тесты

```powershell
pytest tests/test_finance_scenario_presentation.py tests/test_rate_scenario_basis.py tests/test_macro_finance_ux.py tests/test_scenario_display.py -q
cd web; npm run test:finance-scenario-presentation; npm run build
```

Одинаковые fixtures: hike, hold/0, cut, assumed, none/conflict, units, legacy, observed+what-if, null metrics, no label inference.

---

## 7. Ограничения

- FX presentation — 5.4.
- Setup UI не пишет currency долга.
- Полная унификация старых plaintext сообщений без presentation в blocks не делается (только новые блоки + read-time API).
- Визуальная/React e2e проверка не заявлялась.
