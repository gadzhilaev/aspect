# Фикс: ручной профиль в agent loop и корректность ответа

Дата: 2026-10-24  
Стенд: `:5180` → `:8020` → `real_news_613` (профиль/история пользователя не менялись).

---

## 1. Диагностика сохранённого turn

| | |
|--|--|
| Компания | `упк` (`b76ead25-eaf9-4eea-89f0-70b7bbb0acb0`), twin `ready` |
| Событие | `evt_live_57984a7413fbe2ec94f22f10` — «История и искусство: в ФТС России открылись тематические экспозиции» |
| Conversation | `9e520cbf-62a5-4338-bad2-9cac2a4ae960` |
| User message | `a90e303c-b12b-46d4-ab2d-32df37c055c4` |
| Assistant message | `544733de-af77-476f-9556-5738415e66f9` |

### Доказано (из БД)

- В twin есть цепочка: **Поставщик (Китай) → Телефон** (+ площадка Махачкала, рынок Россия и т.д.).
- `case_org_company_links` для компании пуст; `EventImpact` по этой паре отсутствует.
- Ответ модели прямо ссылается на `get_event_context` и утверждает, что из компании известны только название и UUID.
- В `assistant_tool_runs` записей **нет** (loop tools туда не пишутся).
- `loop_trace` в публичных blocks **нет** (trace кладётся только в diagnostics bank-блока при citations; у turn citations не было).
- Сохранённый `content` ответа **не переписывался**.

### Граница недоказанного

- Точный runtime provider / число HTTP transport attempts / полный payload к модели **не восстановлены** из БД (нет сохранённого trace для этого final).
- По самоописанию ответа модель видела event+sources+company id/name; вызов `get_company_case_context` либо не дал профиля, либо не использовался для вывода.

### Классификация причин

| Гипотеза | Вердикт |
|----------|---------|
| Данных нет | **Нет** — twin в БД полный |
| Отфильтрованы как unknown | **Нет** — узлы `active` с именами |
| Инструмент не вызван / недоступен | **Да** — в allow-list loop **не было** инструмента ручного twin; `get_event_context` отдаёт только `company.{id,name}`; `get_company_case_context` — только case (без link → пусто) |
| Проекция потеряла поля | **Частично** — даже полный `build_conversation_context` помечал `source: manual_twin`, но **не загружал** nodes/edges |
| Модель проигнорировала переданные данные | **Не подтверждено** — скорее данные twin **не передавались** |

Дополнительно (ответ): `calculation_unavailable` ошибочно назван «уже введёнными ограничениями»; в текст ушли UUID, имена tools, `source_quality`.

---

## 2. Исправления

1. **`get_company_manual_context`** (read-only loop tool) на базе `build_company_context` + nodes/edges:
   - доступен **без** case-link и **без** EventImpact;
   - known nodes/edges по именам (без UUID в model projection);
   - unknown/incomplete рёбра **не** выдаются за подтверждённую цепочку;
   - demo-профиль не подставляется.
2. **Server seed** observation перед первым model HTTP (не тратит `max_tool_calls`).
3. Правила в system prompt / task.constraints: разделение фактов / данных компании / вывода; `calculation_unavailable` = состояние приложения, не мера регулятора; запрет tech-полей в `final.content`.
4. Из event-проекции убран `source_quality` (внутренний score).
5. UI: безопасный Markdown (`SafeMarkdown` + `safeMarkdownLogic`) — абзацы, списки, bold/italic, только http(s)/relative ссылки; без исполнения HTML.

Файлы (основные):  
`manual_company_context.py`, `loop_tools.py`, `loop_projections.py`, `protocol.py`, `runner.py`, `hackathon_loop.py`, `context_builder.py`, `web/src/lib/safeMarkdown*.tsx|ts`, `AssistantChat.tsx`.

---

## 3. Отдельный дефект: macro / risk / 60 для выставки

**Не чинился в этом этапе** (ingestion не переделывался).

| | |
|--|--|
| Симптом | Событие-выставка ФТС размечено `category=macro`, `event_type=risk`, `severity=60` |
| Место | `app/services/ingestion/enrich.py` → `heuristic_enrich` (и запись в Event через `publish.py`) |
| Замечание | Ветки macro/60 завязаны на ключевые слова («ставк», «цб», «курс», …); выставка могла попасть через live/иную ветку или эвристику — нужна отдельная проверка enrichment path для этого raw |

---

## 4. Проверки без live LLM

- `tests/test_assistant_manual_context_fix.py` — twin без case/impact; partial unknown; seed; calc wording; ACL; budget.
- `tests/test_assistant_agent_runtime.py` — обновлены ожидания seed observation.
- `web` → `npm run test:assistant-markdown`.

Scripted-тесты **не** доказывают качество реальной модели.

---

## 5. Ручная проверка (один вопрос)

На http://127.0.0.1:5180 открыть новость  
`/news/evt_live_57984a7413fbe2ec94f22f10`  
под компанией **упк**, в обсуждении отправить:

> Касается ли эта новость моей компании? Используй известные данные профиля (в том числе цепочку поставок). Если прямой связи с выставкой нет — скажи об этом. Отдельно отличи отсутствие расчёта влияния в приложении от любых ограничений регулятора. Источники укажи без технических полей.

Ожидание (качественно): модель опирается на Китай→телефон и пр.; не утверждает «известны только название/ID»; не называет `calculation_unavailable` ограничениями регулятора; без UUID/tool names в тексте.
