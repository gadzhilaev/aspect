"""Build a human-readable business-context view from real company twin data."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    Company,
    CompanyEdge,
    CompanyNode,
    Event,
    EventImpact,
    ImpactPath,
    User,
)
from app.schemas.common import INDUSTRIES
from app.schemas.company_context import (
    CaseContextOut,
    CaseFactoringOut,
    CaseFtsGeographyOut,
    CaseGroupOut,
    CaseProductMarkOut,
    CaseProfileOut,
    CaseProvenanceOut,
    CaseResolvedFieldOut,
    CaseRevenueOut,
    CompanyContextOut,
    ContextExampleOut,
    CoverageBlockOut,
    MapGroupOut,
    TrackingCategoryOut,
)
from app.services.case_data.activate_snapshot import ActivationIntegrityError
from app.services.case_data.company_case_context import (
    CaseCompanyContext,
    CaseContextAccessError,
    CaseContextError,
    ResolvedCaseField,
    read_case_company_context,
)
from app.services.impact import has_finance_context

_INDUSTRY_LABELS = {i.id: i.name for i in INDUSTRIES}

_SIZE_LABELS = {
    "small": "Небольшая компания",
    "medium": "Средняя компания",
    "large": "Крупная компания",
    "enterprise": "Крупное предприятие",
}

_SETUP = "/company/setup"

_PRODUCT_LABELS = {
    "RKO": "Расчётно-кассовое обслуживание",
    "GAR": "Банковские гарантии",
    "LOA": "Кредиты",
    "LEA": "Лизинг",
    "DEP": "Депозиты",
    "ZPP": "Зарплатный проект",
}

_CASE_STATUS_EXPLANATIONS = {
    "integration_not_configured": (
        "Конкурсный слой данных не настроен на сервере "
        "(CASE_CONTEXT_SLOT_KEY не задан)."
    ),
    "not_linked": (
        "Компания не привязана к организации конкурсного справочника в этом слоте."
    ),
    "no_active_snapshot": (
        "Для слота нет активного снимка конкурсных данных."
    ),
    "uid_missing_in_snapshot": (
        "Привязанный U_ID отсутствует в активном снимке; данные прежнего снимка "
        "не подставляются."
    ),
    "profile_absent": (
        "Организация есть в активном снимке, но каталожный профиль отсутствует."
    ),
    "profile_available": (
        "Доступен профиль конкурсной организации из активного снимка. "
        "Ручные поля компании не заменяются."
    ),
}

_FACTORING_EXPLANATIONS = {
    "true": (
        "В каталоге отмечено наличие факторинга. "
        "Сумма, ставка и условия договора неизвестны."
    ),
    "false": (
        "В каталоге факторинг отмечен как отсутствующий. "
        "Это не оценка кредитоспособности."
    ),
    "unknown": "Сведения о факторинге в каталоге неизвестны или неполны.",
    "conflict": (
        "Отметки факторинга в вариантах каталога расходятся; "
        "значение не подтверждено."
    ),
}


_GEO_CANONICAL = {
    "china": "Китай",
    "китай": "Китай",
    "prc": "Китай",
    "кнр": "Китай",
    "russia": "Россия",
    "россия": "Россия",
    "rf": "Россия",
    "рф": "Россия",
    "cis": "СНГ",
    "снг": "СНГ",
}


def _canonical_geo(text: str) -> str:
    return _GEO_CANONICAL.get(text.casefold(), text)


def _uniq(values: list[str], *, limit: int = 8) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        text = (raw or "").strip()
        if not text:
            continue
        text = _canonical_geo(text)
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _join_human(values: list[str], *, max_show: int = 3) -> str:
    items = values[:max_show]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} и {items[1]}"
    head = ", ".join(items[:-1])
    return f"{head} и {items[-1]}"


def _node_countries(node: CompanyNode) -> list[str]:
    vals: list[str] = []
    if node.country:
        vals.append(node.country)
    if node.region:
        vals.append(node.region)
    attrs = node.attributes_json if isinstance(node.attributes_json, dict) else {}
    for key in ("countries", "markets"):
        raw = attrs.get(key)
        if isinstance(raw, list):
            vals.extend(str(x) for x in raw if x)
        elif isinstance(raw, str) and raw.strip():
            vals.append(raw.strip())
    return vals


def _business_role(nodes: list[CompanyNode]) -> str | None:
    for node in nodes:
        if node.node_type != "product":
            continue
        attrs = node.attributes_json if isinstance(node.attributes_json, dict) else {}
        role = attrs.get("business_role")
        if isinstance(role, str) and role.strip():
            return role.strip()
    return None


def _finance_snapshot(settings: Any) -> tuple[bool, list[str], dict[str, Any]]:
    from app.services.impact import has_fx_finance_context, has_rate_finance_context

    purchase = list((settings.purchase_currencies_json if settings else None) or [])
    optional = dict((settings.optional_finance_json if settings else None) or {})
    filled = has_finance_context(optional)
    values: list[str] = []
    for cur in purchase:
        if isinstance(cur, str) and cur.strip():
            values.append(cur.strip().upper())
    if has_rate_finance_context(optional):
        debt = optional.get("debt_amount")
        unit = str(
            optional.get("debt_amount_unit") or optional.get("debt_currency") or ""
        ).strip().upper()
        unit_s = f" {unit}" if unit and unit not in {"UNSPECIFIED", "UNKNOWN"} else ""
        if isinstance(debt, (int, float)) and debt == debt:
            if debt >= 1_000_000:
                values.append(
                    f"долг ~{debt / 1_000_000:.1f}".rstrip("0").rstrip(".")
                    + f" млн{unit_s or ' (ед. долга)'}"
                )
            else:
                values.append(f"долг указан{unit_s}")
        float_share = optional.get("floating_rate_share_percent")
        if isinstance(float_share, (int, float)) and float_share == float_share:
            values.append(f"плавающая ставка {int(round(float_share))}%")
    if has_fx_finance_context(optional):
        amt = optional.get("fx_exposure_amount")
        ccy = optional.get("fx_exposure_currency")
        direction = optional.get("fx_exposure_direction")
        if isinstance(amt, (int, float)) and isinstance(ccy, str):
            dir_ru = "платёж" if direction == "payment" else (
                "поступление" if direction == "receipt" else "FX"
            )
            values.append(f"{dir_ru}: {amt:g} {ccy}")
    if filled:
        cash = optional.get("cash_reserve_days")
        if isinstance(cash, (int, float)) and cash == cash:
            values.append(f"резерв ~{int(cash)} дн.")
    return filled, _uniq(values), optional


def _example_for_company(db: Session, company_id: str) -> ContextExampleOut:
    impact = (
        db.query(EventImpact)
        .filter(EventImpact.company_id == company_id)
        .order_by(EventImpact.impact_score.desc())
        .first()
    )
    if impact is None:
        return ContextExampleOut(available=False)
    event = db.get(Event, impact.event_id)
    if event is None:
        return ContextExampleOut(available=False)

    link_label: str | None = None
    path = (
        db.query(ImpactPath)
        .filter(ImpactPath.event_impact_id == impact.id)
        .order_by(ImpactPath.sort_order.desc())
        .first()
    )
    if path and isinstance(path.path_nodes_json, list):
        for node in reversed(path.path_nodes_json):
            if not isinstance(node, dict):
                continue
            name = node.get("name")
            ntype = node.get("node_type")
            if isinstance(name, str) and name.strip() and ntype in {
                "production_line",
                "market",
                "supplier",
                "component",
                "facility",
                "currency",
            }:
                link_label = name.strip()
                break
    if not link_label and impact.exposure_label:
        link_label = str(impact.exposure_label)

    return ContextExampleOut(
        available=True,
        event_id=event.id,
        public_title=event.title,
        public_summary=(event.summary or "")[:220] or None,
        impact_score=int(round(impact.impact_score or 0)),
        confidence_percent=int(round((impact.confidence or 0) * 100)),
        link_label=link_label,
        impact_href=f"/events/{event.id}/impact",
    )


def _basename_only(name: str | None) -> str | None:
    if not name:
        return None
    raw = name.strip()
    if not raw:
        return None
    # Never expose local paths — keep last path segment only.
    base = PureWindowsPath(raw).name
    base = PurePosixPath(base).name
    return base or None


def _sanitize_resolution_map(payload: dict[str, Any]) -> dict[str, Any]:
    banned = {"raw_json", "raw", "absolute_path", "file_path", "path"}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in banned or key.endswith("_path"):
            continue
        out[key] = value
    return out


def _field_out(field: ResolvedCaseField) -> CaseResolvedFieldOut:
    return CaseResolvedFieldOut(
        key=field.key,
        status=field.status,
        value=field.value,
        detail=field.detail,
    )


def _map_case_profile(ctx: CaseCompanyContext) -> CaseProfileOut | None:
    profile = ctx.profile
    if profile is None:
        return None
    snap = ctx.active_snapshot
    prov = profile.provenance
    return CaseProfileOut(
        external_uid=profile.external_uid,
        profile_resolution=profile.profile_resolution,
        okved_code=_field_out(profile.okved_code),
        okved_name=_field_out(profile.okved_name),
        city=_field_out(profile.city),
        region=_field_out(profile.region),
        workers_fns=_field_out(profile.workers_fns),
        workers_spark=_field_out(profile.workers_spark),
        company_age=_field_out(profile.company_age),
        products=[
            CaseProductMarkOut(
                code=p.code,
                label=_PRODUCT_LABELS.get(p.code, p.code),
                status=p.status,
            )
            for p in profile.products
        ],
        factoring=CaseFactoringOut(
            status=profile.factoring.status,
            explanation=_FACTORING_EXPLANATIONS[profile.factoring.status],
        ),
        fts_geography=CaseFtsGeographyOut(
            status=profile.fts_countries.status,
            countries_raw=list(profile.fts_countries.countries_raw),
            interpretation_note=(
                "Сырые названия стран ФТС из каталога; направление торговли не выводится."
            ),
            detail=profile.fts_countries.detail,
        ),
        group=CaseGroupOut(
            status=profile.group.status,
            external_group_id=profile.group.external_group_id,
            is_conflicted=profile.group.is_conflicted,
            detail=profile.group.detail,
        ),
        revenue=CaseRevenueOut(
            status=profile.revenue.status,
            revenue_raw=profile.revenue.revenue_raw,
            amount=profile.revenue.amount,
            unit=profile.revenue.unit,
            currency=profile.revenue.currency,
            limitations=list(profile.revenue.limitations),
        ),
        conflicts=_sanitize_resolution_map(profile.conflicts),
        absent=_sanitize_resolution_map(profile.absent),
        provenance=CaseProvenanceOut(
            snapshot_id=prov.snapshot_id,
            version_label=snap.version_label if snap else None,
            version_seq=snap.version_seq if snap else None,
            source_file=_basename_only(prov.source_file),
            source_row_numbers=list(prov.source_row_numbers),
            catalog_row_ids=list(prov.catalog_row_ids),
            variant_count=prov.variant_count,
        ),
    )


def build_case_context_block(
    db: Session,
    *,
    company: Company,
    user: User,
) -> CaseContextOut:
    """Additive case block for product context. Read-only; never writes."""
    slot = (get_settings().case_context_slot_key or "").strip()
    if not slot:
        return CaseContextOut(
            status="integration_not_configured",
            explanation=_CASE_STATUS_EXPLANATIONS["integration_not_configured"],
            read_only=True,
        )

    try:
        ctx = read_case_company_context(
            db,
            user=user,
            company_id=company.id,
            slot_key=slot,
        )
    except CaseContextAccessError as exc:
        # Membership is enforced by the endpoint; surface as forbidden if reached.
        raise AppError("FORBIDDEN", "Нет доступа к этой компании", 403) from exc
    except ActivationIntegrityError as exc:
        raise AppError(
            "CASE_INTEGRITY",
            f"Нарушение целостности активного снимка кейса: {exc}",
            500,
        ) from exc
    except CaseContextError as exc:
        raise AppError("CASE_CONTEXT_ERROR", str(exc), 500) from exc

    external_uid = None
    if ctx.link is not None:
        external_uid = ctx.link.external_uid
    elif ctx.missing_external_uid:
        external_uid = ctx.missing_external_uid

    snap = ctx.active_snapshot
    return CaseContextOut(
        status=ctx.status,  # type: ignore[arg-type]
        explanation=_CASE_STATUS_EXPLANATIONS.get(ctx.status, ctx.reason),
        slot_key=ctx.slot_key,
        external_uid=external_uid,
        snapshot_id=snap.snapshot_id if snap else None,
        version_label=snap.version_label if snap else None,
        version_seq=snap.version_seq if snap else None,
        profile=_map_case_profile(ctx),
        read_only=True,
    )


def build_company_context(
    db: Session,
    *,
    company: Company,
    user: User,
) -> CompanyContextOut:
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company.id).all()
    edges = db.query(CompanyEdge).filter(CompanyEdge.company_id == company.id).all()
    settings = company.settings

    by_type: dict[str, list[CompanyNode]] = {}
    for node in nodes:
        by_type.setdefault(node.node_type, []).append(node)

    countries = _uniq(
        [c for n in nodes for c in _node_countries(n)],
        limit=10,
    )
    products = _uniq(
        [n.name for n in by_type.get("product", [])]
        + [n.name for n in by_type.get("component", [])],
    )
    markets = _uniq([n.name for n in by_type.get("market", [])])
    suppliers = _uniq([n.name for n in by_type.get("supplier", [])])
    facilities = _uniq([n.name for n in by_type.get("facility", [])])
    lines = _uniq([n.name for n in by_type.get("production_line", [])])

    finance_filled, finance_values, _optional = _finance_snapshot(settings)
    purchase_curs = _uniq(
        [
            str(c).upper()
            for c in ((settings.purchase_currencies_json if settings else None) or [])
            if c
        ]
        + [n.name.upper() for n in by_type.get("currency", []) if n.name],
    )

    profile_ready = company.profile_status == "ready"
    status_label = "Контекст настроен" if profile_ready else "Нужно завершить настройку"
    setup_cta = "Изменить контекст" if profile_ready else "Продолжить настройку"

    tracking: list[TrackingCategoryOut] = []
    gaps: list[TrackingCategoryOut] = []

    if countries:
        tracking.append(
            TrackingCategoryOut(
                key="geo",
                title="Страны и регионы",
                values=countries[:6],
                explanation=(
                    f"{_join_human(countries)} — экспортные ограничения, логистика "
                    "и спрос на этих рынках."
                ),
            )
        )
    else:
        gaps.append(
            TrackingCategoryOut(
                key="geo",
                title="Страны и регионы",
                values=[],
                explanation="Добавьте географию — тогда Аспект отфильтрует сигналы по вашим рынкам.",
                filled=False,
                cta_label="Указать страны",
                cta_href=f"{_SETUP}?step=geo",
            )
        )

    if products:
        tracking.append(
            TrackingCategoryOut(
                key="products",
                title="Продукты и компоненты",
                values=products[:6],
                explanation=(
                    f"{_join_human(products)} — новости о поставках, компонентах "
                    "и производственных ограничениях становятся персональными."
                ),
            )
        )
    else:
        gaps.append(
            TrackingCategoryOut(
                key="products",
                title="Продукты и компоненты",
                values=[],
                explanation="Без продукта или критичного компонента сложно оценить риск остановки.",
                filled=False,
                cta_label="Добавить критичный компонент",
                cta_href=f"{_SETUP}?step=chain",
            )
        )

    if markets:
        tracking.append(
            TrackingCategoryOut(
                key="markets",
                title="Рынки присутствия",
                values=markets[:6],
                explanation=(
                    f"{_join_human(markets)} — спрос, импортные условия и отраслевые "
                    "изменения на этих рынках попадают в ленту «Для вас»."
                ),
            )
        )
    else:
        gaps.append(
            TrackingCategoryOut(
                key="markets",
                title="Рынки присутствия",
                values=[],
                explanation="Укажите рынки сбыта — Аспект свяжет с ними релевантные сигналы.",
                filled=False,
                cta_label="Указать рынки",
                cta_href=f"{_SETUP}?step=geo",
            )
        )

    if finance_filled or purchase_curs:
        values = purchase_curs[:]
        # Append non-currency finance snapshots (debt, float share, cash)
        for item in finance_values:
            if item.upper() not in {c.upper() for c in purchase_curs}:
                values.append(item)
        tracking.append(
            TrackingCategoryOut(
                key="finance",
                title="Валюты и финансы",
                values=_uniq(values, limit=6),
                explanation=(
                    "Ставка и валюта влияют на стоимость финансирования и платежи — "
                    "Аспект считает это по вашим параметрам."
                    if finance_filled
                    else "Валюты закупок помогают отслеживать курсовые и платёжные сигналы."
                ),
            )
        )
    else:
        gaps.append(
            TrackingCategoryOut(
                key="finance",
                title="Валюты и финансы",
                values=[],
                explanation="Для макро- и FX-сценариев нужны валюты и параметры финансирования.",
                filled=False,
                cta_label="Добавить финансовые параметры",
                cta_href=f"{_SETUP}?step=finance",
            )
        )

    if suppliers:
        tracking.append(
            TrackingCategoryOut(
                key="suppliers",
                title="Поставщики и цепочки",
                values=suppliers[:6],
                explanation=(
                    f"{_join_human(suppliers)} — сбои у поставщиков и логистические "
                    "ограничения оцениваются через вашу цепочку."
                ),
            )
        )
    else:
        gaps.append(
            TrackingCategoryOut(
                key="suppliers",
                title="Поставщики и цепочки",
                values=[],
                explanation="Добавьте поставщика — тогда ограничения экспорта свяжутся с вашей линией.",
                filled=False,
                cta_label="Проверить цепочку поставок",
                cta_href=f"{_SETUP}?step=chain",
            )
        )

    map_groups: list[MapGroupOut] = []
    supply_items = _uniq(suppliers + [n.name for n in by_type.get("component", [])])
    if supply_items:
        map_groups.append(
            MapGroupOut(
                key="supplies",
                title="Поставки",
                count=len(supply_items),
                items=supply_items[:4],
                explanation=(
                    "Через поставки Аспект связывает новости о странах, компонентах "
                    "и логистике с риском для вашей линии."
                ),
            )
        )
    production_items = _uniq(facilities + lines + [n.name for n in by_type.get("product", [])])
    if production_items:
        map_groups.append(
            MapGroupOut(
                key="production",
                title="Производство",
                count=len(production_items),
                items=production_items[:4],
                explanation=(
                    "Производственный контур показывает, какая площадка и линия "
                    "затронуты сигналом и какая доля выпуска под риском."
                ),
            )
        )
    if markets:
        map_groups.append(
            MapGroupOut(
                key="markets",
                title="Рынки",
                count=len(markets),
                items=markets[:4],
                explanation=(
                    "Рынки присутствия делают релевантными новости о спросе, "
                    "импорте и конкуренции именно там, где вы работаете."
                ),
            )
        )
    if finance_filled or purchase_curs:
        fin_items = purchase_curs[:] if purchase_curs else finance_values[:3]
        map_groups.append(
            MapGroupOut(
                key="finance",
                title="Финансы",
                count=len(fin_items) or 1,
                items=fin_items[:4] or ["Финансовый контекст"],
                explanation=(
                    "Финансовый контур переводит ставки и валюту в расчётные сценарии "
                    "давления на финансирование — без supply-chain метрик."
                ),
            )
        )

    # Coverage from real filled categories (transparent counts, no invented %).
    coverage_defs: list[tuple[str, str, bool, str, str | None, str | None]] = [
        (
            "industry",
            "Отрасль",
            bool(company.industry),
            _INDUSTRY_LABELS.get(company.industry or "", company.industry or "Отрасль указана")
            if company.industry
            else "Отрасль ещё не выбрана",
            None if company.industry else "Указать отрасль",
            None if company.industry else f"{_SETUP}?step=role",
        ),
        (
            "geo",
            "География",
            bool(countries),
            _join_human(countries) if countries else "Страны и регионы не заданы",
            None if countries else "Указать страны",
            None if countries else f"{_SETUP}?step=geo",
        ),
        (
            "products",
            "Продукты и компоненты",
            bool(products),
            _join_human(products) if products else "Нет продукта или критичного компонента",
            None if products else "Добавить критичный компонент",
            None if products else f"{_SETUP}?step=chain",
        ),
        (
            "markets",
            "Рынки",
            bool(markets),
            _join_human(markets) if markets else "Рынки присутствия не указаны",
            None if markets else "Указать рынки",
            None if markets else f"{_SETUP}?step=geo",
        ),
        (
            "chain",
            "Цепочка поставок",
            bool(suppliers and edges),
            (
                f"{len(suppliers)} поставщик(ов), {len(edges)} связей"
                if suppliers and edges
                else "Цепочка неполная — нет поставщика или связей"
            ),
            None if (suppliers and edges) else "Проверить цепочку поставок",
            None if (suppliers and edges) else f"{_SETUP}?step=chain",
        ),
        (
            "finance",
            "Финансы",
            finance_filled,
            (
                _join_human(finance_values or purchase_curs)
                if finance_filled
                else (
                    "Валюты есть, но не хватает параметров финансирования"
                    if purchase_curs
                    else "Финансовые параметры не заполнены"
                )
            ),
            None if finance_filled else "Добавить финансовые параметры",
            None if finance_filled else f"{_SETUP}?step=finance",
        ),
    ]

    coverage_blocks = [
        CoverageBlockOut(
            key=key,
            title=title,
            filled=filled,
            summary=summary,
            cta_label=cta_label,
            cta_href=cta_href,
        )
        for key, title, filled, summary, cta_label, cta_href in coverage_defs
    ]
    coverage_filled = sum(1 for b in coverage_blocks if b.filled)
    coverage_total = len(coverage_blocks)

    case_context = build_case_context_block(db, company=company, user=user)

    return CompanyContextOut(
        company_name=company.name,
        industry_label=_INDUSTRY_LABELS.get(company.industry or "") if company.industry else None,
        business_role=_business_role(nodes),
        size_label=_SIZE_LABELS.get(company.size_band or "") if company.size_band else None,
        hq_region=company.hq_region,
        profile_ready=profile_ready,
        status_label=status_label,
        setup_cta_label=setup_cta,
        setup_href=_SETUP if profile_ready else f"{_SETUP}?step=basics",
        is_demo=bool(company.is_demo),
        tracking=tracking,
        tracking_gaps=gaps,
        map_groups=map_groups,
        coverage_blocks=coverage_blocks,
        coverage_filled=coverage_filled,
        coverage_total=coverage_total,
        example=_example_for_company(db, company.id),
        case_context=case_context,
    )
