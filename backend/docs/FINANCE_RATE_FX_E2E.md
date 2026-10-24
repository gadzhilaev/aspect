# Finance rate/FX E2E (этап 5.6)

Сквозная проверка серверного пути после 5.2–5.5 **без LLM и браузера**.  
Рабочая БД / `.env` / демостенд не менялись. Использована сессионная `kontur_test.db` (как в `tests/conftest.py`) и синтетические компании/события.

## Путь

```
PATCH /companies/{id}/finance
  → GET profile (новая Session / expire)
  → recompute_company_impact (штатно)
  → GET …/impact (assessment_state)
  → POST …/assistant/conversations
  → compare_scenarios (assistant tool; ASSISTANT_PROVIDER=mock)
  → GET /scenarios/{id} (+ presentation)
  → POST /decisions  или draft-decision confirm
  → GET /decisions/{id}
```

**Как создаются сценарии:** через tool `compare_scenarios` (тот же путь, что legacy assistant flow). HTTP `POST …/messages` с mock-provider проверен отдельно (`test_message_path_mock_provider_finance_ready`). Прямой вызов `simulate_financial_scenarios` использован только для точечных проверок матрицы (zero debt / presentation), и помечен ниже как function-level.

What-if (`assumed_rate_change_pp` / `assumed_fx_change_percent`) передаётся аргументами tool — mock message path их сам не задаёт.

## Матрица: входы → фактический результат

| # | Вход | Результат | Уровень |
|---|------|-----------|---------|
| R1 | Только debt+floating; hold | `observed` Δ=0; annual=0; hold_note; не «рисков нет» | API+tool |
| R2 | Observed hike 16→17 (+1 п.п.), debt 100e6 × 40% | annual=400_000; DecisionDetail presentation совпадает | API+tool+decision |
| R3 | Hold + assumed 1.5 п.п. | ok, assumed row / basis | tool |
| R4 | Профиль готов, нет Δ | unavailable / пустые scenarios | tool |
| R5 | Долг без unit | не `debt_unit_confirmed_rub`; без авто-₽ | tool+function pres |
| R6 | debt=0 vs debt cleared | 0 → annual 0; clear → rate track not ready | API+function |
| F1 | FX-only 1000 CNY payment, 12→13 | baseline 12000, scenario 13000, Δ=1000 payment_cost_increase | API+tool |
| F2 | receipt, те же числа | Δ=1000 receipt_equivalent_increase; не «прибыль» | API+tool |
| F3 | FX-профиль, нет курса/основания | без денежных scenarios | tool |
| F4 | what-if +10% при rate_from=12 | rate_to=13.2, Δ=1200 | tool |
| F5 | conflict rate_delta | unavailable | tool |
| X1 | FX-only + rate-событие | нет rate annual money | tool |
| X2 | rate-only + FX-событие | нет FX track rows | tool |
| X3 | mixed profile + оба основания | rate 400k и FX 1000 раздельно; FX money_period≠annual | tool |
| P1 | PATCH: absent keep / null clear / 0 keep | подтверждено после expire Session | API |
| P2 | Смена пары без fx_rate_from в PATCH | сервер **очищает** fx_rate_from | API+unit |
| L1 | Legacy shock_proxy_pp Scenario | GET → basis=legacy; не observed; не пересчёт после PATCH | API |
| A1 | Чужой user | 403 на scenario/finance | API |

## Найденный дефект и исправление

**Дефект:** при смене `fx_exposure_currency` / `fx_quote_currency` через API (без web-формы) старый `fx_rate_from` мог остаться и применяться к новой паре.

**Исправление (минимальное):** в `merge_optional_finance` при изменении пары, если patch не содержит явно `fx_rate_from`/`fx_rate_to`, ключи курса удаляются. Регрессия: `test_merge_clears_rate_when_pair_changes_without_explicit_rate`, `test_patch_pair_change_clears_rate_via_api`.

Дополнительно: `GET /scenarios` и DecisionDetail распознают FX-track (`fx_change_basis` / `track=fx`) для presentation.

## Ограничения пользовательского пути

- Денежные finance-сценарии создаются через assistant tool / mock message routing, не отдельным REST «create finance scenario».
- What-if %/п.п. — аргументы tool, не поля профиля и не UI setup (5.5).
- Agent loop по-прежнему read-only: финансовых write-tools не добавлялось.
- Публичные read endpoints не создают расчёты (не менялось).
- Это не визуальная/браузерная приёмка.

## Прогоны

```
pytest tests/test_finance_rate_fx_e2e.py \
       tests/test_finance_setup_rate_fx.py \
       tests/test_rate_scenario_basis.py \
       tests/test_fx_scenario_basis.py \
       tests/test_finance_scenario_presentation.py \
       tests/test_macro_finance_ux.py \
       tests/test_decisions.py
```

См. вывод прогона в сессии 5.6. Frontend не менялся в этом этапе (кроме уже существующих 5.5 артефактов) — `npm run build` не требовался для 5.6.

См. также: `FINANCE_SETUP_RATE_FX.md`, `RATE_SCENARIO_BASIS_FIX.md`, `FX_SCENARIO_BASIS_FIX.md`, `FINANCE_SCENARIO_PRESENTATION.md`.
