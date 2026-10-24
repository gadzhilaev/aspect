"""Reusable value parsers for case CSV → future importer.

Statuses: missing | valid | invalid. Never coerce unknown flags to false.
Money uses Decimal only; must fit NUMERIC(20,1) without rounding.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

# PostgreSQL NUMERIC(20,1): up to 19 digits left of decimal, 1 to the right.
MONEY_PRECISION = 20
MONEY_SCALE = 1
MONEY_MAX_INT_DIGITS = MONEY_PRECISION - MONEY_SCALE  # 19

_UID_RE = re.compile(r"^U_\d+$")
_FID_RE = re.compile(r"^F_\d+$")
_MONEY_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_PAY_CNT_RE = re.compile(r"^\d+$")

# Known bank flag encodings from the competition files.
_BOOL_TRUE = frozenset({"1", "1.0"})
_BOOL_FALSE = frozenset({"0", "0.0"})


class ParseStatus(str, Enum):
    MISSING = "missing"
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class ParseResult:
    status: ParseStatus
    raw: str
    value: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is ParseStatus.VALID


def _as_raw(value: object | None) -> str:
    if value is None:
        return ""
    return str(value)


def parse_external_uid(value: object | None) -> ParseResult:
    raw = _as_raw(value).strip()
    if raw == "":
        return ParseResult(ParseStatus.MISSING, raw, error="empty_uid")
    if not _UID_RE.fullmatch(raw):
        return ParseResult(ParseStatus.INVALID, raw, error="uid_format")
    return ParseResult(ParseStatus.VALID, raw, value=raw)


def parse_external_fid(value: object | None) -> ParseResult:
    raw = _as_raw(value).strip()
    if raw == "":
        return ParseResult(ParseStatus.MISSING, raw, error="empty_fid")
    if not _FID_RE.fullmatch(raw):
        return ParseResult(ParseStatus.INVALID, raw, error="fid_format")
    return ParseResult(ParseStatus.VALID, raw, value=raw)


def parse_group_id(value: object | None) -> ParseResult:
    raw = _as_raw(value).strip()
    if raw == "":
        return ParseResult(ParseStatus.MISSING, raw, error="empty_group_id")
    # Source uses opaque numeric-looking ids; accept non-empty tokens without whitespace.
    if any(ch.isspace() for ch in raw):
        return ParseResult(ParseStatus.INVALID, raw, error="group_id_whitespace")
    return ParseResult(ParseStatus.VALID, raw, value=raw)


def parse_bool_flag(value: object | None) -> ParseResult:
    """Parse CL_PRODUCT_* / NEGATIVEMARK / FTS_FLAG style values.

    Unknown tokens → invalid (not false). Empty → missing.
    """
    raw = _as_raw(value).strip()
    if raw == "":
        return ParseResult(ParseStatus.MISSING, raw, error="empty_flag")
    if raw in _BOOL_TRUE:
        return ParseResult(ParseStatus.VALID, raw, value=True)
    if raw in _BOOL_FALSE:
        return ParseResult(ParseStatus.VALID, raw, value=False)
    return ParseResult(ParseStatus.INVALID, raw, error="unknown_flag")


def parse_money_numeric_20_1(value: object | None) -> ParseResult:
    """Parse REVENUE_COMPANY / PAY_AMT for exact NUMERIC(20,1) storage."""
    # Reject binary floats up front (no silent coercion from float).
    if isinstance(value, float):
        return ParseResult(
            ParseStatus.INVALID,
            _as_raw(value),
            error="nan_or_infinity"
            if math.isnan(value) or math.isinf(value)
            else "float_not_allowed",
        )

    raw = _as_raw(value).strip()
    if raw == "":
        return ParseResult(ParseStatus.MISSING, raw, error="empty_money")

    lowered = raw.casefold()
    if lowered in {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
        return ParseResult(ParseStatus.INVALID, raw, error="nan_or_infinity")

    if not _MONEY_RE.fullmatch(raw):
        return ParseResult(ParseStatus.INVALID, raw, error="invalid_format")

    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        return ParseResult(ParseStatus.INVALID, raw, error="invalid_format")

    if not amount.is_finite():
        return ParseResult(ParseStatus.INVALID, raw, error="nan_or_infinity")

    sign, digits, exponent = amount.as_tuple()
    # Normalize exponent: Decimal('1000.0') → digits=(1,0,0,0,0), exp=-1
    if exponent > 0:
        # 1E+2 style should not appear after regex, but guard overflow path.
        int_digits = len(digits) + exponent
        frac_digits = 0
    elif exponent == 0:
        int_digits = len(digits)
        frac_digits = 0
    else:
        frac_digits = -exponent
        int_digits = max(len(digits) - frac_digits, 0)

    if frac_digits > MONEY_SCALE:
        return ParseResult(ParseStatus.INVALID, raw, error="too_many_fraction_digits")

    if int_digits > MONEY_MAX_INT_DIGITS:
        return ParseResult(ParseStatus.INVALID, raw, error="overflow")

    # Exact fit into scale 1: quantize must not round.
    try:
        quantized = amount.quantize(Decimal("0.1"))
    except InvalidOperation:
        return ParseResult(ParseStatus.INVALID, raw, error="overflow")

    if quantized != amount:
        return ParseResult(ParseStatus.INVALID, raw, error="would_round")

    return ParseResult(ParseStatus.VALID, raw, value=quantized)


def parse_pay_cnt(value: object | None) -> ParseResult:
    """PAY_CNT in source is a non-negative integer string (no fractional part observed)."""
    raw = _as_raw(value).strip()
    if raw == "":
        return ParseResult(ParseStatus.MISSING, raw, error="empty_pay_cnt")
    if not _PAY_CNT_RE.fullmatch(raw):
        # Allow trailing .0 only if exactly integer (source may vary in fixtures).
        if re.fullmatch(r"\d+\.0", raw):
            raw_int = raw[:-2]
            return ParseResult(ParseStatus.VALID, raw, value=int(raw_int))
        return ParseResult(ParseStatus.INVALID, raw, error="pay_cnt_format")
    try:
        n = int(raw)
    except ValueError:
        return ParseResult(ParseStatus.INVALID, raw, error="pay_cnt_format")
    if n < 1:
        return ParseResult(ParseStatus.INVALID, raw, error="pay_cnt_non_positive")
    return ParseResult(ParseStatus.VALID, raw, value=n)
