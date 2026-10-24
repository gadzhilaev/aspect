# Исправление контракта персональной ленты (этап 6.9.1)

Дата: 2026-10-23  

Правила релевантности (LOA/DEP × `policy_rate`) **не** расширялись.  
Исправлены три риска контракта из `CASE_PERSONALIZED_FEED.md`.

Рабочая БД, root `.env`, `:8003`, исходный конкурсный стенд — не трогались.  
Live LLM / браузер / CDP / скриншоты / commit/push — нет.

---

## 1. Отсутствующая оценка

### Проблема

У profile-only карточек `impact_score=0` мог читаться как **известный ноль** влияния.

### Решение

| Поле | Поведение |
|------|-----------|
| `impact_score` | `float \| null` — известная оценка (включая **0.0**) или `null`, если оценки нет |
| `impact_score_available` | `true` при известной оценке; `false` для `case_profile_match` (тогда `impact_score` = `null`) |

- Реальные нули Impact **не** менялись (`impact_score=0.0`, `available=true`).
- Web `ForYouNewsCard` не рисует число, если `available===false` / profile-only / `impact_score==null`.
- Flutter-клиент в репозитории **недоступен** — совместимость Flutter **не** заявляется доказанной; контракт описан в OpenAPI / `MOBILE_API.md`.

Файлы: `app/schemas/event.py`, `app/services/case_profile_feed.py`, `web/src/api/types.ts`, `web/src/components/news/ForYouNewsCard.tsx`.

---

## 2. Пагинация при равных значениях

### Проблема

Cursor `{group}:{sort_key}` при одинаковом score / `occurred_at` терял или дублировал элементы.

### Решение

- ORDER BY: `group ASC`, `sort_key DESC`, **`event_id ASC`**.
- Cursor: `{group}:{sort_key}:{event_id}`.
- Условие следующей страницы согласовано с этим порядком.
- Legacy `{group}:{sort_key}` / bare score: конец bucket’а с этим `sort_key` (равные ключи без `event_id` могут быть пропущены — задокументировано).
- Некорректный cursor → **422**.

Проверено: >page_size с одинаковым `occurred_at`; >page_size с одинаковым impact score; полная выдача без потерь/повторов; привязка к компании / ACL.

---

## 3. Скрытые записи при GET

### Проблема

`GET .../dashboard` при twin `ready|partial` и отсутствии Impact вызывал `recompute_events_for_company` (запись Impact).

### Решение

Lazy recompute **удалён** из GET dashboard / events.

Явный пересчёт (как и раньше):

- `POST /companies/{id}/digital-twin/build`
- `POST /events/{id}/recompute-impact`

Профиль-лента при twin без Impact продолжает работать (карточки `case_profile_match`).  
GET dashboard на twin+nodes+rate-событие: счётчик `EventImpact` не растёт; profile cards присутствуют.

---

## 4. Проверки

```powershell
pytest tests/test_case_personalized_feed.py `
  tests/test_personalization_proof.py tests/test_event_discoverability.py `
  tests/test_case_context_api.py tests/test_assessment_trust.py -q
cd web; npm run build; npm run test:event-discoverability
```

| Проверка | Результат |
|----------|-----------|
| Profile-only: `impact_score=null`, `available=false` | PASS |
| Known zero остаётся `0.0` / `available=true` | PASS |
| Пагинация equal occurred_at / equal score | PASS |
| Invalid cursor 422 | PASS |
| GET + twin ready без Impact → 0 новых Impact | PASS |
| Регрессии personalization / discoverability / case_context / assessment | PASS (37) |
| Frontend build + event-discoverability UI | PASS |

Обновлены: `contracts/openapi.json`, `docs/MOBILE_API.md`, `docs/CASE_PERSONALIZED_FEED.md`.
