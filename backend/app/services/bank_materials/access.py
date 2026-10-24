"""Stub access helpers — bank corpus not shipped with mobile backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.bank_materials import BankDocumentFile


class _Scope:
    """Minimal stand-in for OCR/corpus scope settings."""

    configured: bool = False
    root: Path | None = None


def scope_from_settings() -> _Scope:
    return _Scope()


def require_bank_materials_configured(scope: _Scope) -> None:
    if not scope.configured:
        raise AppError(
            "NOT_CONFIGURED",
            "Банковские материалы не подключены в этом пакете бэкенда",
            503,
        )


def build_document_out(
    db: Session, *, document_id: str, scope: _Scope
) -> Any:
    del db, document_id, scope
    raise AppError(
        "NOT_CONFIGURED",
        "Банковские материалы не подключены в этом пакете бэкенда",
        503,
    )


def build_fragment_out(
    db: Session, *, fragment_id: str, scope: _Scope
) -> Any:
    del db, fragment_id, scope
    raise AppError(
        "NOT_CONFIGURED",
        "Банковские материалы не подключены в этом пакете бэкенда",
        503,
    )


def file_has_allowed_run(db: Session, *, file_id: str, scope: _Scope) -> bool:
    del db, file_id, scope
    return False


def resolve_pdf_path_for_file(*, file: BankDocumentFile, scope: _Scope) -> Path:
    del file, scope
    raise AppError(
        "NOT_CONFIGURED",
        "Банковские материалы не подключены в этом пакете бэкенда",
        503,
    )


def verify_pdf_sha256(*, path: Path, expected_sha256: str) -> None:
    del path, expected_sha256


def safe_download_filename(name: str | None) -> str:
    raw = (name or "document.pdf").strip() or "document.pdf"
    return raw.replace("/", "_").replace("\\", "_")
