# Аудит оснований финансовых сценариев (Этап 5.1)

Дата: 2026-10-22  
Область: key-rate / FX → `financial_simulator` → API/UI/assistant.  
Код, формулы, БД, API, UI, `.env` и процессы в этом этапе **не** менялись.  
Live LLM / браузер / OCR / commit не выполнялись.

Контрольные случаи: чистые вызовы `simulate_financial_scenarios` на временных
`Event`-объектах в памяти (без рабочей БД).

---

## 1. Цепочка происхождения результата

### 1.1 Key-rate / FX (единый код)

```
Event (title, category, severity, attributes_json, match_*)
  → is_macro_fx_event()          [app/services/relevance.py]
  → resolve_assessment_state()   [app/services/impact.py]
       finance_data_required | finance_ready
  → optional_finance_json        [CompanyProfileSettings; PATCH /companies/{id}/finance]
  → simulate_financial_scenarios [app/services/financial_simulator.py]
  → compare_scenarios (finance_ready branch)
       [app/services/assistant/tools.py]
  → Scenario.results_json + parameters_json (persist)
  → orchestrator → block scenario_comparison
  → UI: scenarioMetrics / scenario_display
       («давление финансирования», «доп. годовая нагрузка ~N ₽»)
```

Supply-chain `app/services/simulator.py` для макро/FX **не** используется
(`compare_scenarios` уходит в financial branch при `finance_ready`).

Bank fragments / OCR / case LOA **не** входят в формулу шока (см. prompts §12–14;
`docs/ASSISTANT_CASE_CONTEXT.md`). Это уже задокументированное ограничение.

### 1.2 Формулы (факт кода)

Файл: `app/services/financial_simulator.py` → `simulate_financial_scenarios`.

| Шаг | Выражение | Комментарий в коде |
|-----|-----------|-------------------|
| Shock | `shock = max(0.2, min(3.0, float(event.severity or 50) / 40.0))` | «0–100 → 0–3 pp rate / FX move proxy» |
| Floating | `floating_share = clamp(floating,0..100)/100` | из профиля |
| Годовая доп. нагрузка | `debt * floating_share * (shock / 100)` | shock трактуется как **п.п.** → доля |
| Near-term | `payments_90d * (0.02 + shock/200) + fx_volume * (shock/100) * 0.35` | смешение ставки и FX |
| FX index | `fx_volume/max(debt,1)*40 + shock*5` (cap 100) | индекс, не курс |
| Funding pressure | `25 + shock*12 + floating*20 + reserve_stress*0.3` (cap 100) | модельный индекс |
| Альтернативы | −12 / −18 к pressure; ×0.55 FX; refinance ×0.45 annual | what-if действий |

`parameters.shock_proxy_pp` сохраняется в Scenario; в UI как «п.п. события»
**не** показывается — показываются рубли и «давление %».

### 1.3 Числовые входы

#### Событие

| Поле | Источник | Единицы | Период | Обязательность | Default / отсутствие | Конфликт |
|------|----------|---------|--------|----------------|----------------------|----------|
| `severity` | Event | 0…100 triage | нет | да (модель) | `severity or 50`: **0.0 → 50** (falsy) | не сверяется с текстом «сохранена/повышена» |
| `title` / `summary` | Event | текст | — | да | — | **не** парсятся для Δ ставки/курса |
| `attributes_json` (delta, fx_from/to, forecast) | Event | любые | — | нет | игнорируются формулой | — |
| `category` / title keywords | Event | — | — | для маршрута | macro или «ставк/курс/валют/fx» → finance track | market+currencies без materials тоже macro/FX |

#### Компания (`optional_finance_json`)

| Ключ | Источник | Единицы в UI | Период | Обязательность для `finance_ready` | Default | Нет / ноль / конфликт |
|------|----------|--------------|--------|-------------------------------------|---------|------------------------|
| `debt_amount` | setup / PATCH finance | «Объём долга», **валюта не указана**; display как ₽ | не задан | да (ключ присутствует) | `_num` → 0 | missing → блок; **0 = известный ноль** |
| `floating_rate_share_percent` | setup | % долга | — | да | 0 | **0 ≠ «неизвестно»**; неизвестное нельзя отличить |
| `near_term_payments_90d` | setup | сумма (валюта не указана) | 90 дней | да | 0 | 0 допустим |
| `fx_purchase_volume` | setup | «закупки в валютах», **без кода валюты и курса** | не задан | да | 0 | объём сразу идёт в «₽»-формулы |
| `cash_reserve_days` | setup | дни | — | да | 0 | влияет на reserve_stress |

