"""Authorized read-only bank materials API (stage 2.12). No search, no writes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models import User
from app.models.bank_materials import BankDocumentFile
from app.schemas.bank_materials import BankDocumentOut, BankFragmentOut
from app.services.bank_materials.access import (
    build_document_out,
    build_fragment_out,
    file_has_allowed_run,
    require_bank_materials_configured,
    resolve_pdf_path_for_file,
    safe_download_filename,
    scope_from_settings,
    verify_pdf_sha256,
)

router = APIRouter(tags=["bank-materials"])


@router.get(
    "/bank-materials/documents/{document_id}",
    response_model=BankDocumentOut,
    summary="Bank document metadata (scoped)",
)
def get_bank_document(
    document_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BankDocumentOut:
    scope = scope_from_settings()
    return build_document_out(db, document_id=document_id, scope=scope)


@router.get(
    "/bank-materials/fragments/{fragment_id}",
    response_model=BankFragmentOut,
    summary="Bank fragment detail (scoped)",
)
def get_bank_fragment(
    fragment_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BankFragmentOut:
    scope = scope_from_settings()
    return build_fragment_out(db, fragment_id=fragment_id, scope=scope)


@router.get(
    "/bank-materials/files/{file_id}/content",
    summary="Original bank PDF (scoped)",
    response_class=FileResponse,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Original PDF bytes",
        }
    },
)
def get_bank_file_content(
    file_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> FileResponse:
    scope = scope_from_settings()
    require_bank_materials_configured(scope)

    file = db.get(BankDocumentFile, file_id)
    if file is None or not file_has_allowed_run(db, file_id=file_id, scope=scope):
        raise AppError("NOT_FOUND", "Материал не найден", 404)

    path = resolve_pdf_path_for_file(file=file, scope=scope)
    verify_pdf_sha256(path=path, expected_sha256=file.sha256)

    filename = safe_download_filename(file.original_filename)
    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="attachment",
    )
