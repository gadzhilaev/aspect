"""Server-side validation and PATCH merge for optional finance (stages 5.4–5.5).

Empty / omitted keys are unknown. Explicit null/"" clears knowledge.
Numeric 0 is a known zero. Does not invent defaults from contest payments or FTS.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.errors import AppError

_FX_DIRECTIONS = frozenset({"payment", "receipt"})

# Keys managed by finance setup / API merge (others pass through unchanged).
MANAGED_FINANCE_KEYS = frozenset(
    {
        "debt_amount",
        "debt_amount_unit",
        "debt_currency",
        "floating_rate_share_percent",
        "near_term_payments_90d",
        "fx_purchase_volume",
        "cash_reserve_days",
        "fx_exposure_amount",
        "fx_exposure_currency",
        "fx_exposure_direction",
        "fx_exposure_period",
        "fx_quote_currency",
        "fx_quote_convention",
        "fx_rate_from",
        "fx_rate_to",
    }
)


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise AppError(
            "VALIDATION_ERROR",
            "Булево значение недопустимо для денежного/курсового поля",
            422,
        )
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AppError(
            "VALIDATION_ERROR",
            f"Некорректное число: {value!r}",
            422,
        ) from exc
    if not d.is_finite():
        raise AppError(
            "VALIDATION_ERROR",
            "NaN/Infinity недопустимы для денежных и курсовых полей",
            422,
        )
    return d


def _is_clear(value: Any) -> bool:
    """Explicit clear of knowledge (not the same as known zero)."""
    return value is None or value == ""


def _norm_ccy(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip().upper()
    return s or None


def merge_optional_finance(
    existing: dict[str, Any] | None,
    patch: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge PATCH into stored optional_finance.

    - Key absent in patch → keep previous value.
    - Key present with null/"" → remove knowledge (do not write 0).
    - Key present with value → set (0 stays 0).

    If the FX currency pair changes and the patch does **not** explicitly set
    ``fx_rate_from`` / ``fx_rate_to``, drop stored rates so clients without the
    web-form guard (e.g. Flutter) cannot reuse a rate from the previous pair.
    """
    before = dict(existing or {})
    patch = patch or {}
    out = dict(before)
    for key, value in patch.items():
        if _is_clear(value):
            out.pop(key, None)
        else:
            out[key] = value

    old_pair = (
        _norm_ccy(before.get("fx_exposure_currency")),
        _norm_ccy(before.get("fx_quote_currency")),
    )
    new_pair = (
        _norm_ccy(out.get("fx_exposure_currency")),
        _norm_ccy(out.get("fx_quote_currency")),
    )
    pair_changed = old_pair != new_pair and any(new_pair)
    if pair_changed:
        if "fx_rate_from" not in patch:
            out.pop("fx_rate_from", None)
        if "fx_rate_to" not in patch:
            out.pop("fx_rate_to", None)
    return out


