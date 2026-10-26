# Документация Аспект

Навигация по репозиторию. Секреты (пароли demo, API-ключи) в Git **не** кладём — только в пакете стенда (`demo_password.local`) / private-канале.

## С чего начать

| Документ | Для кого |
|----------|----------|
| [../README.md](../README.md) | Обзор продукта, быстрый старт, ссылки на релиз |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Как устроены клиент, API, данные |
| [MOBILE_APP.md](MOBILE_APP.md) | Flutter: экраны, API-клиент, темы, сборка |
| [PRODUCTION.md](PRODUCTION.md) | Публичный стенд, контейнеры, диагностика |
| [JURY_MOBILE_SCENARIO.md](JURY_MOBILE_SCENARIO.md) | Сценарий показа жюри в приложении |
| [MOBILE_STAND_CONNECTION.md](MOBILE_STAND_CONNECTION.md) | Подключение Flutter к локальному/стендовому API |

## Backend (контракты и домены)

Корень backend: [../backend/README.md](../backend/README.md).

| Тема | Документ |
|------|----------|
| HTTP API для мобилки | [../backend/docs/MOBILE_API.md](../backend/docs/MOBILE_API.md) |
| OpenAPI | [../backend/contracts/openapi.json](../backend/contracts/openapi.json) |
| Docker / конкурсный compose | [../backend/docs/COMPETITION_DOCKER.md](../backend/docs/COMPETITION_DOCKER.md) |
| Case-контекст (CSV / U_*) | [../backend/docs/CASE_CONTEXT_INTEGRATION.md](../backend/docs/CASE_CONTEXT_INTEGRATION.md) |
| Персональная лента | [../backend/docs/CASE_PERSONALIZED_FEED.md](../backend/docs/CASE_PERSONALIZED_FEED.md) |
| Impact / доверие к оценкам | [../backend/docs/ASSESSMENT_TRUST_AUDIT.md](../backend/docs/ASSESSMENT_TRUST_AUDIT.md) |
| Ассистент без impact | [../backend/docs/ASSISTANT_WITHOUT_IMPACT.md](../backend/docs/ASSISTANT_WITHOUT_IMPACT.md) |
| Hackathon LLM | [../backend/docs/HACKATHON_PROVIDER.md](../backend/docs/HACKATHON_PROVIDER.md) |
| Материалы банка | [../backend/docs/BANK_MATERIALS_API.md](../backend/docs/BANK_MATERIALS_API.md) |
| News scheduler | [../backend/docs/NEWS_SCHEDULER.md](../backend/docs/NEWS_SCHEDULER.md) |
| Telegram | [../backend/docs/TELEGRAM_NEWS_POLICY.md](../backend/docs/TELEGRAM_NEWS_POLICY.md) |
| Runbook жюри (API) | [../backend/docs/COMPETITION_JURY_RUNBOOK.md](../backend/docs/COMPETITION_JURY_RUNBOOK.md) |
| Acceptance | [../backend/docs/FINAL_COMPETITION_ACCEPTANCE.md](../backend/docs/FINAL_COMPETITION_ACCEPTANCE.md) |

Глубокие audit/fix-заметки лежат в `backend/docs/` (много файлов по отдельным фиксам). Для повседневной работы достаточно таблицы выше + OpenAPI.

## Прочее в `docs/`

- [INDUSTRY_NEWS_PERSONALIZATION.md](INDUSTRY_NEWS_PERSONALIZATION.md) — отраслевой отбор новостей  
- [QUALITY_MONITORING.md](QUALITY_MONITORING.md) — метрики качества  
- [MOBILE_BACKEND_RECONCILIATION.md](MOBILE_BACKEND_RECONCILIATION.md) — сверка мобилка ↔ API  

## Версии и релизы

| | |
|--|--|
| Версия приложения | `1.0.0+1` (`pubspec.yaml`) |
| GitHub Release | https://github.com/gadzhilaev/aspect/releases/tag/v1.0.0 |
| APK | asset `aspect-1.0.0.apk` на том же теге (не коммитится в дерево) |
