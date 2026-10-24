# Официальные первичные источники: публикация

Дата: 2026-10-24

Цель: корректная классификация первичных источников в gate `can_publish`, а не отключение проверки. Работа только на копии `business_news_coverage`. Основной стенд / root `.env` / профиль пользователя не менялись.

Связанные: `BUSINESS_NEWS_COVERAGE.md`. Код: `app/services/ingestion/official_sources.py`, `publish.py`, `reprocess.py`.

---

## 1. Аудит сохранённых WTO / ФТС / EC

На копии 15 raw с feed на `wto.org` / `customs.gov.ru` / `ec.europa.eu`. У всех проверенных записей: host статьи = host организации после redirects; feed URL принадлежит тому же сайту; организация — первоисточник **своей** пресс-страницы. HTTP 200 и строка publisher сами по себе доверия не давали (`payload.is_official` был false; gate отклонял как `unverified_single_source`).

### EC `dossier=trade`

**Фильтр не работает.** Сравнение первых заголовков RSS с `dossier=trade` и без параметра: полное совпадение (`ec_dossier_trade_effective=False`). Ленту **нельзя** называть торговой — это общая presscorner-выдача (heritage, speeches, civil protection и т.п. рядом с trade remarks).

---

## 2. Изменения политики

Добавлен allow-list первичных источников с ограничениями host/path для **статьи и feed**:

| source_id | hosts | path | основание |
|-----------|-------|------|-----------|
| `cbr` | cbr.ru | — | Банк России, первичная публикация |
| `wto` | wto.org | article `/english/news_e/…`, feed `/library/rss/` | ВТО, первичная news RSS |
| `fts_ru` | customs.gov.ru | `/press/` | ФТС, первичная пресс-лента |
| `ec_presscorner` | ec.europa.eu | `/commission/presscorner/` | Еврокомиссия presscorner; **не** «trade feed» |

Явно **не** доверяем:

- `payload.is_official` / RSS connector hint;
- совпадению publisher («Банк России», «WTO…») на чужом хосте;
- lookalike-доменам (`wto.org.evil…`);
- пометке всего `RssProvider` как official.

Gate для одиночных неподтверждённых источников сохранён (`unverified_single_source`). Публикация официального сообщения подтверждает **происхождение**, не прогноз и не ущерб компании.

---

## 3. Reprocess на копии

COMPETITION_MODE=True, ASSISTANT_PROVIDER=hackathon, prefer_live_enrich=False (heuristic; live LLM не вызывался).

Ранее rejected → `pending` без смены ID / удаления raw (`reprocess_rejected`). Dedup `store_article` публикации не блокирует.

| | |
|--|--|
| dry-run candidates | 15 |
| published (pass 1) | 15 |
| Δ live events | 15 |
| Δ scenarios | 0 |
| Δ decisions | 0 |
| Δ outbox | 0 |
| pass 2 candidates | 0 (ожидаемо 0) |

### Опубликовано (примеры)

- **ФТС России продолжит укреплять свое лидерство за счет командной работы** (`evt_live_452cf4659ffa7746823f2a92`)
  - reason=`official_source`, official=`['fts_ru']`, occurred_at=`2026-10-23T13:45:00`
  - source: Федеральная таможенная служба · https://customs.gov.ru/press/federal/document/714229 · published_at=2026-10-23T13:45:00
  - limitation: Институциональные пресс-релизы ФТС ≠ автоматически экспортное ограничение.…
- **В ФТС России состоялась встреча Валерия Пикалёва и Алексея Сазанова** (`evt_live_a38d1323296c657f5719117b`)
  - reason=`official_source`, official=`['fts_ru']`, occurred_at=`2026-10-23T12:05:00`
  - source: Федеральная таможенная служба · https://customs.gov.ru/press/federal/document/714148 · published_at=2026-10-23T12:05:00
  - limitation: Институциональные пресс-релизы ФТС ≠ автоматически экспортное ограничение.…
- **История и искусство: в ФТС России открылись тематические экспозиции** (`evt_live_a6b3697d5d6f004dfdfb9984`)
  - reason=`official_source`, official=`['fts_ru']`, occurred_at=`2026-10-23T11:48:00`
  - source: Федеральная таможенная служба · https://customs.gov.ru/press/federal/document/714107 · published_at=2026-10-23T11:48:00
  - limitation: Институциональные пресс-релизы ФТС ≠ автоматически экспортное ограничение.…
