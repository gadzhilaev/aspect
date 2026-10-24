# Mobile-first audit — Аспект (web)

Дата: 2026-10-19  
Область: `web/` (UI/UX only). Backend, API, Flutter, business logic, provider settings и demo data не менялись.

## Проверенные viewport

| Viewport | Назначение |
|---|---|
| 375×812 | компактный iPhone |
| 390×844 | основной mobile |
| 430×932 | большой телефон |
| 768×1024 | tablet portrait |

Критерий overflow: `document.documentElement.scrollWidth <= window.innerWidth` (через CDP `Runtime.evaluate`, без screenshots).

## Проверенные маршруты

### Публичные
- `/`
- `/news`
- `/news/markets`
- `/news/industries`
- `/news/opportunities`
- `/news/:id` (живой id из public news)
- `/about`
- `/login`
- `/register`

### После входа (demo session)
- `/company/setup`
- `/company`
- `/for-you` → redirect на `/news/for-you`
- `/scenarios`
- `/events/:id/impact`
- `/events/:id/assistant`
- `/decisions/:decisionId`

## Найденные и исправленные mobile defects

### Layout / chrome
- `.site` / `.auth-shell`: `100vh` → `100dvh` (с `vh` fallback).
- Safe-area insets для `.site`, footer, mobile-nav, assistant stage/expanded chat.
- Sticky setup CTA на mobile (`safe-area-inset-bottom`).
- Footer: уже был 1-col ≤768; увеличен touch padding у ссылок.
- News hub nav: горизонтальный scroll вместо сжатого wrap на узких экранах.
- Home: section head в колонку; уменьшен clamp заголовков; radar chain уже был 1-col.

### Header / theme / menu
- `menu-toggle` и `theme-toggle`: минимум 44×44.
- Theme menu items: `min-height: 44px`.
- Mobile menu: закрытие по Escape и при смене маршрута.
- Theme menu ширина ограничена `calc(100vw - 32px)`.

### Forms / setup
- `input/select/textarea` (`.field`, search, mobile search, scenarios search, assistant composer, decision dialog): `font-size: 16px` (без iOS zoom).
- Setup progress: горизонтальный stepper вместо тесной 2-колоночной сетки.
- Setup actions: sticky + `min-height: 44px` у кнопок.

### Assistant / impact / decision / scenarios
- Assistant panel: `max-height` на `100dvh`.
- Expanded chat учитывает safe-area.
- Chips wrap (не горизонтальный overflow-скролл).
- Touch targets: send, chips, scenario select, decision actions.
- Source name: убран жёсткий `min-width: 8rem`.
- Scenarios mobile: full-bleed workspace (без лишних container gutters).
- Scenarios row footer: `flex-wrap`.
- Decision cancel dialog: bottom-sheet поведение на ≤640px.
- Decision checkbox hit area: 44×44.
- ImpactPanel: убраны inline styles → `.metric-span` / `.metric-val-lg`.
- Metrics: `clamp` + `overflow-wrap` для длинных значений.

## Изменённые файлы

- `web/src/styles/site.css`
- `web/src/styles/global.css`
- `web/src/styles/assistant.css`
- `web/src/styles/scenarios.css`
- `web/src/styles/decision.css`
- `web/src/styles/home.css`
- `web/src/layouts/SiteLayout.tsx`
- `web/src/components/personal/ImpactPanel.tsx`
- `docs/MOBILE_AUDIT.md` (этот отчёт)

Ранее в этой ветке (не часть backend): `about.css` / `company.css` / `ThemeToggle` — без дополнительной правки в этом аудите, кроме уже существующих inverse/h1 фиксов.

## Результаты проверок

### Build
- `npm run build` — **успешно**

### Tests
- `pytest tests/test_theme_contract.py tests/test_frontend_routes_contract.py` — **10 passed**

### Static search (после фиксов)
- Form controls: **16px**
- Full-screen mobile UI: **`100dvh`** (assistant/scenarios/decision); shell имеет `vh`+`dvh`
- Hover-only primary actions: не найдены (hover — визуальный усилитель)
- Signal-strip marquee шире viewport **намеренно**, клипится `overflow: hidden` родителя → document overflow **нет**

### DOM overflow

| Viewport | Маршруты | `scrollWidth <= innerWidth` |
|---|---|---|
| 375×812 | полный набор (public + auth + impact/assistant/decision) | **pass** |
| 390×844 | полный набор | **pass** |
| 430×932 | ключевые + auth | **pass** |
| 768×1024 | ключевые + auth | **pass** |

## Намеренно desktop-only

- Desktop nav + search в header (≥769px); на mobile — hamburger + mobile-nav.
- Assistant analysis aside / dual-pane — скрыты ≤1024px (полноэкранный chat).
- Scenarios list+detail split — desktop; на ≤900px — list **или** detail.
- Company map desktop layout — mobile использует `.company-map-mobile`.
- Header CTA short label (`cta-short`) на mobile.

## Известные ограничения

- Soft SPA-навигация в CDP через `history.pushState` + `popstate` (без Playwright). Контент мог частично оставаться от предыдущего маршрута; критерий document overflow всё равно проверялся на каждом URL.
- Signal-strip анимация визуально выходит за край внутри клипнутого контейнера — ожидаемо.
- Реальные notched devices / hardware keyboard / iOS Safari auto-zoom не тестировались на железе.
- Live AI / ingestion не запускались.
- Нет отдельного e2e suite на touch gestures (swipe/long-press).

## Итог

**mobile ready**

Оставшихся блокеров горизонтального overflow / обрезанных CTA / iOS zoom на формах / недоступного mobile menu по результатам этого аудита нет.
