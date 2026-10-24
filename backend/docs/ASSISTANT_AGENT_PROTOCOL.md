# Протокол многошагового ассистента (Этап 4.2)

Дата: 2026-10-22  
Статус: **протокол + бюджет** (4.2); **внутренний runner** (4.3); **HackathonLoopProvider + mocked HTTP** (4.4, см. `ASSISTANT_AGENT_HACKATHON_ADAPTER.md`).  
Рабочий orchestrator / публичный `post_message` **не** подключены.

Код: `app/services/assistant/agent_loop/`  
Тесты: `tests/test_assistant_agent_protocol.py`, `tests/test_assistant_agent_runtime.py`  
План: `docs/ASSISTANT_AGENT_LOOP_PLAN.md`

---

## 1. ActionEnvelope (модель → сервер)

Discriminated union по `kind`. `extra=forbid`. Старый формат `{content, tool_calls}` **без** `kind` отклоняется (`missing_kind_not_legacy`) — молча не принимается.

### 1.1 `kind=tool_request`

Один запрос инструмента. **Не** содержит финальный ответ.

```json
{
  "kind": "tool_request",
  "action": {
    "name": "get_event_context",
    "goal": "Уточнить факты события",
    "arguments": {}
  }
}
```

Запрещены ключи: `content`, `bank_evidence_citations`, `tool_calls`, `trace`, `plan` (даже с `null`).

- `goal` — опционально, ≤ 160 символов (краткая цель действия). Скрытые рассуждения / CoT не предусмотрены.
- `arguments` — только пустой объект `{}` (или отсутствие → `{}`). Любые непустые поля → ошибка валидации.
- Запрещённые ключи аргументов (явный scope smuggling):  
  `company_id`, `user_id`, `event_id`, `ocr_run_id(s)`, `storage_root`, `url`, `sql`, `query`, `path`, `http`, `headers`, `authorization`, `api_key`, `database_url`.

MVP allow-list имён:

| name | Назначение |
|------|------------|
| `get_event_context` | контекст события |
| `get_company_case_context` | case context компании |
| `get_bank_evidence` | банковские фрагменты |
| `get_available_assessment` | доступная оценка / unavailable |

Неизвестный `name` → `ActionParseError(code=unknown_tool)`, **не** запуск legacy `run_tool`.

**Нет** `kind=plan`: отдельный plan расходует model HTTP без действия. Короткая `goal` внутри `tool_request` достаточна.

### 1.2 `kind=final`

Непустой текст пользователю + структурированные citations.

```json
{
  "kind": "final",
  "content": "Краткий ответ пользователю.",
  "bank_evidence_citations": [
    { "fragment_id": "frag-1", "revision": 2, "section_hint": null, "quoted_text": null }
  ]
}
```

Запрещены ключи: `action`, `tool_calls`, `trace`, `plan`, `reasoning`, `reasoning_content`.

- `content`: strip, min_length 1, max 12000.
- `bank_evidence_citations`: ≤ 20; `fragment_id` непустой; `revision` ≥ 1 или null.

### 1.3 Конфликт final + action

Объект с `kind=final` и полем `action` → `conflicting_fields`.  
`tool_request` с `content` → `conflicting_fields`.

---

## 2. ToolResultEnvelope (сервер → модель)

Назначается **сервером** (`call_id`, `step`). Модель не управляет трассировкой.

```json
{
  "kind": "tool_result",
  "call_id": "c1",
  "name": "get_event_context",
  "status": "ok",
  "data": { "title": "…" },
  "source_refs": [
    {
      "type": "bank_fragment",
      "id": "frag-1",
      "revision": 2,
      "inclusion": "tool_result_obtained",
      "exact_quote": null,
      "exact_quote_excluded": false
    }
  ],
  "reason_code": null,
  "step": 1
}
```

| Поле | Правило |
|------|---------|
| `status` | `ok` \| `unavailable` \| `error` \| `denied` \| `truncated` |
| `data` | объект; размер ограничивается бюджетом результата (см. §4) |
| `reason_code` | безопасный код ≤ 64; без секретов / SQL / stack |
| `name` | только MVP allow-list |

Серверный scope (`event_id`, `company_id`, OCR runs) передаётся **вне** ответа модели — в runtime wrappers, не через `arguments`.

---

## 3. Парсер

`parse_action_envelope(text, max_raw_chars=…)` → `ActionEnvelope`.

Правила:

1. Один JSON-объект; лимит сырого текста (`ASSISTANT_LOOP_MAX_RAW_ACTION_CHARS`, default 24000).
2. **Допустимы** markdown fences только если весь payload — один fence:  
   `` ```json\n{…}\n``` `` или `` ```\n{…}\n``` ``.
