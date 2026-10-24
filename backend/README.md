# Kontur backend (для Aspect mobile)

Пакет из `kontur_backend_mobile_*`, лежит в репозитории приложения.

## Старт (macOS / Linux)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # или: pip install --require-hashes -r requirements.lock
cp -n .env.example .env
alembic upgrade head              # обязательно: схема, в т.ч. 012 preferences_json
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
- `DELETE /users/me` — body `{ "password": "..." }`; отказ `SOLE_OWNER` / `HAS_AUDIT_RECORDS`
- `PATCH /users/me/preferences` (`language`, `theme_mode`)
- поле `preferences` в `GET /users/me`

## Bank materials

Исходный код `app/services/bank_materials/` восстановлен из патча (не stubs).
Без env/корпуса API честно отвечает `integration_not_configured` / `BANK_MATERIALS_NOT_CONFIGURED`.

Нужно для живого корпуса:

- `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS`
- `BANK_MATERIALS_STORAGE_ROOT`
- OCR/PDF данные (обычно `data/bank_materials/…`)
- миграция `007_bank_materials` (входит в `alembic upgrade head`)

См. `docs/BANK_MATERIALS_PATCH_README.md`, `docs/MOBILE_BACKEND_RECONCILIATION.md`.
