# Исправления по ручной проверке UI (этап 6.11.1)

Дата: 2026-10-23  
Стенд ручного прогона (`ui_acceptance_611`) и сохранённое решение **не** переписывались.  
Проверка — pytest / frontend unit / `npm run build` на временных фикстурах.

Связанные: `COMPETITION_UI_ACCEPTANCE.md`, `USER_TRIGGERED_FINANCE_SCENARIOS.md`,
`FINANCE_SCENARIO_PRESENTATION.md`.

---

## 1. Несоответствие выбранного плана («Снизить валютную экспозицию»)

### Воспроизведение

RUB-кредит (`debt=100_000_000`, `floating=40%`), событие hold, без typed FX-экспозиции →
`compare-scenarios` → выбор → draft → confirm → DecisionDetail.

### Причина

**Нерелевантная альтернатива simulator**, не ошибка привязки `scenario_id`.

- `financial_simulator._simulate_rate_scenarios` всегда добавлял `reduce_fx_exposure`
  («Снизить валютную экспозицию») рядом с baseline / refinance, даже без
  `has_fx_exposure_context`.
- DecisionDetail берёт заголовок из `scenario.results_json.label` → ID совпадал с
  выбранным рядом; подпись не «ломалась» сама по себе.
- Автовыбор UI раньше мог цеплять первый ряд с `scenario_id` без предпочтения baseline.

### Исправление

- Без подтверждённой FX-экспозиции `reduce_fx_exposure` **не** создаётся как Scenario.
- В `parameters.omitted_action_hypotheses` остаётся общая гипотеза модели (не план).
- При наличии typed FX — альтернатива по-прежнему в пакете.
- UI: `pickDefaultScenarioId` предпочитает `kind=baseline`; omitted hypotheses
  показываются отдельной пометкой под списком сценариев.

Старое сохранённое решение ручного прогона не менялось.

---

## 2. Повторный what-if

### Причина

`showFinanceCalcCta` скрывал панель при `hasScenarios=true`; кнопка ещё и
блокировалась через `usedQuickActions`.

### Исправление

- `showFinanceRecalcCta` + CTA **«Рассчитать другой вариант»** в той же беседе.
- Явный новый расчёт → новый `client_request_id`.
- Повтор сетевого запроса («Повторить» после ошибки) → тот же id при тех же what-if.
- Результаты append’ятся system-блоками; hold / assumed различаются presentation
  (`basis`, badge, `data-what-if`).

---

## 3. Устаревший notice

### Причина

Opening-message с `assessment_state=calculation_unavailable` пишется в историю при
создании беседы и не переписывается после finance + recompute (правильно для
истории, плохо как «текущий» статус).

### Исправление

- История не переписывается.
- Если текущий `assessment_state` уже не `calculation_unavailable`, блок помечается
  как **«Состояние на момент открытия обсуждения»** + пояснение, что сейчас расчёт
  доступен; CTA из устаревшего notice не показываются.
- Актуальная доступность — из `conversation.assessment_state` /
  `has_impact_calculation` и панели расчёта.

---

## 4. Статус решения («Черновик плана» после confirm)

### Причина

- `create_decision_draft` копировал draft-note («Черновик плана: …») в confirmed result.
- UI fallback title был «Черновик плана»; успех UI не требовал `status=confirmed` +
  `decision_id`.

### Исправление

- Confirmed note: «Решение подтверждено. План: …»; title блока — «Решение сохранено».
- Черновик в истории остаётся черновиком; confirmed-сообщение — подтверждённым.
- UI: `setConfirmed` только при `res.status === 'confirmed' && res.decision_id`.

---

## Тесты

| Проверка | Где |
|----------|-----|
| Rate-only hold без FX-плана; с FX — есть reduce_fx | `tests/test_rate_scenario_basis.py` |
| Macro UX after finance без «валютн» в labels | `tests/test_macro_finance_ux.py` |
| Draft/confirm note + title; decision без FX | `tests/test_user_triggered_finance_scenarios.py` |
| Recalc CTA + baseline pick | `web/scripts/user-triggered-finance.test.mjs` |
| Build | `cd web; npm run build` |

Запуск:

```powershell
pytest tests/test_rate_scenario_basis.py tests/test_macro_finance_ux.py tests/test_user_triggered_finance_scenarios.py -q
cd web; npm run test:user-triggered-finance; npm run build
```

---

## Короткий маршрут повторной ручной проверки

Стенд: http://127.0.0.1:5178 (копия / чистый старт предпочтительнее; старое решение
ручного прогона можно не трогать).

1. **План без FX.** Войти → «Для вас» → новость о ставке → обсудить → финансы:
   долг `100000000` / `RUB` / доля `40` → сохранить и пересчитать → рассчитать
   **без** what-if.  
   Ожидание: есть «Без действий» и «Пересмотреть финансирование»; **нет** выбираемого
   «Снизить валютную экспозицию»; возможна пометка общей гипотезы. Выбрать baseline
   или refinance → черновик → подтвердить → DecisionDetail с тем же label, без «валютн».

2. **What-if.** В той же беседе: «Рассчитать другой вариант», what-if ставка `1.5` →
   расчёт.  
   Ожидание: оба system-блока на месте; hold и assumed разделены; новый
   `client_request_id` у второго запроса.

3. **Notice.** После шага 1 opening-notice не выглядит как текущий блокер; заголовок
   «на момент открытия»; панель расчёта доступна.

4. **Статус.** Сразу после confirm, после F5 и из «План действий»: текст/title
   подтверждённого решения, не «Черновик плана».

Без live LLM / commit / push. Root `.env` и `:8003` не трогать.
