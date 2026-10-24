# Assistant without impact — UI path (Этап 3.4)

Дата: 2026-10-21  
Пользовательский путь: новость → обсуждение без `EventImpact`.  
Без браузера / CDP / OCR / скриншотов / live LLM / commit/push.  
Рабочая БД, `.env`, backend `:8003`, формулы — **не** менялись.

## Найденные разрывы (до правок)

| Место | Проблема |
|-------|----------|
| `NewsDetailPage` | Без impact CTA «Обсудить…» не было: только relevance/setup или пусто |
| `AssistantPage` | Обязательный `eventsApi.impact` → 404 ломал весь экран; назад вел на `/impact` |
| `AssistantAnalysisAside` | Требовал `Impact`; без расчёта нечего показать |
| `AssistantChat` | Кнопка «Сравнить сценарии» всегда; `impact_score ?? 0` подставлял ноль |
| `missing_data` / draft | `tool_unavailable` / 409 не отделялись от «мало данных» |
| `ScenariosPage` | `impact_score >= 70` → «Нужны действия»; `decision_saved` без `decision_id` мог выглядеть как решение |
| Guest CTA | Login/register без `state.from` к новости |
| Типы | Нет `assessment_state` / `has_impact_calculation` на conversation list |

Что уже работало и **не** переписывалось целиком: `BankEvidenceBlock`, open conversation API, серверные chips/`calculation_unavailable`, ImpactPage chat при наличии impact.

## Изменения пользовательского пути

### Вход

- Авторизован + компания + **нет** impact → aside «Расчётная оценка пока недоступна» + **«Обсудить с Аспектом»** → `/events/:id/assistant`.
- С impact → «Обсудить с Аспектом» (+ разобрать / сценарии) из `ImpactPanel`.
- Гость → `/login` / `/register` с `state.from=/news/:id` (возврат через существующий `postLoginPath`).
- User без компании → `/company/setup` с `from`.
- Impact с фронта **не** создаётся; recompute **не** вызывается.

### Чат (`AssistantPage` + `AssistantChat`)

- Открытие **без** обязательного impact; назад → новость.
- Aside без impact: пояснение «пока недоступна», не monitoring_only, не «безопасно».
- Контракт: `assessment_state` + `has_impact_calculation` с open conversation (отдельных capability-полей нет — задокументировано).
- Без расчёта: нет шкал 0%, нет активных «Сравнить сценарии» / черновик / подтвердить.
- Chips с сервера (обновлены тексты для `calculation_unavailable`).
- `impact_summary`: известный **0** остаётся 0; null/unavailable → текст, не кольцо с нулём.
- `tool_unavailable` / 409 `CALCULATION_UNAVAILABLE` → понятное сообщение, чат не падает.
- Банковские блоки и обычные сообщения не скрываются.
- Историческое сохранённое решение (`decision_id`) по-прежнему открывается; это не создание нового расчётного плана.
- Смена `companyId`/`eventId`: очистка сообщений до нового open.

### История (`ScenariosPage`)

- Обсуждения без impact в списке; название/дата как раньше.
- Нет фиктивных score/confidence без расчёта («Без расчётной оценки»).
- «Решение принято» только при `decision_saved` **и** `decision_id`.
- Высокий score сам по себе не даёт статус «Нужны действия».

## Состояния и действия

| Состояние | UI |
|-----------|-----|
| `calculation_unavailable` | Обсуждение ок; без метрик/сценариев; aside + chips про смысл/данные/проверки |
| `monitoring_only` | Как раньше (есть impact row); + CTA обсудить |
| Известный score=0 | Показ **0**, не «недоступно» |
| `tool_unavailable` / 409 | Сообщение в чате / ошибка draft без краша |
| loading / 401 / 403 / 404 | StateBlock / сообщения; retry где уместно |

Скрытие кнопок **не** заменяет серверные проверки tools/draft.

## Backend (минимально)

| Файл | Зачем |
|------|--------|
| `app/services/assistant/prompts.py` | Chips `calculation_unavailable` ближе к продуктовым формулировкам |

Контракты/формулы/open conversation без impact — без изменений семантики 3.2.

## Проверки

```bash
cd web && npm run test:assistant-without-impact && npm run build
pytest tests/test_assistant_without_impact.py -q
```

- 12 node-тестов на `assistantWithoutImpact.ts` (поведение хелперов/фикстур состояний, не grep JSX).
- `npm run build` — PASS.
- Backend without-impact — 6 passed.

**React-рендер / браузер не проверялись** — явно: нет RTL/CDP; UI-контракт закреплён хелперами + сборкой TypeScript.

## Ограничения

- Нет редизайна сайта; токены/тема/safe-area сохранены.
- Register после verify по-прежнему ведёт в ленту/setup (не отдельный deep-link на новость после регистрации).
- Стабильность модели / live LLM вне этапа.
- Capability API не добавлялся: UI опирается на `assessment_state` / `has_impact_calculation`.

**Стоп этапа 3.4.**
