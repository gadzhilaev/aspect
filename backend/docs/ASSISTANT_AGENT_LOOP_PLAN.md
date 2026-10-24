# План многошагового цикла ассистента (Этап 4.1 + уточнения 4.2)

Дата: 2026-10-21 (план); уточнения протокола: 2026-10-22  
Статус:

- **4.1** — анализ и проектирование (без кода).
- **4.2** — протокол / парсер / `TurnBudget` / флаг default off / unit-тесты без сети.  
  Спека: `docs/ASSISTANT_AGENT_PROTOCOL.md`.
- **4.3** — внутренний `AgentLoopRunner` + scripted provider + 4 read-only tools (SQLite, без сети).  
  Отчёт: `docs/ASSISTANT_AGENT_RUNTIME.md`.
- **4.4** — `HackathonLoopProvider` (chat.completions) + mocked HTTP; legacy `generate` не ломался.  
  Отчёт: `docs/ASSISTANT_AGENT_HACKATHON_ADAPTER.md`.
- **4.5** — wiring в `post_message` за `ASSISTANT_AGENT_LOOP`; `AGENT_LOOP_RUNTIME_INTEGRATED=True`.  
  Отчёт: `docs/ASSISTANT_AGENT_API_INTEGRATION.md`.

Live LLM / браузер / CDP / OCR / скриншоты / commit/push — не выполнялись в 4.1–4.5.

Документы-основания в репозитории:  
`docs/ASSISTANT_WITHOUT_IMPACT.md`, `ASSISTANT_CASE_CONTEXT.md`, `ASSISTANT_BANK_EVIDENCE.md`,  
`HACKATHON_PROVIDER.md`, `HACKATHON_RESPONSE_DIAGNOSTICS.md`, `MOBILE_API.md`,  
`TZ_Backend_Kontur_MVP.md`, `ASSISTANT_AGENT_PROTOCOL.md`.

### О конкурсном ТЗ

В репозитории есть `TZ_Backend_Kontur_MVP.md` (MVP Contour). Явных требований к  
«многошаговому AI-агенту с tool loop» там **нет**. Зафиксировано:

- AI может помогать формулировать краткие объяснения; факты, оценки, источники и решения —  
  структурированные и проверяемые (`TZ_Backend_Kontur_MVP.md`, финальный принцип).
- **Запрещены** AI-агенты, самостоятельно меняющие профиль, выбирающие поставщика или  
  рассылающие решения (раздел out-of-scope).

Полное соответствие «конкурсному ТЗ хакатона» по agent loop **не заявляется**: отдельного  
текста ТЗ организаторов про agent loop в репозитории нет. План ниже опирается на  
фактический код + совместимость с MVP-ограничениями TZ.

---

## 1. Фактический текущий поток

### 1.1 Последовательность (с доказательствами)

```
POST /assistant/conversations/{id}/messages
  → orch.post_message
       → build_conversation_context (+ slim_live_context для live)
       → provider.generate  [1 model HTTP; опц. +1 shared retry]
       → validate_bank_evidence_citations
       → [опц.] citation retry → generate ещё раз
       → for tool_call in result.tool_calls: run_tool → blocks
       → append bank_evidence_list / case_context_ref
       → commit AssistantMessage (user + assistant)
```

| Шаг | Функция / файл | Что делает |
|-----|----------------|------------|
| Вопрос | `app/api/v1/assistant.py` → `orchestrator.post_message` | Idempotency по `client_message_id`; flush user msg |
| Контекст | `context_builder.build_conversation_context` | event, sources, company, case, bank_evidence, impact\|null |
| Slim | `context_builder.slim_live_context` | урезанный payload для live (hackathon/openai/gigachat) |
| Model call | `HackathonProvider.generate` → `_chat_completions` | Один `POST …/chat/completions`; JSON-протокол в system prose |
| Parse | `inspect_chat_completions_body` + `parse_hackathon_assistant_payload` | text → `content` + `tool_calls` + citations |
| Tools | `orchestrator.post_message` цикл + `tools.run_tool` | **После** generate; ACL через `event_id`/`company_id` conversation |
| Ответ | `AssistantMessage` + blocks | content модели + UI-блоки из tools |
| История | `GET …/messages` | сохранённые messages; tool_runs отдельно |

