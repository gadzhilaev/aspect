from collections.abc import Generator

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_token
from app.db.session import get_db
from app.models import CompanyMembership, User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User:
    if credentials is None:
        raise AppError("UNAUTHORIZED", "Требуется авторизация", 401)
    try:
        payload = decode_token(credentials.credentials, "access")
    except ValueError as exc:
        raise AppError("UNAUTHORIZED", "Недействительный токен", 401) from exc
    user = db.get(User, payload["sub"])
    if user is None:
        raise AppError("UNAUTHORIZED", "Пользователь не найден", 401)
    return user


def require_company_member(
    company_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompanyMembership:
    membership = (
        db.query(CompanyMembership)
        .filter(
            CompanyMembership.company_id == company_id,
            CompanyMembership.user_id == user.id,
        )
        .first()
    )
    if membership is None:
        raise AppError("FORBIDDEN", "Нет доступа к этой компании", 403)
    return membership


def optional_telegram_secret(
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> str | None:
    return x_telegram_bot_api_secret_token
