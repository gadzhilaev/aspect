# Agent loop — live E2E (Этап 4.6)

Дата: 2026-10-22  
Статус: **один** сквозной live-прогон на изолированном стенде (TestClient).  
Root `.env` / рабочая БД `kontur.db` / backend `:8003` **не** менялись. Флаг loop в root `.env` не включался.

Скрипт: `scripts/run_assistant_agent_live_e2e_46.py`  
Машиночитаемый отчёт: `data/bank_materials/verification/e2e46/e2e46_report.json`

**Один успешный прогон не доказывает стабильность и не заявляет полное соответствие конкурсному ТЗ.**

---

## Стенд

| | |
|--|--|
| Тестовая БД | `data/bank_materials/verification/e2e46/assistant_agent_live_e2e.db` (SQLite `backup()` от QA copy) |
| Источник QA | `data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db` |
| Storage | `data/bank_materials/verification/e2e46/storage` (копия PDF Policy Rate, SHA совпал) |
| Провайдер | `hackathon` / `deepseek/deepseek-v4.1-flash` |
| Режим | `ASSISTANT_AGENT_LOOP=true` только в процессе раннера |

Синтетика (без импорта всего CSV):

- user / company / membership;
- case snapshot + catalog `U_460`, product marks `LOA=true`, `DEP=false`;
- событие `[СИНТЕТИЧЕСКИЙ ТЕСТ 4.6]…`, `occurred_at=2026-09-20` (после публикации Policy Rate 2026-09-11);
- **нет** `EventImpact` для пары company/event;
- банковские QA-фрагменты Policy Rate **без** изменения оригинальных дат/текстов.

---

## Лимиты (фактические Settings)

| Параметр | Значение |
|----------|----------|
| max model HTTP | 4 |
| max tool calls | 3 |
| max repairs | 1 |
| timeout_s | 90 |

Факт прогона: **3** model HTTP записаны транспортом; в `loop_trace` — `model_http_used=4`, `tool_calls_used=3`, `repairs_used=0`.  
Остановка: `budget_exhausted` / detail **`transcript size budget exceeded`** (не timeout модели).

Лимиты **не** повышались. Второй live turn **не** запускался.

---

## Preflight (без LLM) — PASS

- Подключение к e2e46 DB подтверждено; login 200; membership через create conversation 200.
- Wrappers: event `ok`; case/bank `truncated` (лимит символов preflight), assessment `unavailable` (ожидаемо без impact).
- Collector: `available`, 3 evidence; есть **fact** и **forecast**.
- Fragment HTTP 200; PDF `content_href` 200, без Bearer → 401; SHA PDF совпал.
- Offline ScriptedLoopProvider: первый payload с пустым `observations`, без preload bank/case тел.
- Открытие обсуждения: **0** model HTTP.

---

## Последовательность model HTTP (live)

Доказательство обратной связи — рост `observations` в **следующем** запросе (не только список tool runs).

| HTTP # | Observations в запросе | tools_in_observations | source_refs | Ответ (транспорт) |
|--------|------------------------|-----------------------|-------------|-------------------|
| 1 | 0 | [] | 0 | 200 (тело action в summarizer не разобрано) |
| 2 | 1 | `get_event_context` | 1 | 200 |
| 3 | 2 | `get_event_context`, `get_bank_evidence` | 4 | 200 |

Из `loop_trace` (сервер):

1. `get_event_context` → ok  
2. `get_bank_evidence` → truncated  
3. `get_company_case_context` → truncated  

Затем stop: transcript budget exceeded (до успешного `final`).

`usage` / `finish_reason` в transport summarizer для этого прогона не извлечены (`parse: non_json` на чтении body в recorder — пробел диагностики recorder’а; HTTP при этом 200 и runner отработал tools). Ключи / Authorization / reasoning / полный prompt **не** сохранялись.

---

## Оценки A–E (раздельно)

| | Результат | Комментарий |
|--|-----------|-------------|
| **A. Механика цикла** | **PASS** | Модель запросила инструменты; результат event (и затем bank) виден в следующем model HTTP (`observation_count` вырос; имена tools в DATA). |
| **B. Полнота задачи** | **PARTIAL** | Запрошены event + bank + case. Assessment **не** запрошен. Финала нет — early-stop по transcript budget; ранний общий final без tools **не** было. |
| **C. Источники** | **N/A_STOP** | Citations не сформированы (нет final). |
| **D. Содержание** | **N/A_STOP** | Нет финального AI-текста; сохранено системное уведомление о незавершённом разборе. |
| **E. История / идемпотентность** | **PASS** | Stop сохранён как incomplete. Повтор того же `client_message_id` + того же текста → снова `ASSISTANT_LOOP_BUDGET_EXHAUSTED` с `reused`, **0** доп. model HTTP. Новых EventImpact / Scenario / Decision нет. |

---

## Выдержка / причина остановки

Пользовательский текст остановки:

> Не удалось завершить разбор: исчерпан лимит шагов. Можно отправить вопрос ещё раз.

Технически: `LoopStopReason.budget_exhausted`, detail `transcript size budget exceeded` после трёх tool observations (усечённые bank/case раздувают transcript).

**Не** исправлялось вручную. **Не** переключалось на legacy. **Не** делалось дополнительных live-попыток в этапе 4.6.

---

## Ограничения проверки

- Один live turn на одной модели/ключе; не выборка и не регрессия.
- Recorder не извлёк usage/action_kind из части ответов — механика восстановлена из `loop_trace` + роста observations в следующих request bodies.
- Truncated tool results + общий transcript cap помешали финалу в пределах 4 HTTP.
- Конкурсное ТЗ по agent loop в репозитории не сформулировано отдельно; соответствие ему **не** заявляется.

---

## Уточнение критериев (после 4.6.1, факты прогона не меняются)

Итог прогона 4.6 остаётся **stopped** (не PASS). Оценки A–E выше сохранены как есть.

Уточнение классификации (разбор offline в этапе 4.6.1, см. `docs/ASSISTANT_AGENT_CONTEXT_FIX.md`):

- Detail `transcript size budget exceeded` относился к **накопительному** учёту размеров payload и проверке размера после резерва HTTP-слота, а не к исчерпанию «лимита шагов» в пользовательском смысле.
- Расхождение transport **3** HTTP vs `model_http_used=4` — следствие резерва слота до size-check.
- После 4.6.1 аналогичная остановка должна идти как `context_limit`; UX больше не смешивает её с «просто отправьте тот же вопрос ещё раз» как гарантией.

Эти уточнения **не** переписывают таблицу A–E и **не** отменяют зафиксированные факты `e2e46_report.json`.
