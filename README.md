# Aspect — новостная аналитика для бизнес-решений

Мобильный прототип (Flutter) + backend (FastAPI) для кейса «Альфа Хак / Новостная аналитика».
Сервис отбирает значимые для компании события и даёт персонализированную интерпретацию
с опорой на внешние новости и аналитику Альфа-Банка.

**Не является** встройкой в интернет-банк Альфа-Бизнес. Точка входа для демо —
кнопка «войти через Альфа-Бизнес» в приложении; дальнейшую интеграцию делает заказчик.

## Идентификатор версии

| | |
|--|--|
| Ветка | `main` |
| Commit | см. `git rev-parse HEAD` на момент сдачи |
| Клиент | Flutter (`lib/`) |
| API | `backend/` |

## Архитектура

```text
Flutter (Aspect)
    │  HTTPS / LAN
    ▼
FastAPI (competition stand / Docker API)
    ├── лента + персонализация (case / industry / impact)
    ├── bank_materials (PDF + OCR + citations)
    ├── assistant agent loop (hackathon LLM allow-list)
    └── case CSV / company twin
```

Подробности API: [`backend/docs/MOBILE_API.md`](backend/docs/MOBILE_API.md).  
Стенд mobile: [`docs/MOBILE_STAND_CONNECTION.md`](docs/MOBILE_STAND_CONNECTION.md).  
Сценарий жюри: [`docs/JURY_MOBILE_SCENARIO.md`](docs/JURY_MOBILE_SCENARIO.md).  
Мониторинг качества: [`docs/QUALITY_MONITORING.md`](docs/QUALITY_MONITORING.md).  
Сторонние компоненты: [`THIRD_PARTY_NOTICES`](THIRD_PARTY_NOTICES).

## Требования

- Python **3.12**
- Flutter (stable) для клиента
- Docker Engine + Compose (опционально, для API-стека)
- Конкурсные CSV/PDF/OCR — **вне Git** (см. jury runbook)

## Быстрый старт — локальный стенд (рекомендуется для мобилки)

1. Поднять API по [`docs/MOBILE_STAND_CONNECTION.md`](docs/MOBILE_STAND_CONNECTION.md)
   (порт обычно `:8020`, `COMPETITION_MODE=true`).
2. В Flutter указать base URL стенда.
3. Пройти [`docs/JURY_MOBILE_SCENARIO.md`](docs/JURY_MOBILE_SCENARIO.md):
   Альфа-демо → компания → лента → новость → основания (банк / AI) → чат → план.

Учётки и пароли — только в `demo_password.local` стенда (не в Git).

## Docker — API (+ bootstrap, news_scheduler)

Compose в корне репозитория: [`docker-compose.competition.yml`](docker-compose.competition.yml).  
**Без** React web: UI — Flutter. Подробности: [`backend/docs/COMPETITION_DOCKER.md`](backend/docs/COMPETITION_DOCKER.md).

```bash
# из корня репо
cp backend/.env.competition.example backend/.env.competition
# правьте COMPETITION_INPUTS_DIR / COMPETITION_EXTERNAL_UIDS

docker compose -f docker-compose.competition.yml --env-file backend/.env.competition build api

COMPETITION_BOOTSTRAP_MODE=preflight \
  docker compose -f docker-compose.competition.yml --env-file backend/.env.competition \
  --profile bootstrap run --rm bootstrap

COMPETITION_BOOTSTRAP_MODE=bootstrap \
  docker compose -f docker-compose.competition.yml --env-file backend/.env.competition \
  --profile bootstrap run --rm bootstrap

docker compose -f docker-compose.competition.yml --env-file backend/.env.competition \
  up -d api news_scheduler

curl -fsS "http://127.0.0.1:${COMPETITION_API_HOST_PORT:-8019}/health"
```

Конкурсный профиль (обязателен на сдаче):

- `COMPETITION_MODE=true`
- `ASSISTANT_PROVIDER=hackathon` (только allow-list моделей организаторов)
- `ASSISTANT_AGENT_LOOP=true`
- без `OPENAI_API_KEY` / `GIGACHAT_AUTH_KEY`

## Зависимости backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install --require-hashes -r requirements.lock
```

Linux-образ Docker: `requirements-linux.lock`.

## Проверки

```bash
cd backend
pytest tests/test_industry_news_personalization.py tests/test_holdout_personalization.py -q
python scripts/quality_metrics_snapshot.py --db path/to/stand.db
python scripts/verify_competition_docker_static.py
```

## Честные границы

- AI-evidence в демо опирается в первую очередь на материал «Ключевая ставка» (Policy Rate); остальные PDF банка доступны как поиск / оригинал.
- Доля рынка из кейс-CSV как отдельный признак **не** выдумывается.
- K08 (главный экран Альфа-Бизнес) закрыт демо-кнопкой входа; нативная интеграция — на стороне банка.