3. **Не** вырезается JSON из окружающего prose «на удачу».
4. Частичные / множественные `` ``` `` → `ambiguous_markdown_fence`.
5. Дубликаты ключей JSON → `duplicate_json_key` (`object_pairs_hook`).
6. Несколько top-level значений / невалидный JSON → `invalid_json`.
7. Без `eval`, исполнения кода, `str(...)` произвольных объектов, без использования `reasoning_content` как ответа.
8. Неизвестный `kind` → `unknown_kind` (в т.ч. `"plan"`).

Коды ошибок:  
`empty_payload`, `payload_not_string`, `payload_too_large`, `ambiguous_markdown_fence`, `invalid_json`, `json_root_must_be_object`, `duplicate_json_key`, `missing_kind_not_legacy`, `unknown_kind`, `unknown_tool`, `scope_via_arguments`, `conflicting_fields`, `schema_validation`.

---

## 4. Единый бюджет (`TurnBudget`)

Независим от HTTP/БД. Monotonic clock (`time.monotonic`), подмена `clock=` в тестах.

Defaults:

| Параметр | Default | Settings |
|----------|---------|----------|
| max model HTTP | 4 | `ASSISTANT_LOOP_MAX_MODEL_HTTP` |
| max tool calls | 3 | `ASSISTANT_LOOP_MAX_TOOL_CALLS` |
| max repairs (format **или** citation, суммарно) | 1 | `ASSISTANT_LOOP_MAX_REPAIRS` |
| turn timeout | 90 s | `ASSISTANT_LOOP_TIMEOUT_S` |
| max result chars / tool | 4000 | `ASSISTANT_LOOP_MAX_RESULT_CHARS` |
| max transcript chars | 12000 | `ASSISTANT_LOOP_MAX_TRANSCRIPT_CHARS` |
| max raw action chars | 24000 | `ASSISTANT_LOOP_MAX_RAW_ACTION_CHARS` |

Поведение:

- `begin_model_attempt(as_repair=False)` резервирует слот **до** отправки. Слот **не** возвращается при timeout / 401 / 429 / 5xx / invalid response после send.
- Repair расходует тот же HTTP-бюджет **и** счётчик `repairs_used` (общий лимит 1).
- Исчерпание до запроса → `BudgetExhausted` **без** HTTP.
- `check_deadline()` / `remaining_timeout_s()` перед каждым действием; lease отдаёт `remaining_timeout_s` транспорту (запрос не должен штатно брать timeout больше остатка turn).
- **Final-only:** при `model_http_remaining == 1` новый `tool_request` не считается завершённым разбором (`allows_tool_request()` = false) — после tool модель уже не сможет получить результат в бюджете.
- Tool budget: `begin_tool_call()` до исполнения (механика; исполнение — следующий этап).

Внутренние остановки (`LoopStopReason`) — **не** финальный ответ:

- `budget_exhausted`
- `timeout`
- `invalid_action`
- `no_progress`

Фиктивный «успешный» AI-текст при остановке **не** формируется на этом этапе. HTTP/UI для незавершённого разбора — при интеграции.

---

## 5. Источники и размер

Различие стадий (`SourceInclusion` / `SourceLedger`):

| Стадия | Смысл |
|--------|--------|
| `tool_result_obtained` | tool вернул ref |
| `prepared_for_context` | отобран в сборщик следующего payload |
| `sent_to_model` | реально присутствовал в теле HTTP к модели |

Источник **не** становится допустимым для citation только потому, что tool его нашёл. Citable = `inclusion=sent_to_model` (и не quote-excluded bank-only).

**Exact quote:** не обрезается посередине. Либо целиком в лимит (`ExactQuotePolicy`), либо исключается (`exact_quote_excluded=true`); тогда `source_ref` нельзя оставлять как основание «прочитанное моделью» для citation index.

Полный сборщик контекста — этап 4.3+; здесь закреплены модели и ledger API.

---

## 6. Флаг

| Env | Default | Назначение |
|-----|---------|------------|
| `ASSISTANT_AGENT_LOOP` | `false` | включение цикла |

В root `.env` флаг **не** включается этим этапом (только `.env.example` с закомментированными примерами).

С этапа 4.5 `AGENT_LOOP_RUNTIME_INTEGRATED = True`:

- `ASSISTANT_AGENT_LOOP=false` → legacy `post_message`.
- `ASSISTANT_AGENT_LOOP=true` + `hackathon` → `AgentLoopRunner` (см. `ASSISTANT_AGENT_API_INTEGRATION.md`).
- Иной провайдер при флаге on → `ASSISTANT_AGENT_LOOP_UNSUPPORTED_PROVIDER` (без fallback).

---

## 7. Выполненные тесты (без сети)

Файл: `tests/test_assistant_agent_protocol.py`

- валидные `tool_request` / `final` (+ markdown fence целиком);
- prose+JSON, unknown kind/tool/fields;
- конфликт final+action / tool_request+content;
- scope через `arguments`; пустой final; плохие citations;
- размер / duplicate keys / legacy без kind;
- ровно N model attempts; failed attempt остаётся учтён;
- один shared repair; deadline с FakeClock (без sleep);
- remaining timeout для транспорта; last-call final-only; tool budget; transcript size;
- стадии источников + exact quote no mid-cut;
- default flag off; flag on → NOT_READY; invalid Settings limits;
- `post_message` не импортирует loop parse/budget (legacy untouched).

**Не** объявляются выполненными: реальный транспорт, исполнение tools, wiring orchestrator, live LLM.

---

## 8. Последующие этапы (относительно 4.2)

- Интеграция в `post_message` — **4.5** (`ASSISTANT_AGENT_API_INTEGRATION.md`).
- Runner / tools — **4.3**; hackathon adapter — **4.4**.
- Write-tools в цикле — вне v1 (см. план).
- Live LLM — не в scope этих этапов.
