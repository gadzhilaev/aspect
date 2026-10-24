"""FX scenario basis and money (stage 5.4).

Severity is never used as an FX rate proxy. Money requires explicit currencies,
quote convention, and observed or assumed rates. Rate (key-rate) formulas stay
in financial_simulator (5.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from app.core.config import get_settings
from app.models import Event

FxBasis = Literal["observed", "assumed", "none", "conflict"]
FxDirection = Literal["payment", "receipt"]

FINANCE_FX_MODEL_SUFFIX = "finance-fx-v1"
MONEY_QUANT = Decimal("0.01")
RATE_QUANT = Decimal("0.000001")

_TRUSTED_FX_STATUS = frozenset(
    {
        "observed",
        "market_observed",
        "decision_observed",
        "observed_fx",
    }
)

# Documented optional_finance / scenario keys for the next setup stage (not invented here).
FX_SETUP_FIELD_SPEC: dict[str, str] = {
    "fx_exposure_amount": "Сумма экспозиции (число, включая 0)",
    "fx_exposure_currency": "ISO-код валюты суммы (например CNY)",
    "fx_exposure_direction": "payment | receipt",
    "fx_exposure_period": "Опционально: период суммы (строка); иначе «Период не указан»",
    "fx_quote_currency": "Валюта расчёта / котировки (например RUB)",
    "fx_quote_convention": "Всегда quote_per_exposure: единиц quote за 1 exposure",
    "fx_rate_from": "Опционально в профиле; обычно из event с trusted status",
    "fx_rate_to": "Опционально в профиле",
}


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not d.is_finite():
        return None
    return d


def _money(d: Decimal) -> Decimal:
    return d.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _rate(d: Decimal) -> Decimal:
    return d.quantize(RATE_QUANT, rounding=ROUND_HALF_UP)


def _norm_ccy(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip().upper()
    if len(s) < 3:
        return None
    return s


def _positive_rate(d: Decimal | None) -> bool:
    return d is not None and d.is_finite() and d > 0


@dataclass
class FxChangeResolution:
    basis: FxBasis
    rate_from: Decimal | None = None
    rate_to: Decimal | None = None
    assumed_change_percent: Decimal | None = None
    exposure_currency: str | None = None
    quote_currency: str | None = None
    quote_convention: str = "quote_per_exposure"
    source: str = ""
    assumptions: list[str] = field(default_factory=list)
    unavailable_reasons: list[str] = field(default_factory=list)
    conflict_reasons: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "rate_from": str(self.rate_from) if self.rate_from is not None else None,
            "rate_to": str(self.rate_to) if self.rate_to is not None else None,
            "assumed_change_percent": (
                str(self.assumed_change_percent)
                if self.assumed_change_percent is not None
                else None
            ),
            "exposure_currency": self.exposure_currency,
            "quote_currency": self.quote_currency,
            "quote_convention": self.quote_convention,
            "source": self.source,
            "assumptions": list(self.assumptions),
            "unavailable_reasons": list(self.unavailable_reasons),
            "conflict_reasons": list(self.conflict_reasons),
            "limitations": list(self.limitations),
        }


@dataclass
class FxExposure:
    amount: Decimal
    currency: str
    direction: FxDirection
    period: str | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount": str(self.amount),
            "currency": self.currency,
            "direction": self.direction,
            "period": self.period,
            "source": self.source,
        }


def has_fx_exposure_context(optional_finance: dict[str, Any] | None) -> bool:
    """True when typed FX exposure fields are present (currency required).

    Legacy ``fx_purchase_volume`` alone is **not** enough.
    """
    data = optional_finance or {}
    amount = _dec(data.get("fx_exposure_amount"))
    ccy = _norm_ccy(data.get("fx_exposure_currency"))
    direction = str(data.get("fx_exposure_direction") or "").strip().lower()
    quote = _norm_ccy(data.get("fx_quote_currency"))
    if amount is None or ccy is None or quote is None:
        return False
    if direction not in {"payment", "receipt"}:
        return False
    return True


def resolve_fx_exposure(optional_finance: dict[str, Any] | None) -> FxExposure | None:
    data = optional_finance or {}
    amount = _dec(data.get("fx_exposure_amount"))
    ccy = _norm_ccy(data.get("fx_exposure_currency"))
    quote = _norm_ccy(data.get("fx_quote_currency"))
    direction = str(data.get("fx_exposure_direction") or "").strip().lower()
    if amount is None or ccy is None or quote is None:
        return None
    if direction not in {"payment", "receipt"}:
        return None
    period_raw = data.get("fx_exposure_period")
    period = period_raw.strip() if isinstance(period_raw, str) and period_raw.strip() else None
    # Same-currency exposure: still valid structurally; money Δ will be 0 if rates equal 1.
    return FxExposure(
        amount=amount,
        currency=ccy,
        direction=direction,  # type: ignore[arg-type]
        period=period,
        source="optional_finance.fx_exposure_*",
    )


def _fx_block(attrs: dict[str, Any]) -> dict[str, Any] | None:
    nested = attrs.get("fx_rate_decision")
    if isinstance(nested, dict):
        return nested
    status = attrs.get("fx_decision_status") or attrs.get("fx_rate_decision_status")
    if status in _TRUSTED_FX_STATUS:
        return {
            "status": status,
            "rate_from": attrs.get("fx_rate_from", attrs.get("rate_from")),
            "rate_to": attrs.get("fx_rate_to", attrs.get("rate_to")),
            "rate_delta": attrs.get("fx_rate_delta"),
            "exposure_currency": attrs.get("fx_exposure_currency")
            or attrs.get("exposure_currency"),
            "quote_currency": attrs.get("fx_quote_currency") or attrs.get("quote_currency"),
            "quote_convention": attrs.get("fx_quote_convention") or "quote_per_exposure",
        }
    return None


def resolve_observed_fx_change(
    event: Event,
    *,
    exposure_currency: str | None = None,
    quote_currency: str | None = None,
) -> FxChangeResolution:
    """Resolve observed FX rates. Bare fx_from/fx_to without trusted status → none."""
    attrs = event.attributes_json if isinstance(event.attributes_json, dict) else {}
    limitations = [
        "Observed рыночный курс — не доказанный курс исполнения договора компании",
        "Комиссии, хеджирование, налоги и даты исполнения не учтены (данных нет)",
    ]

    # Explicitly ignore untrusted bare keys / severity / bank forecast.
    if any(k in attrs for k in ("claimed_fx_delta", "bank_fx_forecast", "demo_story")):
        pass

    block = _fx_block(attrs)
    if block is None:
        # Numbers without status are not observed (incl. legacy fx_from/fx_to).
        if any(k in attrs for k in ("fx_from", "fx_to", "fx_rate_from", "fx_rate_to")):
            return FxChangeResolution(
                basis="none",
                source="fx_numbers_without_trusted_status",
                unavailable_reasons=[
                    "fx_from/fx_to без fx_decision_status / fx_rate_decision "
                    "не считаются observed"
                ],
                limitations=limitations,
            )
        return FxChangeResolution(
            basis="none",
            source="no_trusted_fx_decision",
            unavailable_reasons=[
                "Нет доверенного observed изменения курса "
                "(severity и прогноз банка не используются)"
            ],
            limitations=limitations,
        )

    status = str(block.get("status") or "").strip()
    if status not in _TRUSTED_FX_STATUS:
        return FxChangeResolution(
            basis="none",
            source="fx_untrusted_status",
            unavailable_reasons=[f"Статус FX {status!r} не в доверенном наборе"],
            limitations=limitations,
        )

    conv = str(block.get("quote_convention") or "quote_per_exposure").strip()
    if conv and conv != "quote_per_exposure":
        return FxChangeResolution(
            basis="conflict",
            source="fx_quote_convention",
            conflict_reasons=[
                f"Поддержана только котировка quote_per_exposure, получено {conv!r}"
            ],
            unavailable_reasons=["Неоднозначная котировка"],
            limitations=limitations,
        )

    exp_ccy = _norm_ccy(block.get("exposure_currency")) or exposure_currency
    quote_ccy = _norm_ccy(block.get("quote_currency")) or quote_currency
    rate_from = _dec(block.get("rate_from"))
    rate_to = _dec(block.get("rate_to"))
    delta_given = _dec(block.get("rate_delta") or block.get("delta"))

    if exp_ccy and quote_ccy and exposure_currency and quote_currency:
        if exp_ccy != exposure_currency or quote_ccy != quote_currency:
            return FxChangeResolution(
                basis="conflict",
                source="fx_pair_mismatch",
                exposure_currency=exp_ccy,
                quote_currency=quote_ccy,
                conflict_reasons=[
                    f"Пара события {exp_ccy}/{quote_ccy} не совпадает с экспозицией "
                    f"{exposure_currency}/{quote_currency}"
                ],
                unavailable_reasons=["Несовпадающая валютная пара"],
                limitations=limitations,
            )

    if rate_from is not None and not _positive_rate(rate_from):
        return FxChangeResolution(
            basis="conflict",
            source="fx_invalid_rate_from",
            conflict_reasons=["rate_from должен быть конечным и > 0"],
            unavailable_reasons=["Некорректный курс"],
            limitations=limitations,
        )
    if rate_to is not None and not _positive_rate(rate_to):
        return FxChangeResolution(
            basis="conflict",
            source="fx_invalid_rate_to",
            conflict_reasons=["rate_to должен быть конечным и > 0"],
            unavailable_reasons=["Некорректный курс"],
            limitations=limitations,
        )

    if rate_from is not None and rate_to is not None:
        computed = rate_to - rate_from
        if delta_given is not None and abs(computed - delta_given) > Decimal("1e-9"):
            return FxChangeResolution(
                basis="conflict",
                source="fx_from_to_vs_delta",
                rate_from=_rate(rate_from),
                rate_to=_rate(rate_to),
                exposure_currency=exp_ccy,
                quote_currency=quote_ccy,
                conflict_reasons=[
                    f"rate_to - rate_from = {computed}, но rate_delta = {delta_given}"
                ],
                unavailable_reasons=["Конфликт курсовых полей"],
                limitations=limitations,
            )
        return FxChangeResolution(
            basis="observed",
            rate_from=_rate(rate_from),
            rate_to=_rate(rate_to),
            exposure_currency=exp_ccy,
            quote_currency=quote_ccy,
            source="attributes.fx_rate_decision",
            assumptions=[
                "Котировка: единиц валюты расчёта (quote) за 1 единицу валюты экспозиции",
                "observed — изменение рыночного курса, не курс исполнения договора",
            ],
            limitations=limitations,
        )

    if rate_from is not None or rate_to is not None:
        return FxChangeResolution(
            basis="none",
            source="fx_incomplete_pair",
            unavailable_reasons=["Нужны оба rate_from и rate_to для observed FX"],
            limitations=limitations,
        )

    return FxChangeResolution(
        basis="none",
        source="fx_trusted_block_empty",
        unavailable_reasons=["Доверенный FX-блок без курсов"],
        limitations=limitations,
    )


def resolve_fx_change_for_scenario(
    event: Event,
    *,
    exposure: FxExposure | None,
    quote_currency: str | None = None,
    assumed_fx_change_percent: Decimal | float | str | None = None,
    profile_rate_from: Decimal | None = None,
    profile_rate_to: Decimal | None = None,
) -> FxChangeResolution:
    """Combine observed FX with optional explicit percent what-if."""
    exp_ccy = exposure.currency if exposure else None
    observed = resolve_observed_fx_change(
        event, exposure_currency=exp_ccy, quote_currency=quote_currency
    )

    # Profile rates only usable when both positive and pair already trusted elsewhere —
    # they never upgrade to observed without event status; may seed assumed path.
    assumed_pct = _dec(assumed_fx_change_percent)

    if observed.basis == "conflict":
        return observed

    if observed.basis == "observed":
        if assumed_pct is not None and observed.rate_from is not None:
            # Keep observed; caller may add separate what-if row.
            out = FxChangeResolution(
                basis="observed",
                rate_from=observed.rate_from,
                rate_to=observed.rate_to,
                assumed_change_percent=assumed_pct,
                exposure_currency=observed.exposure_currency or exp_ccy,
                quote_currency=observed.quote_currency,
                source=observed.source,
                assumptions=[
                    *observed.assumptions,
                    f"Отдельно задан assumed_fx_change_percent={assumed_pct}",
                    "Observed курсы не перезаписываются допущением",
                ],
                unavailable_reasons=list(observed.unavailable_reasons),
                limitations=list(observed.limitations),
            )
            return out
        return observed

    # none → try assumed
    if assumed_pct is not None:
        base = observed.rate_from or profile_rate_from
        if base is not None and _positive_rate(base):
            rate_to = _rate(base * (Decimal("1") + assumed_pct / Decimal("100")))
            if not _positive_rate(rate_to):
                return FxChangeResolution(
                    basis="conflict",
                    source="assumed_fx_non_positive_to",
                    conflict_reasons=["Расчётный rate_to неположителен"],
                    unavailable_reasons=["Некорректный what-if курс"],
                    limitations=list(observed.limitations),
                )
            return FxChangeResolution(
                basis="assumed",
                rate_from=_rate(base),
                rate_to=rate_to,
                assumed_change_percent=assumed_pct,
                exposure_currency=exp_ccy,
                quote_currency=observed.quote_currency,
                source="explicit_assumed_fx_change_percent",
                assumptions=[
                    f"What-if: курс × (1 + {assumed_pct}/100)",
                    "Допущение сценария, не факт новости и не прогноз банка",
                    "Котировка: quote за 1 exposure",
                ],
                unavailable_reasons=list(observed.unavailable_reasons),
                limitations=list(observed.limitations),
            )
        # Percent without base rate: qualitative only — no money
        return FxChangeResolution(
            basis="assumed",
            rate_from=None,
            rate_to=None,
            assumed_change_percent=assumed_pct,
            exposure_currency=exp_ccy,
            source="assumed_percent_without_base_rate",
            assumptions=[
                f"What-if процентного изменения курса {assumed_pct}% без исходного курса",
                "Рублёвый/quote эффект из суммы в инвалюте недоступен без rate_from",
            ],
            unavailable_reasons=[
                "Нет исходного курса для перевода what-if % в денежный эффект"
            ],
            limitations=list(observed.limitations),
        )

    # Profile from/to alone without trusted event status are not observed.
    if profile_rate_from is not None or profile_rate_to is not None:
        return FxChangeResolution(
            basis="none",
            source="profile_rates_untrusted_as_observed",
            unavailable_reasons=[
                "Курсы в профиле без доверенного event status не дают observed FX"
            ],
            limitations=list(observed.limitations),
        )

    return observed


def compute_fx_value_change(
    *,
    exposure: FxExposure,
    rate_from: Decimal,
    rate_to: Decimal,
    quote_currency: str,
) -> dict[str, Any]:
    """baseline = V×R_from; scenario = V×R_to; change = V×(R_to−R_from)."""
    if not _positive_rate(rate_from) or not _positive_rate(rate_to):
        raise ValueError("rates must be finite and > 0")
    # Same currency pair: if exposure currency == quote and rates are 1, change is 0.
    baseline = _money(exposure.amount * rate_from)
    scenario = _money(exposure.amount * rate_to)
    change = _money(exposure.amount * (rate_to - rate_from))

    if exposure.direction == "payment":
        if change > 0:
            meaning = "payment_cost_increase"
            meaning_label = "Рост стоимости платежа"
        elif change < 0:
            meaning = "payment_cost_decrease"
            meaning_label = "Снижение стоимости платежа"
        else:
            meaning = "payment_cost_unchanged"
            meaning_label = "Стоимость платежа без изменения"
    else:
        if change > 0:
            meaning = "receipt_equivalent_increase"
            meaning_label = "Рост эквивалента поступления"
        elif change < 0:
            meaning = "receipt_equivalent_decrease"
            meaning_label = "Снижение эквивалента поступления"
        else:
            meaning = "receipt_equivalent_unchanged"
            meaning_label = "Эквивалент поступления без изменения"

    return {
        "baseline_value": str(baseline),
        "scenario_value": str(scenario),
        "value_change": str(change),
        "value_change_decimal": change,
        "result_currency": quote_currency,
        "meaning": meaning,
        "meaning_label": meaning_label,
        "rounding": "ROUND_HALF_UP to 0.01",
    }


def simulate_fx_scenarios(
    *,
    event: Event,
    optional_finance: dict[str, Any],
    assumed_fx_change_percent: float | str | Decimal | None = None,
) -> dict[str, Any]:
    """Build FX scenarios or an explicit unavailable payload. No severity input."""
    settings = get_settings()
    model_version = f"{settings.simulator_model_version}-{FINANCE_FX_MODEL_SUFFIX}"
    computed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Legacy volume without currency must not become money.
    legacy_vol = optional_finance.get("fx_purchase_volume")
    exposure = resolve_fx_exposure(optional_finance)
    if exposure is None:
        reasons = [
            "Нужны fx_exposure_amount, fx_exposure_currency, "
            "fx_exposure_direction, fx_quote_currency"
        ]
        if legacy_vol is not None and legacy_vol != "":
            reasons.append(
                "Устаревший fx_purchase_volume без валюты/единицы не используется "
                "как валютная сумма"
            )
        return {
            "source": "financial_calculation",
            "track": "fx",
            "status": "unavailable",
            "type": "missing_data",
            "model_version": model_version,
            "computed_at": computed_at,
            "is_estimate": True,
            "labels": ["estimate"],
            "message": "Недостаточно данных для FX-расчёта",
            "fields": list(FX_SETUP_FIELD_SPEC.keys()),
            "parameters": {
                "fx_change": {
                    "basis": "none",
                    "unavailable_reasons": reasons,
                },
                "fx_setup_field_spec": FX_SETUP_FIELD_SPEC,
                "model_version": model_version,
                "severity_used_as_fx_rate": False,
            },
            "scenarios": [],
        }

    quote_ccy = _norm_ccy(optional_finance.get("fx_quote_currency")) or "UNSPECIFIED"
    profile_from = _dec(optional_finance.get("fx_rate_from"))
    profile_to = _dec(optional_finance.get("fx_rate_to"))

    # Same-currency calculation: no FX move — money Δ is zero when rates are 1/1.
    same_ccy = exposure.currency == quote_ccy

    fx = resolve_fx_change_for_scenario(
        event,
        exposure=exposure,
        quote_currency=quote_ccy,
        assumed_fx_change_percent=assumed_fx_change_percent,
        profile_rate_from=profile_from,
        profile_rate_to=profile_to,
    )
    if fx.quote_currency is None:
        fx.quote_currency = quote_ccy
    if fx.exposure_currency is None:
        fx.exposure_currency = exposure.currency

    if (
        fx.basis != "conflict"
        and fx.exposure_currency
        and fx.quote_currency
        and (
            fx.exposure_currency != exposure.currency
            or fx.quote_currency != quote_ccy
        )
    ):
        fx = FxChangeResolution(
            basis="conflict",
            source="fx_pair_mismatch_finance",
            conflict_reasons=["Валютная пара события не совпадает с экспозицией профиля"],
            unavailable_reasons=["Несовпадающая валютная пара"],
            limitations=list(fx.limitations),
        )

    if same_ccy and fx.basis in {"observed", "assumed"} and fx.rate_from and fx.rate_to:
        # Explicit same-currency: treat as no FX conversion effect (rates must be 1).
        if fx.rate_from != Decimal("1") or fx.rate_to != Decimal("1"):
            fx = FxChangeResolution(
                basis="conflict",
                source="same_currency_non_unit_rate",
                conflict_reasons=[
                    "При расчёте в той же валюте ожидаются курсы 1→1; иначе конфликт"
                ],
                unavailable_reasons=["Некорректные курсы для одновалютного расчёта"],
                limitations=list(fx.limitations),
            )
        else:
            fx.assumptions = [
                *fx.assumptions,
                "Экспозиция и расчёт в одной валюте — валютное изменение отсутствует",
            ]

    base_params: dict[str, Any] = {
        "track": "fx",
        "fx_exposure": exposure.to_dict(),
        "fx_change": fx.to_dict(),
        "fx_setup_field_spec": FX_SETUP_FIELD_SPEC,
        "model_version": model_version,
        "severity_used_as_fx_rate": False,
        # Explicitly unused legacy:
        "fx_purchase_volume_ignored": legacy_vol is not None and legacy_vol != "",
    }

    if fx.basis == "conflict":
        return {
            "source": "financial_calculation",
            "track": "fx",
            "status": "unavailable",
            "type": "missing_data",
            "model_version": model_version,
            "computed_at": computed_at,
            "message": "Исходные данные о курсе противоречат друг другу",
            "fields": ["fx_change"],
            "parameters": base_params,
            "scenarios": [],
            "is_estimate": True,
            "labels": ["estimate"],
        }

    can_money = (
        fx.rate_from is not None
        and fx.rate_to is not None
        and _positive_rate(fx.rate_from)
        and _positive_rate(fx.rate_to)
    )

    if fx.basis == "none" or (fx.basis == "assumed" and not can_money):
        msg = (
            "What-if процента без исходного курса: рублёвый эффект недоступен"
            if fx.basis == "assumed" and fx.assumed_change_percent is not None
            else "Недостаточно данных об изменении курса (severity не заменяет курс)"
        )
        return {
            "source": "financial_calculation",
            "track": "fx",
            "status": "unavailable",
            "type": "missing_data",
            "model_version": model_version,
            "computed_at": computed_at,
            "message": msg,
            "fields": ["fx_rate_observed_or_assumed"],
            "parameters": base_params,
            "scenarios": [],
            "is_estimate": True,
            "labels": ["estimate"],
            # Qualitative assumed percent may be echoed without money:
            "qualitative": (
                {
                    "assumed_fx_change_percent": str(fx.assumed_change_percent),
                    "note": "Процентное допущение без денежного эффекта",
                }
                if fx.assumed_change_percent is not None and not can_money
                else None
            ),
        }

    assert fx.rate_from is not None and fx.rate_to is not None
    calc = compute_fx_value_change(
        exposure=exposure,
        rate_from=fx.rate_from,
        rate_to=fx.rate_to,
        quote_currency=quote_ccy,
    )
    period_label = exposure.period or "Период не указан"
    limitations = list(fx.limitations) + [
        "Условная чувствительность к курсу, не фактический PnL договора",
        "Не учтены комиссии, хеджирование, налоги, даты исполнения",
    ]

    def _row(
        *,
        kind: str,
        label: str,
        action_id: str | None,
        basis: FxBasis,
        rate_from: Decimal,
        rate_to: Decimal,
        calc_row: dict[str, Any],
        assumptions: list[str],
    ) -> dict[str, Any]:
        return {
            "kind": kind,
            "track": "fx",
            "label": label,
            "action_id": action_id,
            "fx_change_basis": basis,
            "rate_change_basis": None,  # not a rate track
            "fx_exposure_amount": str(exposure.amount),
            "fx_exposure_currency": exposure.currency,
            "fx_exposure_direction": exposure.direction,
            "fx_quote_currency": quote_ccy,
            "fx_quote_convention": "quote_per_exposure",
            "fx_rate_from": str(rate_from),
            "fx_rate_to": str(rate_to),
            "fx_baseline_value": calc_row["baseline_value"],
            "fx_scenario_value": calc_row["scenario_value"],
            "fx_value_change": calc_row["value_change"],
            "fx_value_change_meaning": calc_row["meaning"],
            "fx_value_change_meaning_label": calc_row["meaning_label"],
            "fx_result_currency": calc_row["result_currency"],
            "fx_period": exposure.period,
            "fx_period_label": period_label,
            "extra_annual_cost": None,
            "annual_rate_sensitivity": None,
            "near_term_pressure": None,
            "near_term_pressure_status": "unavailable_not_applicable_to_fx",
            "fx_exposure_index": None,
            "funding_pressure_percent": None,
            "assumptions": assumptions,
            "limitations": limitations,
            "labels": ["estimate"],
            "is_estimate": True,
        }

    baseline = _row(
        kind="baseline",
        label="FX: без действий",
        action_id=None,
        basis=fx.basis if fx.basis in {"observed", "assumed"} else "assumed",
        rate_from=fx.rate_from,
        rate_to=fx.rate_to,
        calc_row=calc,
        assumptions=[*fx.assumptions, "Оценка, не финансовая гарантия"],
    )

    scenarios: list[dict[str, Any]] = [baseline]

    # Separate what-if when assumed percent differs from observed path.
    if (
        fx.basis == "observed"
        and fx.assumed_change_percent is not None
        and fx.rate_from is not None
    ):
        a_to = _rate(
            fx.rate_from
            * (Decimal("1") + fx.assumed_change_percent / Decimal("100"))
        )
        if _positive_rate(a_to):
            a_calc = compute_fx_value_change(
                exposure=exposure,
                rate_from=fx.rate_from,
                rate_to=a_to,
                quote_currency=quote_ccy,
            )
            scenarios.append(
                _row(
                    kind="alternative",
                    label=f"What-if FX: курс {fx.assumed_change_percent:+g}%",
                    action_id="assumed_fx_shock",
                    basis="assumed",
                    rate_from=fx.rate_from,
                    rate_to=a_to,
                    calc_row=a_calc,
                    assumptions=[
                        f"Явное допущение assumed_fx_change_percent={fx.assumed_change_percent}",
                        "Observed курсы сохранены отдельно",
                        "Оценка, не финансовая гарантия",
                    ],
                )
            )

    return {
        "source": "financial_calculation",
        "track": "fx",
        "status": "ok",
        "model_version": model_version,
        "computed_at": computed_at,
        "is_estimate": True,
        "labels": ["estimate"],
        "parameters": base_params,
        "scenarios": scenarios,
    }


def legacy_fx_basis_from_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    params = parameters or {}
    if isinstance(params.get("fx_change"), dict):
        return dict(params["fx_change"])
    # Old severity FX mix left near_term/fx index — never call observed.
    if params.get("shock_proxy_pp") is not None or params.get("fx_purchase_volume") is not None:
        return {
            "basis": "assumed",
            "legacy": True,
            "source": "legacy_fx_or_severity_proxy",
            "assumptions": [
                "Legacy FX/severity proxy; не интерпретировать как observed курс"
            ],
            "unavailable_reasons": ["Основание FX до этапа 5.4 не типизировано"],
        }
    return {
        "basis": "none",
        "legacy": True,
        "source": "legacy_fx_missing",
        "unavailable_reasons": ["Нет полей fx_change"],
    }
