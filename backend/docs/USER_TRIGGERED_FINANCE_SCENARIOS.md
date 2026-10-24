# Пользовательский запуск финансовых сценариев (этап 6.6)

Дата: 2026-10-23  
Статус: явный UI/API путь при **включённом** read-only agent loop.  
Модель **не** вызывается для расчёта; write-tools **не** добавляются в allowlist loop.

Связанные: `FINANCE_RATE_FX_E2E.md`, `FINANCE_SETUP_RATE_FX.md`,
`FINANCE_SCENARIO_PRESENTATION.md`, `ASSISTANT_AGENT_API_INTEGRATION.md`.

---

## 1. Путь пользователя

1. Открыть обсуждение события (conversation) для своей компании.  
2. При `finance_ready` / `finance_data_required` — CTA **«Рассчитать финансовые сценарии»**  
   (не chip «через модель»). Опционально what-if: ставка в **п.п.**, курс в **%**.  
3. Сервер считает и сохраняет `Scenario` пакетно; в ленту пишется **system**-блок  
   «Расчёт по вашему запросу» (не AI-сообщение).  
4. Пользователь выбирает сценарий → **Черновик решения** → **Подтвердить**  
   (существующие ACL `draft-decision`).  
5. Без usable impact обсуждение остаётся доступным; расчёт блокируется с причиной.

Supply-chain: отдельная CTA **«Сравнить сценарии»** на том же endpoint  
(при `supply_chain_ready`). Нет отдельного «только supply» write-path сверх этого.

---

## 2. Endpoint

```
POST /api/v1/assistant/conversations/{conversation_id}/compare-scenarios
```

Тело (`UserCompareScenariosIn`):

| Поле | Назначение |
|------|------------|
| `client_request_id` | обязателен; идемпотентность / анти-даблклик |
| `assumed_rate_change_pp` | optional what-if, **процентные пункты** |
| `assumed_fx_change_percent` | optional what-if, **проценты** |
| `inventory_days` / `delay_days` | supply defaults (как у legacy tool) |

Ответ (`UserCompareScenariosOut`): `status`, `reused`, `result`, `message` (system),  
`scenario_ids`, `decision_created=false`, `next_step`, `disclaimer`.

Реализация: `app/services/user_triggered_scenarios.py` → прямой вызов  
`compare_scenarios` (тот же сервис, что и legacy tool).  
**Не** вызывается provider / `generate` / agent-loop tools.

Код конфликта параметров: HTTP **409** `USER_COMPARE_REQUEST_CONFLICT`.

---

## 3. Предусловия и доступ

| Проверка | Поведение |
|----------|-----------|
| Membership + владелец conversation | через `get_conversation_for_user` |
| Usable `EventImpact` | иначе `missing_data` / unavailable (без фиктивного impact / hidden recompute) |
| Track readiness | `finance_ready` → rate/FX simulator; иначе supply или missing |
| Основание события или явный what-if | без них — `missing_data`, пустые `scenarios` |
| FX без курса / валюты | деньги FX не считаются; RUB не подставляется |

Модель **не** выбирает права и область доступа.

Что **нельзя** передать как доверенное: observed status, готовый результат, чужой Scenario,  
подтверждение источника, итоговую сумму.

Формулы 5.2 / 5.4 **не** менялись. Параметры и `model_version` фиксируются в Scenario  
при создании (последующие правки профиля старые результаты не пересчитывают).

---

## 4. Идемпотентность

Ключ: `(conversation_id, tool=user_compare_scenarios, client_request_id)`.

| Повтор | Результат |
|--------|-----------|
| тот же id + те же параметры | `reused=true`, те же `scenario_ids` |
| тот же id + другие параметры | 409 `USER_COMPARE_REQUEST_CONFLICT` |

Пакет сценариев сохраняется атомарно внутри `compare_scenarios`.  
**Decision не создаётся** этим endpoint.

---

## 5. Связь с decision flow

1. `POST …/compare-scenarios` → `Scenario` + system message.  
2. Выбор `scenario_id` в UI.  
3. `POST …/draft-decision` (`confirm=false`) — черновик.  
4. `POST …/draft-decision` (`confirm=true`) — Decision.  
5. `GET /decisions/{id}` — `DecisionDetail` с presentation.

ACL выбора/подтверждения — существующие.

---

## 6. UI

- Финансовый CTA вызывает API; старый chip «расчёт через read-only loop» убран  
  из `SUGGESTION_CHIPS_FINANCE_READY`.  
- Loading + lock против повторного клика.  
- Unavailable / missing_data с текстом причины; ссылка на `/company/setup?step=finance`.  
- Результаты через существующий `presentFinanceScenario` / presentation.  
- Не обещается «всегда три сценария».  
- Смена `companyId`/`eventId` очищает сообщения и what-if.

Код: `web/src/lib/userTriggeredFinance.ts`, `AssistantChat.tsx`, `assistantApi.compareScenarios`.

---

## 7. Тесты

| Слой | Где |
|------|-----|
| TestClient, competition + agent loop ON, 0 model HTTP | `tests/test_user_triggered_finance_scenarios.py` |
| ACL, no impact, no basis, assumed≠observed, idempotency, conflict, decision after confirm | то же |
| Frontend helpers / CTA wiring | `web/scripts/user-triggered-finance.test.mjs` |

Связанные регрессии: finance e2e / assistant smoke по необходимости.  
Браузер / live LLM / CDP **не** заявлялись.

---

## 8. Ограничения

- Agent loop остаётся read-only: расчёт — отдельный пользовательский POST.  
- Supply-chain путь есть (та же CTA/API), но без отдельного финансового what-if UI.  
- Без usable impact расчёт недоступен; чат обсуждения — да.  
- Не создаёт Decision автоматически.  
- Не меняет root `.env`, рабочую БД `:8003`, формулы 5.2/5.4.
