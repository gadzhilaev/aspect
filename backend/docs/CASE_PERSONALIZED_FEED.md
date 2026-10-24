# Персональная лента по конкурсному профилю (этап 6.9)

Дата: 2026-10-23  

Устраняет разрыв этапа 6.8: `case_context` был доступен ассистенту, но новости без
`EventImpact` не попадали в «Для вас».

Рабочая БД, root `.env`, `:8003`, исходный конкурсный стенд — **не** менялись.  
Live LLM / браузер / CDP / скриншоты / commit/push — нет.  
Retrieval банковских материалов в этом этапе **не** менялся.

Связанные: `EVENT_DISCOVERABILITY.md`, `CASE_CONTEXT_API.md`, `UNSEEN_EVENTS_VERIFICATION.md`,
`PERSONALIZATION_PROOF.md`, `ASSISTANT_WITHOUT_IMPACT_UI.md`, `MOBILE_API.md`.

---

## 1. Правила (v1)

Источник профиля: **один** вызов `build_case_context_block` на запрос ленты  
(активный snapshot серверного `CASE_CONTEXT_SLOT_KEY`, существующий ACL membership).

### Тема события

| Тема | Как определяется |
|------|------------------|
| `policy_rate` | Структурированно: `match_categories_json` содержит фразу из набора («ключевая ставка», «дкп», …) **или** составной сигнал «ставк»+политический маркер в categories. Текстовый fallback: пара «ключев»+«ставк» в title/summary **или** «ставк»+ЦБ/Банк России + глагол решения. |

Одного общего токена («ставка», «спрос») **недостаточно**.

### Продуктовые правила

| rule_id | Тема | Продукт | Объяснение |
|---------|------|---------|------------|
| `policy_rate_loan_mark` | policy_rate | LOA=`true` | «В данных компании указан кредитный продукт» |
| `policy_rate_deposit_mark` | policy_rate | DEP=`true` | «В данных компании указан депозитный продукт» |

Статусы отметок:

- `true` — может дать положительное основание;
- `false` — нет основания (это отсутствие отметки **в данном источнике**, не «нет продукта во всех банках»);
- `unknown` / `conflict` — **не** дают положительного основания.

### Ограничения интерпретации (зафиксированы в выдаче)

- Кредит ≠ известный долг / плавающая ставка.
- Депозит ≠ известный остаток.
- Связь с профилем ≠ расчёт влияния / денежный эффект.
- Нет совпадения с правилами ≠ «новость не влияет».
- Платежи / ФТС / OKVED в v1 **не** используются как основания ленты.
- Нет hardcode по U_ID, имени компании или ID события.

---

## 2. API и контракт

Файлы:

| Файл | Роль |
|------|------|
| `app/services/case_profile_relevance.py` | темы + правила |
| `app/services/case_profile_feed.py` | merge ленты, карточки, cursor |
| `app/api/v1/events.py` | dashboard / `GET .../events` |
| `app/schemas/event.py` | `ProfileRelevanceOut`, additive поля `EventCardOut` |
| `contracts/openapi.json` | обновлён |
| `docs/MOBILE_API.md` | контракт для клиентов |

### Аддитивные поля карточки

- `inclusion_bases`: `calculated_impact` | `event_severity_signal` | `case_profile`
- `profile_relevance`: summary, matches[], limitations, provenance (snapshot / source_file / uid)
- `score_kind=case_profile_match` + label «По профилю компании»

Для profile-only (этап **6.9.1**):

- `impact_score=null`, `impact_score_available=false` — оценки нет (не «ноль влияния»);
- известный ноль Impact остаётся `impact_score=0.0` / `available=true`;
- `assessment_state=calculation_unavailable`;
- `status=profile_match`;
- фиктивный `impact_id` **не** создаётся.

Счётчик dashboard: `profile_match` (только profile-only карточки).  
`total` / `action_required` / … — по-прежнему по Impact.

GET dashboard / events **не** создаёт Impact / Scenario / Decision  
(в т.ч. нет lazy twin-recompute; явный пересчёт — `POST .../digital-twin/build` /
`POST .../recompute-impact`). Подробности: `CASE_PERSONALIZED_FEED_CONTRACT_FIX.md`.

---

## 3. Порядок групп и пагинация

1. `company_calculated` — внутри `impact_score DESC`, tie-break `event_id ASC`
2. `event_severity_signal` — внутри `impact_score DESC`, tie-break `event_id ASC`
3. `case_profile_match` — внутри `occurred_at DESC`, tie-break `event_id ASC`

Cursor: `{group}:{sort_key}:{event_id}`.  
Legacy `{group}:{sort_key}` — конец bucket’а sort_key (равные без id могут быть пропущены).  
Некорректный cursor → 422.

Одна новость — **один** раз: при Impact + профиле карточка остаётся impact-kind,
`profile_relevance` и `case_profile` в `inclusion_bases` добавляются.

Фильтр `?status=` на `GET .../events` — только Impact (без инъекции профиля).

---

## 4. UI

`ForYouNewsCard` / `ForYouPage`:

- chip «По профилю компании» + текст объяснения;
- без фиктивных % / денежных эффектов на profile-only;
- CTA «Обсудить с Аспектом» → `/events/:id/assistant` (без обязательного Impact);
- карточки с расчётом влияния без изменений по смыслу («Разобрать влияние»).

---

## 5. Примеры A / B

Одна новость о ключевой ставке (`match_categories`: ключевая ставка + ДКП):

| Компания | Отметки | Лента |
|----------|---------|--------|
| A | LOA=`true`, DEP=`false` | Карточка с основанием кредита |
| B | LOA=`false`, DEP=`true` | Карточка с основанием депозита |

Одинаковое событие **может** быть релевантно обеим — списки не обязаны различаться
«ради демо». Переименование компании результат **не** меняет.  
Нерелевантная тема (сталь) **не** добавляется для заполнения ленты.

---

## 6. Проверки

```powershell
pytest tests/test_case_personalized_feed.py tests/test_personalization_proof.py `
  tests/test_event_discoverability.py tests/test_case_context_api.py -q
cd web; npm run build
```

| Проверка | Результат |
|----------|-----------|
| Loan vs deposit основания на одной новости | PASS |
| Rename компании | PASS |
| false/unknown/conflict не подтверждают | PASS (unit) |
| Сталь не в ленте | PASS |
| Impact + профиль без дубля | PASS |
| ACL 403 | PASS |
| Пагинация без пересечений | PASS |
| GET без новых Impact/Scenario/Decision | PASS |
| Open assistant без Impact | PASS |
| Регрессии personalization / discoverability / case_context | PASS |

---

## 7. Ограничения

- Узкий набор правил (ставка × LOA/DEP); расширение — отдельный этап.
- Лексическая/структурная тема ≠ полная семантика новости.
- Клиенты должны читать `impact_score_available` / null `impact_score`; не подставлять 0.
- Совместимость Flutter с nullable `impact_score` **не** доказана в этом репозитории (клиента нет).
- Legacy cursor без `event_id` может пропускать элементы с тем же sort_key.
- Без Impact и без профильного совпадения лента по-прежнему пуста; twin сам по себе GET не заполняет.
