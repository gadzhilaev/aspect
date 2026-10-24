# Assistant without EventImpact (Этап 3.2)

Дата: 2026-10-21  
Обсуждение доступного события участником компании **без** обязательного `EventImpact`.  
Без live LLM, UI-редизайна, новых формул, импорта и скрытого пересчёта влияния.

Рабочая БД, `.env`, запущенные сервисы **не** менялись. Commit/push не делались.  
Миграция схемы conversation **не** потребовалась (`impact_id` в модели не было).

## Найденные зависимости от impact

| Место | Было | После 3.2 |
|-------|------|-----------|
| `context_builder._require_impact` | 404 без impact / `not_relevant` | `lookup_usable_impact` → optional |
| `get_or_create_conversation` | вызывал builder → падал без impact; state=`monitoring_only` | builder с `user`; state=`calculation_unavailable` |
| `_assessment_for_conversation` | `None` → `monitoring_only` | `None`/`not_relevant` → `calculation_unavailable` |
| `post_message` / slim | предполагал словарь impact | `impact: null`, `impact_results: null` |
| Mock provider | `impact_score or 0` | ранняя ветка без фиктивных нулей |
| Tools: impact/paths/solutions/simulate/compare/decision | падение или слабый missing_data | `tool_unavailable` + `unavailable_reason=calculation_unavailable` |
| `draft_decision` API | мог идти к сценарию | 409 `CALCULATION_UNAVAILABLE` без usable impact |
| Список обсуждений | `impact_score=None` уже был | + `has_impact_calculation`; `not_relevant` → null scores |

## Изменения

| Файл | Назначение |
|------|------------|
| `app/services/impact.py` | `AssessmentState` += `calculation_unavailable` |
| `app/services/assessment_explain.py` | score_kind → `unavailable` для нового состояния |
| `app/services/assistant/context_builder.py` | optional impact; tools_available; slim без нулей |
| `app/services/assistant/tools.py` | серверный gate расчётных tools |
| `app/services/assistant/orchestrator.py` | open/list/draft без фиктивного impact |
| `app/services/assistant/prompts.py` | opening/chips + правило в system prompt |
| `app/services/assistant/provider.py` | mock: ветка calculation_unavailable |
| `app/schemas/assistant.py` | аддитивные поля conversation / list |
| `contracts/openapi.json` | регенерация |
| `docs/MOBILE_API.md` | контракт |
| `tests/test_assistant_without_impact.py` | TestClient + ScriptedPayloadProvider |
| `docs/ASSISTANT_WITHOUT_IMPACT.md` | этот отчёт |

## Состояния контекста

### С usable EventImpact (как раньше)

- `has_impact_calculation: true`
- `impact: {…}` с числами (включая **известный** `0`)
- `assessment_state` ∈ supply_chain_ready / finance_* / monitoring_only
- paths / solutions / расчётные tools доступны по прежним предусловиям

### Без usable impact (`None` или `status=not_relevant`)

- `has_impact_calculation: false`
- `impact: null` (не `{}`, не нули)
- `assessment_state: calculation_unavailable` — **отдельно** от `monitoring_only`
- `paths: []`, `solutions: []` — без выдуманных цепочек
- доступны: event, sources, manual `company`, `case_company_context`, `bank_evidence`
- `calculation.available: false` + explanation

Ассистент может объяснять событие, признаки компании, пробелы данных и что проверить.  
Не утверждает доказанное персональное влияние. Отсутствие расчёта ≠ «безопасно».

## Ограничения инструментов

| Tool | Без impact |
|------|------------|
| `get_event_context` | OK |
| `get_company_impact` / `get_impact_paths` / `list_solution_candidates` | `tool_unavailable` |
| `simulate_scenario` / `compare_scenarios` | `tool_unavailable`; Scenario rows **не** создаются |
| `create_decision_draft` | `tool_unavailable` |
| `POST …/draft-decision` | HTTP 409 `CALCULATION_UNAVAILABLE` |

Структурированный ответ:

```json
{
  "available": false,
  "unavailable_reason": "calculation_unavailable",
  "assessment_state": "calculation_unavailable",
  "type": "tool_unavailable",
  "message": "…"
}
```

С существующим impact сценарный/decision flow не ослаблялся.

## Совместимость API

- Аддитивные поля: `assessment_state`, `has_impact_calculation` на conversation out и list item.
- `impact_score` / `confidence` в списке уже были nullable; семантика уточнена: без расчёта → `null`, не `0`.
- Старые клиенты могут игнорировать новые поля.
- История, `bank_evidence_list`, pinned revisions, `case_context_ref` — без смены семантики; старые сообщения не переписываются.
- Схема БД conversation без миграции.

## Тесты (без платного LLM)

`tests/test_assistant_without_impact.py`:

- открытие / повтор / история без impact;
- case_company_context + bank_evidence в контексте;
- нет новых строк EventImpact;
- нет фиктивных чисел в slim payload;
- список: с impact (в т.ч. known zero) и без;
- чужая company / conversation → 403;
- compare_scenarios → unavailable, Scenario не создаётся; draft-decision → 409;
- known `0` score/exposure сохраняются и отличаются от `null`.

## Ограничения этапа

- Нет UI-редизайна, новых формул, смены профиля через чат, импорта.
- Нет live LLM / браузера / CDP / OCR / скриншотов.
- Impact / relevance / confidence формулы не менялись.
- Зависимость **расчётных** сценариев от impact сохранена намеренно.
