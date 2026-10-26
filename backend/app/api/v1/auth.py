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
from app.models.assistant import AssistantConversation
from app.models.company_registry import CompanyRegistryLookup
from app.models.decision import ActionItem, Decision
from app.models.notification import (
    NotificationOutbox,
    NotificationSubscription,
    TelegramLinkToken,
)
from app.models.solution import Scenario
from app.schemas.auth import (
    ChangePasswordIn,
    DeleteAccountIn,
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


def _email_reserved(user: User) -> bool:
    """Почта занята только после открытия главного экрана (registration_complete).

    Черновики онбординга (даже с кодом/компанией) можно перерегистрировать.
    """
    return bool(_prefs(user).get("registration_complete"))


@router.post("/register", response_model=MessageOut)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> MessageOut:
    email = body.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    # Почта «занята» только после главного экрана.
    # Незавершённую заявку можно перезаписать.
    if existing is not None and _email_reserved(existing):
        raise AppError("CONFLICT", "Пользователь с таким email уже существует", 409)

    now = datetime.now(timezone.utc)
    if existing is not None:
        user = existing
        user.password_hash = hash_password(body.password)
        user.display_name = body.display_name
        user.email_verified_at = now
        user.preferences_json = {}
        db.query(EmailVerification).filter(EmailVerification.email == email).delete(
            synchronize_session=False
        )
    else:
        user = User(
            id=str(uuid4()),
            email=email,
            password_hash=hash_password(body.password),
            display_name=body.display_name,
            email_verified_at=now,
            preferences_json={},
        )
        db.add(user)

    # Подтверждение email кодом отключено (хакатон / без SMTP).
    db.query(EmailVerification).filter(EmailVerification.email == email).delete(
        synchronize_session=False
    )
    db.commit()
    return MessageOut(
        message="Аккаунт создан.",
        details={"email": user.email, "email_verified": True},
    )


@router.post("/verify-email", response_model=MessageOut)
def verify_email(body: VerifyEmailIn, db: Session = Depends(get_db)) -> MessageOut:
    settings = get_settings()
    email = body.email.lower().strip()
    code = "".join(c for c in (body.code or "") if c.isdigit())
    demo = "".join(c for c in (settings.demo_email_code or "") if c.isdigit()) or "123456"

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise AppError("NOT_FOUND", "Пользователь не найден", 404)

    row = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.email == email,
            EmailVerification.code == code,
            EmailVerification.consumed_at.is_(None),
        )
        .order_by(EmailVerification.created_at.desc())
        .first()
    )
    # DEBUG / competition: принимаем demo-код даже если в БД ещё старый random OTP.
    if row is None and code == demo and (settings.debug or settings.competition_mode):
        row = (
            db.query(EmailVerification)
            .filter(
                EmailVerification.email == email,
                EmailVerification.consumed_at.is_(None),
            )
            .order_by(EmailVerification.created_at.desc())
            .first()
        )
        if row is not None:
            row.code = demo
            row.note = "demo_code"
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
    # Email OTP отключён — если аккаунт ещё без verified_at, подтверждаем при логине.
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()
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
    if body.registration_complete is not None:
        prefs["registration_complete"] = bool(body.registration_complete)
    if body.job_role is not None:
        role = body.job_role.strip()
        if role:
            prefs["job_role"] = role
        else:
            prefs.pop("job_role", None)
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


def _sole_owned_companies(db: Session, user_id: str) -> list[dict]:
    """Companies where this user is an owner and no other owner remains."""
    owned = (
        db.query(CompanyMembership)
        .filter(
            CompanyMembership.user_id == user_id,
            CompanyMembership.role == "owner",
        )
        .all()
    )
    blocked: list[dict] = []
    for m in owned:
        other_owners = (
            db.query(CompanyMembership)
            .filter(
                CompanyMembership.company_id == m.company_id,
                CompanyMembership.role == "owner",
                CompanyMembership.user_id != user_id,
            )
            .count()
        )
        if other_owners == 0:
            company = db.get(Company, m.company_id)
            blocked.append(
                {
                    "company_id": m.company_id,
                    "name": company.name if company else None,
                }
            )
    return blocked


