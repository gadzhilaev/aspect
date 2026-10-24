# Clean-environment verification (этап 6.4)

Дата: **2026-10-23**  
Назначение: воспроизводимые зависимости + установка в **новое изолированное** окружение на этой машине.  
**Не** является проверкой Docker-образа, Linux CI или «другой физической машины».

Рабочий `.venv`, `web/node_modules`, root `.env`, `:8003` и живые процессы **не** трогались.

---

## 1. Платформа и toolchain (факт)

| | |
|--|--|
| OS | Windows 10/11 (build 10.0.26200), win_amd64 |
| Python | **3.12.10** (`C:\Users\…\Python312\python.exe`) |
| pip (в clean venv) | 26.2.2 |
| Node.js | **v24.19.0** |
| npm | **11.17.0** |
| Lock compiler | `pip-tools` / `pip-compile --generate-hashes` (изолированный temp venv) |

Зафиксировано в репо:

- `.python-version` → `3.12.10`
- `web/.nvmrc` → `24`
- `web/package.json` → `engines.node >=18.18.0`

---

## 2. Lock-файлы

| Файл | Содержание |
|------|------------|
| `requirements.in` | Прямые **runtime** пины |
| `requirements.lock` | Полное дерево runtime + hashes + markers (`pip-compile`) |
| `requirements-dev.in` | Runtime + pytest / pytest-asyncio / Pillow |
| `requirements-dev.lock` | Полное дерево dev/test + hashes |
| `requirements.txt` | Человекочитаемые runtime-пины (= `.in`); install → **lock** |
| `web/package-lock.json` | npm lock (уже был) |

**Не** использовался `pip freeze` из загрязнённого рабочего venv.

Добавлен runtime-пакет `pypdf==5.4.0` (использовался кодом/тестами, ранее отсутствовал в pins).

**Платформа проверки lock:** Windows win_amd64 (эта машина).  
Наличие multi-platform hashes в lock **не** равно «Docker/Linux install пройден».

Пересборка:

```powershell
python -m venv %TEMP%\kontur_pip_compile
%TEMP%\kontur_pip_compile\Scripts\pip install -U pip pip-tools
pip-compile --generate-hashes -o requirements.lock requirements.in
pip-compile --generate-hashes -o requirements-dev.lock requirements-dev.in
```

---

## 3. Чистая установка (результаты)

### 3.1 Python runtime lock

Каталог: `%TEMP%\kontur_clean_runtime_venv_64` (новый venv).

```text
pip install --require-hashes -r requirements.lock
→ exit 0
pip check
→ No broken requirements found. (exit 0)
```

### 3.2 Python dev lock (+ тесты)

Каталог: `%TEMP%\kontur_clean_venv_64` (новый venv).

```text
pip install --require-hashes -r requirements-dev.lock
→ exit 0
pip check
→ No broken requirements found. (exit 0)
```

### 3.3 Frontend

Каталог: `%TEMP%\kontur_clean_web_64` — копия `web/` **без** `node_modules` / `dist` / `.env`  
(актуальные незакоммиченные исходники + `package-lock.json`).

```text
npm ci   → exit 0
npm run build → exit 0 (dist/index.html created)
```

Предупреждения Vite о отсутствующих Styrene `.woff2` — ожидаемы (шрифты не в репо; см. `THIRD_PARTY_NOTICES`).

---

## 4. Проверки backend из clean venv

Env: временная SQLite / `APP_ENV=test`; `HACKATHON_API_KEY` / model keys сняты;  
`tests/conftest.py` сбрасывает унаследованный `COMPETITION_MODE`.

| Проверка | Результат |
|----------|-----------|
| `from app.main import app` | OK |
| `alembic upgrade head` на новой temp SQLite | OK (001→007) |
| `tests/test_competition_profile.py` | passed |
| `tests/test_competition_stand_bootstrap.py` | passed |
| `tests/test_competition_stand_storage_regression.py` | passed |
| `tests/test_assistant_agent_hackathon_loop.py` (mocked HTTP) | passed |
| **Итого critical** | **47 passed** |

Live LLM / ingestion / полный импорт 1.38M платежей / текущие серверы — **не** запускались.

---

## 5. Регрессия storage (из 6.3) без repair

Тест: `tests/test_competition_stand_storage_regression.py`  
Фикстуры: tiny CSV (`U_900001`/`U_900002`) + синтетический Policy Rate PDF/OCR/QA.

Поток доказательства:

1. Полный штатный `run_bootstrap` → `status=ready`, storage непустой (PDF SHA = source).  
2. **Новый процесс** `scripts/verify_competition_stand.py`: login, company context, bank evidence/documents, PDF via API + SHA; `model_http` blocked.  
3. Relocate stand → повторный verify.  
4. Повторный bootstrap с теми же входами → **no-op**, inventory SHA storage без изменений.

`scripts/_repair_stand_storage.py` **не** вызывался и не импортируется тестом.

---

## 6. OCR: runtime vs rebuild

| Нужно для | Зависимости |
|-----------|-------------|
| Запуск стенда / API с **готовым** OCR-корпусом | Python runtime lock + (для UI) npm; **без** Tesseract |
| Повторный / новый OCR корпуса | Системный Tesseract + `eng`/`rus` tessdata (см. `THIRD_PARTY_NOTICES` §F); **не** в `requirements.lock` |

---

## 7. Ограничения (честно)

| Утверждение | Статус после 6.4 |
|-------------|------------------|
| Lock существует | **Да** (`requirements.lock`, `requirements-dev.lock`, npm lock) |
| Установка из lock на этой Windows-машине | **Да** (temp venv + temp web) |
| Docker build / install-from-lock в Linux-образе | **PASS** в 6.14 (API image + `uvloop` pin); fixture smoke OK — `docs/COMPETITION_DOCKER_VERIFICATION.md` |
| Запуск на другой физической машине | **Не пройдено** |
| Clean-machine «с нуля без локального Python/Node» | **Не пройдено** |

Windows-проверка **не** выдаётся за Linux/Docker-совместимость.

---

## 8. Сопутствующие правки (минимальные)

- `pypdf` в runtime pins.  
- `stage_corpus`: создание `staging_parent`, если отсутствует.  
- Preflight OCR fingerprint: сбор PSM из `pages[]` как у loader (иначе QA binding расходился с corpus manifests).  
- `tests/conftest.py`: изоляция от parent `COMPETITION_MODE`.  
- Forbidden host: `PROVIDER_MISCONFIGURED` в normal mode; `COMPETITION_MISCONFIGURED` при `require_competition_exact` / competition mode.
