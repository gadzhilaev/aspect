"""Streaming CSV helpers for case dry-run / future import (no DB writes)."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class FileRole(str, Enum):
    COMPANIES = "companies"
    PAYMENTS = "payments"
    PERSON_LINKS = "person_links"
    UNKNOWN = "unknown"


REQUIRED_COLUMNS: dict[FileRole, frozenset[str]] = {
    FileRole.COMPANIES: frozenset(
        {
            "SYNTHETIC_U",
            "ORG_TYPE",
            "OKFS_NAME",
            "COMPANY_AGE_YEARS_GRADATION",
            "ECO_MARK_LABEL",
            "MAINOKVED_CODE",
            "MAINOKVED_NAME",
            "NEGATIVEMARK",
            "AMOUNT_WORKERS_FNS_GRADATION",
            "AMOUNT_WORKERS_SPARK_GRADATION",
            "CL_TYPE",
            "CL_PRODUCT_RKO_MARK",
            "CL_PRODUCT_GAR_MARK",
            "CL_PRODUCT_LOA_MARK",
            "CL_PRODUCT_LEA_MARK",
            "CL_PRODUCT_DEP_MARK",
            "CL_PRODUCT_ZPP_MARK",
            "FTS_FLAG",
            "FTS_COUNTRY_NAME",
            "FACTORING_MARK",
            "REVENUE_COMPANY",
            "GROUP_ID",
            "CITY",
            "REGION",
        }
    ),
    FileRole.PAYMENTS: frozenset({"BENEFICIARY", "PAYER", "PAY_AMT", "PAY_CNT"}),
    FileRole.PERSON_LINKS: frozenset({"SYNTHETIC_F", "CITY_NAME", "RC_NAME", "SYNTHETIC_U"}),
}

# Signature columns used to pick a role when filenames vary.
_ROLE_SIGNATURES: list[tuple[FileRole, frozenset[str]]] = [
    (FileRole.PAYMENTS, frozenset({"BENEFICIARY", "PAYER", "PAY_AMT", "PAY_CNT"})),
    (FileRole.PERSON_LINKS, frozenset({"SYNTHETIC_F", "SYNTHETIC_U", "RC_NAME"})),
    (FileRole.COMPANIES, frozenset({"SYNTHETIC_U", "REVENUE_COMPANY", "GROUP_ID", "MAINOKVED_CODE"})),
]


@dataclass(frozen=True, slots=True)
class CsvFileInfo:
    path: Path
    role: FileRole
    sha256: str
    byte_size: int
    fieldnames: list[str]
    missing_columns: list[str]
    duplicate_headers: list[str]


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return h.hexdigest(), size


def detect_role(fieldnames: list[str]) -> FileRole:
    cols = {c.strip() for c in fieldnames if c is not None}
    for role, sig in _ROLE_SIGNATURES:
        if sig.issubset(cols):
            return role
    return FileRole.UNKNOWN


def inspect_csv_header(path: Path) -> CsvFileInfo:
    sha, size = sha256_file(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        try:
            header = next(reader)
        except StopIteration:
            return CsvFileInfo(
                path=path,
                role=FileRole.UNKNOWN,
                sha256=sha,
                byte_size=size,
                fieldnames=[],
                missing_columns=[],
                duplicate_headers=[],
            )

    fieldnames = [(c or "").strip() for c in header]
    seen: dict[str, int] = {}
    dupes: list[str] = []
    for name in fieldnames:
        seen[name] = seen.get(name, 0) + 1
    for name, cnt in seen.items():
        if name and cnt > 1:
            dupes.append(name)

    role = detect_role(fieldnames)
    required = REQUIRED_COLUMNS.get(role, frozenset())
    missing = sorted(required - set(fieldnames))
    return CsvFileInfo(
        path=path,
        role=role,
        sha256=sha,
        byte_size=size,
        fieldnames=fieldnames,
        missing_columns=missing,
        duplicate_headers=sorted(dupes),
    )


@dataclass(frozen=True, slots=True)
class CsvRow:
    """One logical CSV data record (quoted newlines stay in the same record)."""

    record_number: int  # 1-based data record after header
    values: dict[str, str]


def iter_csv_rows(path: Path) -> Iterator[CsvRow]:
    """Stream DictReader rows; record_number counts logical records, not physical lines.

    A newline inside a quoted field does not increment record_number.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";", restkey="_extra", restval="")
        if not reader.fieldnames:
            return
        fieldnames = [(c or "").strip() for c in reader.fieldnames]
        for idx, row in enumerate(reader, start=1):
            if row.get("_extra"):
                # Extra columns beyond header — still yield; caller may flag.
                pass
            values: dict[str, str] = {}
            for name in fieldnames:
                raw = row.get(name)
                values[name] = "" if raw is None else str(raw)
            yield CsvRow(record_number=idx, values=values)


def payment_content_sha256(beneficiary: str, payer: str, pay_amt_raw: str, pay_cnt_raw: str) -> str:
    payload = f"{beneficiary}\0{payer}\0{pay_amt_raw}\0{pay_cnt_raw}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def catalog_conflict_fingerprint(values: dict[str, str]) -> str:
    """Hash of business fields used to detect conflicting duplicate UIDs."""
    keys = [
        "ORG_TYPE",
        "OKFS_NAME",
        "COMPANY_AGE_YEARS_GRADATION",
        "ECO_MARK_LABEL",
        "MAINOKVED_CODE",
        "MAINOKVED_NAME",
        "NEGATIVEMARK",
        "AMOUNT_WORKERS_FNS_GRADATION",
        "AMOUNT_WORKERS_SPARK_GRADATION",
        "CL_TYPE",
        "CL_PRODUCT_RKO_MARK",
        "CL_PRODUCT_GAR_MARK",
        "CL_PRODUCT_LOA_MARK",
        "CL_PRODUCT_LEA_MARK",
        "CL_PRODUCT_DEP_MARK",
        "CL_PRODUCT_ZPP_MARK",
        "FTS_FLAG",
        "FTS_COUNTRY_NAME",
        "FACTORING_MARK",
        "REVENUE_COMPANY",
        "GROUP_ID",
        "CITY",
        "REGION",
    ]
    parts = [f"{k}={values.get(k, '')}" for k in keys]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
