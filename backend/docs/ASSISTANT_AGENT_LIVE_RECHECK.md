# Agent loop — live recheck (Этап 4.6.2)

Дата: 2026-10-22
**Повтор после исправления 4.6.1 прошёл.**

Один live-прогон на **новой** изолированной БД после фикса контекста (4.6.1).
Исходный этап 4.6 остаётся **stopped** (`docs/ASSISTANT_AGENT_LIVE_E2E.md`, `e2e46_report.json`).
Root `.env` / рабочая БД / backend `:8003` **не** менялись. Флаг loop в root `.env` не включался.

**Один успешный прогон не доказывает стабильность.**

## Стенд

- Тестовая БД: `data/bank_materials/verification/e2e462/assistant_agent_live_recheck.db` (новая копия; e2e46 не перезаписывалась)
- Источник QA: `data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db`
- Storage: `data/bank_materials/verification/e2e462/storage`
- Модель: `deepseek/deepseek-v4.1-flash`
- Синтетика: user/company/membership (synthetic), case snapshot + catalog U_460 + product marks LOA=true DEP=false, event labeled synthetic; occurred_at=2026-09-20; NO EventImpact, Policy Rate bank QA fragments unchanged from QA DB backup, storage layout copy of PDF under test-only root, same user question as stage 4.6
- EventImpact: отсутствует по дизайну (`no_event_impact_by_design=True`)
- Вопрос: тот же, что в 4.6 (без подстройки под модель)

## Лимиты

- model HTTP ≤ 4; tool calls ≤ 3; repairs ≤ 1; timeout_s=90
- Фактически transport HTTP: `4`; reserved=`4`; responses=`4`; tools≈3; repairs=0

## Preflight (без LLM)

- ok: `True`
- offline packed payload fits ≤12000: `True` (chars=`8587`)
- open conversation spent model HTTP: `False`

## Последовательность model HTTP

- **HTTP #1**: kind=`tool_request` tool=`get_event_context` finish=`stop` final_only=`False` prepared_data_chars=`937` obs_count=`0` obs_tools=[] source_refs=0 usage={'prompt_tokens': 720, 'completion_tokens': 173, 'total_tokens': 893}
- **HTTP #2**: kind=`tool_request` tool=`get_company_case_context` finish=`stop` final_only=`False` prepared_data_chars=`1769` obs_count=`1` obs_tools=['get_event_context'] source_refs=1 usage={'prompt_tokens': 1065, 'completion_tokens': 467, 'total_tokens': 1532}
- **HTTP #3**: kind=`tool_request` tool=`get_bank_evidence` finish=`stop` final_only=`False` prepared_data_chars=`5806` obs_count=`2` obs_tools=['get_event_context', 'get_company_case_context'] source_refs=2 usage={'prompt_tokens': 2460, 'completion_tokens': 335, 'total_tokens': 2795}
- **HTTP #4**: kind=`final` tool=`None` finish=`stop` final_only=`True` prepared_data_chars=`8756` obs_count=`3` obs_tools=['get_event_context', 'get_company_case_context', 'get_bank_evidence'] source_refs=5 usage={'prompt_tokens': 3546, 'completion_tokens': 4928, 'total_tokens': 8474}

### Обратная связь tool → следующий HTTP

- proven: `True`

## Оценки A–E

- **A механика:** PASS
- **B полнота:** PASS (missing=['assessment']; early_final=False)
- **C источники:** PASS
- **D содержание:** PASS
- **E история/идемпотентность:** PASS

## Финал / остановка

- outcome: `final` status=`200`
- error: `None`
- stop_message: `None`
- content sample: Разбор события для компании «Синтетика Агент Loop 4.6.2».  1. Что известно о событии (карточка события, не банковский источник) - Событие: «[СИНТЕТИЧЕСКИЙ ТЕСТ 4.6.2] Сохранение ключевой ставки ЦБ», категория macro, тип risk, severity 55. - В источнике: «ЦБ сохранил ключевую ставку (синтетический stub)». Источник помечен как stub, quality 0.7, то есть это тестовые/ограниченные данные, а не полноценная новость. - Персональный расчёт влияния для компании отсутствует: assessment_state = calculation…

### Примеры содержания (ручная выдержка)

- Факт банка отдельно: «ЦБ РФ принял решение оставить ставку неизменной на уровне 14,0%» + `fragment_id` / revision 2.
- Прогноз отдельно: «ожидается сохранение паузы…»; банк изменил взгляд с 13,5%.
- Компания: разбор для «Синтетика…»; блок «что стоит проверить» про кредиты/процентные расходы (металлоконструкции).
- Карточка события отделена от банковских материалов; stub-источник новости отмечен явно.
- Персональный расчёт влияния отсутствует — не трактуется как «риска нет».

## Идемпотентность

- replay: `{"replay_status": 200, "model_http_after_replay": 4, "extra_http": 0, "replay_reused": true, "ok": true}`

## Ограничения

- Один live turn; не доказательство стабильности и не полное соответствие конкурсному ТЗ.
- Ключи / Authorization / reasoning_content / полный prompt в отчёт не включались.
- Второй live turn при неудаче **не** запускался.

