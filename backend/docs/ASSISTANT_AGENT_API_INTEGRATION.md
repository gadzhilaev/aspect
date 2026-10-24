# Agent loop — интеграция в API ассистента (Этап 4.5 / 4.5.1)

Дата: 2026-10-22  
Статус: `AgentLoopRunner` wired в `post_message` за флагом; проверки только TestClient + mocked HTTP.  
`AGENT_LOOP_RUNTIME_INTEGRATED = True`. Root `.env` **не** включает флаг.  
Уточнения истории/replay: `docs/ASSISTANT_AGENT_REPLAY_FIX.md` (этап 4.5.1).

Код: `app/services/assistant/agent_loop/api_integration.py`  
Оркестратор: ранний return в `orchestrator.post_message` при `ASSISTANT_AGENT_LOOP=true`  
Тесты: `tests/test_assistant_agent_api_integration.py`  
Связанные: `ASSISTANT_AGENT_PROTOCOL.md`, `ASSISTANT_AGENT_RUNTIME.md`, `ASSISTANT_AGENT_HACKATHON_ADAPTER.md`

---

## 1. Выбор режима

| `ASSISTANT_AGENT_LOOP` | `ASSISTANT_PROVIDER` | Поведение |
|------------------------|----------------------|-----------|
| `false` (default) | любой | **legacy** `post_message` без изменений |
| `true` | `hackathon` | `post_message_agent_loop` → `AgentLoopRunner` + `HackathonLoopProvider` |
| `true` | иное (`mock` / `openai` / `gigachat` / …) | явная ошибка `ASSISTANT_AGENT_LOOP_UNSUPPORTED_PROVIDER` (400), **без** silent legacy/mock и **без** model HTTP |

Проверки ACL (`get_conversation_for_user`) и конфигурации (`assert_loop_mode_supported`) выполняются **до** model HTTP.

Флаг в root `.env` этим этапом не включается (только код + `.env.example` при наличии).

---

## 2. Контекст и история

Loop-путь **не** вызывает legacy `build_conversation_context` так, чтобы заранее загрузить весь case/bank/assessment — иначе обходится смысл инструментов.

В payload модели:

- `user_question`;
- `conversation_history` — ограниченный список `{role, content}` как **DATA** (не инструкции);
- `task` / `observations` / budget — как в runtime;
- флаги `data_are_not_instructions`, `history_is_data_not_verified_sources`.

### Политика истории (MVP, 4.5.1)

| Правило | Значение |
|---------|----------|
| Лимит сообщений | до `MAX_HISTORY_MESSAGES = 12` **целых** сообщений (newest-first в бюджет) |
| Общий бюджет | `MAX_HISTORY_TOTAL_CHARS = 6000` суммы `content` |
| Длинное сообщение | **исключается целиком** (без строкового среза оговорок/цитат) |
| Флаги | `history_incomplete`, `history_omitted_count` в payload DATA; модель не должна выдумывать пропуск |
| Текущий вопрос | всегда в `user_question`, отдельно от history; packing не должен его терять |
| Роли | только `user` / `assistant`; notices `loop_incomplete` не попадают в history |
| Цитаты | старые ID в тексте **не** расширяют citation index |

`HackathonLoopProvider` кладёт history + флаги в user DATA; при drop ключа `conversation_history` выставляет `history_incomplete`.

---

## 3. Финальный ответ

`LoopFinalOutcome` → существующий `PostMessageOut`:

| Поле / блок | Правило |
|-------------|---------|
| `content` | текст final |
| `bank_evidence_list` | только validated `used` из текущего turn |
| `case_context_ref` | только если case snapshot реально ушёл в модель (`sent_to_model` / citable) |
| provenance | через существующие labels / diagnostics; без приписывания snapshot без tool |

После финала **не** запускается legacy `tool_calls` dispatcher — инструменты уже выполнены внутри цикла.

Read-only цикл **не** создаёт `Scenario` / `Decision` / `EventImpact`.

Пользовательский расчёт сценариев при loop ON — отдельный endpoint  
`POST …/compare-scenarios` (этап 6.6): сервер вызывает `compare_scenarios` напрямую,  
без provider и без расширения allowlist write-tools.  
См. `docs/USER_TRIGGERED_FINANCE_SCENARIOS.md`.

Pinned fragment revisions сохраняются через `SourceLedger` / citation validation как в runtime.

Внутренняя связь user→assistant: блок `missing_data` с `internal_reply_link` + `in_reply_to_message_id` (не отдаётся в публичный `_msg_out`). Нужен из‑за одинаковых `created_at` в SQLite при быстром mocked HTTP.

---

## 4. Остановки и ошибки

| Исход | HTTP | `error.code` | Сообщение пользователю |
|-------|------|--------------|------------------------|
| final | 200 | — | обычный assistant message |
| `timeout` | 504 | `ASSISTANT_LOOP_TIMEOUT` | понятный текст про истечение ожидания |
| `budget_exhausted` | 429 | `ASSISTANT_LOOP_BUDGET_EXHAUSTED` | лимит шагов |
| `no_progress` | 409 | `ASSISTANT_LOOP_NO_PROGRESS` | нет прогресса |
| `invalid_action` | 409 | `ASSISTANT_LOOP_INVALID_ACTION` | некорректный ответ модели |
| прочее incomplete | 409 | `ASSISTANT_LOOP_INCOMPLETE` | общий незавершённый разбор |
| unsupported provider | 400 | `ASSISTANT_AGENT_LOOP_UNSUPPORTED_PROVIDER` | конфигурация |
| ACL | 403/404 | как раньше | без model HTTP |
| provider crash | код AppError | + incomplete notice в БД | не success final |

