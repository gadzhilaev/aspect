# Расширение реальных источников для ручной персонализации

Дата: 2026-10-24

Цель: проверить персонализацию компании «упк» на корпусе шире ЦБ.  
Исходный `real_news_613` **не изменялся**; перенос новых публикаций на основной стенд **не делался**.  
Live LLM не вызывался. Telegram-уведомления не запускались (`TELEGRAM_BOT_TOKEN` очищен).

Связанные: `REAL_NEWS_INGESTION_VERIFICATION.md`, `MANUAL_PROFILE_FEED_VERIFICATION.md`.  
Скрипт: `scripts/verify_business_news_coverage.py`.  
Машинный отчёт: `data/competition_stand/business_news_coverage/coverage_report.json`.

---

## 1. Копия стенда

| | |
|--|--|
| Источник | `data/competition_stand/real_news_613/stand.db` |
| Копия | `data/competition_stand/business_news_coverage/stand.db` |
| SHA256 копии | `465cca822d1d396f…` |
| ASSISTANT_PROVIDER | mock (heuristic enrich only) |
| COMPETITION_MODE | false на копии (чтобы не требовать hackathon LLM) |
| OFFICIAL/trusted в коде | **не расширялся** |

Профиль «упк» на копии: те же 6 узлов (Китай → телефон → линия 24% → рынок Россия), finance пустой, case-link нет. Данные профиля **не менялись**.

---

## 2. Источники: URL, доступность, доверие

Предпочтение: существующие коннекторы `RssProvider` (whitelist) и `GdeltProvider`.  
CBR / `CbrProvider` в этот прогон **не** включались — корпус уже ЦБ-тяжёлый.

### Проверенные и выбранные

| Источник | URL | HTTP | Тема | Основание доверия / статус в Kontur |
|----------|-----|------|------|-------------------------------------|
| Interfax RSS | `https://www.interfax.ru/rss.asp` | 200 | business / general | Уже в whitelist. Коммерческий агрегатор. **Не** official → Event только при ≥2 издателях в кластере |
| Vedomosti RSS | `https://www.vedomosti.ru/rss/news` | 200 | business | Уже в whitelist. Деловая пресса. Не official |
| WTO latest news | `https://www.wto.org/library/rss/latest_news_e.xml` | 200 | trade | Первичная лента ВТО. В `OFFICIAL_PROVIDERS` **не** добавлялась — gate не обходили |
| EC press (trade) | `https://ec.europa.eu/commission/presscorner/api/rss?dossier=trade&language=en` | 200 | trade / export policy | Официальные press releases Еврокомиссии. Не помечена official в Kontur |
| ФТС России | `https://customs.gov.ru/press/federal/rss` | 200 | customs / logistics | Первичная гос. пресс-лента. Не добавлена в trusted ради публикации |
| GDELT DOC API | существующий `GdeltProvider` (3 query: export+electronics, logistics+China, trade+China) | 200 / 429 | electronics, logistics, trade | Метаданные DOC 2.1, не полный текст, `is_official=False` |

### Не использованы (не обходили HTML/антибот)

| URL | Причина |
|-----|---------|
| BIS newsroom `?format=feed&type=rss` | HTTP 200, но `text/html` — не RSS |
| Минпромторг `…/news/rss/` | HTML, не RSS |
| Federal Register «RSS» search | HTML, не лента |

Paywall не обходился; в trusted ничего не добавлялось только чтобы «протолкнуть» записи.

---

## 3. Ограниченный импорт (≤50, без LLM)

Конфиг на копии: 5 RSS × `max_per_feed=5` + 3 GDELT × `max_per_query=8` (потолок 49).  
Фактически:

| Метрика | Pass 1 |
|---------|--------|
| fetched | **25** (только RSS; GDELT вернул 0 статей — частично 429 на probe) |
| inserted | **25** |
| duplicates | 0 |
| clusters | 25 |
| published Events | **0** |
| rejected clusters | 25 |
| errors | [] |

Лимит ≤50: **PASS**.

Все 25 новых raw → `unverified_single_source`.  
Сырьё сохранено с provenance: `provider`, `publisher`, `canonical_url`, `published_at`, `fetched_at`, `payload_json.feed_url` / GDELT query.

### Примеры сохранённых записей (не Event)

**ФТС (5):**

- «ФТС России продолжит укреплять свое лидерство…» — 2026-10-23 13:45 — rejected  
- «В ФТС России состоялась встреча…» — 2026-10-23 12:05 — rejected  
- «История и искусство: в ФТС России открылись тематические экспозиции» — rejected  

Темы в основном институциональные/PR, не экспортные ограничения по электронике.

**WTO (5):**

