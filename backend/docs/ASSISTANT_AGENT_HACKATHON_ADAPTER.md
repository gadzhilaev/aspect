# HackathonLoopProvider — адаптер agent loop (Этап 4.4)

Дата: 2026-10-22  
Статус: адаптер + mocked HTTP с `AgentLoopRunner` и read-only wrappers (этап 4.4).  
С этапа 4.5 адаптер используется из `post_message` при флаге on — см. `ASSISTANT_AGENT_API_INTEGRATION.md`.

Код: `app/services/assistant/agent_loop/hackathon_loop.py`  
Тесты: `tests/test_assistant_agent_hackathon_loop.py`  
Связанные: `ASSISTANT_AGENT_PROTOCOL.md`, `ASSISTANT_AGENT_RUNTIME.md`, `HACKATHON_PROVIDER.md`

---

## 1. Адаптер

`HackathonLoopProvider` реализует `LoopActionProvider.next_action`.

Переиспользует из legacy `hackathon.py`:

- `HACKATHON_ALLOWED_MODELS` / `assert_hackathon_model`
- `FORBIDDEN_HOST_MARKERS`
- `inspect_chat_completions_body`, `extract_usage`
- `map_hackathon_http_error`

**Не** вызывает `HackathonProvider.generate` и **не** использует `parse_hackathon_assistant_payload` (prose-fallback).

Правила:

| Правило | Поведение |
|---------|-----------|
| Один `next_action` | ≤ 1 HTTP POST |
| Внутренние retry | нет (только runner + `TurnBudget`) |
| Model slot | резервирует runner **до** вызова; адаптер слот не трогает |
| Base URL | только `HACKATHON_BASE_URL` |
| Fallback | нет (ни openai / gigachat / mock) |
| Native tools / `response_format` | не отправляются |

Флаг `confirms_http_sources=True`: runner **не** делает pre-dispatch; подтверждение источников — после успешного HTTP.

---

## 2. Формат messages

```
system  — протокол ActionEnvelope (tool_request|final), allow-list tools,
          пустые arguments, запрет CoT, DATA≠instructions, FINAL_ONLY при lease
user    — BEGIN_UNTRUSTED_APPLICATION_DATA + JSON:
            user_question, conversation_history (DATA), observations,
            final_only, repair_note
          END_UNTRUSTED_APPLICATION_DATA
```

`conversation_history` — ограниченные prior turns как данные, не verified sources.

- Роли только `system` / `user` (и при необходимости будущие `assistant` шаги).  
  Внутренний `tool_result_data` **не** является chat role — это поле observation в DATA.
- Tool results и тексты фрагментов **не** поднимаются в system.
- Полный case/bank/assessment **не** предзагружается в первый запрос.
- `lease.final_only` → `FINAL_ONLY=true` в system + `final_only` в DATA; серверная проверка в runner обязательна.

---

## 3. Ответ и ошибки

1. HTTP → `inspect_chat_completions_body`
2. Строгий `parse_action_envelope` (без legacy prose-as-final)

| Ситуация | Результат |
|----------|-----------|
| Пустой / truncated (`finish_reason=length`) / refusal / error-in-200 | `PROVIDER_BAD_RESPONSE` → до 1 format repair в runner |
| Неверный JSON / неизвестный kind/tool | `ActionParseError` → format repair (общий лимит) |
| Обычный текст без ActionEnvelope | **не** final → parse/stop |
| `reasoning_content` | не используется и не сохраняется |
| Budget exceeded / 401 / rate limit | stop **без** repair |
| Timeout | `LoopStopReason.timeout` без repair |
| 5xx / сеть | stop без скрытых повторов |

Диагностики (`last_diagnostics`, `usage`) сохраняются на провайдере и при ошибке разбора.

Citation repair — только через runner; делит `max_repairs=1` с format repair.

---

## 4. Timeout и бюджет

- HTTP timeout = `min(lease.remaining_timeout_s, transport_timeout_s)`.
- Deadline: runner проверяет до `begin_model_attempt` и **после** возврата провайдера; просроченный результат не публикуется как final.
- Planning / tools / final / repair — единый `TurnBudget` (нет второго счётчика).
- Ошибка после отправки слот **не** возвращает.

---

## 5. SourceLedger и HTTP manifest

После упаковки messages адаптер строит `SentSourceItem` manifest:

- только фрагменты, у которых в теле запроса есть полный `text_plain`;
- fragment_id, revision, text_kind, текст для validation.

`confirm_transport_sent` вызывается **только** после получения HTTP-ответа (2xx body).

| Событие | Confirm? |
|---------|----------|
| Tool нашёл фрагмент | нет |
| Фрагмент в arguments адаптера, но выпал из body | нет |
| Успешный HTTP с текстом в body | да |
| Timeout / connection error | нет (доставка неизвестна) |
| Успешный HTTP | не доказывает, что модель «прочитала» источник |

Citation index для live-адаптера = `ledger.passed_index_for_citations()` после confirm.  
`ScriptedLoopProvider` остаётся отдельным режимом (dispatched = передано тестовому провайдеру).

Exact quote: целиком в body либо исключена из manifest (нет cite rights через голые `source_refs`).

---

## 6. Выполненные тесты (без сети)

`pytest tests/test_assistant_agent_hackathon_loop.py`

- tool → observation в следующем HTTP body → final  
- несколько инструментов → final  
- bank отсутствует в 1-м запросе, появляется после tool; citation по отправленному  
- ghost / неотправленный fragment нельзя цитировать  
- unavailable assessment виден в HTTP body  
- неверный JSON → один format repair  
- citation после format repair без второго repair  
- 401 / budget без повторов  
- timeout / truncated  
- final_only на 4-м слоте; ≤4 HTTP при бюджете 4  
- tool_request на last slot → stop  
- base URL / model / Bearer; нет openai/sber hosts  
- нет новых Impact/Scenario/Decision  
- legacy `HackathonProvider.generate` по-прежнему проходит  
- prose без envelope ≠ final
- (после 4.5) `AGENT_LOOP_RUNTIME_INTEGRATED=True`; API wiring — отдельный suite

Случайный выход в сеть исключён (`httpx` FakeTransport). Реальный ключ не нужен.

---

## 7. Ограничения этапа 4.4 / дальше

- На момент 4.4 runner ещё не был в `post_message` — закрыто в **4.5**.
- Root `.env` флаг не включался.
- Нет live LLM / браузера / CDP / OCR / commit/push.