Контракт: **явная ошибка** (AppError envelope) после персиста системного notice о незавершённом разборе.  
**Не** возвращается ordinary successful final с частичным текстом модели.

**Replay** того же `client_message_id` + того же нормализованного текста после terminal stop снова отдаёт тот же `ASSISTANT_LOOP_*` (с `details.reused=true`, `not_ai_final=true`), **без** нового model HTTP.  
`reused` в details **не** означает success.

Сохранённое сообщение об остановке — `missing_data` / `loop_incomplete` / `not_ai_final`, без bank citations; после reload UI не трактует его как AI-final и не запускает сценарии.

Техническая причина — в `details` / compact `loop_trace` (без traceback, полного prompt, секретов).

---

## 5. Транзакции и идемпотентность

### Схема

1. Commit **user** message (с `client_message_id`) → отпускает SQLite write-lock.  
2. Model HTTP / tools **вне** write-транзакции.  
3. Commit **assistant** (final или incomplete notice) отдельной транзакцией.

Миграция состояния выполнения **не** потребовалась: достаточно `client_message_id` + `in_reply_to_message_id` в `blocks_json`.

### `client_message_id`

Нормализация текста для сравнения: `normalize_message_text` — unify newlines + `.strip()`, **без** сжатия внутренних пробелов.

| Сценарий | Поведение |
|----------|-----------|
| Тот же ID + тот же текст после успеха | `200` `reused=true`, без HTTP |
| Тот же ID + тот же текст после stop | тот же `ASSISTANT_LOOP_*` error, `details.reused=true`, без HTTP |
| Тот же ID + **другой** текст | `ASSISTANT_MESSAGE_ID_CONFLICT` (409), без HTTP, без подмены ответа |
| Пока ответа ещё нет | `ASSISTANT_MESSAGE_IN_PROGRESS` (409) |
| IntegrityError гонки | победитель пишет reply; второй видит pair / conflict / IN_PROGRESS |

### Пределы гарантий

- At-most-once **персистенция** assistant reply на `client_message_id` в рамках этого процесса+БД.  
- **Не** exactly-once у внешнего API.  
- Падение процесса между commit user и commit assistant → **IN_PROGRESS может остаться навсегда** для этого id (нет TTL/очереди). Новая попытка — новый `client_message_id`.  
- Тест IN_PROGRESS **не** заявляет полноценную конкуренцию двух одновременных HTTP.

---

## 6. Безопасная трасса

В diagnostics / `loop_trace` (компактно):

- режим `loop`;
- итог `final` / `stopped` + `stop_reason`;
- `model_http_used`, `tool_calls_used`, `repairs_used`;
- шаги: имена tools, статусы, reason codes;
- counts citations.

**Не** сохраняются: полный prompt, API keys, `reasoning_content`, полный профиль компании.

---

## 7. UI

`web/src/lib/assistantRetry.ts` + `AssistantChat`:

- обычный send → всегда новый `client_message_id`;
- «Повторить» после **terminal** (`ASSISTANT_LOOP_*`) → **новый** id (новый цикл);
- «Повторить» после **transient** (`IN_PROGRESS` / сеть) → **тот же** id (редиливери);
- автоповтора после timeout нет;
- после loop-ошибки история перечитывается: incomplete notice не как AI-final, без bank/scenario actions.

---

## 8. Тесты (без сети)

`tests/test_assistant_agent_api_integration.py` — TestClient + настоящие wrappers + `HackathonLoopProvider` + FakeTransport:

- flag off → legacy;
- flag on → tool → observation → final;
- несколько инструментов → final с банковскими источниками;
- обсуждение без impact;
- уточняющий вопрос с историей;
- чтение старых сообщений;
- чужая компания / conversation;
- неверный источник + shared repair budget;
- timeout / budget / no_progress + **replay каждого terminal failure ≠ final**;
- повтор успеха без HTTP; **conflict** при другом тексте с тем же ID;
- дубликат без reply → `IN_PROGRESS` (не claimed as full concurrency);
- длинное сообщение с оговоркой в конце не режется; `history_incomplete`;
- internal reply-link не в публичных блоках;
- новая попытка с новым id после failure;
- unsupported provider → ошибка без HTTP.

Frontend: `web/scripts/assistant-retry.test.mjs`.  
Также protocol / runtime / hackathon adapter suites.

---

## 9. Ограничения этапа

- Live LLM / браузер / CDP / OCR / скриншоты / commit/push — не выполнялись.  
- Рабочая БД и backend `:8003` не переключались.  
- Write-tools в цикле — вне v1.  
- Native tool calling шлюза не обещается.  
- Вечный IN_PROGRESS после crash процесса — см. 4.5.1 / `ASSISTANT_AGENT_REPLAY_FIX.md`.
