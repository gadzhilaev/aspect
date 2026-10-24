# Key-rate scenario basis fix (Этап 5.2)

Дата: 2026-10-22  
Опирается на: `docs/FINANCE_SCENARIO_BASIS_AUDIT.md`  
Код изменён: financial simulator, scenario_display, compare_scenarios, seed attrs, тесты, MOBILE_API.

---

## 1. До / после

| | До (5.1) | После (5.2) |
|--|----------|-------------|
| Δ ставки | `shock = clamp(severity/40)` (≥0.2; `severity or 50`) | **observed** из доверенных attrs / текста hold **или** явный `assumed_rate_change_pp` |
| Hold + высокий severity | `extra_annual_cost > 0` | observed Δ=0 → annual sensitivity **0** (без what-if) |
| Нет Δ | всё равно считали proxy | `status=unavailable`, пустые scenarios |
| `claimed_delta_pp` | мог бы путать | **игнорируется** |
| Прогноз / «ожидается сохранение» | severity→shock | basis=`none` |
| Near-term + FX ₽ от severity | в baseline | `null` + `*_status=unavailable_*` (до 5.4) |
| Единица долга | formatter всегда «₽» | `debt_amount_unit` (`unspecified` → «ед. введённого долга») |
| `impact_score` / `score_kind` | severity signal | **без изменений** |
| Supply-chain simulator | — | **не трогали** |

### Формула rate-sensitivity (когда есть Δ)

```
annual_rate_sensitivity = debt_amount × (floating_share_percent/100) × (delta_pp/100)
```

- `delta_pp` — изменение **ключевой ставки**, не расходов компании.
- Знак сохраняется (снижение → отрицательная чувствительность).
- Это **условная годовая** чувствительность при допущении переноса на плавающую долю; без дат пересмотра не утверждается немедленный / 90-дневный факт расхода.

Модель: `{simulator_model_version}-finance-rate-v2`.

---

## 2. Политика доверия event attributes

### Доверенный observed

1. Блок `attributes_json.key_rate_decision` **или** плоские поля при  
   `rate_decision_status ∈ {observed, cb_decision, decision_observed, observed_cb_decision}`:
   - `rate_from` + `rate_to` → `delta_pp = rate_to - rate_from`;
   - если ещё дан `rate_delta_pp` / `delta_pp` и он **не** совпадает с разностью → **conflict** (не выбираем «удобное»);
   - только `rate_delta_pp` при trusted status (без from/to) → observed.
2. Текст **свершившегося** решения о сохранении (title / первое предложение summary):
   - глагольные паттерны «сохранил ставку», «оставил ставку неизменной», «ставка без изменений» и т.п.;
   - noun «сохранение ключевой ставки» только без маркеров ожидания;
   - **отклоняется**: ожидание/прогноз (`ожида*`, `прогноз*`, …), отрицание (`не сохранил`), пересказ прошлого.

### Не observed

- `severity` (включая 0 и «высокий»);
- `claimed_delta_pp`, `demo_story`, bank forecast attrs;
- `rate_from`/`rate_to` **без** trusted status;
- «ожидается сохранение», прогнозы банка.

Демо-seed `evt_rate_hike_001`: добавлены `rate_decision_status=observed`, `rate_from=16`, `rate_to=17` (не `claimed_delta_pp`).

---

## 3. What-if

Параметр `assumed_rate_change_pp` (п.п.) в:

- `simulate_financial_scenarios(..., assumed_rate_change_pp=)`;
- `compare_scenarios(..., assumed_rate_change_pp=)` и tool args.

Поведение:

| Observed | Assumed | Результат |
|----------|---------|-----------|
| conflict | * | unavailable |
| none | нет | unavailable |
| none | да | scenarios с basis=`assumed` |
| hold (0) / hike | нет | baseline + action alternatives на observed |
| hold (0) | да (≠0) | baseline observed 0 **и** отдельный what-if ряд; факт не перезаписывается |

Альтернативы «Снизить валютную экспозицию» / «Пересмотреть финансирование» сохранены как **условия модели** (коэффициенты не «доказанная эффективность»). FX-деньги в них не подставляются из severity.

---

## 4. Единицы и смешанные метрики

- `debt_amount_unit`: из `debt_amount_unit` / `debt_currency` профиля, иначе `unspecified`.
- Display (`scenario_display.format_debt_amount`): без подтверждённого RUB **не** добавляет «₽».
- `near_term_pressure`, `fx_exposure_index`: для новых rate-сценариев `null` + status unavailable (этап 5.4).
- `funding_pressure_percent` от severity-proxy **снят** (`null`).

---

## 5. Подписи (backend)

| basis | `scenario_display` |
|-------|-------------------|
| assumed | «При допущении изменения ставки на … п.п.» + условная чувствительность |
| observed | факт Δ п.п. + оговорка условного переноса на кредит |
| none/conflict | без выдуманного денежного эффекта |
| legacy (нет `rate_change`) | не зовётся observed; legacy-оценка без ₽ |

Полная унификация UI/decision copy — **этап 5.3**. История чата не переписывается.

---

## 6. Совместимость Scenario

Новые `parameters_json` содержат `rate_change`, `debt_amount_unit`, `model_version`, `severity_used_as_rate_shock=false`, `shock_proxy_pp=null`.

`legacy_rate_basis_from_parameters()`:

- есть `rate_change` → как есть;
- только старый `shock_proxy_pp` → basis=`assumed`, `legacy=true`, **не** observed;
- пусто → basis=`none`, legacy.

Старые строки **не** пересчитываются.

---

## 7. Тесты

`tests/test_rate_scenario_basis.py` — чистые функции + persist через TestClient.  
Регрессия: `test_macro_finance_ux`, `test_scenario_display`, `test_assessment_trust` (finance score_kind).

Покрыто: hold+severity; severity 0; what-if; hike/cut; conflict; прогноз; claimed_delta; unknown Δ; unknown floating; known zeros; no auto ₽; no FX mix; persist basis; legacy read.

---

## 8. Остаётся на 5.3 / 5.4

**5.3** — UI / decision reason / chips: единые формулировки what-if vs факт; не смешивать «давление ставки» в decision copy.  
**5.4** — FX: курсы, конвертация, near-term без severity-proxy; единицы валютных объёмов.

Без организаторов по-прежнему нельзя: даты пересмотра кредита, подтверждённый договорный портфель, официальный курс на дату.

---

## 9. Ключевые файлы

- `app/services/financial_simulator.py`
- `app/services/scenario_display.py`
- `app/services/assistant/tools.py` (`compare_scenarios`)
- `scripts/seed_demo.py` (trusted attrs hike)
- `docs/MOBILE_API.md`
- `tests/test_rate_scenario_basis.py`