Ключевые места:

- `orchestrator.post_message` (~L487–674): generate → citations → tools → commit.
- `hackathon.HackathonProvider.generate` (~L448–544): один HTTP; без native tools API.
- `tools.run_tool` (~L721+): allow-list + серверный scope conversation.

### 1.2 Ответы на контрольные вопросы

| Вопрос | Ответ с доказательством |
|--------|-------------------------|
| Кто выбирает инструмент? | **Модель** (или mock-эвристика) указывает `tool_calls` в JSON. Сервер **фильтрует** allow-list (`validate_tool_calls` / `TOOL_NAMES`) и подставляет `event_id`/`company_id` из conversation, не из аргументов модели. Mock: фиксированные if/elif в `MockAssistantProvider.generate`. |
| Получает ли модель результат tool? | **Нет.** После `run_tool` результат идёт в `blocks` сообщения (`_blocks_from_tool_result`). Повторного `generate` с tool result **нет**. |
| Может ли сделать следующий осмысленный шаг? | **Нет** в рамках одного user-turn: один (макс. два) model HTTP без feedback loop. |
| Видит ли ошибку/недоступность tool? | **Нет как следующий шаг модели.** `tool_unavailable` становится UI-блоком `missing_data` для пользователя. |
| Когда финальный ответ? | Сразу после первого успешного `generate` (+ append строк метрик при `compare_scenarios`). Content **не** переписывается по итогам tools, кроме дописывания scenario lines. |
| Что лишь отображается после генерации? | Почти всё из tools: impact cards, scenario lists, missing_data, action_plan_draft blocks. Bank/case blocks добавляет orchestrator. |
| Citation retry + budget | Общий флаг `extra_model_http_used`: ≤ **1** доп. HTTP на user message — либо retryable `PROVIDER_BAD_RESPONSE`, либо citation-fix (`orchestrator` L558–610). Budget/401 не retry. Provider без внутреннего HTTP-retry. |

### 1.3 Почему это не «многошаговый агент»

Несколько серверных `run_tool` подряд **без** возврата результата модели — это  
post-processing UI, не agent loop. Shared HTTP retry / citation fix — тоже не цикл  
«действие → наблюдение → следующее действие».

### 1.4 Подтверждённые пробелы

1. Нет обратной связи model ← tool result.
2. Нет единого бюджета на планирование + tools + final + format/citation repair сверх  
   «1 primary + 1 extra».
3. Контекст уже «залит» в system (до 12k JSON); tools часто дублируют уже известное.
4. Write-пути (`compare_scenarios` создаёт Scenario; `create_decision_draft`) могут  
   вызываться из model `tool_calls` без отдельного UI confirm в том же turn  
   (UI confirm есть для draft-decision API; model tool path — отдельный риск).
5. Native tool calling шлюза организаторов **не подтверждён**; сейчас prose JSON.
6. Трасса шагов для provenance (кроме `AssistantToolRun` idempotency) слабая:  
   в user text не попадает, но и structured «agent trace» для аудита нет.

---

## 2. Минимальный целевой цикл

### 2.1 Целевой цикл (один user message)

```
budget = shared ModelHttpBudget (см. §4)
state = { context_slim, history, tool_transcript=[], passed_sources={} }

budget = TurnBudget(...)   # единый HTTP/tool/repair/timeout (см. §4 и PROTOCOL.md)
state = { context_slim, history, tool_transcript=[], source_ledger=SourceLedger() }

while budget.can_begin_model_attempt():
  if budget.is_final_only_mode():
    # tool_request нельзя считать завершённым разбором
    …
  lease = budget.begin_model_attempt()   # слот до send; no refund
  model → ActionEnvelope   # только tool_request | final  (kind=plan запрещён)
  validate envelope (extra=forbid; no CoT; empty arguments)
  if final:
    break
  if tool_request and budget.allows_tool_request():
    call_id/step = server-assigned
    result = run_readonly_tool(...)   # scope из conversation, не из args
    append ToolResultEnvelope; ledger.record_obtained(...)
    continue
  else:
    stop invalid_action / budget_exhausted / no_progress

citations = validate against ledger.passed_index (только sent_to_model)
if citations rejected and budget.can_begin_model_attempt(as_repair=True):
  one more model HTTP (repair shares the same HTTP budget)
persist assistant message + safe stop_reason; never dump CoT/prompt/secrets
```

