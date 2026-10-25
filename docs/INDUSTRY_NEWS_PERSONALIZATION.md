# Отраслевые новости и персонализация (electronics v1)

Дата: 25 октября 2026  
ТЗ: `INDUSTRY_NEWS_PERSONALIZATION_TZ.md`

## Карта потока

```
профиль (nodes + preferences.industry_profile)
  → SearchInterest (общие ключи, без PII компании)
  → источники (RSS / GDELT / CBR — существующий scheduler)
  → Event (+ attributes brands / categories / industry_event_types)
  → industry_profile_match | case_profile_match | Impact
  → карточка Flutter («По вашим продуктам», без фейкового Impact)
```

## Признаки профиля

Хранятся аддитивно в `CompanyProfileSettings.preferences_json["industry_profile"]`:

| Поле | Назначение |
|------|------------|
| `activity_role` | retailer / manufacturer / distributor / other |
| `product_categories` | смартфоны, электроника… |
| `brands` | Apple, Samsung… |
| `product_lines` | iPhone… |
| `sales_markets` | рынки продаж |
| `procurement_countries` | география закупок |
| `purchase_currencies` | валюты закупок |

Плюс имена продуктов/рынков из `CompanyNode` (ручной twin). Конкурсные case-данные не перезаписываются.

API:

- `GET /companies/{id}/industry-profile`
- `PATCH /companies/{id}/industry-profile`

## Отбор в ленту

Новый `score_kind=industry_profile_match`:

- `impact_score=null`, `impact_score_available=false`
- `inclusion_bases` включает `industry_profile`
- `profile_relevance.label` = «По вашим продуктам»
- **не** создаёт `EventImpact`
- **не** даёт право на Telegram (политика: только `company_calculated`)

Точность: `exact` (бренд/линейка) vs `broad` (категория без бренда).

## Источники (v1)

Используется существующий whitelist RSS + GDELT + CBR.  
Новые хосты в доверенные автоматически не добавляются.  
Сигналы брендов/категорий пишутся в `event.attributes_json` при publish (`electronics_v1`).

Ограничения: квоты GDELT, backoff `429`, поиск **не** запускается из GET ленты.

## Flutter

- В «Продукты»: бренды и категории.
- В «Рынки»: география закупок.
- Лента читает `profile_relevance` / `industry_profile_match`.
- Нет демо-fallback при ошибке API.
- Тематическая карточка без денежного exposure.

## Тесты

`backend/tests/test_industry_news_personalization.py` — матрица персонализации (iPhone US/CN, broad, food no-match, shared interests).

## Ограничения

- Первая отрасль: электроника. Успех здесь ≠ поддержка всех отраслей.
- Удаление узлов графа API пока не даёт; industry prefs очищаются через PATCH null/[].
- Live LLM / расширение Telegram — вне этой версии.
