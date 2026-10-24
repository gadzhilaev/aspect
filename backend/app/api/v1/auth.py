from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models import Company, CompanyMembership, EmailVerification, User
from app.schemas.auth import (
    ChangePasswordIn,
    LoginIn,
    RefreshIn,
    RegisterIn,
    UserOut,
    UserPreferencesIn,
    VerifyEmailIn,
)
from app.schemas.common import MessageOut, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])
# /me includes profile_status for CTA routing on web/mobile.


def _user_companies(db: Session, user: User) -> list[dict]:
    memberships = (
        db.query(CompanyMembership).filter(CompanyMembership.user_id == user.id).all()
    )
    companies: list[dict] = []
    for m in memberships:
        company = db.get(Company, m.company_id)
        companies.append(
            {
                "company_id": m.company_id,
                "role": m.role,
                "name": company.name if company else None,
                "profile_status": company.profile_status if company else "draft",
            }
        )
    return companies


def _prefs(user: User) -> dict:
    raw = getattr(user, "preferences_json", None) or {}
    return dict(raw) if isinstance(raw, dict) else {}


@router.post("/register", response_model=MessageOut)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> MessageOut:
    existing = db.query(User).filter(User.email == body.email.lower()).first()
    if existing:
        raise AppError("CONFLICT", "Пользователь с таким email уже существует", 409)

    user = User(
        id=str(uuid4()),
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        email_verified_at=None,
        preferences_json={},
    )
    db.add(user)

    settings = get_settings()
    code = settings.demo_email_code if settings.app_env != "production" else f"{uuid4().int % 10**6:06d}"
    db.add(
        EmailVerification(
            id=str(uuid4()),
            email=user.email,
            code=code,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            note="demo_code" if settings.app_env != "production" else None,
        )
    )
    db.commit()
    return MessageOut(
        message="Аккаунт создан. Подтвердите email кодом.",
        details={"email": user.email, "demo_code": code if settings.debug else None},
    )


@router.post("/verify-email", response_model=MessageOut)
def verify_email(body: VerifyEmailIn, db: Session = Depends(get_db)) -> MessageOut:
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user is None:
        raise AppError("NOT_FOUND", "Пользователь не найден", 404)
    row = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.email == body.email.lower(),
            EmailVerification.code == body.code,
            EmailVerification.consumed_at.is_(None),
        )
        .order_by(EmailVerification.created_at.desc())
        .first()
    )
    if row is None:
        raise AppError("INVALID_CODE", "Неверный код подтверждения", 400)
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise AppError("CODE_EXPIRED", "Срок действия кода истёк", 400)
    row.consumed_at = datetime.now(timezone.utc)
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    return MessageOut(message="Email подтверждён")


@router.post("/login", response_model=TokenPair)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenPair:
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Неверный email или пароль", 401)
    if user.email_verified_at is None:
        raise AppError("EMAIL_NOT_VERIFIED", "Сначала подтвердите email", 403)
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshIn) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token, "refresh")
    except ValueError as exc:
        raise AppError("UNAUTHORIZED", "Недействительный refresh token", 401) from exc
    return TokenPair(
        access_token=create_access_token(payload["sub"]),
        refresh_token=create_refresh_token(payload["sub"]),
    )


@users_router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        email_verified_at=user.email_verified_at,
        companies=_user_companies(db, user),
        preferences=_prefs(user),
    )


@users_router.patch("/me/preferences", response_model=UserOut)
def patch_preferences(
    body: UserPreferencesIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    prefs = _prefs(user)
    if body.language is not None:
        prefs["language"] = body.language
    if body.theme_mode is not None:
        prefs["theme_mode"] = body.theme_mode
    user.preferences_json = prefs
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        email_verified_at=user.email_verified_at,
        companies=_user_companies(db, user),
        preferences=_prefs(user),
    )


@users_router.post("/me/change-password", response_model=MessageOut)
def change_password(
    body: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageOut:
    if not verify_password(body.current_password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Неверный текущий пароль", 401)
    if body.current_password == body.new_password:
        raise AppError("VALIDATION_ERROR", "Новый пароль совпадает с текущим", 422)
    user.password_hash = hash_password(body.new_password)
    db.add(user)
    db.commit()
    return MessageOut(message="Пароль обновлён")


@users_router.delete("/me", response_model=MessageOut)
def delete_account(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageOut:
    """Удаляет аккаунт пользователя и его memberships (компании владельца не удаляются массово)."""
    memberships = (
        db.query(CompanyMembership).filter(CompanyMembership.user_id == user.id).all()
    )
    for m in memberships:
        db.delete(m)
    db.query(EmailVerification).filter(EmailVerification.email == user.email).delete(
        synchronize_session=False
    )
    db.delete(user)
    db.commit()
    return MessageOut(message="Аккаунт удалён")