### 2.2 Протокол (основной вариант: chat.completions + JSON)

Native OpenAI `tools=` / function calling **не** предполагать. Как сейчас у  
`HackathonProvider`: один completion, structured JSON в тексте, строгая валидация.

**Принято в 4.2** (детали и примеры — `ASSISTANT_AGENT_PROTOCOL.md`):

- Discriminated union: `tool_request` **без** final-полей; `final` **без** `action`/`tool_calls`.
- **Нет** `kind=plan` (расходует HTTP без действия). Допустима короткая `action.goal`.
- MVP tools: пустые `arguments={}`; scope только серверный.
- Неизвестный tool → ошибка валидации, не legacy `run_tool`.
- Markdown fence допустим **только** как обёртка всего payload; prose+JSON — нет.
- `call_id` / `step` назначает сервер.
- Стадии источника: obtained → prepared → sent; citation только из sent.
- Exact quote: целиком или исключить вместе с citable basis.

**ActionEnvelope** (модель → сервер):

```json
{
  "kind": "tool_request",
  "action": {
    "name": "get_event_context",
    "goal": "кратко: зачем шаг",
    "arguments": {}
  }
}
```

или финал:

```json
{
  "kind": "final",
  "content": "текст пользователю",
  "bank_evidence_citations": [ { "fragment_id": "…", "revision": 2 } ]
}
```

**ToolResultEnvelope** (сервер → модель):

```json
{
  "kind": "tool_result",
  "call_id": "c1",
  "step": 1,
  "name": "get_event_context",
  "status": "ok" | "unavailable" | "error" | "denied" | "truncated",
  "reason_code": null,
  "data": { },
  "source_refs": [
    {
      "type": "bank_fragment",
      "id": "…",
      "revision": 2,
      "inclusion": "tool_result_obtained"
    }
  ]
}
```

Требования:

- Без chain-of-thought; `goal` ≤ короткой фразы.
- Неизвестный `kind` / `name` → `invalid_action` (format-repair ≤ 1 внутри общего HTTP-бюджета).
- `arguments` не могут переопределить `company_id` / `event_id` / OCR scope.

### 2.3 Почему без внешних агентных фреймворков

Достаточно расширить orchestrator + JSON-валидатор вокруг существующего  
`HackathonProvider._chat_completions`. LangChain/etc. не нужны для MVP цикла.

---

## 3. Первый набор инструментов (read-only)

Переиспользовать существующие сервисы; **не** произвольный SQL/HTTP/Python.

| Tool (proposal) | Источник сейчас | Scope | Запись? |
|-----------------|-----------------|-------|---------|
| `get_event_context` | `tools.get_event_context` | conversation.event_id | нет |
| `get_company_case_context` | `case_company_context` / slim | conversation.company_id + membership | нет |
| `get_bank_evidence` | `bank_evidence_context` slim passed set | event + allowed OCR runs | нет |
| `get_available_assessment` | `lookup_usable_impact` + slim impact_results | event×company; иначе `calculation_unavailable` | нет |

**Не включать в первый цикл (write / side-effect):**

- `simulate_scenario`, `compare_scenarios` (создают Scenario rows),
- `create_decision_draft`,
- изменение профиля компании,
- любые действия «отправить / выбрать поставщика».

Пользовательские операции подтверждения решения остаются через  
`POST …/draft-decision` + явный UI confirm (как сейчас).

ACL:

- `run_tool` / новые wrappers берут `event_id`, `company_id`, `user_id` **только** из  
  conversation + `require_company_member` (уже паттерн `post_message` / `get_conversation_for_user`).
- Модель не выбирает чужую компанию и не расширяет `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS`.

---

## 4. Ограничения выполнения (конкретные пределы)