`has_finance_context` (`impact.py`): все пять ключей не `None`/не `""`.  
Значение `0` считается заполненным.

Конкурсный LOA / платежи case **не** заполняют эти ключи и **не** должны
(`docs/ASSISTANT_CASE_CONTEXT.md`, prompts).

#### Assessment / impact_score (отдельная ветка)

| Состояние | Файл | Что считается | Что это не |
|-----------|------|---------------|------------|
| `finance_data_required` | `impact.recompute_company_impact` | `severity × 0.5`, `score_kind=event_severity_signal` | персональный финэффект |
| `finance_ready` | то же | `severity × 0.55`, тот же kind; reason про сценарии | `extra_annual_cost` |

Это уже разведено в `docs/ASSESSMENT_TRUST_AUDIT.md` — **не** дефект этапа 5.1.

### 1.4 Подписи в UI / ассистенте

| Место | Что показывает | Риск смешения |
|-------|----------------|---------------|
| `scenario_display.format_scenario_metric_line` | «доп. годовая нагрузка ~N ₽», «давление на 90 дней ~N ₽» | рубль без оговорки «при допущении Δ=shock» |
| `web/.../scenarioMetrics.ts` | «давление финансирования P%» | индекс как «%» |
| `decisions._scenario_reason` | «давления ставки и валюты» | звучит как факт события |
| `decisions._horizon` | «Горизонт около 90 дней» | рядом с **годовой** нагрузкой |
| Assumptions в JSON | «Шок … пропорционален severity» | честно в данных; UI money line это не повторяет |
| ImpactPanel `finance_ready` | сигнал события ≠ финэффект | уже честно |
| Bank evidence | цитаты отдельно | не меняют симулятор (prompts) |

---

## 2. Три вида утверждений — сохраняет ли модель различие?

| Вид | Пример | До API/UI |
|-----|--------|-----------|
| **А. Факт события** | «Ставка сохранена на 14%» | Живёт в title/summary/sources/bank fragment. **Не** подаётся в shock. |
| **Б. Условный what-if** | «Если ставка/курс сдвинется на shock_proxy_pp…» | Фактически **весь** financial baseline — what-if от severity. Маркер `is_estimate` / assumptions есть; отдельного `shock_kind=assumed` **нет**. Альтернативы reduce_fx / refinance — тоже what-if (это ок). |
| **В. Прогноз банка** | «Банк ждёт 12% к концу 2027» | Retrieval/citations. **Не** становится shock (правильно). Но событие с severity всё равно гоняет формулу, если вызван `compare_scenarios`. |

**Вывод:** А и В от Б в данных **не** склеены на входе шока, но **Б маскируется под денежный эффект события** в подписях «доп. годовая нагрузка» без явного «допущение сценария, не факт новости». Hold и hike при одинаковом severity дают **одинаковые** рубли.

---

## 3. Контрольные случаи (чистые вызовы)

Профиль FULL = debt 100e6, floating 40%, payments_90d 8e6, fx 25e6, cash 21.

| # | Кейс | Результат | Интерпретация |
|---|------|-----------|---------------|
| 1 | Ставка сохранена, finance нет | `has_finance_context=False` → tool `missing_data` / `finance_data_required` | Ок: без профиля нет денежного сценария |
| 2 | Ставка **сохранена**, finance FULL, severity=55 | `shock_proxy_pp=1.375`, `extra_annual_cost=550_000` | **Дефект:** hold ≠ Δ=0; приписан прирост расходов |
| 3 | Ставка **повышена** (attrs `claimed_delta_pp=1`), тот же severity | **Идентично** кейсу 2; attrs игнорируются | Нет чтения наблюдаемой Δ |
| 4 | Известный ноль долга (+ fx_vol=0) | `extra_annual_cost=0`; near_term>0 от payments×f(shock) | Ноль долга ок; near-term всё ещё от severity |
| 5 | Floating = 0 | annual=0; pressure/near-term/FX остаются | «Фикс» и «доля неизвестна=0» неразличимы |
| 6 | FX без курса в событии | Тот же severity-shock; annual+fx pressure | Нет курса → всё равно «₽»-эффект |
| 7 | FX attrs `fx_from=90, fx_to=100` | **Игнорируются**; числа как в #6 | Наблюдаемый FX move не используется |
| 8 | Платежи/долг, fx_vol=0 | annual от ставки-proxy; near_term без fx_pressure | Частично осмысленно как what-if |
| 9 | «Прогноз банка» в title/attrs | attrs не читаются; severity→shock→annual | Прогноз **не** становится фактом ЦБ, но severity всё равно крутит what-if |
| — | severity=**0.0**, hold | из‑за `severity or 50` → shock **1.25**, annual **500_000** | **Дефект:** нулевая severity не «нет шока» |
| — | severity=100 | shock 2.5 (cap), annual 1e6 | Ожидаемо для proxy |

