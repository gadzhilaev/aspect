# Выравнивание сайта под мобильный стиль Аспекта

Дата: 2026-10-26  
Figma: `hQVv5iK7G49zrP3w4tPGQc` (экраны Обзор `24:460`, События `24:732`, Сценарии `24:1225`, Вход `24:372`, Компания уже ранее).

## Что сделано

Общий слой `frontend/src/styles/mobile-align.css` + правки страниц без смены API:

| Экран сайта | Ориентир Figma | Изменения |
|-------------|----------------|-----------|
| `/news`, `/news/markets` | События | kicker, pill-фильтры, signal-карточки |
| `/news/for-you` | События / Обзор | заголовок «Главные новости…», metric-strip, signal-карточки |
| `/news/industries`, `/news/opportunities` | События | тот же chrome |
| `/scenarios` | Сценарии | копирайт, поиск, accent-bar у строк |
| `/login`, `/register` | Вход / Регистрация | лого, «Назад», крупные поля, CTA |
| `/notifications`, `/settings` | стиль компании | surface-panel, page-kicker |
| `/company` | Компания | уже в предыдущей задаче |

Desktop остаётся многоколоночным (`signal-grid` 2 колонки ≥900px), не растянутым телефоном.

## Чего нет в API / не имитировали

- Курсовые плитки CNY/AMD/KRW с Обзора — **не добавлены** (нет источника в публичном API ленты).
- «Забыли пароль?» с экрана Вход — **нет** endpoint reset password.
- Нижний tab-bar Обзор/События/Компания/Сценарии — у сайта уже header/footer; мобильный tab bar не дублировали.
- Демо-подмены «СеверПром» не использовались.

## Проверки

- `npm run lint`
- `npm run build`
- `npm run test:company-hub` (регрессия хаба)

DOM/browser UI pass не заявлялся обязательным в этой итерации.

## Как смотреть

```powershell
cd frontend
npm run dev
```

Маршруты: `/news/for-you`, `/news`, `/scenarios`, `/login`, `/company`.
