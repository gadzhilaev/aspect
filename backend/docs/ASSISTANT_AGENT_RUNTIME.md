# Внутренний read-only agent loop (Этап 4.3)

Дата: 2026-10-22  
Статус: **внутренний runner + scripted provider + 4 read-only tools** (этап 4.3).  
С этапа 4.5: `AGENT_LOOP_RUNTIME_INTEGRATED = True`; публичный wiring — `docs/ASSISTANT_AGENT_API_INTEGRATION.md`.

Спека протокола: `docs/ASSISTANT_AGENT_PROTOCOL.md`  
План: `docs/ASSISTANT_AGENT_LOOP_PLAN.md`

Код: `app/services/assistant/agent_loop/`  
Тесты: `tests/test_assistant_agent_runtime.py`

---

## 1. Зависимости runner

`AgentLoopRunner(db, scope, provider, budget?, ledger?, clock?)`

| Зависимость | Роль |
|-------------|------|
| `LoopActionProvider` / `ScriptedLoopProvider` | следующий `ActionEnvelope`; записывает фактически полученный payload |
| `ServerScope` → `resolve_server_scope` | `user_id` / `company_id` / `event_id` + membership + event exists |
| `Session` | чтение через wrappers |
| `TurnBudget` (4.2) | единый HTTP/tool/repair/timeout — **второй счётчик не создаётся** |
| `SourceLedger` | obtained → prepared → dispatched |
| `clock` | monotonic, подмена в тестах |

Legacy `run_tool` / write tools **не** вызываются. Allow-list только MVP имён в `loop_tools.py`.

---

## 2. Минимальный начальный контекст

В первый payload провайдера:

- `user_question`;
- `task.constraints` (read-only, data≠instructions, cite only dispatched, no impact zeros);
- `task.available_tools` (4 инструмента с кратким описанием);
- пустой `observations`;
- `budget` (remaining timeout, `final_only`, attempt index).

**Не** предзагружаются полные case / bank / assessment тела — иначе тест не доказывает, что ответ пришёл из tool result.

---

## 3. Наблюдения между шагами

После `tool_request`:

1. Проверка действия и бюджета (`final_only`, tool slots, deadline).
2. Исполнение read-only wrapper.
3. `ToolResultEnvelope` → observation (`role=tool_result_data`) в следующем payload.
4. Результаты — **DATA**, не system-инструкции. CoT не запрашивается и не хранится.

`ScriptedLoopProvider` видит полный payload и может выбирать следующий шаг от observation (доказано тестом).

---

## 4. Scope и snapshot

- Scope только серверный; `arguments` инструментов пустые (валидатор 4.2).
- Membership через `require_company_member`; чужая компания → stopped `acl:FORBIDDEN` без вызова провайдера.
- Case: один `pinned_case_snapshot_id` на turn; смена активного snapshot mid-turn → `error` / `snapshot_changed_mid_turn`.
- Кеш turn: повтор того же tool name без новых данных не переисполняется.

**Политика дубликатов**

1. Первый повтор → `ToolResultEnvelope(status=denied, reason_code=duplicate_tool_call)` (расходует tool slot).
2. Второй повтор того же tool → `LoopStopReason.no_progress`.

---

## 5. Бюджет

Подключён `TurnBudget` из 4.2.

- `final_only` фиксируется в `ModelAttemptLease` **до** расходования последнего model slot.
- При 4 HTTP-слотах и 3 tool-слотах: три `tool_request` + один `final` — допустимо (тест).
- `tool_request` на последнем model slot → stopped `invalid_action` (`tool_request_on_last_model_slot`).
- Format repair и citation repair делят `max_repairs=1`; repair расходует основной HTTP-бюджет.
- Citation repair видит `observations` и `citation_passed_index_keys`.
- При неуспехе — `LoopStoppedOutcome`, не фиктивный final; `partial_content` не публикуется как завершённый ответ.

### Timeout (ограничение)

Синхронный tool **нельзя** прервать по mid-flight timeout.  
Проверка deadline: **до** и **после** шага. Если срок уже истёк — следующий шаг не запускается. Документировано явно; прерывание внутри SQL/сервиса не реализовано.

---

## 6. Источники и упаковка

Стадии: `tool_result_obtained` → `prepared_for_context` → `sent_to_model` (в 4.3 = **dispatched to provider**).

- `mark_dispatched` = включено в payload scripted/test provider, **не** доказанная отправка HTTP.
- Точка будущего ACK: `SourceLedger.confirm_transport_sent` (после успешного wire send).
- Citation index = только dispatched bank fragments с точными revision/текстами.
- Конфликт revision одного id: первая dispatched версия сохраняется; новая не подменяет молча (`revision_conflicts`).
- Exact quote: целиком или exclude вместе с правом цитировать. `status=truncated` сам по себе не даёт права на исключённый текст.
- Сериализация: `pack_object_to_budget` — drop keys / целых list items, **без** строкового среза JSON.

Отсутствующий impact → `unavailable` + `calculation_unavailable`, без нулей.  
Ошибка чтения → `status=error`, не маскируется под «нет данных».

---

## 7. Результаты тестов (без сети)

`tests/test_assistant_agent_runtime.py` + прежние protocol-тесты:

| Сценарий | Ожидание |
|----------|----------|
| tool → observation → final | final; observation DATA; без preload case/bank/impact |
| два инструмента → final | оба observation в payload |
| следующий шаг от observation | scripted callback видит unavailable |
| bank → valid citation | FinalOutcome с citation |
| excluded / ghost fragment cite | stopped, не final |
| unavailable assessment | модель видит unavailable и продолжает |
| write/unknown tool + scope args | stopped invalid_action |
| ACL чужой компании | stopped; provider не вызван |
| повторный tool | denied, затем no_progress |
| deadline FakeClock | timeout без sleep |
| бюджет 4: 3 tool + final | success; last lease final_only |
| tool_request на последнем слоте | invalid_action |
| общий repair | format repair → final; repairs_used=1 |
| revision conflict | kept first revision |
| нет новых Impact/Scenario/Decision/Company | counts unchanged |
| legacy untouched + flag NOT_READY | `AgentLoopRunner` нет в `post_message` |

Реальный HTTP-транспорт и live LLM **не** проверялись.

---

## 8. Что подключено позже / вне 4.3

- Wiring `post_message` + HTTP outcomes — этап **4.5** (`ASSISTANT_AGENT_API_INTEGRATION.md`).
- `HackathonLoopProvider` + mocked HTTP — этап **4.4**.
- Dedupe через `AssistantToolRun` (в runner — in-memory turn cache).
- Write tools в цикле — вне v1.
- Live LLM — не выполнялся.
