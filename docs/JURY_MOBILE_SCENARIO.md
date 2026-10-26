# Сценарий жюри — Flutter Aspect (единый путь)

Дата: 2026-10-25  
Цель: пройти **один** поток от входа до персонализированной интерпретации
с отделением аналитики банка и вывода AI.  
Точка входа Альфа-Бизнес (K08) — демо-кнопка в приложении; нативная интеграция вне скоупа.

## Предпосылки

1. API доступен:
   - публично: `https://gadzhilaev.ru/aspekt-api` — [`PRODUCTION.md`](PRODUCTION.md);  
   - локально `:8020` — [`MOBILE_STAND_CONNECTION.md`](MOBILE_STAND_CONNECTION.md);  
   - Docker — [`../backend/docs/COMPETITION_DOCKER.md`](../backend/docs/COMPETITION_DOCKER.md).
2. `COMPETITION_MODE=true`, `ASSISTANT_PROVIDER=hackathon`, agent loop on.
3. Flutter / APK указывает на base URL стенда (release по умолчанию — публичный API).
4. Учётки — email demo A/B в README; **пароль** только из `demo_password.local` (не в Git).

## Шаги

| # | Действие | Что проверить |
|---|----------|---------------|
| 1 | Экран входа → **войти через Альфа-Бизнес** (демо) | Открывается демо-поток / стенд без фейковой ленты при ошибке API |
| 2 | Компания | Имя, отрасль; при case-link — ОКВЭД / группа / выручка; **доля рынка** — «не рассчитана», не выдумана |
| 3 | Контекст: продукты / бренды / рынки / закупки | Сохранение industry-profile |
| 4 | Лента событий | Есть карточки с why-label («По вашим продуктам» / case / impact) |
| 5 | Открыть новость | Факт, «почему про вас», блок **Вывод модели (AI)** отдельно от **Аналитика Альфа-Банка** |
| 6 | «На чем основан вывод?» | Секции: компания / факт / банк / AI / неизвестно — без «СеверПром»-хардкода |
| 7 | «Обсудить с Аспект» (чат) | Ответ ассистента; при agent loop — блок **Шаги анализа** (`analysis_steps`) |
| 8 | Материал банка / сценарии / план | PDF или evidence при доступности; сценарии — явный user action |

## Честные границы демо

- AI-evidence цитирования в первую очередь на **Policy Rate**; остальные PDF — search / оригинал.
- Hold-out логика без seed Policy Rate / China-export — `backend/tests/test_holdout_personalization.py`.
- Пустая лента при пустом корпусе — честный empty state, не демо-fallback.

## После прогона

```bash
cd backend
python scripts/quality_metrics_snapshot.py --db path/to/stand.db --json
pytest tests/test_holdout_personalization.py tests/test_industry_news_personalization.py -q
```
