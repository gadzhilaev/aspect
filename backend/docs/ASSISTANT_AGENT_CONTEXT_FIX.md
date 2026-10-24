# Agent loop — context overflow fix (Этап 4.6.1)

Дата: 2026-10-22  
Режим: **только offline** (TestClient / scripted / mocked). Live LLM, root `.env`, `:8003`, рабочая БД и лимиты **не** менялись.  
Исходный live-результат этапа 4.6 остаётся **stopped** — см. `docs/ASSISTANT_AGENT_LIVE_E2E.md` и `data/bank_materials/verification/e2e46/e2e46_report.json`. Этот документ **не** заменяет его на PASS.

Offline-измерения на копии стенда 4.6: `data/bank_materials/verification/e2e46/e2e461_offline_measure.json`.

---

## 1. Причина остановки 4.6 (по коду + измерениям)

Live 4.6 остановился с `budget_exhausted` / detail `transcript size budget exceeded` после  
`get_event_context` → `get_bank_evidence` → `get_company_case_context` (до `final`).

Две независимые ошибки учёта (не «просто слишком много данных»):

### A. Накопительный учёт transcript

`TurnBudget.record_transcript_chars` **суммировал** размеры подготовленных payload по каждой model-попытке.  
Каждый следующий шаг с растущими observations добавлял полный размер текущего payload к уже накопленному.

Offline на копии e2e46 (после компактных проекций, scripted path):

| Метрика | Значение |
|---------|----------|
| Сумма трёх observations (после проекций) | ~7779 |
| Один packed payload (question + task + 3 tools) | **8413** ≤ 12000 |
| Гипотетическая сумма размеров растущих payload за 4 попытки | **14022** > 12000 |

Именно накопительная семантика объясняет stop при ещё не исчерпанном «одном» лимите 12k на текущий запрос.

### B. Слот HTTP до проверки размера

Runner вызывал `begin_model_attempt` **до** проверки размера. При последующем fail по transcript слот уже был потрачен без транспорта.  
В отчёте 4.6: транспорт записал **3** model HTTP, а `loop_trace.model_http_used=4`.

### C. Избыточные DTO в observations

До фикса в модель уходили href/SHA, дубли exact quote в `source_refs`, длинные diagnostics.  
Три результата по 4000 символов **не** гарантируют payload ≤12000 из‑за JSON-обёртки (`user_question`, `task`, `budget`, ключи, кавычки).  
Naive `3×4000 = 12000` совпадает с лимитом «впритык» и ломается накладными расходами.

Скриптовые/mocked ответы в offline 4.6.1 **не** утверждаются как сохранённые live completions: recorder 4.6 корректно не разобрал часть тел (`parse: non_json`).

---

## 2. Компактные проекции

Модуль `app/services/assistant/agent_loop/loop_projections.py`:

| Tool | В модели | На сервере (не в каждом observation) |
|------|----------|--------------------------------------|
| event | факты, дата, краткие sources | — |
| case | признаки, products, unknown/conflict, snapshot, interpretation_limits | полные UI-блоки |
| bank | целый `text_plain` выбранных фрагментов, id/revision, date, content_type, role | href, SHA, diagnostics |

`source_refs` в observation — только `type` / `id` / `revision` (без дубля цитаты).

Проекции **не** захардкожены под Policy Rate / `U_460` / фиксированный tool order.

---

## 3. Общая упаковка контекста

`prepare_turn_payload` (`context_pack.py`) перед каждой model-попыткой:

1. Сохраняет текущий вопрос и обязательные `task.constraints`.
2. Сокращает историю **только** целыми сообщениями (oldest-first) + `history_incomplete`.
3. Исключает bank-фрагменты **целиком** (без mid-cut exact quote) + явный `context_incomplete`.
4. При необходимости опускает целые observations с флагом неполноты.
5. **Не** вырезает unknown/conflict / interpretation_limits так, чтобы оставшееся выглядело достовернее.
6. Если минимальный безопасный контекст не помещается → `LoopStopReason.context_limit` (не фиктивный `final`).

Default-лимиты **не** увеличены: `max_result_chars=4000`, `max_transcript_chars=12000`, `max_model_http=4`.  
LLM для сжатия контекста **не** используется.

Порядок в runner: **pack + size-check → begin_model_attempt → transport**.

---

## 4. Источники после упаковки

