# Manual profile → «Для вас» (компания «упк»)

Дата: 2026-10-24. Стенд: `http://127.0.0.1:5180` → API `127.0.0.1:8020` →  
`data/competition_stand/real_news_613/stand.db`. Пользовательские строки в этой БД **не изменялись**.

## 1. Фактический профиль «упк»

| Поле | Значение |
|------|----------|
| id | `b76ead25-eaf9-4eea-89f0-70b7bbb0acb0` |
| name | `упк` |
| owner | `forplayson@gmail.com` |
| profile_status | `ready` |
| digital_twin_status | `ready` |
| digital_twin_coverage | `100%` |
| nodes / edges | 6 / 6 |
| case_org_company_links | **нет** (`case_context` → not_linked / без profile_available) |
| optional_finance | `{}` |
| purchase_currencies | `[]` |
| event_impacts | **0** |

Узлы: поставщик Китай, компонент/продукт «Телефон», линия «Большая» (24%), площадка Махачкала, рынок Россия.

Вторая запись `УПК` (`bbee9840-…`) — draft / twin not_built; к проверке «Для вас» не относится.

## 2. Путь: onboarding → лента

1. Мастер сохраняет узлы/рёбра (`saveChain` / `finishSetup`).
2. `POST …/profile/complete` → `profile_status=ready`.
3. `POST …/digital-twin/build` → coverage + **`recompute_events_for_company`** (явный пересчёт).
4. `GET …/dashboard` — **read-only**: только уже посчитанные Impact + case-profile matches; lazy recompute **нет**.

Для «упк» шаги 1–3 уже выполнены (twin ready). Пустая лента **не** из‑за «расчёт не запускался» и **не** из‑за ошибки API/UI.

## 3. Точная причина пустой выдачи

**Нет подходящих опубликованных новостей** для ручного twin при пустом финансовом профиле.

Ветки:

| Основание ленты | Участвует ли «упк»? | Результат |
|-----------------|---------------------|-----------|
| Impact / twin (`recompute_events_for_company`) | Да, ручной профиль | 0 релевантных событий → 0 Impact |
| `case_profile_match` (LOA/DEP из кейса) | Нет case-link | `usable=false`, совпадений нет |
| Demo-компания / SYNTHETIC_U | Не подставлялась | — |

Это допустимый empty state, не баг заполнения экрана.

## 4. Диагностика 14 active-событий vs «упк»

Правило: валютный своп / MIACR / RUONIA **не** считаются решением по ключевой ставке (исправлено в `event_suggests_rate_track`).

| Событие | Почему не в «Для вас» |
|---------|------------------------|
| Большинство `market` ЦБ без `match_countries` / материалов | Нет пересечения со страной рынка/поставщика (Китай/Россия в нужной роли) |
| Вестник с `ЕС` | Рынок компании — Россия, не ЕС |
| Macro: своп юань, MIACR, RUONIA (+ RUB) | Macro-ветка; нет finance и нет purchase currencies; своп ≠ key rate |
| `[ДЕМО] ключевая ставка` (+ rates, RUB, Россия) | Нужен кредитный finance **или** валюта закупок — у «упк» пусто |
| Цепочные export/China в корпусе live | **Отсутствуют** — нечему матчить поставщика «Китай» / «Телефон» |

Что *могло бы* попасть при тех же узлах без выдуманных карточек:

- новость с страной поставок **Китай** (export/geopolitics) и/или материалом «телефон»;
- решение по **ключевой ставке** — только после заполнения финансового профиля или валют закупок;
- case-profile по LOA/DEP — только после реального case-link (не делается автоматически).

## 5. Воспроизведение на временной БД + фиксы

Тесты: `tests/test_manual_profile_feed.py` (pytest temp `kontur_test.db`).

| Проверка | Результат |
|----------|-----------|
| Новый user + ручной twin без case-link + CBR-like corpus | dashboard empty, `feed_empty.reason=no_matching_published_news`, без «конкурсн» |
| Тот же путь + China export event | карточка в priority_events после `digital-twin/build` |
| Своп / MIACR ≠ rate track; key rate = true | PASS |
| GET не поднимает `not_relevant` в priority | PASS |
| Related feed/personalization suite | 37 passed |
| `web` `npm run build` | PASS |

Код:

- `event_suggests_rate_track` — без ложного key-rate для свопа/денежного рынка.
- `DashboardOut.feed_empty` + `describe_personal_feed_empty` — честный empty по причине.
- `ForYouPage` — текст без «конкурсный профиль»; CTA из `feed_empty`.
- Setup done — не обещает, что лента обязательно заполнится; показывает `impacts_computed`.

## 6. Empty state (после фикса)

Для «упк» API отдаёт:

- `reason`: `no_matching_published_news`
- primary: «Все новости» → `/news`
- secondary: «Финансовый профиль» → `/company/setup?step=finance`  
  (подсказка про макро/ставку; **не** обещание, что вход в аккаунт добавит Impact)

Другие reason: `profile_incomplete`, `twin_not_built`.

## 7. Стенд для проверки

| | |
|--|--|
| URL | http://127.0.0.1:5180 |
| API | http://127.0.0.1:8020 (restart PID **18656**, тот же `real_news_613`) |
| Provider | hackathon + agent-loop |
| Telegram-стенд 5187/8027 | не трогали |

Обновить страницу «Для вас» после HMR/перезагрузки FE.

## Простыми словами

Открывайте **http://127.0.0.1:5180**. У «упк» модель компании уже собрана, но **текущие новости ЦБ почти не пересекаются** с цепочкой «Китай → телефон», а финансовый профиль пуст — поэтому «Для вас» честно пустое. Это не сломанный расчёт и не подмена demo-компанией. Общая лента с реальными новостями на месте; персональные карточки появятся только при реальном совпадении (или после осознанного заполнения финансов для макро по ключевой ставке).
