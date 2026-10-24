# Event discoverability without EventImpact (Этап 4.8)

Дата: 2026-10-22

## Найденная причина

Проверены отдельно общая лента, персональная лента, клиентский поиск и список обсуждений на стенде `data/agent_demo` и в коде API.

| Поверхность | Событие без EventImpact | Причина отсутствия / присутствия |
|-------------|-------------------------|----------------------------------|
| `GET /api/v1/public/news` | **Есть** (фильтр только `status==active`) | Impact **не** требуется. На agent-demo в БД одно active-событие — оно в выдаче (rank 0). |
| `GET /public/news/{id}` | **Есть** для active | Draft/не active → 404. |
| Персональная лента (`/news/for-you` ← dashboard `priority_events`) | **Частично** | Impact **или** совпадение с конкурсным профилем (этап 6.9, `CASE_PERSONALIZED_FEED.md`). Без обоих — пусто. |
| `GET /companies/{id}/events` | **Нет** | Тоже impact-based. |
| Поиск в UI (`/news?q=…`) | Клиентский фильтр по уже загруженной public-ленте | На стенде с одним active событием поиск по «СИНТЕТИЧЕСКИЙ» находит карточку. Серверного search API нет. |
| `GET /assistant/conversations` | **Есть**, если разговор создан | Impact не нужен; `impact_score=null`, `has_impact_calculation=false`, без фиктивного «решение принято». |

**Итог:** пользователь «не видел» событие после логина, потому что post-login вёл в пустую «Для вас» (нет impact), а empty state **не** предлагал переход в общую ленту / историю. Runbook 4.7 усиливал это ручным URL с ID. Объявлять причиной «impact блокирует public feed» **нельзя** — public feed impact не требует.

## Исправления

1. **ForYouPage** empty state → «Все новости» (`/news`) + «История обсуждений» (`/scenarios`).
2. **ScenariosPage** empty state → «Все новости» + «Лента для вас» (раньше только for-you).
3. **Демостенд (только явный конфиг):**
   - Backend: `AGENT_DEMO_STAND=true` (+ опционально `AGENT_DEMO_EVENT_ID`) → `GET /api/v1/agent-demo/entry`.
   - Frontend: `VITE_AGENT_DEMO=true` → маршрут `/agent-demo`, пункт «Демостенд», post-login → `/agent-demo`.
   - Резолв события по env id или маркеру заголовка `СИНТЕТИЧЕСКИЙ ТЕСТ` / attrs — **без** hardcode ID в продуктовой ленте.
4. Prepare-стенда: пишет флаги в `stand.env` / `web.env`, на **копии** БД ставит `is_demo=1` синтетическому событию (source e2e462 не трогается).
5. Карточка новости «Обсудить с Аспектом» без impact — уже по этапу 3.4; не ломалась.

**Не делалось:** смена `occurred_at`, создание EventImpact/Scenario/Decision, hardcode synth ID в `/news`.

## Тесты

```powershell
pytest tests/test_event_discoverability.py -q
cd web; npm run test:event-discoverability; npm run build
```

Покрыто TestClient (без LLM / браузера):

- active без impact в public;
- draft не в public / 404;
- personal dashboard + company events не «становятся» общей лентой;
- история без impact с null score; GET messages не создаёт Impact/Scenario/Decision;
- `/agent-demo/entry` 404 по умолчанию; 200 при флаге с путями на существующие маршруты.

Frontend: source/wiring-тесты empty state и env-gate панели.

## Ограничения

- Персональная лента без Impact может показывать карточки «По профилю компании» (6.9); без профиля и без Impact — по-прежнему пуста.
- Панель `/agent-demo` только при `VITE_AGENT_DEMO` + `AGENT_DEMO_STAND`; обычный `:5173` / product build без флагов её не показывает.
- Исторический ответ в БД не является новой генерацией.
- Визуальная проверка UI **не** заявлялась.