- Manifest / cite-scope строится из **окончательного** body (Hackathon: после pack в `_pack_observations_data`; scripted: из packed `observations`).
- Фрагмент, не попавший в текущий HTTP body, **не** цитируется.
- Stateless: ранее отправленный, но исключённый из текущего запроса фрагмент не считается «помнящимся» моделью (`SourceLedger.begin_request_cite_scope`).
- Pinned revisions и серверные meta (href и т.п.) сохраняются в ledger для UI; eligibility / exact-quote validation **не** ослаблены.

---

## 5. Учёт запросов и остановки

| Счётчик | Смысл |
|---------|--------|
| `model_http_used` / `reserved` | Слоты после успешной подготовки payload |
| `model_http_transport` | Фактически начатые HTTP-вызовы |
| `model_http_responses` | Полученные ответы транспорта |
| `transcript_chars` | Размер **текущего** prepared payload (не сумма) |
| `peak_payload_chars` | Пик за turn |

Проверка размера до отправки **не** считается model HTTP.  
Слот после `mark_transport_started` **не** возвращается (в т.ч. при timeout).

Пользовательские причины (`api_integration._incomplete_content`):

| Reason | Код | UX |
|--------|-----|-----|
| лимит шагов | `ASSISTANT_LOOP_BUDGET_EXHAUSTED` | можно повторить |
| контекст | `ASSISTANT_LOOP_CONTEXT_LIMIT` | **не** обещает успех при том же вопросе |
| timeout | `ASSISTANT_LOOP_TIMEOUT` | можно повторить |
| дневной бюджет провайдера | `ASSISTANT_LOOP_PROVIDER_DAILY_BUDGET` | позже |

Terminal replay incomplete по `client_message_id` по-прежнему без доп. HTTP.

---

## 6. Recorder

В `scripts/run_assistant_agent_live_e2e_46.py`:

- тело ответа буферизуется и возвращается провайдеру (stream не «съедается»);
- `merge_provider_diagnostics` предпочитает уже разобранную диагностику адаптера (`usage`, `finish_reason`, `action_kind`);
- `try_peek_action_kind` в `parse.py` — безопасный peek без секретов;
- reasoning_content / Authorization / полный prompt **не** сохраняются.

---

## 7. Регрессии (без сети)

Файл: `tests/test_assistant_agent_context_fix.py` (+ правки protocol/hackathon).

Проверено:

- event → bank → case → final помещается в прежние лимиты на данных стенда 4.6 (offline measure: packed **8413**);
- итоговый payload содержит сведения всех трёх инструментов; fact/forecast (`14`, прогноз), products, unknown сохранены;
- длинные результаты сокращаются целыми фрагментами/сообщениями;
- неделимый oversized фрагмент исключается целиком и не цитируется;
- ≤4 reserved HTTP; pack-fail до отправки → 0 transport;
- repair учитывает тот же budget/pack;
- recorder peek / adapter diagnostics;
- assessment **не** обязателен в сценарии с лимитом 3 tools (отдельные тесты на assessment остаются).

Полный набор agent-loop тестов: **95 passed** (protocol + runtime + hackathon + api_integration + context_fix).

---

## 8. Уточнение критериев оценки 4.6 (факты прогона не переписываются)

Исходный прогон 4.6:

- outcome **stopped**;
- A = PASS (механика / tool feedback);
- B = PARTIAL (нет final);
- C/D = N/A_STOP;
- E = PASS (idempotent replay incomplete).

**Уточнение (4.6.1):** остановка классифицировалась как `budget_exhausted` / «лимит шагов» в UX, но detail был `transcript size budget exceeded`. После 4.6.1 такой случай должен мапиться на `context_limit` / `ASSISTANT_LOOP_CONTEXT_LIMIT`, а «лимит шагов» — на исчерпание tool/HTTP слотов. Расхождение `model_http_used=4` vs transport `3` объясняется резервом слота до size-check (исправлено).  
Эти уточнения **не** меняют зафиксированные факты 4.6 и **не** переводят отчёт в PASS.

---

## 9. Ограничения этапа 4.6.1

- Нет повторного live LLM.
- Нет повышения default-лимитов и нет смены модели.
- Offline measure использует scripted/tool wrappers на копии БД; не заявляет сохранённые live completions.
- Стабильность на проде / конкурсе не доказана одним offline набором.
