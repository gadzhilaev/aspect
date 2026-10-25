from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)


class VerifyEmailIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=16)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserPreferencesIn(BaseModel):
    language: str | None = Field(default=None, pattern=r"^(ru|en)$")
    theme_mode: str | None = Field(default=None, pattern=r"^(light|dark|system)$")
    # True only after onboarding reaches main — until then email can be re-used.
    registration_complete: bool | None = None


class DeleteAccountIn(BaseModel):
    """Подтверждение личности паролем. Компании не удаляются автоматически."""

    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    email_verified_at: datetime | None
    companies: list[dict] = []
    preferences: dict[str, Any] = {}
