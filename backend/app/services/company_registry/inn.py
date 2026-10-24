"""Russian INN (ИНН) validation — string-safe, control-digit checked.

A 10-digit INN belongs to a legal entity; a 12-digit INN belongs to a person
(often an individual entrepreneur / ИП). Length alone does NOT prove IE status —
only the registry record (type=INDIVIDUAL) does. Here ``inn_kind`` is a syntactic
classification by length, not a legal claim.
"""

from __future__ import annotations

from dataclasses import dataclass

# Control-digit coefficients (ФНС algorithm).
_W11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)


class InnValidationError(Exception):
    """Raised for syntactically invalid INN. ``reason`` is a stable machine code."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class NormalizedInn:
    inn: str
    length: int
    # "legal" for 10 digits, "individual" for 12 digits — syntactic only.
    inn_kind: str


def _control_digit(digits: list[int], weights: tuple[int, ...]) -> int:
    total = sum(d * w for d, w in zip(digits, weights))
    return (total % 11) % 10


def normalize_inn(raw: object) -> NormalizedInn:
    """Return a NormalizedInn or raise InnValidationError.

    - Outer whitespace is trimmed; leading zeros are preserved (string).
    - Only 10 or 12 digits accepted; letters / inner junk / wrong length rejected.
    - Control digits must match.
    """
    if raw is None:
        raise InnValidationError("empty", "Укажите ИНН")
    value = str(raw).strip()
    if not value:
        raise InnValidationError("empty", "Укажите ИНН")
    if not value.isdigit():
        raise InnValidationError(
            "non_digit",
            "ИНН состоит только из цифр (10 для организации, 12 для ИП/физлица)",
        )
    length = len(value)
    if length not in (10, 12):
        raise InnValidationError(
            "bad_length",
            "ИНН должен содержать 10 цифр (организация) или 12 цифр (ИП/физлицо)",
        )
    digits = [int(ch) for ch in value]
    if length == 10:
        if _control_digit(digits[:9], _W10) != digits[9]:
            raise InnValidationError("bad_checksum", "Контрольная цифра ИНН не совпадает")
        return NormalizedInn(inn=value, length=10, inn_kind="legal")
    # length == 12
    c11 = _control_digit(digits[:10], _W11)
    c12 = _control_digit(digits[:11], _W12)
    if c11 != digits[10] or c12 != digits[11]:
        raise InnValidationError("bad_checksum", "Контрольные цифры ИНН не совпадают")
    return NormalizedInn(inn=value, length=12, inn_kind="individual")