Единый бюджет на **один** user message — объект `TurnBudget` (реализован в 4.2; без сети):

| Параметр | Default v1 | Примечание |
|----------|------------|------------|
| `ASSISTANT_LOOP_MAX_MODEL_HTTP` | **4** | primary + steps + final; repair тоже из этого пула |
| `ASSISTANT_LOOP_MAX_TOOL_CALLS` | **3** | только read-only allow-list |
| `ASSISTANT_LOOP_MAX_REPAIRS` | **1** | format **или** citation суммарно; не отдельный HTTP-лимит |
| `ASSISTANT_LOOP_MAX_RESULT_CHARS` | **4000** / tool | truncate + `status=truncated` (исполнение — позже) |
| `ASSISTANT_LOOP_MAX_TRANSCRIPT_CHARS` | **12000** | сумма transcript + slim context |
| `ASSISTANT_LOOP_MAX_RAW_ACTION_CHARS` | **24000** | сырой текст ответа модели до parse |
| `ASSISTANT_LOOP_TIMEOUT_S` | **90** | monotonic; lease.remaining_timeout_s → транспорт |
| Final-only | last HTTP slot | `tool_request` недопустим как завершённый разбор |
| Dedupe | `(name, args_hash)` | при интеграции (есть idempotency `AssistantToolRun`) |

Совместимость с текущим «1+1»:

- Новый бюджет **заменяет** ad-hoc `extra_model_http_used` **внутри** loop-режима.
- Пока `ASSISTANT_AGENT_LOOP=false` (default) — поведение 3.3.1 без изменений.
- Флаг `true` + hackathon (с 4.5) → loop path; иной провайдер → явная ошибка конфигурации.

Не повторять:

- `PROVIDER_BUDGET_EXCEEDED`, `PROVIDER_UNAUTHORIZED`.

Запрещено:

- fallback на другую модель / OpenAI / GigaChat / mock при live hackathon;
- оценка стоимости в рублях без тарифов.

**Остановка (внутренний результат ≠ final):**

- `LoopStopReason`: `budget_exhausted` / `timeout` / `invalid_action` / `no_progress`.
- **Не** формировать фиктивный успешный AI-ответ на этапе механики.
- HTTP/UI для незавершённого разбора — при интеграции (кандидат: честный текст + только уже ok tool blocks + citations из sent sources).

---

## 5. Источники и история

### 5.1 Что сохранять на ход

| Артефакт | Куда | Правило |
|----------|------|---------|
| case snapshot | `case_context_ref` block (как сейчас) | pinned на **новом** ответе |
| bank fragment id + revision | `bank_evidence_list.used` после validation | только validated |
| tool results shown to model | `AssistantToolRun` + optional `blocks` / internal `loop_trace_json` (не user text) | truncated copy = то, что видела модель |
| final citations | validated subset | union **passed-to-model this run**, не весь корпус |

### 5.2 Citation validation

Сегодня: `passed_fragment_index(bank_block)` из одного pre-built context  
(`orchestrator` + `bank_evidence_citations.validate_…`).

Цель: индекс = объединение:

- fragments из начального slim `bank_evidence`;
- `source_refs` из tool results, реально добавленных в transcript этого turn.

Rejected → один citation-fix **внутри** общего HTTP-бюджета (не отдельный бесконечный цикл).

### 5.3 Чего не сохранять / не показывать

- reasoning_content / CoT;
- Authorization, API keys, полный system prompt;
- сырой OCR вне passed fragments;
- техническую трассу в пользовательский `content` автоматически  
  (опциональный debug block только под флагом, вне MVP UI).

---

## 6. Совместимость

| Сохранить | Как |
|-----------|-----|
| Обсуждения без impact | Loop работает при `calculation_unavailable`; `get_available_assessment` → unavailable |
| `tool_unavailable` | ToolResultEnvelope.status=`unavailable`; UI `missing_data` как сейчас |
| Банковские цитаты / история | Те же blocks; старые messages не rewrite |
| Сценарии / решения | Вне loop v1; UI draft-decision API без изменений |
| Mock | `MockAssistantProvider` эмулирует ActionEnvelope детерминированно |
| Старые сообщения | Аддитивные поля; отсутствие `loop_trace` = pre-loop |
| API / Flutter | `PostMessageOut` shape сохранить; новые поля только additive optional |

