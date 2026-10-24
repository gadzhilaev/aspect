"""Explainable relevance: feature match vs dependency vs data sufficiency.

Does not replace assessment_state — that describes calculation readiness.
Relevance answers: why this event is (or is not) linked to this company profile.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal

from app.models import Company, CompanyNode, Event

CountryRole = Literal["supplier", "market"]
RelevanceLevel = Literal[
    "dependency_ready",
    "feature_match",
    "not_relevant",
]

_COUNTRY_ALIAS_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"china", "китай", "prc", "кнр", "китайская народная республика"}),
    frozenset({"russia", "россия", "rf", "рф", "russian federation"}),
    frozenset({"cis", "снг", "eaeu", "еаэс"}),
    frozenset({"usa", "us", "сша", "united states", "америка"}),
    frozenset({"eu", "ес", "europe", "европа", "european union"}),
)


def norm_token(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("ё", "е").split())


def expand_country_tokens(values: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for raw in values:
        token = norm_token(str(raw))
        if not token:
            continue
        out.add(token)
        for group in _COUNTRY_ALIAS_GROUPS:
            if token in group:
                out |= set(group)
    return out


def company_material_tokens(nodes: list[CompanyNode]) -> set[str]:
    tokens: set[str] = set()
    for node in nodes:
        if node.node_type not in {"component", "product"}:
            continue
        name = norm_token(node.name)
        if name:
            tokens.add(name)
        attrs = node.attributes_json or {}
        for key in ("materials", "material", "sku"):
            val = attrs.get(key)
            if isinstance(val, list):
                tokens |= {norm_token(str(v)) for v in val if str(v).strip()}
            elif isinstance(val, str) and val.strip():
                tokens.add(norm_token(val))
    return {t for t in tokens if t}


def company_currency_tokens(
    nodes: list[CompanyNode],
    purchase_currencies: Iterable[str] | None,
) -> set[str]:
    tokens: set[str] = set()
    for code in purchase_currencies or []:
        c = str(code).strip().upper()
        if c:
            tokens.add(c)
    for node in nodes:
        if node.node_type != "currency":
            continue
        name = (node.name or "").strip().upper()
        if name:
            tokens.add(name)
        attrs = node.attributes_json or {}
        code = attrs.get("code")
        if isinstance(code, str) and code.strip():
            tokens.add(code.strip().upper())
    return tokens


def materials_overlap(event_materials: Iterable[str], company_materials: set[str]) -> bool:
    event_tokens = {norm_token(str(m)) for m in event_materials if str(m).strip()}
    if not event_tokens or not company_materials:
        return False
    for et in event_tokens:
        for ct in company_materials:
            if et == ct or et in ct or ct in et:
                return True
    return False


def is_macro_fx_event(event: Event) -> bool:
    if (event.category or "").lower() == "macro":
        return True
    currencies = [str(c).strip() for c in (event.match_currencies_json or []) if str(c).strip()]
    materials = [str(m).strip() for m in (event.match_materials_json or []) if str(m).strip()]
    title = (event.title or "").lower()
    if any(k in title for k in ("ставк", "курс", "валют", "fx", "key rate")):
        return True
    return bool(currencies) and not materials


@dataclass
class RelevanceMatch:
    axis: str
    role: str | None
    event_value: str
    company_value: str
    node_id: str | None = None
    node_name: str | None = None
    node_type: str | None = None


@dataclass
class RelevanceAssessment:
    is_relevant: bool
    level: RelevanceLevel
    summary: str
    matched_features: list[RelevanceMatch] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    country_roles_considered: list[str] = field(default_factory=list)
    profile_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_relevant": self.is_relevant,
            "level": self.level,
            "summary": self.summary,
            "matched_features": [asdict(m) for m in self.matched_features],
            "missing_data": list(self.missing_data),
            "limitations": list(self.limitations),
            "country_roles_considered": list(self.country_roles_considered),
            "profile_fingerprint": self.profile_fingerprint,
        }


def profile_fingerprint(
    nodes: list[CompanyNode], purchase_currencies: Iterable[str] | None
) -> str:
    parts: list[str] = []
    for n in sorted(nodes, key=lambda x: x.id):
        share = "" if n.output_share_percent is None else f":{n.output_share_percent:g}"
        country = (n.country or "").strip()
        parts.append(
            f"{n.id}:{n.node_type}:{norm_token(n.name)}:{norm_token(country)}{share}"
        )
    ccy = ",".join(
        sorted(
            {
                str(c).strip().upper()
                for c in (purchase_currencies or [])
                if str(c).strip()
            }
        )
    )
    return "|".join(parts) + f"#ccy={ccy}"


def country_roles_for_event(event: Event) -> frozenset[CountryRole] | None:
    """Which geography roles may open the personalization gate.

    None → country axis unused (macro/FX uses currencies).
    """
    if is_macro_fx_event(event):
        return None
    cats = {norm_token(str(c)) for c in (event.match_categories_json or [])}
    category = norm_token(event.category or "")
    if (
        "export_control" in cats
        or category in {"geopolitics", "electronics"}
        or "export" in cats
    ):
        return frozenset({"supplier"})
    if category == "market" or "market" in cats or "import" in cats:
        return frozenset({"market"})
    return frozenset({"supplier", "market"})


def _collect_country_matches(
    event: Event,
    nodes: list[CompanyNode],
    *,
    allowed_roles: frozenset[CountryRole],
) -> list[RelevanceMatch]:
    event_countries = expand_country_tokens(event.match_countries_json or [])
    if not event_countries:
        return []
    hits: list[RelevanceMatch] = []
    for node in nodes:
        if node.node_type == "supplier" and "supplier" in allowed_roles:
            role: CountryRole = "supplier"
        elif node.node_type == "market" and "market" in allowed_roles:
            role = "market"
        else:
            continue
        node_tokens: set[str] = set()
        if node.country:
            node_tokens |= expand_country_tokens([node.country])
        node_tokens |= expand_country_tokens([node.name])
        attrs = node.attributes_json or {}
        node_tokens |= expand_country_tokens(attrs.get("countries") or [])
        if not (event_countries & node_tokens):
            continue
        hits.append(
            RelevanceMatch(
                axis="country",
                role=role,
                event_value=", ".join(sorted(str(x) for x in (event.match_countries_json or []))),
                company_value=node.country or node.name,
                node_id=node.id,
                node_name=node.name,
                node_type=node.node_type,
            )
        )
    return hits


def _collect_material_matches(event: Event, nodes: list[CompanyNode]) -> list[RelevanceMatch]:
    event_materials = event.match_materials_json or []
    if not event_materials:
        return []
    company_mats = company_material_tokens(nodes)
    if not materials_overlap(event_materials, company_mats):
        return []
    hits: list[RelevanceMatch] = []
    event_tokens = {norm_token(str(m)) for m in event_materials if str(m).strip()}
    for node in nodes:
        if node.node_type not in {"component", "product"}:
            continue
        tokens: set[str] = set()
        name = norm_token(node.name)
        if name:
            tokens.add(name)
        attrs = node.attributes_json or {}
        for key in ("materials", "material", "sku"):
            val = attrs.get(key)
            if isinstance(val, list):
                tokens |= {norm_token(str(v)) for v in val if str(v).strip()}
            elif isinstance(val, str) and val.strip():
                tokens.add(norm_token(val))
        if any(et == ct or et in ct or ct in et for et in event_tokens for ct in tokens):
            hits.append(
                RelevanceMatch(
                    axis="material",
                    role="component",
                    event_value=", ".join(str(m) for m in event_materials),
                    company_value=node.name,
                    node_id=node.id,
                    node_name=node.name,
                    node_type=node.node_type,
                )
            )
    return hits


def _collect_currency_matches(
    event: Event,
    nodes: list[CompanyNode],
    purchase_currencies: list[str] | None,
) -> list[RelevanceMatch]:
    event_ccy = {
        str(c).strip().upper() for c in (event.match_currencies_json or []) if str(c).strip()
    }
    if not event_ccy:
        return []
    company_ccy = company_currency_tokens(nodes, purchase_currencies)
    overlap = event_ccy & company_ccy
    if not overlap:
        return []
    return [
        RelevanceMatch(
            axis="currency",
            role="purchase",
            event_value=", ".join(sorted(event_ccy)),
            company_value=", ".join(sorted(overlap)),
        )
    ]


def _event_currencies(event: Event) -> set[str]:
    return {
        str(c).strip().upper() for c in (event.match_currencies_json or []) if str(c).strip()
    }


def _key_present(data: dict[str, Any], key: str) -> bool:
    if key not in data:
        return False
    val = data.get(key)
    return val is not None and val != ""


def _rate_finance_ready(optional_finance: dict[str, Any] | None) -> bool:
    data = optional_finance or {}
    return _key_present(data, "debt_amount") and _key_present(
        data, "floating_rate_share_percent"
    )


def _fx_finance_ready(optional_finance: dict[str, Any] | None) -> bool:
    data = optional_finance or {}
    if not all(
        _key_present(data, k)
        for k in (
            "fx_exposure_amount",
            "fx_exposure_currency",
            "fx_exposure_direction",
            "fx_quote_currency",
        )
    ):
        return False
    direction = str(data.get("fx_exposure_direction") or "").strip().lower()
    return direction in {"payment", "receipt"}


def _debt_currency(optional_finance: dict[str, Any] | None) -> str | None:
    data = optional_finance or {}
    for key in ("debt_amount_unit", "debt_currency", "currency"):
        raw = data.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip().upper()
    return None


def event_suggests_rate_track(event: Event) -> bool:
    """True for key/policy rate — not money-market quotes or FX swap «ставки».

    Bare token «ставк» (MIACR, RUONIA, валютный своп) must not open the rate
    finance track as if it were a ЦБ key-rate decision.
    """
    cats = {norm_token(str(c)) for c in (event.match_categories_json or [])}
    if cats & {
        "rates",
        "rate",
        "key_rate",
        "policy_rate",
        "ключевая ставка",
        "ключевой ставки",
        "ключевую ставку",
        "дкп",
        "monetary policy",
        "policy rate",
        "key rate",
    }:
        return True
    attrs = event.attributes_json if isinstance(event.attributes_json, dict) else {}
    if attrs.get("rate_decision_status") is not None:
        return True
    if attrs.get("rate_from") is not None or attrs.get("rate_to") is not None:
        return True
    if attrs.get("bank_route") == "policy_rate":
        return True

    blob = f"{event.title or ''} {event.summary or ''}".lower().replace("ё", "е")
    # Instrument / money-market noise: only policy-rate language overrides.
    noise = ("своп", "swap", "miacr", "ruonia", "вмененн")
    if any(n in blob for n in noise) and "ключев" not in blob and "дкп" not in blob:
        return False
    if "ключев" in blob and "ставк" in blob:
        return True
    if "key rate" in blob or "policy rate" in blob:
        return True
    if "ставк" in blob and any(
        k in blob for k in ("цб", "банк россии", "регулятор")
    ) and any(v in blob for v in ("решен", "сохран", "повыш", "сниж", "заседан")):
        return True
    return False


def event_suggests_fx_track(event: Event) -> bool:
    """True when the event carries an FX / currency-move signal."""
    attrs = event.attributes_json if isinstance(event.attributes_json, dict) else {}
    if attrs.get("fx_rate_decision") or attrs.get("fx_decision_status"):
        return True
    if attrs.get("fx_rate_decision_status"):
        return True
    blob = f"{event.title or ''} {event.summary or ''}".lower()
    if any(k in blob for k in ("курс", "валют", "fx ", " fx", "обменн")):
        return True
    cats = {norm_token(str(c)) for c in (event.match_categories_json or [])}
    if cats & {"fx", "currency", "валют", "курс"}:
        return True
    return False


def _finance_feature_match(
    event: Event,
    nodes: list[CompanyNode],
    *,
    purchase_currencies: list[str] | None,
    optional_finance: dict[str, Any] | None,
) -> RelevanceAssessment | None:
    """Macro/FX feature_match from rate/FX profile or purchase currencies.

    Purchase currencies are **not** required for every finance event: rate debt
    or typed FX exposure can open the gate when they align with the event.
    Incomplete finance and LOA/DEP-only profiles do not invent a match here
    (case_profile_match stays a separate feed basis).
    """
    if not is_macro_fx_event(event):
        return None
    finance = optional_finance if isinstance(optional_finance, dict) else {}
    event_ccy = _event_currencies(event)
    limitations = [
        "Финансовый feature_match — не company_calculated impact и не основание события."
    ]
    if not nodes:
        limitations.append(
            "Профиль без узлов Digital Twin: supply-chain влияние не считается."
        )

    # Rate track: debt + floating share; debt currency must fit event currencies if any.
    if event_suggests_rate_track(event) and _rate_finance_ready(finance):
        debt_ccy = _debt_currency(finance)
        if debt_ccy and (not event_ccy or debt_ccy in event_ccy):
            return RelevanceAssessment(
                is_relevant=True,
                level="feature_match",
                summary=(
                    f"Кредитный профиль ({debt_ccy}) пересекается с макро/ставковым событием. "
                    "Это персональный финансовый сигнал; расчёт денег требует основания "
                    "события или явного what-if."
                ),
                matched_features=[
                    RelevanceMatch(
                        axis="finance_rate",
                        role="debt",
                        event_value=", ".join(sorted(event_ccy)) or "rate",
                        company_value=debt_ccy,
                    )
                ],
                limitations=limitations,
                profile_fingerprint=None,  # filled by caller
            )

    # FX track: typed payment/receipt exposure currency ∩ event currencies.
    if _fx_finance_ready(finance):
        exp = str(finance.get("fx_exposure_currency") or "").strip().upper()
        direction = str(finance.get("fx_exposure_direction") or "").strip().lower()
        # Match when event lists the exposure currency, or FX-signal event with that pair.
        if exp and event_ccy and exp in event_ccy:
            return RelevanceAssessment(
                is_relevant=True,
                level="feature_match",
                summary=(
                    f"Валютная операция ({direction}, {exp}) пересекается с валютами события. "
                    "Это персональный финансовый сигнал; не цепочный company_calculated impact."
                ),
                matched_features=[
                    RelevanceMatch(
                        axis="finance_fx",
                        role=direction or "exposure",
                        event_value=", ".join(sorted(event_ccy)),
                        company_value=exp,
                    )
                ],
                limitations=limitations,
                profile_fingerprint=None,
            )
        if exp and event_suggests_fx_track(event) and not event_ccy:
            # FX narrative without listed currencies — still tie to exposure currency.
            return RelevanceAssessment(
                is_relevant=True,
                level="feature_match",
                summary=(
                    f"Валютная операция ({direction}, {exp}) сопоставлена с FX-событием. "
                    "В событии нет match_currencies — пересечение по типу сигнала, не по коду."
                ),
                matched_features=[
                    RelevanceMatch(
                        axis="finance_fx",
                        role=direction or "exposure",
                        event_value="fx",
                        company_value=exp,
                    )
                ],
                limitations=limitations
                + ["У события нет match_currencies — валютный код события не подтверждён."],
                profile_fingerprint=None,
            )

    currency_hits = _collect_currency_matches(event, nodes, purchase_currencies)
    if currency_hits:
        return RelevanceAssessment(
            is_relevant=True,
            level="feature_match",
            summary=(
                f"Совпадение по валюте закупок/обязательств ({currency_hits[0].company_value}). "
                "Для макро/FX это основание персонального сигнала; "
                "полный финансовый расчёт зависит от заполненности finance-полей."
            ),
            matched_features=currency_hits,
            limitations=limitations,
            profile_fingerprint=None,
        )
    return None


def analyze_event_company_relevance(
    event: Event,
    company: Company,
    nodes: list[CompanyNode],
    *,
    purchase_currencies: list[str] | None = None,
    optional_finance: dict[str, Any] | None = None,
) -> RelevanceAssessment:
    del company
    fp = profile_fingerprint(nodes, purchase_currencies)
    if not nodes:
        # Finance-only / empty twin: rate or FX context (or purchase currencies).
        fin = _finance_feature_match(
            event,
            [],
            purchase_currencies=purchase_currencies,
            optional_finance=optional_finance,
        )
        if fin is not None:
            fin.profile_fingerprint = fp
            return fin
        if is_macro_fx_event(event):
            missing: list[str] = []
            if not _rate_finance_ready(optional_finance) and not _fx_finance_ready(
                optional_finance
            ):
                missing.append("финансовый профиль (кредит и/или валютная операция)")
            missing.append("или валюта закупок из match_currencies события")
            return RelevanceAssessment(
                is_relevant=False,
                level="not_relevant",
                summary=(
                    "Нет пересечения макро/FX-события с финансовым профилем компании "
                    "(кредит/FX) и нет валютного пересечения по закупкам. "
                    "Узлы Digital Twin не заданы."
                ),
                missing_data=missing,
                limitations=[
                    "Конкурсный LOA/DEP без ручных сумм не открывает финансовый feature_match.",
                    "Без twin-узлов цепочная релевантность недоступна.",
                ],
                profile_fingerprint=fp,
            )
        return RelevanceAssessment(
            is_relevant=False,
            level="not_relevant",
            summary="Профиль компании пуст — сопоставить событие с Digital Twin нельзя.",
            missing_data=["узлы Digital Twin"],
            limitations=["Без профиля нельзя утверждать ни связь, ни её отсутствие."],
            profile_fingerprint=fp,
        )

    roles = country_roles_for_event(event)
    country_hits = (
        _collect_country_matches(event, nodes, allowed_roles=roles) if roles is not None else []
    )
    all_country = _collect_country_matches(
        event, nodes, allowed_roles=frozenset({"supplier", "market"})
    )
    material_hits = _collect_material_matches(event, nodes)
    currency_hits = _collect_currency_matches(event, nodes, purchase_currencies)
    ignored_market = [
        m
        for m in all_country
        if m.role == "market"
        and roles is not None
        and "market" not in roles
    ]

    if roles is not None:
        if country_hits:
            supplier_hits = [h for h in country_hits if h.role == "supplier"]
            market_hits = [h for h in country_hits if h.role == "market"]
            matched = list(country_hits) + list(material_hits)
            if supplier_hits:
                names = ", ".join(
                    sorted({h.node_name or h.company_value for h in supplier_hits})
                )
                summary = (
                    f"В профиле указан поставщик, связанный со страной события ({names}). "
                    "Совпадение по стране поставок — основание персональной релевантности; "
                    "конкретная цепочка к линии проверяется при расчёте влияния."
                )
                if material_hits:
                    comps = ", ".join(
                        sorted({h.node_name or h.company_value for h in material_hits})
                    )
                    summary += f" Также совпадают материалы/компоненты: {comps}."
                return RelevanceAssessment(
                    is_relevant=True,
                    level="dependency_ready",
                    summary=summary,
                    matched_features=matched,
                    country_roles_considered=sorted(roles),
                    profile_fingerprint=fp,
                )
            names = ", ".join(sorted({h.node_name or h.company_value for h in market_hits}))
            return RelevanceAssessment(
                is_relevant=True,
                level="dependency_ready",
                summary=(
                    f"Совпадение по рынку продаж ({names}). "
                    "Это связь с рынком сбыта, а не со страной поставок."
                ),
                matched_features=matched,
                country_roles_considered=sorted(roles),
                profile_fingerprint=fp,
            )

        limitations: list[str] = []
        missing: list[str] = []
        if ignored_market:
            limitations.append(
                "Рынок продаж с совпадающей страной не считается основанием "
                "для этого типа события (нужна страна поставок / роль supplier)."
            )
        if material_hits or currency_hits:
            limitations.append(
                "Совпадение материалов или валюты без страны нужной роли "
                "не открывает персональную карточку влияния для этого события."
            )
            missing.append("поставщик (или рынок — для market-событий) в стране события")
            detail_bits = []
            if material_hits:
                detail_bits.append(
                    "материалы/компоненты: "
                    + ", ".join(
                        sorted({h.node_name or "" for h in material_hits if h.node_name})
                    )
                )
            if currency_hits:
                detail_bits.append("валюта: " + currency_hits[0].company_value)
            summary = (
                "По текущему профилю прямая зависимость по стране нужной роли "
                "не установлена. "
                + (
                    "Есть частичные совпадения (" + "; ".join(detail_bits) + "). "
                    if detail_bits
                    else ""
                )
                + "Происхождение закупок поставщика за пределами профиля неизвестно — "
                "косвенная зависимость не утверждается."
            )
            return RelevanceAssessment(
                is_relevant=False,
                level="not_relevant",
                summary=summary,
                matched_features=list(material_hits) + list(currency_hits) + ignored_market,
                missing_data=missing,
                limitations=limitations,
                country_roles_considered=sorted(roles),
                profile_fingerprint=fp,
            )

        missing.append(
            "пересечение профиля со страной события в роли " + "/".join(sorted(roles))
        )
        limitations.append(
            "Отсутствие прямой связи в профиле не означает, что риска нет — "
            "только что модель не связала событие с доступными данными."
        )
        return RelevanceAssessment(
            is_relevant=False,
            level="not_relevant",
            summary=(
                "По текущему профилю прямая зависимость не установлена. "
                "Поставщик из страны события не указан; происхождение компонентов "
                "текущего поставщика в профиле не задано."
            ),
            matched_features=ignored_market,
            missing_data=missing,
            limitations=limitations,
            country_roles_considered=sorted(roles),
            profile_fingerprint=fp,
        )

    # Macro/FX (roles is None): rate/FX profile or purchase currencies — not LOA alone.
    fin = _finance_feature_match(
        event,
        nodes,
        purchase_currencies=purchase_currencies,
        optional_finance=optional_finance,
    )
    if fin is not None:
        fin.profile_fingerprint = fp
        return fin

    return RelevanceAssessment(
        is_relevant=False,
        level="not_relevant",
        summary=(
            "Нет пересечения макро/FX-события с финансовым профилем "
            "(кредит/FX) или валютами закупок компании."
        ),
        missing_data=[
            "финансовый профиль (кредит и/или валютная операция) "
            "или валюта закупок из match_currencies события"
        ],
        limitations=[
            "Макро/FX без rate/FX-контекста и без валютного пересечения "
            "не попадает в персональную twin-релевантность.",
            "Конкурсный LOA/DEP без ручных сумм — отдельное основание ленты "
            "(case_profile_match), не финансовый feature_match.",
        ],
        profile_fingerprint=fp,
    )