- **Состоялось торжественное открытие памятника Михаилу Дмитриевичу Поспелову** (`evt_live_203ded6238eca4871706dddf`)
  - reason=`official_source`, official=`['fts_ru']`, occurred_at=`2026-10-23T09:23:00`
  - source: Федеральная таможенная служба · https://customs.gov.ru/press/federal/document/714064 · published_at=2026-10-23T09:23:00
  - limitation: Институциональные пресс-релизы ФТС ≠ автоматически экспортное ограничение.…
- **В центральном аппарате ФТС России будет воздвигнут мемориал таможенникам – участникам специальной военной операции** (`evt_live_c455c7c09a694916e87cee0d`)
  - reason=`official_source`, official=`['fts_ru']`, occurred_at=`2026-10-23T09:06:00`
  - source: Федеральная таможенная служба · https://customs.gov.ru/press/federal/document/714058 · published_at=2026-10-23T09:06:00
  - limitation: Институциональные пресс-релизы ФТС ≠ автоматически экспортное ограничение.…
- **Remarks by Commissioner Šefčovič at the press conference following the informal Foreign Affairs Council (Trade)** (`evt_live_cab435340ab494d71a358eb3`)
  - reason=`official_source`, official=`['ec_presscorner']`, occurred_at=`2026-10-23T14:54:52`
  - source: Press releases - RSS · https://ec.europa.eu/commission/presscorner/detail/en/speech_26_2252 · published_at=2026-10-23T14:54:52
  - limitation: Параметр dossier=trade в RSS API фактически не фильтрует выдачу (проверено 2026-10-24: те же заголовки с/без dossier). Ленту нельзя называть «торговой»; это общ…
- **Speech by President von der Leyen to the Hungarian National Assembly on the occasion of the 70th anniversary of the Hungarian Revolution of 1956** (`evt_live_9feb2149dbe092a7ab1be89c`)
  - reason=`official_source`, official=`['ec_presscorner']`, occurred_at=`2026-10-23T09:40:50`
  - source: Press releases - RSS · https://ec.europa.eu/commission/presscorner/detail/en/speech_26_2251 · published_at=2026-10-23T09:40:50
  - limitation: Параметр dossier=trade в RSS API фактически не фильтрует выдачу (проверено 2026-10-24: те же заголовки с/без dossier). Ленту нельзя называть «торговой»; это общ…
- **Commission proposes stronger recognition of European heritage sites*** (`evt_live_e1705836e2eec45579fc420a`)
  - reason=`official_source`, official=`['ec_presscorner']`, occurred_at=`2026-10-23T09:39:39`
  - source: Press releases - RSS · https://ec.europa.eu/commission/presscorner/detail/en/ip_26_2250 · published_at=2026-10-23T09:39:39
  - limitation: Параметр dossier=trade в RSS API фактически не фильтрует выдачу (проверено 2026-10-24: те же заголовки с/без dossier). Ленту нельзя называть «торговой»; это общ…
- **Daily News 23 / 10 / 2026** (`evt_live_19e683fc49b7867b7152e36b`)
  - reason=`official_source`, official=`['ec_presscorner']`, occurred_at=`2026-10-23T09:37:47`
  - source: Press releases - RSS · https://ec.europa.eu/commission/presscorner/detail/en/mex_26_2249 · published_at=2026-10-23T09:37:47
  - limitation: Параметр dossier=trade в RSS API фактически не фильтрует выдачу (проверено 2026-10-24: те же заголовки с/без dossier). Ленту нельзя называть «торговой»; это общ…
- **EU Civil Protection Mechanism turns 25** (`evt_live_0ed7cca2b28af52ddf70fa59`)
  - reason=`official_source`, official=`['ec_presscorner']`, occurred_at=`2026-10-23T09:09:38`
  - source: Press releases - RSS · https://ec.europa.eu/commission/presscorner/detail/en/ip_26_2248 · published_at=2026-10-23T09:09:38
  - limitation: Параметр dossier=trade в RSS API фактически не фильтрует выдачу (проверено 2026-10-24: те же заголовки с/без dossier). Ленту нельзя называть «торговой»; это общ…
- **The Philippines launches safeguard investigation on pork** (`evt_live_0570a918bb2f1672f6aacf9f`)
  - reason=`official_source`, official=`['wto']`, occurred_at=`2026-10-21T00:00:00`
  - source: World Trade Organization — Latest news · https://wto.org/english/news_e/news26_e/safe_phl_21oct26_520_e.htm · published_at=2026-10-21T00:00:00
  - limitation: Публикация подтверждает происхождение сообщения ВТО, не вступившую меру третьей страны и не ущерб конкретной компании.…
