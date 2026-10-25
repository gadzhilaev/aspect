# Мониторинг качества контента, персонализации и AI (K12)

Дата: 2026-10-25  
Назначение: процесс регулярной проверки для прототипа Aspect / конкурсного стенда.
Это **операционный** процесс команды, не отдельный продуктовый дашборд.

## Метрики (минимум)

| ID | Метрика | Как считать | Цель / тревога |
|----|---------|-------------|----------------|
| M1 | Coverage персонализации | Доля карточек ленты с `inclusion_bases` ∈ {case_profile, industry_profile, company_calculated} среди показанных за период | Тревога: &lt; 40% при заполненном профиле |
| M2 | Bank-cited answers | Доля ответов ассистента с citation `label=bank_material` (или fragment id) среди ответов по событиям с доступным corpus | Тревога: 0% на Policy Rate демо-событии |
| M3 | Tool-ledger completeness | Доля agent-loop turns с ≥1 tool run и сохранённым ledger (tools/sources) | Тревога: loop ON, но ledger пуст |
| M4 | Empty-feed rate | Доля компаний с профилем, у которых лента пуста при наличии events в корпусе | Тревога: рост после ingest |
| M5 | Feedback | Число пометок «полезно / неверно / галлюцинация» от пользователя или эксперта (ручной лог) | Еженедельный разбор |

Снимок БД без LLM:  
`python backend/scripts/quality_metrics_snapshot.py --db path/to/stand.db`

## Периодичность

| Когда | Что |
|-------|-----|
| После каждого bootstrap / крупного ingest | M1, M4 snapshot |
| Перед демо жюри | M2 на Policy Rate; M3 при `ASSISTANT_AGENT_LOOP=true` |
| Еженедельно (команда) | Разбор M5 + 3 случайных hold-out новости (см. `tests/test_holdout_personalization.py`) |

## Обратная связь

1. Пользователь в чате / разборе отмечает ошибку факта или нерелевантность (пока — запись в issue / correspondence вне Git).
2. Эксперт сверяет citation с PDF (страница / fragment).
3. Регрессии фиксируются тестом или чеклистом в `docs/JURY_MOBILE_SCENARIO.md`.

## Границы

- Метрики не заменяют live-оценку жюри.
- Snapshot скрипт не вызывает LLM и не пишет в БД.
- При выключенном competition mode OpenAI/GigaChat возможны в разработке — на сдаче только hackathon.