@users_router.post("/me/change-password", response_model=MessageOut)
def change_password(
    body: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageOut:
    # Passwords are never logged (body fields not passed to logger).
    if not verify_password(body.current_password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Неверный текущий пароль", 401)
    if body.current_password == body.new_password:
        raise AppError("VALIDATION_ERROR", "Новый пароль совпадает с текущим", 422)
    if len(body.new_password) < 8:
        raise AppError("VALIDATION_ERROR", "Новый пароль слишком короткий", 422)
    user.password_hash = hash_password(body.new_password)
    db.add(user)
    db.commit()
    # JWT is stateless: previously issued access/refresh tokens remain valid until
    # natural expiry. Clients must discard local tokens after this call.
    return MessageOut(
        message="Пароль обновлён",
        details={
            "token_policy": (
                "Existing access/refresh JWTs stay valid until expiry; "
                "client must clear stored tokens and re-login."
            )
        },
    )


@users_router.delete("/me", response_model=MessageOut)
def delete_account(
    body: DeleteAccountIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageOut:
    """Delete the authenticated user only.

    Does **not** delete companies. If the user is the sole owner of any company,
    deletion is refused (product decision required: transfer ownership / archive).
    """
    if not verify_password(body.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Неверный пароль", 401)

    blocked = _sole_owned_companies(db, user.id)
    if blocked:
        raise AppError(
            "SOLE_OWNER",
            "Нельзя удалить аккаунт: вы единственный владелец компании. "
            "Сначала передайте владение другому участнику или запросите "
            "архивацию компании у оператора стенда.",
            409,
            details=blocked,
        )

    user_id = user.id
    email = user.email

    # Audit rows with NOT NULL created_by — do not destroy company history silently.
    decision_n = (
        db.query(Decision).filter(Decision.created_by == user_id).count()
    )
    scenario_n = (
        db.query(Scenario).filter(Scenario.created_by == user_id).count()
    )
    if decision_n or scenario_n:
        raise AppError(
            "HAS_AUDIT_RECORDS",
            "Нельзя удалить аккаунт: есть решения или сценарии, созданные вами. "
            "Нужно продуктовое решение по передаче/анонимизации аудита "
            "(компании и записи других пользователей не трогаем).",
            409,
            details=[
                {"decisions_created": decision_n, "scenarios_created": scenario_n}
            ],
        )

    # Telegram: unlink subscriptions, drop pending tokens/outbox rows for this user.
    subs = (
        db.query(NotificationSubscription)
        .filter(NotificationSubscription.user_id == user_id)
        .all()
    )
    sub_ids = [s.id for s in subs]
    if sub_ids:
        db.query(NotificationOutbox).filter(
            NotificationOutbox.subscription_id.in_(sub_ids),
            NotificationOutbox.status.in_(("pending", "retry")),
        ).delete(synchronize_session=False)
    for s in subs:
        db.delete(s)
    db.query(TelegramLinkToken).filter(TelegramLinkToken.user_id == user_id).delete(
        synchronize_session=False
    )

    # Nullable FKs — clear, do not delete shared company rows.
    db.query(Company).filter(Company.created_by == user_id).update(
        {Company.created_by: None}, synchronize_session=False
    )
    db.query(Decision).filter(Decision.cancelled_by_user_id == user_id).update(
        {Decision.cancelled_by_user_id: None}, synchronize_session=False
    )
    db.query(ActionItem).filter(ActionItem.assignee_user_id == user_id).update(
        {ActionItem.assignee_user_id: None}, synchronize_session=False
    )

    db.query(CompanyRegistryLookup).filter(
        CompanyRegistryLookup.user_id == user_id
    ).delete(synchronize_session=False)
    # ORM delete so assistant message/tool cascades apply.
    for conv in (
        db.query(AssistantConversation)
        .filter(AssistantConversation.user_id == user_id)
        .all()
    ):
        db.delete(conv)

    memberships = (
        db.query(CompanyMembership).filter(CompanyMembership.user_id == user_id).all()
    )
    for m in memberships:
        db.delete(m)

    db.query(EmailVerification).filter(EmailVerification.email == email).delete(
        synchronize_session=False
    )
    db.delete(user)
    db.commit()
    # After delete, Bearer tokens still decode until expiry but /users/me → 401
    # (user missing). No server-side denylist in this MVP.
    return MessageOut(
        message="Аккаунт удалён",
        details={
            "token_policy": (
                "JWTs are not revoked server-side; subsequent authenticated "
                "calls fail because the user no longer exists."
            ),
            "companies_policy": "Shared companies and other members were preserved.",
        },
    )