**Менять не требуется на первом этапе реализации:**

- формулы impact/relevance/simulator;
- bank OCR import / ACL runs;
- case import pipeline;
- Flutter routes (если клиент игнорирует unknown fields);
- UI редизайн (достаточно существующих missing_data / bank blocks);
- write tools в agent loop.

---

## 7. Этапы реализации (последовательные, небольшие)

### Этап A / 4.2 — протокол + валидатор + бюджет (без полной интеграции) — **сделано**

- Pydantic ActionEnvelope / ToolResultEnvelope / SourceRef (`agent_loop/`).
- `TurnBudget` + `parse_action_envelope` + `SourceLedger` / exact-quote policy.
- Unit-тесты: `tests/test_assistant_agent_protocol.py`.
- Feature flag `ASSISTANT_AGENT_LOOP` default off; on → NOT_READY до runtime.
- Документ: `docs/ASSISTANT_AGENT_PROTOCOL.md`.
- **Критерий выполнен:** тесты без сети; `post_message` не wired.

### Этап B / 4.3 — внутренний read-only loop (scripted provider) — **сделано**

- `AgentLoopRunner` + `ScriptedLoopProvider` (не orchestrator / не live HTTP).
- 4 read-only wrappers (`loop_tools.py`); ACL; pack limits; turn dedupe → no_progress.
- Citation index = `SourceLedger` dispatched-to-provider (не весь поиск).
- **Критерий выполнен:** тесты `test_assistant_agent_runtime.py`; Scenario/Decision не создаются;
  флаг on → NOT_READY; legacy `post_message` без изменений.

### Этап C / 4.4 — HackathonLoopProvider (mocked HTTP) — **сделано**

- Отдельный адаптер `LoopActionProvider`; legacy `HackathonProvider.generate` без изменений.
- Строгий ActionEnvelope; prose ≠ final; один HTTP на attempt; HTTP source manifest + confirm.
- Format/citation repair только через runner / общий `max_repairs`.
- **Критерий выполнен:** `test_assistant_agent_hackathon_loop.py`; budget/401 без retry; ≤4 HTTP.

### Этап D — включение за флагом + совместимость UI

- Additive diagnostics; UI без обязательных новых экранов.
- Документация MOBILE_API additive fields.
- Опциональный ограниченный live smoke (отдельный этап, не 4.1).

---

## 8. Критерии приёмки и тесты без платных LLM

| Тест | Ожидание |
|------|----------|
| Парсер ActionEnvelope | ok / unknown kind / missing fields |
| Бюджет 0 remaining | безопасная остановка, не «успешный» вымысел |
| Tool deny чужой company_id в args | ignored; server scope wins |
| Dedupe identical tool | второй вызов denied/skip |
| Truncate result | status=truncated, модель видит урезанное |
| calculation_unavailable | assessment tool → unavailable; final без чисел 0% |
| Citations | только из union переданных; invented id rejected |
| Write tools absent in loop v1 | compare/create_decision не в allow-list цикла |
| Mock path | детерминированный multi-step без HTTP |
| Старое сообщение | читается; нет обязательного loop_trace |
| Feature flag off | поведение ≡ текущий post_message |

React/браузер не обязательны для приёмки цикла backend.

---

## 9. Риски и явные non-goals v1

- Не обещать native tool calling шлюза.
- Не строить автономного «агента решений» (против TZ out-of-scope).
- Не оценивать ₽ без тарифов.
- Не расширять OCR/company scope из модели.
- Не считать текущий post-hoc tool render многошаговым агентом.

---

**Стоп этапа 4.1** (план).  
**Стоп этапа 4.2** (протокол/бюджет).  
**Стоп этапа 4.3** (внутренний runner).  
**Стоп этапа 4.4** (hackathon adapter / mocked HTTP).  
**Стоп этапа 4.5** (API integration за флагом) — root `.env` / live процессы не переключать.
