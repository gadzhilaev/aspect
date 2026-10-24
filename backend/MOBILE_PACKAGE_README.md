# Kontur backend — пакет для мобильного разработчика

Снято с машины: 2026-10-24 18:16
Источник: kontur_back/backend (monorepo)

## Что внутри
- Весь код FastAPI (pp/), миграции, scripts, tests (+fixtures)
- contracts/openapi.json — контракт API
- docs/MOBILE_BACKEND_HANDOFF.md, docs/MOBILE_API.md, docs/COMPANY_INN_LOOKUP.md, …
- Lock-файлы зависимостей, Dockerfile, .env.example
- kontur.db — локальная демо-БД (если была на машине)

## Что НЕ включено (слишком тяжёлое / секреты / не нужно mobile)
- data/competition_stand, data/bank_materials, data/case (~30+ ГБ стенды/OCR/PDF)
- 	ools/tessdata (OCR)
- .env / .env.competition (секреты — бери только .env.example)
- __pycache__, .pytest_cache, .venv

## Старт
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install --require-hashes -r requirements.lock
copy .env.example .env
# заполни SECRET_KEY и при необходимости DADATA_API_KEY / ASSISTANT_*
python -m scripts.ensure_demo
.\scripts\run_backend.ps1
```
API: http://127.0.0.1:8003/docs
Демо: demo@kontur.app / DemoKontur1!

Handoff: docs/MOBILE_BACKEND_HANDOFF.md