def validate_optional_finance_fx(optional_finance: dict[str, Any] | None) -> dict[str, Any]:
    """Validate typed FX and rate keys if present; leave unknown keys untouched.

    Returns a copy. Raises AppError on conflict/invalid values.
    """
    data = dict(optional_finance or {})

    # --- Rate / debt ---
    if "debt_amount" in data and not _is_clear(data.get("debt_amount")):
        amount = _dec(data.get("debt_amount"))
        assert amount is not None
        if amount < 0:
            raise AppError(
                "VALIDATION_ERROR",
                "debt_amount не может быть отрицательным",
                422,
                details=[{"field": "debt_amount", "reason": "non_negative"}],
            )
        data["debt_amount"] = float(amount)

    for unit_key in ("debt_amount_unit", "debt_currency"):
        raw = data.get(unit_key)
        if raw is None or raw == "":
            continue
        if not isinstance(raw, str) or not raw.strip():
            raise AppError(
                "VALIDATION_ERROR",
                f"{unit_key} должен быть строкой ISO",
                422,
            )
        data[unit_key] = raw.strip().upper()

    if "floating_rate_share_percent" in data and not _is_clear(
        data.get("floating_rate_share_percent")
    ):
        share = _dec(data.get("floating_rate_share_percent"))
        assert share is not None
        if share < 0 or share > 100:
            raise AppError(
                "VALIDATION_ERROR",
                "floating_rate_share_percent: 0…100",
                422,
                details=[{"field": "floating_rate_share_percent", "reason": "range"}],
            )
        data["floating_rate_share_percent"] = float(share)

    for liq_key in ("near_term_payments_90d", "fx_purchase_volume", "cash_reserve_days"):
        if liq_key not in data or _is_clear(data.get(liq_key)):
            continue
        n = _dec(data.get(liq_key))
        assert n is not None
        if n < 0:
            raise AppError(
                "VALIDATION_ERROR",
                f"{liq_key} не может быть отрицательным",
                422,
                details=[{"field": liq_key, "reason": "non_negative"}],
            )
        data[liq_key] = float(n)

    # --- Typed FX ---
    amount_raw = data.get("fx_exposure_amount")
    ccy = data.get("fx_exposure_currency")
    direction = data.get("fx_exposure_direction")
    quote = data.get("fx_quote_currency")
    conv = data.get("fx_quote_convention")
    rate_from = data.get("fx_rate_from")
    rate_to = data.get("fx_rate_to")

    typed_structural = (amount_raw, ccy, direction, quote)
    typed_any = any(v is not None and v != "" for v in (*typed_structural, rate_from, rate_to))
    if not typed_any:
        return data

    missing = [
        k
        for k, v in (
            ("fx_exposure_amount", amount_raw),
            ("fx_exposure_currency", ccy),
            ("fx_exposure_direction", direction),
            ("fx_quote_currency", quote),
        )
        if v is None or v == ""
    ]
    if missing and any(v is not None and v != "" for v in typed_structural):
        raise AppError(
            "VALIDATION_ERROR",
            "Неполный FX-блок: нужны amount, currency, direction, quote_currency",
            422,
            details=[{"field": f, "reason": "required_with_fx_block"} for f in missing],
        )

    if amount_raw is not None and amount_raw != "":
        amount = _dec(amount_raw)
        assert amount is not None
        if amount < 0:
            raise AppError(
                "VALIDATION_ERROR",
                "fx_exposure_amount не может быть отрицательным",
                422,
                details=[{"field": "fx_exposure_amount", "reason": "non_negative"}],
            )
        data["fx_exposure_amount"] = float(amount)

    if isinstance(ccy, str) and ccy.strip():
        data["fx_exposure_currency"] = ccy.strip().upper()
    elif ccy is not None and ccy != "":
        raise AppError(
            "VALIDATION_ERROR",
            "fx_exposure_currency должен быть строкой ISO",
            422,
        )

    if direction is not None and direction != "":
        d = str(direction).strip().lower()
        if d not in _FX_DIRECTIONS:
            raise AppError(
                "VALIDATION_ERROR",
                "fx_exposure_direction: payment | receipt",
                422,
                details=[{"field": "fx_exposure_direction", "reason": "enum"}],
            )
        data["fx_exposure_direction"] = d

    if isinstance(quote, str) and quote.strip():
        data["fx_quote_currency"] = quote.strip().upper()
    elif quote is not None and quote != "":
        raise AppError(
            "VALIDATION_ERROR",
            "fx_quote_currency должен быть строкой ISO",
            422,
        )

    if conv is not None and conv != "":
        if str(conv).strip() != "quote_per_exposure":
            raise AppError(
                "VALIDATION_ERROR",
                "fx_quote_convention поддерживается только quote_per_exposure",
                422,
            )
        data["fx_quote_convention"] = "quote_per_exposure"
    elif all(
        data.get(k) not in (None, "")
        for k in (
            "fx_exposure_amount",
            "fx_exposure_currency",
            "fx_exposure_direction",
            "fx_quote_currency",
        )
    ):
        data["fx_quote_convention"] = "quote_per_exposure"

    for key in ("fx_rate_from", "fx_rate_to"):
        raw = data.get(key)
        if raw is None or raw == "":
            continue
        r = _dec(raw)
        assert r is not None
        if r <= 0:
            raise AppError(
                "VALIDATION_ERROR",
                f"{key} должен быть конечным и > 0",
                422,
                details=[{"field": key, "reason": "positive"}],
            )
        data[key] = float(r)

    period = data.get("fx_exposure_period")
    if period is not None and period != "" and not isinstance(period, str):
        raise AppError(
            "VALIDATION_ERROR",
            "fx_exposure_period должен быть строкой",
            422,
        )

    return data