What-if альтернативы при FULL считаются стабильно (pressure −12/−18 и т.д.) — **удалять не предлагается**; нужна явная рамка допущения.

---

## 4. Матрица допустимости

| Входные данные | Допустимый результат | Нельзя утверждать | Запросить в setup (существующий) |
|----------------|----------------------|-------------------|----------------------------------|
| Макро/ставка, нет finance keys | `finance_data_required`, CTA `/company/setup?step=finance` | Денежный эффект, «расходы выросли» | Все `FINANCE_REQUIRED_KEYS` |
| Ставка **сохранена** (факт А), finance есть | Факт А + мониторинг рисков пересмотра/ликвидности **без** Δ-driven annual cost; либо явный what-if «если +X п.п.» | «Доп. годовая нагрузка N ₽ из‑за сохранения ставки» | — (не через чат) |
| Ставка выросла с известного a→b | What-if/observed Δ=(b−a) п.п. × debt × floating / 100 | Что severity = фактические п.п. | debt, floating; опционально даты пересмотра — **поля сейчас нет** |
| Долг = 0 (известный) | annual cost 0 | «Нет кредитных рисков вообще» | — |
| Floating неизвестен | Не считать rate annual; сказать «нужна доля» | Подставлять 0 как «нет плавающей» без различения | `floating_rate_share_percent` (сейчас 0=заполнено) |
| Фикс / нет сведений о пересмотре | Не приписывать немедленный рост % расходов | Автоматический hike cost | (даты пересмотра — нет в модели) |
| FX без курса и без явного what-if % | Индекс/качественно; или блок | Конвертация в ₽ «по шоку severity» | fx volume + валюты закупок; **курс/Δ не в setup** |
| FX с известными курсами + объём | Δ%/Δabs × объём (в валюте или через известный курс) | Severity-proxy как курс | объём; курс сейчас не собирается |
| Поступления/платежи одной валюты | Давление по payments×assumptions без FX члена | FX-эффект | near_term_payments_90d |
| Прогноз банка без Δ события | Цитата В с датой/источником | Авто-shock и «банк посчитал ваш долг» | — |
| LOA=true без finance | Тема для проверки | Сумма долга / рост расходов | optional finance вручную |

Единицы конкурсных денежных полей **не** выдумывать; LOA ≠ finance profile.

---

## 5. Дефекты vs допущения vs ограничения

### Дефекты (доказанные контрольными случаями)

1. **Наблюдаемое изменение ставки/курса не отделено от severity-proxy.**  
   Hold и hike с severity=55 → одинаковые `550_000` ₽ «доп. годовая нагрузка».
2. **`float(event.severity or 50)`:** severity `0.0` → 50 → ненулевой шок.
3. **Подпись UI/assistant** форматирует proxy-результат как деньги события
   (`доп. годовая нагрузка ~N ₽`) без обязательной рамки «допущение what-if».
4. **FX:** нет использования известных курсов; объём без курса всё равно в рублёвой формуле.

### Допущения модели (не баги сами по себе, если честно подписаны)

- What-if амплитуда от severity (0.2…3 «п.п.»).
- Альтернативы хеджа/рефинансирования (−12/−18 pressure, коэффициенты 0.55/0.45).
- `funding_pressure_percent` / `fx_exposure_index` — модельные индексы 0…100.
- Горизонт решения «~90 дней» рядом с **annual** cost — эвристика продукта.

### Ограничения данных (без организаторов / без новых полей)

- Нет обязательных `rate_from`/`rate_to` / `fx_from`/`fx_to` на Event.
- Нет валюты и курса у `debt_amount` / `fx_purchase_volume`.
- Нет даты пересмотра кредита; floating 0 = «нет» или «не знаю».
- Case LOA/DEP и bank forecast не дают денежный twin.

### Уже исправлено ранее (не предлагать снова)