- **Trade Facilitation Committee advances TFA review and discusses implementation support** (`evt_live_5ca416b18888afa7eff455ca`)
  - reason=`official_source`, official=`['wto']`, occurred_at=`2026-10-21T00:00:00`
  - source: World Trade Organization — Latest news · https://wto.org/english/news_e/news26_e/fac_21oct26_522_e.htm · published_at=2026-10-21T00:00:00
  - limitation: Публикация подтверждает происхождение сообщения ВТО, не вступившую меру третьей страны и не ущерб конкретной компании.…
- **WTO and multilateral partners review progress on supply chain finance initiative** (`evt_live_91a879ee7112b6658161dde7`)
  - reason=`official_source`, official=`['wto']`, occurred_at=`2026-10-16T00:00:00`
  - source: World Trade Organization — Latest news · https://wto.org/english/news_e/news26_e/trfin_16oct26_517_e.htm · published_at=2026-10-16T00:00:00
  - limitation: Публикация подтверждает происхождение сообщения ВТО, не вступившую меру третьей страны и не ущерб конкретной компании.…
- **Import Licensing Committee addresses notifications, trade concerns, transparency efforts** (`evt_live_cc2284f878309abbe668fb08`)
  - reason=`official_source`, official=`['wto']`, occurred_at=`2026-10-15T00:00:00`
  - source: World Trade Organization — Latest news · https://wto.org/english/news_e/news26_e/impl_15oct26_518_e.htm · published_at=2026-10-15T00:00:00
  - limitation: Публикация подтверждает происхождение сообщения ВТО, не вступившую меру третьей страны и не ущерб конкретной компании.…
- **Talks kick off for Timor-Leste's accession to government procurement pact** (`evt_live_6e7009ecab522d8f08274eda`)
  - reason=`official_source`, official=`['wto']`, occurred_at=`2026-10-14T00:00:00`
  - source: World Trade Organization — Latest news · https://wto.org/english/news_e/news26_e/gpro_14oct26_515_e.htm · published_at=2026-10-14T00:00:00
  - limitation: Публикация подтверждает происхождение сообщения ВТО, не вступившую меру третьей страны и не ущерб конкретной компании.…

### Остаются отклонёнными

Interfax / Vedomosti (и прочие одиночные коммерческие) — по-прежнему `unverified_single_source`. Примеры:

- Тела трех человек нашли при разборе завалов после ракетной атаки ВСУ в Орле — `unverified_single_source` (commercial_single_source_gate)
- В Ижевске из-за угрозы БПЛА временно остановили работу общественного транспорта — `unverified_single_source` (commercial_single_source_gate)
- За сутки силы ПВО сбили 1297 украинских БПЛА и пять ракет — `unverified_single_source` (commercial_single_source_gate)
- Захарова призвала Италию прислушаться к мнению граждан — `unverified_single_source` (commercial_single_source_gate)
- На Украине Starlink возобновил стабильную работу на скорости более 400 км/ч — `unverified_single_source` (commercial_single_source_gate)
- Аэропорты двух городов ХМАО ограничили прием и выпуск рейсов — `unverified_single_source` (commercial_single_source_gate)
- Пожар произошел в историческом чайном домике в Альпах, принадлежавшем Гитлеру — `unverified_single_source` (commercial_single_source_gate)
- Более 40 БПЛА уничтожено за сутки над Брянской областью — `unverified_single_source` (commercial_single_source_gate)

Расследование / предложение / вступившая мера не смешиваются в статусе Event: заголовок источника сохраняется (напр. WTO «safeguard **investigation**» не переписывается во «вступившую меру»).

---

## 4. Конкурсный режим + heuristic

Отключать `COMPETITION_MODE` для heuristic **не нужно**: `enrich_cluster(..., prefer_live=False)` сразу вызывает `heuristic_enrich` и не заходит в `live_enrich` / hackathon HTTP. Guard провайдера не ослаблялся. В прогоне COMPETITION_MODE=true + `--heuristic-enrich` / `prefer_live_enrich=False`.

---

## 5. Регрессии

`tests/test_official_primary_sources.py` + `tests/test_ingestion.py` — 21 passed (в т.ч. fake publisher, lookalike domain, payload ignore, reprocess idempotent, competition+heuristic).

---

## 6. Ограничения

- EC presscorner официален как первоисточник EC, но лента с `dossier=trade` тематически не отфильтрована API.
- Официальная публикация ≠ релевантность для «упк» (optional recompute: {'impacts_returned': 0, 'active': 0}).
- Основной стенд и `real_news_613` не обновлялись этим прогоном.

Машинный отчёт: `data/competition_stand/business_news_coverage/primary_publication_report.json`
