# Kontur backend (для Aspect mobile)

Пакет из `kontur_backend_mobile_*`, лежит в репозитории приложения.

## Старт (macOS / Linux)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.example .env   # SECRET_KEY уже можно поправить
python -m scripts.ensure_demo
uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

- Docs: http://127.0.0.1:8003/docs  
- Demo: `demo@kontur.app` / `DemoKontur1!`

iOS Simulator → `http://127.0.0.1:8003`  
Android emulator → `http://10.0.2.2:8003`  
Устройство в LAN → `--dart-define=API_BASE=http://<ip>:8003`

## Мобильные доработки API

- `POST /users/me/change-password`
- `DELETE /users/me`
- `PATCH /users/me/preferences` (`language`, `theme_mode`)
- поле `preferences` в `GET /users/me`

## Заглушки mobile-пакета

Корпус `app/services/bank_materials` (OCR/PDF) в пакет не входит.
Есть лёгкие stubs: evidence → `integration_not_configured`, download API → 503.
Для полного стенда банковских материалов нужен полный monorepo + `data/bank_materials`.