| Тема | Где | Контроль |
|------|-----|----------|
| `impact_score` finance = severity signal, не company calc | `impact.py`, `ASSESSMENT_TRUST_AUDIT.md` | `tests/test_assessment_trust.py` |
| Без finance → CTA, без supply-chain paths | `test_macro_finance_ux.py` | key-rate without finance |
| LOA ≠ долг / рост расходов | prompts, case context | personalization docs |
| Bank evidence не меняет simulator | prompts §12 | design |

---

## 6. Минимальный план исправления (≤3 этапа)

Что **сохранить:** what-if альтернативы; `is_estimate`; finance gate; `score_kind`; bank/case разделение; supply-chain simulator отдельно.

### Этап 5.2 (первый, узкий) — отделить наблюдённую Δ от допущения

**Проблема:** hold → ненулевой annual cost; severity falsy→50.

**Сделать:**
- Ввести явное `shock_basis`: `observed` | `assumed` | `none` в `parameters` симулятора (аддитивно).
- Для rate: если событие/атрибуты дают Δ=0 или «сохранена» (минимальный детерминированный сигнал — **без LLM**), rate-компонент annual = 0; what-if только при явном assumed shock.
- Исправить `severity or 50` → различать `None` и `0.0`.
- Не читать bank forecast как observed Δ.
- Подпись metric line: при `assumed`/`none` не выдавать «доп. нагрузка» как факт события (например префикс «при допущении…» или скрыть annual при Δ=0).

**Контракты:** аддитивные поля в `parameters_json` / tool result; старые Scenario без `shock_basis` читать как legacy assumed (не пересчитывать историю чата).  
**Тесты:** hold+finance → annual=0 (или только явный what-if); hike с observed Δ; severity=0; attrs ignore bank forecast; регресс `test_macro_finance_ux`.

### Этап 5.3 — контракт честности what-if / legacy

- Документировать/проставить `shock_proxy_pp` + basis в API explanation.
- UI/assistant: единый текст assumptions; decisions reason не говорить «из‑за ставки», если basis≠observed.
- Старые сообщения **не** переписывать; новые блоки — с basis.

### Этап 5.4 — FX только с курсом или явным what-if %

- `fx_pressure` / рублёвая конвертация только при известной Δ курса **или** явном assumed_fx_pct в parameters.
- Без курса — индекс/качественно, без «млн ₽» от severity.
- Не раздувать setup новыми chat-полями; при необходимости — только существующий finance step / атрибуты события из пайплайна.

**Не** предлагается: переписать весь simulator; LLM в формулах; профиль через чат.

### Что останется невозможно без данных организаторов

- Реальный график пересмотра кредитов клиента.
- Подтверждённый портфель в рублях/валюте с договором.
- Официальный курс на дату без источника.
- Сведение bank forecast → персональный денежный PnL.

---

## 7. Регрессионные тесты (для будущих этапов)

1. Pure: hold severity>0 + FULL → нет positive rate annual без assumed flag.  
2. Pure: severity `0.0` не становится 50.  
3. Pure: observed Δ=1 п.п. ≠ severity/40 при наличии observed.  
4. Pure: fx attrs ignored сегодня → после 5.4 используются или явно assumed.  
5. API: `compare_scenarios` finance по-прежнему 3 estimate-сценария.  
6. Legacy Scenario без `shock_basis` отображается без падения.  
7. Bank fragment в контексте не меняет `parameters.shock_proxy_pp`.

**Не** заявлять финансовую точность по зелёным тестам — только согласованность контракта и отсутствие ложного «факта Δ».

---

## 8. Ключевые файлы

| Роль | Путь |
|------|------|
| Формула | `app/services/financial_simulator.py` |
| Gate / states | `app/services/impact.py` (`FINANCE_REQUIRED_KEYS`, `resolve_assessment_state`) |
| Macro detect | `app/services/relevance.py` (`is_macro_fx_event`) |
| Tool + persist | `app/services/assistant/tools.py` (`compare_scenarios`) |
| Подписи backend | `app/services/scenario_display.py` |
| Подписи web | `web/src/lib/scenarioMetrics.ts`, `AssistantChat.tsx` |
| Setup | `web/src/pages/CompanySetupPage.tsx`, `PATCH .../finance` |
| Decisions copy | `app/api/v1/decisions.py` |
| Ограничения | `docs/ASSESSMENT_TRUST_AUDIT.md`, `docs/ASSISTANT_CASE_CONTEXT.md`, prompts |

---

**Стоп этапа 5.1.** Следующий ограниченный шаг — **5.2** (observed vs assumed + severity falsy), без переписывания симулятора целиком.
