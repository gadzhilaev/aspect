# Company page redesign

Дата: 2026-10-24  
Маршрут хаба: **`/company`**  
Frontend: `frontend/` (monorepo `kontur_back`).

## Что изменено

- Главная «Компания» пересобрана под структуру мобильного макета Figma (`24:794`): карточка компании + сетка из шести разделов.
- Desktop: сетка **3×2**; планшет/телефон: **2 колонки** (не растянутый телефон на всю ширину).
- Добавлены разделы (frontend-only маршруты):
  - `/company/products` — Продукты  
  - `/company/markets` — Рынки  
  - `/company/geography` — География  
  - `/company/me` — Мои данные  
  - `/company/finance` — Финансы  
  - `/company/setup` — без изменений (мастер)  
  - `/company/counterparties` — Контрагенты и связи  
- Редактирование ведёт в существующий `/company/setup?step=…` (без изменений backend).
- `useAsync` сбрасывает предыдущие данные при смене зависимостей (защита от чужого контекста при смене компании).
- Убраны с хаба: «карта влияния», «точность рекомендаций / качество», искусственные проценты, показ размера/сотрудников без требования ТЗ.

Figma была доступна через MCP; визуал адаптирован к токенам Аспекта (не 1:1 копия фиолетовых/водяных знаков макета).

## Откуда данные каждого раздела

| Раздел | Источник |
|--------|----------|
| Шапка (имя, отрасль, ИНН) | `GET /companies/{id}/profile` → `company.*` |
| Происхождение реквизитов | `profile.settings.preferences.registry_provenance` |
| Переключатель компаний | `GET /users/me` → `companies[]` + `setCompanyId` |
| Продукты | nodes `product` (отдельно components / production_line) |
| Рынки | nodes `market` |
| География | `hq_region`, facilities, прочие country/region узлов (не markets) |
| Мои данные | `user.display_name`, `user.email`; бизнес-роль из `product.attributes_json.business_role`; доступ — `companies[].role` |
| Финансы | ручные: `settings.optional_finance` + `purchase_currencies`; банк: `case_context.profile.products` / factoring при `profile_available` |
| Контрагенты | nodes `supplier` + edges без payment/`case_payment` |

Case-контекст подгружается через `GET /companies/{id}/context` best-effort (ошибка не роняет хаб).

## Что API не отдаёт / разрывы

- Список «конкурсных контрагентов» целиком — **нет**; UI явно это говорит.
- Смена пароля / удаление аккаунта — **нет** кнопок-заглушек.
- Размер компании и численность на хабе **не показываем** (даже если `size_band` есть в профиле) — по ТЗ.
- Полный Figma-набор декоративных SVG/водяных знаков не копировался; иконки — локальные inline SVG на токенах.

## Проверки

Выполнено (2026-10-24):

- `npm run test:company-hub` — 9/9 (пустые секции, zero vs null, 4 mark-статуса, payment≠supply, без «СеверПром»)
- `npm run test:company-registry` — 19/19
- `npm run lint` — без ошибок (есть прежние warnings вне этой задачи)
- `npm run build` — production build OK

Не заявлено как выполненное:

- DOM/browser UI pass (по ограничению: без скриншотов/CDP в этой задаче).

### Ручной чеклист

1. Войти → `/company` — имя, отрасль/ИНН при наличии, 6 карточек.  
2. Светлая и тёмная тема.  
3. Ширина desktop ≥1024 (3 колонки) и ~390px (2 колонки).  
4. Пустой профиль → «Не заполнено» + переход в setup.  
5. Карточка Финансы: `debt_amount: 0` видно как 0; пустое поле не как 0.  
6. Смена компании в select — экран очищается, затем новые данные.  
7. Каждый из шести разделов → «← К компании», редактирование в setup.

## Как открыть

```powershell
cd frontend
# VITE_API_BASE_URL=http://127.0.0.1:8003
npm run dev
```

Открыть http://127.0.0.1:5173/company (нужна сессия и выбранная компания).
