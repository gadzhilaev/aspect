"""Public diagnostics from mobile/web clients (no auth required)."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.client_error_report import ClientErrorReport
from app.schemas.diagnostics import ClientErrorReportIn, ClientErrorReportOut

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

_RATE_WINDOW_SEC = 60.0
_RATE_MAX_PER_IP = 30
_rate_buckets: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return "unknown"


def _rate_limit(ip: str) -> None:
    now = time.monotonic()
    bucket = _rate_buckets[ip]
    cutoff = now - _RATE_WINDOW_SEC
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= _RATE_MAX_PER_IP:
        raise AppError("RATE_LIMITED", "Слишком много отчётов, попробуйте позже", 429)
    bucket.append(now)


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return "password" in k or k in {"authorization", "refresh_token", "access_token"}


def _scrub_value(value: object) -> object:
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for k, v in value.items():
            if _is_sensitive_key(str(k)):
                out[str(k)] = "(redacted)"
            else:
                out[str(k)] = _scrub_value(v)
        return out
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    return value


def _scrub_details(details: dict | None) -> dict | None:
    if not details:
        return None
    return _scrub_value(details)  # type: ignore[return-value]


@router.post("/client-error", response_model=ClientErrorReportOut)
def report_client_error(
    body: ClientErrorReportIn,
    request: Request,
    db: Session = Depends(get_db),
) -> ClientErrorReportOut:
    ip = _client_ip(request)
    _rate_limit(ip)

    details = _scrub_details(body.details)
    details_json = json.dumps(details, ensure_ascii=False) if details is not None else None

    row_id = str(uuid4())
    row = ClientErrorReport(
        id=row_id,
        source=body.source.strip()[:16],
        screen=(body.screen.strip()[:64] if body.screen else None),
        message=body.message.strip()[:8000],
        exception_type=(body.exception_type.strip()[:255] if body.exception_type else None),
        stack=(body.stack[:32000] if body.stack else None),
        http_status=body.http_status,
        http_code=(body.http_code.strip()[:64] if body.http_code else None),
        url=(body.url.strip()[:2048] if body.url else None),
        method=(body.method.strip()[:16].upper() if body.method else None),
        details_json=details_json,
        app_version=(body.app_version.strip()[:64] if body.app_version else None),
        platform=(body.platform.strip()[:64] if body.platform else None),
        device_info=(body.device_info.strip()[:512] if body.device_info else None),
        email_attempted=(body.email_attempted.strip()[:320] if body.email_attempted else None),
        client_ip=ip,
    )
    db.add(row)
    db.commit()

    logger.info(
        "client_error_report id=%s source=%s screen=%s status=%s code=%s ip=%s email=%s msg=%s",
        row_id,
        row.source,
        row.screen,
        row.http_status,
        row.http_code,
        ip,
        row.email_attempted or "-",
        row.message[:500],
    )
    return ClientErrorReportOut(id=row_id, accepted=True)