- «The Philippines launches safeguard investigation on pork» — 2026-10-21 — rejected  
- «Trade Facilitation Committee advances TFA review…» — rejected  
- «WTO and multilateral partners review progress on supply chain finance initiative» — rejected  

Есть trade/supply-chain finance, но **не** вступившие экспортные меры по китайской электронике. Планы/расследования не трактовались как действующие ограничения.

**EC trade dossier (5):** press remarks / heritage / assemblies — мало пересечения с цепочкой «телефон/Китай».

**Vedomosti / Interfax (по 5 новых):** общая лента (в т.ч. не business-electronics); без второго независимого издателя в кластере не публиковались.

**Гипотезы → меры:** не превращались. Публикация Event не выполнялась без verification gate.

Ожидаемое поведение gate (из `publish.can_publish`): official (сейчас по сути CBR) **или** ≥2 независимых publisher.  
Без расширения trusted бизнес-ленты остаются в raw — это **не** дефект персонализации «упк».

---

## 4. Темы, страны, роли (фактически)

На копии по-прежнему **13 active live Event** (прежний CBR-корпус) + 0 новых.

Роли gate (`country_roles_for_event`):

| Тип события | Роль страны для матча | Для «упк» |
|-------------|----------------------|-----------|
| geopolitics / export_control | **supplier** | нужен поставщик в стране события |
| market | **market** | нужен рынок сбыта в стране события |
| macro / FX | страны не открывают gate | нужны finance или purchase currencies |

**Важно:** одного слова «Китай»/China в заголовке или heuristic `match_countries` **недостаточно**, чтобы подтвердить влияние на цепочку с китайским поставщиком. Нужна содержательная мера (экспорт/поставки/материал), а не упоминание страны. В этом прогоне слабых «только токен страны» active Impact не появилось — потому что **новых Event не было**, а старый CBR-корпус с «упк» не пересекается.

Различие:

- **страна события** (где мера) ≠  
- **рынок сбыта** компании (у «упк» — Россия) ≠  
- **страна поставщика** (у «упк» — Китай).

---

## 5. Явный пересчёт «упк» на копии

Вызов: `recompute_events_for_company` (тот же путь, что `POST …/digital-twin/build`).  
Профиль, доли, новости **не** подгонялись под PASS.

| | |
|--|--|
| Impact до | 0 |
| Impact после | 0 |
| returned active impacts | 0 |

### В персональной ленте

**Пусто.** Карточек нет.

### Исключены (14 active Event, в т.ч. demo rate)

| Группа | Почему |
|--------|--------|
| ~10 market/CBR без страны / без нужной роли | нет пересечения со страной поставщика/рынка |
| ~4 macro (своп, MIACR, RUONIA, demo key rate) | нет finance и purchase currencies; своп ≠ key-rate track |

### Нельзя подтвердить из данных

- Сырьё ФТС/WTO/EC/GDELT **не стало Event** → нельзя считать их основаниями персональной ленты.  
- Нет опубликованной меры «экспортный контроль Китая / электроника», которая матчила бы supplier-роль.  
- Case-profile (LOA/DEP) недоступен (`not_linked`) — не подставлялся.

Честный итог: **подходящей опубликованной публикации для «упк» в этом расширенном прогоне нет.**

---

## 6. Повторная обработка (идемпотентность)

| | Pass 2 |
|--|--------|
| fetched | 25 |
| inserted | 0 |
| duplicates | 25 |
| Δ raw | 0 |
| Δ live events | 0 |
| Δ scenarios | 0 |
| Δ decisions | 0 |
| Δ notification_outbox | 0 |

**PASS:** без дублей raw/Event, без Scenario/Decision, outbox не рос. Telegram не слали.

---

## 7. Выводы

1. Доступны для дальнейшего покрытия: Interfax, Vedomosti, WTO, EC trade, ФТС RSS; GDELT — с учётом rate-limit; BIS/Минпромторг «RSS» — не ленты.  
2. Без расширения `OFFICIAL`/`trusted` одиночные бизнес-источники остаются `unverified_single_source` — gate работает как задумано.  
3. Персонализация «упк» на копии после явного пересчёта **по-прежнему пустая** — это допустимый результат при текущем опубликованном корпусе.  
4. Исходный стенд `:5180`/`:8020` и БД `real_news_613` не переключались на эту копию.

### Простыми словами

Мы скачали реальные пресс-ленты ФТС, ВТО, Еврокомиссии и деловую прессу на **отдельную копию** базы. По правилам доверия Kontur они пока лежат как сырьё и **не попали в общую ленту новостей** (нужен официальный маркер вроде ЦБ или два независимых издания об одном событии). Поэтому у «упк» в «Для вас» по-прежнему пусто — не потому что пересчёт сломан, а потому что **опубликованных** новостей про экспорт/электронику под китайского поставщика всё ещё нет. Основной сайт не трогали.
